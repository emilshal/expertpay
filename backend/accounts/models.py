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
        unique_together = ("fleet", "phone_number")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.fleet.name}:{self.phone_number}"


class LoginCodeChallenge(models.Model):
    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="login_challenges")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_challenges")
    phone_number = models.CharField(max_length=32)
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    is_consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def is_valid(self):
        return (not self.is_consumed) and self.expires_at > timezone.now()
