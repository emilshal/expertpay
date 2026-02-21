from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import serializers


class InternalTransferCreateSerializer(serializers.Serializer):
    receiver_username = serializers.CharField(max_length=150)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_receiver_username(self, value):
        if not User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Receiver user not found.")
        return value
