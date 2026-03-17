from decimal import Decimal

from django.conf import settings
from django.db import transaction as db_transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import FleetPhoneBinding
from accounts.roles import get_request_fleet_binding, meets_min_role
from audit.services import begin_idempotent_request, finalize_idempotent_request, log_audit
from ledger.models import LedgerAccount, LedgerEntry
from ledger.services import (
    create_ledger_entry,
    ensure_opening_entry,
    get_account_balance,
    get_or_create_user_ledger_account,
)
from payments.models import InternalTransfer
from integrations.models import ProviderConnection
from integrations.services import sync_bog_deposits
from .models import BankAccount, Deposit, IncomingBankTransfer, Wallet, WithdrawalRequest
from .serializers import (
    BankAccountSerializer,
    DepositInstructionSerializer,
    DepositSerializer,
    IncomingBankTransferMatchSerializer,
    IncomingBankTransferSerializer,
    WalletTopUpSerializer,
    TransactionFeedSerializer,
    WalletSerializer,
    WithdrawalCreateSerializer,
    WithdrawalSerializer,
    WithdrawalStatusUpdateSerializer,
)
from .services import build_wallet_deposit_reference, complete_bank_deposit


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


class BalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
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
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.OPERATOR):
            raise PermissionError("Only operator/admin/owner can add bank accounts.")
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
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.OPERATOR):
            return Response({"detail": "Only operator/admin/owner can create withdrawals."}, status=403)

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

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        ledger_account = get_or_create_user_ledger_account(request.user, wallet.currency)
        ensure_opening_entry(ledger_account, wallet.balance, created_by=request.user)
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

        with db_transaction.atomic():
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
        return WithdrawalRequest.objects.filter(user=self.request.user).select_related("bank_account")


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

            wallet = withdrawal.wallet
            ledger_account = get_or_create_user_ledger_account(wallet.user, wallet.currency)
            locked_ledger_account = LedgerAccount.objects.select_for_update().get(id=ledger_account.id)
            current_balance = get_account_balance(locked_ledger_account, wallet.currency)

            if target_status == WithdrawalRequest.Status.FAILED:
                # Reverse the hold if payout failed.
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
        payload = {
            "bank_name": "Bank of Georgia",
            "account_holder_name": settings.BOG_PAYER_NAME or "",
            "account_number": settings.BOG_SOURCE_ACCOUNT_NUMBER or "",
            "currency": "GEL",
            "reference_code": build_wallet_deposit_reference(request.user),
            "note": "Send a bank transfer to this account and include the exact reference code.",
        }
        serializer = DepositInstructionSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DepositListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DepositSerializer

    def get_queryset(self):
        return Deposit.objects.filter(user=self.request.user)


class UnmatchedIncomingTransferListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IncomingBankTransferSerializer

    def get_queryset(self):
        binding = get_request_fleet_binding(user=self.request.user, request=self.request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return IncomingBankTransfer.objects.none()
        return IncomingBankTransfer.objects.filter(
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
        )

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
        phone_number = serializer.validated_data["phone_number"].strip()

        transfer = IncomingBankTransfer.objects.filter(id=transfer_id).first()
        if transfer is None:
            return Response({"detail": "Incoming transfer not found."}, status=404)
        if transfer.match_status != IncomingBankTransfer.MatchStatus.UNMATCHED:
            return Response({"detail": "Incoming transfer is already finalized."}, status=400)
        if transfer.amount <= Decimal("0.00"):
            return Response({"detail": "Only positive incoming transfers can be matched."}, status=400)

        target_binding = (
            FleetPhoneBinding.objects.select_related("user")
            .filter(
                fleet__name__iexact=fleet_name,
                phone_number=phone_number,
                is_active=True,
                user__is_active=True,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if target_binding is None:
            return Response({"detail": "Phone number was not found in the selected fleet."}, status=404)

        transfer.user = target_binding.user
        transfer.match_status = IncomingBankTransfer.MatchStatus.MATCHED
        transfer.save(update_fields=["user", "match_status", "updated_at"])

        deposit, _ = complete_bank_deposit(
            user=target_binding.user,
            provider=transfer.provider,
            provider_transaction_id=transfer.provider_transaction_id,
            amount=transfer.amount,
            currency=transfer.currency,
            reference_code=build_wallet_deposit_reference(target_binding.user),
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
                "matched_phone_number": phone_number,
                "matched_user_id": target_binding.user_id,
                "deposit_id": deposit.id,
                "fleet_name": fleet_name,
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

        connection = ProviderConnection.objects.filter(
            user=request.user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
        ).first()
        if connection is None:
            return Response({"detail": "Bank of Georgia connection is not configured."}, status=status.HTTP_400_BAD_REQUEST)

        result = sync_bog_deposits(connection=connection)
        return Response(result, status=status.HTTP_200_OK)
