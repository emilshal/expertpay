from decimal import Decimal
import random
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ledger.services import create_ledger_entry, ensure_opening_entry, get_or_create_user_ledger_account
from wallet.models import Wallet

from .models import ExternalEvent, ProviderConnection


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
