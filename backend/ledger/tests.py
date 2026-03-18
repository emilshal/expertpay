from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import DriverFleetMembership, Fleet

from .models import LedgerAccount
from .services import (
    get_account_balance,
    get_or_create_platform_fee_account,
    get_or_create_treasury_account,
    get_or_create_user_ledger_account,
    record_driver_earning_allocation,
    record_fleet_reserve_deposit,
    record_platform_fee_charge,
)


User = get_user_model()


class NewMoneyModelLedgerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner_finance", password="pass1234")
        self.driver = User.objects.create_user(username="driver_finance", password="pass1234")
        self.fleet = Fleet.objects.create(name="Ledger Refactor Fleet")

    def test_user_can_have_legacy_wallet_account_and_driver_available_account(self):
        legacy_account = get_or_create_user_ledger_account(self.driver)
        membership = DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="yandex-driver-001",
        )

        self.assertIsNotNone(membership.id)
        accounts = LedgerAccount.objects.filter(user=self.driver).order_by("account_type")
        self.assertEqual(accounts.count(), 2)
        self.assertEqual(legacy_account.account_type, LedgerAccount.AccountType.USER_WALLET)
        self.assertTrue(
            accounts.filter(
                account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
                fleet=self.fleet,
            ).exists()
        )

    def test_fleet_deposit_credits_treasury_and_fleet_reserve(self):
        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("150.00"),
            created_by=self.owner,
            reference_id="dep-1",
            metadata={"source": "test"},
        )

        treasury = get_or_create_treasury_account()
        reserve = LedgerAccount.objects.get(
            fleet=self.fleet,
            account_type=LedgerAccount.AccountType.FLEET_RESERVE,
        )

        self.assertEqual(get_account_balance(treasury), Decimal("150.00"))
        self.assertEqual(get_account_balance(reserve), Decimal("150.00"))

    def test_driver_earnings_and_platform_fee_are_tracked_in_separate_accounts(self):
        DriverFleetMembership.objects.create(
            user=self.driver,
            fleet=self.fleet,
            yandex_external_driver_id="yandex-driver-002",
        )

        record_fleet_reserve_deposit(
            fleet=self.fleet,
            amount=Decimal("80.00"),
            created_by=self.owner,
            reference_id="dep-2",
        )
        record_driver_earning_allocation(
            user=self.driver,
            fleet=self.fleet,
            amount=Decimal("25.50"),
            created_by=self.owner,
            reference_id="earning-1",
        )
        record_platform_fee_charge(
            fleet=self.fleet,
            amount=Decimal("2.00"),
            created_by=self.owner,
            reference_id="fee-1",
        )

        driver_account = LedgerAccount.objects.get(
            user=self.driver,
            account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
        )
        reserve_account = LedgerAccount.objects.get(
            fleet=self.fleet,
            account_type=LedgerAccount.AccountType.FLEET_RESERVE,
        )
        fee_account = get_or_create_platform_fee_account()

        self.assertEqual(get_account_balance(driver_account), Decimal("25.50"))
        self.assertEqual(get_account_balance(reserve_account), Decimal("78.00"))
        self.assertEqual(get_account_balance(fee_account), Decimal("2.00"))
