from decimal import Decimal

from django.db import transaction as db_transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ledger.models import LedgerAccount
from ledger.services import (
    create_ledger_entry,
    ensure_opening_entry,
    get_account_balance,
    get_or_create_user_ledger_account,
)
from .models import BankAccount, Transaction, Wallet, WithdrawalRequest
from .serializers import (
    BankAccountSerializer,
    TransactionSerializer,
    WalletSerializer,
    WithdrawalCreateSerializer,
    WithdrawalSerializer,
)


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
        serializer.save(user=self.request.user)


class TransactionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer

    def get_queryset(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet.transactions.all()


class WithdrawalCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WithdrawalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bank_account_id = serializer.validated_data["bank_account_id"]
        amount = serializer.validated_data["amount"]
        note = serializer.validated_data.get("note", "")

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        ledger_account = get_or_create_user_ledger_account(request.user, wallet.currency)
        ensure_opening_entry(ledger_account, wallet.balance, created_by=request.user)
        bank_account = BankAccount.objects.filter(
            id=bank_account_id, user=request.user, is_active=True
        ).first()

        if bank_account is None:
            return Response({"detail": "Bank account not found."}, status=status.HTTP_404_NOT_FOUND)

        if amount <= Decimal("0"):
            return Response({"detail": "Amount must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

        with db_transaction.atomic():
            locked_ledger_account = LedgerAccount.objects.select_for_update().get(id=ledger_account.id)
            current_balance = get_account_balance(locked_ledger_account, wallet.currency)

            if amount > current_balance:
                return Response(
                    {"detail": "Insufficient wallet balance for this withdrawal."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            create_ledger_entry(
                account=locked_ledger_account,
                amount=-amount,
                entry_type="withdrawal_hold",
                created_by=request.user,
                reference_type="withdrawal",
                metadata={"bank_account_id": bank_account.id},
            )

            wallet.balance = current_balance - amount
            wallet.save(update_fields=["balance", "updated_at"])

            withdrawal = WithdrawalRequest.objects.create(
                user=request.user,
                wallet=wallet,
                bank_account=bank_account,
                amount=amount,
                currency=wallet.currency,
                status=WithdrawalRequest.Status.PENDING,
                note=note,
            )

            Transaction.objects.create(
                wallet=wallet,
                kind=Transaction.Kind.WITHDRAWAL,
                amount=-amount,
                currency=wallet.currency,
                status=Transaction.Status.PENDING,
                description=f"Withdrawal to {bank_account.bank_name}",
            )

        return Response(WithdrawalSerializer(withdrawal).data, status=status.HTTP_201_CREATED)
