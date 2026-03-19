from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Fleet, FleetPhoneBinding, LoginCodeChallenge


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "email")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password", "first_name", "last_name")

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class FleetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fleet
        fields = ("id", "name")


class RequestCodeSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=32)


class VerifyCodeSerializer(serializers.Serializer):
    challenge_id = serializers.IntegerField()
    code = serializers.CharField(max_length=6)

    def validate_challenge_id(self, value):
        if not LoginCodeChallenge.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid challenge.")
        return value


class FleetPhoneBindingSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = FleetPhoneBinding
        fields = (
            "id",
            "fleet",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "is_active",
            "created_at",
        )


class FleetMemberRoleUpdateSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=32)
    role = serializers.ChoiceField(choices=FleetPhoneBinding.Role.choices)


class DriverYandexMappingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    fleet = serializers.IntegerField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    phone_number = serializers.CharField()
    role = serializers.CharField()
    is_active = serializers.BooleanField()
    has_mapping = serializers.BooleanField()
    yandex_external_driver_id = serializers.CharField(allow_blank=True)
    mapping_conflict = serializers.BooleanField(default=False)
    mapping_conflict_fleet_name = serializers.CharField(allow_blank=True, allow_null=True, required=False)


class DriverYandexMappingUpdateSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120)
    yandex_external_driver_id = serializers.CharField(max_length=120, allow_blank=True, required=False)

    def validate_yandex_external_driver_id(self, value):
        return (value or "").strip()
