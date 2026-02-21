from django.contrib import admin

from .models import AuditLog, IdempotencyRecord


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "resource_type", "resource_id", "user", "request_id", "created_at")
    list_filter = ("action", "resource_type")
    search_fields = ("resource_id", "request_id", "user__username")


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "method", "endpoint", "key", "response_code", "updated_at")
    list_filter = ("method", "endpoint", "response_code")
    search_fields = ("user__username", "key", "endpoint")

# Register your models here.
