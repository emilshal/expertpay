from django.core.management.base import BaseCommand

from integrations.models import ProviderConnection
from integrations.services import sync_open_bog_payouts


class Command(BaseCommand):
    help = "Poll open Bank of Georgia payouts and update withdrawal statuses."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="Optional owner user id for a single BoG connection.")

    def handle(self, *args, **options):
        queryset = ProviderConnection.objects.filter(provider=ProviderConnection.Provider.BANK_OF_GEORGIA)
        user_id = options.get("user_id")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        checked_connections = 0
        checked_payouts = 0
        updated_payouts = 0
        error_count = 0

        for connection in queryset.order_by("id"):
            checked_connections += 1
            result = sync_open_bog_payouts(connection=connection)
            checked_payouts += result["checked_count"]
            updated_payouts += result["updated_count"]
            error_count += result["error_count"]
            self.stdout.write(
                self.style.NOTICE(
                    f"BoG connection {connection.id}: checked={result['checked_count']} "
                    f"updated={result['updated_count']} errors={result['error_count']}"
                )
            )

        summary = (
            f"Completed BoG payout sync for {checked_connections} connection(s); "
            f"checked {checked_payouts} payout(s), updated {updated_payouts}, errors {error_count}."
        )
        self.stdout.write(self.style.SUCCESS(summary))
