import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory
from rest_framework.test import APITestCase

from accounts.models import DriverFleetMembership, Fleet, FleetPhoneBinding, LoginCodeChallenge
from accounts.roles import get_request_fleet_binding, is_platform_admin, meets_min_role


class MockJsonHttpResponse:
    def __init__(self, payload: dict, *, status: int = 200):
        self.payload = payload
        self.status = status
        self.headers = {}

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@override_settings(OTP_PROVIDER="local", OTP_API_KEY="")
class FleetRoleManagementTests(APITestCase):
    def setUp(self):
        self.fleet = Fleet.objects.create(name="Role Test Fleet")
        self.owner = User.objects.create_user(username="fleet_owner_user", password="pass1234")
        self.admin = User.objects.create_user(username="fleet_admin_user", password="pass1234")
        self.driver = User.objects.create_user(username="fleet_driver_user", password="pass1234")
        self.target = User.objects.create_user(username="fleet_target_user", password="pass1234")

        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598111111",
            role=FleetPhoneBinding.Role.OWNER,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.admin,
            phone_number="598222222",
            role=FleetPhoneBinding.Role.ADMIN,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver,
            phone_number="598333333",
            role=FleetPhoneBinding.Role.DRIVER,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.target,
            phone_number="598444444",
            role=FleetPhoneBinding.Role.DRIVER,
        )

    def test_verify_code_response_contains_role(self):
        request_response = self.client.post(
            f"{reverse('request-fleet-code')}?debug=1",
            data={"fleet_name": self.fleet.name, "phone_number": "598333333"},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)
        challenge_id = request_response.data["challenge_id"]
        code = request_response.data["code"]

        verify_response = self.client.post(
            reverse("verify-fleet-code"),
            data={"challenge_id": challenge_id, "code": code},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data["role"], FleetPhoneBinding.Role.DRIVER)

    @override_settings(OTP_PROVIDER="verify_ge", OTP_API_KEY="test-key", OTP_TEST_FIXED_CODES="598333333:111333")
    def test_fixed_demo_code_bypasses_provider_for_whitelisted_number(self):
        request_response = self.client.post(
            reverse("request-fleet-code"),
            data={"fleet_name": self.fleet.name, "phone_number": "598333333"},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)
        challenge = LoginCodeChallenge.objects.get(id=request_response.data["challenge_id"])
        self.assertEqual(challenge.provider, "local")
        self.assertEqual(challenge.code, "111333")

        verify_response = self.client.post(
            reverse("verify-fleet-code"),
            data={"challenge_id": challenge.id, "code": "111333"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)

    def test_request_code_can_target_role_for_same_phone_number(self):
        shared_user = User.objects.create_user(username="shared_role_user", password="pass1234")
        shared_fleet = Fleet.objects.create(name="Shared Role Fleet")
        FleetPhoneBinding.objects.create(
            fleet=shared_fleet,
            user=shared_user,
            phone_number="598666666",
            role=FleetPhoneBinding.Role.OWNER,
        )
        FleetPhoneBinding.objects.create(
            fleet=shared_fleet,
            user=shared_user,
            phone_number="598666666",
            role=FleetPhoneBinding.Role.DRIVER,
        )

        request_response = self.client.post(
            f"{reverse('request-fleet-code')}?debug=1",
            data={
                "fleet_name": shared_fleet.name,
                "phone_number": "598666666",
                "role": FleetPhoneBinding.Role.DRIVER,
            },
            format="json",
        )

        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)
        challenge = LoginCodeChallenge.objects.get(id=request_response.data["challenge_id"])
        self.assertEqual(challenge.requested_role, FleetPhoneBinding.Role.DRIVER)

        verify_response = self.client.post(
            reverse("verify-fleet-code"),
            data={"challenge_id": challenge.id, "code": request_response.data["code"]},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data["role"], FleetPhoneBinding.Role.DRIVER)

    def test_admin_login_role_requires_internal_header_and_allowlisted_phone(self):
        request_response = self.client.post(
            f"{reverse('request-fleet-code')}?debug=1",
            data={
                "fleet_name": self.fleet.name,
                "phone_number": "598222222",
                "role": FleetPhoneBinding.Role.ADMIN,
            },
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(OTP_INTERNAL_ADMIN_PHONES="598222222")
    def test_internal_admin_login_role_allows_allowlisted_phone(self):
        request_response = self.client.post(
            f"{reverse('request-fleet-code')}?debug=1",
            data={
                "fleet_name": self.fleet.name,
                "phone_number": "598222222",
                "role": FleetPhoneBinding.Role.ADMIN,
            },
            format="json",
            HTTP_X_INTERNAL_ADMIN_LOGIN="1",
        )
        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)
        challenge = LoginCodeChallenge.objects.get(id=request_response.data["challenge_id"])
        self.assertEqual(challenge.requested_role, FleetPhoneBinding.Role.ADMIN)

        verify_response = self.client.post(
            reverse("verify-fleet-code"),
            data={"challenge_id": challenge.id, "code": request_response.data["code"]},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data["role"], FleetPhoneBinding.Role.ADMIN)

    def test_driver_cannot_list_members(self):
        self.client.force_authenticate(self.driver)
        response = self.client.get(reverse("fleet-members"), {"fleet_name": self.fleet.name})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_promote_driver_to_operator(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            reverse("fleet-member-role-update"),
            data={
                "fleet_name": self.fleet.name,
                "phone_number": "598444444",
                "role": FleetPhoneBinding.Role.OPERATOR,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        binding = FleetPhoneBinding.objects.get(fleet=self.fleet, phone_number="598444444")
        self.assertEqual(binding.role, FleetPhoneBinding.Role.OPERATOR)

    def test_admin_cannot_assign_owner_role(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            reverse("fleet-member-role-update"),
            data={
                "fleet_name": self.fleet.name,
                "phone_number": "598444444",
                "role": FleetPhoneBinding.Role.OWNER,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_assign_admin_role(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            reverse("fleet-member-role-update"),
            data={
                "fleet_name": self.fleet.name,
                "phone_number": "598444444",
                "role": FleetPhoneBinding.Role.ADMIN,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        binding = FleetPhoneBinding.objects.get(fleet=self.fleet, phone_number="598444444")
        self.assertEqual(binding.role, FleetPhoneBinding.Role.ADMIN)

    def test_owner_can_add_driver_member(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            reverse("fleet-members"),
            data={
                "fleet_name": self.fleet.name,
                "phone_number": "598555000",
                "first_name": "New",
                "last_name": "Driver",
                "role": FleetPhoneBinding.Role.DRIVER,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], FleetPhoneBinding.Role.DRIVER)
        binding = FleetPhoneBinding.objects.get(fleet=self.fleet, phone_number="598555000")
        self.assertEqual(binding.user.first_name, "New")
        self.assertTrue(DriverFleetMembership.objects.filter(user=binding.user, fleet=self.fleet).exists())

    def test_driver_cannot_add_driver_member(self):
        self.client.force_authenticate(self.driver)

        response = self.client.post(
            reverse("fleet-members"),
            data={
                "fleet_name": self.fleet.name,
                "phone_number": "598555001",
                "role": FleetPhoneBinding.Role.DRIVER,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_request_binding_prefers_highest_role_for_same_fleet(self):
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.admin,
            phone_number="598999999",
            role=FleetPhoneBinding.Role.DRIVER,
        )
        request = APIRequestFactory().post("/api/integrations/bog/test-token/", {}, format="json")
        request.user = self.admin
        request.query_params = {}
        request.headers = {"X-Fleet-Name": self.fleet.name}

        binding = get_request_fleet_binding(user=self.admin, request=request)
        self.assertIsNotNone(binding)
        self.assertEqual(binding.role, FleetPhoneBinding.Role.ADMIN)

    def test_request_binding_honors_active_role_header(self):
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.admin,
            phone_number="598999998",
            role=FleetPhoneBinding.Role.DRIVER,
        )
        request = APIRequestFactory().post("/api/auth/me/", {}, format="json")
        request.user = self.admin
        request.query_params = {}
        request.headers = {
            "X-Fleet-Name": self.fleet.name,
            "X-Active-Role": FleetPhoneBinding.Role.DRIVER,
        }

        binding = get_request_fleet_binding(user=self.admin, request=request)
        self.assertIsNotNone(binding)
        self.assertEqual(binding.role, FleetPhoneBinding.Role.DRIVER)

    def test_meets_min_role_fails_closed_without_binding(self):
        self.assertFalse(
            meets_min_role(binding=None, minimum_role=FleetPhoneBinding.Role.DRIVER)
        )

    def test_is_platform_admin_uses_staff_flag_only(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])

        self.assertTrue(is_platform_admin(user=self.owner))
        self.assertFalse(is_platform_admin(user=self.admin))

    def test_me_response_includes_platform_admin_flag(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse("me"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_platform_admin"])


class DriverYandexMappingApiTests(APITestCase):
    def setUp(self):
        self.fleet = Fleet.objects.create(name="Mapping Fleet")
        self.other_fleet = Fleet.objects.create(name="Mapping Other Fleet")
        self.owner = User.objects.create_user(username="mapping_owner", password="pass1234")
        self.other_owner = User.objects.create_user(username="mapping_other_owner", password="pass1234")
        self.driver = User.objects.create_user(username="mapping_driver", password="pass1234")

        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598555552",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_owner,
            phone_number="598555553",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        self.driver_binding = FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver,
            phone_number="598555551",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )

    def test_owner_can_list_driver_mappings(self):
        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="drv-map-1",
            is_active=True,
        )
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse("fleet-driver-mappings"), {"fleet_name": self.fleet.name})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["username"], self.driver.username)
        self.assertTrue(response.data[0]["has_mapping"])
        self.assertEqual(response.data[0]["yandex_external_driver_id"], "drv-map-1")

    def test_driver_cannot_list_driver_mappings(self):
        self.client.force_authenticate(self.driver)

        response = self.client.get(reverse("fleet-driver-mappings"), {"fleet_name": self.fleet.name})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_update_driver_mapping(self):
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            reverse("fleet-driver-mapping-update", kwargs={"binding_id": self.driver_binding.id}),
            data={"fleet_name": self.fleet.name, "yandex_external_driver_id": "drv-map-2"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        membership = DriverFleetMembership.objects.get(user=self.driver)
        self.assertEqual(membership.fleet, self.fleet)
        self.assertEqual(membership.yandex_external_driver_id, "drv-map-2")
        self.assertTrue(response.data["has_mapping"])

    def test_cross_fleet_mapping_update_is_blocked(self):
        self.client.force_authenticate(self.other_owner)

        response = self.client.patch(
            reverse("fleet-driver-mapping-update", kwargs={"binding_id": self.driver_binding.id}),
            data={"fleet_name": self.other_fleet.name, "yandex_external_driver_id": "drv-map-cross"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_driver_assigned_to_other_fleet_cannot_be_hijacked(self):
        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.other_fleet,
            yandex_external_driver_id="drv-other-fleet",
            is_active=True,
        )
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            reverse("fleet-driver-mapping-update", kwargs={"binding_id": self.driver_binding.id}),
            data={"fleet_name": self.fleet.name, "yandex_external_driver_id": "drv-map-3"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(
    OTP_PROVIDER="verify_ge",
    OTP_API_KEY="test-otp-key",
    OTP_BASE_URL="https://api.verify.ge/api/v1",
    OTP_CODE_LENGTH=6,
)
class OtpProviderIntegrationTests(APITestCase):
    def setUp(self):
        self.fleet = Fleet.objects.create(name="OTP Fleet")
        self.user = User.objects.create_user(username="otp_driver_user", password="pass1234")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598777777",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )

    @patch("accounts.services.urlopen")
    def test_request_code_uses_verify_ge_provider_when_api_key_is_configured(self, mocked_urlopen):
        mocked_urlopen.return_value = MockJsonHttpResponse({"success": True, "requestId": "req_123"})

        response = self.client.post(
            reverse("request-fleet-code"),
            data={"fleet_name": self.fleet.name, "phone_number": "598777777"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        challenge = LoginCodeChallenge.objects.get(id=response.data["challenge_id"])
        self.assertEqual(challenge.provider, "verify_ge")
        self.assertEqual(challenge.provider_hash, "req_123")
        self.assertEqual(challenge.code, "")

        request_body = json.loads(mocked_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(
            request_body,
            {
                "phoneNumber": "+995598777777",
                "channel": "SMS",
                "ttl": 300,
                "length": 6,
            },
        )

    @override_settings(OTP_TEST_PHONE_NUMBER="598950001")
    @patch("accounts.services.urlopen")
    def test_verify_ge_can_route_delivery_to_free_plan_test_number(self, mocked_urlopen):
        mocked_urlopen.return_value = MockJsonHttpResponse({"success": True, "requestId": "req_123"})

        response = self.client.post(
            reverse("request-fleet-code"),
            data={"fleet_name": self.fleet.name, "phone_number": "598777777"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        challenge = LoginCodeChallenge.objects.get(id=response.data["challenge_id"])
        self.assertEqual(challenge.phone_number, "598777777")

        request_body = json.loads(mocked_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(request_body["phoneNumber"], "+995598950001")

    @patch("accounts.services.urlopen")
    def test_verify_code_uses_verify_ge_provider_verification(self, mocked_urlopen):
        mocked_urlopen.return_value = MockJsonHttpResponse({"success": True, "verified": True})
        challenge = LoginCodeChallenge.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598777777",
            code="",
            provider="verify_ge",
            provider_hash="req_123",
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = self.client.post(
            reverse("verify-fleet-code"),
            data={"challenge_id": challenge.id, "code": "654321"},
            format="json",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        challenge.refresh_from_db()
        self.assertTrue(challenge.is_consumed)

        request_body = json.loads(mocked_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(
            request_body,
            {
                "requestId": "req_123",
                "code": "654321",
                "ipAddress": "127.0.0.1",
            },
        )


class FleetRegistrationApiTests(APITestCase):
    def test_register_fleet_creates_owner_binding(self):
        response = self.client.post(
            reverse("fleet-register"),
            data={
                "fleet_name": "Fresh Fleet",
                "phone_number": "598123456",
                "first_name": "Fleet",
                "last_name": "Owner",
                "email": "owner@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Fresh Fleet")
        fleet = Fleet.objects.get(name="Fresh Fleet")
        binding = FleetPhoneBinding.objects.get(fleet=fleet, phone_number="598123456")
        self.assertEqual(binding.role, FleetPhoneBinding.Role.OWNER)
        self.assertEqual(binding.user.first_name, "Fleet")
        self.assertEqual(binding.user.email, "owner@example.com")
        self.assertTrue(DriverFleetMembership.objects.filter(user=binding.user, fleet=fleet).exists())

    def test_register_fleet_rejects_existing_fleet_name(self):
        Fleet.objects.create(name="Fresh Fleet")

        response = self.client.post(
            reverse("fleet-register"),
            data={"fleet_name": "fresh fleet", "phone_number": "598123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_driver_creates_driver_binding_for_existing_fleet(self):
        fleet = Fleet.objects.create(name="Fresh Fleet")

        response = self.client.post(
            reverse("driver-register"),
            data={
                "fleet_name": "Fresh Fleet",
                "phone_number": "598123457",
                "first_name": "Fresh",
                "last_name": "Driver",
                "email": "driver@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        binding = FleetPhoneBinding.objects.get(fleet=fleet, phone_number="598123457")
        self.assertEqual(binding.role, FleetPhoneBinding.Role.DRIVER)
        self.assertEqual(binding.user.first_name, "Fresh")
        self.assertTrue(DriverFleetMembership.objects.filter(user=binding.user, fleet=fleet).exists())
