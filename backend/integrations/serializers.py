from rest_framework import serializers

from .models import BankSimulatorPayout, ExternalEvent, ProviderConnection


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


class SubmitBankPayoutSerializer(serializers.Serializer):
    withdrawal_id = serializers.IntegerField(min_value=1)


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
