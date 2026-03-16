from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Fleet, FleetPhoneBinding
from ledger.models import LedgerAccount, LedgerEntry
from wallet.models import BankAccount, Deposit, IncomingBankTransfer, Wallet, WithdrawalRequest

from .models import (
    BankSimulatorPayout,
    BogPayout,
    ExternalEvent,
    ProviderConnection,
    YandexDriverProfile,
    YandexSyncRun,
    YandexTransactionCategory,
    YandexTransactionRecord,
)
from .services import get_valid_bog_access_token, live_sync_yandex_data, sync_bog_deposits


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

    def test_purge_simulated_data_removes_sim_events_and_ledger_impact(self):
        self.client.post(reverse("yandex-connect"), data={}, format="json")
        self.client.post(
            reverse("yandex-simulate"),
            data={"mode": "steady", "count": 4},
            format="json",
        )
        import_response = self.client.post(reverse("yandex-import"), data={}, format="json")
        imported_total = Decimal(import_response.data["imported_total"])

        purge_response = self.client.post(reverse("yandex-purge-simulated"), data={}, format="json")
        self.assertEqual(purge_response.status_code, status.HTTP_200_OK)
        self.assertEqual(purge_response.data["deleted_events"], 4)
        self.assertEqual(Decimal(purge_response.data["removed_total"]), imported_total)

        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(ExternalEvent.objects.filter(connection__user=self.user, external_id__startswith="yandex-").count(), 0)

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

    @patch("integrations.views.test_live_yandex_connection")
    def test_test_connection_endpoint_updates_connection_status(self, mocked_test):
        mocked_test.return_value = {
            "ok": True,
            "configured": True,
            "mode": "live",
            "http_status": 200,
            "endpoint": "/v1/parks/driver-work-rules",
            "detail": "Connection test succeeded.",
            "response": {"ok": True},
        }

        response = self.client.post(reverse("yandex-test-connection"), data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["test"]["ok"])
        self.assertEqual(response.data["test"]["http_status"], 200)

        connection = ProviderConnection.objects.get(user=self.user, provider="yandex")
        self.assertEqual(connection.status, "active")
        self.assertIn("last_connection_test", connection.config)
        self.assertEqual(connection.config["last_connection_test"]["http_status"], 200)

    @patch("integrations.views.test_live_yandex_connection")
    def test_test_connection_endpoint_marks_error_on_failure(self, mocked_test):
        mocked_test.return_value = {
            "ok": False,
            "configured": True,
            "mode": "live",
            "http_status": 401,
            "endpoint": "/v1/parks/driver-work-rules",
            "detail": "Unauthorized: check X-Client-ID/X-API-Key.",
        }

        response = self.client.post(reverse("yandex-test-connection"), data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["test"]["ok"])
        self.assertEqual(response.data["test"]["http_status"], 401)

        connection = ProviderConnection.objects.get(user=self.user, provider="yandex")
        self.assertEqual(connection.status, "error")

    @patch("integrations.views.live_sync_yandex_data")
    def test_sync_live_endpoint_persists_last_sync_metadata(self, mocked_sync):
        mocked_sync.return_value = {
            "ok": True,
            "partial": False,
            "configured": True,
            "detail": "Live sync completed.",
            "drivers": {"http_status": 200, "fetched": 12},
            "transactions": {
                "http_status": 200,
                "fetched": 8,
                "stored_new_events": 6,
                "imported_count": 6,
                "imported_total": "41.20",
            },
            "cursor": {
                "from": "2026-03-01T00:00:00+04:00",
                "to": "2026-03-02T00:00:00+04:00",
                "next_from": "2026-03-02T00:00:01+04:00",
                "full_sync": False,
            },
            "errors": {"drivers": None, "transactions": None},
        }

        response = self.client.post(reverse("yandex-sync-live"), data={"limit": 50, "dry_run": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["sync"]["ok"])
        self.assertEqual(response.data["sync"]["transactions"]["imported_count"], 6)

        connection = ProviderConnection.objects.get(user=self.user, provider="yandex")
        self.assertEqual(connection.status, "active")
        self.assertIn("last_live_sync", connection.config)
        self.assertEqual(connection.config["last_live_sync"]["drivers_fetched"], 12)
        self.assertIn("last_transaction_cursor", connection.config)
        self.assertEqual(connection.config["last_transaction_cursor"]["next_from"], "2026-03-02T00:00:01+04:00")

    def test_sync_live_endpoint_validates_limit(self):
        response = self.client.post(reverse("yandex-sync-live"), data={"limit": 1000}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_driver_role_cannot_run_sync_live(self):
        fleet = Fleet.objects.create(name="Yandex Guard Fleet")
        FleetPhoneBinding.objects.create(
            fleet=fleet,
            user=self.user,
            phone_number="598900003",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        response = self.client.post(
            reverse("yandex-sync-live"),
            data={"limit": 10, "dry_run": True, "full_sync": False},
            format="json",
            HTTP_X_FLEET_NAME=fleet.name,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("integrations.views.sync_yandex_transaction_categories")
    def test_sync_categories_endpoint(self, mocked_sync):
        mocked_sync.return_value = {
            "ok": True,
            "configured": True,
            "detail": "Category sync completed.",
            "fetched": 3,
            "upserted": 3,
            "http_status": 200,
            "errors": None,
        }
        response = self.client.post(reverse("yandex-sync-categories"), data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["categories_sync"]["ok"])
        self.assertEqual(response.data["categories_sync"]["upserted"], 3)

    def test_list_sync_runs_endpoint(self):
        connect_response = self.client.post(reverse("yandex-connect"), data={}, format="json")
        connection = ProviderConnection.objects.get(id=connect_response.data["id"])
        YandexSyncRun.objects.create(
            connection=connection,
            trigger=YandexSyncRun.Trigger.API,
            status=YandexSyncRun.Status.OK,
            dry_run=True,
            full_sync=False,
            detail="test",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        response = self.client.get(reverse("yandex-sync-runs"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_categories_endpoint(self):
        connect_response = self.client.post(reverse("yandex-connect"), data={}, format="json")
        connection = ProviderConnection.objects.get(id=connect_response.data["id"])
        YandexTransactionCategory.objects.create(
            connection=connection,
            external_category_id="cat-1",
            code="earning",
            name="Earning",
            is_creatable=True,
            is_enabled=True,
        )
        response = self.client.get(reverse("yandex-categories"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_drivers_endpoint(self):
        connect_response = self.client.post(reverse("yandex-connect"), data={}, format="json")
        connection = ProviderConnection.objects.get(id=connect_response.data["id"])
        YandexDriverProfile.objects.create(
            connection=connection,
            external_driver_id="drv-1",
            first_name="Nika",
            last_name="Beridze",
            phone_number="+995598123123",
            status="active",
        )

        response = self.client.get(reverse("yandex-drivers"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["external_driver_id"], "drv-1")

    def test_list_transactions_endpoint(self):
        connect_response = self.client.post(reverse("yandex-connect"), data={}, format="json")
        connection = ProviderConnection.objects.get(id=connect_response.data["id"])
        event = ExternalEvent.objects.create(
            connection=connection,
            external_id="tx-1",
            event_type="earning",
            payload={"amount": "12.50"},
            processed=True,
        )
        YandexTransactionRecord.objects.create(
            connection=connection,
            external_event=event,
            external_transaction_id="tx-1",
            driver_external_id="drv-1",
            amount=Decimal("12.50"),
            currency="GEL",
            category="earning",
            direction="credit",
        )

        response = self.client.get(reverse("yandex-transactions"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["external_transaction_id"], "tx-1")

    def test_list_driver_summaries_endpoint(self):
        connect_response = self.client.post(reverse("yandex-connect"), data={}, format="json")
        connection = ProviderConnection.objects.get(id=connect_response.data["id"])
        YandexDriverProfile.objects.create(
            connection=connection,
            external_driver_id="drv-1",
            first_name="Nika",
            last_name="Beridze",
            phone_number="+995598123123",
            status="active",
        )
        event_one = ExternalEvent.objects.create(
            connection=connection,
            external_id="tx-earn",
            event_type="earning",
            payload={"amount": "12.50"},
            processed=True,
        )
        event_two = ExternalEvent.objects.create(
            connection=connection,
            external_id="tx-deduct",
            event_type="fine",
            payload={"amount": "-2.00"},
            processed=True,
        )
        YandexTransactionRecord.objects.create(
            connection=connection,
            external_event=event_one,
            external_transaction_id="tx-earn",
            driver_external_id="drv-1",
            amount=Decimal("12.50"),
            currency="GEL",
            category="earning",
            direction="credit",
        )
        YandexTransactionRecord.objects.create(
            connection=connection,
            external_event=event_two,
            external_transaction_id="tx-deduct",
            driver_external_id="drv-1",
            amount=Decimal("-2.00"),
            currency="GEL",
            category="penalty",
            direction="debit",
        )

        response = self.client.get(reverse("yandex-driver-summaries"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["driver"]["external_driver_id"], "drv-1")
        self.assertEqual(response.data[0]["summary"]["transaction_count"], 2)
        self.assertEqual(Decimal(response.data[0]["summary"]["total_earned"]), Decimal("12.50"))
        self.assertEqual(Decimal(response.data[0]["summary"]["total_deductions"]), Decimal("2.00"))
        self.assertEqual(Decimal(response.data[0]["summary"]["net_total"]), Decimal("10.50"))

    def test_driver_detail_endpoint(self):
        connect_response = self.client.post(reverse("yandex-connect"), data={}, format="json")
        connection = ProviderConnection.objects.get(id=connect_response.data["id"])
        YandexDriverProfile.objects.create(
            connection=connection,
            external_driver_id="drv-99",
            first_name="Ana",
            last_name="Kapanadze",
            phone_number="+995555111222",
            status="active",
        )
        event = ExternalEvent.objects.create(
            connection=connection,
            external_id="tx-99",
            event_type="earning",
            payload={"amount": "50.00"},
            processed=True,
        )
        YandexTransactionRecord.objects.create(
            connection=connection,
            external_event=event,
            external_transaction_id="tx-99",
            driver_external_id="drv-99",
            amount=Decimal("50.00"),
            currency="GEL",
            category="earning",
            direction="credit",
        )

        response = self.client.get(reverse("yandex-driver-detail", kwargs={"external_driver_id": "drv-99"}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["driver"]["external_driver_id"], "drv-99")
        self.assertEqual(response.data["summary"]["transaction_count"], 1)
        self.assertEqual(len(response.data["recent_transactions"]), 1)


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

    def test_reconciliation_summary_endpoint_returns_aggregate_report(self):
        withdrawal_id = self._create_withdrawal(amount="15.00")
        payout = self.client.post(reverse("bank-sim-submit"), data={"withdrawal_id": withdrawal_id}, format="json")
        payout_id = payout.data["id"]
        self.client.post(
            reverse("bank-sim-status-update", kwargs={"payout_id": payout_id}),
            data={"status": "settled"},
            format="json",
        )

        response = self.client.get(reverse("reconciliation-summary"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currency"], "GEL")
        self.assertIn("wallet", response.data)
        self.assertIn("yandex", response.data)
        self.assertIn("withdrawals", response.data)
        self.assertIn("bank_simulator", response.data)
        self.assertIn("bog", response.data)
        self.assertEqual(response.data["withdrawals"]["count"], 1)
        self.assertEqual(response.data["bank_simulator"]["count"], 1)


class BogTokenApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bog_user", password="pass1234")
        self.client.force_authenticate(self.user)

    @patch("integrations.views.test_live_bog_token_connection")
    def test_test_token_endpoint_updates_connection_status(self, mocked_test):
        mocked_test.return_value = {
            "ok": True,
            "configured": True,
            "provider": "bog",
            "http_status": 200,
            "endpoint": "https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token",
            "detail": "Token request succeeded.",
            "response": {
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": None,
                "access_token_received": True,
            },
        }

        response = self.client.post(reverse("bog-test-token"), data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["test"]["ok"])
        self.assertTrue(response.data["test"]["response"]["access_token_received"])
        self.assertNotIn("access_token", response.data["test"]["response"])

        connection = ProviderConnection.objects.get(
            user=self.user, provider=ProviderConnection.Provider.BANK_OF_GEORGIA
        )
        self.assertEqual(connection.status, "active")
        self.assertIn("last_token_test", connection.config)
        self.assertEqual(connection.config["last_token_test"]["http_status"], 200)

    @patch("integrations.views.test_live_bog_token_connection")
    def test_test_token_endpoint_marks_error_on_failure(self, mocked_test):
        mocked_test.return_value = {
            "ok": False,
            "configured": True,
            "provider": "bog",
            "http_status": 401,
            "endpoint": "https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token",
            "detail": "BoG token request failed.",
            "response": {"error": "invalid_client"},
        }

        response = self.client.post(reverse("bog-test-token"), data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["test"]["ok"])
        self.assertEqual(response.data["test"]["http_status"], 401)

        connection = ProviderConnection.objects.get(
            user=self.user, provider=ProviderConnection.Provider.BANK_OF_GEORGIA
        )
        self.assertEqual(connection.status, "error")

    @patch("integrations.services.test_live_bog_token_connection")
    def test_bog_access_token_is_cached_until_expiry_window(self, mocked_test):
        connection = ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="bog-cache-user",
            status="active",
            config={"mode": "live"},
        )
        cache.clear()
        mocked_test.return_value = {
            "ok": True,
            "configured": True,
            "provider": "bog",
            "http_status": 200,
            "endpoint": "https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token",
            "detail": "Token request succeeded.",
            "response": {
                "token_type": "Bearer",
                "expires_in": 1800,
                "scope": "cib-scope",
                "access_token_received": True,
                "access_token": "cached-token-value",
            },
        }

        first = get_valid_bog_access_token(connection=connection)
        second = get_valid_bog_access_token(connection=connection)

        self.assertEqual(first, "cached-token-value")
        self.assertEqual(second, "cached-token-value")
        self.assertEqual(mocked_test.call_count, 1)


class BogPayoutApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bog_payout_user", password="pass1234")
        self.client.force_authenticate(self.user)
        self.fleet, _ = Fleet.objects.get_or_create(name="New Tech")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598950001",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.wallet.balance = Decimal("150.00")
        self.wallet.save(update_fields=["balance"])
        self.bank_account = BankAccount.objects.create(
            user=self.user,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000002",
            beneficiary_name="Nika Beridze",
            beneficiary_inn="01001010101",
        )

    def _create_withdrawal(self, amount="25.00"):
        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.bank_account.id, "amount": amount, "note": "bog payout"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY=f"withdrawal-bog-{amount}",
            HTTP_X_REQUEST_ID=f"req-bog-{amount}",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return WithdrawalRequest.objects.get(id=response.data["id"])

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    def test_submit_bog_payout_moves_withdrawal_to_processing(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": [{"UniqueKey": 345678, "ResultCode": 0, "Match": 1}],
        }

        withdrawal = self._create_withdrawal()
        response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "processing")
        self.assertEqual(response.data["provider_unique_key"], 345678)
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.PROCESSING)
        self.assertEqual(BogPayout.objects.count(), 1)

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    def test_failed_bog_status_reverses_wallet_balance(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.side_effect = [
            {
                "ok": True,
                "http_status": 200,
                "body": [{"UniqueKey": 999111, "ResultCode": 0, "Match": 1}],
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {"Status": "Rejected", "ResultCode": 12, "Match": 1},
            },
        ]

        withdrawal = self._create_withdrawal(amount="30.00")
        submit_response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        payout_id = submit_response.data["id"]

        status_response = self.client.post(
            reverse("bog-status-sync", kwargs={"payout_id": payout_id}),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data["status"], "failed")
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.FAILED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("150.00"))

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    def test_sync_all_bog_statuses_endpoint_checks_open_payouts(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.side_effect = [
            {
                "ok": True,
                "http_status": 200,
                "body": [{"UniqueKey": 222333, "ResultCode": 0, "Match": 1}],
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {"Status": "Completed", "ResultCode": 0, "Match": 1},
            },
        ]

        withdrawal = self._create_withdrawal(amount="40.00")
        self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        response = self.client.post(
            reverse("bog-sync-all"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["checked_count"], 1)
        self.assertEqual(response.data["updated_count"], 1)
        self.assertEqual(response.data["error_count"], 0)

        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.COMPLETED)


class YandexLiveSyncServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="yandex_sync_user", password="pass1234")
        self.connection = ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.YANDEX,
            external_account_id="fleet-yandex-sync-user",
            status="active",
            config={"mode": "live"},
        )

    @patch("integrations.services._yandex_request")
    def test_live_sync_persists_normalized_driver_and_transaction_records(self, mocked_request):
        mocked_request.side_effect = [
            {
                "ok": True,
                "http_status": 200,
                "body": {
                    "driver_profiles": [
                        {
                            "id": "drv-1",
                            "first_name": "Nika",
                            "last_name": "Beridze",
                            "phone": "+995598123123",
                            "status": "active",
                        }
                    ]
                },
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {
                    "transactions": [
                        {
                            "id": "tx-100",
                            "driver_id": "drv-1",
                            "event_at": "2026-03-05T12:00:00+04:00",
                            "amount": "15.25",
                            "currency": "GEL",
                            "category": "earning",
                            "direction": "credit",
                        }
                    ]
                },
            },
        ]

        result = live_sync_yandex_data(connection=self.connection, limit=10, dry_run=False, full_sync=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["drivers"]["upserted_profiles"], 1)
        self.assertEqual(result["transactions"]["stored_new_events"], 1)
        self.assertEqual(result["transactions"]["imported_count"], 1)

        self.assertEqual(YandexDriverProfile.objects.filter(connection=self.connection).count(), 1)
        self.assertEqual(YandexTransactionRecord.objects.filter(connection=self.connection).count(), 1)
        event = ExternalEvent.objects.get(connection=self.connection, external_id="tx-100")
        self.assertEqual(event.payload["driver_id"], "drv-1")
        self.assertEqual(event.payload["currency"], "GEL")


class BogDepositSyncServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="deposit_sync_user", password="pass1234")
        self.connection = ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="bog-deposit-sync",
            status="active",
            config={"mode": "live"},
        )

    @patch("integrations.services._bog_request")
    def test_sync_bog_deposits_matches_reference_and_credits_wallet(self, mocked_request):
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": {
                "Records": [
                    {
                        "DocKey": 1001,
                        "Credit": "45.50",
                        "Nomination": f"Deposit EXP-{self.user.id:06d}",
                        "PayerName": "Levan Bagashvili",
                        "PayerInn": "01001010101",
                        "PostDate": "2026-03-16",
                        "ValueDate": "2026-03-16",
                    }
                ]
            },
        }

        with patch("integrations.services.settings.BOG_SOURCE_ACCOUNT_NUMBER", "GE00BG00000000000001"):
            result = sync_bog_deposits(connection=self.connection)

        self.assertTrue(result["ok"])
        self.assertEqual(result["credited_count"], 1)
        self.assertEqual(Decimal(result["credited_total"]), Decimal("45.50"))

        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, Decimal("45.50"))
        self.assertEqual(Deposit.objects.filter(user=self.user).count(), 1)
        self.assertEqual(IncomingBankTransfer.objects.filter(user=self.user).count(), 1)

        account = LedgerAccount.objects.get(user=self.user)
        self.assertEqual(LedgerEntry.objects.filter(account=account, entry_type="bank_deposit").count(), 1)
