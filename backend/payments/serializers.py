from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import serializers

from wallet.models import BankAccount


class InternalTransferCreateSerializer(serializers.Serializer):
    receiver_username = serializers.CharField(max_length=150)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_receiver_username(self, value):
        if not User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Receiver user not found.")
        return value


class InternalTransferByBankSerializer(serializers.Serializer):
    bank_name = serializers.CharField(max_length=80)
    account_number = serializers.CharField(max_length=64)
    beneficiary_name = serializers.CharField(max_length=140)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        bank_name = attrs["bank_name"].strip()
        account_number = attrs["account_number"].strip()
        beneficiary_name = attrs["beneficiary_name"].strip()

        bank_account = (
            BankAccount.objects.select_related("user")
            .filter(
                is_active=True,
                bank_name__iexact=bank_name,
                account_number__iexact=account_number,
                beneficiary_name__iexact=beneficiary_name,
            )
            .first()
        )
        if bank_account is None:
            raise serializers.ValidationError(
                {"detail": "No active account found with the provided bank, account number, and beneficiary name."}
            )

        attrs["receiver_user"] = bank_account.user
        return attrs
