from django.contrib import admin

from .models import Fleet, FleetPhoneBinding, LoginCodeChallenge


@admin.register(Fleet)
class FleetAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)


@admin.register(FleetPhoneBinding)
class FleetPhoneBindingAdmin(admin.ModelAdmin):
    list_display = ("fleet", "user", "phone_number", "role", "is_active", "created_at")
    search_fields = ("fleet__name", "user__username", "phone_number")
    list_filter = ("is_active", "role", "fleet")


@admin.register(LoginCodeChallenge)
class LoginCodeChallengeAdmin(admin.ModelAdmin):
    list_display = ("id", "fleet", "user", "phone_number", "is_consumed", "expires_at", "created_at")
    search_fields = ("fleet__name", "user__username", "phone_number")
    list_filter = ("is_consumed", "fleet")

# Register your models here.
