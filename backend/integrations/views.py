from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from wallet.models import WithdrawalRequest

from .models import BankSimulatorPayout, ProviderConnection, YandexSyncRun, YandexTransactionCategory
from .serializers import (
    BankSimulatorPayoutSerializer,
    ExternalEventSerializer,
    LiveYandexSyncSerializer,
    ProviderConnectionSerializer,
    SimulateEventsSerializer,
    SubmitBankPayoutSerializer,
    UpdateBankPayoutStatusSerializer,
    YandexSyncRunSerializer,
    YandexTransactionCategorySerializer,
)
from .services import (
    build_reconciliation_report,
    apply_bank_simulator_status_update,
    generate_simulated_events,
    import_unprocessed_events,
    live_sync_yandex_data,
    reconciliation_summary,
    sync_yandex_transaction_categories,
    submit_withdrawal_to_bank_simulator,
    test_live_yandex_connection,
)
def _get_or_create_yandex_connection(user):
    mode = "live" if settings.YANDEX_MODE == "live" else "simulator"
    connection, _ = ProviderConnection.objects.get_or_create(
        user=user,
        provider=ProviderConnection.Provider.YANDEX,
        external_account_id=f"fleet-{user.username}",
        defaults={"status": "active", "config": {"mode": mode}},
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


class TestYandexConnectionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        result = test_live_yandex_connection()

        config = dict(connection.config or {})
        config["mode"] = "live" if settings.YANDEX_MODE == "live" else "simulator"
        config["last_connection_test"] = {
            "ok": result.get("ok", False),
            "checked_at": timezone.now().isoformat(),
            "http_status": result.get("http_status"),
            "detail": result.get("detail", ""),
        }
        connection.config = config
        connection.status = "active" if result.get("ok") else "error"
        connection.save(update_fields=["config", "status"])

        payload = {
            "connection": ProviderConnectionSerializer(connection).data,
            "test": result,
        }
        return Response(payload, status=status.HTTP_200_OK)


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


class SyncLiveYandexView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LiveYandexSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        limit = serializer.validated_data["limit"]
        dry_run = serializer.validated_data["dry_run"]
        full_sync = serializer.validated_data["full_sync"]

        connection = _get_or_create_yandex_connection(request.user)
        result = live_sync_yandex_data(connection=connection, limit=limit, dry_run=dry_run, full_sync=full_sync)

        config = dict(connection.config or {})
        config["mode"] = "live" if settings.YANDEX_MODE == "live" else "simulator"
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

        payload = {
            "connection": ProviderConnectionSerializer(connection).data,
            "sync": result,
        }
        return Response(payload, status=status.HTTP_200_OK)


class SyncYandexCategoriesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        result = sync_yandex_transaction_categories(connection=connection)
        config = dict(connection.config or {})
        config["last_category_sync"] = {
            "ok": result.get("ok", False),
            "checked_at": timezone.now().isoformat(),
            "fetched": result.get("fetched", 0),
            "upserted": result.get("upserted", 0),
            "http_status": result.get("http_status"),
        }
        connection.config = config
        connection.save(update_fields=["config"])
        payload = {
            "connection": ProviderConnectionSerializer(connection).data,
            "categories_sync": result,
        }
        return Response(payload, status=status.HTTP_200_OK)


class ListYandexCategoriesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        rows = YandexTransactionCategory.objects.filter(connection=connection).order_by("name")
        return Response(YandexTransactionCategorySerializer(rows, many=True).data, status=status.HTTP_200_OK)


class ListYandexSyncRunsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        runs = YandexSyncRun.objects.filter(connection=connection).order_by("-created_at")[:100]
        return Response(YandexSyncRunSerializer(runs, many=True).data, status=status.HTTP_200_OK)


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
