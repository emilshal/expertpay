from decimal import Decimal

from django.conf import settings
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
    fleet_name = serializers.CharField()
    reference_code = serializers.CharField()
    note = serializers.CharField()


class OwnerPendingPayoutSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    driver_name = serializers.CharField()
    driver_username = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    fee_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class OwnerFleetSummarySerializer(serializers.Serializer):
    fleet_name = serializers.CharField()
    currency = serializers.CharField(max_length=3)
    reserve_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_funded = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_withdrawn = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_fees = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_payouts_count = serializers.IntegerField()
    pending_payouts_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    unmatched_deposits_count = serializers.IntegerField()
    failed_payouts_count = serializers.IntegerField()
    failed_payouts_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    active_drivers_count = serializers.IntegerField()
    pending_payouts = OwnerPendingPayoutSerializer(many=True)


class OwnerDriverFinanceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    phone_number = serializers.CharField()
    transaction_count = serializers.IntegerField()
    available_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    created_at = serializers.DateTimeField()


class OwnerTransactionSerializer(serializers.Serializer):
    id = serializers.CharField()
    transaction_type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    created_at = serializers.DateTimeField()


class AdminWithdrawnFleetSerializer(serializers.Serializer):
    fleet_id = serializers.IntegerField()
    fleet_name = serializers.CharField()
    transaction_count = serializers.IntegerField()
    total_withdrawn = serializers.DecimalField(max_digits=14, decimal_places=2)


class AdminPendingFleetSerializer(serializers.Serializer):
    fleet_id = serializers.IntegerField()
    fleet_name = serializers.CharField()
    transaction_count = serializers.IntegerField()
    pending_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    reserve_balance = serializers.DecimalField(max_digits=14, decimal_places=2)


class AdminNetworkSummarySerializer(serializers.Serializer):
    currency = serializers.CharField(max_length=3)
    total_funded = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_withdrawn = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_fees = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_payouts_count = serializers.IntegerField()
    pending_payouts_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    fleet_count = serializers.IntegerField()
    active_fleet_count = serializers.IntegerField()
    completed_withdrawal_transactions = serializers.IntegerField()
    withdrawn_by_fleet = AdminWithdrawnFleetSerializer(many=True)
    pending_by_fleet = AdminPendingFleetSerializer(many=True)


class DepositSerializer(serializers.ModelSerializer):
    fleet_name = serializers.CharField(source="fleet.name", read_only=True)
    sync_source = serializers.SerializerMethodField()

    class Meta:
        model = Deposit
        fields = (
            "id",
            "amount",
            "currency",
            "status",
            "fleet_name",
            "reference_code",
            "provider",
            "provider_transaction_id",
            "payer_name",
            "payer_inn",
            "payer_account_number",
            "note",
            "sync_source",
            "completed_at",
            "created_at",
        )

    def get_sync_source(self, obj):
        metadata = obj.raw_payload.get("_expertpay_sync", {}) if isinstance(obj.raw_payload, dict) else {}
        return metadata.get("source", "activity_poll")


class IncomingBankTransferSerializer(serializers.ModelSerializer):
    fleet_name = serializers.CharField(source="fleet.name", read_only=True)
    sync_source = serializers.SerializerMethodField()

    class Meta:
        model = IncomingBankTransfer
        fields = (
            "id",
            "provider",
            "provider_transaction_id",
            "account_number",
            "currency",
            "amount",
            "fleet_name",
            "reference_text",
            "payer_name",
            "payer_inn",
            "payer_account_number",
            "booking_date",
            "value_date",
            "match_status",
            "sync_source",
            "created_at",
            "updated_at",
        )

    def get_sync_source(self, obj):
        metadata = obj.raw_payload.get("_expertpay_sync", {}) if isinstance(obj.raw_payload, dict) else {}
        return metadata.get("source", "activity_poll")


class IncomingBankTransferMatchSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=32, required=False, allow_blank=True)


class DepositSyncRequestSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if bool(start_date) != bool(end_date):
            raise serializers.ValidationError("Both start_date and end_date are required for backfill.")
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError("start_date must be on or before end_date.")
        return attrs


class WithdrawalCreateSerializer(serializers.Serializer):
    bank_account_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_amount(self, value):
        fee_amount = Decimal(str(getattr(settings, "WITHDRAWAL_FEE_FLAT", "0.50")))
        minimum_payout_amount = max(Decimal("0.01"), Decimal("1.00") - fee_amount)
        maximum_payout_amount = max(Decimal("0.01"), Decimal("500.00") - fee_amount)

        if value < minimum_payout_amount:
            raise serializers.ValidationError("Minimum withdrawal amount is 1.00 GEL.")
        if value > maximum_payout_amount:
            raise serializers.ValidationError("Maximum withdrawal amount is 500.00 GEL.")
        return value


class WithdrawalSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)
    fleet_name = serializers.CharField(source="fleet.name", read_only=True)
    driver_name = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalRequest
        fields = ("id", "amount", "fee_amount", "currency", "status", "note", "fleet_name", "driver_name", "bank_account", "created_at")

    def get_driver_name(self, obj):
        full_name = obj.user.get_full_name().strip()
        return full_name or obj.user.username


class WithdrawalStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WithdrawalRequest.Status.choices)


class WalletTopUpSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)
