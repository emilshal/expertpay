from django.contrib import admin

from .models import ExternalEvent, ProviderConnection


@admin.register(ProviderConnection)
class ProviderConnectionAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "external_account_id", "user", "status", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("external_account_id", "user__username")


@admin.register(ExternalEvent)
class ExternalEventAdmin(admin.ModelAdmin):
    list_display = ("id", "connection", "external_id", "event_type", "processed", "created_at")
    list_filter = ("event_type", "processed", "connection__provider")
    search_fields = ("external_id", "connection__external_account_id", "connection__user__username")
