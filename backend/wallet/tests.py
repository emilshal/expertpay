from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import DriverFleetMembership, Fleet, FleetPhoneBinding
from integrations.models import ProviderConnection
from ledger.models import LedgerAccount, LedgerEntry
from ledger.services import (
    get_account_balance,
    get_or_create_payout_clearing_account,
    get_or_create_platform_fee_account,
    record_driver_earning_allocation,
    record_fleet_reserve_deposit,
)

from .models import BankAccount, Deposit, IncomingBankTransfer, Wallet, WithdrawalRequest
from .services import build_fleet_deposit_reference


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
        self.bound_user = User.objects.create_user(username="wallet_bound_user", password="pass1234")
        self.fleet = Fleet.objects.create(name="Wallet Auth Fleet")
        FleetPhoneBinding.objects.create(
            fleet=self.fleet,
            user=self.bound_user,
            phone_number="598900010",
            role=FleetPhoneBinding.Role.OPERATOR,
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
            user=self.bound_user,
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

        response = self.client.get(reverse("owner-fleet-summary"), HTTP_X_FLEET_NAME=self.fleet.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["fleet_name"], self.fleet.name)
        self.assertEqual(response.data["reserve_balance"], "200.00")
        self.assertEqual(response.data["total_funded"], "200.00")
        self.assertEqual(response.data["total_withdrawn"], "50.00")
        self.assertEqual(response.data["total_fees"], "6.00")
        self.assertEqual(response.data["pending_payouts_count"], 2)
        self.assertEqual(response.data["pending_payouts_total"], "50.00")
        self.assertEqual(response.data["active_drivers_count"], 2)
        pending_ids = {item["id"] for item in response.data["pending_payouts"]}
        self.assertIn(pending_withdrawal.id, pending_ids)
        pending_names = {item["driver_name"] for item in response.data["pending_payouts"]}
        self.assertIn("Nika Gelashvili", pending_names)

    def test_driver_cannot_access_owner_summary(self):
        self.client.force_authenticate(self.driver_one)
        response = self.client.get(reverse("owner-fleet-summary"), HTTP_X_FLEET_NAME=self.fleet.name)
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
        self.assertEqual(Decimal(response.data["fee_amount"]), Decimal("2.00"))
        withdrawal = WithdrawalRequest.objects.get(id=response.data["id"])
        self.assertEqual(withdrawal.fleet_id, self.fleet.id)
        self.assertEqual(withdrawal.fee_amount, Decimal("2.00"))

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

        self.assertEqual(get_account_balance(driver_account), Decimal("10.00"))
        self.assertEqual(get_account_balance(reserve_account), Decimal("68.00"))
        self.assertEqual(get_account_balance(payout_clearing), Decimal("30.00"))
        self.assertEqual(get_account_balance(fee_account), Decimal("2.00"))

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

    def test_withdrawal_fails_when_fleet_reserve_is_too_low(self):
        self._fund_accounts(reserve_amount="20.00", available_amount="40.00")

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
