from django.core.management.base import BaseCommand, CommandError

from integrations.models import ProviderConnection
from integrations.services import purge_simulated_yandex_data


class Command(BaseCommand):
    help = "Remove old simulated Yandex events and the matching wallet ledger entries."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True, help="Owner user id for the Yandex connection.")

    def handle(self, *args, **options):
        user_id = options["user_id"]
        connection = ProviderConnection.objects.filter(
            user_id=user_id,
            provider=ProviderConnection.Provider.YANDEX,
        ).first()
        if connection is None:
            raise CommandError(f"No Yandex connection found for user_id={user_id}.")

        result = purge_simulated_yandex_data(connection=connection)
        self.stdout.write(
            self.style.SUCCESS(
                "Purged simulated Yandex data: "
                f"events={result['deleted_events']} "
                f"transactions={result['deleted_transactions']} "
                f"ledger_entries={result['deleted_ledger_entries']} "
                f"removed_total={result['removed_total']} "
                f"wallet_balance={result['wallet_balance']}"
            )
        )
