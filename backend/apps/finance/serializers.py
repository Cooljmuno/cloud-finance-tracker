from django.db.models import Q
from rest_framework import serializers

from .models import Category, FinancialAccount, Transaction


def normalize_name(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise serializers.ValidationError("This field may not be blank.")
    return normalized


class FinancialAccountSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(max_length=3, required=False, default="USD")

    class Meta:
        model = FinancialAccount
        fields = [
            "id",
            "name",
            "account_type",
            "institution",
            "currency",
            "opening_balance",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        return normalize_name(value)

    def validate_currency(self, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha() or not normalized.isascii():
            raise serializers.ValidationError("Use a three-letter currency code such as USD.")
        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context["request"]
        name = attrs.get("name", getattr(self.instance, "name", None))

        duplicate = FinancialAccount.objects.filter(owner=request.user, name__iexact=name)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"name": "You already have an account with this name."}
            )

        return attrs


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "kind", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        return normalize_name(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context["request"]
        name = attrs.get("name", getattr(self.instance, "name", None))

        duplicate = Category.objects.filter(owner=request.user, name__iexact=name)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"name": "You already have a category with this name."}
            )

        return attrs


class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    currency = serializers.CharField(source="account.currency", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "account",
            "account_name",
            "currency",
            "category",
            "category_name",
            "transaction_date",
            "description",
            "amount",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "account_name",
            "currency",
            "category_name",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            active_or_current_account = Q(is_active=True)
            active_or_current_category = Q(is_active=True)
            if isinstance(self.instance, Transaction):
                active_or_current_account |= Q(pk=self.instance.account_id)
                if self.instance.category_id:
                    active_or_current_category |= Q(pk=self.instance.category_id)

            self.fields["account"].queryset = FinancialAccount.objects.filter(
                owner=request.user,
            ).filter(active_or_current_account)
            self.fields["category"].queryset = Category.objects.filter(
                owner=request.user,
            ).filter(active_or_current_category)
        else:
            self.fields["account"].queryset = FinancialAccount.objects.none()
            self.fields["category"].queryset = Category.objects.none()

    def validate_description(self, value: str) -> str:
        return normalize_name(value)

    def validate_amount(self, value):
        if value == 0:
            raise serializers.ValidationError("Amount must be nonzero.")
        return value
