from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import DriverFleetMembership, Fleet, FleetPhoneBinding
from integrations.models import ProviderConnection
from integrations.services import find_yandex_driver_by_phone
from ledger.services import (
    create_ledger_entry,
    get_account_balance,
    get_or_create_driver_available_account,
)


class Command(BaseCommand):
    help = "Import one driver's current Yandex balance snapshot into ExpertPay."

    def add_arguments(self, parser):
        parser.add_argument("fleet_name")
        parser.add_argument("phone_number")

    def handle(self, *args, **options):
        fleet_name = " ".join(options["fleet_name"].strip().split())
        phone_number = "".join(ch for ch in options["phone_number"] if ch.isdigit())
        if phone_number.startswith("995") and len(phone_number) == 12:
            phone_number = phone_number[3:]

        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            raise CommandError(f"Fleet not found: {fleet_name}")

        connection = (
            ProviderConnection.objects.filter(
                fleet=fleet,
                provider=ProviderConnection.Provider.YANDEX,
                status="active",
            )
            .order_by("-created_at", "id")
            .first()
        )
        if connection is None:
            raise CommandError(f"Fleet {fleet.name} does not have an active Yandex connection.")

        binding = (
            FleetPhoneBinding.objects.filter(
                fleet=fleet,
                phone_number=phone_number,
                role=FleetPhoneBinding.Role.DRIVER,
                is_active=True,
                user__is_active=True,
            )
            .select_related("user")
            .first()
        )
        if binding is None:
            raise CommandError(f"No active driver binding for {phone_number} in fleet {fleet.name}.")

        lookup = find_yandex_driver_by_phone(connection=connection, phone_number=phone_number)
        if not lookup["ok"]:
            raise CommandError(lookup.get("detail", "Yandex lookup failed."))
        matches = lookup.get("matches", [])
        if len(matches) != 1:
            raise CommandError(f"Expected exactly one Yandex match for {phone_number}; found {len(matches)}.")

        yandex_driver = matches[0]
        yandex_balance = Decimal(str(yandex_driver["current_balance"]))
        currency = yandex_driver["balance_currency"] or "GEL"

        with transaction.atomic():
            membership, _created = DriverFleetMembership.objects.select_for_update().get_or_create(
                user=binding.user,
                defaults={"fleet": fleet, "is_active": True},
            )
            membership.fleet = fleet
            membership.yandex_external_driver_id = yandex_driver["external_driver_id"]
            membership.yandex_display_name = yandex_driver["display_name"]
            membership.yandex_phone_number = yandex_driver["phone_number"]
            membership.yandex_current_balance = yandex_balance
            membership.yandex_balance_currency = currency
            membership.yandex_raw = yandex_driver["raw"]
            membership.last_yandex_sync_at = timezone.now()
            membership.is_active = True
            membership.save(
                update_fields=[
                    "fleet",
                    "yandex_external_driver_id",
                    "yandex_display_name",
                    "yandex_phone_number",
                    "yandex_current_balance",
                    "yandex_balance_currency",
                    "yandex_raw",
                    "last_yandex_sync_at",
                    "is_active",
                    "updated_at",
                ]
            )

            driver_account = get_or_create_driver_available_account(binding.user, fleet=fleet, currency=currency)
            current_balance = get_account_balance(driver_account, currency)
            delta = yandex_balance - current_balance
            if delta:
                create_ledger_entry(
                    account=driver_account,
                    amount=delta,
                    entry_type="yandex_balance_snapshot_adjustment",
                    created_by=connection.user,
                    currency=currency,
                    reference_type="yandex_balance_snapshot",
                    reference_id=f"{connection.id}:{yandex_driver['external_driver_id']}",
                    metadata={
                        "fleet_id": fleet.id,
                        "connection_id": connection.id,
                        "driver_external_id": yandex_driver["external_driver_id"],
                        "previous_balance": str(current_balance),
                        "yandex_balance": str(yandex_balance),
                        "delta": str(delta),
                    },
                    idempotency_key=f"yandex-snapshot:{connection.id}:{yandex_driver['external_driver_id']}:{yandex_balance}",
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {fleet.name} driver {phone_number}: "
                f"{yandex_driver['display_name']} balance {yandex_balance} {currency} "
                f"(delta {delta})."
            )
        )
