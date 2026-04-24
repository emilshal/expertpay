from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .roles import get_request_fleet_binding, is_platform_admin
from .models import DriverFleetMembership, Fleet, FleetPhoneBinding, LoginCodeChallenge
from .services import OtpDeliveryError, is_internal_admin_phone, send_login_code, verify_login_code
from .serializers import (
    DriverYandexMappingSerializer,
    DriverYandexMappingUpdateSerializer,
    FleetMemberCreateSerializer,
    FleetRegistrationSerializer,
    FleetMemberRoleUpdateSerializer,
    FleetPhoneBindingSerializer,
    FleetSerializer,
    PublicDriverRegistrationSerializer,
    RegisterSerializer,
    RequestCodeSerializer,
    UserSerializer,
    VerifyCodeSerializer,
)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class FleetRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = FleetRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fleet = serializer.save()
        return Response(FleetSerializer(fleet).data, status=201)


class PublicDriverRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PublicDriverRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        binding = serializer.save()
        return Response(FleetPhoneBindingSerializer(binding).data, status=201)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = UserSerializer(request.user).data
        binding = get_request_fleet_binding(user=request.user, request=request)
        if binding is not None:
            payload["fleet"] = {"id": binding.fleet.id, "name": binding.fleet.name}
            payload["role"] = binding.role
        else:
            payload["fleet"] = None
            payload["role"] = None
        payload["is_platform_admin"] = is_platform_admin(user=request.user)
        return Response(payload)


class FleetListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = FleetSerializer
    queryset = Fleet.objects.all()


class RequestFleetCodeView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth_otp_request"

    def post(self, request):
        serializer = RequestCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fleet_name = serializer.validated_data["fleet_name"].strip()
        phone_number = serializer.validated_data["phone_number"].strip()
        requested_role = serializer.validated_data.get("role") or ""
        internal_admin_requested = request.headers.get("X-Internal-Admin-Login", "").strip() == "1"
        if requested_role == FleetPhoneBinding.Role.ADMIN and not (
            internal_admin_requested and is_internal_admin_phone(phone_number)
        ):
            return Response({"detail": "Admin login is not available."}, status=403)

        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            return Response({"detail": "Fleet not found."}, status=404)

        bindings = FleetPhoneBinding.objects.filter(
            fleet=fleet, phone_number=phone_number, is_active=True, user__is_active=True
        )
        if requested_role:
            bindings = bindings.filter(role=requested_role)
        binding = bindings.first()
        if binding is None:
            return Response({"detail": "Wrong number for this fleet."}, status=400)

        try:
            otp_payload = send_login_code(phone_number=phone_number)
        except OtpDeliveryError as exc:
            return Response({"detail": exc.detail}, status=exc.status_code)

        with transaction.atomic():
            challenge = LoginCodeChallenge.objects.create(
                fleet=fleet,
                user=binding.user,
                phone_number=phone_number,
                code=otp_payload["code"],
                provider=otp_payload["provider"],
                provider_hash=otp_payload["provider_hash"],
                requested_role=requested_role,
                expires_at=timezone.now() + timedelta(seconds=settings.OTP_CODE_TTL_SECONDS),
            )

        response_data = {"challenge_id": challenge.id, "expires_in_seconds": settings.OTP_CODE_TTL_SECONDS}
        if request.query_params.get("debug") == "1" and challenge.code:
            response_data["code"] = challenge.code
        return Response(response_data, status=201)


class VerifyFleetCodeView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth_otp_verify"

    def post(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challenge_id = serializer.validated_data["challenge_id"]
        code = serializer.validated_data["code"].strip()

        with transaction.atomic():
            challenge = LoginCodeChallenge.objects.select_for_update().filter(id=challenge_id).first()
            if challenge is None or not challenge.is_valid():
                return Response({"detail": "Code expired or invalid."}, status=400)
            if not verify_login_code(
                provider=challenge.provider,
                phone_number=challenge.phone_number,
                provider_hash=challenge.provider_hash,
                stored_code=challenge.code,
                submitted_code=code,
                ip_address=request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                or request.META.get("REMOTE_ADDR", "").strip(),
            ):
                return Response({"detail": "Invalid code."}, status=400)

            challenge.is_consumed = True
            challenge.save(update_fields=["is_consumed"])

        selected_bindings = FleetPhoneBinding.objects.filter(
            fleet=challenge.fleet,
            user=challenge.user,
            phone_number=challenge.phone_number,
            is_active=True,
        )
        if challenge.requested_role:
            selected_bindings = selected_bindings.filter(role=challenge.requested_role)
        selected_binding = selected_bindings.first()

        refresh = RefreshToken.for_user(challenge.user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(challenge.user).data,
                "fleet": {"id": challenge.fleet.id, "name": challenge.fleet.name},
                "role": selected_binding.role if selected_binding else FleetPhoneBinding.Role.DRIVER,
            }
        )


def _get_active_binding(*, user, fleet):
    return FleetPhoneBinding.objects.filter(
        user=user,
        fleet=fleet,
        is_active=True,
        user__is_active=True,
    ).first()


def _can_manage_fleet_members(role: str):
    return role in {FleetPhoneBinding.Role.ADMIN, FleetPhoneBinding.Role.OWNER}


def _serialize_driver_mappings(*, fleet, bindings):
    memberships = {
        membership.user_id: membership
        for membership in DriverFleetMembership.objects.select_related("fleet").filter(
            user_id__in=[binding.user_id for binding in bindings]
        )
    }
    rows = []
    for binding in bindings:
        membership = memberships.get(binding.user_id)
        mapping_conflict = membership is not None and membership.fleet_id != fleet.id
        rows.append(
            {
                "id": binding.id,
                "fleet": binding.fleet_id,
                "user_id": binding.user_id,
                "username": binding.user.username,
                "first_name": binding.user.first_name,
                "last_name": binding.user.last_name,
                "phone_number": binding.phone_number,
                "role": binding.role,
                "is_active": binding.is_active,
                "has_mapping": bool(membership and membership.fleet_id == fleet.id and membership.yandex_external_driver_id),
                "yandex_external_driver_id": (
                    membership.yandex_external_driver_id if membership and membership.fleet_id == fleet.id else ""
                )
                or "",
                "mapping_conflict": mapping_conflict,
                "mapping_conflict_fleet_name": membership.fleet.name if mapping_conflict else "",
            }
        )
    return rows


class FleetMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        fleet_name = request.query_params.get("fleet_name", "").strip()
        if not fleet_name:
            return Response({"detail": "fleet_name is required."}, status=400)

        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            return Response({"detail": "Fleet not found."}, status=404)

        actor_binding = _get_active_binding(user=request.user, fleet=fleet)
        if actor_binding is None:
            return Response({"detail": "You are not linked to this fleet."}, status=403)
        if not _can_manage_fleet_members(actor_binding.role):
            return Response({"detail": "Only fleet admin/owner can view members."}, status=403)

        members = FleetPhoneBinding.objects.filter(fleet=fleet).select_related("user").order_by("created_at")
        return Response(FleetPhoneBindingSerializer(members, many=True).data, status=200)

    def post(self, request):
        serializer = FleetMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fleet_name = serializer.validated_data["fleet_name"].strip()
        phone_number = serializer.validated_data["phone_number"].strip()
        target_role = serializer.validated_data.get("role") or FleetPhoneBinding.Role.DRIVER

        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            return Response({"detail": "Fleet not found."}, status=404)

        actor_binding = _get_active_binding(user=request.user, fleet=fleet)
        if actor_binding is None:
            return Response({"detail": "You are not linked to this fleet."}, status=403)
        if not _can_manage_fleet_members(actor_binding.role):
            return Response({"detail": "Only fleet admin/owner can add members."}, status=403)
        if actor_binding.role == FleetPhoneBinding.Role.ADMIN and target_role == FleetPhoneBinding.Role.OWNER:
            return Response({"detail": "Admin cannot assign owner role."}, status=403)

        existing_binding = FleetPhoneBinding.objects.filter(
            fleet=fleet,
            phone_number=phone_number,
            role=target_role,
            is_active=True,
        ).first()
        if existing_binding is not None:
            return Response({"detail": "This phone number is already registered."}, status=400)

        username = f"fleet_member_{phone_number}"
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": serializer.validated_data.get("first_name", "").strip(),
                "last_name": serializer.validated_data.get("last_name", "").strip(),
                "email": serializer.validated_data.get("email", "").strip(),
                "is_active": True,
            },
        )
        update_fields = []
        for field in ("first_name", "last_name", "email"):
            value = serializer.validated_data.get(field, "").strip()
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
            role=target_role,
            is_active=True,
        )
        if target_role == FleetPhoneBinding.Role.DRIVER:
            DriverFleetMembership.objects.get_or_create(
                user=user,
                defaults={
                    "fleet": fleet,
                    "is_active": True,
                },
            )
        return Response(FleetPhoneBindingSerializer(binding).data, status=201)


class FleetMemberRoleUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = FleetMemberRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fleet_name = serializer.validated_data["fleet_name"].strip()
        phone_number = serializer.validated_data["phone_number"].strip()
        target_role = serializer.validated_data["role"]

        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            return Response({"detail": "Fleet not found."}, status=404)

        actor_binding = _get_active_binding(user=request.user, fleet=fleet)
        if actor_binding is None:
            return Response({"detail": "You are not linked to this fleet."}, status=403)
        if not _can_manage_fleet_members(actor_binding.role):
            return Response({"detail": "Only fleet admin/owner can change roles."}, status=403)

        target_binding = FleetPhoneBinding.objects.filter(fleet=fleet, phone_number=phone_number).first()
        if target_binding is None:
            return Response({"detail": "Fleet member not found for this phone number."}, status=404)

        if actor_binding.role == FleetPhoneBinding.Role.ADMIN:
            if target_binding.role == FleetPhoneBinding.Role.OWNER:
                return Response({"detail": "Admin cannot change owner role."}, status=403)
            if target_role == FleetPhoneBinding.Role.OWNER:
                return Response({"detail": "Admin cannot assign owner role."}, status=403)

        target_binding.role = target_role
        target_binding.save(update_fields=["role"])
        return Response(FleetPhoneBindingSerializer(target_binding).data, status=200)


class FleetDriverMappingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        fleet_name = request.query_params.get("fleet_name", "").strip()
        if not fleet_name:
            return Response({"detail": "fleet_name is required."}, status=400)

        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            return Response({"detail": "Fleet not found."}, status=404)

        actor_binding = _get_active_binding(user=request.user, fleet=fleet)
        if actor_binding is None:
            return Response({"detail": "You are not linked to this fleet."}, status=403)
        if not _can_manage_fleet_members(actor_binding.role):
            return Response({"detail": "Only fleet admin/owner can manage Yandex mappings."}, status=403)

        bindings = list(
            FleetPhoneBinding.objects.filter(
                fleet=fleet,
                role=FleetPhoneBinding.Role.DRIVER,
            )
            .select_related("user")
            .order_by("created_at", "id")
        )
        payload = _serialize_driver_mappings(fleet=fleet, bindings=bindings)
        return Response(DriverYandexMappingSerializer(payload, many=True).data, status=200)


class FleetDriverMappingUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, binding_id: int):
        serializer = DriverYandexMappingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fleet_name = serializer.validated_data["fleet_name"].strip()
        yandex_external_driver_id = serializer.validated_data.get("yandex_external_driver_id", "")

        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            return Response({"detail": "Fleet not found."}, status=404)

        actor_binding = _get_active_binding(user=request.user, fleet=fleet)
        if actor_binding is None:
            return Response({"detail": "You are not linked to this fleet."}, status=403)
        if not _can_manage_fleet_members(actor_binding.role):
            return Response({"detail": "Only fleet admin/owner can manage Yandex mappings."}, status=403)

        target_binding = (
            FleetPhoneBinding.objects.select_related("user", "fleet")
            .filter(id=binding_id, fleet=fleet)
            .first()
        )
        if target_binding is None:
            return Response({"detail": "Driver not found for this fleet."}, status=404)
        if target_binding.role != FleetPhoneBinding.Role.DRIVER:
            return Response({"detail": "Only driver members can have Yandex driver mappings."}, status=400)

        existing_membership = (
            DriverFleetMembership.objects.select_related("fleet")
            .filter(user=target_binding.user)
            .first()
        )
        if existing_membership is not None and existing_membership.fleet_id != fleet.id:
            return Response({"detail": "Driver is already assigned to another fleet mapping."}, status=403)

        if yandex_external_driver_id:
            duplicate_membership = (
                DriverFleetMembership.objects.filter(yandex_external_driver_id=yandex_external_driver_id)
                .exclude(user=target_binding.user)
                .first()
            )
            if duplicate_membership is not None:
                return Response({"detail": "This Yandex external driver ID is already mapped to another driver."}, status=400)

        try:
            with transaction.atomic():
                membership = existing_membership
                if membership is None and yandex_external_driver_id:
                    membership = DriverFleetMembership.objects.create(
                        user=target_binding.user,
                        fleet=fleet,
                        is_active=target_binding.is_active,
                        yandex_external_driver_id=yandex_external_driver_id,
                    )
                elif membership is not None:
                    membership.fleet = fleet
                    membership.is_active = target_binding.is_active
                    membership.yandex_external_driver_id = yandex_external_driver_id or None
                    membership.save(update_fields=["fleet", "is_active", "yandex_external_driver_id", "updated_at"])
        except IntegrityError:
            return Response({"detail": "This Yandex external driver ID is already mapped to another driver."}, status=400)

        payload = _serialize_driver_mappings(fleet=fleet, bindings=[target_binding])[0]
        return Response(DriverYandexMappingSerializer(payload).data, status=200)
