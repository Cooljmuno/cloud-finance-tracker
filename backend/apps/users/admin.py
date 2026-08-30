from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Cloud Finance Tracker",
            {"fields": ("id", "cognito_sub", "created_at", "updated_at")},
        ),
    )
