from django.core.management.base import BaseCommand, CommandError

from accounts.models import Fleet
from integrations.models import ExternalEvent, ProviderConnection
from integrations.services import submit_yandex_withdrawal_transaction
from wallet.models import WithdrawalRequest


class Command(BaseCommand):
    help = "Submit missing Yandex debit transactions for completed BoG withdrawals."

    def add_arguments(self, parser):
        parser.add_argument("--fleet-name", default="", help="Optional fleet name scope.")
        parser.add_argument("--limit", type=int, default=25, help="Maximum withdrawals to check.")

    def handle(self, *args, **options):
        fleet_name = " ".join(options["fleet_name"].strip().split())
        fleet = None
        if fleet_name:
            fleet = Fleet.objects.filter(name__iexact=fleet_name).first()
            if fleet is None:
                raise CommandError(f"Fleet not found: {fleet_name}")

        withdrawals = WithdrawalRequest.objects.filter(
            fleet__isnull=False,
            bog_payout__provider_unique_key__isnull=False,
            status=WithdrawalRequest.Status.COMPLETED,
        ).select_related("fleet", "user", "bank_account")
        if fleet is not None:
            withdrawals = withdrawals.filter(fleet=fleet)
        withdrawals = withdrawals.order_by("created_at", "id")[: max(int(options["limit"]), 1)]

        submitted_count = 0
        skipped_count = 0
        error_count = 0
        errors = []
        for withdrawal in withdrawals:
            yandex_connection = ProviderConnection.objects.filter(
                fleet=withdrawal.fleet,
                provider=ProviderConnection.Provider.YANDEX,
                status="active",
            ).first()
            if yandex_connection is not None and ExternalEvent.objects.filter(
                connection=yandex_connection,
                external_id=f"expertpay-withdrawal-{withdrawal.id}",
                event_type="withdrawal_payout",
                processed=True,
            ).exists():
                skipped_count += 1
                continue

            result = submit_yandex_withdrawal_transaction(withdrawal=withdrawal)
            if result.get("ok") and not result.get("skipped"):
                submitted_count += 1
            elif result.get("skipped"):
                skipped_count += 1
            else:
                error_count += 1
                errors.append(f"withdrawal={withdrawal.id}: {result.get('detail')} {result.get('response')}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Submitted {submitted_count} Yandex withdrawal transaction(s); "
                f"skipped={skipped_count}; errors={error_count}."
            )
        )
        for error in errors[:10]:
            self.stdout.write(self.style.WARNING(error))
