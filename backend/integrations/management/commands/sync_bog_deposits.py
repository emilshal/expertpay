from django.core.management.base import BaseCommand

from integrations.models import ProviderConnection
from integrations.services import sync_bog_deposits


class Command(BaseCommand):
    help = "Poll Bank of Georgia incoming activities and credit matched deposits."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="Optional owner user id for a single BoG connection.")
        parser.add_argument("--currency", default="GEL", help="Account currency to poll. Defaults to GEL.")

    def handle(self, *args, **options):
        queryset = ProviderConnection.objects.filter(provider=ProviderConnection.Provider.BANK_OF_GEORGIA)
        user_id = options.get("user_id")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        checked_connections = 0
        credited_total = 0
        matched_total = 0

        for connection in queryset.order_by("id"):
            checked_connections += 1
            result = sync_bog_deposits(connection=connection, currency=options["currency"])
            credited_total += result["credited_count"]
            matched_total += result["matched_count"]
            self.stdout.write(
                self.style.NOTICE(
                    f"BoG deposit sync for connection {connection.id}: "
                    f"checked={result['checked_count']} matched={result['matched_count']} "
                    f"credited={result['credited_count']} total={result['credited_total']}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {checked_connections} BoG connection(s); matched {matched_total} incoming transfers "
                f"and credited {credited_total} deposit(s)."
            )
        )
