from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import DriverFleetMembership, Fleet, FleetPhoneBinding
from ledger.models import LedgerAccount, LedgerEntry
from ledger.services import (
    create_ledger_entry,
    get_account_balance,
    get_or_create_driver_available_account,
    get_or_create_fleet_reserve_account,
    get_or_create_payout_clearing_account,
    get_or_create_platform_fee_account,
    get_or_create_treasury_account,
    record_driver_earning_allocation,
    record_fleet_reserve_deposit,
)
from wallet.models import BankAccount, Deposit, IncomingBankTransfer, Wallet, WithdrawalRequest

from .models import (
    BankSimulatorPayout,
    BogCardOrder,
    BogPayout,
    ExternalEvent,
    ProviderConnection,
    YandexDriverProfile,
    YandexSyncRun,
    YandexTransactionCategory,
    YandexTransactionRecord,
)
from .services import (
    create_bog_card_order,
    get_valid_bog_access_token,
    import_unprocessed_events,
    live_sync_yandex_data,
    sync_bog_card_order,
    sync_bog_deposits,
)


User = get_user_model()


class YandexSimulatorApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fleet_owner", password="pass1234")
        self.fleet = Fleet.objects.create(name="Yandex Simulator Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598700001",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        self.client.force_authenticate(self.user)

    def _create_driver_mapping(self, external_driver_id: str):
        index = external_driver_id.split("-")[-1]
        driver = User.objects.create_user(username=f"driver_{index}", password="pass1234")
        DriverFleetMembership.objects.create(
            user=driver,
            fleet=self.fleet,
            yandex_external_driver_id=external_driver_id,
            is_active=True,
        )
        return driver

    def test_full_simulate_import_reconcile_flow(self):
        mapped_drivers = [self._create_driver_mapping(f"drv-{1000 + index}") for index in range(6)]
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

        yandex_entries = LedgerEntry.objects.filter(
            account__account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
            entry_type="driver_earning_allocation",
        )
        self.assertEqual(yandex_entries.count(), 6)
        self.assertEqual(sum(entry.amount for entry in yandex_entries), imported_total)
        self.assertEqual(
            sum(get_account_balance(LedgerAccount.objects.get(user=driver, account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE)) for driver in mapped_drivers),
            imported_total,
        )

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
        drivers = [self._create_driver_mapping(f"drv-{1000 + index}") for index in range(4)]
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

        for driver in drivers:
            account = LedgerAccount.objects.get(user=driver, account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE)
            self.assertEqual(get_account_balance(account), Decimal("0.00"))
        self.assertEqual(ExternalEvent.objects.filter(connection__user=self.user, external_id__startswith="yandex-").count(), 0)


class IntegrationRoleAuthorizationTests(APITestCase):
    def setUp(self):
        self.unbound_user = User.objects.create_user(username="integrations_unbound", password="pass1234")
        self.owner = User.objects.create_user(username="integrations_owner", password="pass1234")
        self.fleet = Fleet.objects.create(name="Integrations Auth Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598700099",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )

    def test_unbound_user_cannot_run_admin_protected_yandex_test(self):
        self.client.force_authenticate(self.unbound_user)
        response = self.client.post(reverse("yandex-test-connection"), data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("integrations.views.test_live_yandex_connection")
    def test_bound_owner_can_run_admin_protected_yandex_test(self, mocked_test):
        mocked_test.return_value = {
            "ok": True,
            "configured": True,
            "http_status": 200,
            "endpoint": "/test",
            "detail": "ok",
            "response": {},
        }
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            reverse("yandex-test-connection"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_platform_admin_can_access_platform_only_summary_without_fleet_binding(self):
        self.unbound_user.is_staff = True
        self.unbound_user.save(update_fields=["is_staff"])
        self.client.force_authenticate(self.unbound_user)

        response = self.client.get(reverse("platform-finance-summary"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("platform_fee_balance", response.data)

    def test_fleet_roles_cannot_access_platform_only_summary(self):
        for user in [self.owner]:
            self.client.force_authenticate(user)
            response = self.client.get(reverse("platform-finance-summary"), HTTP_X_FLEET_NAME=self.fleet.name)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        operator = User.objects.create_user(username="integrations_operator", password="pass1234")
        driver = User.objects.create_user(username="integrations_driver", password="pass1234")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=operator,
            phone_number="598700097",
            role=FleetPhoneBinding.Role.OPERATOR,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=driver,
            phone_number="598700096",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )

        for user in [operator, driver]:
            self.client.force_authenticate(user)
            response = self.client.get(reverse("platform-finance-summary"), HTTP_X_FLEET_NAME=self.fleet.name)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_admin_access_does_not_replace_fleet_role_checks(self):
        self.unbound_user.is_staff = True
        self.unbound_user.save(update_fields=["is_staff"])
        self.client.force_authenticate(self.unbound_user)

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PlatformEarningsApiTests(APITestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_user(username="platform_admin_user", password="pass1234", is_staff=True)
        self.owner = User.objects.create_user(username="platform_owner_user", password="pass1234")
        self.driver = User.objects.create_user(username="platform_driver_user", password="pass1234")
        self.fleet = Fleet.objects.create(name="Platform Earnings Fleet")
        self.other_fleet = Fleet.objects.create(name="Platform Earnings Other Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598711111",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver,
            phone_number="598711112",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )

    def test_platform_admin_can_fetch_platform_earnings_totals(self):
        fee_account = get_or_create_platform_fee_account()
        fleet_withdrawal = WithdrawalRequest.objects.create(
            user=self.driver,
            wallet=Wallet.objects.get_or_create(user=self.driver)[0],
            fleet=self.fleet,
            bank_account=BankAccount.objects.create(
                user=self.driver,
                bank_name="Bank of Georgia",
                account_number="GE64BG00000000004001",
                beneficiary_name="Platform Driver",
                beneficiary_inn="01010101010",
            ),
            amount=Decimal("25.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PROCESSING,
        )
        other_driver = User.objects.create_user(username="platform_other_driver", password="pass1234")
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=other_driver,
            phone_number="598711113",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        other_withdrawal = WithdrawalRequest.objects.create(
            user=other_driver,
            wallet=Wallet.objects.get_or_create(user=other_driver)[0],
            fleet=self.other_fleet,
            bank_account=BankAccount.objects.create(
                user=other_driver,
                bank_name="TBC Bank",
                account_number="GE64TB00000000004002",
                beneficiary_name="Other Platform Driver",
                beneficiary_inn="02020202020",
            ),
            amount=Decimal("30.00"),
            fee_amount=Decimal("3.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PROCESSING,
        )
        create_ledger_entry(
            account=fee_account,
            amount=Decimal("2.00"),
            entry_type="withdrawal_platform_fee_credit",
            created_by=self.owner,
            currency="GEL",
            reference_type="withdrawal",
            reference_id=str(fleet_withdrawal.id),
        )
        create_ledger_entry(
            account=fee_account,
            amount=Decimal("3.00"),
            entry_type="withdrawal_platform_fee_credit",
            created_by=self.owner,
            currency="GEL",
            reference_type="withdrawal",
            reference_id=str(other_withdrawal.id),
        )
        create_ledger_entry(
            account=fee_account,
            amount=Decimal("-1.00"),
            entry_type="withdrawal_platform_fee_reversal",
            created_by=self.owner,
            currency="GEL",
            reference_type="withdrawal",
            reference_id=str(other_withdrawal.id),
        )

        self.client.force_authenticate(self.platform_admin)
        response = self.client.get(reverse("platform-earnings"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_fees_earned"], "4.00")
        self.assertEqual(response.data["recent_totals"]["last_7_days"], "4.00")
        self.assertEqual(response.data["recent_totals"]["last_30_days"], "4.00")
        by_fleet = {item["fleet_id"]: item for item in response.data["fees_by_fleet"]}
        self.assertEqual(by_fleet[self.fleet.id]["fleet_name"], self.fleet.name)
        self.assertEqual(by_fleet[self.fleet.id]["total_fees_earned"], "2.00")
        self.assertEqual(by_fleet[self.other_fleet.id]["fleet_name"], self.other_fleet.name)
        self.assertEqual(by_fleet[self.other_fleet.id]["total_fees_earned"], "2.00")

    def test_fleet_users_cannot_access_platform_earnings(self):
        for user, role_user in [(self.owner, self.owner), (self.driver, self.driver)]:
            self.client.force_authenticate(role_user)
            response = self.client.get(reverse("platform-earnings"), HTTP_X_FLEET_NAME=self.fleet.name)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class YandexDriverBalanceImportTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="yandex_owner", password="pass1234")
        self.user = self.owner
        self.fleet = Fleet.objects.create(name="Yandex Import Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598722222",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        self.client.force_authenticate(self.user)
        self.connection = None

    def _ensure_connection(self):
        if self.connection is None:
            self.connection = ProviderConnection.objects.create(
                user=self.user,
                provider=ProviderConnection.Provider.YANDEX,
                external_account_id="yandex-import-fleet",
                status="active",
                config={"mode": "live"},
            )
        return self.connection

    def _create_driver_membership(self, username: str, external_driver_id: str):
        driver = User.objects.create_user(username=username, password="pass1234")
        DriverFleetMembership.objects.create(
            user=driver,
            fleet=self.fleet,
            yandex_external_driver_id=external_driver_id,
            is_active=True,
        )
        return driver

    def _create_event(self, *, external_id: str, driver_external_id: str, amount: str):
        event = ExternalEvent.objects.create(
            connection=self._ensure_connection(),
            external_id=external_id,
            event_type="earning",
            payload={
                "external_id": external_id,
                "driver_id": driver_external_id,
                "net_amount": amount,
                "currency": "GEL",
            },
            processed=False,
        )
        YandexTransactionRecord.objects.create(
            connection=self._ensure_connection(),
            external_event=event,
            external_transaction_id=external_id,
            driver_external_id=driver_external_id,
            amount=Decimal(amount),
            currency="GEL",
            category="earning",
            direction="credit",
        )
        return event

    def test_synced_earning_increases_driver_available_balance(self):
        driver = self._create_driver_membership("mapped_driver", "drv-201")
        self._create_event(external_id="tx-201", driver_external_id="drv-201", amount="17.40")

        result = import_unprocessed_events(connection=self._ensure_connection())

        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(Decimal(result["imported_total"]), Decimal("17.40"))
        account = LedgerAccount.objects.get(user=driver, account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE)
        self.assertEqual(get_account_balance(account), Decimal("17.40"))

    def test_driver_mapping_uses_yandex_external_driver_id(self):
        driver = self._create_driver_membership("mapped_driver_two", "drv-202")
        self._create_event(external_id="tx-202", driver_external_id="drv-202", amount="9.00")

        import_unprocessed_events(connection=self._ensure_connection())

        entry = LedgerEntry.objects.get(
            account__user=driver,
            account__account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
            reference_id=str(ExternalEvent.objects.get(external_id="tx-202").id),
        )
        self.assertEqual(entry.metadata["driver_external_id"], "drv-202")

    def test_duplicate_yandex_event_does_not_double_credit(self):
        driver = self._create_driver_membership("mapped_driver_three", "drv-203")
        event = self._create_event(external_id="tx-203", driver_external_id="drv-203", amount="11.25")

        first = import_unprocessed_events(connection=self._ensure_connection())
        second = import_unprocessed_events(connection=self._ensure_connection())

        self.assertEqual(first["imported_count"], 1)
        self.assertEqual(second["imported_count"], 0)
        account = LedgerAccount.objects.get(user=driver, account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE)
        self.assertEqual(get_account_balance(account), Decimal("11.25"))
        self.assertEqual(
            LedgerEntry.objects.filter(
                account=account,
                reference_type="external_event",
                reference_id=str(event.id),
            ).count(),
            1,
        )

    def test_different_drivers_in_same_fleet_stay_isolated(self):
        driver_one = self._create_driver_membership("mapped_driver_four", "drv-204")
        driver_two = self._create_driver_membership("mapped_driver_five", "drv-205")
        self._create_event(external_id="tx-204", driver_external_id="drv-204", amount="13.00")
        self._create_event(external_id="tx-205", driver_external_id="drv-205", amount="21.50")

        result = import_unprocessed_events(connection=self._ensure_connection())

        self.assertEqual(result["imported_count"], 2)
        account_one = LedgerAccount.objects.get(user=driver_one, account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE)
        account_two = LedgerAccount.objects.get(user=driver_two, account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE)
        self.assertEqual(get_account_balance(account_one), Decimal("13.00"))
        self.assertEqual(get_account_balance(account_two), Decimal("21.50"))

    def test_unmapped_yandex_event_does_not_credit_any_driver(self):
        self._create_driver_membership("mapped_driver_six", "drv-206")
        self._create_event(external_id="tx-206", driver_external_id="drv-unmapped", amount="15.00")

        result = import_unprocessed_events(connection=self._ensure_connection())

        self.assertEqual(result["imported_count"], 0)
        self.assertEqual(
            LedgerEntry.objects.filter(
                account__account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
                reference_type="external_event",
            ).count(),
            0,
        )

    def test_cross_fleet_mapping_isolation_prevents_wrong_driver_credit(self):
        other_owner = User.objects.create_user(username="other_yandex_owner", password="pass1234")
        other_fleet = Fleet.objects.create(name="Yandex Import Other Fleet")
        other_driver = User.objects.create_user(username="other_yandex_driver", password="pass1234")
        FleetPhoneBinding.objects.create(
            fleet=other_fleet,
            user=other_owner,
            phone_number="598722223",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=other_driver,
            fleet=other_fleet,
            yandex_external_driver_id="drv-207",
            is_active=True,
        )
        self._create_driver_membership("mapped_driver_seven", "drv-208")
        self._create_event(external_id="tx-207", driver_external_id="drv-207", amount="18.00")

        result = import_unprocessed_events(connection=self._ensure_connection())

        self.assertEqual(result["imported_count"], 0)
        self.assertFalse(
            LedgerEntry.objects.filter(
                account__account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
                reference_type="external_event",
            ).exists()
        )

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
        self.fleet = Fleet.objects.create(name="Bank Sim Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598744444",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )
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
            HTTP_X_FLEET_NAME=self.fleet.name,
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
        self.assertEqual(self.wallet.balance, Decimal("89.50"))

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
        self.assertEqual(self.wallet.balance, Decimal("119.50"))

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

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currency"], "GEL")
        self.assertIn("treasury", response.data)
        self.assertIn("fleet_reserves", response.data)
        self.assertIn("driver_available", response.data)
        self.assertIn("payout_clearing", response.data)
        self.assertIn("platform_fees", response.data)
        self.assertIn("yandex", response.data)
        self.assertIn("deposits", response.data)
        self.assertIn("bank_simulator", response.data)
        self.assertIn("bog", response.data)
        self.assertEqual(response.data["bank_simulator"]["count"], 0)


class FleetScopedBankSimulatorPayoutApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="fleet_banksim_owner", password="pass1234")
        self.operator = User.objects.create_user(username="fleet_banksim_operator", password="pass1234")
        self.driver = User.objects.create_user(username="fleet_banksim_driver", password="pass1234")
        self.fleet = Fleet.objects.create(name="Fleet Scoped Bank Sim")
        for user, role, phone in [
            (self.owner, FleetPhoneBinding.Role.OWNER, "598988800"),
            (self.operator, FleetPhoneBinding.Role.OPERATOR, "598988801"),
            (self.driver, FleetPhoneBinding.Role.DRIVER, "598988802"),
        ]:
            FleetPhoneBinding.objects.create(
                fleet=self.fleet,
                user=user,
                phone_number=phone,
                role=role,
                is_active=True,
            )

        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="banksim-driver-1",
            is_active=True,
        )

        self.other_owner = User.objects.create_user(username="fleet_banksim_other_owner", password="pass1234")
        self.other_driver = User.objects.create_user(username="fleet_banksim_other_driver", password="pass1234")
        self.other_fleet = Fleet.objects.create(name="Fleet Scoped Bank Sim Other")
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_owner,
            phone_number="598988803",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_driver,
            phone_number="598988804",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=self.other_driver,
            fleet=self.other_fleet,
            yandex_external_driver_id="banksim-driver-2",
            is_active=True,
        )

        self.driver_bank = BankAccount.objects.create(
            user=self.driver,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000004001",
            beneficiary_name="Fleet Bank Sim Driver",
            beneficiary_inn="01010101010",
        )
        self.other_driver_bank = BankAccount.objects.create(
            user=self.other_driver,
            bank_name="TBC Bank",
            account_number="GE64TB00000000004002",
            beneficiary_name="Other Fleet Bank Sim Driver",
            beneficiary_inn="02020202020",
        )

        record_fleet_reserve_deposit(fleet=self.fleet, amount=Decimal("200.00"), created_by=self.owner)
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("120.00"),
            created_by=self.owner,
        )
        record_fleet_reserve_deposit(fleet=self.other_fleet, amount=Decimal("200.00"), created_by=self.other_owner)
        record_driver_earning_allocation(
            user=self.other_driver,
            fleet=self.other_fleet,
            amount=Decimal("120.00"),
            created_by=self.other_owner,
        )

    def _create_withdrawal(self, *, driver, bank_account, fleet_name, amount, key_suffix):
        self.client.force_authenticate(driver)
        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": bank_account.id, "amount": amount, "note": "fleet bank sim payout"},
            format="json",
            HTTP_X_FLEET_NAME=fleet_name,
            HTTP_IDEMPOTENCY_KEY=f"fleet-banksim-{key_suffix}",
            HTTP_X_REQUEST_ID=f"req-fleet-banksim-{key_suffix}",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return WithdrawalRequest.objects.get(id=response.data["id"])

    def test_operator_can_submit_and_settle_fleet_bank_sim_payout(self):
        withdrawal = self._create_withdrawal(
            driver=self.driver,
            bank_account=self.driver_bank,
            fleet_name=self.fleet.name,
            amount="25.00",
            key_suffix="own",
        )
        self.client.force_authenticate(self.operator)

        connect_response = self.client.post(
            reverse("bank-sim-connect"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(connect_response.status_code, status.HTTP_201_CREATED)

        submit_response = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertIn(submit_response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        payout_id = submit_response.data["id"]
        self.assertEqual(submit_response.data["withdrawal_id"], withdrawal.id)

        settle_response = self.client.post(
            reverse("bank-sim-status-update", kwargs={"payout_id": payout_id}),
            data={"status": "settled"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(settle_response.status_code, status.HTTP_200_OK)
        self.assertEqual(settle_response.data["status"], "settled")

        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.COMPLETED)

    def test_operator_can_list_only_active_fleet_bank_sim_payouts(self):
        own_withdrawal = self._create_withdrawal(
            driver=self.driver,
            bank_account=self.driver_bank,
            fleet_name=self.fleet.name,
            amount="20.00",
            key_suffix="list-own",
        )
        other_withdrawal = self._create_withdrawal(
            driver=self.other_driver,
            bank_account=self.other_driver_bank,
            fleet_name=self.other_fleet.name,
            amount="22.00",
            key_suffix="list-other",
        )

        self.client.force_authenticate(self.operator)
        self.client.post(reverse("bank-sim-connect"), data={}, format="json", HTTP_X_FLEET_NAME=self.fleet.name)
        own_submit = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": own_withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.client.force_authenticate(self.other_owner)
        self.client.post(reverse("bank-sim-connect"), data={}, format="json", HTTP_X_FLEET_NAME=self.other_fleet.name)
        self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": other_withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.other_fleet.name,
        )

        self.client.force_authenticate(self.operator)
        response = self.client.get(reverse("bank-sim-payouts"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [own_submit.data["id"]])

    def test_operator_cannot_act_on_another_fleets_bank_sim_items(self):
        own_withdrawal = self._create_withdrawal(
            driver=self.driver,
            bank_account=self.driver_bank,
            fleet_name=self.fleet.name,
            amount="18.00",
            key_suffix="cross-own",
        )
        other_withdrawal = self._create_withdrawal(
            driver=self.other_driver,
            bank_account=self.other_driver_bank,
            fleet_name=self.other_fleet.name,
            amount="19.00",
            key_suffix="cross-other",
        )

        self.client.force_authenticate(self.other_owner)
        self.client.post(reverse("bank-sim-connect"), data={}, format="json", HTTP_X_FLEET_NAME=self.other_fleet.name)
        other_submit = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": other_withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.other_fleet.name,
        )
        self.assertIn(other_submit.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])

        self.client.force_authenticate(self.operator)
        self.client.post(reverse("bank-sim-connect"), data={}, format="json", HTTP_X_FLEET_NAME=self.fleet.name)

        submit_response = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": other_withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(submit_response.status_code, status.HTTP_404_NOT_FOUND)

        status_response = self.client.post(
            reverse("bank-sim-status-update", kwargs={"payout_id": other_submit.data["id"]}),
            data={"status": "settled"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(status_response.status_code, status.HTTP_404_NOT_FOUND)

        own_submit = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": own_withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertIn(own_submit.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])

    def test_driver_cannot_access_operator_bank_sim_tooling(self):
        withdrawal = self._create_withdrawal(
            driver=self.driver,
            bank_account=self.driver_bank,
            fleet_name=self.fleet.name,
            amount="16.00",
            key_suffix="driver-access",
        )
        payout = BankSimulatorPayout.objects.create(
            connection=ProviderConnection.objects.create(
                user=self.owner,
                provider=ProviderConnection.Provider.BANK_SIMULATOR,
                external_account_id="fleet-banksim-owner-conn",
                status="active",
                config={"mode": "simulator"},
            ),
            withdrawal=withdrawal,
            provider_payout_id="fleet-banksim-existing",
            status=BankSimulatorPayout.Status.ACCEPTED,
            metadata={"source": "bank_simulator"},
        )

        self.client.force_authenticate(self.driver)

        connect_response = self.client.post(
            reverse("bank-sim-connect"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        list_response = self.client.get(reverse("bank-sim-payouts"), HTTP_X_FLEET_NAME=self.fleet.name)
        submit_response = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        status_response = self.client.post(
            reverse("bank-sim-status-update", kwargs={"payout_id": payout.id}),
            data={"status": "settled"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(connect_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(submit_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(status_response.status_code, status.HTTP_403_FORBIDDEN)


class DriverWithdrawalPayoutFlowTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="driver_payout_owner", password="pass1234")
        self.driver = User.objects.create_user(username="driver_payout_driver", password="pass1234")
        self.fleet = Fleet.objects.create(name="Driver Payout Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598977771",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver,
            phone_number="598977772",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="drv-payout-1",
            is_active=True,
        )
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("100.00"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("30.00"),
            created_by=self.owner,
        )
        self.client.force_authenticate(self.driver)
        self.bank_account = BankAccount.objects.create(
            user=self.driver,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000004",
            beneficiary_name="Driver Payout Flow",
            beneficiary_inn="01001010103",
        )

    def _create_withdrawal(self, amount="20.00"):
        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.bank_account.id, "amount": amount, "note": "driver payout"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY=f"driver-payout-{amount}",
            HTTP_X_REQUEST_ID=f"req-driver-payout-{amount}",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return WithdrawalRequest.objects.get(id=response.data["id"])

    def test_failed_payout_reversal_restores_driver_and_fleet_balances(self):
        withdrawal = self._create_withdrawal(amount="20.00")
        self.client.force_authenticate(self.owner)
        submit_response = self.client.post(
            reverse("bank-sim-submit"),
            data={"withdrawal_id": withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertIn(submit_response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        payout_id = submit_response.data["id"]

        fail_response = self.client.post(
            reverse("bank-sim-status-update", kwargs={"payout_id": payout_id}),
            data={"status": "failed", "failure_reason": "invalid account"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(fail_response.status_code, status.HTTP_200_OK)

        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.FAILED)

        driver_account = LedgerAccount.objects.get(
            user=self.driver,
            account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
        )
        reserve_account = LedgerAccount.objects.get(
            fleet=self.fleet,
            account_type=LedgerAccount.AccountType.FLEET_RESERVE,
        )
        payout_clearing = get_or_create_payout_clearing_account()
        fee_account = get_or_create_platform_fee_account()

        self.assertEqual(get_account_balance(driver_account), Decimal("30.00"))
        self.assertEqual(get_account_balance(reserve_account), Decimal("100.00"))
        self.assertEqual(get_account_balance(payout_clearing), Decimal("0.00"))
        self.assertEqual(get_account_balance(fee_account), Decimal("0.00"))


class ReconciliationReportTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="reconciliation_owner", password="pass1234")
        self.driver = User.objects.create_user(username="reconciliation_driver", password="pass1234")
        self.fleet = Fleet.objects.create(name="Reconciliation Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598988881",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver,
            phone_number="598988882",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="reconcile-drv-1",
            is_active=True,
        )
        self.other_owner = User.objects.create_user(username="reconciliation_other_owner", password="pass1234")
        self.other_driver = User.objects.create_user(username="reconciliation_other_driver", password="pass1234")
        self.other_fleet = Fleet.objects.create(name="Reconciliation Other Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_owner,
            phone_number="598988883",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_driver,
            phone_number="598988884",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=self.other_driver,
            fleet=self.other_fleet,
            yandex_external_driver_id="reconcile-drv-2",
            is_active=True,
        )
        self.client.force_authenticate(self.owner)
        self.yandex_connection = None

    def _ensure_owner_yandex_connection(self):
        if self.yandex_connection is None:
            self.yandex_connection = ProviderConnection.objects.create(
                user=self.owner,
                provider=ProviderConnection.Provider.YANDEX,
                external_account_id="reconciliation-yandex-owner",
                status="active",
                config={"mode": "live"},
            )
        return self.yandex_connection

    def _create_yandex_event(self, *, external_id: str, driver_external_id: str, amount: str):
        event = ExternalEvent.objects.create(
            connection=self._ensure_owner_yandex_connection(),
            external_id=external_id,
            event_type="earning",
            payload={
                "external_id": external_id,
                "driver_id": driver_external_id,
                "net_amount": amount,
                "currency": "GEL",
            },
            processed=False,
        )
        YandexTransactionRecord.objects.create(
            connection=self._ensure_owner_yandex_connection(),
            external_event=event,
            external_transaction_id=external_id,
            driver_external_id=driver_external_id,
            amount=Decimal(amount),
            currency="GEL",
            category="earning",
            direction="credit",
        )
        return event

    def test_reconciliation_totals_match_new_ledger_model(self):
        owner_wallet = Wallet.objects.get_or_create(user=self.owner)[0]
        driver_wallet = Wallet.objects.get_or_create(user=self.driver)[0]

        matched_transfer = IncomingBankTransfer.objects.create(
            provider_transaction_id="reconcile-transfer-1",
            provider="bog",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("160.00"),
            reference_text="matched deposit",
            match_status=IncomingBankTransfer.MatchStatus.MATCHED,
            fleet=self.fleet,
        )
        Deposit.objects.create(
            user=self.owner,
            wallet=owner_wallet,
            fleet=self.fleet,
            incoming_transfer=matched_transfer,
            amount=Decimal("160.00"),
            currency="GEL",
            status=Deposit.Status.COMPLETED,
            reference_code="EXP-FLT-000160",
            provider="bog",
            provider_transaction_id="reconcile-deposit-1",
        )
        IncomingBankTransfer.objects.create(
            provider_transaction_id="reconcile-transfer-unmatched",
            provider="bog",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("45.00"),
            reference_text=f"needs review {self.fleet.id} EXP-FLT-{self.fleet.id:06d}",
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
        )

        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("160.00"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("30.00"),
            created_by=self.owner,
        )

        bank_account = BankAccount.objects.create(
            user=self.driver,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000160",
            beneficiary_name="Reconciliation Driver",
            beneficiary_inn="01001010104",
        )
        withdrawal = WithdrawalRequest.objects.create(
            user=self.driver,
            wallet=driver_wallet,
            fleet=self.fleet,
            bank_account=bank_account,
            amount=Decimal("25.00"),
            fee_amount=Decimal("0.50"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )
        from ledger.services import record_driver_withdrawal_hold

        record_driver_withdrawal_hold(
            withdrawal=withdrawal,
            fleet=self.fleet,
            user=self.driver,
            amount=Decimal("25.00"),
            fee_amount=Decimal("0.50"),
            created_by=self.owner,
            currency="GEL",
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["treasury"]["balance"], "160.00")
        self.assertEqual(response.data["treasury"]["expected_total"], "160.00")
        self.assertEqual(response.data["treasury"]["delta"], "0.00")
        self.assertEqual(response.data["treasury"]["status"], "OK")
        self.assertEqual(response.data["fleet_reserves"]["total_balance"], "135.00")
        self.assertEqual(response.data["fleet_reserves"]["account_count"], 1)
        self.assertEqual(response.data["driver_available"]["total_balance"], "4.50")
        self.assertEqual(response.data["driver_available"]["account_count"], 1)
        self.assertEqual(response.data["payout_clearing"]["balance"], "25.00")
        self.assertEqual(response.data["payout_clearing"]["pending_withdrawals_count"], 1)
        self.assertEqual(response.data["payout_clearing"]["pending_withdrawals_total"], "25.00")
        self.assertEqual(response.data["platform_fees"]["balance"], "0.50")
        self.assertEqual(response.data["deposits"]["matched_count"], 1)
        self.assertEqual(response.data["deposits"]["matched_total"], "160.00")
        self.assertEqual(response.data["deposits"]["unmatched_count"], 1)
        self.assertEqual(response.data["overall_status"], "OK")

    def test_reconciliation_ignores_stale_legacy_wallet_balances(self):
        owner_wallet = Wallet.objects.get_or_create(user=self.owner)[0]
        driver_wallet = Wallet.objects.get_or_create(user=self.driver)[0]
        owner_wallet.balance = Decimal("9999.99")
        owner_wallet.save(update_fields=["balance", "updated_at"])
        driver_wallet.balance = Decimal("777.77")
        driver_wallet.save(update_fields=["balance", "updated_at"])

        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("40.00"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("12.50"),
            created_by=self.owner,
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("wallet", response.data)
        self.assertEqual(response.data["treasury"]["balance"], "40.00")
        self.assertEqual(response.data["fleet_reserves"]["total_balance"], "40.00")
        self.assertEqual(response.data["driver_available"]["total_balance"], "12.50")
        self.assertEqual(response.data["overall_status"], "OK")

    def test_reconciliation_monetary_fields_are_two_decimal_strings(self):
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("160"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("10"),
            created_by=self.owner,
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["treasury"]["balance"], "160.00")
        self.assertEqual(response.data["treasury"]["expected_total"], "160.00")
        self.assertEqual(response.data["treasury"]["delta"], "0.00")
        self.assertEqual(response.data["fleet_reserves"]["total_balance"], "160.00")
        self.assertEqual(response.data["driver_available"]["total_balance"], "10.00")
        self.assertEqual(response.data["payout_clearing"]["balance"], "0.00")
        self.assertEqual(response.data["payout_clearing"]["pending_withdrawals_total"], "0.00")
        self.assertEqual(response.data["platform_fees"]["balance"], "0.00")
        self.assertEqual(response.data["deposits"]["matched_total"], "0.00")
        self.assertEqual(response.data["bank_simulator"]["totals_by_status"]["accepted"], "0.00")
        self.assertEqual(response.data["bog"]["totals_by_status"]["accepted"], "0.00")
        self.assertEqual(response.data["yandex"]["imported_total"], "0.00")
        self.assertEqual(response.data["yandex"]["ledger_total"], "0.00")
        self.assertEqual(response.data["yandex"]["delta"], "0.00")

    def test_treasury_delta_is_zero_when_actual_treasury_matches_internal_obligations(self):
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("115.00"),
            created_by=self.owner,
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["treasury"]["balance"], "115.00")
        self.assertEqual(response.data["treasury"]["expected_total"], "115.00")
        self.assertEqual(response.data["treasury"]["delta"], "0.00")
        self.assertEqual(response.data["treasury"]["status"], "OK")

    def test_treasury_delta_is_non_zero_when_actual_treasury_drifts_from_obligations(self):
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("115.00"),
            created_by=self.owner,
        )
        treasury_account = get_or_create_treasury_account()
        create_ledger_entry(
            account=treasury_account,
            amount=Decimal("-15.00"),
            entry_type="treasury_manual_adjustment",
            created_by=self.owner,
            reference_type="treasury_adjustment",
            reference_id="fleet-a-shortfall",
            metadata={"fleet_id": self.fleet.id, "reason": "bank drift"},
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["treasury"]["balance"], "100.00")
        self.assertEqual(response.data["treasury"]["expected_total"], "115.00")
        self.assertEqual(response.data["treasury"]["delta"], "-15.00")
        self.assertEqual(response.data["treasury"]["status"], "MISMATCH")
        self.assertEqual(response.data["overall_status"], "MISMATCH")

    def test_treasury_mismatch_is_not_masked_by_reusing_expected_total_as_balance(self):
        from ledger.services import record_driver_withdrawal_hold

        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("120.00"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("40.00"),
            created_by=self.owner,
        )
        bank_account = BankAccount.objects.create(
            user=self.driver,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000165",
            beneficiary_name="Reconciliation Drift Driver",
            beneficiary_inn="01001010105",
        )
        withdrawal = WithdrawalRequest.objects.create(
            user=self.driver,
            wallet=Wallet.objects.get_or_create(user=self.driver)[0],
            fleet=self.fleet,
            bank_account=bank_account,
            amount=Decimal("30.00"),
            fee_amount=Decimal("0.50"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )
        record_driver_withdrawal_hold(
            withdrawal=withdrawal,
            fleet=self.fleet,
            user=self.driver,
            amount=Decimal("30.00"),
            fee_amount=Decimal("0.50"),
            created_by=self.owner,
            currency="GEL",
        )
        treasury_account = get_or_create_treasury_account()
        create_ledger_entry(
            account=treasury_account,
            amount=Decimal("-7.00"),
            entry_type="treasury_manual_adjustment",
            created_by=self.owner,
            reference_type="treasury_adjustment",
            reference_id="fleet-a-processing-drift",
            metadata={"fleet_id": self.fleet.id, "reason": "bank shortfall while payout pending"},
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["treasury"]["balance"], "113.00")
        self.assertEqual(response.data["treasury"]["expected_total"], "120.00")
        self.assertNotEqual(response.data["treasury"]["balance"], response.data["treasury"]["expected_total"])
        self.assertEqual(response.data["treasury"]["delta"], "-7.00")
        self.assertEqual(response.data["treasury"]["status"], "MISMATCH")
        self.assertEqual(response.data["overall_status"], "MISMATCH")

    def test_other_fleet_treasury_activity_does_not_affect_active_fleet_reconciliation(self):
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("90.00"),
            created_by=self.owner,
        )
        record_fleet_reserve_deposit(
            fleet=self.other_fleet,
            amount=Decimal("210.00"),
            created_by=self.other_owner,
        )
        treasury_account = get_or_create_treasury_account()
        create_ledger_entry(
            account=treasury_account,
            amount=Decimal("-25.00"),
            entry_type="treasury_manual_adjustment",
            created_by=self.other_owner,
            reference_type="treasury_adjustment",
            reference_id="fleet-b-shortfall",
            metadata={"fleet_id": self.other_fleet.id, "reason": "other fleet drift"},
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["treasury"]["balance"], "90.00")
        self.assertEqual(response.data["treasury"]["expected_total"], "90.00")
        self.assertEqual(response.data["treasury"]["delta"], "0.00")
        self.assertEqual(response.data["treasury"]["status"], "OK")

    def test_owner_does_not_see_other_fleet_totals(self):
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("90.00"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("14.00"),
            created_by=self.owner,
        )
        record_fleet_reserve_deposit(
            fleet=self.other_fleet,
            amount=Decimal("210.00"),
            created_by=self.other_owner,
        )
        record_driver_earning_allocation(
            user=self.other_driver,
            fleet=self.other_fleet,
            amount=Decimal("33.00"),
            created_by=self.other_owner,
        )
        Deposit.objects.create(
            user=self.owner,
            wallet=Wallet.objects.get_or_create(user=self.owner)[0],
            fleet=self.fleet,
            amount=Decimal("90.00"),
            currency="GEL",
            status=Deposit.Status.COMPLETED,
            reference_code="EXP-FLT-000090",
            provider="bog",
            provider_transaction_id="reconcile-owner-fleet-deposit",
        )
        Deposit.objects.create(
            user=self.other_owner,
            wallet=Wallet.objects.get_or_create(user=self.other_owner)[0],
            fleet=self.other_fleet,
            amount=Decimal("210.00"),
            currency="GEL",
            status=Deposit.Status.COMPLETED,
            reference_code="EXP-FLT-000210",
            provider="bog",
            provider_transaction_id="reconcile-other-fleet-deposit",
        )
        own_withdrawal = WithdrawalRequest.objects.create(
            user=self.driver,
            wallet=Wallet.objects.get_or_create(user=self.driver)[0],
            fleet=self.fleet,
            bank_account=BankAccount.objects.create(
                user=self.driver,
                bank_name="Bank of Georgia",
                account_number="GE64BG00000000000161",
                beneficiary_name="Reconciliation Driver",
                beneficiary_inn="01001010104",
            ),
            amount=Decimal("11.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PROCESSING,
        )
        other_withdrawal = WithdrawalRequest.objects.create(
            user=self.other_driver,
            wallet=Wallet.objects.get_or_create(user=self.other_driver)[0],
            fleet=self.other_fleet,
            bank_account=BankAccount.objects.create(
                user=self.other_driver,
                bank_name="TBC",
                account_number="GE64TB00000000000162",
                beneficiary_name="Other Reconciliation Driver",
                beneficiary_inn="02002020205",
            ),
            amount=Decimal("44.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PROCESSING,
        )
        own_connection = ProviderConnection.objects.create(
            user=self.owner,
            provider=ProviderConnection.Provider.BANK_SIMULATOR,
            external_account_id="reconcile-own-bank-sim",
            status="active",
            config={"mode": "simulator"},
        )
        other_connection = ProviderConnection.objects.create(
            user=self.other_owner,
            provider=ProviderConnection.Provider.BANK_SIMULATOR,
            external_account_id="reconcile-other-bank-sim",
            status="active",
            config={"mode": "simulator"},
        )
        BankSimulatorPayout.objects.create(
            connection=own_connection,
            withdrawal=own_withdrawal,
            provider_payout_id="reconcile-own-payout",
            status=BankSimulatorPayout.Status.ACCEPTED,
        )
        BankSimulatorPayout.objects.create(
            connection=other_connection,
            withdrawal=other_withdrawal,
            provider_payout_id="reconcile-other-payout",
            status=BankSimulatorPayout.Status.ACCEPTED,
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["treasury"]["balance"], "90.00")
        self.assertEqual(response.data["fleet_reserves"]["total_balance"], "90.00")
        self.assertEqual(response.data["driver_available"]["total_balance"], "14.00")
        self.assertEqual(response.data["deposits"]["matched_count"], 1)
        self.assertEqual(response.data["deposits"]["matched_total"], "90.00")
        self.assertEqual(response.data["bank_simulator"]["count"], 1)
        self.assertEqual(response.data["bank_simulator"]["totals_by_status"]["accepted"], "11.00")

    def test_unmatched_transfer_count_is_fleet_scoped(self):
        IncomingBankTransfer.objects.create(
            provider_transaction_id="reconcile-own-unmatched",
            provider="bog",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("19.00"),
            reference_text=f"needs review EXP-FLT-{self.fleet.id:06d}",
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
        )
        IncomingBankTransfer.objects.create(
            provider_transaction_id="reconcile-other-unmatched",
            provider="bog",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("29.00"),
            reference_text=f"needs review EXP-FLT-{self.other_fleet.id:06d}",
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deposits"]["unmatched_count"], 1)

    def test_bog_payout_totals_are_fleet_scoped(self):
        own_withdrawal = WithdrawalRequest.objects.create(
            user=self.driver,
            wallet=Wallet.objects.get_or_create(user=self.driver)[0],
            fleet=self.fleet,
            bank_account=BankAccount.objects.create(
                user=self.driver,
                bank_name="Bank of Georgia",
                account_number="GE64BG00000000000171",
                beneficiary_name="Fleet A Driver",
                beneficiary_inn="01001010104",
            ),
            amount=Decimal("22.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PROCESSING,
        )
        other_withdrawal = WithdrawalRequest.objects.create(
            user=self.other_driver,
            wallet=Wallet.objects.get_or_create(user=self.other_driver)[0],
            fleet=self.other_fleet,
            bank_account=BankAccount.objects.create(
                user=self.other_driver,
                bank_name="TBC",
                account_number="GE64TB00000000000172",
                beneficiary_name="Fleet B Driver",
                beneficiary_inn="02002020205",
            ),
            amount=Decimal("55.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PROCESSING,
        )
        own_bog_connection = ProviderConnection.objects.create(
            user=self.owner,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="reconcile-own-bog",
            status="active",
            config={"mode": "live"},
        )
        other_bog_connection = ProviderConnection.objects.create(
            user=self.other_owner,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="reconcile-other-bog",
            status="active",
            config={"mode": "live"},
        )
        BogPayout.objects.create(
            connection=own_bog_connection,
            withdrawal=own_withdrawal,
            provider_unique_id="reconcile-own-bog-payout",
            status=BogPayout.Status.ACCEPTED,
            provider_status="ACCEPTED",
        )
        BogPayout.objects.create(
            connection=other_bog_connection,
            withdrawal=other_withdrawal,
            provider_unique_id="reconcile-other-bog-payout",
            status=BogPayout.Status.ACCEPTED,
            provider_status="ACCEPTED",
        )

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["bog"]["count"], 1)
        self.assertEqual(response.data["bog"]["totals_by_status"]["accepted"], "22.00")

    def test_yandex_totals_are_fleet_scoped(self):
        self._create_yandex_event(
            external_id="reconcile-yandex-own",
            driver_external_id="reconcile-drv-1",
            amount="17.00",
        )
        self._create_yandex_event(
            external_id="reconcile-yandex-other",
            driver_external_id="reconcile-drv-2",
            amount="41.00",
        )
        import_unprocessed_events(connection=self._ensure_owner_yandex_connection())

        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["yandex"]["imported_events"], 1)
        self.assertEqual(response.data["yandex"]["imported_total"], "17.00")
        self.assertEqual(response.data["yandex"]["ledger_total"], "17.00")
        self.assertEqual(response.data["yandex"]["delta"], "0.00")

    def test_driver_cannot_access_reconciliation_summary(self):
        self.client.force_authenticate(self.driver)
        response = self.client.get(reverse("reconciliation-summary"), HTTP_X_FLEET_NAME=self.fleet.name)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class BogTokenApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bog_user", password="pass1234")
        self.fleet = Fleet.objects.create(name="BoG Token Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598755555",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )
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

        response = self.client.post(
            reverse("bog-test-token"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
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

        response = self.client.post(
            reverse("bog-test-token"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
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

    @override_settings(BOG_AUTH_FLOW="implicit", BOG_IMPLICIT_ACCESS_TOKEN="implicit-token-value")
    @patch("integrations.services.test_live_bog_token_connection")
    def test_bog_implicit_access_token_is_used_from_environment(self, mocked_test):
        connection = ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="bog-implicit-user",
            status="active",
            config={"mode": "live"},
        )
        cache.clear()

        first = get_valid_bog_access_token(connection=connection)
        second = get_valid_bog_access_token(connection=connection, force_refresh=True)

        self.assertEqual(first, "implicit-token-value")
        self.assertEqual(second, "implicit-token-value")
        mocked_test.assert_not_called()


class IntegrationBackgroundJobCommandTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="jobs_owner", password="pass1234")
        self.other_owner = User.objects.create_user(username="jobs_other_owner", password="pass1234")
        self.fleet = Fleet.objects.create(name="Jobs Fleet A")
        self.other_fleet = Fleet.objects.create(name="Jobs Fleet B")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598744441",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_owner,
            phone_number="598744442",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        self.yandex_connection = ProviderConnection.objects.create(
            user=self.owner,
            provider=ProviderConnection.Provider.YANDEX,
            external_account_id="jobs-yandex-a",
            status="active",
            config={},
        )
        self.bog_connection = ProviderConnection.objects.create(
            user=self.owner,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="jobs-bog-a",
            status="active",
            config={},
        )
        self.other_yandex_connection = ProviderConnection.objects.create(
            user=self.other_owner,
            provider=ProviderConnection.Provider.YANDEX,
            external_account_id="jobs-yandex-b",
            status="active",
            config={},
        )
        self.other_bog_connection = ProviderConnection.objects.create(
            user=self.other_owner,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="jobs-bog-b",
            status="active",
            config={},
        )
        self.inactive_connection = ProviderConnection.objects.create(
            user=self.owner,
            provider=ProviderConnection.Provider.YANDEX,
            external_account_id="jobs-yandex-inactive",
            status="error",
            config={},
        )

    @patch("integrations.jobs.sync_open_bog_payouts")
    @patch("integrations.jobs.sync_bog_deposits")
    @patch("integrations.jobs.live_sync_yandex_data")
    def test_run_integration_sync_jobs_runs_all_active_jobs(self, mocked_yandex, mocked_deposits, mocked_payouts):
        mocked_yandex.return_value = {
            "ok": True,
            "detail": "ok",
            "drivers": {"fetched": 2, "upserted_profiles": 2},
            "transactions": {"fetched": 3, "imported_count": 1, "imported_total": "12.50"},
        }
        mocked_deposits.return_value = {
            "ok": True,
            "detail": "ok",
            "checked_count": 4,
            "matched_count": 2,
            "credited_count": 1,
            "unmatched_count": 1,
            "credited_total": "40.00",
        }
        mocked_payouts.return_value = {
            "checked_count": 3,
            "updated_count": 2,
            "error_count": 0,
            "errors": [],
        }

        stdout = StringIO()
        call_command("run_integration_sync_jobs", stdout=stdout)

        self.assertEqual(mocked_yandex.call_count, 2)
        self.assertEqual(mocked_deposits.call_count, 2)
        self.assertEqual(mocked_payouts.call_count, 2)
        self.assertIn("Yandex sync: connections=2 ok=2 errors=0 imported=2 total=25.00", stdout.getvalue())
        self.assertIn("BoG deposit sync: connections=2 ok=2 errors=0 checked=8 matched=4 credited=2 total=80.00", stdout.getvalue())
        self.assertIn("BoG payout sync: connections=2 ok=2 errors=0 checked=6 updated=4 payout_errors=0", stdout.getvalue())

        self.yandex_connection.refresh_from_db()
        self.bog_connection.refresh_from_db()
        self.assertIn("last_live_sync", self.yandex_connection.config)
        self.assertIn("last_deposit_sync", self.bog_connection.config)
        self.assertIn("last_payout_sync", self.bog_connection.config)

    @patch("integrations.jobs.sync_open_bog_payouts")
    @patch("integrations.jobs.sync_bog_deposits")
    @patch("integrations.jobs.live_sync_yandex_data")
    def test_run_integration_sync_jobs_can_scope_to_one_fleet(self, mocked_yandex, mocked_deposits, mocked_payouts):
        mocked_yandex.return_value = {
            "ok": True,
            "detail": "ok",
            "drivers": {"fetched": 1, "upserted_profiles": 1},
            "transactions": {"fetched": 1, "imported_count": 1, "imported_total": "10.00"},
        }
        mocked_deposits.return_value = {
            "ok": True,
            "detail": "ok",
            "checked_count": 2,
            "matched_count": 1,
            "credited_count": 1,
            "unmatched_count": 0,
            "credited_total": "10.00",
        }
        mocked_payouts.return_value = {
            "checked_count": 1,
            "updated_count": 1,
            "error_count": 0,
            "errors": [],
        }

        call_command("run_integration_sync_jobs", "--fleet-name", self.fleet.name)

        self.assertEqual(mocked_yandex.call_count, 1)
        self.assertEqual(mocked_yandex.call_args.kwargs["connection"].id, self.yandex_connection.id)
        self.assertEqual(mocked_deposits.call_count, 1)
        self.assertEqual(mocked_deposits.call_args.kwargs["connection"].id, self.bog_connection.id)
        self.assertEqual(mocked_payouts.call_count, 1)
        self.assertEqual(mocked_payouts.call_args.kwargs["connection"].id, self.bog_connection.id)

    @patch("integrations.jobs.sync_open_bog_payouts")
    @patch("integrations.jobs.sync_bog_deposits")
    @patch("integrations.jobs.live_sync_yandex_data")
    def test_run_integration_sync_jobs_can_scope_to_single_user(self, mocked_yandex, mocked_deposits, mocked_payouts):
        mocked_yandex.return_value = {
            "ok": True,
            "detail": "ok",
            "drivers": {"fetched": 1, "upserted_profiles": 1},
            "transactions": {"fetched": 1, "imported_count": 0, "imported_total": "0.00"},
        }
        mocked_deposits.return_value = {
            "ok": True,
            "detail": "ok",
            "checked_count": 0,
            "matched_count": 0,
            "credited_count": 0,
            "unmatched_count": 0,
            "credited_total": "0.00",
        }
        mocked_payouts.return_value = {
            "checked_count": 0,
            "updated_count": 0,
            "error_count": 0,
            "errors": [],
        }

        call_command("run_integration_sync_jobs", "--user-id", str(self.owner.id))

        self.assertEqual(mocked_yandex.call_count, 1)
        self.assertEqual(mocked_yandex.call_args.kwargs["connection"].user_id, self.owner.id)
        self.assertEqual(mocked_deposits.call_count, 1)
        self.assertEqual(mocked_deposits.call_args.kwargs["connection"].user_id, self.owner.id)
        self.assertEqual(mocked_payouts.call_count, 1)
        self.assertEqual(mocked_payouts.call_args.kwargs["connection"].user_id, self.owner.id)

    @patch("integrations.management.commands.run_money_smoke_sync.run_bog_payout_status_sync_jobs")
    @patch("integrations.management.commands.run_money_smoke_sync.run_yandex_sync_jobs")
    @patch("integrations.management.commands.run_money_smoke_sync.run_bog_deposit_sync_jobs")
    def test_run_money_smoke_sync_runs_fleet_sequence(self, mocked_deposits, mocked_yandex, mocked_payouts):
        mocked_deposits.return_value = {
            "checked_connections": 1,
            "checked_count": 2,
            "matched_count": 1,
            "credited_count": 1,
            "unmatched_count": 1,
            "credited_total": "15.00",
        }
        mocked_yandex.return_value = {
            "checked_connections": 1,
            "ok_connections": 1,
            "error_count": 0,
            "imported_count": 1,
            "imported_total": "8.50",
        }
        mocked_payouts.return_value = {
            "checked_connections": 1,
            "checked_count": 1,
            "updated_count": 1,
            "payout_error_count": 0,
        }

        stdout = StringIO()
        call_command("run_money_smoke_sync", "--fleet-name", self.fleet.name, stdout=stdout)

        self.assertEqual(mocked_deposits.call_args.kwargs["fleet_name"], self.fleet.name)
        self.assertEqual(mocked_yandex.call_args.kwargs["fleet_name"], self.fleet.name)
        self.assertEqual(mocked_payouts.call_args.kwargs["fleet_name"], self.fleet.name)
        self.assertIn("1. BoG deposits:", stdout.getvalue())
        self.assertIn("2. Yandex earnings:", stdout.getvalue())
        self.assertIn("3. BoG payouts:", stdout.getvalue())

    def test_run_money_smoke_sync_requires_one_enabled_step(self):
        with self.assertRaisesMessage(Exception, "At least one sync step must be enabled."):
            call_command(
                "run_money_smoke_sync",
                "--fleet-name",
                self.fleet.name,
                "--skip-deposits",
                "--skip-yandex",
                "--skip-payouts",
            )


class BogCardPaymentsApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bog_card_user", password="pass1234")
        self.client.force_authenticate(self.user)
        self.fleet = Fleet.objects.create(name="Card Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598900111",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )
        self.connection = ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BOG_PAYMENTS,
            external_account_id="bog-payments-card-user",
            status="active",
            config={"mode": "live"},
        )

    @patch("integrations.views.test_live_bog_payments_token_connection")
    def test_test_payments_token_endpoint_updates_connection_status(self, mocked_test):
        mocked_test.return_value = {
            "ok": True,
            "configured": True,
            "provider": "bog_payments",
            "http_status": 200,
            "endpoint": "https://oauth2.bog.ge/auth/realms/bog/protocol/openid-connect/token",
            "detail": "BoG Payments token request succeeded.",
            "response": {
                "token_type": "Bearer",
                "expires_in": 1800,
                "access_token_received": True,
                "access_token": "hidden-token",
            },
        }

        response = self.client.post(reverse("bog-payments-test-token"), data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["test"]["ok"])
        self.assertTrue(response.data["test"]["response"]["access_token_received"])
        self.assertNotIn("access_token", response.data["test"]["response"])

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, "active")
        self.assertIn("last_token_test", self.connection.config)

    @patch("integrations.views.create_bog_card_order")
    def test_create_card_order_endpoint_returns_redirect_url(self, mocked_create):
        order = BogCardOrder.objects.create(
            connection=self.connection,
            user=self.user,
            provider_order_id="order-1",
            external_order_id="external-1",
            amount=Decimal("25.00"),
            currency="GEL",
            status=BogCardOrder.Status.CREATED,
            redirect_url="https://pay.example/redirect",
            details_url="https://pay.example/details",
        )
        mocked_create.return_value = order

        response = self.client.post(
            reverse("bog-payments-create-order"),
            data={"amount": "25.00", "currency": "GEL", "save_card": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["provider_order_id"], "order-1")
        self.assertEqual(response.data["redirect_url"], "https://pay.example/redirect")

    @override_settings(
        BOG_PAYMENTS_CALLBACK_URL="https://replace-with-your-public-domain/api/integrations/bog-payments/callback/",
        BOG_PAYMENTS_SUCCESS_URL="",
        BOG_PAYMENTS_FAIL_URL="",
    )
    @patch("integrations.views.create_bog_card_order")
    def test_create_card_order_endpoint_uses_public_origin_when_env_has_placeholder(self, mocked_create):
        order = BogCardOrder.objects.create(
            connection=self.connection,
            user=self.user,
            provider_order_id="order-2",
            external_order_id="external-2",
            amount=Decimal("15.00"),
            currency="GEL",
            status=BogCardOrder.Status.CREATED,
            redirect_url="https://pay.example/redirect-2",
            details_url="https://pay.example/details-2",
        )
        mocked_create.return_value = order

        response = self.client.post(
            reverse("bog-payments-create-order"),
            data={"amount": "15.00", "currency": "GEL", "save_card": False},
            format="json",
            HTTP_ORIGIN="https://ghz-hundreds-efforts-urban.trycloudflare.com",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            mocked_create.call_args.kwargs["callback_url"],
            "https://ghz-hundreds-efforts-urban.trycloudflare.com/api/integrations/bog-payments/callback/",
        )
        self.assertEqual(
            mocked_create.call_args.kwargs["success_url"],
            "https://ghz-hundreds-efforts-urban.trycloudflare.com/card-topup",
        )
        self.assertEqual(
            mocked_create.call_args.kwargs["fail_url"],
            "https://ghz-hundreds-efforts-urban.trycloudflare.com/card-topup",
        )

    @patch("integrations.views.handle_bog_payments_callback")
    def test_callback_endpoint_accepts_unsigned_payload(self, mocked_handle):
        order = BogCardOrder.objects.create(
            connection=self.connection,
            user=self.user,
            provider_order_id="order-callback-1",
            external_order_id="external-callback-1",
            amount=Decimal("10.00"),
            currency="GEL",
            status=BogCardOrder.Status.COMPLETED,
        )
        mocked_handle.return_value = order

        response = self.client.post(
            reverse("bog-payments-callback"),
            data={"event": "order_payment"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["order_id"], "order-callback-1")


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
        self.driver = User.objects.create_user(username="bog_payout_driver", password="pass1234")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver,
            phone_number="598950002",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="bog-driver-1",
            is_active=True,
        )
        ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="bog-payout-admin-conn",
            status="active",
            config={"mode": "live"},
        )
        self.driver_wallet, _ = Wallet.objects.get_or_create(user=self.driver)
        self.driver_wallet.balance = Decimal("150.00")
        self.driver_wallet.save(update_fields=["balance"])
        self.bank_account = BankAccount.objects.create(
            user=self.driver,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000002",
            beneficiary_name="Nika Beridze",
            beneficiary_inn="01001010101",
        )
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("200.00"),
            created_by=self.user,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("150.00"),
            created_by=self.user,
        )

    def _create_withdrawal(self, amount="25.00"):
        self.client.force_authenticate(self.driver)
        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.bank_account.id, "amount": amount, "note": "bog payout"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY=f"withdrawal-bog-{amount}",
            HTTP_X_REQUEST_ID=f"req-bog-{amount}",
        )
        self.client.force_authenticate(self.user)
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
    def test_request_bog_payout_otp_uses_document_key(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.side_effect = [
            {
                "ok": True,
                "http_status": 200,
                "body": [{"UniqueKey": 555001, "ResultCode": 0, "Match": 100}],
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {},
            },
        ]

        withdrawal = self._create_withdrawal()
        submit_response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        payout_id = submit_response.data["id"]

        otp_response = self.client.post(
            reverse("bog-request-otp", kwargs={"payout_id": payout_id}),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(otp_response.status_code, status.HTTP_200_OK)
        self.assertEqual(otp_response.data["detail"], "OTP requested from Bank of Georgia.")
        otp_call = mocked_request.call_args_list[1]
        self.assertEqual(otp_call.kwargs["endpoint"], "/otp/request")
        self.assertEqual(otp_call.kwargs["body"], {"ObjectKey": 555001, "ObjectType": 0})

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    def test_sign_bog_payout_endpoint_completes_withdrawal(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.side_effect = [
            {
                "ok": True,
                "http_status": 200,
                "body": [{"UniqueKey": 555002, "ResultCode": 0, "Match": 100}],
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {},
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {"Status": "P", "ResultCode": None, "Match": 100},
            },
        ]

        withdrawal = self._create_withdrawal()
        submit_response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        payout_id = submit_response.data["id"]

        sign_response = self.client.post(
            reverse("bog-sign", kwargs={"payout_id": payout_id}),
            data={"otp": "123456"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(sign_response.status_code, status.HTTP_200_OK)
        self.assertEqual(sign_response.data["detail"], "BoG payout sign request submitted.")
        self.assertEqual(sign_response.data["payout"]["status"], "settled")
        sign_call = mocked_request.call_args_list[1]
        self.assertEqual(sign_call.kwargs["endpoint"], "/sign/document")
        self.assertEqual(sign_call.kwargs["body"], {"Otp": "123456", "ObjectKey": 555002})
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.COMPLETED)

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
        driver_account = get_or_create_driver_available_account(self.driver, fleet=self.fleet, currency="GEL")
        fleet_reserve_account = get_or_create_fleet_reserve_account(self.fleet, currency="GEL")
        self.assertEqual(get_account_balance(driver_account), Decimal("150.00"))
        self.assertEqual(get_account_balance(fleet_reserve_account), Decimal("200.00"))

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    def test_letter_completed_bog_status_marks_withdrawal_completed(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.side_effect = [
            {
                "ok": True,
                "http_status": 200,
                "body": [{"UniqueKey": 777001, "ResultCode": 0, "Match": 100}],
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {"Status": "P", "ResultCode": None, "Match": 100},
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
        self.assertEqual(status_response.data["status"], "settled")
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.COMPLETED)

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    def test_letter_rejected_bog_status_reverses_wallet_balance(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.side_effect = [
            {
                "ok": True,
                "http_status": 200,
                "body": [{"UniqueKey": 777002, "ResultCode": 0, "Match": 100}],
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {"Status": "R", "ResultCode": 12, "Match": 100},
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
        driver_account = get_or_create_driver_available_account(self.driver, fleet=self.fleet, currency="GEL")
        fleet_reserve_account = get_or_create_fleet_reserve_account(self.fleet, currency="GEL")
        self.assertEqual(get_account_balance(driver_account), Decimal("150.00"))
        self.assertEqual(get_account_balance(fleet_reserve_account), Decimal("200.00"))

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


class FleetScopedBogPayoutApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="fleet_bog_owner", password="pass1234")
        self.operator = User.objects.create_user(username="fleet_bog_operator", password="pass1234")
        self.driver = User.objects.create_user(username="fleet_bog_driver", password="pass1234")
        self.fleet = Fleet.objects.create(name="Fleet Scoped BoG")
        for user, role, phone in [
            (self.owner, FleetPhoneBinding.Role.OWNER, "598977700"),
            (self.operator, FleetPhoneBinding.Role.OPERATOR, "598977701"),
            (self.driver, FleetPhoneBinding.Role.DRIVER, "598977702"),
        ]:
            FleetPhoneBinding.objects.create(
                fleet=self.fleet,
                user=user,
                phone_number=phone,
                role=role,
                is_active=True,
            )

        self.other_owner = User.objects.create_user(username="fleet_bog_other_owner", password="pass1234")
        self.other_driver = User.objects.create_user(username="fleet_bog_other_driver", password="pass1234")
        self.other_fleet = Fleet.objects.create(name="Fleet Scoped Other")
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_owner,
            phone_number="598977703",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_driver,
            phone_number="598977704",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )

        self.owner_connection = ProviderConnection.objects.create(
            user=self.owner,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="fleet-bog-owner-conn",
            status="active",
            config={"mode": "live"},
        )
        self.other_owner_connection = ProviderConnection.objects.create(
            user=self.other_owner,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="fleet-bog-other-conn",
            status="active",
            config={"mode": "live"},
        )

        self.driver_wallet, _ = Wallet.objects.get_or_create(user=self.driver)
        self.driver_wallet.balance = Decimal("120.00")
        self.driver_wallet.save(update_fields=["balance"])
        self.driver_bank = BankAccount.objects.create(
            user=self.driver,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000003001",
            beneficiary_name="Fleet Driver",
            beneficiary_inn="01010101010",
        )
        self.fleet_withdrawal = WithdrawalRequest.objects.create(
            user=self.driver,
            wallet=self.driver_wallet,
            fleet=self.fleet,
            bank_account=self.driver_bank,
            amount=Decimal("25.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )

        self.other_driver_wallet, _ = Wallet.objects.get_or_create(user=self.other_driver)
        self.other_driver_wallet.balance = Decimal("120.00")
        self.other_driver_wallet.save(update_fields=["balance"])
        self.other_bank = BankAccount.objects.create(
            user=self.other_driver,
            bank_name="TBC Bank",
            account_number="GE64TB00000000003002",
            beneficiary_name="Other Fleet Driver",
            beneficiary_inn="02020202020",
        )
        self.other_withdrawal = WithdrawalRequest.objects.create(
            user=self.other_driver,
            wallet=self.other_driver_wallet,
            fleet=self.other_fleet,
            bank_account=self.other_bank,
            amount=Decimal("30.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    def test_operator_can_submit_fleet_withdrawal_with_owner_connection(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": [{"UniqueKey": 777111, "ResultCode": 0, "Match": 1}],
        }
        self.client.force_authenticate(self.operator)

        response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": self.fleet_withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "processing")
        payout = BogPayout.objects.get(id=response.data["id"])
        self.assertEqual(payout.connection_id, self.owner_connection.id)
        self.fleet_withdrawal.refresh_from_db()
        self.assertEqual(self.fleet_withdrawal.status, WithdrawalRequest.Status.PROCESSING)

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    @override_settings(WITHDRAWAL_REQUEST_COOLDOWN_SECONDS=0)
    def test_operator_can_submit_driver_created_withdrawal_in_same_fleet(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": [{"UniqueKey": 777119, "ResultCode": 0, "Match": 1}],
        }

        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="fleet-bog-driver-mapped",
            is_active=True,
        )
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("100.00"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("40.00"),
            created_by=self.owner,
        )

        self.client.force_authenticate(self.driver)
        create_response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank.id, "amount": "18.00", "note": "driver created payout"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="fleet-bog-driver-created",
            HTTP_X_REQUEST_ID="req-fleet-bog-driver-created",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_withdrawal_id = create_response.data["id"]
        auto_payout = BogPayout.objects.get(withdrawal_id=created_withdrawal_id)
        self.assertEqual(auto_payout.connection_id, self.owner_connection.id)
        self.assertEqual(auto_payout.provider_unique_key, 777119)
        created_withdrawal = WithdrawalRequest.objects.get(id=created_withdrawal_id)
        self.assertEqual(created_withdrawal.status, WithdrawalRequest.Status.PROCESSING)

        self.client.force_authenticate(self.operator)
        list_response = self.client.get(reverse("withdrawal-list"), HTTP_X_FLEET_NAME=self.fleet.name)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(created_withdrawal_id, {item["id"] for item in list_response.data})

        submit_response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": created_withdrawal_id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(submit_response.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_response.data["status"], "processing")
        payout = BogPayout.objects.get(id=submit_response.data["id"])
        self.assertEqual(payout.connection_id, self.owner_connection.id)

    @patch("integrations.services._bog_request")
    @patch("integrations.services._bog_missing_payout_env_vars")
    def test_operator_can_refresh_fleet_payout_statuses(self, mocked_missing, mocked_request):
        mocked_missing.return_value = []
        mocked_request.side_effect = [
            {
                "ok": True,
                "http_status": 200,
                "body": [{"UniqueKey": 777222, "ResultCode": 0, "Match": 1}],
            },
            {
                "ok": True,
                "http_status": 200,
                "body": {"Status": "Completed", "ResultCode": 0, "Match": 1},
            },
        ]
        BogPayout.objects.all().delete()
        self.client.force_authenticate(self.operator)
        submit_response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": self.fleet_withdrawal.id},
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
        self.assertEqual(status_response.data["status"], "settled")

    @patch("integrations.views.sync_open_bog_payouts")
    def test_operator_can_refresh_all_fleet_payout_statuses(self, mocked_sync_all):
        mocked_sync_all.return_value = {"checked_count": 1, "updated_count": 1, "error_count": 0, "errors": []}
        self.client.force_authenticate(self.operator)

        response = self.client.post(
            reverse("bog-sync-all"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mocked_sync_all.call_args.kwargs["connection"].id, self.owner_connection.id)

    def test_operator_can_list_fleet_bog_payouts(self):
        payout = BogPayout.objects.create(
            connection=self.owner_connection,
            withdrawal=self.fleet_withdrawal,
            provider_unique_id="fleet-bog-payout",
            status="processing",
        )
        BogPayout.objects.create(
            connection=self.other_owner_connection,
            withdrawal=self.other_withdrawal,
            provider_unique_id="other-bog-payout",
            status="processing",
        )
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("bog-payouts"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [payout.id])

    def test_operator_cannot_act_on_another_fleets_withdrawal_or_payout(self):
        other_payout = BogPayout.objects.create(
            connection=self.other_owner_connection,
            withdrawal=self.other_withdrawal,
            provider_unique_id="other-fleet-status",
            status="processing",
        )
        self.client.force_authenticate(self.operator)

        submit_response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": self.other_withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(submit_response.status_code, status.HTTP_404_NOT_FOUND)

        status_response = self.client.post(
            reverse("bog-status-sync", kwargs={"payout_id": other_payout.id}),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(status_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_driver_cannot_access_owner_operator_bog_payout_tooling(self):
        self.client.force_authenticate(self.driver)

        list_response = self.client.get(reverse("bog-payouts"), HTTP_X_FLEET_NAME=self.fleet.name)
        submit_response = self.client.post(
            reverse("bog-submit"),
            data={"withdrawal_id": self.fleet_withdrawal.id},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        sync_all_response = self.client.post(
            reverse("bog-sync-all"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )

        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(submit_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(sync_all_response.status_code, status.HTTP_403_FORBIDDEN)


class YandexLiveSyncServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="yandex_sync_user", password="pass1234")
        self.fleet = Fleet.objects.create(name="Yandex Live Sync Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598733333",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        self.driver = User.objects.create_user(username="yandex_sync_driver", password="pass1234")
        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="drv-1",
            is_active=True,
        )
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
        driver_account = LedgerAccount.objects.get(
            user=self.driver,
            account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
        )
        self.assertEqual(get_account_balance(driver_account), Decimal("15.25"))


class BogDepositSyncServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="deposit_sync_user", password="pass1234")
        self.fleet = Fleet.objects.create(name="Sync Deposit Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598811111",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        self.connection = ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="bog-deposit-sync",
            status="active",
            config={"mode": "live"},
        )

    @patch("integrations.services._bog_request")
    def test_sync_bog_deposits_matches_reference_and_credits_fleet_reserve(self, mocked_request):
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": {
                "Records": [
                    {
                        "DocKey": 1001,
                        "Credit": "45.50",
                        "Nomination": f"Deposit EXP-FLT-{self.fleet.id:06d}",
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

        self.assertEqual(Deposit.objects.filter(fleet=self.fleet).count(), 1)
        self.assertEqual(IncomingBankTransfer.objects.filter(fleet=self.fleet).count(), 1)
        reserve_account = LedgerAccount.objects.get(
            fleet=self.fleet,
            account_type=LedgerAccount.AccountType.FLEET_RESERVE,
        )
        self.assertEqual(get_account_balance(reserve_account), Decimal("45.50"))
        treasury_account = LedgerAccount.objects.get(account_type=LedgerAccount.AccountType.TREASURY)
        self.assertEqual(get_account_balance(treasury_account), Decimal("45.50"))
        transfer = IncomingBankTransfer.objects.get(provider_transaction_id="1001")
        self.assertEqual(transfer.raw_payload["_expertpay_sync"]["source"], "activity_poll")

    @patch("integrations.services._bog_request")
    def test_sync_bog_deposits_keeps_unmatched_transfers_for_review(self, mocked_request):
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": {
                "Records": [
                    {
                        "DocKey": 1002,
                        "Credit": "12.00",
                        "Nomination": "Deposit without fleet code",
                        "PayerName": "Unmatched Payer",
                        "PostDate": "2026-03-16",
                        "ValueDate": "2026-03-16",
                    }
                ]
            },
        }

        with patch("integrations.services.settings.BOG_SOURCE_ACCOUNT_NUMBER", "GE00BG00000000000001"):
            result = sync_bog_deposits(connection=self.connection)

        self.assertTrue(result["ok"])
        self.assertEqual(result["credited_count"], 0)
        self.assertEqual(result["unmatched_count"], 1)
        self.assertEqual(Deposit.objects.count(), 0)
        transfer = IncomingBankTransfer.objects.get(provider_transaction_id="1002")
        self.assertEqual(transfer.match_status, IncomingBankTransfer.MatchStatus.UNMATCHED)
        self.assertIsNone(transfer.fleet_id)
        self.assertEqual(transfer.raw_payload["_expertpay_sync"]["source"], "activity_poll")

    @patch("integrations.services._bog_request")
    def test_backfill_sync_recovers_older_transfer_without_double_credit_on_rerun(self, mocked_request):
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": {
                "Records": [
                    {
                        "DocKey": 2001,
                        "Credit": "77.25",
                        "Nomination": f"Recovered EXP-FLT-{self.fleet.id:06d}",
                        "PayerName": "Recovered Payer",
                        "PostDate": "2026-03-01",
                        "ValueDate": "2026-03-01",
                    }
                ]
            },
        }

        with patch("integrations.services.settings.BOG_SOURCE_ACCOUNT_NUMBER", "GE00BG00000000000001"):
            first = sync_bog_deposits(
                connection=self.connection,
                use_statement=True,
                start_date="2026-03-01",
                end_date="2026-03-05",
            )
            second = sync_bog_deposits(
                connection=self.connection,
                use_statement=True,
                start_date="2026-03-01",
                end_date="2026-03-05",
            )

        self.assertTrue(first["ok"])
        self.assertEqual(first["sync_source"], "backfill")
        self.assertEqual(first["credited_count"], 1)
        self.assertEqual(second["credited_count"], 0)
        self.assertEqual(Deposit.objects.filter(provider_transaction_id="2001").count(), 1)
        transfer = IncomingBankTransfer.objects.get(provider_transaction_id="2001")
        self.assertEqual(str(transfer.booking_date), "2026-03-01")
        self.assertEqual(transfer.raw_payload["_expertpay_sync"]["source"], "backfill")
        self.assertEqual(transfer.raw_payload["_expertpay_sync"]["start_date"], "2026-03-01")
        reserve_account = LedgerAccount.objects.get(
            fleet=self.fleet,
            account_type=LedgerAccount.AccountType.FLEET_RESERVE,
        )
        self.assertEqual(get_account_balance(reserve_account), Decimal("77.25"))


class BogCardOrderServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="card_sync_user", password="pass1234")
        self.fleet = Fleet.objects.create(name="Card Sync Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598900222",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )
        self.connection = ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BOG_PAYMENTS,
            external_account_id="bog-payments-sync",
            status="active",
            config={"mode": "live"},
        )

    @patch("integrations.services._bog_payments_request")
    def test_sync_bog_card_order_completed_credits_fleet_reserve(self, mocked_request):
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": {
                "status": "completed",
                "payment_detail": {
                    "transaction_id": "txn-1001",
                    "payer_identifier": "payer-1",
                    "transfer_method": {"key": "card"},
                    "card_type": "visa",
                },
            },
        }
        order = BogCardOrder.objects.create(
            connection=self.connection,
            user=self.user,
            fleet=self.fleet,
            provider_order_id="card-order-1001",
            external_order_id="cardtopup-1001",
            amount=Decimal("32.40"),
            currency="GEL",
            status=BogCardOrder.Status.CREATED,
        )

        synced = sync_bog_card_order(order=order)

        self.assertEqual(synced.status, BogCardOrder.Status.COMPLETED)
        self.assertEqual(synced.transaction_id, "txn-1001")
        self.assertEqual(synced.transfer_method, "card")

        deposit = Deposit.objects.get(fleet=self.fleet, provider="bog_card")
        self.assertEqual(deposit.provider_transaction_id, "card-order-1001")
        self.assertEqual(deposit.amount, Decimal("32.40"))

        reserve_account = LedgerAccount.objects.get(
            fleet=self.fleet,
            account_type=LedgerAccount.AccountType.FLEET_RESERVE,
        )
        treasury_account = LedgerAccount.objects.get(
            account_type=LedgerAccount.AccountType.TREASURY,
            user=None,
            fleet=None,
        )
        self.assertEqual(get_account_balance(reserve_account), Decimal("32.40"))
        self.assertEqual(get_account_balance(treasury_account), Decimal("32.40"))

    @patch("integrations.services._bog_payments_request")
    def test_create_bog_card_order_uses_hosted_checkout_defaults_without_forced_methods(self, mocked_request):
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": {
                "id": "card-order-2002",
                "_links": {
                    "details": {"href": "https://api.bog.ge/payments/v1/receipt/card-order-2002"},
                    "redirect": {"href": "https://payment.bog.ge/?order_id=card-order-2002"},
                },
            },
        }

        order = create_bog_card_order(
            connection=self.connection,
            user=self.user,
            fleet=self.fleet,
            amount=Decimal("25.00"),
            currency="GEL",
        )

        self.assertEqual(order.provider_order_id, "card-order-2002")
        payload = mocked_request.call_args.kwargs["body"]
        self.assertEqual(
            payload["purchase_units"]["basket"][0]["description"],
            f"ExpertPay fleet reserve top-up for {self.fleet.name}",
        )
        self.assertEqual(payload["purchase_units"]["basket"][0]["total_price"], 25.0)
        self.assertNotIn("payment_method", payload)

    @override_settings(BOG_PAYMENTS_METHODS=["card", "bog_p2p"])
    @patch("integrations.services._bog_payments_request")
    def test_create_bog_card_order_respects_configured_payment_methods(self, mocked_request):
        mocked_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": {
                "id": "card-order-2003",
                "_links": {
                    "details": {"href": "https://api.bog.ge/payments/v1/receipt/card-order-2003"},
                    "redirect": {"href": "https://payment.bog.ge/?order_id=card-order-2003"},
                },
            },
        }

        create_bog_card_order(
            connection=self.connection,
            user=self.user,
            fleet=self.fleet,
            amount=Decimal("11.50"),
            currency="GEL",
        )

        payload = mocked_request.call_args.kwargs["body"]
        self.assertEqual(payload["payment_method"], ["card", "bog_p2p"])
