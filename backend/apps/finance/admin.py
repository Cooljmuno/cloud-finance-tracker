from django.contrib import admin

from .models import Category, FinancialAccount, Transaction


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "account_type", "currency", "is_active")
    list_filter = ("account_type", "currency", "is_active")
    search_fields = ("name", "institution", "owner__username", "owner__email")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "kind", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "owner__username", "owner__email")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("transaction_date", "description", "owner", "account", "amount", "status")
    list_filter = ("status", "transaction_date")
    search_fields = ("description", "account__name", "owner__username", "owner__email")
    autocomplete_fields = ("owner", "account", "category")
