from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from wallet.models import WithdrawalRequest

from .models import BankSimulatorPayout, ProviderConnection
from .serializers import (
    BankSimulatorPayoutSerializer,
    ExternalEventSerializer,
    ProviderConnectionSerializer,
    SimulateEventsSerializer,
    SubmitBankPayoutSerializer,
    UpdateBankPayoutStatusSerializer,
)
from .services import (
    build_reconciliation_report,
    apply_bank_simulator_status_update,
    generate_simulated_events,
    import_unprocessed_events,
    reconciliation_summary,
    submit_withdrawal_to_bank_simulator,
)


def _get_or_create_yandex_connection(user):
    connection, _ = ProviderConnection.objects.get_or_create(
        user=user,
        provider=ProviderConnection.Provider.YANDEX,
        external_account_id=f"fleet-{user.username}",
        defaults={"status": "active", "config": {"mode": "simulator"}},
    )
    return connection


def _get_or_create_bank_sim_connection(user):
    connection, _ = ProviderConnection.objects.get_or_create(
        user=user,
        provider=ProviderConnection.Provider.BANK_SIMULATOR,
        external_account_id=f"banksim-{user.username}",
        defaults={"status": "active", "config": {"mode": "simulator"}},
    )
    return connection


class ConnectYandexView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        return Response(ProviderConnectionSerializer(connection).data, status=status.HTTP_201_CREATED)


class ListYandexEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        events = connection.events.order_by("-created_at")[:100]
        return Response(ExternalEventSerializer(events, many=True).data)


class SimulateYandexEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SimulateEventsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mode = serializer.validated_data["mode"]
        count = serializer.validated_data["count"]

        connection = _get_or_create_yandex_connection(request.user)
        created = generate_simulated_events(connection=connection, mode=mode, count=count)
        return Response(
            {
                "connection_id": connection.id,
                "mode": mode,
                "requested_count": count,
                "stored_count": len(created),
            },
            status=status.HTTP_201_CREATED,
        )


class ImportYandexEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        result = import_unprocessed_events(connection=connection)
        return Response(result, status=status.HTTP_200_OK)


class ReconcileYandexView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        return Response(reconciliation_summary(connection=connection))


class ConnectBankSimulatorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_bank_sim_connection(request.user)
        return Response(ProviderConnectionSerializer(connection).data, status=status.HTTP_201_CREATED)


class ListBankSimulatorPayoutsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_bank_sim_connection(request.user)
        payouts = connection.bank_payouts.select_related("withdrawal").order_by("-created_at")[:100]
        return Response(BankSimulatorPayoutSerializer(payouts, many=True).data)


class SubmitBankSimulatorPayoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SubmitBankPayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        withdrawal_id = serializer.validated_data["withdrawal_id"]

        withdrawal = WithdrawalRequest.objects.filter(id=withdrawal_id, user=request.user).first()
        if withdrawal is None:
            return Response({"detail": "Withdrawal not found."}, status=status.HTTP_404_NOT_FOUND)
        if withdrawal.status in {WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.FAILED}:
            return Response({"detail": "Withdrawal is already finalized."}, status=status.HTTP_400_BAD_REQUEST)

        connection = _get_or_create_bank_sim_connection(request.user)
        try:
            payout, created = submit_withdrawal_to_bank_simulator(connection=connection, withdrawal=withdrawal)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = BankSimulatorPayoutSerializer(payout).data
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class UpdateBankSimulatorPayoutStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, payout_id):
        serializer = UpdateBankPayoutStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_status = serializer.validated_data["status"]
        failure_reason = serializer.validated_data.get("failure_reason", "")

        connection = _get_or_create_bank_sim_connection(request.user)
        payout = (
            BankSimulatorPayout.objects.select_related("withdrawal")
            .filter(id=payout_id, connection=connection, withdrawal__user=request.user)
            .first()
        )
        if payout is None:
            return Response({"detail": "Payout not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            payout = apply_bank_simulator_status_update(
                payout=payout,
                target_status=target_status,
                failure_reason=failure_reason,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BankSimulatorPayoutSerializer(payout).data, status=status.HTTP_200_OK)


class ReconciliationSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_reconciliation_report(user=request.user), status=status.HTTP_200_OK)
