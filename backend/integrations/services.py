from decimal import Decimal
import random
from datetime import timedelta
import base64
import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from ledger.models import LedgerAccount
from ledger.services import (
    create_ledger_entry,
    ensure_opening_entry,
    get_account_balance,
    get_or_create_user_ledger_account,
)
from wallet.models import Wallet, WithdrawalRequest

from .models import (
    BogPayout,
    BankSimulatorPayout,
    ExternalEvent,
    ProviderConnection,
    YandexDriverProfile,
    YandexSyncRun,
    YandexTransactionCategory,
    YandexTransactionRecord,
)


def _yandex_missing_env_vars():
    missing = []
    if not settings.YANDEX_PARK_ID:
        missing.append("YANDEX_PARK_ID")
    if not settings.YANDEX_CLIENT_ID:
        missing.append("YANDEX_CLIENT_ID")
    if not settings.YANDEX_API_KEY:
        missing.append("YANDEX_API_KEY")
    return missing


def _bog_missing_env_vars():
    missing = []
    if not settings.BOG_TOKEN_URL:
        missing.append("BOG_TOKEN_URL")
    if not settings.BOG_BASE_URL:
        missing.append("BOG_BASE_URL")
    if not settings.BOG_CLIENT_ID:
        missing.append("BOG_CLIENT_ID")
    if not settings.BOG_CLIENT_SECRET:
        missing.append("BOG_CLIENT_SECRET")
    return missing


def _bog_missing_payout_env_vars():
    missing = _bog_missing_env_vars()
    if not settings.BOG_SOURCE_ACCOUNT_NUMBER:
        missing.append("BOG_SOURCE_ACCOUNT_NUMBER")
    if not settings.BOG_PAYER_INN:
        missing.append("BOG_PAYER_INN")
    return missing


def _parse_json_response(response):
    raw_body = response.read().decode("utf-8", errors="replace")
    if not raw_body:
        return {}
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return {"raw": raw_body[:1000]}


def test_live_bog_token_connection():
    missing = _bog_missing_env_vars()
    if missing:
        return {
            "ok": False,
            "configured": False,
            "provider": "bog",
            "http_status": None,
            "endpoint": settings.BOG_TOKEN_URL or "",
            "detail": f"Missing BoG settings: {', '.join(missing)}",
        }

    credentials = f"{settings.BOG_CLIENT_ID}:{settings.BOG_CLIENT_SECRET}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("ascii")
    body = {
        "grant_type": "client_credentials",
        "client_id": settings.BOG_CLIENT_ID,
        "client_secret": settings.BOG_CLIENT_SECRET,
    }
    if settings.BOG_SCOPE:
        body["scope"] = settings.BOG_SCOPE

    request = Request(
        url=settings.BOG_TOKEN_URL,
        method="POST",
        data=urlencode(body).encode("utf-8"),
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urlopen(request, timeout=settings.BOG_REQUEST_TIMEOUT_SECONDS) as response:
            payload = _parse_json_response(response)
            access_token = str(payload.get("access_token") or "")
            ok = bool(access_token)
            return {
                "ok": ok,
                "configured": True,
                "provider": "bog",
                "http_status": getattr(response, "status", 200),
                "endpoint": settings.BOG_TOKEN_URL,
                "detail": "Token request succeeded." if ok else "Token response did not include access_token.",
                "response": {
                    "token_type": payload.get("token_type"),
                    "expires_in": payload.get("expires_in"),
                    "scope": payload.get("scope"),
                    "access_token_received": ok,
                    "access_token": access_token if ok else "",
                },
            }
    except HTTPError as exc:
        parsed_body = {}
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
            parsed_body = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            parsed_body = {"raw": body_text[:1000]} if body_text else {}
        return {
            "ok": False,
            "configured": True,
            "provider": "bog",
            "http_status": exc.code,
            "endpoint": settings.BOG_TOKEN_URL,
            "detail": "BoG token request failed.",
            "response": parsed_body,
        }
    except URLError as exc:
        return {
            "ok": False,
            "configured": True,
            "provider": "bog",
            "http_status": None,
            "endpoint": settings.BOG_TOKEN_URL,
            "detail": f"BoG token request could not reach host: {exc.reason}",
        }


def _bog_cache_key(connection: ProviderConnection):
    return f"integrations:bog:token:{connection.id}"


def _request_new_bog_access_token():
    result = test_live_bog_token_connection()
    if not result.get("ok"):
        raise ValueError(result.get("detail") or "BoG token request failed.")
    response = result.get("response") or {}
    access_token = str(response.get("access_token") or "")
    if not access_token:
        raise ValueError("BoG token response did not include access_token.")
    expires_in = int(response.get("expires_in") or 0)
    return {
        "access_token": access_token,
        "token_type": response.get("token_type") or "Bearer",
        "expires_in": expires_in,
        "scope": response.get("scope"),
        "cached_until": (timezone.now() + timedelta(seconds=max(0, expires_in - 60))).isoformat(),
    }


def get_valid_bog_access_token(*, connection: ProviderConnection, force_refresh: bool = False):
    cache_key = _bog_cache_key(connection)
    if not force_refresh:
        token_payload = cache.get(cache_key)
        if isinstance(token_payload, dict):
            cached_until = parse_datetime(str(token_payload.get("cached_until") or "")) if token_payload.get("cached_until") else None
            if cached_until is not None and timezone.is_naive(cached_until):
                cached_until = timezone.make_aware(cached_until, timezone.get_current_timezone())
            if token_payload.get("access_token") and cached_until and cached_until > timezone.now():
                return str(token_payload["access_token"])

    token_payload = _request_new_bog_access_token()
    ttl = max(60, int(token_payload.get("expires_in") or 1800) - 60)
    cache.set(cache_key, token_payload, ttl)
    return str(token_payload["access_token"])


def _parse_bog_response(response):
    raw_body = response.read().decode("utf-8", errors="replace")
    if not raw_body:
        return {}
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return {"raw": raw_body[:2000]}


def _bog_request(*, connection: ProviderConnection, method: str, endpoint: str, body=None, retry_on_401: bool = True):
    token = get_valid_bog_access_token(connection=connection)
    url = f"{settings.BOG_BASE_URL}{endpoint}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url=url,
        method=method,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=settings.BOG_REQUEST_TIMEOUT_SECONDS) as response:
            return {
                "ok": 200 <= getattr(response, "status", 200) < 300,
                "http_status": getattr(response, "status", 200),
                "body": _parse_bog_response(response),
            }
    except HTTPError as exc:
        parsed_body = {}
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
            parsed_body = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            parsed_body = {"raw": body_text[:2000]} if body_text else {}
        if exc.code == 401 and retry_on_401:
            get_valid_bog_access_token(connection=connection, force_refresh=True)
            return _bog_request(connection=connection, method=method, endpoint=endpoint, body=body, retry_on_401=False)
        return {
            "ok": False,
            "http_status": exc.code,
            "body": parsed_body,
        }
    except URLError as exc:
        return {
            "ok": False,
            "http_status": None,
            "body": {"error": str(exc.reason)},
        }


def _infer_bog_bank_code(bank_name: str):
    normalized = (bank_name or "").strip().lower()
    if normalized in {"bank of georgia", "bog"}:
        return "BAGAGE22"
    if normalized in {"tbc", "tbc bank"}:
        return "TBCBGE22"
    return ""


def _build_bog_document_payload(*, withdrawal: WithdrawalRequest):
    bank_account = withdrawal.bank_account
    beneficiary_bank_code = _infer_bog_bank_code(bank_account.bank_name)
    if not beneficiary_bank_code:
        raise ValueError("Unsupported bank for automatic BoG payout submission.")
    if not bank_account.beneficiary_inn:
        raise ValueError("Bank account is missing beneficiary ID number.")

    unique_id = str(uuid.uuid4())
    dispatch_type = "BULK" if withdrawal.amount <= Decimal("10000.00") else "MT103"
    document_no = f"{settings.BOG_DOCUMENT_PREFIX}{withdrawal.id}"[:16]
    payload = [
        {
            "Nomination": (withdrawal.note or f"ExpertPay withdrawal #{withdrawal.id}")[:250],
            "PayerInn": settings.BOG_PAYER_INN,
            "PayerName": settings.BOG_PAYER_NAME or "",
            "DispatchType": dispatch_type,
            "ValueDate": timezone.now().isoformat(),
            "IsSalary": False,
            "UniqueId": unique_id,
            "Amount": float(withdrawal.amount),
            "DocumentNo": document_no,
            "SourceAccountNumber": settings.BOG_SOURCE_ACCOUNT_NUMBER,
            "BeneficiaryAccountNumber": bank_account.account_number,
            "BeneficiaryBankCode": beneficiary_bank_code,
            "BeneficiaryInn": bank_account.beneficiary_inn,
            "CheckInn": beneficiary_bank_code == "BAGAGE22",
            "BeneficiaryName": bank_account.beneficiary_name,
            "AdditionalInformation": withdrawal.note or "",
        }
    ]
    return payload, unique_id


def _yandex_request(*, method: str, endpoint: str, query: dict | None = None, body: dict | None = None):
    query_string = f"?{urlencode(query)}" if query else ""
    url = f"{settings.YANDEX_BASE_URL}{endpoint}{query_string}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url=url,
        method=method,
        data=data,
        headers={
            "X-Client-ID": settings.YANDEX_CLIENT_ID,
            "X-API-Key": settings.YANDEX_API_KEY,
            "Accept-Language": "en",
            "Content-Type": "application/json",
        },
    )

    max_attempts = max(1, int(getattr(settings, "YANDEX_MAX_RETRIES", 3)))
    base_delay = float(getattr(settings, "YANDEX_RETRY_BASE_SECONDS", 0.5))
    retryable_http = {429, 500, 502, 503, 504}

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=settings.YANDEX_REQUEST_TIMEOUT_SECONDS) as response:
                return {
                    "ok": 200 <= getattr(response, "status", 200) < 300,
                    "http_status": getattr(response, "status", 200),
                    "body": _parse_json_response(response),
                    "attempts": attempt,
                }
        except HTTPError as exc:
            parsed_body = {}
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
                parsed_body = json.loads(body_text) if body_text else {}
            except json.JSONDecodeError:
                parsed_body = {"raw": body_text[:1000]} if body_text else {}

            last_error = {
                "ok": False,
                "http_status": exc.code,
                "body": parsed_body,
                "attempts": attempt,
            }
            if exc.code in retryable_http and attempt < max_attempts:
                sleep_seconds = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, 0.2)
                time.sleep(sleep_seconds)
                continue
            return last_error
        except URLError as exc:
            last_error = {
                "ok": False,
                "http_status": None,
                "body": {"error": str(exc.reason)},
                "attempts": attempt,
            }
            if attempt < max_attempts:
                sleep_seconds = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, 0.2)
                time.sleep(sleep_seconds)
                continue
            return last_error

    return last_error or {
        "ok": False,
        "http_status": None,
        "body": {"error": "Unknown Yandex request failure"},
        "attempts": max_attempts,
    }


def _extract_items(payload: dict, keys: tuple[str, ...]):
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0.00")
    if isinstance(value, dict):
        for candidate_key in ("amount", "value", "sum"):
            if candidate_key in value:
                return _to_decimal(value[candidate_key])
    return Decimal("0.00")


def _extract_transaction_amount(item: dict) -> Decimal:
    # Yandex payloads vary by endpoint/version. We try common amount fields in order.
    for key in ("amount", "net_amount", "total", "value", "cash"):
        if key in item:
            amount = _to_decimal(item[key])
            if amount != Decimal("0.00"):
                return amount
    if "income" in item:
        amount = _to_decimal(item["income"])
        if amount != Decimal("0.00"):
            return amount
    return Decimal("0.00")


def _extract_transaction_id(item: dict) -> str:
    for key in ("id", "transaction_id", "uuid", "event_id"):
        value = item.get(key)
        if value:
            return str(value)
    # Last fallback: stable hash from JSON.
    return str(abs(hash(json.dumps(item, sort_keys=True))))


def _extract_driver_id(item: dict) -> str:
    for key in ("driver_id", "contractor_id", "profile_id", "id"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _extract_driver_name_parts(item: dict):
    first_name = str(item.get("first_name") or item.get("name") or "").strip()
    last_name = str(item.get("last_name") or "").strip()
    if not first_name and "full_name" in item and isinstance(item["full_name"], str):
        parts = item["full_name"].strip().split()
        if parts:
            first_name = parts[0]
            if len(parts) > 1:
                last_name = " ".join(parts[1:])
    return first_name, last_name


def _extract_driver_phone(item: dict) -> str:
    for key in ("phone", "phone_number", "driver_phone"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _extract_driver_status(item: dict) -> str:
    for key in ("status", "is_enabled", "is_active"):
        if key in item:
            return str(item.get(key))
    return ""


def _extract_transaction_timestamp(item: dict):
    for key in ("event_at", "performed_at", "created_at", "transaction_time", "timestamp", "time"):
        value = item.get(key)
        if isinstance(value, str):
            parsed = parse_datetime(value)
            if parsed is not None:
                if timezone.is_naive(parsed):
                    return timezone.make_aware(parsed, timezone.get_current_timezone())
                return parsed
    return None


def _extract_transaction_category(item: dict) -> str:
    for key in ("category", "transaction_type", "type"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _extract_transaction_direction(item: dict) -> str:
    for key in ("direction", "sign"):
        value = item.get(key)
        if value:
            return str(value)
    amount = _extract_transaction_amount(item)
    if amount < Decimal("0.00"):
        return "debit"
    if amount > Decimal("0.00"):
        return "credit"
    return ""


def _normalize_transaction_payload(item: dict):
    transaction_id = _extract_transaction_id(item)
    event_at = _extract_transaction_timestamp(item)
    amount = _extract_transaction_amount(item)
    driver_id = _extract_driver_id(item)
    currency = item.get("currency") or item.get("currency_code") or "GEL"
    category = _extract_transaction_category(item)
    direction = _extract_transaction_direction(item)
    return {
        "external_id": transaction_id,
        "event_at": event_at.isoformat() if event_at else None,
        "driver_id": driver_id,
        "currency": str(currency),
        "net_amount": str(amount),
        "category": category,
        "direction": direction,
        "event_type": item.get("event_type") or "earning",
        "raw": item,
    }


def _build_sync_window(*, connection: ProviderConnection, full_sync: bool = False):
    now = timezone.now()
    config = connection.config or {}
    if full_sync:
        return {
            "from": (now - timedelta(days=7)).isoformat(),
            "to": now.isoformat(),
        }

    last_cursor = config.get("last_transaction_cursor") or {}
    cursor_from_raw = last_cursor.get("next_from")
    cursor_from = parse_datetime(cursor_from_raw) if isinstance(cursor_from_raw, str) else None
    if cursor_from is None:
        cursor_from = now - timedelta(days=1)
    if timezone.is_naive(cursor_from):
        cursor_from = timezone.make_aware(cursor_from, timezone.get_current_timezone())

    # Small overlap to avoid missing edge transactions around boundary timestamps.
    safe_from = cursor_from - timedelta(minutes=2)
    return {
        "from": safe_from.isoformat(),
        "to": now.isoformat(),
    }


def _fetch_live_transactions(*, limit: int, window: dict):
    attempts = [
        {
            "query": {
                "park": {"id": settings.YANDEX_PARK_ID},
                "transaction": {"event_at": window},
            },
            "limit": limit,
        },
        {
            "query": {
                "park": {
                    "id": settings.YANDEX_PARK_ID,
                    "transaction": {"event_at": window},
                }
            },
            "limit": limit,
        },
        {"query": {"park": {"id": settings.YANDEX_PARK_ID}}, "limit": limit},
    ]

    last_response = None
    for body in attempts:
        response = _yandex_request(
            method="POST",
            endpoint="/v2/parks/transactions/list",
            body=body,
        )
        last_response = response
        if response["ok"]:
            return response

    return last_response or {"ok": False, "http_status": None, "body": {"error": "No request attempts made."}}


def _fetch_yandex_transaction_categories():
    attempts = [
        {"query": {"park": {"id": settings.YANDEX_PARK_ID}}},
        {"park": {"id": settings.YANDEX_PARK_ID}},
    ]
    last_response = None
    for body in attempts:
        response = _yandex_request(
            method="POST",
            endpoint="/v2/parks/transactions/categories/list",
            body=body,
        )
        last_response = response
        if response["ok"]:
            return response
    return last_response or {"ok": False, "http_status": None, "body": {"error": "No request attempts made."}}


def _event_amount_for_mode(mode: str) -> Decimal:
    if mode == "spiky":
        return Decimal(random.choice(["8.25", "12.40", "31.50", "60.00", "95.75"]))
    if mode == "adjustment":
        return Decimal(random.choice(["-4.00", "-1.25", "2.10", "5.00"]))
    return Decimal(random.choice(["6.50", "8.30", "9.10", "11.75", "14.00"]))


def generate_simulated_events(*, connection: ProviderConnection, mode: str, count: int):
    now = timezone.now()
    created = []
    for index in range(count):
        amount = _event_amount_for_mode(mode)
        event_time = now - timedelta(minutes=index * random.randint(1, 12))
        external_id = f"yandex-{connection.id}-{int(event_time.timestamp())}-{index}"
        payload = {
            "external_id": external_id,
            "driver_id": f"drv-{1000 + index}",
            "fleet": connection.external_account_id,
            "event_time": event_time.isoformat(),
            "currency": "GEL",
            "gross_amount": str(amount),
            "net_amount": str(amount),
            "event_type": "earning",
        }

        if mode == "duplicates" and index % 3 == 0 and created:
            payload["external_id"] = created[-1].external_id
            external_id = payload["external_id"]

        event, _ = ExternalEvent.objects.get_or_create(
            connection=connection,
            external_id=external_id,
            defaults={"event_type": "earning", "payload": payload, "processed": False},
        )
        created.append(event)

    if mode == "out_of_order":
        random.shuffle(created)

    return created


def import_unprocessed_events(*, connection: ProviderConnection):
    wallet, _ = Wallet.objects.get_or_create(user=connection.user)
    ledger_account = get_or_create_user_ledger_account(connection.user, wallet.currency)
    ensure_opening_entry(ledger_account, wallet.balance, created_by=connection.user)

    events = list(connection.events.filter(processed=False).order_by("created_at", "id"))
    imported = 0
    imported_total = Decimal("0.00")

    with transaction.atomic():
        for event in events:
            net = Decimal(str(event.payload.get("net_amount", "0")))
            if net == Decimal("0.00"):
                event.processed = True
                event.save(update_fields=["processed"])
                continue

            idempotency_key = f"yandex:{connection.id}:{event.external_id}"
            create_ledger_entry(
                account=ledger_account,
                amount=net,
                entry_type="yandex_earning",
                created_by=connection.user,
                reference_type="external_event",
                reference_id=str(event.id),
                idempotency_key=idempotency_key,
                metadata={
                    "description": f"Yandex import {event.external_id}",
                    "external_event_id": event.external_id,
                },
            )
            imported += 1
            imported_total += net
            event.processed = True
            event.save(update_fields=["processed"])

        wallet.balance = wallet.balance + imported_total
        wallet.save(update_fields=["balance", "updated_at"])

    return {"imported_count": imported, "imported_total": str(imported_total)}


def reconciliation_summary(*, connection: ProviderConnection):
    imported_events = connection.events.filter(processed=True)
    imported_total = Decimal("0.00")
    for event in imported_events:
        imported_total += Decimal(str(event.payload.get("net_amount", "0")))

    wallet, _ = Wallet.objects.get_or_create(user=connection.user)
    ledger_account = get_or_create_user_ledger_account(connection.user, wallet.currency)
    yandex_ledger_total = Decimal("0.00")
    for entry in ledger_account.entries.filter(entry_type="yandex_earning"):
        yandex_ledger_total += Decimal(str(entry.amount))

    delta = imported_total - yandex_ledger_total
    return {
        "imported_events": imported_events.count(),
        "imported_total": str(imported_total),
        "ledger_total": str(yandex_ledger_total),
        "delta": str(delta),
        "status": "OK" if delta == Decimal("0.00") else "MISMATCH",
    }


def test_live_yandex_connection():
    missing = _yandex_missing_env_vars()
    if missing:
        return {
            "ok": False,
            "configured": False,
            "mode": settings.YANDEX_MODE,
            "http_status": None,
            "endpoint": "/v1/parks/driver-work-rules",
            "detail": f"Missing Yandex env vars: {', '.join(missing)}",
        }

    response = _yandex_request(
        method="GET",
        endpoint="/v1/parks/driver-work-rules",
        query={"park_id": settings.YANDEX_PARK_ID},
    )
    status_code = response["http_status"]
    parsed_body = response["body"]
    if response["ok"]:
        return {
            "ok": True,
            "configured": True,
            "mode": settings.YANDEX_MODE,
            "http_status": status_code,
            "endpoint": "/v1/parks/driver-work-rules",
            "detail": "Connection test succeeded.",
            "response": parsed_body,
        }

    detail = f"Yandex API returned HTTP {status_code}."
    if status_code == 401:
        detail = "Unauthorized: check X-Client-ID/X-API-Key."
    elif status_code == 403:
        detail = "Forbidden: credentials are valid but endpoint access may be disabled."
    elif status_code == 429:
        detail = "Rate limited by Yandex API."
    elif status_code is None:
        detail = f"Network error while calling Yandex API: {parsed_body.get('error', 'unknown')}"

    return {
        "ok": False,
        "configured": True,
        "mode": settings.YANDEX_MODE,
        "http_status": status_code,
        "endpoint": "/v1/parks/driver-work-rules",
        "detail": detail,
        "response": parsed_body,
    }


def sync_yandex_transaction_categories(*, connection: ProviderConnection):
    missing = _yandex_missing_env_vars()
    if missing:
        return {
            "ok": False,
            "configured": False,
            "detail": f"Missing Yandex env vars: {', '.join(missing)}",
            "fetched": 0,
            "upserted": 0,
            "http_status": None,
            "errors": {"missing": missing},
        }

    response = _fetch_yandex_transaction_categories()
    categories = _extract_items(response["body"] if isinstance(response["body"], dict) else {}, ("categories", "items", "results"))

    upserted = 0
    for item in categories:
        external_category_id = str(item.get("id") or item.get("code") or item.get("name") or "")
        if not external_category_id:
            continue
        _, _created = YandexTransactionCategory.objects.update_or_create(
            connection=connection,
            external_category_id=external_category_id,
            defaults={
                "code": str(item.get("code") or ""),
                "name": str(item.get("name") or item.get("title") or external_category_id),
                "is_creatable": bool(item.get("is_creatable", False)),
                "is_enabled": bool(item.get("is_enabled", True)),
                "raw": item,
            },
        )
        upserted += 1

    return {
        "ok": bool(response["ok"]),
        "configured": True,
        "detail": "Category sync completed." if response["ok"] else "Category sync failed.",
        "fetched": len(categories),
        "upserted": upserted,
        "http_status": response["http_status"],
        "errors": None if response["ok"] else response["body"],
    }


def live_sync_yandex_data(
    *,
    connection: ProviderConnection,
    limit: int = 100,
    dry_run: bool = False,
    full_sync: bool = False,
    trigger: str = YandexSyncRun.Trigger.API,
):
    started_at = timezone.now()
    missing = _yandex_missing_env_vars()
    if missing:
        result = {
            "ok": False,
            "configured": False,
            "detail": f"Missing Yandex env vars: {', '.join(missing)}",
            "drivers": {"fetched": 0},
            "transactions": {"fetched": 0, "stored_new_events": 0, "imported_count": 0, "imported_total": "0.00"},
        }
        _record_yandex_sync_run(
            connection=connection,
            result=result,
            trigger=trigger,
            dry_run=dry_run,
            full_sync=full_sync,
            started_at=started_at,
            completed_at=timezone.now(),
        )
        return result

    drivers_response = _yandex_request(
        method="POST",
        endpoint="/v1/parks/driver-profiles/list",
        body={"query": {"park": {"id": settings.YANDEX_PARK_ID}}, "limit": limit},
    )
    sync_window = _build_sync_window(connection=connection, full_sync=full_sync)
    transactions_response = _fetch_live_transactions(limit=limit, window=sync_window)

    drivers = _extract_items(drivers_response["body"] if isinstance(drivers_response["body"], dict) else {}, ("driver_profiles", "profiles", "items"))
    transactions = _extract_items(
        transactions_response["body"] if isinstance(transactions_response["body"], dict) else {},
        ("transactions", "items", "results"),
    )

    stored_new = 0
    upserted_drivers = 0
    if not dry_run:
        for item in drivers:
            external_driver_id = _extract_driver_id(item)
            if not external_driver_id:
                continue
            first_name, last_name = _extract_driver_name_parts(item)
            _, _created = YandexDriverProfile.objects.update_or_create(
                connection=connection,
                external_driver_id=external_driver_id,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone_number": _extract_driver_phone(item),
                    "status": _extract_driver_status(item),
                    "raw": item,
                },
            )
            upserted_drivers += 1

        for item in transactions:
            normalized = _normalize_transaction_payload(item)
            external_id = normalized["external_id"]
            event, created = ExternalEvent.objects.get_or_create(
                connection=connection,
                external_id=external_id,
                defaults={"event_type": "earning", "payload": normalized, "processed": False},
            )
            if not created:
                # Keep normalized schema fresh even for existing events.
                event.payload = normalized
                event.save(update_fields=["payload"])
            if created:
                stored_new += 1

            YandexTransactionRecord.objects.update_or_create(
                connection=connection,
                external_transaction_id=external_id,
                defaults={
                    "external_event": event,
                    "driver_external_id": normalized.get("driver_id", ""),
                    "event_at": _extract_transaction_timestamp(item),
                    "amount": Decimal(normalized.get("net_amount", "0")),
                    "currency": normalized.get("currency", "GEL"),
                    "category": normalized.get("category", ""),
                    "direction": normalized.get("direction", ""),
                    "raw": item,
                },
            )

    import_result = {"imported_count": 0, "imported_total": "0.00"}
    if not dry_run:
        import_result = import_unprocessed_events(connection=connection)

    latest_event_at = None
    for item in transactions:
        parsed = _extract_transaction_timestamp(item)
        if parsed is not None and (latest_event_at is None or parsed > latest_event_at):
            latest_event_at = parsed
    if latest_event_at is None:
        latest_event_at = timezone.now()
    next_from = latest_event_at + timedelta(seconds=1)

    drivers_ok = bool(drivers_response["ok"])
    transactions_ok = bool(transactions_response["ok"])
    ok = transactions_ok
    partial = transactions_ok and not drivers_ok
    if drivers_ok and transactions_ok:
        detail = "Live sync completed."
    elif partial:
        detail = "Live sync completed for transactions, but driver sync failed."
    else:
        detail = "Live sync finished with API errors."

    result = {
        "ok": ok,
        "partial": partial,
        "configured": True,
        "detail": detail,
        "drivers": {
            "http_status": drivers_response["http_status"],
            "fetched": len(drivers),
            "upserted_profiles": upserted_drivers,
        },
        "transactions": {
            "http_status": transactions_response["http_status"],
            "fetched": len(transactions),
            "stored_new_events": stored_new,
            "imported_count": import_result["imported_count"],
            "imported_total": import_result["imported_total"],
        },
        "cursor": {
            "from": sync_window["from"],
            "to": sync_window["to"],
            "next_from": next_from.isoformat(),
            "full_sync": full_sync,
        },
        "errors": {
            "drivers": None if drivers_response["ok"] else drivers_response["body"],
            "transactions": None if transactions_response["ok"] else transactions_response["body"],
        },
    }
    _record_yandex_sync_run(
        connection=connection,
        result=result,
        trigger=trigger,
        dry_run=dry_run,
        full_sync=full_sync,
        started_at=started_at,
        completed_at=timezone.now(),
    )
    return result


def _record_yandex_sync_run(*, connection, result, trigger, dry_run, full_sync, started_at, completed_at):
    cursor = result.get("cursor") or {}
    cursor_from = parse_datetime(cursor["from"]) if isinstance(cursor.get("from"), str) else None
    cursor_to = parse_datetime(cursor["to"]) if isinstance(cursor.get("to"), str) else None
    cursor_next_from = parse_datetime(cursor["next_from"]) if isinstance(cursor.get("next_from"), str) else None

    status = YandexSyncRun.Status.ERROR
    if result.get("ok"):
        status = YandexSyncRun.Status.PARTIAL if result.get("partial") else YandexSyncRun.Status.OK

    imported_total = Decimal(str(result.get("transactions", {}).get("imported_total", "0")))
    YandexSyncRun.objects.create(
        connection=connection,
        trigger=trigger,
        status=status,
        dry_run=dry_run,
        full_sync=full_sync,
        drivers_http_status=result.get("drivers", {}).get("http_status"),
        transactions_http_status=result.get("transactions", {}).get("http_status"),
        drivers_fetched=result.get("drivers", {}).get("fetched", 0),
        drivers_upserted=result.get("drivers", {}).get("upserted_profiles", 0),
        transactions_fetched=result.get("transactions", {}).get("fetched", 0),
        transactions_stored_new=result.get("transactions", {}).get("stored_new_events", 0),
        imported_count=result.get("transactions", {}).get("imported_count", 0),
        imported_total=imported_total,
        cursor_from=cursor_from,
        cursor_to=cursor_to,
        cursor_next_from=cursor_next_from,
        detail=result.get("detail", ""),
        error_details=result.get("errors") or {},
        started_at=started_at,
        completed_at=completed_at,
    )


def _reverse_withdrawal_to_wallet(*, withdrawal: WithdrawalRequest, reason: str, idempotency_key: str, created_by):
    with transaction.atomic():
        locked_withdrawal = WithdrawalRequest.objects.select_for_update().select_related(
            "wallet", "wallet__user"
        ).get(id=withdrawal.id)
        if locked_withdrawal.status == WithdrawalRequest.Status.FAILED:
            return locked_withdrawal

        wallet = locked_withdrawal.wallet
        ledger_account = get_or_create_user_ledger_account(wallet.user, wallet.currency)
        locked_ledger_account = LedgerAccount.objects.select_for_update().get(id=ledger_account.id)
        current_balance = get_account_balance(locked_ledger_account, wallet.currency)

        create_ledger_entry(
            account=locked_ledger_account,
            amount=locked_withdrawal.amount,
            entry_type="withdrawal_reversal",
            created_by=created_by,
            reference_type="withdrawal",
            reference_id=str(locked_withdrawal.id),
            metadata={"description": reason},
            idempotency_key=idempotency_key,
        )
        wallet.balance = current_balance + locked_withdrawal.amount
        wallet.save(update_fields=["balance", "updated_at"])
        locked_withdrawal.status = WithdrawalRequest.Status.FAILED
        locked_withdrawal.save(update_fields=["status"])
        return locked_withdrawal


def submit_withdrawal_to_bog(*, connection: ProviderConnection, withdrawal: WithdrawalRequest):
    if BogPayout.objects.filter(withdrawal=withdrawal, provider_unique_key__isnull=False).exists():
        payout = BogPayout.objects.select_related("withdrawal").get(withdrawal=withdrawal)
        return payout, False

    missing = _bog_missing_payout_env_vars()
    if missing:
        raise ValueError(f"Missing BoG settings: {', '.join(missing)}")

    request_payload, unique_id = _build_bog_document_payload(withdrawal=withdrawal)
    response = _bog_request(
        connection=connection,
        method="POST",
        endpoint="/documents/domestic",
        body=request_payload,
    )

    body = response.get("body")
    response_items = body if isinstance(body, list) else []
    first_item = response_items[0] if response_items else {}
    unique_key = first_item.get("UniqueKey")
    result_code = first_item.get("ResultCode")
    match_score = first_item.get("Match")

    payout, created = BogPayout.objects.get_or_create(
        withdrawal=withdrawal,
        defaults={
            "connection": connection,
            "provider_unique_id": unique_id,
            "provider_unique_key": unique_key,
            "status": BogPayout.Status.ACCEPTED if response.get("ok") and unique_key else BogPayout.Status.FAILED,
            "result_code": result_code,
            "match_score": match_score,
            "request_payload": request_payload[0],
            "response_payload": first_item or body or {},
        },
    )

    if not created:
        payout.connection = connection
        payout.provider_unique_id = payout.provider_unique_id or unique_id
        payout.provider_unique_key = payout.provider_unique_key or unique_key
        payout.request_payload = request_payload[0]
        payout.response_payload = first_item or body or {}
        payout.result_code = result_code
        payout.match_score = match_score

    if response.get("ok") and unique_key:
        payout.status = BogPayout.Status.PROCESSING
        payout.failure_reason = ""
        payout.save(
            update_fields=[
                "connection",
                "provider_unique_id",
                "provider_unique_key",
                "request_payload",
                "response_payload",
                "result_code",
                "match_score",
                "status",
                "failure_reason",
                "updated_at",
            ]
        )
        if withdrawal.status == WithdrawalRequest.Status.PENDING:
            withdrawal.status = WithdrawalRequest.Status.PROCESSING
            withdrawal.save(update_fields=["status"])
        return payout, created

    failure_reason = f"BoG payout submission failed (HTTP {response.get('http_status') or 'n/a'})."
    payout.status = BogPayout.Status.FAILED
    payout.failure_reason = failure_reason
    payout.save(
        update_fields=[
            "connection",
            "provider_unique_id",
            "provider_unique_key",
            "request_payload",
            "response_payload",
            "result_code",
            "match_score",
            "status",
            "failure_reason",
            "updated_at",
        ]
    )
    _reverse_withdrawal_to_wallet(
        withdrawal=withdrawal,
        reason="BoG payout submission failed, amount returned to wallet",
        idempotency_key=f"bog:submit:reversal:{withdrawal.id}",
        created_by=connection.user,
    )
    raise ValueError(failure_reason)


def _map_bog_status(provider_status: str):
    normalized = (provider_status or "").strip().lower()
    if any(word in normalized for word in ("reject", "fail", "cancel", "error")):
        return BogPayout.Status.FAILED
    if any(word in normalized for word in ("complete", "execut", "success", "done", "finish")):
        return BogPayout.Status.SETTLED
    return BogPayout.Status.PROCESSING


def sync_bog_payout_status(*, payout: BogPayout):
    if not payout.provider_unique_key:
        raise ValueError("BoG payout does not have a provider document key yet.")

    response = _bog_request(
        connection=payout.connection,
        method="GET",
        endpoint=f"/documents/status/{payout.provider_unique_key}",
    )
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    provider_status = str(body.get("Status") or "")
    mapped_status = _map_bog_status(provider_status)

    with transaction.atomic():
        locked_payout = BogPayout.objects.select_for_update().select_related(
            "withdrawal", "withdrawal__wallet", "withdrawal__wallet__user", "connection"
        ).get(id=payout.id)
        locked_payout.provider_status = provider_status
        locked_payout.result_code = body.get("ResultCode")
        locked_payout.match_score = body.get("Match")
        locked_payout.response_payload = body
        locked_payout.last_status_checked_at = timezone.now()

        if response.get("ok"):
            locked_payout.status = mapped_status
            locked_payout.failure_reason = ""
        else:
            locked_payout.status = BogPayout.Status.FAILED
            locked_payout.failure_reason = f"BoG status sync failed (HTTP {response.get('http_status') or 'n/a'})."

        locked_payout.save(
            update_fields=[
                "provider_status",
                "result_code",
                "match_score",
                "response_payload",
                "last_status_checked_at",
                "status",
                "failure_reason",
                "updated_at",
            ]
        )

        withdrawal = locked_payout.withdrawal
        if locked_payout.status == BogPayout.Status.SETTLED:
            if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                withdrawal.status = WithdrawalRequest.Status.COMPLETED
                withdrawal.save(update_fields=["status"])
        elif locked_payout.status == BogPayout.Status.FAILED:
            _reverse_withdrawal_to_wallet(
                withdrawal=withdrawal,
                reason="BoG payout failed, amount returned to wallet",
                idempotency_key=f"bog:status:reversal:{locked_payout.id}",
                created_by=locked_payout.connection.user,
            )
        else:
            if withdrawal.status != WithdrawalRequest.Status.PROCESSING:
                withdrawal.status = WithdrawalRequest.Status.PROCESSING
                withdrawal.save(update_fields=["status"])

        return locked_payout


def sync_open_bog_payouts(*, connection: ProviderConnection):
    payouts = list(
        BogPayout.objects.select_related("withdrawal")
        .filter(connection=connection, status__in=[BogPayout.Status.ACCEPTED, BogPayout.Status.PROCESSING])
        .order_by("created_at")
    )

    updated = []
    errors = []
    for payout in payouts:
        try:
            updated.append(sync_bog_payout_status(payout=payout))
        except ValueError as exc:
            errors.append({"payout_id": payout.id, "detail": str(exc)})

    return {
        "checked_count": len(payouts),
        "updated_count": len(updated),
        "error_count": len(errors),
        "errors": errors,
    }


def submit_withdrawal_to_bank_simulator(*, connection: ProviderConnection, withdrawal: WithdrawalRequest):
    payout, created = BankSimulatorPayout.objects.get_or_create(
        withdrawal=withdrawal,
        defaults={
            "connection": connection,
            "provider_payout_id": f"banksim-{connection.id}-{withdrawal.id}",
            "status": BankSimulatorPayout.Status.ACCEPTED,
            "metadata": {"source": "bank_simulator"},
        },
    )

    # Ensure payout is bound to the same owner connection.
    if payout.connection_id != connection.id:
        raise ValueError("Withdrawal payout belongs to another simulator connection.")

    if withdrawal.status == WithdrawalRequest.Status.PENDING:
        withdrawal.status = WithdrawalRequest.Status.PROCESSING
        withdrawal.save(update_fields=["status"])

    return payout, created


def apply_bank_simulator_status_update(*, payout: BankSimulatorPayout, target_status: str, failure_reason: str = ""):
    with transaction.atomic():
        locked_payout = BankSimulatorPayout.objects.select_for_update().select_related(
            "withdrawal", "withdrawal__wallet", "withdrawal__wallet__user"
        ).get(id=payout.id)

        withdrawal = locked_payout.withdrawal
        if withdrawal.status == WithdrawalRequest.Status.COMPLETED and target_status in {
            BankSimulatorPayout.Status.FAILED,
            BankSimulatorPayout.Status.REVERSED,
        }:
            raise ValueError("Cannot fail or reverse a completed payout.")

        if locked_payout.status == target_status:
            return locked_payout

        locked_payout.status = target_status
        locked_payout.failure_reason = failure_reason
        locked_payout.save(update_fields=["status", "failure_reason", "updated_at"])

        if target_status in {
            BankSimulatorPayout.Status.ACCEPTED,
            BankSimulatorPayout.Status.PROCESSING,
        }:
            if withdrawal.status not in {
                WithdrawalRequest.Status.COMPLETED,
                WithdrawalRequest.Status.FAILED,
            }:
                withdrawal.status = WithdrawalRequest.Status.PROCESSING
                withdrawal.save(update_fields=["status"])
            return locked_payout

        if target_status == BankSimulatorPayout.Status.SETTLED:
            withdrawal.status = WithdrawalRequest.Status.COMPLETED
            withdrawal.save(update_fields=["status"])
            return locked_payout

        if target_status in {BankSimulatorPayout.Status.FAILED, BankSimulatorPayout.Status.REVERSED}:
            if withdrawal.status != WithdrawalRequest.Status.FAILED:
                wallet = withdrawal.wallet
                ledger_account = get_or_create_user_ledger_account(wallet.user, wallet.currency)
                create_ledger_entry(
                    account=ledger_account,
                    amount=withdrawal.amount,
                    entry_type="withdrawal_reversal",
                    created_by=wallet.user,
                    reference_type="withdrawal",
                    reference_id=str(withdrawal.id),
                    metadata={
                        "description": "Bank simulator marked payout failed/reversed",
                        "provider_payout_id": locked_payout.provider_payout_id,
                    },
                    idempotency_key=f"banksim:reversal:{locked_payout.id}",
                )
                wallet.balance = wallet.balance + withdrawal.amount
                wallet.save(update_fields=["balance", "updated_at"])
                withdrawal.status = WithdrawalRequest.Status.FAILED
                withdrawal.save(update_fields=["status"])
            return locked_payout

        return locked_payout


def build_reconciliation_report(*, user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    ledger_account = get_or_create_user_ledger_account(user, wallet.currency)
    ensure_opening_entry(ledger_account, wallet.balance, created_by=user)
    ledger_balance = get_account_balance(ledger_account, wallet.currency)

    yandex_connection = ProviderConnection.objects.filter(
        user=user, provider=ProviderConnection.Provider.YANDEX
    ).first()
    if yandex_connection:
        yandex = reconciliation_summary(connection=yandex_connection)
        yandex_config = yandex_connection.config or {}
        yandex["last_connection_test"] = yandex_config.get("last_connection_test")
        yandex["last_live_sync"] = yandex_config.get("last_live_sync")
        yandex["last_category_sync"] = yandex_config.get("last_category_sync")
        yandex["last_transaction_cursor"] = yandex_config.get("last_transaction_cursor")
        yandex["stored_driver_profiles"] = YandexDriverProfile.objects.filter(connection=yandex_connection).count()
        yandex["stored_transactions"] = YandexTransactionRecord.objects.filter(connection=yandex_connection).count()
        yandex["stored_categories"] = YandexTransactionCategory.objects.filter(connection=yandex_connection).count()
        yandex["sync_runs_count"] = YandexSyncRun.objects.filter(connection=yandex_connection).count()
    else:
        yandex = {
            "imported_events": 0,
            "imported_total": "0.00",
            "ledger_total": "0.00",
            "delta": "0.00",
            "status": "OK",
            "last_connection_test": None,
            "last_live_sync": None,
            "last_category_sync": None,
            "last_transaction_cursor": None,
            "stored_driver_profiles": 0,
            "stored_transactions": 0,
            "stored_categories": 0,
            "sync_runs_count": 0,
        }

    withdrawals = WithdrawalRequest.objects.filter(user=user)
    withdrawals_total = withdrawals.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    withdrawals_completed = (
        withdrawals.filter(status=WithdrawalRequest.Status.COMPLETED).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    withdrawals_pending = (
        withdrawals.filter(status__in=[WithdrawalRequest.Status.PENDING, WithdrawalRequest.Status.PROCESSING]).aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )
    withdrawals_failed = (
        withdrawals.filter(status=WithdrawalRequest.Status.FAILED).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    payouts = BankSimulatorPayout.objects.filter(withdrawal__user=user)
    payouts_by_status = {
        status_key: str(
            payouts.filter(status=status_key).aggregate(total=Sum("withdrawal__amount"))["total"] or Decimal("0.00")
        )
        for status_key in [
            BankSimulatorPayout.Status.ACCEPTED,
            BankSimulatorPayout.Status.PROCESSING,
            BankSimulatorPayout.Status.SETTLED,
            BankSimulatorPayout.Status.FAILED,
            BankSimulatorPayout.Status.REVERSED,
        ]
    }
    bog_payouts = BogPayout.objects.filter(withdrawal__user=user)
    bog_payouts_by_status = {
        status_key: str(
            bog_payouts.filter(status=status_key).aggregate(total=Sum("withdrawal__amount"))["total"] or Decimal("0.00")
        )
        for status_key in [
            BogPayout.Status.ACCEPTED,
            BogPayout.Status.PROCESSING,
            BogPayout.Status.SETTLED,
            BogPayout.Status.FAILED,
            BogPayout.Status.REVERSED,
        ]
    }

    wallet_delta = ledger_balance - wallet.balance

    return {
        "currency": wallet.currency,
        "wallet": {
            "wallet_balance": str(wallet.balance),
            "ledger_balance": str(ledger_balance),
            "delta": str(wallet_delta),
            "status": "OK" if wallet_delta == Decimal("0.00") else "MISMATCH",
        },
        "yandex": yandex,
        "withdrawals": {
            "count": withdrawals.count(),
            "total": str(withdrawals_total),
            "completed_total": str(withdrawals_completed),
            "pending_total": str(withdrawals_pending),
            "failed_total": str(withdrawals_failed),
        },
        "bank_simulator": {
            "count": payouts.count(),
            "totals_by_status": payouts_by_status,
        },
        "bog": {
            "count": bog_payouts.count(),
            "totals_by_status": bog_payouts_by_status,
        },
        "generated_at": timezone.now().isoformat(),
        "overall_status": "OK"
        if wallet_delta == Decimal("0.00") and yandex.get("status") == "OK"
        else "MISMATCH",
    }
