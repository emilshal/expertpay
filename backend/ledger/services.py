from decimal import Decimal

from django.db.models import Sum

from .models import LedgerAccount, LedgerEntry


def get_or_create_user_ledger_account(user, currency="GEL"):
    account, _ = LedgerAccount.objects.get_or_create(
        user=user,
        defaults={"account_type": LedgerAccount.AccountType.USER_WALLET, "name": "main", "currency": currency},
    )
    return account


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
