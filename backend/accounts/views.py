from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Fleet, FleetPhoneBinding, LoginCodeChallenge
from .serializers import (
    FleetSerializer,
    RegisterSerializer,
    RequestCodeSerializer,
    UserSerializer,
    VerifyCodeSerializer,
)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


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

        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            return Response({"detail": "Fleet not found."}, status=404)

        binding = FleetPhoneBinding.objects.filter(
            fleet=fleet, phone_number=phone_number, is_active=True, user__is_active=True
        ).first()
        if binding is None:
            return Response({"detail": "Wrong number for this fleet."}, status=400)

        with transaction.atomic():
            challenge = LoginCodeChallenge.objects.create(
                fleet=fleet,
                user=binding.user,
                phone_number=phone_number,
                code="123456",
                expires_at=timezone.now() + timedelta(minutes=5),
            )

        response_data = {"challenge_id": challenge.id, "expires_in_seconds": 300}
        if request.query_params.get("debug") == "1":
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
            if challenge.code != code:
                return Response({"detail": "Invalid code."}, status=400)

            challenge.is_consumed = True
            challenge.save(update_fields=["is_consumed"])

        refresh = RefreshToken.for_user(challenge.user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(challenge.user).data,
            }
        )
