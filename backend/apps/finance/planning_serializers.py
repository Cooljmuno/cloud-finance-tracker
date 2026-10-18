from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from .models import CategorizationRule, Category, MonthlyBudget
from .reports import month_label, normalize_currency, parse_month
from .serializers import UniqueNameSerializer, normalize_name


class OwnedCategoryMixin:
    expense_only = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = Category.objects.none()
        if request and request.user.is_authenticated:
            active_or_current = Q(is_active=True)
            if isinstance(self.instance, self.Meta.model):
                active_or_current |= Q(pk=self.instance.category_id)
            queryset = Category.objects.filter(owner=request.user).filter(active_or_current)
            if self.expense_only:
                queryset = queryset.filter(kind=Category.Kind.EXPENSE)
        self.fields["category"].queryset = queryset

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                if self.instance:
                    self.instance = get_object_or_404(
                        self.Meta.model.objects.select_for_update(),
                        pk=self.instance.pk,
                        owner=self.context["request"].user,
                    )
                category = self.validated_data.get(
                    "category", getattr(self.instance, "category", None)
                )
                category = (
                    Category.objects.select_for_update()
                    .filter(pk=category.pk, owner=self.context["request"].user)
                    .first()
                )
                if category is None:
                    raise serializers.ValidationError(
                        {"category": "Choose one of your categories."}
                    )
                if not category.is_active and (
                    not self.instance or self.instance.category_id != category.pk
                ):
                    raise serializers.ValidationError({"category": "Choose an active category."})
                if self.expense_only and category.kind != Category.Kind.EXPENSE:
                    raise serializers.ValidationError(
                        {"category": "Budgets require an expense category."}
                    )
                self._validated_data["category"] = category
                self.validate(self.validated_data)
                return super().save(**kwargs)
        except ModelValidationError as error:
            self.validate(self.validated_data)
            raise serializers.ValidationError(error.message_dict) from error
        except IntegrityError:
            self.validate(self.validated_data)
            raise


class RuleSerializer(OwnedCategoryMixin, UniqueNameSerializer):
    duplicate_name_message = "You already have a rule with this name."
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = CategorizationRule
        fields = [
            "id",
            "name",
            "match_text",
            "priority",
            "category",
            "category_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "category_name", "created_at", "updated_at"]

    def validate_name(self, value):
        return normalize_name(value)

    def validate_match_text(self, value):
        return normalize_name(value)


class BudgetMonthField(serializers.Field):
    def to_internal_value(self, data):
        try:
            return parse_month(data)
        except serializers.ValidationError as error:
            raise serializers.ValidationError(error.detail["month"]) from error

    def to_representation(self, value):
        return month_label(value)


class MonthlyBudgetSerializer(OwnedCategoryMixin, serializers.ModelSerializer):
    expense_only = True
    category_name = serializers.CharField(source="category.name", read_only=True)
    month = BudgetMonthField()
    currency = serializers.CharField(max_length=3, required=False, default="USD")

    class Meta:
        model = MonthlyBudget
        fields = [
            "id",
            "category",
            "category_name",
            "month",
            "currency",
            "amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "category_name", "created_at", "updated_at"]
        validators = []

    def validate_currency(self, value):
        try:
            return normalize_currency(value)
        except serializers.ValidationError as error:
            raise serializers.ValidationError(error.detail["currency"]) from error

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Budget amount must be greater than zero.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        values = {
            field: attrs.get(field, getattr(self.instance, field, None))
            for field in ("category", "month", "currency")
        }
        values["currency"] = values["currency"] or "USD"
        duplicate = MonthlyBudget.objects.filter(owner=self.context["request"].user, **values)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"category": "A budget already exists for this category, month, and currency."}
            )
        return attrs
