from decimal import Decimal

from django.conf import settings
from django.db import transaction

from ledger.services import record_fleet_reserve_deposit
from ledger.models import LedgerAccount
from ledger.services import (
    create_ledger_entry,
    ensure_opening_entry,
    get_account_balance,
    get_or_create_user_ledger_account,
)

from .models import Deposit, Wallet


def build_wallet_deposit_reference(user) -> str:
    prefix = (getattr(settings, "BOG_DEPOSIT_REFERENCE_PREFIX", "EXP") or "EXP").strip().upper()
    return f"{prefix}-{int(user.id):06d}"


def build_fleet_deposit_reference(fleet) -> str:
    prefix = (getattr(settings, "BOG_DEPOSIT_REFERENCE_PREFIX", "EXP") or "EXP").strip().upper()
    return f"{prefix}-FLT-{int(fleet.id):06d}"


def complete_bank_deposit(
    *,
    user,
    provider: str,
    provider_transaction_id: str,
    amount: Decimal,
    currency: str,
    reference_code: str,
    incoming_transfer,
    raw_payload: dict,
    note: str,
    payer_name: str,
    payer_inn: str,
    payer_account_number: str,
):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    ledger_account = get_or_create_user_ledger_account(user, currency)
    ensure_opening_entry(ledger_account, wallet.balance, created_by=user)

    with transaction.atomic():
        locked_wallet = Wallet.objects.select_for_update().get(id=wallet.id)
        locked_account = LedgerAccount.objects.select_for_update().get(id=ledger_account.id)
        deposit, created = Deposit.objects.get_or_create(
            provider_transaction_id=provider_transaction_id,
            defaults={
                "user": user,
                "wallet": locked_wallet,
                "incoming_transfer": incoming_transfer,
                "amount": amount,
                "currency": currency,
                "status": Deposit.Status.COMPLETED,
                "reference_code": reference_code,
                "provider": provider,
                "payer_name": payer_name,
                "payer_inn": payer_inn,
                "payer_account_number": payer_account_number,
                "note": note,
                "raw_payload": raw_payload,
            },
        )
        if created:
            create_ledger_entry(
                account=locked_account,
                amount=amount,
                entry_type="bank_deposit",
                created_by=user,
                reference_type="deposit",
                reference_id=str(deposit.id),
                metadata={
                    "description": f"Bank deposit {provider_transaction_id}",
                    "reference_code": reference_code,
                },
                idempotency_key=f"{provider}:deposit:{provider_transaction_id}",
            )
            locked_wallet.balance = get_account_balance(locked_account, locked_wallet.currency)
            locked_wallet.save(update_fields=["balance", "updated_at"])

        return deposit, created


def complete_fleet_bank_deposit(
    *,
    fleet,
    user,
    provider: str,
    provider_transaction_id: str,
    amount: Decimal,
    currency: str,
    reference_code: str,
    incoming_transfer,
    raw_payload: dict,
    note: str,
    payer_name: str,
    payer_inn: str,
    payer_account_number: str,
):
    wallet = Wallet.objects.filter(user=user).first() if user else None
    with transaction.atomic():
        deposit, created = Deposit.objects.get_or_create(
            provider_transaction_id=provider_transaction_id,
            defaults={
                "fleet": fleet,
                "user": user,
                "wallet": wallet,
                "incoming_transfer": incoming_transfer,
                "amount": amount,
                "currency": currency,
                "status": Deposit.Status.COMPLETED,
                "reference_code": reference_code,
                "provider": provider,
                "payer_name": payer_name,
                "payer_inn": payer_inn,
                "payer_account_number": payer_account_number,
                "note": note,
                "raw_payload": raw_payload,
            },
        )
        if created:
            record_fleet_reserve_deposit(
                fleet=fleet,
                amount=amount,
                created_by=user,
                currency=currency,
                reference_type="deposit",
                reference_id=str(deposit.id),
                metadata={
                    "description": f"Fleet deposit {provider_transaction_id}",
                    "reference_code": reference_code,
                    "provider": provider,
                },
            )
        return deposit, created
