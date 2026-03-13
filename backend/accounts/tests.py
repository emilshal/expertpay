from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory
from rest_framework.test import APITestCase

from accounts.models import Fleet, FleetPhoneBinding
from accounts.roles import get_request_fleet_binding


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
            reverse("request-fleet-code"),
            data={"fleet_name": self.fleet.name, "phone_number": "598333333"},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)
        challenge_id = request_response.data["challenge_id"]

        verify_response = self.client.post(
            reverse("verify-fleet-code"),
            data={"challenge_id": challenge_id, "code": "123456"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data["role"], FleetPhoneBinding.Role.DRIVER)

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
