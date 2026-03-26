from decimal import Decimal

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import F, Q, Sum
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import DriverFleetMembership, Fleet, FleetPhoneBinding
from accounts.roles import get_request_fleet_binding, meets_min_role
from audit.services import begin_idempotent_request, finalize_idempotent_request, log_audit
from ledger.models import LedgerAccount, LedgerEntry
from ledger.services import (
    create_ledger_entry,
    ensure_opening_entry,
    get_account_balance,
    get_or_create_driver_available_account,
    get_or_create_fleet_reserve_account,
    get_or_create_user_ledger_account,
    record_driver_withdrawal_hold,
)
from payments.models import InternalTransfer
from integrations.models import ProviderConnection
from integrations.services import sync_bog_deposits
from .models import BankAccount, Deposit, IncomingBankTransfer, Wallet, WithdrawalRequest
from .serializers import (
    BankAccountSerializer,
    DepositInstructionSerializer,
    DepositSerializer,
    DepositSyncRequestSerializer,
    IncomingBankTransferMatchSerializer,
    IncomingBankTransferSerializer,
    OwnerFleetSummarySerializer,
    WalletTopUpSerializer,
    TransactionFeedSerializer,
    WalletSerializer,
    WithdrawalCreateSerializer,
    WithdrawalSerializer,
    WithdrawalStatusUpdateSerializer,
)
from .services import build_fleet_deposit_reference, complete_fleet_bank_deposit


def _transaction_kind(entry_type):
    if entry_type.startswith("bank_deposit"):
        return "deposit"
    if entry_type.startswith("withdrawal"):
        return "withdrawal"
    if entry_type.startswith("internal_transfer"):
        return "internal_transfer"
    return "adjustment"


def _transaction_status(entry, transfer_statuses, withdrawal_statuses):
    if entry.reference_type == "internal_transfer":
        return transfer_statuses.get(entry.reference_id, "completed")
    if entry.reference_type == "withdrawal":
        return withdrawal_statuses.get(entry.reference_id, "pending")
    if entry.entry_type.endswith("failed") or entry.entry_type.endswith("reversal"):
        return "failed"
    return "completed"


def _get_active_fleet_bog_connection(*, fleet):
    bindings = FleetPhoneBinding.objects.filter(
        fleet=fleet,
        is_active=True,
        user__is_active=True,
        role__in=[FleetPhoneBinding.Role.OWNER, FleetPhoneBinding.Role.ADMIN],
    ).order_by("-role", "created_at", "id")
    for fleet_binding in bindings:
        connection = (
            ProviderConnection.objects.filter(
                user=fleet_binding.user,
                provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            )
            .order_by("id")
            .first()
        )
        if connection is not None:
            return connection
    return None


def _fleet_transfer_review_queryset(*, fleet):
    reference_code = build_fleet_deposit_reference(fleet)
    return IncomingBankTransfer.objects.filter(
        provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
        match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
    ).filter(
        Q(fleet=fleet) | Q(reference_text__icontains=reference_code)
    )


class BalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        driver_membership = (
            DriverFleetMembership.objects.select_related("fleet")
            .filter(user=request.user, is_active=True)
            .first()
        )
        if driver_membership is not None:
            driver_account = get_or_create_driver_available_account(
                request.user,
                fleet=driver_membership.fleet,
                currency=wallet.currency,
            )
            driver_balance = get_account_balance(driver_account, wallet.currency)
            return Response(
                {
                    "balance": str(driver_balance),
                    "currency": wallet.currency,
                    "updated_at": wallet.updated_at,
                }
            )
        ledger_account = get_or_create_user_ledger_account(request.user, wallet.currency)
        ensure_opening_entry(ledger_account, wallet.balance, created_by=request.user)
        ledger_balance = get_account_balance(ledger_account, wallet.currency)

        if wallet.balance != ledger_balance:
            wallet.balance = ledger_balance
            wallet.save(update_fields=["balance", "updated_at"])

        return Response(WalletSerializer(wallet).data)


class BankAccountListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BankAccountSerializer

    def get_queryset(self):
        return BankAccount.objects.filter(user=self.request.user, is_active=True)

    def perform_create(self, serializer):
        binding = get_request_fleet_binding(user=self.request.user, request=self.request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.DRIVER):
            raise PermissionError("Only active fleet members can add bank accounts.")
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)


class TransactionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        ledger_account = get_or_create_user_ledger_account(request.user, wallet.currency)
        ensure_opening_entry(ledger_account, wallet.balance, created_by=request.user)

        entries = (
            LedgerEntry.objects.filter(account=ledger_account, currency=wallet.currency)
            .exclude(entry_type="opening_balance")
            .order_by("-created_at", "-id")[:100]
        )

        transfer_ids = [
            int(entry.reference_id)
            for entry in entries
            if entry.reference_type == "internal_transfer" and entry.reference_id.isdigit()
        ]
        withdrawal_ids = [
            int(entry.reference_id)
            for entry in entries
            if entry.reference_type == "withdrawal" and entry.reference_id.isdigit()
        ]

        transfer_statuses = {
            str(item.id): item.status for item in InternalTransfer.objects.filter(id__in=transfer_ids)
        }
        withdrawal_statuses = {
            str(item.id): item.status for item in WithdrawalRequest.objects.filter(id__in=withdrawal_ids)
        }

        payload = [
            {
                "id": str(entry.id),
                "kind": _transaction_kind(entry.entry_type),
                "amount": entry.amount,
                "currency": entry.currency,
                "status": _transaction_status(entry, transfer_statuses, withdrawal_statuses),
                "description": entry.metadata.get("description", ""),
                "created_at": entry.created_at,
            }
            for entry in entries
        ]

        serializer = TransactionFeedSerializer(payload, many=True)
        return Response(serializer.data)


class WithdrawalCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.DRIVER):
            return Response({"detail": "Only active fleet members can create withdrawals."}, status=403)

        request_id = request.headers.get("X-Request-ID", "")
        idempotency_key = request.headers.get("Idempotency-Key", "")
        endpoint = "/api/wallet/withdrawals/"

        serializer = WithdrawalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bank_account_id = serializer.validated_data["bank_account_id"]
        amount = serializer.validated_data["amount"]
        note = serializer.validated_data.get("note", "")

        idempotency_record, replay_body, replay_status = begin_idempotent_request(
            user=request.user,
            method="POST",
            endpoint=endpoint,
            key=idempotency_key,
            payload=serializer.validated_data,
        )
        if replay_body is not None:
            return Response(replay_body, status=replay_status)

        bank_account = BankAccount.objects.filter(
            id=bank_account_id, user=request.user, is_active=True
        ).first()

        if bank_account is None:
            error_payload = {"detail": "Bank account not found."}
            finalize_idempotent_request(idempotency_record, status_code=404, response_body=error_payload)
            return Response(error_payload, status=status.HTTP_404_NOT_FOUND)

        if amount <= Decimal("0"):
            error_payload = {"detail": "Amount must be greater than zero."}
            finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
            return Response(error_payload, status=status.HTTP_400_BAD_REQUEST)

        driver_membership = (
            DriverFleetMembership.objects.select_related("fleet")
            .filter(user=request.user, is_active=True)
            .first()
        )
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        fee_amount = Decimal(str(getattr(settings, "WITHDRAWAL_FEE_FLAT", "2.00")))

        with db_transaction.atomic():
            if driver_membership is not None:
                driver_account = get_or_create_driver_available_account(
                    request.user,
                    fleet=driver_membership.fleet,
                    currency=wallet.currency,
                )
                fleet_reserve_account = get_or_create_fleet_reserve_account(
                    driver_membership.fleet,
                    currency=wallet.currency,
                )
                locked_accounts = LedgerAccount.objects.select_for_update().filter(
                    id__in=[driver_account.id, fleet_reserve_account.id]
                )
                locked_by_id = {account.id: account for account in locked_accounts}
                driver_balance = get_account_balance(locked_by_id[driver_account.id], wallet.currency)
                fleet_reserve_balance = get_account_balance(locked_by_id[fleet_reserve_account.id], wallet.currency)

                if amount > driver_balance:
                    error_payload = {"detail": "Insufficient driver available balance for this withdrawal."}
                    finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
                    return Response(error_payload, status=status.HTTP_400_BAD_REQUEST)

                if amount + fee_amount > fleet_reserve_balance:
                    error_payload = {"detail": "Insufficient fleet reserve balance for this withdrawal."}
                    finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
                    return Response(error_payload, status=status.HTTP_400_BAD_REQUEST)

                withdrawal = WithdrawalRequest.objects.create(
                    user=request.user,
                    wallet=wallet,
                    fleet=driver_membership.fleet,
                    bank_account=bank_account,
                    amount=amount,
                    fee_amount=fee_amount,
                    currency=wallet.currency,
                    status=WithdrawalRequest.Status.PENDING,
                    note=note,
                )

                record_driver_withdrawal_hold(
                    withdrawal=withdrawal,
                    fleet=driver_membership.fleet,
                    user=request.user,
                    amount=amount,
                    fee_amount=fee_amount,
                    created_by=request.user,
                    currency=wallet.currency,
                    metadata={
                        "bank_account_id": bank_account.id,
                        "description": f"Withdrawal to {bank_account.bank_name}",
                        "note": note,
                    },
                )
            else:
                ledger_account = get_or_create_user_ledger_account(request.user, wallet.currency)
                ensure_opening_entry(ledger_account, wallet.balance, created_by=request.user)
                locked_ledger_account = LedgerAccount.objects.select_for_update().get(id=ledger_account.id)
                current_balance = get_account_balance(locked_ledger_account, wallet.currency)

                if amount > current_balance:
                    error_payload = {"detail": "Insufficient wallet balance for this withdrawal."}
                    finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
                    return Response(
                        error_payload,
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                withdrawal = WithdrawalRequest.objects.create(
                    user=request.user,
                    wallet=wallet,
                    bank_account=bank_account,
                    amount=amount,
                    currency=wallet.currency,
                    status=WithdrawalRequest.Status.PENDING,
                    note=note,
                )

                create_ledger_entry(
                    account=locked_ledger_account,
                    amount=-amount,
                    entry_type="withdrawal_hold",
                    created_by=request.user,
                    reference_type="withdrawal",
                    reference_id=str(withdrawal.id),
                    metadata={
                        "bank_account_id": bank_account.id,
                        "description": f"Withdrawal to {bank_account.bank_name}",
                        "note": note,
                    },
                )

                wallet.balance = current_balance - amount
                wallet.save(update_fields=["balance", "updated_at"])

        response_payload = WithdrawalSerializer(withdrawal).data
        finalize_idempotent_request(idempotency_record, status_code=201, response_body=response_payload)
        log_audit(
            user=request.user,
            action="withdrawal_created",
            resource_type="withdrawal",
            resource_id=withdrawal.id,
            request_id=request_id,
            ip_address=request.META.get("REMOTE_ADDR"),
            metadata={"amount": str(amount), "currency": wallet.currency},
        )
        return Response(response_payload, status=status.HTTP_201_CREATED)


class WithdrawalListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawalSerializer

    def get_queryset(self):
        binding = get_request_fleet_binding(user=self.request.user, request=self.request)
        if meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.OPERATOR):
            return WithdrawalRequest.objects.filter(fleet=binding.fleet).select_related("bank_account").order_by("-created_at", "-id")
        if meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.DRIVER):
            return WithdrawalRequest.objects.filter(user=self.request.user).select_related("bank_account").order_by("-created_at", "-id")
        return WithdrawalRequest.objects.none()


class WithdrawalStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_status_write"

    def patch(self, request, withdrawal_id):
        if not request.user.is_staff:
            return Response({"detail": "Only staff users can update withdrawal status."}, status=403)

        serializer = WithdrawalStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_status = serializer.validated_data["status"]

        with db_transaction.atomic():
            withdrawal = (
                WithdrawalRequest.objects.select_for_update()
                .select_related("wallet", "wallet__user")
                .filter(id=withdrawal_id)
                .first()
            )
            if withdrawal is None:
                return Response({"detail": "Withdrawal not found."}, status=404)

            if withdrawal.status in [WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.FAILED]:
                return Response({"detail": "Withdrawal is already finalized."}, status=400)

            if target_status == withdrawal.status:
                return Response(WithdrawalSerializer(withdrawal).data, status=200)

            if target_status == WithdrawalRequest.Status.FAILED:
                if withdrawal.fleet_id:
                    from integrations.services import _reverse_withdrawal_to_wallet

                    _reverse_withdrawal_to_wallet(
                        withdrawal=withdrawal,
                        reason="Withdrawal failed, balances returned",
                        idempotency_key=f"withdrawal:status:reversal:{withdrawal.id}",
                        created_by=request.user,
                    )
                    return Response(WithdrawalSerializer(WithdrawalRequest.objects.get(id=withdrawal.id)).data, status=200)
                wallet = withdrawal.wallet
                ledger_account = get_or_create_user_ledger_account(wallet.user, wallet.currency)
                locked_ledger_account = LedgerAccount.objects.select_for_update().get(id=ledger_account.id)
                current_balance = get_account_balance(locked_ledger_account, wallet.currency)
                create_ledger_entry(
                    account=locked_ledger_account,
                    amount=withdrawal.amount,
                    entry_type="withdrawal_reversal",
                    created_by=request.user,
                    reference_type="withdrawal",
                    reference_id=str(withdrawal.id),
                    metadata={"description": "Withdrawal failed, amount returned to wallet"},
                )
                wallet.balance = current_balance + withdrawal.amount
                wallet.save(update_fields=["balance", "updated_at"])

            withdrawal.status = target_status
            withdrawal.save(update_fields=["status"])

        log_audit(
            user=request.user,
            action="withdrawal_status_updated",
            resource_type="withdrawal",
            resource_id=withdrawal.id,
            request_id=request.headers.get("X-Request-ID", ""),
            ip_address=request.META.get("REMOTE_ADDR"),
            metadata={"status": target_status},
        )
        return Response(WithdrawalSerializer(withdrawal).data, status=200)


class WalletTopUpView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can top up wallet balance."}, status=403)

        request_id = request.headers.get("X-Request-ID", "")
        idempotency_key = request.headers.get("Idempotency-Key", "")
        endpoint = "/api/wallet/top-up/"

        serializer = WalletTopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]
        note = serializer.validated_data.get("note", "")

        idempotency_record, replay_body, replay_status = begin_idempotent_request(
            user=request.user,
            method="POST",
            endpoint=endpoint,
            key=idempotency_key,
            payload=serializer.validated_data,
        )
        if replay_body is not None:
            return Response(replay_body, status=replay_status)

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        ledger_account = get_or_create_user_ledger_account(request.user, wallet.currency)
        ensure_opening_entry(ledger_account, wallet.balance, created_by=request.user)

        with db_transaction.atomic():
            locked_ledger_account = LedgerAccount.objects.select_for_update().get(id=ledger_account.id)
            create_ledger_entry(
                account=locked_ledger_account,
                amount=amount,
                entry_type="sandbox_topup",
                created_by=request.user,
                reference_type="wallet",
                reference_id=str(wallet.id),
                metadata={"description": "Sandbox top-up", "note": note},
            )

            wallet.balance = wallet.balance + amount
            wallet.save(update_fields=["balance", "updated_at"])

        response_payload = {"balance": str(wallet.balance), "currency": wallet.currency, "credited_amount": str(amount)}
        finalize_idempotent_request(idempotency_record, status_code=201, response_body=response_payload)
        log_audit(
            user=request.user,
            action="wallet_topped_up",
            resource_type="wallet",
            resource_id=wallet.id,
            request_id=request_id,
            ip_address=request.META.get("REMOTE_ADDR"),
            metadata={"amount": str(amount), "currency": wallet.currency, "note": note},
        )
        return Response(response_payload, status=status.HTTP_201_CREATED)


class DepositInstructionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if binding is None:
            return Response({"detail": "An active fleet is required to view deposit instructions."}, status=400)
        payload = {
            "bank_name": "Bank of Georgia",
            "account_holder_name": settings.BOG_PAYER_NAME or "",
            "account_number": settings.BOG_SOURCE_ACCOUNT_NUMBER or "",
            "currency": "GEL",
            "fleet_name": binding.fleet.name,
            "reference_code": build_fleet_deposit_reference(binding.fleet),
            "note": "Send a bank transfer to this account and include the exact fleet reference code.",
        }
        serializer = DepositInstructionSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OwnerFleetSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can view owner dashboard data."}, status=403)

        currency = "GEL"
        fleet_reserve_account = get_or_create_fleet_reserve_account(binding.fleet, currency=currency)
        reserve_balance = get_account_balance(fleet_reserve_account, currency)

        deposits = Deposit.objects.filter(fleet=binding.fleet, status=Deposit.Status.COMPLETED)
        total_funded = deposits.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        completed_withdrawals = WithdrawalRequest.objects.filter(
            fleet=binding.fleet,
            status=WithdrawalRequest.Status.COMPLETED,
        )
        total_withdrawn = completed_withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        billed_withdrawals = WithdrawalRequest.objects.filter(fleet=binding.fleet).exclude(
            status=WithdrawalRequest.Status.FAILED
        )
        total_fees = billed_withdrawals.aggregate(total=Sum("fee_amount"))["total"] or Decimal("0.00")

        pending_withdrawals = (
            WithdrawalRequest.objects.filter(
                fleet=binding.fleet,
                status__in=[WithdrawalRequest.Status.PENDING, WithdrawalRequest.Status.PROCESSING],
            )
            .select_related("user")
            .order_by("-created_at", "-id")
        )
        pending_payouts_total = (
            pending_withdrawals.aggregate(total=Sum(F("amount") + F("fee_amount")))["total"] or Decimal("0.00")
        )
        failed_withdrawals = WithdrawalRequest.objects.filter(
            fleet=binding.fleet,
            status=WithdrawalRequest.Status.FAILED,
        )
        failed_payouts_total = failed_withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        unmatched_deposits_count = _fleet_transfer_review_queryset(fleet=binding.fleet).count()

        pending_payouts = [
            {
                "id": item.id,
                "driver_name": item.user.get_full_name().strip() or item.user.username,
                "driver_username": item.user.username,
                "amount": item.amount,
                "fee_amount": item.fee_amount,
                "currency": item.currency,
                "status": item.status,
                "created_at": item.created_at,
            }
            for item in pending_withdrawals[:5]
        ]

        active_drivers_count = DriverFleetMembership.objects.filter(
            fleet=binding.fleet,
            is_active=True,
            user__is_active=True,
        ).count()

        serializer = OwnerFleetSummarySerializer(
            {
                "fleet_name": binding.fleet.name,
                "currency": currency,
                "reserve_balance": reserve_balance,
                "total_funded": total_funded,
                "total_withdrawn": total_withdrawn,
                "total_fees": total_fees,
                "pending_payouts_count": pending_withdrawals.count(),
                "pending_payouts_total": pending_payouts_total,
                "unmatched_deposits_count": unmatched_deposits_count,
                "failed_payouts_count": failed_withdrawals.count(),
                "failed_payouts_total": failed_payouts_total,
                "active_drivers_count": active_drivers_count,
                "pending_payouts": pending_payouts,
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class DepositListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DepositSerializer

    def get_queryset(self):
        binding = get_request_fleet_binding(user=self.request.user, request=self.request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Deposit.objects.none()
        return Deposit.objects.filter(fleet=binding.fleet).select_related("fleet")

    def list(self, request, *args, **kwargs):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can view fleet deposits."}, status=403)
        return super().list(request, *args, **kwargs)


class UnmatchedIncomingTransferListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IncomingBankTransferSerializer

    def get_queryset(self):
        binding = get_request_fleet_binding(user=self.request.user, request=self.request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return IncomingBankTransfer.objects.none()
        return _fleet_transfer_review_queryset(fleet=binding.fleet)

    def list(self, request, *args, **kwargs):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can review unmatched bank transfers."}, status=403)
        return super().list(request, *args, **kwargs)


class IncomingTransferManualMatchView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_write"

    def post(self, request, transfer_id):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can manually match bank transfers."}, status=403)

        fleet_name = (request.headers.get("X-Fleet-Name") or request.query_params.get("fleet_name") or "").strip()
        if not fleet_name:
            return Response({"detail": "Fleet name is required to match a transfer."}, status=400)

        serializer = IncomingBankTransferMatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested_fleet_name = serializer.validated_data.get("fleet_name", "").strip()
        if requested_fleet_name and requested_fleet_name.lower() != binding.fleet.name.lower():
            return Response({"detail": "You can only match incoming transfers to your active fleet."}, status=403)

        transfer = _fleet_transfer_review_queryset(fleet=binding.fleet).filter(id=transfer_id).first()
        if transfer is None:
            return Response({"detail": "Incoming transfer not found."}, status=404)
        if transfer.match_status != IncomingBankTransfer.MatchStatus.UNMATCHED:
            return Response({"detail": "Incoming transfer is already finalized."}, status=400)
        if transfer.amount <= Decimal("0.00"):
            return Response({"detail": "Only positive incoming transfers can be matched."}, status=400)

        target_fleet = binding.fleet

        transfer.user = request.user
        transfer.fleet = target_fleet
        transfer.match_status = IncomingBankTransfer.MatchStatus.MATCHED
        transfer.save(update_fields=["user", "fleet", "match_status", "updated_at"])

        deposit, _ = complete_fleet_bank_deposit(
            fleet=target_fleet,
            user=request.user,
            provider=transfer.provider,
            provider_transaction_id=transfer.provider_transaction_id,
            amount=transfer.amount,
            currency=transfer.currency,
            reference_code=build_fleet_deposit_reference(target_fleet),
            incoming_transfer=transfer,
            raw_payload=transfer.raw_payload,
            note=transfer.reference_text or "Manual deposit match",
            payer_name=transfer.payer_name,
            payer_inn=transfer.payer_inn,
            payer_account_number=transfer.payer_account_number,
        )

        log_audit(
            user=request.user,
            action="incoming_transfer_matched",
            resource_type="incoming_bank_transfer",
            resource_id=transfer.id,
            request_id=request.headers.get("X-Request-ID", ""),
            ip_address=request.META.get("REMOTE_ADDR"),
            metadata={
                "deposit_id": deposit.id,
                "fleet_name": target_fleet.name,
            },
        )

        return Response(
            {
                "transfer": IncomingBankTransferSerializer(transfer).data,
                "deposit": DepositSerializer(deposit).data,
            },
            status=status.HTTP_200_OK,
        )


class DepositSyncView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_status_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.OPERATOR):
            return Response({"detail": "Only operator/admin/owner can sync deposits from bank."}, status=403)

        serializer = DepositSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start_date = serializer.validated_data.get("start_date")
        end_date = serializer.validated_data.get("end_date")
        use_statement = bool(start_date and end_date)
        if use_statement and not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can run deposit backfill."}, status=403)

        connection = _get_active_fleet_bog_connection(fleet=binding.fleet)
        if connection is None:
            return Response({"detail": "Bank of Georgia connection is not configured."}, status=status.HTTP_400_BAD_REQUEST)

        result = sync_bog_deposits(
            connection=connection,
            use_statement=use_statement,
            start_date=start_date,
            end_date=end_date,
        )
        return Response(result, status=status.HTTP_200_OK)
