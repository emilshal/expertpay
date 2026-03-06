from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Fleet, FleetPhoneBinding
from ledger.models import LedgerAccount, LedgerEntry

from .models import Wallet


User = get_user_model()


class WalletTopUpApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="wallet_user", password="pass1234")
        self.client.force_authenticate(self.user)

    def test_top_up_increases_wallet_and_creates_ledger_entry(self):
        response = self.client.post(
            reverse("wallet-top-up"),
            data={"amount": "25.00", "note": "sandbox fund"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="topup-key-1",
            HTTP_X_REQUEST_ID="req-topup-1",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["credited_amount"], "25.00")

        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, Decimal("25.00"))

        account = LedgerAccount.objects.get(user=self.user)
        entries = LedgerEntry.objects.filter(account=account, entry_type="sandbox_topup")
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().amount, Decimal("25.00"))

    def test_top_up_is_idempotent(self):
        payload = {"amount": "10.00", "note": "idempotent"}
        headers = {"HTTP_IDEMPOTENCY_KEY": "topup-key-2", "HTTP_X_REQUEST_ID": "req-topup-2"}

        first = self.client.post(reverse("wallet-top-up"), data=payload, format="json", **headers)
        second = self.client.post(reverse("wallet-top-up"), data=payload, format="json", **headers)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, Decimal("10.00"))

    def test_driver_role_cannot_top_up(self):
        fleet = Fleet.objects.create(name="Wallet Fleet")
        FleetPhoneBinding.objects.create(
            fleet=fleet,
            user=self.user,
            phone_number="598900002",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        response = self.client.post(
            reverse("wallet-top-up"),
            data={"amount": "5.00", "note": "blocked"},
            format="json",
            HTTP_X_FLEET_NAME=fleet.name,
            HTTP_IDEMPOTENCY_KEY="topup-key-3",
            HTTP_X_REQUEST_ID="req-topup-3",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
