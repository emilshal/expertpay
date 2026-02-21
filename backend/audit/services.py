import hashlib
import json

from django.db import transaction

from .models import AuditLog, IdempotencyRecord


def _request_hash(payload):
    payload_str = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def _json_safe(value):
    return json.loads(json.dumps(value, default=str))


def begin_idempotent_request(*, user, method, endpoint, key, payload):
    if not key:
        return None, {"detail": "Idempotency-Key header is required."}, 400

    payload_hash = _request_hash(payload)

    with transaction.atomic():
        record, created = IdempotencyRecord.objects.select_for_update().get_or_create(
            user=user,
            method=method,
            endpoint=endpoint,
            key=key,
            defaults={"request_hash": payload_hash},
        )

        if created:
            return record, None, None

        if record.request_hash != payload_hash:
            return None, {"detail": "Idempotency-Key already used with different payload."}, 409

        if record.response_code is not None:
            return record, _json_safe(record.response_body), record.response_code

        return None, {"detail": "Request with this Idempotency-Key is currently being processed."}, 409


def finalize_idempotent_request(record, *, status_code, response_body):
    if record is None:
        return
    record.response_code = status_code
    record.response_body = _json_safe(response_body)
    record.save(update_fields=["response_code", "response_body", "updated_at"])


def log_audit(*, user, action, resource_type="", resource_id="", request_id="", ip_address=None, metadata=None):
    AuditLog.objects.create(
        user=user,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else "",
        request_id=request_id,
        ip_address=ip_address,
        metadata=metadata or {},
    )
