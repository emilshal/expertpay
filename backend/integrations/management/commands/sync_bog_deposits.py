from django.core.management.base import BaseCommand

from integrations.jobs import run_bog_deposit_sync_jobs


class Command(BaseCommand):
    help = "Poll Bank of Georgia incoming activities and credit matched deposits."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="Optional owner user id for a single BoG connection.")
        parser.add_argument("--currency", default="GEL", help="Account currency to poll. Defaults to GEL.")

    def handle(self, *args, **options):
        summary = run_bog_deposit_sync_jobs(
            user_id=options.get("user_id"),
            currency=options["currency"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {summary['checked_connections']} BoG connection(s); "
                f"matched {summary['matched_count']} incoming transfers and "
                f"credited {summary['credited_count']} deposit(s) totaling {summary['credited_total']}."
            )
        )
