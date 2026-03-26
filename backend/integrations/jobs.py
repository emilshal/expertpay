import logging
from decimal import Decimal

from django.utils import timezone

from .models import ProviderConnection
from .services import live_sync_yandex_data, sync_bog_deposits, sync_open_bog_payouts


logger = logging.getLogger(__name__)


def _filtered_connections(*, provider, user_id=None, fleet_name=None, connection_id=None, active_only=True):
    queryset = ProviderConnection.objects.filter(provider=provider)
    if active_only:
        queryset = queryset.filter(status="active")
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    if fleet_name:
        queryset = queryset.filter(
            user__fleet_phone_bindings__fleet__name=fleet_name,
            user__fleet_phone_bindings__is_active=True,
        )
    if connection_id is not None:
        queryset = queryset.filter(id=connection_id)
    return queryset.select_related("user").distinct().order_by("id")


def _record_connection_run(connection, *, state_key, ok, payload, mark_error_status=False):
    config = dict(connection.config or {})
    config[state_key] = payload
    connection.config = config
    if mark_error_status:
        connection.status = "active" if ok else "error"
        connection.save(update_fields=["config", "status"])
    else:
        connection.save(update_fields=["config"])


def run_yandex_sync_jobs(
    *,
    limit=100,
    dry_run=False,
    full_sync=False,
    user_id=None,
    fleet_name=None,
    connection_id=None,
    active_only=True,
):
    checked_connections = 0
    ok_connections = 0
    error_count = 0
    imported_count = 0
    imported_total = Decimal("0.00")
    results = []

    for connection in _filtered_connections(
        provider=ProviderConnection.Provider.YANDEX,
        user_id=user_id,
        fleet_name=fleet_name,
        connection_id=connection_id,
        active_only=active_only,
    ):
        checked_connections += 1
        checked_at = timezone.now().isoformat()
        try:
            result = live_sync_yandex_data(
                connection=connection,
                limit=limit,
                dry_run=dry_run,
                full_sync=full_sync,
                trigger="scheduler",
            )
            ok = bool(result.get("ok"))
            tx_result = result.get("transactions", {})
            imported_count += int(tx_result.get("imported_count", 0) or 0)
            imported_total += Decimal(str(tx_result.get("imported_total", "0.00")))
            if ok:
                ok_connections += 1
            else:
                error_count += 1

            payload = {
                "ok": ok,
                "partial": result.get("partial", False),
                "checked_at": checked_at,
                "drivers_fetched": result.get("drivers", {}).get("fetched", 0),
                "drivers_upserted": result.get("drivers", {}).get("upserted_profiles", 0),
                "transactions_fetched": tx_result.get("fetched", 0),
                "imported_count": tx_result.get("imported_count", 0),
                "imported_total": tx_result.get("imported_total", "0.00"),
                "detail": result.get("detail", ""),
            }
            if result.get("cursor"):
                payload["cursor"] = result["cursor"]

            _record_connection_run(
                connection,
                state_key="last_live_sync",
                ok=ok,
                payload=payload,
                mark_error_status=True,
            )
            results.append(
                {
                    "connection_id": connection.id,
                    "provider": "yandex",
                    "user_id": connection.user_id,
                    "ok": ok,
                    "detail": result.get("detail", ""),
                    "imported_count": tx_result.get("imported_count", 0),
                    "imported_total": tx_result.get("imported_total", "0.00"),
                }
            )
            logger.info(
                "Yandex sync job finished",
                extra={
                    "connection_id": connection.id,
                    "user_id": connection.user_id,
                    "ok": ok,
                    "imported_count": tx_result.get("imported_count", 0),
                    "imported_total": tx_result.get("imported_total", "0.00"),
                },
            )
        except Exception as exc:
            error_count += 1
            payload = {
                "ok": False,
                "partial": False,
                "checked_at": checked_at,
                "drivers_fetched": 0,
                "drivers_upserted": 0,
                "transactions_fetched": 0,
                "imported_count": 0,
                "imported_total": "0.00",
                "detail": str(exc),
            }
            _record_connection_run(
                connection,
                state_key="last_live_sync",
                ok=False,
                payload=payload,
                mark_error_status=True,
            )
            results.append(
                {
                    "connection_id": connection.id,
                    "provider": "yandex",
                    "user_id": connection.user_id,
                    "ok": False,
                    "detail": str(exc),
                    "imported_count": 0,
                    "imported_total": "0.00",
                }
            )
            logger.exception("Yandex sync job failed for connection %s", connection.id)

    return {
        "job": "yandex",
        "checked_connections": checked_connections,
        "ok_connections": ok_connections,
        "error_count": error_count,
        "imported_count": imported_count,
        "imported_total": f"{imported_total.quantize(Decimal('0.01'))}",
        "results": results,
    }


def run_bog_deposit_sync_jobs(
    *,
    user_id=None,
    fleet_name=None,
    connection_id=None,
    active_only=True,
    currency="GEL",
    use_statement=False,
    start_date=None,
    end_date=None,
):
    checked_connections = 0
    ok_connections = 0
    error_count = 0
    checked_count = 0
    matched_count = 0
    credited_count = 0
    credited_total = Decimal("0.00")
    unmatched_count = 0
    results = []

    for connection in _filtered_connections(
        provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
        user_id=user_id,
        fleet_name=fleet_name,
        connection_id=connection_id,
        active_only=active_only,
    ):
        checked_connections += 1
        checked_at = timezone.now().isoformat()
        try:
            if use_statement:
                result = sync_bog_deposits(
                    connection=connection,
                    currency=currency,
                    use_statement=True,
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                result = sync_bog_deposits(connection=connection, currency=currency)
            ok = bool(result.get("ok"))
            checked_count += int(result.get("checked_count", 0) or 0)
            matched_count += int(result.get("matched_count", 0) or 0)
            credited_count += int(result.get("credited_count", 0) or 0)
            unmatched_count += int(result.get("unmatched_count", 0) or 0)
            credited_total += Decimal(str(result.get("credited_total", "0.00")))
            if ok:
                ok_connections += 1
            else:
                error_count += 1

            payload = {
                "ok": ok,
                "checked_at": checked_at,
                "checked_count": result.get("checked_count", 0),
                "matched_count": result.get("matched_count", 0),
                "credited_count": result.get("credited_count", 0),
                "unmatched_count": result.get("unmatched_count", 0),
                "credited_total": result.get("credited_total", "0.00"),
                "detail": result.get("detail", ""),
            }
            _record_connection_run(
                connection,
                state_key="last_deposit_sync",
                ok=ok,
                payload=payload,
                mark_error_status=True,
            )
            results.append(
                {
                    "connection_id": connection.id,
                    "provider": "bog_deposits",
                    "user_id": connection.user_id,
                    "ok": ok,
                    "checked_count": result.get("checked_count", 0),
                    "matched_count": result.get("matched_count", 0),
                    "credited_count": result.get("credited_count", 0),
                    "credited_total": result.get("credited_total", "0.00"),
                    "detail": result.get("detail", ""),
                }
            )
            logger.info(
                "BoG deposit sync job finished",
                extra={
                    "connection_id": connection.id,
                    "user_id": connection.user_id,
                    "ok": ok,
                    "matched_count": result.get("matched_count", 0),
                    "credited_count": result.get("credited_count", 0),
                    "credited_total": result.get("credited_total", "0.00"),
                },
            )
        except Exception as exc:
            error_count += 1
            payload = {
                "ok": False,
                "checked_at": checked_at,
                "checked_count": 0,
                "matched_count": 0,
                "credited_count": 0,
                "unmatched_count": 0,
                "credited_total": "0.00",
                "detail": str(exc),
            }
            _record_connection_run(
                connection,
                state_key="last_deposit_sync",
                ok=False,
                payload=payload,
                mark_error_status=True,
            )
            results.append(
                {
                    "connection_id": connection.id,
                    "provider": "bog_deposits",
                    "user_id": connection.user_id,
                    "ok": False,
                    "checked_count": 0,
                    "matched_count": 0,
                    "credited_count": 0,
                    "credited_total": "0.00",
                    "detail": str(exc),
                }
            )
            logger.exception("BoG deposit sync job failed for connection %s", connection.id)

    return {
        "job": "bog_deposits",
        "checked_connections": checked_connections,
        "ok_connections": ok_connections,
        "error_count": error_count,
        "checked_count": checked_count,
        "matched_count": matched_count,
        "credited_count": credited_count,
        "credited_total": f"{credited_total.quantize(Decimal('0.01'))}",
        "unmatched_count": unmatched_count,
        "sync_source": "backfill" if use_statement else "activity_poll",
        "results": results,
    }


def run_bog_payout_status_sync_jobs(
    *,
    user_id=None,
    fleet_name=None,
    connection_id=None,
    active_only=True,
):
    checked_connections = 0
    ok_connections = 0
    error_count = 0
    checked_count = 0
    updated_count = 0
    payout_error_count = 0
    results = []

    for connection in _filtered_connections(
        provider=ProviderConnection.Provider.BANK_OF_GEORGIA,
        user_id=user_id,
        fleet_name=fleet_name,
        connection_id=connection_id,
        active_only=active_only,
    ):
        checked_connections += 1
        checked_at = timezone.now().isoformat()
        try:
            result = sync_open_bog_payouts(connection=connection)
            ok = int(result.get("error_count", 0) or 0) == 0
            checked_count += int(result.get("checked_count", 0) or 0)
            updated_count += int(result.get("updated_count", 0) or 0)
            payout_error_count += int(result.get("error_count", 0) or 0)
            if ok:
                ok_connections += 1
            else:
                error_count += 1

            payload = {
                "ok": ok,
                "checked_at": checked_at,
                "checked_count": result.get("checked_count", 0),
                "updated_count": result.get("updated_count", 0),
                "error_count": result.get("error_count", 0),
                "errors": result.get("errors", []),
                "detail": "" if ok else "One or more BoG payouts failed to sync.",
            }
            _record_connection_run(
                connection,
                state_key="last_payout_sync",
                ok=ok,
                payload=payload,
                mark_error_status=False,
            )
            results.append(
                {
                    "connection_id": connection.id,
                    "provider": "bog_payouts",
                    "user_id": connection.user_id,
                    "ok": ok,
                    "checked_count": result.get("checked_count", 0),
                    "updated_count": result.get("updated_count", 0),
                    "error_count": result.get("error_count", 0),
                }
            )
            logger.info(
                "BoG payout sync job finished",
                extra={
                    "connection_id": connection.id,
                    "user_id": connection.user_id,
                    "ok": ok,
                    "checked_count": result.get("checked_count", 0),
                    "updated_count": result.get("updated_count", 0),
                    "error_count": result.get("error_count", 0),
                },
            )
        except Exception as exc:
            error_count += 1
            payload = {
                "ok": False,
                "checked_at": checked_at,
                "checked_count": 0,
                "updated_count": 0,
                "error_count": 1,
                "errors": [{"detail": str(exc)}],
                "detail": str(exc),
            }
            _record_connection_run(
                connection,
                state_key="last_payout_sync",
                ok=False,
                payload=payload,
                mark_error_status=False,
            )
            results.append(
                {
                    "connection_id": connection.id,
                    "provider": "bog_payouts",
                    "user_id": connection.user_id,
                    "ok": False,
                    "checked_count": 0,
                    "updated_count": 0,
                    "error_count": 1,
                }
            )
            logger.exception("BoG payout sync job failed for connection %s", connection.id)

    return {
        "job": "bog_payouts",
        "checked_connections": checked_connections,
        "ok_connections": ok_connections,
        "error_count": error_count,
        "checked_count": checked_count,
        "updated_count": updated_count,
        "payout_error_count": payout_error_count,
        "results": results,
    }
