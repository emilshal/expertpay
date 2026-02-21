from django.contrib import admin

from .models import LedgerAccount, LedgerEntry


@admin.register(LedgerAccount)
class LedgerAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "account_type", "name", "currency", "is_active", "updated_at")
    search_fields = ("user__username", "name")
    list_filter = ("account_type", "currency", "is_active")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "account", "amount", "currency", "entry_type", "reference_type", "created_at")
    search_fields = ("account__user__username", "entry_type", "reference_type", "reference_id")
    list_filter = ("currency", "entry_type")
    readonly_fields = ("created_at",)

# Register your models here.
