from django.db import models

from django.conf import settings
from wallet.models import WithdrawalRequest


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


class YandexDriverProfile(models.Model):
    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE, related_name="yandex_driver_profiles")
    external_driver_id = models.CharField(max_length=120)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    phone_number = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=40, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("connection", "external_driver_id")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.connection_id}:{self.external_driver_id}"


class YandexTransactionRecord(models.Model):
    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE, related_name="yandex_transactions")
    external_event = models.OneToOneField(
        ExternalEvent,
        on_delete=models.CASCADE,
        related_name="yandex_transaction_record",
    )
    external_transaction_id = models.CharField(max_length=120)
    driver_external_id = models.CharField(max_length=120, blank=True)
    event_at = models.DateTimeField(null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=6)
    currency = models.CharField(max_length=8, default="GEL")
    category = models.CharField(max_length=80, blank=True)
    direction = models.CharField(max_length=20, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("connection", "external_transaction_id")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.connection_id}:{self.external_transaction_id}"


class BankSimulatorPayout(models.Model):
    class Status(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        PROCESSING = "processing", "Processing"
        SETTLED = "settled", "Settled"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE, related_name="bank_payouts")
    withdrawal = models.OneToOneField(
        WithdrawalRequest, on_delete=models.CASCADE, related_name="bank_simulator_payout"
    )
    provider_payout_id = models.CharField(max_length=120, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACCEPTED)
    failure_reason = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider_payout_id}:{self.status}"
