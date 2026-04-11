from django.db import models

from django.conf import settings
from accounts.models import Fleet
from wallet.models import WithdrawalRequest


class ProviderConnection(models.Model):
    class Provider(models.TextChoices):
        YANDEX = "yandex", "Yandex"
        BANK_OF_GEORGIA = "bog", "Bank of Georgia"
        BOG_PAYMENTS = "bog_payments", "BoG Payments"
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


class YandexTransactionCategory(models.Model):
    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE, related_name="yandex_categories")
    external_category_id = models.CharField(max_length=120)
    code = models.CharField(max_length=120, blank=True)
    name = models.CharField(max_length=200)
    is_creatable = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("connection", "external_category_id")
        ordering = ["name"]

    def __str__(self):
        return f"{self.connection_id}:{self.external_category_id}:{self.name}"


class YandexSyncRun(models.Model):
    class Status(models.TextChoices):
        OK = "ok", "OK"
        PARTIAL = "partial", "Partial"
        ERROR = "error", "Error"

    class Trigger(models.TextChoices):
        API = "api", "API"
        SCHEDULER = "scheduler", "Scheduler"

    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE, related_name="yandex_sync_runs")
    trigger = models.CharField(max_length=20, choices=Trigger.choices, default=Trigger.API)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ERROR)
    dry_run = models.BooleanField(default=False)
    full_sync = models.BooleanField(default=False)
    drivers_http_status = models.IntegerField(null=True, blank=True)
    transactions_http_status = models.IntegerField(null=True, blank=True)
    drivers_fetched = models.IntegerField(default=0)
    drivers_upserted = models.IntegerField(default=0)
    transactions_fetched = models.IntegerField(default=0)
    transactions_stored_new = models.IntegerField(default=0)
    imported_count = models.IntegerField(default=0)
    imported_total = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    cursor_from = models.DateTimeField(null=True, blank=True)
    cursor_to = models.DateTimeField(null=True, blank=True)
    cursor_next_from = models.DateTimeField(null=True, blank=True)
    detail = models.CharField(max_length=255, blank=True)
    error_details = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.connection_id}:{self.status}:{self.created_at.isoformat()}"


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


class BogPayout(models.Model):
    class Status(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        PROCESSING = "processing", "Processing"
        SETTLED = "settled", "Settled"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE, related_name="bog_payouts")
    withdrawal = models.OneToOneField(
        WithdrawalRequest, on_delete=models.CASCADE, related_name="bog_payout"
    )
    provider_unique_id = models.CharField(max_length=120, blank=True)
    provider_unique_key = models.BigIntegerField(null=True, blank=True, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACCEPTED)
    provider_status = models.CharField(max_length=120, blank=True)
    result_code = models.IntegerField(null=True, blank=True)
    match_score = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    last_status_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"bog:{self.withdrawal_id}:{self.status}"


class BogCardOrder(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    connection = models.ForeignKey(ProviderConnection, on_delete=models.CASCADE, related_name="bog_card_orders")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bog_card_orders")
    fleet = models.ForeignKey(
        Fleet,
        on_delete=models.SET_NULL,
        related_name="bog_card_orders",
        null=True,
        blank=True,
    )
    provider_order_id = models.CharField(max_length=120, unique=True)
    external_order_id = models.CharField(max_length=120, db_index=True)
    parent_order_id = models.CharField(max_length=120, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="GEL")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    provider_order_status = models.CharField(max_length=80, blank=True)
    redirect_url = models.TextField(blank=True)
    details_url = models.TextField(blank=True)
    callback_url = models.TextField(blank=True)
    success_url = models.TextField(blank=True)
    fail_url = models.TextField(blank=True)
    save_card = models.BooleanField(default=False)
    transaction_id = models.CharField(max_length=120, blank=True)
    payer_identifier = models.CharField(max_length=64, blank=True)
    transfer_method = models.CharField(max_length=32, blank=True)
    card_type = models.CharField(max_length=32, blank=True)
    raw_request = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    latest_details = models.JSONField(default=dict, blank=True)
    latest_callback = models.JSONField(default=dict, blank=True)
    callback_received_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"bog-card:{self.user_id}:{self.provider_order_id}:{self.status}"
