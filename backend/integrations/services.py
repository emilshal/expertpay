from decimal import Decimal
import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ledger.services import (
    create_ledger_entry,
    ensure_opening_entry,
    get_account_balance,
    get_or_create_user_ledger_account,
)
from wallet.models import Wallet, WithdrawalRequest

from .models import BankSimulatorPayout, ExternalEvent, ProviderConnection


def _event_amount_for_mode(mode: str) -> Decimal:
    if mode == "spiky":
        return Decimal(random.choice(["8.25", "12.40", "31.50", "60.00", "95.75"]))
    if mode == "adjustment":
        return Decimal(random.choice(["-4.00", "-1.25", "2.10", "5.00"]))
    return Decimal(random.choice(["6.50", "8.30", "9.10", "11.75", "14.00"]))


def generate_simulated_events(*, connection: ProviderConnection, mode: str, count: int):
    now = timezone.now()
    created = []
    for index in range(count):
        amount = _event_amount_for_mode(mode)
        event_time = now - timedelta(minutes=index * random.randint(1, 12))
        external_id = f"yandex-{connection.id}-{int(event_time.timestamp())}-{index}"
        payload = {
            "external_id": external_id,
            "driver_id": f"drv-{1000 + index}",
            "fleet": connection.external_account_id,
            "event_time": event_time.isoformat(),
            "currency": "GEL",
            "gross_amount": str(amount),
            "net_amount": str(amount),
            "event_type": "earning",
        }

        if mode == "duplicates" and index % 3 == 0 and created:
            payload["external_id"] = created[-1].external_id
            external_id = payload["external_id"]

        event, _ = ExternalEvent.objects.get_or_create(
            connection=connection,
            external_id=external_id,
            defaults={"event_type": "earning", "payload": payload, "processed": False},
        )
        created.append(event)

    if mode == "out_of_order":
        random.shuffle(created)

    return created


def import_unprocessed_events(*, connection: ProviderConnection):
    wallet, _ = Wallet.objects.get_or_create(user=connection.user)
    ledger_account = get_or_create_user_ledger_account(connection.user, wallet.currency)
    ensure_opening_entry(ledger_account, wallet.balance, created_by=connection.user)

    events = list(connection.events.filter(processed=False).order_by("created_at", "id"))
    imported = 0
    imported_total = Decimal("0.00")

    with transaction.atomic():
        for event in events:
            net = Decimal(str(event.payload.get("net_amount", "0")))
            if net == Decimal("0.00"):
                event.processed = True
                event.save(update_fields=["processed"])
                continue

            idempotency_key = f"yandex:{connection.id}:{event.external_id}"
            create_ledger_entry(
                account=ledger_account,
                amount=net,
                entry_type="yandex_earning",
                created_by=connection.user,
                reference_type="external_event",
                reference_id=str(event.id),
                idempotency_key=idempotency_key,
                metadata={
                    "description": f"Yandex import {event.external_id}",
                    "external_event_id": event.external_id,
                },
            )
            imported += 1
            imported_total += net
            event.processed = True
            event.save(update_fields=["processed"])

        wallet.balance = wallet.balance + imported_total
        wallet.save(update_fields=["balance", "updated_at"])

    return {"imported_count": imported, "imported_total": str(imported_total)}


def reconciliation_summary(*, connection: ProviderConnection):
    imported_events = connection.events.filter(processed=True)
    imported_total = Decimal("0.00")
    for event in imported_events:
        imported_total += Decimal(str(event.payload.get("net_amount", "0")))

    wallet, _ = Wallet.objects.get_or_create(user=connection.user)
    ledger_account = get_or_create_user_ledger_account(connection.user, wallet.currency)
    yandex_ledger_total = Decimal("0.00")
    for entry in ledger_account.entries.filter(entry_type="yandex_earning"):
        yandex_ledger_total += Decimal(str(entry.amount))

    delta = imported_total - yandex_ledger_total
    return {
        "imported_events": imported_events.count(),
        "imported_total": str(imported_total),
        "ledger_total": str(yandex_ledger_total),
        "delta": str(delta),
        "status": "OK" if delta == Decimal("0.00") else "MISMATCH",
    }


def submit_withdrawal_to_bank_simulator(*, connection: ProviderConnection, withdrawal: WithdrawalRequest):
    payout, created = BankSimulatorPayout.objects.get_or_create(
        withdrawal=withdrawal,
        defaults={
            "connection": connection,
            "provider_payout_id": f"banksim-{connection.id}-{withdrawal.id}",
            "status": BankSimulatorPayout.Status.ACCEPTED,
            "metadata": {"source": "bank_simulator"},
        },
    )

    # Ensure payout is bound to the same owner connection.
    if payout.connection_id != connection.id:
        raise ValueError("Withdrawal payout belongs to another simulator connection.")

    if withdrawal.status == WithdrawalRequest.Status.PENDING:
        withdrawal.status = WithdrawalRequest.Status.PROCESSING
        withdrawal.save(update_fields=["status"])

    return payout, created


def apply_bank_simulator_status_update(*, payout: BankSimulatorPayout, target_status: str, failure_reason: str = ""):
    with transaction.atomic():
        locked_payout = BankSimulatorPayout.objects.select_for_update().select_related(
            "withdrawal", "withdrawal__wallet", "withdrawal__wallet__user"
        ).get(id=payout.id)

        withdrawal = locked_payout.withdrawal
        if withdrawal.status == WithdrawalRequest.Status.COMPLETED and target_status in {
            BankSimulatorPayout.Status.FAILED,
            BankSimulatorPayout.Status.REVERSED,
        }:
            raise ValueError("Cannot fail or reverse a completed payout.")

        if locked_payout.status == target_status:
            return locked_payout

        locked_payout.status = target_status
        locked_payout.failure_reason = failure_reason
        locked_payout.save(update_fields=["status", "failure_reason", "updated_at"])

        if target_status in {
            BankSimulatorPayout.Status.ACCEPTED,
            BankSimulatorPayout.Status.PROCESSING,
        }:
            if withdrawal.status not in {
                WithdrawalRequest.Status.COMPLETED,
                WithdrawalRequest.Status.FAILED,
            }:
                withdrawal.status = WithdrawalRequest.Status.PROCESSING
                withdrawal.save(update_fields=["status"])
            return locked_payout

        if target_status == BankSimulatorPayout.Status.SETTLED:
            withdrawal.status = WithdrawalRequest.Status.COMPLETED
            withdrawal.save(update_fields=["status"])
            return locked_payout

        if target_status in {BankSimulatorPayout.Status.FAILED, BankSimulatorPayout.Status.REVERSED}:
            if withdrawal.status != WithdrawalRequest.Status.FAILED:
                wallet = withdrawal.wallet
                ledger_account = get_or_create_user_ledger_account(wallet.user, wallet.currency)
                create_ledger_entry(
                    account=ledger_account,
                    amount=withdrawal.amount,
                    entry_type="withdrawal_reversal",
                    created_by=wallet.user,
                    reference_type="withdrawal",
                    reference_id=str(withdrawal.id),
                    metadata={
                        "description": "Bank simulator marked payout failed/reversed",
                        "provider_payout_id": locked_payout.provider_payout_id,
                    },
                    idempotency_key=f"banksim:reversal:{locked_payout.id}",
                )
                wallet.balance = wallet.balance + withdrawal.amount
                wallet.save(update_fields=["balance", "updated_at"])
                withdrawal.status = WithdrawalRequest.Status.FAILED
                withdrawal.save(update_fields=["status"])
            return locked_payout

        return locked_payout


def build_reconciliation_report(*, user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    ledger_account = get_or_create_user_ledger_account(user, wallet.currency)
    ensure_opening_entry(ledger_account, wallet.balance, created_by=user)
    ledger_balance = get_account_balance(ledger_account, wallet.currency)

    yandex_connection = ProviderConnection.objects.filter(
        user=user, provider=ProviderConnection.Provider.YANDEX
    ).first()
    if yandex_connection:
        yandex = reconciliation_summary(connection=yandex_connection)
    else:
        yandex = {
            "imported_events": 0,
            "imported_total": "0.00",
            "ledger_total": "0.00",
            "delta": "0.00",
            "status": "OK",
        }

    withdrawals = WithdrawalRequest.objects.filter(user=user)
    withdrawals_total = withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    withdrawals_completed = (
        withdrawals.filter(status=WithdrawalRequest.Status.COMPLETED).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    withdrawals_pending = (
        withdrawals.filter(status__in=[WithdrawalRequest.Status.PENDING, WithdrawalRequest.Status.PROCESSING]).aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )
    withdrawals_failed = (
        withdrawals.filter(status=WithdrawalRequest.Status.FAILED).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    payouts = BankSimulatorPayout.objects.filter(withdrawal__user=user)
    payouts_by_status = {
        status_key: str(
            payouts.filter(status=status_key).aggregate(total=Sum("withdrawal__amount"))["total"] or Decimal("0.00")
        )
        for status_key in [
            BankSimulatorPayout.Status.ACCEPTED,
            BankSimulatorPayout.Status.PROCESSING,
            BankSimulatorPayout.Status.SETTLED,
            BankSimulatorPayout.Status.FAILED,
            BankSimulatorPayout.Status.REVERSED,
        ]
    }

    wallet_delta = ledger_balance - wallet.balance

    return {
        "currency": wallet.currency,
        "wallet": {
            "wallet_balance": str(wallet.balance),
            "ledger_balance": str(ledger_balance),
            "delta": str(wallet_delta),
            "status": "OK" if wallet_delta == Decimal("0.00") else "MISMATCH",
        },
        "yandex": yandex,
        "withdrawals": {
            "count": withdrawals.count(),
            "total": str(withdrawals_total),
            "completed_total": str(withdrawals_completed),
            "pending_total": str(withdrawals_pending),
            "failed_total": str(withdrawals_failed),
        },
        "bank_simulator": {
            "count": payouts.count(),
            "totals_by_status": payouts_by_status,
        },
        "generated_at": timezone.now().isoformat(),
        "overall_status": "OK"
        if wallet_delta == Decimal("0.00") and yandex.get("status") == "OK"
        else "MISMATCH",
    }
