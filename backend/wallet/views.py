from datetime import timedelta
from decimal import Decimal
import logging

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
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
from integrations.models import ProviderConnection, YandexTransactionRecord
from integrations.services import BogPayoutPreflightError, submit_withdrawal_to_bog, sync_bog_deposits
from .models import BankAccount, Deposit, FleetRatingPenalty, IncomingBankTransfer, Wallet, WithdrawalRequest
from .serializers import (
    AdminNetworkSummarySerializer,
    BankAccountSerializer,
    DepositInstructionSerializer,
    DepositSerializer,
    DepositSyncRequestSerializer,
    IncomingBankTransferMatchSerializer,
    IncomingBankTransferSerializer,
    OwnerTransactionSerializer,
    OwnerFleetSummarySerializer,
    OwnerDriverFinanceSerializer,
    WalletTopUpSerializer,
    TransactionFeedSerializer,
    WalletSerializer,
    WithdrawalCreateSerializer,
    WithdrawalSerializer,
    WithdrawalStatusUpdateSerializer,
)
from .services import build_fleet_deposit_reference, complete_fleet_bank_deposit


logger = logging.getLogger(__name__)


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


def _get_active_fleet_yandex_connection(*, fleet):
    connection = (
        ProviderConnection.objects.filter(
            fleet=fleet,
            provider=ProviderConnection.Provider.YANDEX,
            status="active",
        )
        .order_by("-created_at", "id")
        .first()
    )
    if connection is not None:
        return connection

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
                provider=ProviderConnection.Provider.YANDEX,
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


def _fleet_rating_from_completed_withdrawals(*, completed_withdrawals_count, penalty_count=0):
    rating_value = (Decimal(completed_withdrawals_count // 5000) - Decimal(penalty_count)) / Decimal("10")
    return f"{rating_value:.1f}"


def _driver_level_from_completed_withdrawals(*, completed_withdrawals_count):
    return (completed_withdrawals_count // 100) + 1


def _driver_reward_from_completed_withdrawals(*, completed_withdrawals_count):
    if completed_withdrawals_count < 100:
        return "No reward yet"
    return "5 free withdrawals"


def _recent_duplicate_withdrawal(*, user, fleet, bank_account, amount, fee_amount, currency):
    duplicate_window_seconds = max(int(getattr(settings, "WITHDRAWAL_DUPLICATE_WINDOW_SECONDS", 30)), 0)
    if duplicate_window_seconds <= 0:
        return None

    cutoff = timezone.now() - timedelta(seconds=duplicate_window_seconds)
    return (
        WithdrawalRequest.objects.select_for_update()
        .filter(
            user=user,
            fleet=fleet,
            bank_account=bank_account,
            amount=amount,
            fee_amount=fee_amount,
            currency=currency,
            created_at__gte=cutoff,
        )
        .exclude(status=WithdrawalRequest.Status.FAILED)
        .order_by("-created_at", "-id")
        .first()
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
            driver_completed_withdrawals_count = WithdrawalRequest.objects.filter(
                user=request.user,
                fleet=driver_membership.fleet,
                status=WithdrawalRequest.Status.COMPLETED,
            ).count()
            completed_withdrawals_count = WithdrawalRequest.objects.filter(
                fleet=driver_membership.fleet,
                status=WithdrawalRequest.Status.COMPLETED,
            ).count()
            fleet_rating_penalty_count = FleetRatingPenalty.objects.filter(
                fleet=driver_membership.fleet,
                reason=FleetRatingPenalty.Reason.INSUFFICIENT_RESERVE,
            ).count()
            full_name = request.user.get_full_name().strip()
            return Response(
                {
                    "balance": str(driver_balance),
                    "currency": wallet.currency,
                    "updated_at": wallet.updated_at,
                    "fleet_rating": _fleet_rating_from_completed_withdrawals(
                        completed_withdrawals_count=completed_withdrawals_count,
                        penalty_count=fleet_rating_penalty_count,
                    ),
                    "fleet_completed_withdrawals": completed_withdrawals_count,
                    "driver_name": full_name or request.user.username,
                    "driver_level": _driver_level_from_completed_withdrawals(
                        completed_withdrawals_count=driver_completed_withdrawals_count
                    ),
                    "driver_reward": _driver_reward_from_completed_withdrawals(
                        completed_withdrawals_count=driver_completed_withdrawals_count
                    ),
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
        fee_amount = Decimal(str(getattr(settings, "WITHDRAWAL_FEE_FLAT", "0.50")))

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

                duplicate_withdrawal = _recent_duplicate_withdrawal(
                    user=request.user,
                    fleet=driver_membership.fleet,
                    bank_account=bank_account,
                    amount=amount,
                    fee_amount=fee_amount,
                    currency=wallet.currency,
                )
                if duplicate_withdrawal is not None:
                    response_payload = WithdrawalSerializer(duplicate_withdrawal).data
                    finalize_idempotent_request(idempotency_record, status_code=200, response_body=response_payload)
                    return Response(response_payload, status=status.HTTP_200_OK)

                if amount + fee_amount > driver_balance:
                    error_payload = {"detail": "Insufficient driver available balance for this withdrawal."}
                    finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
                    return Response(error_payload, status=status.HTTP_400_BAD_REQUEST)

                if amount > fleet_reserve_balance:
                    FleetRatingPenalty.objects.create(
                        fleet=driver_membership.fleet,
                        user=request.user,
                        reason=FleetRatingPenalty.Reason.INSUFFICIENT_RESERVE,
                        metadata={
                            "requested_amount": str(amount),
                            "fleet_reserve_balance": str(fleet_reserve_balance),
                            "driver_balance": str(driver_balance),
                        },
                    )
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

                duplicate_withdrawal = _recent_duplicate_withdrawal(
                    user=request.user,
                    fleet=None,
                    bank_account=bank_account,
                    amount=amount,
                    fee_amount=fee_amount,
                    currency=wallet.currency,
                )
                if duplicate_withdrawal is not None:
                    response_payload = WithdrawalSerializer(duplicate_withdrawal).data
                    finalize_idempotent_request(idempotency_record, status_code=200, response_body=response_payload)
                    return Response(response_payload, status=status.HTTP_200_OK)

                if amount + fee_amount > current_balance:
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
                    fee_amount=fee_amount,
                    currency=wallet.currency,
                    status=WithdrawalRequest.Status.PENDING,
                    note=note,
                )

                create_ledger_entry(
                    account=locked_ledger_account,
                    amount=-(amount + fee_amount),
                    entry_type="withdrawal_hold",
                    created_by=request.user,
                    reference_type="withdrawal",
                    reference_id=str(withdrawal.id),
                    metadata={
                        "bank_account_id": bank_account.id,
                        "description": f"Withdrawal to {bank_account.bank_name}",
                        "note": note,
                        "fee_amount": str(fee_amount),
                    },
                )

                wallet.balance = current_balance - amount - fee_amount
                wallet.save(update_fields=["balance", "updated_at"])

        if withdrawal.fleet_id:
            connection = _get_active_fleet_bog_connection(fleet=withdrawal.fleet)
            if connection is not None:
                try:
                    submit_withdrawal_to_bog(connection=connection, withdrawal=withdrawal)
                except BogPayoutPreflightError as exc:
                    logger.warning("Automatic BoG payout preflight failed for withdrawal %s: %s", withdrawal.id, exc)
                    error_payload = {"detail": str(exc)}
                    finalize_idempotent_request(idempotency_record, status_code=400, response_body=error_payload)
                    log_audit(
                        user=request.user,
                        action="withdrawal_bog_preflight_failed",
                        resource_type="withdrawal",
                        resource_id=withdrawal.id,
                        request_id=request_id,
                        ip_address=request.META.get("REMOTE_ADDR"),
                        metadata={"detail": str(exc), "reversal_detail": "Withdrawal failed before BoG document creation."},
                    )
                    return Response(error_payload, status=status.HTTP_400_BAD_REQUEST)
                except Exception as exc:
                    logger.exception("Automatic BoG payout submission failed for withdrawal %s", withdrawal.id)
                    log_audit(
                        user=request.user,
                        action="withdrawal_bog_auto_submit_failed",
                        resource_type="withdrawal",
                        resource_id=withdrawal.id,
                        request_id=request_id,
                        ip_address=request.META.get("REMOTE_ADDR"),
                        metadata={"detail": str(exc), "reversal_detail": "No automatic reversal; withdrawal remains queued."},
                    )

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
            return WithdrawalRequest.objects.filter(fleet=binding.fleet).select_related("bank_account", "user").order_by("-created_at", "-id")
        if meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.DRIVER):
            return WithdrawalRequest.objects.filter(user=self.request.user).select_related("bank_account", "user").order_by("-created_at", "-id")
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
        currency = "GEL"
        account_number = (settings.BOG_SOURCE_ACCOUNT_NUMBER or "").strip()
        display_account_number = account_number
        if account_number and not account_number.upper().endswith(currency):
            display_account_number = f"{account_number}{currency}"
        payload = {
            "bank_name": "Bank of Georgia",
            "account_holder_name": settings.BOG_PAYER_NAME or "",
            "account_number": display_account_number,
            "currency": currency,
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
        pending_payouts_total = pending_withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
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


class AdminNetworkSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if binding is None or binding.role != FleetPhoneBinding.Role.ADMIN:
            return Response({"detail": "Only admins can view app-wide finance data."}, status=403)

        currency = "GEL"
        total_funded = (
            LedgerEntry.objects.filter(
                account__account_type=LedgerAccount.AccountType.FLEET_RESERVE,
                entry_type="fleet_reserve_deposit_credit",
                currency=currency,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        tracked_withdrawals = WithdrawalRequest.objects.filter(
            fleet__isnull=False,
            currency=currency,
        ).exclude(status=WithdrawalRequest.Status.FAILED)
        total_withdrawn = tracked_withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        completed_withdrawal_transactions = tracked_withdrawals.count()

        total_fees = tracked_withdrawals.aggregate(total=Sum("fee_amount"))["total"] or Decimal("0.00")

        pending_withdrawals = WithdrawalRequest.objects.filter(
            fleet__isnull=False,
            status__in=[WithdrawalRequest.Status.PENDING, WithdrawalRequest.Status.PROCESSING],
            currency=currency,
        )
        pending_payouts_total = pending_withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        withdrawn_by_fleet = list(
            tracked_withdrawals.values("fleet_id", "fleet__name")
            .annotate(
                transaction_count=Count("id"),
                total_withdrawn=Sum("amount"),
            )
            .order_by("-transaction_count", "-total_withdrawn", "fleet__name")
        )
        pending_by_fleet_rows = list(
            pending_withdrawals.values("fleet_id", "fleet__name")
            .annotate(
                transaction_count=Count("id"),
                pending_total=Sum("amount"),
            )
            .order_by("-transaction_count", "-pending_total", "fleet__name")
        )
        pending_fleet_ids = [item["fleet_id"] for item in pending_by_fleet_rows if item["fleet_id"]]
        pending_fleets = {fleet.id: fleet for fleet in Fleet.objects.filter(id__in=pending_fleet_ids)}

        serializer = AdminNetworkSummarySerializer(
            {
                "currency": currency,
                "total_funded": total_funded,
                "total_withdrawn": total_withdrawn,
                "total_fees": total_fees,
                "pending_payouts_count": pending_withdrawals.count(),
                "pending_payouts_total": pending_payouts_total,
                "fleet_count": Fleet.objects.count(),
                "active_fleet_count": Fleet.objects.filter(phone_bindings__is_active=True).distinct().count(),
                "completed_withdrawal_transactions": completed_withdrawal_transactions,
                "withdrawn_by_fleet": [
                    {
                        "fleet_id": item["fleet_id"],
                        "fleet_name": item["fleet__name"] or f"Fleet {item['fleet_id']}",
                        "transaction_count": item["transaction_count"],
                        "total_withdrawn": item["total_withdrawn"] or Decimal("0.00"),
                    }
                    for item in withdrawn_by_fleet
                ],
                "pending_by_fleet": [
                    {
                        "fleet_id": item["fleet_id"],
                        "fleet_name": item["fleet__name"] or f"Fleet {item['fleet_id']}",
                        "transaction_count": item["transaction_count"],
                        "pending_total": item["pending_total"] or Decimal("0.00"),
                        "reserve_balance": get_account_balance(
                            get_or_create_fleet_reserve_account(pending_fleets[item["fleet_id"]], currency=currency),
                            currency,
                        )
                        if item["fleet_id"] in pending_fleets
                        else Decimal("0.00"),
                    }
                    for item in pending_by_fleet_rows
                ],
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


class OwnerDriverFinanceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can view driver finance data."}, status=403)

        driver_bindings = list(
            FleetPhoneBinding.objects.filter(
                fleet=binding.fleet,
                role=FleetPhoneBinding.Role.DRIVER,
                is_active=True,
                user__is_active=True,
            )
            .select_related("user")
            .order_by("created_at", "id")
        )
        memberships = {
            membership.user_id: membership
            for membership in DriverFleetMembership.objects.filter(
                fleet=binding.fleet,
                user_id__in=[item.user_id for item in driver_bindings],
                is_active=True,
            )
        }

        transaction_count_map = {}
        yandex_connection = _get_active_fleet_yandex_connection(fleet=binding.fleet)
        if yandex_connection is not None:
            external_ids = [
                membership.yandex_external_driver_id
                for membership in memberships.values()
                if membership.yandex_external_driver_id
            ]
            if external_ids:
                transaction_count_map = {
                    row["driver_external_id"]: row["transaction_count"]
                    for row in YandexTransactionRecord.objects.filter(
                        connection=yandex_connection,
                        driver_external_id__in=external_ids,
                    )
                    .values("driver_external_id")
                    .annotate(transaction_count=Count("id"))
                }

        payload = []
        for item in driver_bindings:
            driver_account = get_or_create_driver_available_account(
                item.user,
                fleet=binding.fleet,
                currency="GEL",
            )
            membership = memberships.get(item.user_id)
            external_driver_id = membership.yandex_external_driver_id if membership else ""
            payload.append(
                {
                    "id": item.id,
                    "first_name": item.user.first_name,
                    "last_name": item.user.last_name,
                    "phone_number": item.phone_number,
                    "transaction_count": transaction_count_map.get(external_driver_id, 0),
                    "available_balance": get_account_balance(driver_account, "GEL"),
                    "currency": "GEL",
                    "created_at": item.created_at,
                    "yandex_external_driver_id": external_driver_id,
                    "yandex_display_name": membership.yandex_display_name if membership else "",
                    "yandex_phone_number": membership.yandex_phone_number if membership else "",
                    "yandex_current_balance": membership.yandex_current_balance if membership else Decimal("0.00"),
                    "yandex_balance_currency": membership.yandex_balance_currency if membership else "GEL",
                    "last_yandex_sync_at": membership.last_yandex_sync_at if membership else None,
                    "sync_status": "synced" if external_driver_id else "needs_mapping",
                }
            )

        serializer = OwnerDriverFinanceSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OwnerTransactionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if binding is None or binding.role != FleetPhoneBinding.Role.OWNER:
            return Response({"detail": "Only owners can view fleet transactions."}, status=403)

        currency = "GEL"
        deposit_rows = [
            {
                "id": f"D-{item.id}",
                "transaction_type": "Deposit",
                "amount": item.amount,
                "currency": item.currency,
                "created_at": item.created_at,
            }
            for item in Deposit.objects.filter(
                fleet=binding.fleet,
                status=Deposit.Status.COMPLETED,
                currency=currency,
            )
            .order_by("-created_at", "-id")[:100]
        ]
        withdrawal_rows = [
            {
                "id": f"W-{item.id}",
                "transaction_type": "Withdrawal",
                "amount": item.amount,
                "currency": item.currency,
                "created_at": item.created_at,
            }
            for item in WithdrawalRequest.objects.filter(
                fleet=binding.fleet,
                currency=currency,
            )
            .exclude(status=WithdrawalRequest.Status.FAILED)
            .order_by("-created_at", "-id")[:100]
        ]
        payload = sorted(
            deposit_rows + withdrawal_rows,
            key=lambda item: item["created_at"],
            reverse=True,
        )[:100]
        serializer = OwnerTransactionSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
