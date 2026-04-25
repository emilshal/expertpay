from django.db import models

from django.contrib.auth.models import User
from django.utils import timezone


class Fleet(models.Model):
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class FleetPhoneBinding(models.Model):
    class Role(models.TextChoices):
        DRIVER = "driver", "Driver"
        OPERATOR = "operator", "Operator"
        ADMIN = "admin", "Admin"
        OWNER = "owner", "Owner"

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="phone_bindings")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="fleet_phone_bindings")
    phone_number = models.CharField(max_length=32)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DRIVER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("fleet", "phone_number", "role")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.fleet.name}:{self.phone_number}"


class LoginCodeChallenge(models.Model):
    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="login_challenges")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_challenges")
    phone_number = models.CharField(max_length=32)
    code = models.CharField(max_length=6)
    provider = models.CharField(max_length=32, default="local")
    provider_hash = models.CharField(max_length=255, blank=True, default="")
    requested_role = models.CharField(max_length=20, blank=True, default="")
    expires_at = models.DateTimeField()
    is_consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def is_valid(self):
        return (not self.is_consumed) and self.expires_at > timezone.now()


class DriverFleetMembership(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="driver_fleet_membership")
    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="driver_memberships")
    yandex_external_driver_id = models.CharField(max_length=120, blank=True, null=True, unique=True)
    yandex_display_name = models.CharField(max_length=180, blank=True)
    yandex_phone_number = models.CharField(max_length=40, blank=True)
    yandex_current_balance = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    yandex_balance_currency = models.CharField(max_length=8, default="GEL")
    yandex_raw = models.JSONField(default=dict, blank=True)
    last_yandex_sync_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fleet__name", "user__username"]

    def __str__(self):
        return f"{self.user.username}:{self.fleet.name}"
