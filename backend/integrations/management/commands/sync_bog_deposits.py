from django.core.management.base import BaseCommand, CommandError

from integrations.jobs import run_bog_deposit_sync_jobs


class Command(BaseCommand):
    help = "Poll Bank of Georgia incoming activities and credit matched deposits."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="Optional owner user id for a single BoG connection.")
        parser.add_argument("--currency", default="GEL", help="Account currency to poll. Defaults to GEL.")
        parser.add_argument("--start-date", help="Optional YYYY-MM-DD start date for statement backfill.")
        parser.add_argument("--end-date", help="Optional YYYY-MM-DD end date for statement backfill.")

    def handle(self, *args, **options):
        use_statement = bool(options.get("start_date") or options.get("end_date"))
        if bool(options.get("start_date")) != bool(options.get("end_date")):
            raise CommandError("Both --start-date and --end-date are required for backfill.")
        summary = run_bog_deposit_sync_jobs(
            user_id=options.get("user_id"),
            currency=options["currency"],
            use_statement=use_statement,
            start_date=options.get("start_date"),
            end_date=options.get("end_date"),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {summary['checked_connections']} BoG connection(s) via {summary['sync_source']}; "
                f"matched {summary['matched_count']} incoming transfers and "
                f"credited {summary['credited_count']} deposit(s) totaling {summary['credited_total']}."
            )
        )
