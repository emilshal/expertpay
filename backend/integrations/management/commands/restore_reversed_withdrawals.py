from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ledger.services import (
    create_ledger_entry,
    get_or_create_driver_available_account,
    get_or_create_fleet_reserve_account,
    get_or_create_payout_clearing_account,
    get_or_create_platform_fee_account,
    get_or_create_user_ledger_account,
)
from wallet.models import WithdrawalRequest


class Command(BaseCommand):
    help = "Re-apply local withdrawal holds that were reversed by mistake."

    def add_arguments(self, parser):
        parser.add_argument(
            "--withdrawal-id",
            action="append",
            type=int,
            dest="withdrawal_ids",
            default=[],
            help="Withdrawal ID to restore. Pass multiple times for multiple withdrawals.",
        )
        parser.add_argument(
            "--status",
            choices=[
                WithdrawalRequest.Status.PENDING,
                WithdrawalRequest.Status.PROCESSING,
            ],
            default=WithdrawalRequest.Status.PENDING,
            help="Status to set after restoring the local hold.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be restored without changing balances.",
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

        restored_count = 0
        skipped_count = 0
        for withdrawal in withdrawals:
            self.stdout.write(
                f"Restore withdrawal {withdrawal.id}: user={withdrawal.user_id} "
                f"fleet={withdrawal.fleet_id or '-'} amount={withdrawal.amount} fee={withdrawal.fee_amount} "
                f"status={withdrawal.status} -> {options['status']}"
            )
            if options["dry_run"]:
                continue

            with transaction.atomic():
                locked_withdrawal = WithdrawalRequest.objects.select_for_update().select_related(
                    "fleet", "user", "wallet"
                ).get(id=withdrawal.id)
                metadata = {
                    "description": "Restore local withdrawal hold after accidental reversal",
                    "restored_from_status": locked_withdrawal.status,
                }

                if locked_withdrawal.fleet_id:
                    driver_account = get_or_create_driver_available_account(
                        locked_withdrawal.user,
                        fleet=locked_withdrawal.fleet,
                        currency=locked_withdrawal.currency,
                    )
                    fleet_reserve_account = get_or_create_fleet_reserve_account(
                        locked_withdrawal.fleet,
                        currency=locked_withdrawal.currency,
                    )
                    payout_clearing_account = get_or_create_payout_clearing_account(currency=locked_withdrawal.currency)
                    platform_fee_account = get_or_create_platform_fee_account(currency=locked_withdrawal.currency)

                    create_ledger_entry(
                        account=driver_account,
                        amount=-(locked_withdrawal.amount + locked_withdrawal.fee_amount),
                        entry_type="driver_withdrawal_hold_restored",
                        created_by=locked_withdrawal.user,
                        currency=locked_withdrawal.currency,
                        reference_type="withdrawal",
                        reference_id=str(locked_withdrawal.id),
                        metadata=metadata,
                        idempotency_key=f"withdrawal:{locked_withdrawal.id}:driver_hold_restored",
                    )
                    create_ledger_entry(
                        account=fleet_reserve_account,
                        amount=-locked_withdrawal.amount,
                        entry_type="fleet_reserve_withdrawal_hold_restored",
                        created_by=locked_withdrawal.user,
                        currency=locked_withdrawal.currency,
                        reference_type="withdrawal",
                        reference_id=str(locked_withdrawal.id),
                        metadata=metadata,
                        idempotency_key=f"withdrawal:{locked_withdrawal.id}:fleet_hold_restored",
                    )
                    create_ledger_entry(
                        account=payout_clearing_account,
                        amount=locked_withdrawal.amount,
                        entry_type="withdrawal_payout_clearing_credit_restored",
                        created_by=locked_withdrawal.user,
                        currency=locked_withdrawal.currency,
                        reference_type="withdrawal",
                        reference_id=str(locked_withdrawal.id),
                        metadata=metadata,
                        idempotency_key=f"withdrawal:{locked_withdrawal.id}:payout_clearing_restored",
                    )
                    if locked_withdrawal.fee_amount > Decimal("0.00"):
                        create_ledger_entry(
                            account=platform_fee_account,
                            amount=locked_withdrawal.fee_amount,
                            entry_type="withdrawal_platform_fee_credit_restored",
                            created_by=locked_withdrawal.user,
                            currency=locked_withdrawal.currency,
                            reference_type="withdrawal",
                            reference_id=str(locked_withdrawal.id),
                            metadata=metadata,
                            idempotency_key=f"withdrawal:{locked_withdrawal.id}:fee_credit_restored",
                        )
                else:
                    ledger_account = get_or_create_user_ledger_account(
                        locked_withdrawal.user,
                        locked_withdrawal.currency,
                    )
                    create_ledger_entry(
                        account=ledger_account,
                        amount=-(locked_withdrawal.amount + locked_withdrawal.fee_amount),
                        entry_type="withdrawal_hold_restored",
                        created_by=locked_withdrawal.user,
                        currency=locked_withdrawal.currency,
                        reference_type="withdrawal",
                        reference_id=str(locked_withdrawal.id),
                        metadata=metadata,
                        idempotency_key=f"withdrawal:{locked_withdrawal.id}:wallet_hold_restored",
                    )

                locked_withdrawal.status = options["status"]
                locked_withdrawal.save(update_fields=["status"])
            restored_count += 1

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete; skipped={skipped_count}."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Restored {restored_count} reversed withdrawal hold(s); skipped={skipped_count}.")
            )
