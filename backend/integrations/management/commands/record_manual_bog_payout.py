from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Fleet, FleetPhoneBinding
from integrations.models import BogPayout, ProviderConnection
from wallet.models import WithdrawalRequest


def _get_active_fleet_bog_connection(*, fleet):
    connection = (
        ProviderConnection.objects.filter(
            fleet=fleet,
            provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
            status="active",
        )
        .order_by("id")
        .first()
    )
    if connection is not None:
        return connection

    bindings = FleetPhoneBinding.objects.filter(
        fleet=fleet,
        is_active=True,
        user__is_active=True,
        role__in=[FleetPhoneBinding.Role.OWNER, FleetPhoneBinding.Role.ADMIN],
    ).order_by("-role", "created_at", "id")
    for binding in bindings:
        connection = (
            ProviderConnection.objects.filter(
                user=binding.user,
                provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
                status="active",
            )
            .order_by("id")
            .first()
        )
        if connection is not None:
            return connection
    return None


class Command(BaseCommand):
    help = "Attach a manually-created BoG document key to an existing pending withdrawal."

    def add_arguments(self, parser):
        parser.add_argument("--fleet-name", required=True)
        parser.add_argument("--amount", required=True)
        parser.add_argument("--unique-key", required=True, type=int)
        parser.add_argument("--withdrawal-id", type=int, default=None)
        parser.add_argument("--document-no", default="")

    def handle(self, *args, **options):
        fleet = Fleet.objects.filter(name__iexact=" ".join(options["fleet_name"].strip().split())).first()
        if fleet is None:
            raise CommandError(f"Fleet not found: {options['fleet_name']}")

        withdrawal_query = WithdrawalRequest.objects.filter(
            fleet=fleet,
            amount=Decimal(options["amount"]),
            bog_payout__isnull=True,
        ).select_related("bank_account")
        if options["withdrawal_id"]:
            withdrawal_query = withdrawal_query.filter(id=options["withdrawal_id"])
        else:
            withdrawal_query = withdrawal_query.filter(status=WithdrawalRequest.Status.PENDING)
        withdrawal = withdrawal_query.order_by("-id").first()
        if withdrawal is None:
            raise CommandError("No matching pending withdrawal without a BoG payout was found.")

        connection = _get_active_fleet_bog_connection(fleet=fleet)
        if connection is None:
            raise CommandError("No active BoG connection found for this fleet.")

        payout, created = BogPayout.objects.get_or_create(
            withdrawal=withdrawal,
            defaults={
                "connection": connection,
                "provider_unique_id": options["document_no"] or f"manual-{options['unique_key']}",
                "provider_unique_key": options["unique_key"],
                "status": BogPayout.Status.PROCESSING,
                "provider_status": "A",
                "result_code": 0,
                "match_score": Decimal("100.0"),
                "request_payload": {
                    "manual": True,
                    "document_no": options["document_no"],
                    "amount": str(withdrawal.amount),
                    "beneficiary_account_number": withdrawal.bank_account.account_number,
                },
                "response_payload": {
                    "submission": {
                        "endpoint": "manual:/documents/domestic",
                        "ok": True,
                        "http_status": 200,
                        "correlation_id": "",
                        "request_body": {},
                        "response_body": {
                            "UniqueKey": options["unique_key"],
                            "ResultCode": 0,
                            "Match": 100.0,
                        },
                        "recorded_at": timezone.now().isoformat(),
                    },
                    "latest_status": {
                        "UniqueKey": options["unique_key"],
                        "Status": "A",
                        "Match": 100.0,
                    },
                    "otp_requests": [],
                    "sign_attempts": [],
                },
            },
        )

        if not created:
            payout.connection = connection
            payout.provider_unique_key = options["unique_key"]
            payout.provider_status = payout.provider_status or "A"
            payout.status = BogPayout.Status.PROCESSING
            payout.save(update_fields=["connection", "provider_unique_key", "provider_status", "status", "updated_at"])

        if withdrawal.status == WithdrawalRequest.Status.PENDING:
            withdrawal.status = WithdrawalRequest.Status.PROCESSING
            withdrawal.save(update_fields=["status"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Recorded BoG document {options['unique_key']} for withdrawal {withdrawal.id}; created={created}."
            )
        )
