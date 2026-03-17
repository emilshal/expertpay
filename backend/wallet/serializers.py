from decimal import Decimal

from rest_framework import serializers

from .models import BankAccount, Deposit, IncomingBankTransfer, Wallet, WithdrawalRequest


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ("balance", "currency", "updated_at")


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ("id", "bank_name", "account_number", "beneficiary_name", "beneficiary_inn", "is_active", "created_at")
        read_only_fields = ("id", "is_active", "created_at")


class TransactionFeedSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    status = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class DepositInstructionSerializer(serializers.Serializer):
    bank_name = serializers.CharField()
    account_holder_name = serializers.CharField(allow_blank=True)
    account_number = serializers.CharField()
    currency = serializers.CharField()
    reference_code = serializers.CharField()
    note = serializers.CharField()


class DepositSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deposit
        fields = (
            "id",
            "amount",
            "currency",
            "status",
            "reference_code",
            "provider",
            "provider_transaction_id",
            "payer_name",
            "payer_inn",
            "payer_account_number",
            "note",
            "completed_at",
            "created_at",
        )


class IncomingBankTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomingBankTransfer
        fields = (
            "id",
            "provider",
            "provider_transaction_id",
            "account_number",
            "currency",
            "amount",
            "reference_text",
            "payer_name",
            "payer_inn",
            "payer_account_number",
            "booking_date",
            "value_date",
            "match_status",
            "created_at",
            "updated_at",
        )


class IncomingBankTransferMatchSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=32)


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
