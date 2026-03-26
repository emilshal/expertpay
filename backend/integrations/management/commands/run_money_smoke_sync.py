from django.core.management.base import BaseCommand, CommandError

from integrations.jobs import (
    run_bog_deposit_sync_jobs,
    run_bog_payout_status_sync_jobs,
    run_yandex_sync_jobs,
)


class Command(BaseCommand):
    help = "Run the recommended fleet-scoped sync sequence for a live money smoke test."

    def add_arguments(self, parser):
        parser.add_argument("--fleet-name", required=True, help="Active fleet name for the smoke test.")
        parser.add_argument("--limit", type=int, default=100, help="Yandex live sync limit.")
        parser.add_argument("--full-sync", action="store_true", help="Run Yandex full sync instead of incremental.")
        parser.add_argument("--dry-run", action="store_true", help="Run Yandex sync in dry-run mode.")
        parser.add_argument("--currency", default="GEL", help="BoG deposit sync currency. Defaults to GEL.")
        parser.add_argument("--skip-deposits", action="store_true", help="Skip BoG deposit sync.")
        parser.add_argument("--skip-yandex", action="store_true", help="Skip Yandex earnings sync.")
        parser.add_argument("--skip-payouts", action="store_true", help="Skip BoG payout status sync.")

    def handle(self, *args, **options):
        fleet_name = options["fleet_name"].strip()
        if not fleet_name:
            raise CommandError("--fleet-name is required.")

        skipped_all = options["skip_deposits"] and options["skip_yandex"] and options["skip_payouts"]
        if skipped_all:
            raise CommandError("At least one sync step must be enabled.")

        self.stdout.write(self.style.SUCCESS(f"Running live money smoke sync for fleet '{fleet_name}'"))

        if not options["skip_deposits"]:
            deposit_summary = run_bog_deposit_sync_jobs(
                fleet_name=fleet_name,
                currency=options["currency"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "1. BoG deposits: "
                    f"connections={deposit_summary['checked_connections']} "
                    f"checked={deposit_summary['checked_count']} "
                    f"matched={deposit_summary['matched_count']} "
                    f"credited={deposit_summary['credited_count']} "
                    f"unmatched={deposit_summary['unmatched_count']} "
                    f"total={deposit_summary['credited_total']}"
                )
            )

        if not options["skip_yandex"]:
            yandex_summary = run_yandex_sync_jobs(
                fleet_name=fleet_name,
                limit=options["limit"],
                dry_run=options["dry_run"],
                full_sync=options["full_sync"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "2. Yandex earnings: "
                    f"connections={yandex_summary['checked_connections']} "
                    f"ok={yandex_summary['ok_connections']} "
                    f"errors={yandex_summary['error_count']} "
                    f"imported={yandex_summary['imported_count']} "
                    f"total={yandex_summary['imported_total']}"
                )
            )

        if not options["skip_payouts"]:
            payout_summary = run_bog_payout_status_sync_jobs(fleet_name=fleet_name)
            self.stdout.write(
                self.style.SUCCESS(
                    "3. BoG payouts: "
                    f"connections={payout_summary['checked_connections']} "
                    f"checked={payout_summary['checked_count']} "
                    f"updated={payout_summary['updated_count']} "
                    f"errors={payout_summary['payout_error_count']}"
                )
            )

        self.stdout.write(self.style.SUCCESS("Smoke sync sequence completed."))
