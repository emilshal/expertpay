from decimal import Decimal

from rest_framework import serializers

from .models import BankAccount, Wallet, WithdrawalRequest


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ("balance", "currency", "updated_at")


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ("id", "bank_name", "account_number", "beneficiary_name", "is_active", "created_at")
        read_only_fields = ("id", "is_active", "created_at")


class TransactionFeedSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    status = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class WithdrawalCreateSerializer(serializers.Serializer):
    bank_account_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class WithdrawalSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)

    class Meta:
        model = WithdrawalRequest
        fields = ("id", "amount", "currency", "status", "note", "bank_account", "created_at")


class WithdrawalStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WithdrawalRequest.Status.choices)


class WalletTopUpSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)
