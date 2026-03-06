from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Fleet, FleetPhoneBinding
from wallet.models import BankAccount, Wallet


User = get_user_model()


class InternalTransferByBankApiTests(APITestCase):
    def setUp(self):
        self.sender = User.objects.create_user(username="sender_user", password="pass1234")
        self.receiver = User.objects.create_user(username="receiver_user", password="pass1234")
        self.client.force_authenticate(self.sender)

        sender_wallet, _ = Wallet.objects.get_or_create(user=self.sender)
        sender_wallet.balance = Decimal("50.00")
        sender_wallet.save(update_fields=["balance"])

        BankAccount.objects.create(
            user=self.receiver,
            bank_name="TBC",
            account_number="GE29TB00000000000001",
            beneficiary_name="Receiver User",
        )

    def test_transfer_by_bank_details_success(self):
        response = self.client.post(
            reverse("internal-transfer-by-bank"),
            data={
                "bank_name": "TBC",
                "account_number": "GE29TB00000000000001",
                "beneficiary_name": "Receiver User",
                "amount": "10.00",
                "note": "Private transfer",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="bank-transfer-1",
            HTTP_X_REQUEST_ID="req-bank-transfer-1",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["receiver_username"], "receiver_user")

    def test_transfer_by_bank_details_not_found(self):
        response = self.client.post(
            reverse("internal-transfer-by-bank"),
            data={
                "bank_name": "Bank of Georgia",
                "account_number": "GE00000000000000000000",
                "beneficiary_name": "Nobody",
                "amount": "5.00",
                "note": "Private transfer",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="bank-transfer-2",
            HTTP_X_REQUEST_ID="req-bank-transfer-2",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_driver_role_cannot_create_transfer(self):
        fleet = Fleet.objects.create(name="Transfer Fleet")
        FleetPhoneBinding.objects.create(
            fleet=fleet,
            user=self.sender,
            phone_number="598900001",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        response = self.client.post(
            reverse("internal-transfer-by-bank"),
            data={
                "bank_name": "TBC",
                "account_number": "GE29TB00000000000001",
                "beneficiary_name": "Receiver User",
                "amount": "10.00",
                "note": "Private transfer",
            },
            format="json",
            HTTP_X_FLEET_NAME=fleet.name,
            HTTP_IDEMPOTENCY_KEY="bank-transfer-3",
            HTTP_X_REQUEST_ID="req-bank-transfer-3",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
