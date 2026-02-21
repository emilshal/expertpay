from rest_framework import serializers

from .models import ExternalEvent, ProviderConnection


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
