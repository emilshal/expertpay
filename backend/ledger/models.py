from django.conf import settings
from django.db import models


class LedgerAccount(models.Model):
    class AccountType(models.TextChoices):
        USER_WALLET = "user_wallet", "User Wallet"
        SYSTEM = "system", "System"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ledger_account", null=True, blank=True
    )
    account_type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.USER_WALLET)
    name = models.CharField(max_length=64, default="main")
    currency = models.CharField(max_length=3, default="GEL")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        owner = self.user.username if self.user else "system"
        return f"{owner}:{self.name}:{self.currency}"


class LedgerEntry(models.Model):
    account = models.ForeignKey(LedgerAccount, on_delete=models.CASCADE, related_name="entries")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="GEL")
    entry_type = models.CharField(max_length=40)
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=100, blank=True, null=True, unique=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="created_ledger_entries", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["entry_type"]),
        ]

    def __str__(self):
        return f"{self.account_id} {self.amount} {self.currency} {self.entry_type}"

# Create your models here.
