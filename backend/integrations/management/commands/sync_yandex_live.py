from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.models import ProviderConnection
from integrations.services import live_sync_yandex_data


class Command(BaseCommand):
    help = "Run live Yandex sync for active Yandex connections (incremental by cursor)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--full-sync", action="store_true")
        parser.add_argument("--user-id", type=int, default=None)

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]
        full_sync = options["full_sync"]
        user_id = options["user_id"]

        connections = ProviderConnection.objects.filter(provider=ProviderConnection.Provider.YANDEX)
        if user_id is not None:
            connections = connections.filter(user_id=user_id)

        count = 0
        started_at = timezone.now()
        for connection in connections.select_related("user"):
            result = live_sync_yandex_data(
                connection=connection,
                limit=limit,
                dry_run=dry_run,
                full_sync=full_sync,
            )

            config = dict(connection.config or {})
            config["mode"] = "live"
            config["last_live_sync"] = {
                "ok": result.get("ok", False),
                "partial": result.get("partial", False),
                "checked_at": timezone.now().isoformat(),
                "drivers_fetched": result.get("drivers", {}).get("fetched", 0),
                "drivers_upserted": result.get("drivers", {}).get("upserted_profiles", 0),
                "transactions_fetched": result.get("transactions", {}).get("fetched", 0),
                "imported_count": result.get("transactions", {}).get("imported_count", 0),
                "imported_total": result.get("transactions", {}).get("imported_total", "0.00"),
                "detail": result.get("detail", ""),
            }
            if result.get("cursor"):
                config["last_transaction_cursor"] = result["cursor"]

            connection.config = config
            connection.status = "active" if result.get("ok") else "error"
            connection.save(update_fields=["config", "status"])

            count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{connection.user.username}] ok={result.get('ok')} "
                    f"drivers_upserted={result.get('drivers', {}).get('upserted_profiles', 0)} "
                    f"tx_fetched={result.get('transactions', {}).get('fetched', 0)} "
                    f"imported={result.get('transactions', {}).get('imported_count', 0)}"
                )
            )

        elapsed = timezone.now() - started_at
        self.stdout.write(self.style.SUCCESS(f"Processed {count} Yandex connection(s) in {elapsed}."))
