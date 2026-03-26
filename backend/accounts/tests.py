from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory
from rest_framework.test import APITestCase

from accounts.models import DriverFleetMembership, Fleet, FleetPhoneBinding
from accounts.roles import get_request_fleet_binding, is_platform_admin, meets_min_role


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
