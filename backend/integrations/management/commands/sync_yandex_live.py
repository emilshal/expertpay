from django.core.management.base import BaseCommand

from integrations.jobs import run_yandex_sync_jobs


class Command(BaseCommand):
    help = "Run live Yandex sync for active Yandex connections (incremental by cursor)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--full-sync", action="store_true")
        parser.add_argument("--user-id", type=int, default=None)

    def handle(self, *args, **options):
        summary = run_yandex_sync_jobs(
            limit=options["limit"],
            dry_run=options["dry_run"],
            full_sync=options["full_sync"],
            user_id=options["user_id"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {summary['checked_connections']} Yandex connection(s); "
                f"ok={summary['ok_connections']} errors={summary['error_count']} "
                f"imported={summary['imported_count']} total={summary['imported_total']}."
            )
        )
