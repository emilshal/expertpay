from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ledger.models import LedgerAccount, LedgerEntry
from wallet.models import BankAccount, Wallet, WithdrawalRequest

from .models import BankSimulatorPayout, ExternalEvent, ProviderConnection


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


class BankSimulatorApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="banksim_user", password="pass1234")
        self.client.force_authenticate(self.user)
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user, defaults={"balance": Decimal("120.00")})
        self.wallet.balance = Decimal("120.00")
        self.wallet.save(update_fields=["balance"])

        self.bank_account = BankAccount.objects.create(
            user=self.user,
            bank_name="TBC",
            account_number="GE29TB00000000000001",
            beneficiary_name="Bank Sim User",
        )

    def _create_withdrawal(self, amount="30.00"):
        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.bank_account.id, "amount": amount, "note": "test payout"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="withdrawal-test-key",
            HTTP_X_REQUEST_ID="req-withdraw-1",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response.data["id"]

    def test_submit_and_settle_bank_sim_payout(self):
        withdrawal_id = self._create_withdrawal()

        connect_response = self.client.post(reverse("bank-sim-connect"), data={}, format="json")
        self.assertEqual(connect_response.status_code, status.HTTP_201_CREATED)

        submit_response = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": withdrawal_id},
            format="json",
        )
        self.assertIn(submit_response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        payout_id = submit_response.data["id"]
        self.assertEqual(submit_response.data["status"], "accepted")

        status_response = self.client.post(
            reverse("bank-sim-status-update", kwargs={"payout_id": payout_id}),
            data={"status": "settled"},
            format="json",
        )
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data["status"], "settled")

        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.COMPLETED)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("90.00"))

    def test_failed_bank_sim_payout_reverses_wallet_balance(self):
        withdrawal_id = self._create_withdrawal(amount="20.00")
        submit_response = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": withdrawal_id},
            format="json",
        )
        self.assertIn(submit_response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        payout_id = submit_response.data["id"]

        fail_response = self.client.post(
            reverse("bank-sim-status-update", kwargs={"payout_id": payout_id}),
            data={"status": "failed", "failure_reason": "invalid account"},
            format="json",
        )
        self.assertEqual(fail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(fail_response.data["status"], "failed")

        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.FAILED)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("120.00"))

        account = LedgerAccount.objects.get(user=self.user)
        reversals = LedgerEntry.objects.filter(
            account=account,
            reference_type="withdrawal",
            reference_id=str(withdrawal_id),
            entry_type="withdrawal_reversal",
        )
        self.assertEqual(reversals.count(), 1)
        self.assertEqual(reversals.first().amount, Decimal("20.00"))

    def test_list_bank_sim_payouts_returns_user_payouts(self):
        withdrawal_id = self._create_withdrawal(amount="10.00")
        self.client.post(reverse("bank-sim-submit"), data={"withdrawal_id": withdrawal_id}, format="json")

        list_response = self.client.get(reverse("bank-sim-payouts"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["withdrawal_id"], withdrawal_id)
        self.assertEqual(BankSimulatorPayout.objects.count(), 1)
