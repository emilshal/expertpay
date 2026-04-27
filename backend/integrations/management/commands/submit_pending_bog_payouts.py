from django.core.management.base import BaseCommand, CommandError

from accounts.models import Fleet, FleetPhoneBinding
from integrations.models import ProviderConnection
from integrations.services import submit_withdrawal_to_bog
from wallet.models import WithdrawalRequest


def _get_active_fleet_bog_connection(*, fleet):
    connection = (
        ProviderConnection.objects.filter(
            fleet=fleet,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            status="active",
        )
        .order_by("id")
        .first()
    )
    if connection is not None:
        return connection

    bindings = FleetPhoneBinding.objects.filter(
        fleet=fleet,
        is_active=True,
        user__is_active=True,
        role__in=[FleetPhoneBinding.Role.OWNER, FleetPhoneBinding.Role.ADMIN],
    ).order_by("-role", "created_at", "id")
    for fleet_binding in bindings:
        connection = (
            ProviderConnection.objects.filter(
                user=fleet_binding.user,
                provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
                status="active",
            )
            .order_by("id")
            .first()
        )
        if connection is not None:
            return connection
    return None


class Command(BaseCommand):
    help = "Submit pending fleet withdrawal requests to Bank of Georgia."

    def add_arguments(self, parser):
        parser.add_argument("--fleet-name", default="", help="Optional fleet name scope.")
        parser.add_argument("--limit", type=int, default=25, help="Maximum pending withdrawals to submit.")

    def handle(self, *args, **options):
        fleet_name = " ".join(options["fleet_name"].strip().split())
        fleet = None
        if fleet_name:
            fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
            if fleet is None:
                raise CommandError(f"Fleet not found: {fleet_name}")

        withdrawals = WithdrawalRequest.objects.filter(
            status=WithdrawalRequest.Status.PENDING,
            fleet__isnull=False,
            bog_payout__isnull=True,
        ).select_related("fleet", "bank_account", "user")
        if fleet is not None:
            withdrawals = withdrawals.filter(fleet=fleet)
        withdrawals = withdrawals.order_by("created_at", "id")[: max(int(options["limit"]), 1)]

        submitted_count = 0
        error_count = 0
        errors = []
        for withdrawal in withdrawals:
            connection = _get_active_fleet_bog_connection(fleet=withdrawal.fleet)
            if connection is None:
                error_count += 1
                errors.append(f"withdrawal={withdrawal.id}: missing BoG connection")
                continue
            try:
                payout, created = submit_withdrawal_to_bog(connection=connection, withdrawal=withdrawal)
                if created or payout.provider_unique_key:
                    submitted_count += 1
            except Exception as exc:
                error_count += 1
                errors.append(f"withdrawal={withdrawal.id}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Submitted {submitted_count} pending BoG payout(s); errors={error_count}."
            )
        )
        for error in errors[:10]:
            self.stdout.write(self.style.WARNING(error))
