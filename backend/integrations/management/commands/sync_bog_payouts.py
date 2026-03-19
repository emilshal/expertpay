from django.core.management.base import BaseCommand

from integrations.jobs import run_bog_payout_status_sync_jobs


class Command(BaseCommand):
    help = "Poll open Bank of Georgia payouts and update withdrawal statuses."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="Optional owner user id for a single BoG connection.")

    def handle(self, *args, **options):
        summary = run_bog_payout_status_sync_jobs(user_id=options.get("user_id"))
        summary = (
            f"Completed BoG payout sync for {summary['checked_connections']} connection(s); "
            f"checked {summary['checked_count']} payout(s), updated {summary['updated_count']}, "
            f"errors {summary['payout_error_count']}."
        )
        self.stdout.write(self.style.SUCCESS(summary))
