from decimal import Decimal

from django.db import transaction as db_transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

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
        bank_account = BankAccount.objects.filter(
            id=bank_account_id, user=request.user, is_active=True
        ).first()

        if bank_account is None:
            return Response({"detail": "Bank account not found."}, status=status.HTTP_404_NOT_FOUND)

        if amount <= Decimal("0"):
            return Response({"detail": "Amount must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

        if amount > wallet.balance:
            return Response(
                {"detail": "Insufficient wallet balance for this withdrawal."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():
            wallet.balance = wallet.balance - amount
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
