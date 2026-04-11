from django.conf import settings
from django.db import models

from accounts.models import Fleet


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="GEL")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet<{self.user_id}> {self.balance} {self.currency}"


class BankAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_accounts")
    bank_name = models.CharField(max_length=80)
    account_number = models.CharField(max_length=64)
    beneficiary_name = models.CharField(max_length=140)
    beneficiary_inn = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.bank_name} ({self.account_number})"


class Transaction(models.Model):
    class Kind(models.TextChoices):
        WITHDRAWAL = "withdrawal", "Withdrawal"
        INTERNAL_TRANSFER = "internal_transfer", "Internal Transfer"
        ADJUSTMENT = "adjustment", "Adjustment"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="GEL")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} {self.amount} {self.currency} ({self.status})"


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="withdrawals")
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="withdrawals")
    fleet = models.ForeignKey(
        Fleet,
        on_delete=models.SET_NULL,
        related_name="withdrawals",
        null=True,
        blank=True,
    )
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="withdrawals")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="GEL")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Withdrawal<{self.user_id}> {self.amount} {self.currency} ({self.status})"


class FleetRatingPenalty(models.Model):
    class Reason(models.TextChoices):
        INSUFFICIENT_RESERVE = "insufficient_reserve", "Insufficient Reserve"

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="rating_penalties")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="fleet_rating_penalties",
        null=True,
        blank=True,
    )
    reason = models.CharField(max_length=32, choices=Reason.choices, default=Reason.INSUFFICIENT_RESERVE)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"FleetRatingPenalty<{self.fleet_id}> {self.reason}"


class IncomingBankTransfer(models.Model):
    class MatchStatus(models.TextChoices):
        MATCHED = "matched", "Matched"
        UNMATCHED = "unmatched", "Unmatched"
        IGNORED = "ignored", "Ignored"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="incoming_bank_transfers",
        null=True,
        blank=True,
    )
    fleet = models.ForeignKey(
        Fleet,
        on_delete=models.SET_NULL,
        related_name="incoming_bank_transfers",
        null=True,
        blank=True,
    )
    provider = models.CharField(max_length=32, default="bog")
    provider_transaction_id = models.CharField(max_length=120, unique=True)
    account_number = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=8, default="GEL")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference_text = models.TextField(blank=True)
    payer_name = models.CharField(max_length=140, blank=True)
    payer_inn = models.CharField(max_length=32, blank=True)
    payer_account_number = models.CharField(max_length=64, blank=True)
    booking_date = models.DateField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    match_status = models.CharField(max_length=16, choices=MatchStatus.choices, default=MatchStatus.UNMATCHED)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider}:{self.provider_transaction_id}:{self.amount} {self.currency}"


class Deposit(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="deposits",
        null=True,
        blank=True,
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.SET_NULL,
        related_name="deposits",
        null=True,
        blank=True,
    )
    fleet = models.ForeignKey(
        Fleet,
        on_delete=models.SET_NULL,
        related_name="deposits",
        null=True,
        blank=True,
    )
    incoming_transfer = models.OneToOneField(
        IncomingBankTransfer,
        on_delete=models.SET_NULL,
        related_name="deposit",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="GEL")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.COMPLETED)
    reference_code = models.CharField(max_length=32)
    provider = models.CharField(max_length=32, default="bog")
    provider_transaction_id = models.CharField(max_length=120, unique=True)
    payer_name = models.CharField(max_length=140, blank=True)
    payer_inn = models.CharField(max_length=32, blank=True)
    payer_account_number = models.CharField(max_length=64, blank=True)
    note = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        subject = f"fleet={self.fleet_id}" if self.fleet_id else f"user={self.user_id}"
        return f"Deposit<{subject}> {self.amount} {self.currency} ({self.status})"
