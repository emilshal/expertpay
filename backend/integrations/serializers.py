from decimal import Decimal

from rest_framework import serializers

from .models import (
    BankSimulatorPayout,
    BogCardOrder,
    BogPayout,
    ExternalEvent,
    ProviderConnection,
    YandexDriverProfile,
    YandexSyncRun,
    YandexTransactionCategory,
    YandexTransactionRecord,
)


class ProviderConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderConnection
        fields = ("id", "provider", "external_account_id", "status", "config", "created_at")
        read_only_fields = ("id", "created_at")


class ExternalEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalEvent
        fields = ("id", "external_id", "event_type", "payload", "processed", "created_at")


class SimulateEventsSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(
        choices=["steady", "spiky", "adjustment", "duplicates", "out_of_order"], default="steady"
    )
    count = serializers.IntegerField(min_value=1, max_value=100, default=10)


class LiveYandexSyncSerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=500, default=100)
    dry_run = serializers.BooleanField(default=False)
    full_sync = serializers.BooleanField(default=False)


class BankSimulatorPayoutSerializer(serializers.ModelSerializer):
    withdrawal_id = serializers.IntegerField(source="withdrawal.id", read_only=True)

    class Meta:
        model = BankSimulatorPayout
        fields = (
            "id",
            "withdrawal_id",
            "provider_payout_id",
            "status",
            "failure_reason",
            "metadata",
            "created_at",
            "updated_at",
        )


class BogPayoutSerializer(serializers.ModelSerializer):
    withdrawal_id = serializers.IntegerField(source="withdrawal.id", read_only=True)

    class Meta:
        model = BogPayout
        fields = (
            "id",
            "withdrawal_id",
            "provider_unique_id",
            "provider_unique_key",
            "status",
            "provider_status",
            "result_code",
            "match_score",
            "failure_reason",
            "request_payload",
            "response_payload",
            "submitted_at",
            "last_status_checked_at",
            "created_at",
            "updated_at",
        )


class BogCardOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = BogCardOrder
        fields = (
            "id",
            "provider_order_id",
            "external_order_id",
            "parent_order_id",
            "amount",
            "currency",
            "status",
            "provider_order_status",
            "redirect_url",
            "details_url",
            "callback_url",
            "success_url",
            "fail_url",
            "save_card",
            "transaction_id",
            "payer_identifier",
            "transfer_method",
            "card_type",
            "callback_received_at",
            "completed_at",
            "created_at",
            "updated_at",
        )


class SubmitBankPayoutSerializer(serializers.Serializer):
    withdrawal_id = serializers.IntegerField(min_value=1)


class CreateBogCardOrderSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.50"))
    currency = serializers.CharField(max_length=8, default="GEL")
    save_card = serializers.BooleanField(default=False)
    parent_order_id = serializers.CharField(required=False, allow_blank=True, max_length=120)


class SyncBogPayoutStatusSerializer(serializers.Serializer):
    payout_id = serializers.IntegerField(min_value=1, required=False)


class UpdateBankPayoutStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            BankSimulatorPayout.Status.ACCEPTED,
            BankSimulatorPayout.Status.PROCESSING,
            BankSimulatorPayout.Status.SETTLED,
            BankSimulatorPayout.Status.FAILED,
            BankSimulatorPayout.Status.REVERSED,
        ]
    )
    failure_reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class YandexTransactionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = YandexTransactionCategory
        fields = (
            "id",
            "external_category_id",
            "code",
            "name",
            "is_creatable",
            "is_enabled",
            "updated_at",
        )


class YandexDriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = YandexDriverProfile
        fields = (
            "id",
            "external_driver_id",
            "first_name",
            "last_name",
            "phone_number",
            "status",
            "updated_at",
        )


class YandexTransactionRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = YandexTransactionRecord
        fields = (
            "id",
            "external_transaction_id",
            "driver_external_id",
            "event_at",
            "amount",
            "currency",
            "category",
            "direction",
            "updated_at",
        )


class YandexSyncRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = YandexSyncRun
        fields = (
            "id",
            "trigger",
            "status",
            "dry_run",
            "full_sync",
            "drivers_http_status",
            "transactions_http_status",
            "drivers_fetched",
            "drivers_upserted",
            "transactions_fetched",
            "transactions_stored_new",
            "imported_count",
            "imported_total",
            "cursor_from",
            "cursor_to",
            "cursor_next_from",
            "detail",
            "started_at",
            "completed_at",
            "created_at",
        )
