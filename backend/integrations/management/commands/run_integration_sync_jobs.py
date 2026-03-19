from django.core.management.base import BaseCommand

from integrations.jobs import (
    run_bog_deposit_sync_jobs,
    run_bog_payout_status_sync_jobs,
    run_yandex_sync_jobs,
)


class Command(BaseCommand):
    help = "Run background sync jobs for Yandex earnings, BoG incoming deposits, and BoG payout statuses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--job",
            choices=["all", "yandex", "bog_deposits", "bog_payouts"],
            default="all",
            help="Select one sync job or run all of them.",
        )
        parser.add_argument("--user-id", type=int, default=None, help="Optional owner user id scope.")
        parser.add_argument("--fleet-name", default="", help="Optional fleet name scope.")
        parser.add_argument("--connection-id", type=int, default=None, help="Optional single provider connection id.")
        parser.add_argument("--include-inactive", action="store_true", help="Include non-active connections.")
        parser.add_argument("--limit", type=int, default=100, help="Yandex live sync limit.")
        parser.add_argument("--dry-run", action="store_true", help="Run Yandex sync without persisting remote data.")
        parser.add_argument("--full-sync", action="store_true", help="Run Yandex full backfill instead of incremental sync.")
        parser.add_argument("--currency", default="GEL", help="BoG deposit sync currency. Defaults to GEL.")

    def handle(self, *args, **options):
        active_only = not options["include_inactive"]
        job = options["job"]
        summaries = []

        if job in {"all", "yandex"}:
            summary = run_yandex_sync_jobs(
                limit=options["limit"],
                dry_run=options["dry_run"],
                full_sync=options["full_sync"],
                user_id=options["user_id"],
                fleet_name=options["fleet_name"] or None,
                connection_id=options["connection_id"],
                active_only=active_only,
            )
            summaries.append(summary)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Yandex sync: connections={summary['checked_connections']} ok={summary['ok_connections']} "
                    f"errors={summary['error_count']} imported={summary['imported_count']} "
                    f"total={summary['imported_total']}"
                )
            )

        if job in {"all", "bog_deposits"}:
            summary = run_bog_deposit_sync_jobs(
                user_id=options["user_id"],
                fleet_name=options["fleet_name"] or None,
                connection_id=options["connection_id"],
                active_only=active_only,
                currency=options["currency"],
            )
            summaries.append(summary)
            self.stdout.write(
                self.style.SUCCESS(
                    f"BoG deposit sync: connections={summary['checked_connections']} ok={summary['ok_connections']} "
                    f"errors={summary['error_count']} checked={summary['checked_count']} "
                    f"matched={summary['matched_count']} credited={summary['credited_count']} "
                    f"total={summary['credited_total']}"
                )
            )

        if job in {"all", "bog_payouts"}:
            summary = run_bog_payout_status_sync_jobs(
                user_id=options["user_id"],
                fleet_name=options["fleet_name"] or None,
                connection_id=options["connection_id"],
                active_only=active_only,
            )
            summaries.append(summary)
            self.stdout.write(
                self.style.SUCCESS(
                    f"BoG payout sync: connections={summary['checked_connections']} ok={summary['ok_connections']} "
                    f"errors={summary['error_count']} checked={summary['checked_count']} "
                    f"updated={summary['updated_count']} payout_errors={summary['payout_error_count']}"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Completed {len(summaries)} sync job group(s)."))
