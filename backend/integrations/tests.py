from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ledger.models import LedgerAccount, LedgerEntry
from wallet.models import Wallet

from .models import ExternalEvent, ProviderConnection


User = get_user_model()


class YandexSimulatorApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fleet_owner", password="pass1234")
        self.client.force_authenticate(self.user)

    def test_full_simulate_import_reconcile_flow(self):
        connect_response = self.client.post(reverse("yandex-connect"), data={}, format="json")
        self.assertEqual(connect_response.status_code, status.HTTP_201_CREATED)
        connection_id = connect_response.data["id"]

        simulate_response = self.client.post(
            reverse("yandex-simulate"),
            data={"mode": "steady", "count": 6},
            format="json",
        )
        self.assertEqual(simulate_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(simulate_response.data["connection_id"], connection_id)
        self.assertEqual(simulate_response.data["requested_count"], 6)
        self.assertEqual(simulate_response.data["stored_count"], 6)

        import_response = self.client.post(reverse("yandex-import"), data={}, format="json")
        self.assertEqual(import_response.status_code, status.HTTP_200_OK)
        self.assertEqual(import_response.data["imported_count"], 6)
        imported_total = Decimal(import_response.data["imported_total"])
        self.assertNotEqual(imported_total, Decimal("0.00"))

        # Import is one-time for unprocessed events.
        second_import = self.client.post(reverse("yandex-import"), data={}, format="json")
        self.assertEqual(second_import.status_code, status.HTTP_200_OK)
        self.assertEqual(second_import.data["imported_count"], 0)

        reconcile_response = self.client.get(reverse("yandex-reconcile"))
        self.assertEqual(reconcile_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reconcile_response.data["status"], "OK")
        self.assertEqual(Decimal(reconcile_response.data["delta"]), Decimal("0.00"))
        self.assertEqual(reconcile_response.data["imported_events"], 6)

        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, imported_total)

        account = LedgerAccount.objects.get(user=self.user)
        yandex_entries = LedgerEntry.objects.filter(account=account, entry_type="yandex_earning")
        self.assertEqual(yandex_entries.count(), 6)
        self.assertEqual(sum(entry.amount for entry in yandex_entries), imported_total)

        processed_events = ExternalEvent.objects.filter(
            connection__id=connection_id,
            processed=True,
        )
        self.assertEqual(processed_events.count(), 6)

    def test_events_endpoint_returns_created_events(self):
        self.client.post(reverse("yandex-connect"), data={}, format="json")
        self.client.post(
            reverse("yandex-simulate"),
            data={"mode": "steady", "count": 3},
            format="json",
        )

        events_response = self.client.get(reverse("yandex-events"))
        self.assertEqual(events_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(events_response.data), 3)
        self.assertIn("external_id", events_response.data[0])

    def test_connection_is_reused_for_same_user(self):
        first = self.client.post(reverse("yandex-connect"), data={}, format="json")
        second = self.client.post(reverse("yandex-connect"), data={}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(
            ProviderConnection.objects.filter(user=self.user, provider="yandex").count(),
            1,
        )
