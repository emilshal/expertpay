from django.contrib import admin

from .models import BankAccount, Transaction, Wallet, WithdrawalRequest


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "currency", "updated_at")
    search_fields = ("user__username", "user__email")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "bank_name", "account_number", "beneficiary_name", "is_active", "created_at")
    list_filter = ("is_active", "bank_name")
    search_fields = ("user__username", "beneficiary_name", "account_number")


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "bank_account", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("user__username", "bank_account__account_number")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "kind", "amount", "currency", "status", "created_at")
    list_filter = ("kind", "status", "currency")
    search_fields = ("wallet__user__username", "description")

# Register your models here.
