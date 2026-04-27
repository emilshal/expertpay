from django.contrib import admin

from .models import DriverFleetMembership, Fleet, FleetPhoneBinding, LoginCodeChallenge


@admin.register(Fleet)
class FleetAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "bog_source_account_number", "created_at")
    search_fields = ("name", "bog_source_account_number")


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


@admin.register(DriverFleetMembership)
class DriverFleetMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "fleet", "yandex_external_driver_id", "is_active", "updated_at")
    search_fields = ("user__username", "fleet__name", "yandex_external_driver_id")
    list_filter = ("is_active", "fleet")

# Register your models here.
