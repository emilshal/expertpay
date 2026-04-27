from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import DriverFleetMembership, Fleet, FleetPhoneBinding
from integrations.models import ExternalEvent, ProviderConnection, YandexTransactionRecord
from ledger.models import LedgerAccount, LedgerEntry
from ledger.services import (
    get_account_balance,
    get_or_create_payout_clearing_account,
    get_or_create_platform_fee_account,
    record_driver_earning_allocation,
    record_fleet_reserve_deposit,
)

from .models import BankAccount, Deposit, FleetRatingPenalty, IncomingBankTransfer, Wallet, WithdrawalRequest
from .services import build_fleet_deposit_reference
from .views import _fleet_rating_from_completed_withdrawals


User = get_user_model()


class WalletTopUpApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="wallet_user", password="pass1234")
        self.fleet = Fleet.objects.create(name="Wallet Topup Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598900001",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )
        self.client.force_authenticate(self.user)

    def test_top_up_increases_wallet_and_creates_ledger_entry(self):
        response = self.client.post(
            reverse("wallet-top-up"),
            data={"amount": "25.00", "note": "sandbox fund"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="topup-key-1",
            HTTP_X_REQUEST_ID="req-topup-1",
            HTTP_X_FLEET_NAME=self.fleet.name,
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
        headers["HTTP_X_FLEET_NAME"] = self.fleet.name

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


class WalletRoleAuthorizationTests(APITestCase):
    def setUp(self):
        self.unbound_user = User.objects.create_user(username="wallet_unbound_user", password="pass1234")
        self.owner_user = User.objects.create_user(username="wallet_owner_user", password="pass1234")
        self.bound_user = User.objects.create_user(username="wallet_bound_user", password="pass1234")
        self.fleet = Fleet.objects.create(name="Wallet Auth Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner_user,
            phone_number="598900009",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.bound_user,
            phone_number="598900010",
            role=FleetPhoneBinding.Role.OPERATOR,
            is_active=True,
        )
        self.other_owner = User.objects.create_user(username="wallet_other_owner", password="pass1234")
        self.other_fleet = Fleet.objects.create(name="Wallet Other Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_owner,
            phone_number="598900011",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        self.bank_account = BankAccount.objects.create(
            user=self.bound_user,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000999",
            beneficiary_name="Bound User",
            beneficiary_inn="01010101010",
        )

    def test_unbound_user_cannot_create_bank_account(self):
        self.client.force_authenticate(self.unbound_user)
        response = self.client.post(
            reverse("bank-account-list-create"),
            data={
                "bank_name": "Bank of Georgia",
                "account_number": "GE64BG00000000000011",
                "beneficiary_name": "No Fleet User",
                "beneficiary_inn": "99999999999",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unbound_user_cannot_create_withdrawal(self):
        self.client.force_authenticate(self.unbound_user)
        foreign_account = BankAccount.objects.create(
            user=self.unbound_user,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000012",
            beneficiary_name="No Fleet User",
            beneficiary_inn="99999999999",
        )
        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": foreign_account.id, "amount": "5.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="unbound-withdrawal-key",
            HTTP_X_REQUEST_ID="unbound-withdrawal-request",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unbound_user_cannot_sync_deposits(self):
        self.client.force_authenticate(self.unbound_user)
        response = self.client.post(reverse("deposit-sync"), data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bound_operator_can_sync_deposits(self):
        ProviderConnection.objects.create(
            user=self.owner_user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="wallet-auth-bog",
            status="active",
            config={"mode": "live"},
        )
        self.client.force_authenticate(self.bound_user)
        with patch("wallet.views.sync_bog_deposits") as mocked_sync:
            mocked_sync.return_value = {
                "ok": True,
                "configured": True,
                "detail": "sync ok",
                "checked_count": 0,
                "matched_count": 0,
                "credited_count": 0,
                "unmatched_count": 0,
                "ignored_count": 0,
                "credited_total": "0.00",
                "http_status": 200,
                "endpoint": "/documents/v2/todayactivities/test/GEL",
                "errors": None,
            }
            response = self.client.post(
                reverse("deposit-sync"),
                data={},
                format="json",
                HTTP_X_FLEET_NAME=self.fleet.name,
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mocked_sync.call_args.kwargs["connection"].user_id, self.owner_user.id)

    def test_bound_operator_cannot_run_deposit_backfill(self):
        ProviderConnection.objects.create(
            user=self.owner_user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="wallet-auth-bog-backfill",
            status="active",
            config={"mode": "live"},
        )
        self.client.force_authenticate(self.bound_user)
        response = self.client.post(
            reverse("deposit-sync"),
            data={"start_date": "2026-03-01", "end_date": "2026-03-05"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_operator_cannot_use_another_fleets_bog_connection(self):
        ProviderConnection.objects.create(
            user=self.other_owner,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="wallet-other-fleet-bog",
            status="active",
            config={"mode": "live"},
        )
        self.client.force_authenticate(self.bound_user)
        response = self.client.post(
            reverse("deposit-sync"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Bank of Georgia connection is not configured.")

    def test_operator_gets_missing_connection_error_when_active_fleet_has_no_bog_connection(self):
        self.client.force_authenticate(self.bound_user)
        response = self.client.post(
            reverse("deposit-sync"),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Bank of Georgia connection is not configured.")


class WalletDepositApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="deposit_user", password="pass1234")
        self.client.force_authenticate(self.user)
        self.fleet = Fleet.objects.create(name="Deposit Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.user,
            phone_number="598955555",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )
        self.other_user = User.objects.create_user(username="target_user", password="pass1234")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.other_user,
            phone_number="598955556",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        self.other_fleet = Fleet.objects.create(name="Other Deposit Fleet")
        self.other_admin = User.objects.create_user(username="other_deposit_admin", password="pass1234")
        FleetPhoneBinding.objects.create(
            fleet=self.other_fleet,
            user=self.other_admin,
            phone_number="598955557",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )

    def test_deposit_instructions_return_account_and_reference(self):
        response = self.client.get(reverse("deposit-instructions"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fleet_name"], self.fleet.name)
        self.assertIn("reference_code", response.data)
        self.assertTrue(response.data["reference_code"].startswith("EXP-FLT-"))

    def test_admin_can_trigger_deposit_backfill(self):
        ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="deposit-backfill-bog",
            status="active",
            config={"mode": "live"},
        )
        with patch("wallet.views.sync_bog_deposits") as mocked_sync:
            mocked_sync.return_value = {
                "ok": True,
                "configured": True,
                "detail": "backfill ok",
                "checked_count": 2,
                "matched_count": 1,
                "credited_count": 1,
                "unmatched_count": 1,
                "ignored_count": 0,
                "credited_total": "50.00",
                "http_status": 200,
                "endpoint": "/statement/test/GEL/2026-03-01/2026-03-05",
                "sync_source": "backfill",
                "start_date": "2026-03-01",
                "end_date": "2026-03-05",
                "errors": None,
            }
            response = self.client.post(
                reverse("deposit-sync"),
                data={"start_date": "2026-03-01", "end_date": "2026-03-05"},
                format="json",
                HTTP_X_FLEET_NAME=self.fleet.name,
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["sync_source"], "backfill")
        self.assertEqual(mocked_sync.call_args.kwargs["use_statement"], True)
        self.assertEqual(str(mocked_sync.call_args.kwargs["start_date"]), "2026-03-01")
        self.assertEqual(str(mocked_sync.call_args.kwargs["end_date"]), "2026-03-05")

    @patch("wallet.views.sync_bog_deposits")
    def test_deposit_sync_endpoint_returns_sync_result(self, mocked_sync):
        ProviderConnection.objects.create(
            user=self.user,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="bog-deposit-user",
            status="active",
            config={"mode": "live"},
        )
        mocked_sync.return_value = {
            "ok": True,
            "configured": True,
            "detail": "BoG deposit sync completed.",
            "checked_count": 1,
            "matched_count": 1,
            "credited_count": 1,
            "unmatched_count": 0,
            "ignored_count": 0,
            "credited_total": "50.00",
            "http_status": 200,
            "endpoint": "/documents/v2/todayactivities/test/GEL",
            "errors": None,
        }

        response = self.client.post(reverse("deposit-sync"), data={}, format="json", HTTP_X_FLEET_NAME=self.fleet.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["credited_count"], 1)

    def test_deposit_list_returns_user_deposits(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.user)
        Deposit.objects.create(
            user=self.user,
            wallet=wallet,
            fleet=self.fleet,
            amount=Decimal("25.00"),
            currency="GEL",
            reference_code="EXP-FLT-000123",
            provider_transaction_id="bog-doc-1",
        )
        response = self.client.get(reverse("deposit-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["provider_transaction_id"], "bog-doc-1")
        self.assertEqual(response.data[0]["fleet_name"], self.fleet.name)

    def test_driver_cannot_fetch_fleet_deposits(self):
        self.client.force_authenticate(self.other_user)
        response = self.client.get(reverse("deposit-list"), HTTP_X_FLEET_NAME=self.fleet.name)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_unmatched_incoming_transfers(self):
        IncomingBankTransfer.objects.create(
            provider_transaction_id="bog-unmatched-1",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("42.00"),
            reference_text=f"deposit for {build_fleet_deposit_reference(self.fleet)}",
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
        )

        response = self.client.get(
            reverse("incoming-transfer-unmatched"),
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["provider_transaction_id"], "bog-unmatched-1")

    def test_fleet_admin_cannot_see_other_fleet_unmatched_transfers(self):
        IncomingBankTransfer.objects.create(
            provider_transaction_id="bog-unmatched-own-fleet",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("20.00"),
            reference_text=f"deposit for {build_fleet_deposit_reference(self.fleet)}",
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
        )
        IncomingBankTransfer.objects.create(
            provider_transaction_id="bog-unmatched-other-fleet",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("25.00"),
            reference_text=f"deposit for {build_fleet_deposit_reference(self.other_fleet)}",
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
        )

        response = self.client.get(
            reverse("incoming-transfer-unmatched"),
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["provider_transaction_id"], "bog-unmatched-own-fleet")

    def test_driver_cannot_list_unmatched_incoming_transfers(self):
        binding = FleetPhoneBinding.objects.get(user=self.user, fleet=self.fleet)
        binding.role = FleetPhoneBinding.Role.DRIVER
        binding.save(update_fields=["role"])

        response = self.client.get(
            reverse("incoming-transfer-unmatched"),
            HTTP_X_FLEET_NAME=self.fleet.name,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_manually_match_unmatched_transfer(self):
        transfer = IncomingBankTransfer.objects.create(
            provider_transaction_id="bog-unmatched-2",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("55.00"),
            reference_text=f"cash deposit {build_fleet_deposit_reference(self.fleet)}",
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
            payer_name="Test Payer",
        )

        response = self.client.post(
            reverse("incoming-transfer-manual-match", args=[transfer.id]),
            data={},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_X_REQUEST_ID="req-manual-match-1",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        transfer.refresh_from_db()
        self.assertEqual(transfer.match_status, IncomingBankTransfer.MatchStatus.MATCHED)
        self.assertEqual(transfer.fleet_id, self.fleet.id)
        self.assertEqual(Deposit.objects.filter(provider_transaction_id="bog-unmatched-2").count(), 1)
        deposit = Deposit.objects.get(provider_transaction_id="bog-unmatched-2")
        self.assertEqual(deposit.fleet_id, self.fleet.id)
        reserve_account = LedgerAccount.objects.get(
            fleet=self.fleet,
            account_type=LedgerAccount.AccountType.FLEET_RESERVE,
        )
        self.assertEqual(get_account_balance(reserve_account), Decimal("55.00"))

    def test_cross_fleet_manual_assignment_is_blocked(self):
        transfer = IncomingBankTransfer.objects.create(
            provider_transaction_id="bog-unmatched-cross-fleet",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("18.00"),
            reference_text=f"cash deposit {build_fleet_deposit_reference(self.fleet)}",
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
            payer_name="Cross Fleet Payer",
        )

        response = self.client.post(
            reverse("incoming-transfer-manual-match", args=[transfer.id]),
            data={"fleet_name": self.other_fleet.name},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_X_REQUEST_ID="req-manual-match-cross-fleet",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        transfer.refresh_from_db()
        self.assertEqual(transfer.match_status, IncomingBankTransfer.MatchStatus.UNMATCHED)
        self.assertEqual(Deposit.objects.filter(provider_transaction_id="bog-unmatched-cross-fleet").count(), 0)


class OwnerFleetSummaryApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner_summary", password="pass1234")
        self.driver_one = User.objects.create_user(
            username="owner_summary_driver_one",
            password="pass1234",
            first_name="Nika",
            last_name="Gelashvili",
        )
        self.driver_two = User.objects.create_user(username="owner_summary_driver_two", password="pass1234")
        self.fleet = Fleet.objects.create(name="Owner Summary Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598955600",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver_one,
            phone_number="598955601",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver_two,
            phone_number="598955602",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=self.driver_one,
            fleet=self.fleet,
            yandex_external_driver_id="owner-summary-driver-1",
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=self.driver_two,
            fleet=self.fleet,
            yandex_external_driver_id="owner-summary-driver-2",
            is_active=True,
        )
        self.client.force_authenticate(self.owner)

    def test_owner_summary_returns_fleet_financial_overview(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.owner)
        Deposit.objects.create(
            user=self.owner,
            wallet=wallet,
            fleet=self.fleet,
            amount=Decimal("120.00"),
            currency="GEL",
            reference_code="EXP-FLT-000120",
            provider_transaction_id="owner-summary-deposit-1",
        )
        Deposit.objects.create(
            user=self.owner,
            wallet=wallet,
            fleet=self.fleet,
            amount=Decimal("80.00"),
            currency="GEL",
            reference_code="EXP-FLT-000121",
            provider_transaction_id="owner-summary-deposit-2",
        )
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("200.00"),
            created_by=self.owner,
        )
        pending_bank = BankAccount.objects.create(
            user=self.driver_one,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000100",
            beneficiary_name="Nika Gelashvili",
            beneficiary_inn="01010101010",
        )
        processing_bank = BankAccount.objects.create(
            user=self.driver_two,
            bank_name="TBC Bank",
            account_number="GE64TB00000000000101",
            beneficiary_name="Driver Two",
            beneficiary_inn="02020202020",
        )
        completed_bank = BankAccount.objects.create(
            user=self.driver_one,
            bank_name="Liberty",
            account_number="GE64LB00000000000102",
            beneficiary_name="Nika Gelashvili",
            beneficiary_inn="01010101010",
        )
        pending_withdrawal = WithdrawalRequest.objects.create(
            user=self.driver_one,
            wallet=Wallet.objects.get_or_create(user=self.driver_one)[0],
            fleet=self.fleet,
            bank_account=pending_bank,
            amount=Decimal("35.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )
        WithdrawalRequest.objects.create(
            user=self.driver_two,
            wallet=Wallet.objects.get_or_create(user=self.driver_two)[0],
            fleet=self.fleet,
            bank_account=processing_bank,
            amount=Decimal("15.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PROCESSING,
        )
        WithdrawalRequest.objects.create(
            user=self.driver_one,
            wallet=Wallet.objects.get_or_create(user=self.driver_one)[0],
            fleet=self.fleet,
            bank_account=completed_bank,
            amount=Decimal("50.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.COMPLETED,
        )
        WithdrawalRequest.objects.create(
            user=self.driver_two,
            wallet=Wallet.objects.get_or_create(user=self.driver_two)[0],
            fleet=self.fleet,
            bank_account=processing_bank,
            amount=Decimal("12.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.FAILED,
        )
        IncomingBankTransfer.objects.create(
            provider_transaction_id="owner-summary-unmatched-1",
            provider="bog",
            account_number="GE00BOG",
            currency="GEL",
            amount=Decimal("60.00"),
            reference_text=build_fleet_deposit_reference(self.fleet),
            match_status=IncomingBankTransfer.MatchStatus.UNMATCHED,
        )

        response = self.client.get(reverse("owner-fleet-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fleet_name"], self.fleet.name)
        self.assertEqual(response.data["reserve_balance"], "200.00")
        self.assertEqual(response.data["total_funded"], "200.00")
        self.assertEqual(response.data["total_withdrawn"], "50.00")
        self.assertEqual(response.data["total_fees"], "6.00")
        self.assertEqual(response.data["pending_payouts_count"], 2)
        self.assertEqual(response.data["pending_payouts_total"], "50.00")
        self.assertEqual(response.data["unmatched_deposits_count"], 1)
        self.assertEqual(response.data["failed_payouts_count"], 1)
        self.assertEqual(response.data["failed_payouts_total"], "12.00")
        self.assertEqual(response.data["active_drivers_count"], 2)
        pending_ids = {item["id"] for item in response.data["pending_payouts"]}
        self.assertIn(pending_withdrawal.id, pending_ids)
        pending_names = {item["driver_name"] for item in response.data["pending_payouts"]}
        self.assertIn("Nika Gelashvili", pending_names)

    def test_owner_summary_pending_total_counts_only_principal_when_driver_pays_fees(self):
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("51.00"),
            created_by=self.owner,
        )
        bank_account = BankAccount.objects.create(
            user=self.driver_one,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000999",
            beneficiary_name="Nika Gelashvili",
            beneficiary_inn="01010101010",
        )
        WithdrawalRequest.objects.create(
            user=self.driver_one,
            wallet=Wallet.objects.get_or_create(user=self.driver_one)[0],
            fleet=self.fleet,
            bank_account=bank_account,
            amount=Decimal("50.00"),
            fee_amount=Decimal("0.50"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )

        response = self.client.get(reverse("owner-fleet-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["reserve_balance"], "51.00")
        self.assertEqual(response.data["pending_payouts_total"], "50.00")
        self.assertLess(Decimal(response.data["pending_payouts_total"]), Decimal(response.data["reserve_balance"]))

    def test_driver_cannot_access_owner_summary(self):
        self.client.force_authenticate(self.driver_one)
        response = self.client.get(reverse("owner-fleet-summary"), HTTP_X_FLEET_NAME=self.fleet.name)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_driver_finance_returns_driver_balances_and_transaction_counts(self):
        record_driver_earning_allocation(
            user=self.driver_one,
            fleet=self.fleet,
            amount=Decimal("44.00"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver_two,
            fleet=self.fleet,
            amount=Decimal("12.50"),
            created_by=self.owner,
        )
        yandex_connection = ProviderConnection.objects.create(
            user=self.owner,
            provider=ProviderConnection.Provider.YANDEX,
            external_account_id="owner-summary-yandex",
            status="active",
        )
        first_event = ExternalEvent.objects.create(
            connection=yandex_connection,
            external_id="evt-owner-summary-1",
            event_type="transaction",
            payload={},
        )
        second_event = ExternalEvent.objects.create(
            connection=yandex_connection,
            external_id="evt-owner-summary-2",
            event_type="transaction",
            payload={},
        )
        YandexTransactionRecord.objects.create(
            connection=yandex_connection,
            external_event=first_event,
            external_transaction_id="tx-owner-summary-1",
            driver_external_id="owner-summary-driver-1",
            amount=Decimal("20.00"),
            currency="GEL",
        )
        YandexTransactionRecord.objects.create(
            connection=yandex_connection,
            external_event=second_event,
            external_transaction_id="tx-owner-summary-2",
            driver_external_id="owner-summary-driver-1",
            amount=Decimal("15.00"),
            currency="GEL",
        )

        response = self.client.get(reverse("owner-driver-finance"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        row_map = {item["first_name"] or item["phone_number"]: item for item in response.data}
        self.assertEqual(row_map["Nika"]["transaction_count"], 2)
        self.assertEqual(row_map["Nika"]["available_balance"], "44.00")
        self.assertEqual(row_map["598955602"]["transaction_count"], 0)
        self.assertEqual(row_map["598955602"]["available_balance"], "12.50")

    def test_driver_cannot_access_owner_driver_finance(self):
        self.client.force_authenticate(self.driver_one)
        response = self.client.get(reverse("owner-driver-finance"), HTTP_X_FLEET_NAME=self.fleet.name)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_transactions_returns_fleet_deposits_and_withdrawals(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.owner)
        Deposit.objects.create(
            user=self.owner,
            wallet=wallet,
            fleet=self.fleet,
            amount=Decimal("90.00"),
            currency="GEL",
            reference_code="EXP-FLT-000301",
            provider_transaction_id="owner-transactions-deposit-1",
        )
        bank_account = BankAccount.objects.create(
            user=self.driver_one,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000301",
            beneficiary_name="Nika Gelashvili",
            beneficiary_inn="01010101010",
        )
        WithdrawalRequest.objects.create(
            user=self.driver_one,
            wallet=Wallet.objects.get_or_create(user=self.driver_one)[0],
            fleet=self.fleet,
            bank_account=bank_account,
            amount=Decimal("25.00"),
            fee_amount=Decimal("0.50"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )

        response = self.client.get(reverse("owner-transactions"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["transaction_type"], "Withdrawal")
        self.assertEqual(response.data[0]["amount"], "25.00")
        self.assertEqual(response.data[1]["transaction_type"], "Deposit")
        self.assertEqual(response.data[1]["amount"], "90.00")


class AdminNetworkSummaryApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_network_summary", password="pass1234")
        self.owner = User.objects.create_user(username="admin_network_owner", password="pass1234")
        self.driver_one = User.objects.create_user(username="admin_network_driver_one", password="pass1234")
        self.driver_two = User.objects.create_user(username="admin_network_driver_two", password="pass1234")
        self.driver_three = User.objects.create_user(username="admin_network_driver_three", password="pass1234")
        self.primary_fleet = Fleet.objects.create(name="Alpha Fleet")
        self.secondary_fleet = Fleet.objects.create(name="Beta Fleet")

        FleetPhoneBinding.objects.create(
            fleet=self.primary_fleet,
            user=self.admin,
            phone_number="598955610",
            role=FleetPhoneBinding.Role.ADMIN,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.primary_fleet,
            user=self.owner,
            phone_number="598955611",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )

        self.client.force_authenticate(self.admin)

    def test_admin_network_summary_returns_all_fleet_totals_and_sorted_withdrawals(self):
        record_fleet_reserve_deposit(
            fleet=self.primary_fleet,
            amount=Decimal("120.00"),
            created_by=self.admin,
        )
        record_fleet_reserve_deposit(
            fleet=self.secondary_fleet,
            amount=Decimal("80.00"),
            created_by=self.owner,
        )

        primary_bank = BankAccount.objects.create(
            user=self.driver_one,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000201",
            beneficiary_name="Driver One",
            beneficiary_inn="01010101010",
        )
        secondary_bank = BankAccount.objects.create(
            user=self.driver_two,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000202",
            beneficiary_name="Driver Two",
            beneficiary_inn="02020202020",
        )
        tertiary_bank = BankAccount.objects.create(
            user=self.driver_three,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000203",
            beneficiary_name="Driver Three",
            beneficiary_inn="03030303030",
        )

        WithdrawalRequest.objects.create(
            user=self.driver_one,
            wallet=Wallet.objects.get_or_create(user=self.driver_one)[0],
            fleet=self.primary_fleet,
            bank_account=primary_bank,
            amount=Decimal("30.00"),
            fee_amount=Decimal("0.50"),
            currency="GEL",
            status=WithdrawalRequest.Status.COMPLETED,
        )
        WithdrawalRequest.objects.create(
            user=self.driver_two,
            wallet=Wallet.objects.get_or_create(user=self.driver_two)[0],
            fleet=self.primary_fleet,
            bank_account=secondary_bank,
            amount=Decimal("20.00"),
            fee_amount=Decimal("0.50"),
            currency="GEL",
            status=WithdrawalRequest.Status.COMPLETED,
        )
        WithdrawalRequest.objects.create(
            user=self.driver_three,
            wallet=Wallet.objects.get_or_create(user=self.driver_three)[0],
            fleet=self.secondary_fleet,
            bank_account=tertiary_bank,
            amount=Decimal("40.00"),
            fee_amount=Decimal("0.50"),
            currency="GEL",
            status=WithdrawalRequest.Status.COMPLETED,
        )
        WithdrawalRequest.objects.create(
            user=self.driver_three,
            wallet=Wallet.objects.get_or_create(user=self.driver_three)[0],
            fleet=self.secondary_fleet,
            bank_account=tertiary_bank,
            amount=Decimal("10.00"),
            fee_amount=Decimal("0.50"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )

        response = self.client.get(reverse("admin-network-summary"), HTTP_X_FLEET_NAME=self.primary_fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_funded"], "200.00")
        self.assertEqual(response.data["total_withdrawn"], "100.00")
        self.assertEqual(response.data["total_fees"], "2.00")
        self.assertEqual(response.data["pending_payouts_count"], 1)
        self.assertEqual(response.data["pending_payouts_total"], "10.00")
        self.assertEqual(response.data["completed_withdrawal_transactions"], 4)
        self.assertEqual(response.data["fleet_count"], Fleet.objects.count())
        self.assertEqual(
            response.data["active_fleet_count"],
            Fleet.objects.filter(phone_bindings__is_active=True).distinct().count(),
        )
        self.assertEqual(response.data["withdrawn_by_fleet"][0]["fleet_name"], self.primary_fleet.name)
        self.assertEqual(response.data["withdrawn_by_fleet"][0]["transaction_count"], 2)
        self.assertEqual(response.data["withdrawn_by_fleet"][0]["total_withdrawn"], "50.00")
        self.assertEqual(response.data["withdrawn_by_fleet"][1]["fleet_name"], self.secondary_fleet.name)
        self.assertEqual(response.data["withdrawn_by_fleet"][1]["transaction_count"], 2)
        self.assertEqual(response.data["withdrawn_by_fleet"][1]["total_withdrawn"], "50.00")
        self.assertEqual(response.data["pending_by_fleet"][0]["fleet_name"], self.secondary_fleet.name)
        self.assertEqual(response.data["pending_by_fleet"][0]["transaction_count"], 1)
        self.assertEqual(response.data["pending_by_fleet"][0]["pending_total"], "10.00")
        self.assertEqual(response.data["pending_by_fleet"][0]["reserve_balance"], "80.00")

    def test_owner_cannot_access_admin_network_summary(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("admin-network-summary"), HTTP_X_FLEET_NAME=self.primary_fleet.name)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DriverWithdrawalApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="fleet_owner_withdraw", password="pass1234")
        self.driver = User.objects.create_user(username="fleet_driver_withdraw", password="pass1234")
        self.fleet = Fleet.objects.create(name="Withdrawal Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.owner,
            phone_number="598955557",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.driver,
            phone_number="598955558",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="drv-withdraw-1",
            is_active=True,
        )
        self.bank_account = Wallet.objects.get_or_create(user=self.driver)[0]
        self.driver_bank_account = BankAccount.objects.create(
            user=self.driver,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000003",
            beneficiary_name="Driver Withdraw",
            beneficiary_inn="01001010102",
        )
        self.client.force_authenticate(self.driver)

    def _fund_accounts(self, *, reserve_amount: str, available_amount: str):
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal(reserve_amount),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal(available_amount),
            created_by=self.owner,
        )

    def test_successful_withdrawal_debits_driver_and_fleet_and_routes_fee(self):
        self._fund_accounts(reserve_amount="100.00", available_amount="40.00")

        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "30.00", "note": "driver payout"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-1",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-1",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["fee_amount"]), Decimal("0.50"))
        withdrawal = WithdrawalRequest.objects.get(id=response.data["id"])
        self.assertEqual(withdrawal.fleet_id, self.fleet.id)
        self.assertEqual(withdrawal.fee_amount, Decimal("0.50"))

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

        self.assertEqual(get_account_balance(driver_account), Decimal("9.50"))
        self.assertEqual(get_account_balance(reserve_account), Decimal("70.00"))
        self.assertEqual(get_account_balance(payout_clearing), Decimal("30.00"))
        self.assertEqual(get_account_balance(fee_account), Decimal("0.50"))

    @patch("wallet.views.submit_withdrawal_to_bog")
    @patch("integrations.services._yandex_request")
    def test_withdrawal_posts_yandex_payout_transaction_when_connection_exists(
        self,
        mocked_yandex_request,
        mocked_bog_submit,
    ):
        mocked_yandex_request.return_value = {
            "ok": True,
            "http_status": 200,
            "body": {"transaction_id": "yandex-withdrawal-1"},
            "attempts": 1,
        }
        mocked_bog_submit.return_value = (None, True)
        ProviderConnection.objects.create(
            user=self.owner,
            fleet=self.fleet,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id="bog-withdrawal-test",
            status="active",
            config={},
        )
        ProviderConnection.objects.create(
            user=self.owner,
            fleet=self.fleet,
            provider=ProviderConnection.Provider.YANDEX,
            external_account_id="park-withdrawal-test",
            status="active",
            config={
                "park_id": "park-withdrawal-test",
                "client_id": "client",
                "api_key": "key",
            },
        )
        self._fund_accounts(reserve_amount="100.00", available_amount="40.00")

        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "30.00", "note": "driver payout"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-yandex",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-yandex",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = mocked_yandex_request.call_args.kwargs["body"]
        self.assertEqual(mocked_yandex_request.call_args.kwargs["endpoint"], "/v3/parks/driver-profiles/transactions")
        self.assertEqual(body["park_id"], "park-withdrawal-test")
        self.assertEqual(body["contractor_profile_id"], "drv-withdraw-1")
        self.assertEqual(body["amount"], "-30.0000")
        self.assertEqual(body["condition"]["balance_min"], "30.5000")
        self.assertEqual(body["data"]["kind"], "payout")
        self.assertEqual(body["data"]["fee_amount"], "-0.5000")
        self.assertEqual(
            mocked_yandex_request.call_args.kwargs["extra_headers"]["X-Idempotency-Token"],
            f"expertpay-withdrawal-{response.data['id']}",
        )
        self.assertTrue(
            ExternalEvent.objects.filter(
                external_id=f"expertpay-withdrawal-{response.data['id']}",
                event_type="withdrawal_payout",
                processed=True,
            ).exists()
        )

    def test_withdrawal_fails_when_driver_available_balance_is_too_low(self):
        self._fund_accounts(reserve_amount="100.00", available_amount="10.00")

        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "20.00"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-2",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-2",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("driver available balance", response.data["detail"])

    def test_withdrawal_with_empty_fleet_reserve_applies_rating_penalty(self):
        self._fund_accounts(reserve_amount="0.00", available_amount="20.00")

        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "10.00"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-empty-reserve",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-empty-reserve",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fleet reserve balance", response.data["detail"])
        self.assertEqual(
            FleetRatingPenalty.objects.filter(
                fleet=self.fleet,
                reason=FleetRatingPenalty.Reason.INSUFFICIENT_RESERVE,
            ).count(),
            1,
        )

        balance_response = self.client.get(reverse("wallet-balance"), HTTP_X_FLEET_NAME=self.fleet.name)
        self.assertEqual(balance_response.status_code, status.HTTP_200_OK)
        self.assertEqual(balance_response.data["fleet_rating"], "-0.1")

    def test_withdrawal_fails_when_amount_is_below_minimum(self):
        self._fund_accounts(reserve_amount="100.00", available_amount="40.00")

        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "0.49"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-min",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-min",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Minimum withdrawal amount", str(response.data))

    def test_withdrawal_fails_when_amount_is_above_maximum(self):
        self._fund_accounts(reserve_amount="1000.00", available_amount="1000.00")

        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "499.51"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-max",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-max",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Maximum withdrawal amount", str(response.data))

    def test_withdrawal_fails_when_fleet_reserve_is_too_low(self):
        self._fund_accounts(reserve_amount="18.00", available_amount="40.00")

        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "19.00"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-3",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-3",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fleet reserve", response.data["detail"])

    def test_withdrawal_fails_when_bank_account_is_missing_beneficiary_inn(self):
        incomplete_bank_account = BankAccount.objects.create(
            user=self.driver,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000000099",
            beneficiary_name="Driver Missing Inn",
            beneficiary_inn="",
        )
        self._fund_accounts(reserve_amount="100.00", available_amount="100.00")

        response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": incomplete_bank_account.id, "amount": "10.00"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-missing-inn",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-missing-inn",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("beneficiary ID number", response.data["detail"])

    def test_duplicate_withdrawal_returns_existing_request_without_second_debit(self):
        self._fund_accounts(reserve_amount="100.00", available_amount="100.00")

        first = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "10.00"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-duplicate-1",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-duplicate-1",
        )
        second = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "10.00"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-duplicate-2",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-duplicate-2",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(
            WithdrawalRequest.objects.filter(
                user=self.driver,
                bank_account=self.driver_bank_account,
                amount=Decimal("10.00"),
            ).count(),
            1,
        )
        driver_account = LedgerAccount.objects.get(
            user=self.driver,
            account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
        )
        self.assertEqual(get_account_balance(driver_account), Decimal("89.50"))

    def test_multiple_withdrawals_are_allowed_without_cooldown(self):
        self._fund_accounts(reserve_amount="100.00", available_amount="100.00")

        first = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "10.00"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-cooldown-1",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-cooldown-1",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_bank_account.id, "amount": "5.00"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="driver-withdrawal-cooldown-2",
            HTTP_X_REQUEST_ID="req-driver-withdrawal-cooldown-2",
        )

        self.assertEqual(second.status_code, status.HTTP_201_CREATED)


class WalletFleetRatingTests(APITestCase):
    def test_rating_starts_at_zero_and_grows_by_point_one_every_five_thousand_completed_withdrawals(self):
        self.assertEqual(
            _fleet_rating_from_completed_withdrawals(completed_withdrawals_count=0),
            "0.0",
        )
        self.assertEqual(
            _fleet_rating_from_completed_withdrawals(completed_withdrawals_count=4999),
            "0.0",
        )
        self.assertEqual(
            _fleet_rating_from_completed_withdrawals(completed_withdrawals_count=5000),
            "0.1",
        )
        self.assertEqual(
            _fleet_rating_from_completed_withdrawals(completed_withdrawals_count=10000),
            "0.2",
        )
        self.assertEqual(
            _fleet_rating_from_completed_withdrawals(completed_withdrawals_count=0, penalty_count=1),
            "-0.1",
        )

    def test_driver_balance_includes_fleet_rating(self):
        owner = User.objects.create_user(username="fleet_rating_owner", password="pass1234")
        driver = User.objects.create_user(
            username="fleet_rating_driver",
            password="pass1234",
            first_name="Demo",
            last_name="Driver",
        )
        fleet = Fleet.objects.create(name="Rating Fleet")
        FleetPhoneBinding.objects.create(
            fleet=fleet,
            user=owner,
            phone_number="598955561",
            role=FleetPhoneBinding.Role.OWNER,
            is_active=True,
        )
        FleetPhoneBinding.objects.create(
            fleet=fleet,
            user=driver,
            phone_number="598955562",
            role=FleetPhoneBinding.Role.DRIVER,
            is_active=True,
        )
        DriverFleetMembership.objects.create(
            user=driver,
            fleet=fleet,
            yandex_external_driver_id="drv-rating-1",
            is_active=True,
        )
        self.client.force_authenticate(driver)

        response = self.client.get(reverse("wallet-balance"), HTTP_X_FLEET_NAME=fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fleet_rating"], "0.0")
        self.assertEqual(response.data["fleet_completed_withdrawals"], 0)
        self.assertEqual(response.data["driver_name"], "Demo Driver")
        self.assertEqual(response.data["driver_level"], 1)
        self.assertEqual(response.data["driver_reward"], "No reward yet")


class WithdrawalListScopeTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="withdraw_list_owner", password="pass1234")
        self.operator = User.objects.create_user(username="withdraw_list_operator", password="pass1234")
        self.driver_one = User.objects.create_user(username="withdraw_list_driver_one", password="pass1234")
        self.driver_two = User.objects.create_user(username="withdraw_list_driver_two", password="pass1234")
        self.fleet = Fleet.objects.create(name="Withdrawal List Fleet")
        for user, role, phone in [
            (self.owner, FleetPhoneBinding.Role.OWNER, "598966600"),
            (self.operator, FleetPhoneBinding.Role.OPERATOR, "598966601"),
            (self.driver_one, FleetPhoneBinding.Role.DRIVER, "598966602"),
            (self.driver_two, FleetPhoneBinding.Role.DRIVER, "598966603"),
        ]:
            FleetPhoneBinding.objects.create(
                fleet=self.fleet,
                user=user,
                phone_number=phone,
                role=role,
                is_active=True,
            )

        self.driver_one_bank = BankAccount.objects.create(
            user=self.driver_one,
            bank_name="Bank of Georgia",
            account_number="GE64BG00000000002001",
            beneficiary_name="Driver One",
            beneficiary_inn="01010101010",
        )
        self.driver_two_bank = BankAccount.objects.create(
            user=self.driver_two,
            bank_name="TBC Bank",
            account_number="GE64TB00000000002002",
            beneficiary_name="Driver Two",
            beneficiary_inn="02020202020",
        )
        self.driver_one_withdrawal = WithdrawalRequest.objects.create(
            user=self.driver_one,
            wallet=Wallet.objects.get_or_create(user=self.driver_one)[0],
            fleet=self.fleet,
            bank_account=self.driver_one_bank,
            amount=Decimal("10.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PENDING,
        )
        self.driver_two_withdrawal = WithdrawalRequest.objects.create(
            user=self.driver_two,
            wallet=Wallet.objects.get_or_create(user=self.driver_two)[0],
            fleet=self.fleet,
            bank_account=self.driver_two_bank,
            amount=Decimal("12.00"),
            fee_amount=Decimal("2.00"),
            currency="GEL",
            status=WithdrawalRequest.Status.PROCESSING,
        )

    def test_operator_can_list_fleet_withdrawals(self):
        self.client.force_authenticate(self.operator)
        response = self.client.get(reverse("withdrawal-list"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data}
        self.assertEqual(ids, {self.driver_one_withdrawal.id, self.driver_two_withdrawal.id})
        names = {item["driver_name"] for item in response.data}
        self.assertEqual(names, {"withdraw_list_driver_one", "withdraw_list_driver_two"})

    def test_driver_only_sees_own_withdrawals(self):
        self.client.force_authenticate(self.driver_one)
        response = self.client.get(reverse("withdrawal-list"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data]
        self.assertEqual(ids, [self.driver_one_withdrawal.id])
        self.assertEqual(response.data[0]["driver_name"], "withdraw_list_driver_one")

    def test_operator_can_see_withdrawal_created_by_driver_via_api(self):
        DriverFleetMembership.objects.create(
            user=self.driver_one,
            fleet=self.fleet,
            yandex_external_driver_id="withdraw-list-driver-one",
            is_active=True,
        )
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("100.00"),
            created_by=self.owner,
        )
        record_driver_earning_allocation(
            user=self.driver_one,
            fleet=self.fleet,
            amount=Decimal("40.00"),
            created_by=self.owner,
        )

        self.client.force_authenticate(self.driver_one)
        create_response = self.client.post(
            reverse("withdrawal-create"),
            data={"bank_account_id": self.driver_one_bank.id, "amount": "18.00", "note": "operator visibility check"},
            format="json",
            HTTP_X_FLEET_NAME=self.fleet.name,
            HTTP_IDEMPOTENCY_KEY="withdrawal-list-driver-api",
            HTTP_X_REQUEST_ID="req-withdrawal-list-driver-api",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_id = create_response.data["id"]

        self.client.force_authenticate(self.operator)
        response = self.client.get(reverse("withdrawal-list"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data}
        self.assertIn(created_id, ids)
