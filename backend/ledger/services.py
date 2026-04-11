from decimal import Decimal

from django.db.models import Sum

from .models import LedgerAccount, LedgerEntry


def get_or_create_user_ledger_account(user, currency="GEL"):
    account, _ = LedgerAccount.objects.get_or_create(
        user=user,
        account_type=LedgerAccount.AccountType.USER_WALLET,
        currency=currency,
        defaults={"name": "main"},
    )
    return account


def get_or_create_driver_available_account(user, *, fleet, currency="GEL"):
    account, created = LedgerAccount.objects.get_or_create(
        user=user,
        account_type=LedgerAccount.AccountType.DRIVER_AVAILABLE,
        currency=currency,
        defaults={"fleet": fleet, "name": "available"},
    )
    if account.fleet_id != fleet.id:
        account.fleet = fleet
        account.save(update_fields=["fleet", "updated_at"])
    elif created:
        account.fleet = fleet
        account.save(update_fields=["fleet", "updated_at"])
    return account


def get_or_create_fleet_reserve_account(fleet, currency="GEL"):
    account, _ = LedgerAccount.objects.get_or_create(
        fleet=fleet,
        account_type=LedgerAccount.AccountType.FLEET_RESERVE,
        currency=currency,
        defaults={"name": "reserve"},
    )
    return account


def get_or_create_system_ledger_account(*, account_type, currency="GEL", name="main"):
    account, _ = LedgerAccount.objects.get_or_create(
        user=None,
        fleet=None,
        account_type=account_type,
        currency=currency,
        name=name,
    )
    return account


def get_or_create_treasury_account(currency="GEL"):
    return get_or_create_system_ledger_account(
        account_type=LedgerAccount.AccountType.TREASURY,
        currency=currency,
        name="bog_main",
    )


def get_or_create_platform_fee_account(currency="GEL"):
    return get_or_create_system_ledger_account(
        account_type=LedgerAccount.AccountType.PLATFORM_FEE,
        currency=currency,
        name="withdrawal_fees",
    )


def get_or_create_payout_clearing_account(currency="GEL"):
    return get_or_create_system_ledger_account(
        account_type=LedgerAccount.AccountType.PAYOUT_CLEARING,
        currency=currency,
        name="payout_clearing",
    )


def get_account_balance(account, currency="GEL"):
    total = (
        LedgerEntry.objects.filter(account=account, currency=currency).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    return total


def ensure_opening_entry(account, opening_balance, created_by=None):
    if opening_balance == Decimal("0.00"):
        return
    if LedgerEntry.objects.filter(account=account).exists():
        return
    LedgerEntry.objects.create(
        account=account,
        amount=opening_balance,
        currency=account.currency,
        entry_type="opening_balance",
        reference_type="wallet",
        reference_id=str(account.user_id or ""),
        created_by=created_by,
        metadata={"source": "wallet_seed"},
    )


def create_ledger_entry(
    *,
    account,
    amount,
    entry_type,
    created_by=None,
    currency=None,
    reference_type="",
    reference_id="",
    metadata=None,
    idempotency_key=None,
):
    return LedgerEntry.objects.create(
        account=account,
        amount=amount,
        currency=currency or account.currency,
        entry_type=entry_type,
        created_by=created_by,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=metadata or {},
        idempotency_key=idempotency_key,
    )


def record_fleet_reserve_deposit(
    *,
    fleet,
    amount,
    created_by=None,
    currency="GEL",
    reference_type="fleet_deposit",
    reference_id="",
    metadata=None,
):
    treasury_account = get_or_create_treasury_account(currency=currency)
    fleet_reserve_account = get_or_create_fleet_reserve_account(fleet, currency=currency)
    entry_metadata = {
        **(metadata or {}),
        "fleet_id": fleet.id,
    }

    create_ledger_entry(
        account=treasury_account,
        amount=amount,
        entry_type="fleet_reserve_deposit_treasury_credit",
        created_by=created_by,
        currency=currency,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=entry_metadata,
    )
    create_ledger_entry(
        account=fleet_reserve_account,
        amount=amount,
        entry_type="fleet_reserve_deposit_credit",
        created_by=created_by,
        currency=currency,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=entry_metadata,
    )
    return {
        "treasury_account": treasury_account,
        "fleet_reserve_account": fleet_reserve_account,
    }


def record_driver_earning_allocation(
    *,
    user,
    fleet,
    amount,
    created_by=None,
    currency="GEL",
    reference_type="driver_earning",
    reference_id="",
    metadata=None,
):
    driver_account = get_or_create_driver_available_account(user, fleet=fleet, currency=currency)
    create_ledger_entry(
        account=driver_account,
        amount=amount,
        entry_type="driver_earning_allocation",
        created_by=created_by,
        currency=currency,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=metadata or {},
    )
    return driver_account


def record_platform_fee_charge(
    *,
    fleet,
    amount,
    created_by=None,
    currency="GEL",
    reference_type="platform_fee",
    reference_id="",
    metadata=None,
):
    fleet_reserve_account = get_or_create_fleet_reserve_account(fleet, currency=currency)
    platform_fee_account = get_or_create_platform_fee_account(currency=currency)
    entry_metadata = metadata or {}

    create_ledger_entry(
        account=fleet_reserve_account,
        amount=-amount,
        entry_type="platform_fee_debit_from_fleet_reserve",
        created_by=created_by,
        currency=currency,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=entry_metadata,
    )
    create_ledger_entry(
        account=platform_fee_account,
        amount=amount,
        entry_type="platform_fee_credit",
        created_by=created_by,
        currency=currency,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=entry_metadata,
    )
    return {
        "fleet_reserve_account": fleet_reserve_account,
        "platform_fee_account": platform_fee_account,
    }


def record_driver_withdrawal_hold(
    *,
    withdrawal,
    fleet,
    user,
    amount,
    fee_amount,
    created_by=None,
    currency="GEL",
    metadata=None,
):
    driver_account = get_or_create_driver_available_account(user, fleet=fleet, currency=currency)
    fleet_reserve_account = get_or_create_fleet_reserve_account(fleet, currency=currency)
    payout_clearing_account = get_or_create_payout_clearing_account(currency=currency)
    platform_fee_account = get_or_create_platform_fee_account(currency=currency)
    entry_metadata = metadata or {}

    create_ledger_entry(
        account=driver_account,
        amount=-(amount + fee_amount),
        entry_type="driver_withdrawal_hold",
        created_by=created_by,
        currency=currency,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        metadata=entry_metadata,
        idempotency_key=f"withdrawal:{withdrawal.id}:driver_hold",
    )
    create_ledger_entry(
        account=fleet_reserve_account,
        amount=-amount,
        entry_type="fleet_reserve_withdrawal_hold",
        created_by=created_by,
        currency=currency,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        metadata=entry_metadata,
        idempotency_key=f"withdrawal:{withdrawal.id}:fleet_hold",
    )
    create_ledger_entry(
        account=payout_clearing_account,
        amount=amount,
        entry_type="withdrawal_payout_clearing_credit",
        created_by=created_by,
        currency=currency,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        metadata=entry_metadata,
        idempotency_key=f"withdrawal:{withdrawal.id}:payout_clearing",
    )
    if fee_amount > Decimal("0.00"):
        create_ledger_entry(
            account=platform_fee_account,
            amount=fee_amount,
            entry_type="withdrawal_platform_fee_credit",
            created_by=created_by,
            currency=currency,
            reference_type="withdrawal",
            reference_id=str(withdrawal.id),
            metadata=entry_metadata,
            idempotency_key=f"withdrawal:{withdrawal.id}:fee_credit",
        )


def reverse_driver_withdrawal_hold(
    *,
    withdrawal,
    fleet,
    user,
    amount,
    fee_amount,
    created_by=None,
    currency="GEL",
    reason="",
):
    driver_account = get_or_create_driver_available_account(user, fleet=fleet, currency=currency)
    fleet_reserve_account = get_or_create_fleet_reserve_account(fleet, currency=currency)
    payout_clearing_account = get_or_create_payout_clearing_account(currency=currency)
    platform_fee_account = get_or_create_platform_fee_account(currency=currency)
    metadata = {"description": reason} if reason else {}

    create_ledger_entry(
        account=driver_account,
        amount=amount + fee_amount,
        entry_type="driver_withdrawal_reversal",
        created_by=created_by,
        currency=currency,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        metadata=metadata,
        idempotency_key=f"withdrawal:{withdrawal.id}:driver_reversal",
    )
    create_ledger_entry(
        account=fleet_reserve_account,
        amount=amount,
        entry_type="fleet_reserve_withdrawal_reversal",
        created_by=created_by,
        currency=currency,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        metadata=metadata,
        idempotency_key=f"withdrawal:{withdrawal.id}:fleet_reversal",
    )
    create_ledger_entry(
        account=payout_clearing_account,
        amount=-amount,
        entry_type="withdrawal_payout_clearing_reversal",
        created_by=created_by,
        currency=currency,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        metadata=metadata,
        idempotency_key=f"withdrawal:{withdrawal.id}:payout_reversal",
    )
    if fee_amount > Decimal("0.00"):
        create_ledger_entry(
            account=platform_fee_account,
            amount=-fee_amount,
            entry_type="withdrawal_platform_fee_reversal",
            created_by=created_by,
            currency=currency,
            reference_type="withdrawal",
            reference_id=str(withdrawal.id),
            metadata=metadata,
            idempotency_key=f"withdrawal:{withdrawal.id}:fee_reversal",
        )


def settle_driver_withdrawal(
    *,
    withdrawal,
    amount,
    created_by=None,
    currency="GEL",
):
    payout_clearing_account = get_or_create_payout_clearing_account(currency=currency)
    treasury_account = get_or_create_treasury_account(currency=currency)
    metadata = {"description": "Withdrawal settled"}

    create_ledger_entry(
        account=payout_clearing_account,
        amount=-amount,
        entry_type="withdrawal_payout_clearing_settlement",
        created_by=created_by,
        currency=currency,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        metadata=metadata,
        idempotency_key=f"withdrawal:{withdrawal.id}:payout_settlement",
    )
    create_ledger_entry(
        account=treasury_account,
        amount=-amount,
        entry_type="treasury_withdrawal_settlement",
        created_by=created_by,
        currency=currency,
        reference_type="withdrawal",
        reference_id=str(withdrawal.id),
        metadata=metadata,
        idempotency_key=f"withdrawal:{withdrawal.id}:treasury_settlement",
    )
