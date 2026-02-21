from django.db import models

from django.conf import settings


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=80, blank=True)
    resource_id = models.CharField(max_length=80, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} ({self.resource_type}:{self.resource_id})"


class IdempotencyRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="idempotency_records")
    method = models.CharField(max_length=12)
    endpoint = models.CharField(max_length=255)
    key = models.CharField(max_length=120)
    request_hash = models.CharField(max_length=64)
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "method", "endpoint", "key")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}:{self.method}:{self.endpoint}:{self.key}"
