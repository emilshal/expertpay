from django.core.management.base import BaseCommand, CommandError

from integrations.models import BogPayout
from integrations.services import _reverse_withdrawal_to_wallet
from wallet.models import WithdrawalRequest


class Command(BaseCommand):
    help = "Reverse local withdrawal holds that never produced a BoG document."

    def add_arguments(self, parser):
        parser.add_argument(
            "--withdrawal-id",
            action="append",
            type=int,
            dest="withdrawal_ids",
            default=[],
            help="Withdrawal ID to reverse. Pass multiple times for multiple withdrawals.",
        )
        parser.add_argument(
            "--reason",
            default="BoG payout document was not created; local hold reversed.",
            help="Reason stored on reversal ledger entries.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be reversed without changing balances.",
        )

    def handle(self, *args, **options):
        withdrawal_ids = options["withdrawal_ids"]
        if not withdrawal_ids:
            raise CommandError("Provide at least one --withdrawal-id.")

        withdrawals = (
            WithdrawalRequest.objects.select_related("fleet", "user", "wallet")
            .filter(id__in=withdrawal_ids)
            .order_by("id")
        )
        found_ids = {withdrawal.id for withdrawal in withdrawals}
        missing_ids = sorted(set(withdrawal_ids) - found_ids)
        if missing_ids:
            raise CommandError(f"Withdrawal(s) not found: {', '.join(str(item) for item in missing_ids)}")

        reversed_count = 0
        skipped_count = 0
        for withdrawal in withdrawals:
            payout = BogPayout.objects.filter(withdrawal=withdrawal).first()
            if payout is not None and payout.provider_unique_key:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped withdrawal {withdrawal.id}: BoG document key {payout.provider_unique_key} exists."
                    )
                )
                continue
            if withdrawal.status == WithdrawalRequest.Status.FAILED:
                skipped_count += 1
                self.stdout.write(self.style.WARNING(f"Skipped withdrawal {withdrawal.id}: already failed."))
                continue

            self.stdout.write(
                f"Reverse withdrawal {withdrawal.id}: user={withdrawal.user_id} "
                f"fleet={withdrawal.fleet_id or '-'} amount={withdrawal.amount} fee={withdrawal.fee_amount} "
                f"status={withdrawal.status}"
            )
            if options["dry_run"]:
                continue

            _reverse_withdrawal_to_wallet(
                withdrawal=withdrawal,
                reason=options["reason"],
                idempotency_key=f"manual:unsubmitted:reversal:{withdrawal.id}",
                created_by=withdrawal.user,
            )
            reversed_count += 1

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete; skipped={skipped_count}."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Reversed {reversed_count} unsubmitted withdrawal(s); skipped={skipped_count}.")
            )
