from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from .models import Category, FinancialAccount, ImportBatch, Transaction
from .planning import assign_category


def normalize_name(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise serializers.ValidationError("This field may not be blank.")
    return normalized


class UniqueNameSerializer(serializers.ModelSerializer):
    duplicate_name_message = "You already have a resource with this name."

    def validate(self, attrs):
        attrs = super().validate(attrs)
        name = attrs.get("name", getattr(self.instance, "name", None))
        duplicate = self.Meta.model.objects.filter(
            owner=self.context["request"].user,
            name__iexact=name,
        )
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError({"name": self.duplicate_name_message})
        return attrs

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except ModelValidationError, IntegrityError:
            self.validate(self.validated_data)
            raise


class FinancialAccountSerializer(UniqueNameSerializer):
    duplicate_name_message = "You already have an account with this name."
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


class CategorySerializer(UniqueNameSerializer):
    duplicate_name_message = "You already have a category with this name."

    class Meta:
        model = Category
        fields = ["id", "name", "kind", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        return normalize_name(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if (
            self.instance
            and attrs.get("kind", self.instance.kind) != Category.Kind.EXPENSE
            and self.instance.budgets.exists()
        ):
            raise serializers.ValidationError(
                {"kind": "Categories with budgets must remain expense categories."}
            )
        return attrs

    def update(self, instance, validated_data):
        with transaction.atomic():
            instance = get_object_or_404(
                Category.objects.select_for_update(),
                pk=instance.pk,
                owner=self.context["request"].user,
            )
            self.instance = instance
            self.validate(validated_data)
            return super().update(instance, validated_data)


class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    currency = serializers.CharField(source="account.currency", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    matched_rule_name = serializers.CharField(
        source="matched_rule.name", read_only=True, allow_null=True
    )
    category_mode = serializers.ChoiceField(
        choices=["automatic", "manual"], required=False, write_only=True
    )

    class Meta:
        model = Transaction
        fields = [
            "id",
            "account",
            "account_name",
            "currency",
            "category",
            "category_name",
            "category_source",
            "matched_rule",
            "matched_rule_name",
            "category_mode",
            "import_batch",
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
            "category_source",
            "matched_rule",
            "matched_rule_name",
            "import_batch",
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

    def validate(self, attrs):
        if attrs.get("category_mode") == "automatic" and attrs.get("category") is not None:
            raise serializers.ValidationError(
                {"category": "Automatic categorization does not accept an explicit category."}
            )
        return super().validate(attrs)

    def _lock_references(self, values, current=None):
        owner = self.context["request"].user
        for field, model in (("account", FinancialAccount), ("category", Category)):
            if field not in values or values[field] is None:
                continue
            reference = (
                model.objects.select_for_update().filter(pk=values[field].pk, owner=owner).first()
            )
            current_id = getattr(current, f"{field}_id", None)
            if reference is None or (not reference.is_active and reference.pk != current_id):
                raise serializers.ValidationError({field: f"Choose one of your active {field}s."})
            values[field] = reference

    @staticmethod
    def _set_category(entry, values, *, creating=False):
        mode = values.pop("category_mode", None)
        explicit = "category" in values
        description_changed = "description" in values and values["description"] != entry.description
        for field, value in values.items():
            setattr(entry, field, value)
        if mode == "manual" or (mode is None and explicit):
            entry.category_source = Transaction.CategorySource.MANUAL
            entry.matched_rule = None
        elif (
            mode == "automatic"
            or creating
            or (description_changed and entry.category_source != Transaction.CategorySource.MANUAL)
        ):
            assign_category(entry)

    def create(self, validated_data):
        with transaction.atomic():
            self._lock_references(validated_data)
            entry = Transaction(owner=validated_data["owner"])
            self._set_category(entry, validated_data, creating=True)
            entry.save()
            return entry

    def update(self, instance, validated_data):
        with transaction.atomic():
            entry = get_object_or_404(
                Transaction.objects.select_for_update(),
                pk=instance.pk,
                owner=self.context["request"].user,
            )
            self._lock_references(validated_data, entry)
            self._set_category(entry, validated_data)
            entry.save()
            return entry


class ImportBatchSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "account",
            "account_name",
            "file_name",
            "file_hash",
            "row_count",
            "created_at",
        ]
        read_only_fields = fields
