from django.db import models

from django.conf import settings


class ProviderConnection(models.Model):
    class Provider(models.TextChoices):
        YANDEX = "yandex", "Yandex"
        BANK_SIMULATOR = "bank_sim", "Bank Simulator"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="provider_connections")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    external_account_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="active")
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("provider", "external_account_id")

    def __str__(self):
        return f"{self.provider}:{self.external_account_id}"


class ExternalEvent(models.Model):
    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE, related_name="events")
    external_id = models.CharField(max_length=120)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("connection", "external_id")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.connection_id}:{self.external_id}:{self.event_type}"

# Create your models here.
