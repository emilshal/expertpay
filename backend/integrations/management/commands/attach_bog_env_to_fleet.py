from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Fleet, FleetPhoneBinding
from integrations.models import ProviderConnection


class Command(BaseCommand):
    help = "Attach the Bank of Georgia Business Online credentials from env to an existing fleet."

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
                "BOG_CLIENT_ID": settings.BOG_CLIENT_ID,
                "BOG_CLIENT_SECRET": settings.BOG_CLIENT_SECRET,
                "BOG_BASE_URL": settings.BOG_BASE_URL,
                "BOG_TOKEN_URL": settings.BOG_TOKEN_URL,
                "BOG_SOURCE_ACCOUNT_NUMBER": settings.BOG_SOURCE_ACCOUNT_NUMBER,
            }.items()
            if not value
        ]
        if missing:
            raise CommandError(f"Missing env vars: {', '.join(missing)}")

        connection, created = ProviderConnection.objects.update_or_create(
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            external_account_id=f"bog-{fleet.id}",
            defaults={
                "user": owner_user,
                "fleet": fleet,
                "status": "active",
                "config": {
                    "mode": "live",
                    "source_account_number": settings.BOG_SOURCE_ACCOUNT_NUMBER,
                    "fee_account_number": settings.BOG_FEE_ACCOUNT_NUMBER,
                },
            },
        )

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} BoG connection {connection.external_account_id} for fleet {fleet.name}."
            )
        )
