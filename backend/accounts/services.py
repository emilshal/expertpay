import json
import logging
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)

LOCAL_OTP_PROVIDER = "local"
GOSMS_OTP_PROVIDER = "gosms"
VERIFY_GE_OTP_PROVIDER = "verify_ge"


class OtpDeliveryError(Exception):
    def __init__(self, detail: str, *, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _normalize_provider_name(value: str) -> str:
    normalized = (value or LOCAL_OTP_PROVIDER).strip().lower()
    normalized = normalized.replace(".", "_").replace("-", "_").replace(" ", "_")
    if normalized in {"verifyge", "verify_ge"}:
        return VERIFY_GE_OTP_PROVIDER
    return normalized or LOCAL_OTP_PROVIDER


def _effective_otp_provider() -> str:
    configured = _normalize_provider_name(settings.OTP_PROVIDER)
    if configured == LOCAL_OTP_PROVIDER and settings.OTP_API_KEY:
        return VERIFY_GE_OTP_PROVIDER
    return configured or LOCAL_OTP_PROVIDER


def _fixed_test_codes() -> dict[str, str]:
    codes = {}
    for item in (settings.OTP_TEST_FIXED_CODES or "").split(","):
        if ":" not in item:
            continue
        phone_number, code = item.split(":", 1)
        normalized_phone = normalize_phone_number(phone_number)[-9:]
        normalized_code = "".join(ch for ch in code if ch.isdigit())
        if normalized_phone and normalized_code:
            codes[normalized_phone] = normalized_code
    return codes


def _fixed_test_code_for(phone_number: str) -> str:
    normalized_phone = normalize_phone_number(phone_number)[-9:]
    return _fixed_test_codes().get(normalized_phone, "")


def is_internal_admin_phone(phone_number: str) -> bool:
    normalized_phone = normalize_phone_number(phone_number)[-9:]
    allowed = {
        normalize_phone_number(item)[-9:]
        for item in (settings.OTP_INTERNAL_ADMIN_PHONES or "").split(",")
        if item.strip()
    }
    return bool(normalized_phone and normalized_phone in allowed)


def normalize_phone_number(phone_number: str) -> str:
    digits = "".join(ch for ch in str(phone_number or "") if ch.isdigit())
    if digits.startswith("995") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        digits = digits[1:]
    if len(digits) == 9 and digits.startswith("5"):
        return f"995{digits}"
    return digits


def generate_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def send_login_code(*, phone_number: str) -> dict:
    fixed_code = _fixed_test_code_for(phone_number)
    if fixed_code:
        logger.info("Using fixed test OTP code for %s", phone_number)
        return {
            "provider": LOCAL_OTP_PROVIDER,
            "provider_hash": "",
            "code": fixed_code,
        }

    provider = _effective_otp_provider()
    if provider == VERIFY_GE_OTP_PROVIDER:
        return _send_verify_ge_otp(phone_number=phone_number)
    if provider == GOSMS_OTP_PROVIDER:
        return _send_gosms_otp(phone_number=phone_number)

    code = generate_login_code()
    logger.info("Generated local OTP code for %s", phone_number)
    return {
        "provider": LOCAL_OTP_PROVIDER,
        "provider_hash": "",
        "code": code,
    }


def verify_login_code(
    *,
    provider: str,
    phone_number: str,
    provider_hash: str,
    stored_code: str,
    submitted_code: str,
    ip_address: str = "",
) -> bool:
    normalized_provider = _normalize_provider_name(provider)
    if normalized_provider == VERIFY_GE_OTP_PROVIDER:
        return _verify_verify_ge_otp(
            provider_request_id=provider_hash,
            submitted_code=submitted_code,
            ip_address=ip_address,
        )
    if normalized_provider == GOSMS_OTP_PROVIDER:
        return _verify_gosms_otp(
            phone_number=phone_number,
            provider_hash=provider_hash,
            submitted_code=submitted_code,
        )
    return secrets.compare_digest(stored_code or "", submitted_code or "")


def _gosms_request(*, endpoint: str, body: dict) -> tuple[dict, int]:
    request = Request(
        url=f"{settings.OTP_BASE_URL.rstrip('/')}{endpoint}",
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=settings.OTP_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, getattr(response, "status", 200)
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            payload = {"raw": body_text[:2000]} if body_text else {}
        return payload, exc.code
    except URLError as exc:
        raise OtpDeliveryError(f"OTP provider network error: {exc.reason}", status_code=502) from exc


def _otp_provider_error_detail(payload: dict, *, fallback: str) -> str:
    if not isinstance(payload, dict):
        return fallback

    for key in ("message", "Message", "error", "detail", "raw"):
        value = payload.get(key)
        if value:
            return str(value)

    code = payload.get("code") or payload.get("errorCode")
    if code:
        return f"{fallback} (provider code {code})"
    return fallback


def _send_gosms_otp(*, phone_number: str) -> dict:
    if not settings.OTP_API_KEY:
        raise OtpDeliveryError("OTP provider key is missing.", status_code=503)

    normalized_phone = normalize_phone_number(phone_number)
    payload, status_code = _gosms_request(
        endpoint="/otp/send",
        body={
            "api_key": settings.OTP_API_KEY,
            "phone": normalized_phone,
        },
    )

    if not payload.get("success") or not payload.get("hash"):
        error_code = str(payload.get("code") or payload.get("errorCode") or "")
        error_status = 429 if error_code in {"109", "110"} else 502
        detail = _otp_provider_error_detail(payload, fallback="OTP send failed.")
        raise OtpDeliveryError(detail, status_code=error_status)

    return {
        "provider": GOSMS_OTP_PROVIDER,
        "provider_hash": str(payload.get("hash") or ""),
        "code": "",
    }


def _verify_gosms_otp(*, phone_number: str, provider_hash: str, submitted_code: str) -> bool:
    if not settings.OTP_API_KEY or not provider_hash:
        return False

    normalized_phone = normalize_phone_number(phone_number)
    payload, _status_code = _gosms_request(
        endpoint="/otp/verify",
        body={
            "api_key": settings.OTP_API_KEY,
            "phone": normalized_phone,
            "hash": provider_hash,
            "code": submitted_code,
        },
    )
    return bool(payload.get("success")) and bool(payload.get("verify"))


def _verify_ge_request(*, endpoint: str, method: str = "POST", body: dict | None = None) -> tuple[dict, int]:
    request = Request(
        url=f"{settings.OTP_BASE_URL.rstrip('/')}{endpoint}",
        method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={
            "X-API-Key": settings.OTP_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=settings.OTP_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, getattr(response, "status", 200)
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            payload = {"raw": body_text[:2000]} if body_text else {}
        return payload, exc.code
    except URLError as exc:
        raise OtpDeliveryError(f"OTP provider network error: {exc.reason}", status_code=502) from exc


def _send_verify_ge_otp(*, phone_number: str) -> dict:
    if not settings.OTP_API_KEY:
        raise OtpDeliveryError("OTP provider key is missing.", status_code=503)

    delivery_phone_number = settings.OTP_TEST_PHONE_NUMBER or phone_number
    normalized_phone = normalize_phone_number(delivery_phone_number)
    phone_with_plus = f"+{normalized_phone}" if normalized_phone and not normalized_phone.startswith("+") else normalized_phone
    payload, status_code = _verify_ge_request(
        endpoint="/otp/send",
        body={
            "phoneNumber": phone_with_plus,
            "channel": "SMS",
            "ttl": settings.OTP_CODE_TTL_SECONDS,
            "length": settings.OTP_CODE_LENGTH,
        },
    )

    request_id = (
        payload.get("requestId")
        or payload.get("request_id")
        or payload.get("id")
    )
    if not payload.get("success") or not request_id:
        error_status = 429 if status_code == 429 else 502
        detail = _otp_provider_error_detail(payload, fallback="OTP send failed.")
        raise OtpDeliveryError(detail, status_code=error_status)

    return {
        "provider": VERIFY_GE_OTP_PROVIDER,
        "provider_hash": str(request_id),
        "code": "",
    }


def _verify_verify_ge_otp(*, provider_request_id: str, submitted_code: str, ip_address: str) -> bool:
    if not settings.OTP_API_KEY or not provider_request_id:
        return False

    body = {
        "requestId": provider_request_id,
        "code": submitted_code,
    }
    if ip_address:
        body["ipAddress"] = ip_address

    payload, _status_code = _verify_ge_request(
        endpoint="/otp/verify",
        body=body,
    )
    return bool(payload.get("success")) and bool(
        payload.get("verified", True) if "verified" in payload else payload.get("success")
    )
