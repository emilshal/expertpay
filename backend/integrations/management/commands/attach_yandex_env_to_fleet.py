from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Fleet, FleetPhoneBinding
from integrations.services import create_fleet_yandex_connection


class Command(BaseCommand):
    help = "Attach the Yandex credentials from env to an existing fleet."

    def add_arguments(self, parser):
        parser.add_argument("fleet_name", help="Existing ExpertPay fleet name.")
        parser.add_argument(
            "--owner-phone",
            default="",
            help="Owner phone to use as the connection owner. Defaults to the first active owner binding.",
        )

    def handle(self, *args, **options):
        fleet_name = " ".join(options["fleet_name"].strip().split())
        fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
        if fleet is None:
            raise CommandError(f"Fleet not found: {fleet_name}")

        owner_binding = None
        owner_phone = options.get("owner_phone", "").strip()
        if owner_phone:
            owner_binding = FleetPhoneBinding.objects.filter(
                fleet=fleet,
                phone_number=owner_phone,
                role=FleetPhoneBinding.Role.OWNER,
                is_active=True,
            ).select_related("user").first()
        if owner_binding is None:
            owner_binding = (
                FleetPhoneBinding.objects.filter(
                    fleet=fleet,
                    role=FleetPhoneBinding.Role.OWNER,
                    is_active=True,
                )
                .select_related("user")
                .order_by("id")
                .first()
            )
        if owner_binding is None:
            owner_user = get_user_model().objects.filter(is_superuser=True).order_by("id").first()
            if owner_user is None:
                raise CommandError("Fleet has no active owner binding and no superuser fallback exists.")
        else:
            owner_user = owner_binding.user

        missing = [
            key
            for key, value in {
                "YANDEX_PARK_ID": settings.YANDEX_PARK_ID,
                "YANDEX_CLIENT_ID": settings.YANDEX_CLIENT_ID,
                "YANDEX_API_KEY": settings.YANDEX_API_KEY,
            }.items()
            if not value
        ]
        if missing:
            raise CommandError(f"Missing env vars: {', '.join(missing)}")

        connection, result = create_fleet_yandex_connection(
            fleet=fleet,
            user=owner_user,
            park_id=settings.YANDEX_PARK_ID,
            client_id=settings.YANDEX_CLIENT_ID,
            api_key=settings.YANDEX_API_KEY,
        )
        if connection is None:
            raise CommandError(result.get("detail", "Yandex connection failed."))

        park = result.get("park") or {}
        self.stdout.write(
            self.style.SUCCESS(
                f"Attached Yandex park {connection.external_account_id} "
                f"({park.get('name', 'unknown park')}) to fleet {fleet.name}."
            )
        )
