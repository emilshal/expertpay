from django.conf import settings
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import FleetPhoneBinding
from accounts.roles import get_request_fleet_binding, meets_min_role
from wallet.models import WithdrawalRequest

from .models import (
    BankSimulatorPayout,
    BogCardOrder,
    BogPayout,
    ProviderConnection,
    YandexDriverProfile,
    YandexSyncRun,
    YandexTransactionCategory,
    YandexTransactionRecord,
)
from .serializers import (
    BankSimulatorPayoutSerializer,
    BogCardOrderSerializer,
    BogPayoutSerializer,
    CreateBogCardOrderSerializer,
    ExternalEventSerializer,
    LiveYandexSyncSerializer,
    ProviderConnectionSerializer,
    SimulateEventsSerializer,
    SyncBogPayoutStatusSerializer,
    SubmitBankPayoutSerializer,
    UpdateBankPayoutStatusSerializer,
    YandexDriverProfileSerializer,
    YandexSyncRunSerializer,
    YandexTransactionCategorySerializer,
    YandexTransactionRecordSerializer,
)
from .services import (
    apply_bank_simulator_status_update,
    build_reconciliation_report,
    create_bog_card_order,
    generate_simulated_events,
    handle_bog_payments_callback,
    import_unprocessed_events,
    live_sync_yandex_data,
    purge_simulated_yandex_data,
    reconciliation_summary,
    sync_bog_card_order,
    sync_yandex_transaction_categories,
    sync_bog_payout_status,
    submit_withdrawal_to_bog,
    submit_withdrawal_to_bank_simulator,
    sync_open_bog_payouts,
    test_live_bog_payments_token_connection,
    test_live_bog_token_connection,
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


def _get_or_create_bog_connection(user):
    connection, _ = ProviderConnection.objects.get_or_create(
        user=user,
        provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
        external_account_id=f"bog-{user.username}",
        defaults={"status": "active", "config": {"mode": "live"}},
    )
    return connection


def _get_or_create_bog_payments_connection(user):
    existing = (
        ProviderConnection.objects.filter(user=user, provider=ProviderConnection.Provider.BOG_PAYMENTS)
        .order_by("id")
        .first()
    )
    if existing is not None:
        return existing

    connection, _ = ProviderConnection.objects.get_or_create(
        user=user,
        provider=ProviderConnection.Provider.BOG_PAYMENTS,
        external_account_id=f"bog-payments-{user.username}",
        defaults={"status": "active", "config": {"mode": "live"}},
    )
    return connection


def _sanitize_token_test_result(result: dict):
    payload = dict(result or {})
    response = dict(payload.get("response") or {})
    response.pop("access_token", None)
    if response:
        payload["response"] = response
    return payload


class ConnectYandexView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        return Response(ProviderConnectionSerializer(connection).data, status=status.HTTP_201_CREATED)


class ListYandexEventsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_read"

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        events = connection.events.order_by("-created_at")[:100]
        return Response(ExternalEventSerializer(events, many=True).data)


class TestYandexConnectionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can run Yandex connection tests."}, status=403)

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
    throttle_scope = "yandex_write"

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
    throttle_scope = "yandex_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can run live Yandex sync."}, status=403)

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
    throttle_scope = "yandex_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can sync Yandex categories."}, status=403)

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
    throttle_scope = "yandex_read"

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        rows = YandexTransactionCategory.objects.filter(connection=connection).order_by("name")
        return Response(YandexTransactionCategorySerializer(rows, many=True).data, status=status.HTTP_200_OK)


class ListYandexDriversView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_read"

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        rows = YandexDriverProfile.objects.filter(connection=connection).order_by("-updated_at")[:200]
        return Response(YandexDriverProfileSerializer(rows, many=True).data, status=status.HTTP_200_OK)


class ListYandexDriverSummariesView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_read"

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        profiles = list(YandexDriverProfile.objects.filter(connection=connection).order_by("first_name", "last_name", "external_driver_id"))
        tx_rows = (
            YandexTransactionRecord.objects.filter(connection=connection)
            .values("driver_external_id", "currency")
            .annotate(
                transaction_count=Count("id"),
                total_earned=Sum("amount", filter=Q(amount__gt=0)),
                total_deductions=Sum("amount", filter=Q(amount__lt=0)),
                last_transaction_at=Max("event_at"),
            )
        )
        tx_map = {
            row["driver_external_id"]: row
            for row in tx_rows
            if row.get("driver_external_id")
        }

        payload = []
        for profile in profiles:
            stats = tx_map.get(profile.external_driver_id, {})
            earned = stats.get("total_earned")
            deductions = stats.get("total_deductions")
            earned_str = str(earned or "0")
            deductions_decimal = deductions or 0
            deductions_str = str(abs(deductions_decimal))
            net_total = (earned or 0) + (deductions or 0)
            payload.append(
                {
                    "driver": YandexDriverProfileSerializer(profile).data,
                    "summary": {
                        "transaction_count": stats.get("transaction_count", 0),
                        "total_earned": earned_str,
                        "total_deductions": deductions_str,
                        "net_total": str(net_total),
                        "last_transaction_at": stats.get("last_transaction_at"),
                        "currency": stats.get("currency") or "GEL",
                    },
                }
            )
        return Response(payload, status=status.HTTP_200_OK)


class YandexDriverDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_read"

    def get(self, request, external_driver_id):
        connection = _get_or_create_yandex_connection(request.user)
        profile = YandexDriverProfile.objects.filter(
            connection=connection, external_driver_id=external_driver_id
        ).first()
        if profile is None:
            return Response({"detail": "Driver not found."}, status=status.HTTP_404_NOT_FOUND)

        tx_queryset = YandexTransactionRecord.objects.filter(
            connection=connection,
            driver_external_id=external_driver_id,
        ).order_by("-event_at", "-created_at")
        stats = tx_queryset.aggregate(
            transaction_count=Count("id"),
            total_earned=Sum("amount", filter=Q(amount__gt=0)),
            total_deductions=Sum("amount", filter=Q(amount__lt=0)),
            last_transaction_at=Max("event_at"),
        )
        total_earned = stats.get("total_earned") or 0
        total_deductions = stats.get("total_deductions") or 0
        currency = tx_queryset.values_list("currency", flat=True).first() or "GEL"

        payload = {
            "driver": YandexDriverProfileSerializer(profile).data,
            "summary": {
                "transaction_count": stats.get("transaction_count", 0),
                "total_earned": str(total_earned),
                "total_deductions": str(abs(total_deductions)),
                "net_total": str(total_earned + total_deductions),
                "last_transaction_at": stats.get("last_transaction_at"),
                "currency": currency,
            },
            "recent_transactions": YandexTransactionRecordSerializer(tx_queryset[:100], many=True).data,
        }
        return Response(payload, status=status.HTTP_200_OK)


class ListYandexTransactionsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_read"

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        rows = YandexTransactionRecord.objects.filter(connection=connection).order_by("-event_at", "-created_at")[:200]
        return Response(YandexTransactionRecordSerializer(rows, many=True).data, status=status.HTTP_200_OK)


class ListYandexSyncRunsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_read"

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        runs = YandexSyncRun.objects.filter(connection=connection).order_by("-created_at")[:100]
        return Response(YandexSyncRunSerializer(runs, many=True).data, status=status.HTTP_200_OK)


class ImportYandexEventsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_write"

    def post(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        result = import_unprocessed_events(connection=connection)
        return Response(result, status=status.HTTP_200_OK)


class ReconcileYandexView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_read"

    def get(self, request):
        connection = _get_or_create_yandex_connection(request.user)
        return Response(reconciliation_summary(connection=connection))


class PurgeSimulatedYandexDataView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "yandex_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can purge simulated Yandex data."}, status=403)

        connection = _get_or_create_yandex_connection(request.user)
        result = purge_simulated_yandex_data(connection=connection)
        return Response(result, status=status.HTTP_200_OK)


class ConnectBankSimulatorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        connection = _get_or_create_bank_sim_connection(request.user)
        return Response(ProviderConnectionSerializer(connection).data, status=status.HTTP_201_CREATED)


class TestBogTokenConnectionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_status_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can run Bank of Georgia connection tests."}, status=403)

        connection = _get_or_create_bog_connection(request.user)
        result = test_live_bog_token_connection()
        sanitized_result = _sanitize_token_test_result(result)

        config = dict(connection.config or {})
        config["mode"] = "live"
        config["last_token_test"] = {
            "ok": sanitized_result.get("ok", False),
            "checked_at": timezone.now().isoformat(),
            "http_status": sanitized_result.get("http_status"),
            "detail": sanitized_result.get("detail", ""),
            "access_token_received": bool((sanitized_result.get("response") or {}).get("access_token_received")),
        }
        connection.config = config
        connection.status = "active" if sanitized_result.get("ok") else "error"
        connection.save(update_fields=["config", "status"])

        payload = {
            "connection": ProviderConnectionSerializer(connection).data,
            "test": sanitized_result,
        }
        return Response(payload, status=status.HTTP_200_OK)


class TestBogPaymentsTokenConnectionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_status_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can run BoG card payment connection tests."}, status=403)

        connection = _get_or_create_bog_payments_connection(request.user)
        result = test_live_bog_payments_token_connection()
        sanitized_result = _sanitize_token_test_result(result)

        config = dict(connection.config or {})
        config["mode"] = "live"
        config["last_token_test"] = {
            "ok": sanitized_result.get("ok", False),
            "checked_at": timezone.now().isoformat(),
            "http_status": sanitized_result.get("http_status"),
            "detail": sanitized_result.get("detail", ""),
            "access_token_received": bool((sanitized_result.get("response") or {}).get("access_token_received")),
        }
        connection.config = config
        connection.status = "active" if sanitized_result.get("ok") else "error"
        connection.save(update_fields=["config", "status"])

        payload = {
            "connection": ProviderConnectionSerializer(connection).data,
            "test": sanitized_result,
        }
        return Response(payload, status=status.HTTP_200_OK)


class ListBogCardOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_bog_payments_connection(request.user)
        orders = connection.bog_card_orders.filter(user=request.user).order_by("-created_at")[:100]
        return Response(BogCardOrderSerializer(orders, many=True).data, status=status.HTTP_200_OK)


class CreateBogCardOrderView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_write"

    def post(self, request):
        serializer = CreateBogCardOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        connection = _get_or_create_bog_payments_connection(request.user)
        try:
            order = create_bog_card_order(
                connection=connection,
                user=request.user,
                amount=serializer.validated_data["amount"],
                currency=serializer.validated_data["currency"],
                save_card=serializer.validated_data["save_card"],
                parent_order_id=serializer.validated_data.get("parent_order_id", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BogCardOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class SyncBogCardOrderView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_status_write"

    def post(self, request, provider_order_id):
        connection = _get_or_create_bog_payments_connection(request.user)
        order = connection.bog_card_orders.filter(user=request.user, provider_order_id=provider_order_id).first()
        if order is None:
            return Response({"detail": "BoG card order not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            order = sync_bog_card_order(order=order)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BogCardOrderSerializer(order).data, status=status.HTTP_200_OK)


class BogPaymentsCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get("Callback-Signature", "")
        try:
            order = handle_bog_payments_callback(raw_body=request.body, signature=signature)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "ok": True,
                "order_id": order.provider_order_id,
                "status": order.status,
            },
            status=status.HTTP_200_OK,
        )


class ListBogPayoutsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connection = _get_or_create_bog_connection(request.user)
        payouts = connection.bog_payouts.select_related("withdrawal").order_by("-created_at")[:100]
        return Response(BogPayoutSerializer(payouts, many=True).data, status=status.HTTP_200_OK)


class SubmitBogPayoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_status_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.OPERATOR):
            return Response({"detail": "Only operator/admin/owner can submit BoG payouts."}, status=403)

        serializer = SubmitBankPayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        withdrawal_id = serializer.validated_data["withdrawal_id"]

        withdrawal = WithdrawalRequest.objects.filter(id=withdrawal_id, user=request.user).first()
        if withdrawal is None:
            return Response({"detail": "Withdrawal not found."}, status=status.HTTP_404_NOT_FOUND)
        if withdrawal.status in {WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.FAILED}:
            return Response({"detail": "Withdrawal is already finalized."}, status=status.HTTP_400_BAD_REQUEST)

        connection = _get_or_create_bog_connection(request.user)
        try:
            payout, created = submit_withdrawal_to_bog(connection=connection, withdrawal=withdrawal)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = BogPayoutSerializer(payout).data
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class SyncBogPayoutStatusView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_status_write"

    def post(self, request, payout_id):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.OPERATOR):
            return Response({"detail": "Only operator/admin/owner can refresh BoG payout status."}, status=403)

        serializer = SyncBogPayoutStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        connection = _get_or_create_bog_connection(request.user)
        payout = (
            BogPayout.objects.select_related("withdrawal")
            .filter(id=payout_id, connection=connection, withdrawal__user=request.user)
            .first()
        )
        if payout is None:
            return Response({"detail": "BoG payout not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            payout = sync_bog_payout_status(payout=payout)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BogPayoutSerializer(payout).data, status=status.HTTP_200_OK)


class SyncAllBogPayoutStatusesView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "money_status_write"

    def post(self, request):
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.OPERATOR):
            return Response({"detail": "Only operator/admin/owner can refresh BoG payout statuses."}, status=403)

        connection = _get_or_create_bog_connection(request.user)
        result = sync_open_bog_payouts(connection=connection)
        return Response(result, status=status.HTTP_200_OK)


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
        binding = get_request_fleet_binding(user=request.user, request=request)
        if not meets_min_role(binding=binding, minimum_role=FleetPhoneBinding.Role.ADMIN):
            return Response({"detail": "Only admin/owner can view reconciliation."}, status=403)
        return Response(
            build_reconciliation_report(user=request.user, fleet=binding.fleet),
            status=status.HTTP_200_OK,
        )
