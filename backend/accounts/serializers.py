from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from .models import DriverFleetMembership, Fleet, FleetPhoneBinding, LoginCodeChallenge


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


class FleetRegistrationSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=32)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    yandex_park_id = serializers.CharField(max_length=120)
    yandex_client_id = serializers.CharField(max_length=160)
    yandex_api_key = serializers.CharField(max_length=180, write_only=True)

    def validate_fleet_name(self, value):
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise serializers.ValidationError("Fleet name is required.")
        if Fleet.objects.filter(name__iexact=cleaned).exists():
            raise serializers.ValidationError("Fleet already exists.")
        return cleaned

    def validate_phone_number(self, value):
        digits = _normalize_georgian_mobile(value)
        return digits

    def validate(self, attrs):
        from integrations.services import test_yandex_credentials

        result = test_yandex_credentials(
            park_id=attrs.get("yandex_park_id", "").strip(),
            client_id=attrs.get("yandex_client_id", "").strip(),
            api_key=attrs.get("yandex_api_key", "").strip(),
        )
        if not result["ok"]:
            raise serializers.ValidationError({"yandex": result.get("detail", "Yandex credentials could not be verified.")})
        attrs["_yandex_test_result"] = result
        return attrs

    def create(self, validated_data):
        from integrations.services import create_fleet_yandex_connection

        phone_number = validated_data["phone_number"]
        username = f"fleet_owner_{phone_number}"
        with transaction.atomic():
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": validated_data.get("first_name", "").strip(),
                    "last_name": validated_data.get("last_name", "").strip(),
                    "email": validated_data.get("email", "").strip(),
                    "is_active": True,
                },
            )
            update_fields = []
            for field in ("first_name", "last_name", "email"):
                value = validated_data.get(field, "").strip()
                if value and getattr(user, field) != value:
                    setattr(user, field, value)
                    update_fields.append(field)
            if not user.is_active:
                user.is_active = True
                update_fields.append("is_active")
            if update_fields:
                user.save(update_fields=update_fields)

            fleet = Fleet.objects.create(name=validated_data["fleet_name"])
            FleetPhoneBinding.objects.create(
                fleet=fleet,
                user=user,
                phone_number=phone_number,
                role=FleetPhoneBinding.Role.OWNER,
                is_active=True,
            )
            DriverFleetMembership.objects.get_or_create(
                user=user,
                defaults={
                    "fleet": fleet,
                    "is_active": True,
                },
            )
            connection, result = create_fleet_yandex_connection(
                fleet=fleet,
                user=user,
                park_id=validated_data["yandex_park_id"].strip(),
                client_id=validated_data["yandex_client_id"].strip(),
                api_key=validated_data["yandex_api_key"].strip(),
            )
            if connection is None:
                raise serializers.ValidationError({"yandex": result.get("detail", "Yandex credentials could not be saved.")})
        return fleet


class PublicDriverRegistrationSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=32)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_phone_number(self, value):
        digits = _normalize_georgian_mobile(value)
        return digits

    def create(self, validated_data):
        from integrations.models import ProviderConnection
        from integrations.services import find_yandex_driver_by_phone

        fleet = Fleet.objects.filter(name__iexact=validated_data["fleet_name"].strip()).first()
        if fleet is None:
            raise serializers.ValidationError({"fleet_name": "Fleet not found."})

        connection = (
            ProviderConnection.objects.filter(
                provider=ProviderConnection.Provider.YANDEX,
                fleet=fleet,
                status="active",
            )
            .order_by("-created_at")
            .first()
        )
        if connection is None:
            raise serializers.ValidationError({"yandex": "This fleet does not have an active Yandex connection."})

        phone_number = validated_data["phone_number"]
        if FleetPhoneBinding.objects.filter(
            fleet=fleet,
            phone_number=phone_number,
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        ).exists():
            raise serializers.ValidationError({"phone_number": "This phone number is already registered."})

        lookup = find_yandex_driver_by_phone(connection=connection, phone_number=phone_number)
        if not lookup["ok"]:
            raise serializers.ValidationError({"yandex": lookup.get("detail", "Could not look up driver in Yandex.")})
        matches = lookup.get("matches", [])
        if len(matches) != 1:
            raise serializers.ValidationError(
                {"yandex": "Driver phone number must match exactly one Yandex driver for this fleet."}
            )
        yandex_driver = matches[0]

        username = f"fleet_driver_{phone_number}"
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": validated_data.get("first_name", "").strip() or yandex_driver["display_name"].split(" ", 1)[0],
                "last_name": validated_data.get("last_name", "").strip() or (
                    yandex_driver["display_name"].split(" ", 1)[1] if " " in yandex_driver["display_name"] else ""
                ),
                "email": validated_data.get("email", "").strip(),
                "is_active": True,
            },
        )
        update_fields = []
        for field in ("first_name", "last_name", "email"):
            value = validated_data.get(field, "").strip()
            if value and getattr(user, field) != value:
                setattr(user, field, value)
                update_fields.append(field)
        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")
        if update_fields:
            user.save(update_fields=update_fields)

        binding = FleetPhoneBinding.objects.create(
            fleet=fleet,
            user=user,
            phone_number=phone_number,
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.get_or_create(
            user=user,
            defaults={
                "fleet": fleet,
                "yandex_external_driver_id": yandex_driver["external_driver_id"],
                "yandex_display_name": yandex_driver["display_name"],
                "yandex_phone_number": yandex_driver["phone_number"],
                "yandex_current_balance": yandex_driver["current_balance"],
                "yandex_balance_currency": yandex_driver["balance_currency"],
                "yandex_raw": yandex_driver["raw"],
                "is_active": True,
            },
        )
        membership = user.driver_fleet_membership
        membership.fleet = fleet
        membership.yandex_external_driver_id = yandex_driver["external_driver_id"]
        membership.yandex_display_name = yandex_driver["display_name"]
        membership.yandex_phone_number = yandex_driver["phone_number"]
        membership.yandex_current_balance = yandex_driver["current_balance"]
        membership.yandex_balance_currency = yandex_driver["balance_currency"]
        membership.yandex_raw = yandex_driver["raw"]
        membership.save(
            update_fields=[
                "fleet",
                "yandex_external_driver_id",
                "yandex_display_name",
                "yandex_phone_number",
                "yandex_current_balance",
                "yandex_balance_currency",
                "yandex_raw",
                "updated_at",
            ]
        )
        return binding


class FleetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fleet
        fields = ("id", "name")


class RequestCodeSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=32)
    role = serializers.ChoiceField(choices=FleetPhoneBinding.Role.choices, required=False)


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


def _normalize_georgian_mobile(value):
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("995") and len(digits) == 12:
        digits = digits[3:]
    if len(digits) != 9 or not digits.startswith("5"):
        raise serializers.ValidationError("Enter a valid Georgian mobile number.")
    return digits


class FleetMemberRoleUpdateSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=32)
    role = serializers.ChoiceField(choices=FleetPhoneBinding.Role.choices)


class FleetMemberCreateSerializer(serializers.Serializer):
    fleet_name = serializers.CharField(max_length=120)
    phone_number = serializers.CharField(max_length=32)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=FleetPhoneBinding.Role.choices, default=FleetPhoneBinding.Role.DRIVER)

    def validate_phone_number(self, value):
        return _normalize_georgian_mobile(value)


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
