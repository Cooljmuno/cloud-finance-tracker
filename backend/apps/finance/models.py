import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower

currency_validator = RegexValidator(
    regex=r"^[A-Z]{3}$",
    message="Currency must be a three-letter uppercase code.",
)


class OwnerImmutableQuerySet(models.QuerySet):
    ownership_fields = {"owner", "owner_id"}

    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValueError("Bulk conflict updates are not allowed.")

        objects = list(objs)
        for obj in objects:
            obj.full_clean()
        return super().bulk_create(objects, **kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if self.ownership_fields.intersection(fields):
            raise ValueError("Bulk ownership changes are not allowed.")

        objects = list(objs)
        for obj in objects:
            obj.full_clean()
        return super().bulk_update(objects, fields, batch_size=batch_size)

    def update(self, **kwargs):
        if self.ownership_fields.intersection(kwargs):
            raise ValueError("QuerySet ownership changes are not allowed.")
        return super().update(**kwargs)


class TransactionQuerySet(OwnerImmutableQuerySet):
    ownership_fields = OwnerImmutableQuerySet.ownership_fields | {
        "account",
        "account_id",
        "category",
        "category_id",
        "import_batch",
        "import_batch_id",
        "matched_rule",
        "matched_rule_id",
        "category_source",
    }


class ImportBatchQuerySet(OwnerImmutableQuerySet):
    ownership_fields = OwnerImmutableQuerySet.ownership_fields | {"account", "account_id"}


class CategoryReferenceQuerySet(OwnerImmutableQuerySet):
    ownership_fields = OwnerImmutableQuerySet.ownership_fields | {"category", "category_id"}


class OwnerImmutableModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self._state.adding:
            return

        original_owner_id = (
            type(self).objects.filter(pk=self.pk).values_list("owner_id", flat=True).get()
        )
        if self.owner_id != original_owner_id:
            raise ValidationError({"owner": "Owner cannot be changed after creation."})


class FinancialAccount(OwnerImmutableModel):
    class AccountType(models.TextChoices):
        CHECKING = "checking", "Checking"
        SAVINGS = "savings", "Savings"
        CREDIT_CARD = "credit_card", "Credit card"
        CASH = "cash", "Cash"
        INVESTMENT = "investment", "Investment"
        LOAN = "loan", "Loan"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="financial_accounts",
    )
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    institution = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=3, default="USD", validators=[currency_validator])
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OwnerImmutableQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "owner",
                name="unique_account_name_per_owner",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "is_active"], name="account_owner_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class ImportBatch(OwnerImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="import_batches",
    )
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.RESTRICT,
        related_name="import_batches",
    )
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(
        max_length=64,
        validators=[RegexValidator(regex=r"^[0-9a-f]{64}$", message="Use a SHA-256 file hash.")],
    )
    row_count = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImportBatchQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "file_hash"],
                name="unique_import_file_per_account",
            ),
            models.CheckConstraint(
                condition=models.Q(row_count__gt=0),
                name="import_row_count_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "-created_at"], name="import_owner_created_idx"),
        ]

    def __str__(self) -> str:
        return self.file_name

    def clean(self) -> None:
        super().clean()
        if self.owner_id and self.account_id and self.account.owner_id != self.owner_id:
            raise ValidationError({"account": "Account must belong to the import owner."})


class Category(OwnerImmutableModel):
    class Kind(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        TRANSFER = "transfer", "Transfer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OwnerImmutableQuerySet.as_manager()

    class Meta:
        ordering = ["kind", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "owner",
                name="unique_category_name_per_owner",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "is_active"], name="category_owner_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if not self._state.adding and self.kind != self.Kind.EXPENSE and self.budgets.exists():
            raise ValidationError(
                {"kind": "Categories with budgets must remain expense categories."}
            )


class CategorizationRule(OwnerImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categorization_rules"
    )
    name = models.CharField(max_length=100)
    match_text = models.CharField(max_length=100)
    priority = models.PositiveIntegerField(
        default=100, validators=[MinValueValidator(1), MaxValueValidator(9999)]
    )
    category = models.ForeignKey(Category, on_delete=models.RESTRICT, related_name="rules")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CategoryReferenceQuerySet.as_manager()

    class Meta:
        ordering = ["priority", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(Lower("name"), "owner", name="unique_rule_name_per_owner"),
            models.CheckConstraint(
                condition=models.Q(priority__gte=1, priority__lte=9999),
                name="rule_priority_valid",
            ),
        ]
        indexes = [models.Index(fields=["owner", "is_active"], name="rule_owner_active_idx")]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        self.name = " ".join(self.name.split())
        self.match_text = " ".join(self.match_text.split())
        errors = {}
        if not self.name:
            errors["name"] = "This field may not be blank."
        if not self.match_text:
            errors["match_text"] = "This field may not be blank."
        if self.owner_id and self.category_id and self.category.owner_id != self.owner_id:
            errors["category"] = "Category must belong to the rule owner."
        elif self.category_id and not self.category.is_active:
            original_category_id = None
            if not self._state.adding:
                original_category_id = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values_list("category_id", flat=True)
                    .first()
                )
            if original_category_id != self.category_id:
                errors["category"] = "Choose an active category."
        if errors:
            raise ValidationError(errors)


class MonthlyBudget(OwnerImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monthly_budgets"
    )
    category = models.ForeignKey(Category, on_delete=models.RESTRICT, related_name="budgets")
    month = models.DateField()
    currency = models.CharField(max_length=3, default="USD", validators=[currency_validator])
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CategoryReferenceQuerySet.as_manager()

    class Meta:
        ordering = ["-month", "category__name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "category", "month", "currency"],
                name="unique_monthly_category_budget",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="budget_amount_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.month:%Y-%m}: {self.category.name} ({self.currency})"

    def clean(self) -> None:
        super().clean()
        errors = {}
        if isinstance(self.month, date) and self.month.day != 1:
            errors["month"] = "Use the first day of the budget month."
        if self.owner_id and self.category_id:
            if self.category.owner_id != self.owner_id:
                errors["category"] = "Category must belong to the budget owner."
            elif self.category.kind != Category.Kind.EXPENSE:
                errors["category"] = "Budgets require an expense category."
            elif not self.category.is_active:
                original_category_id = None
                if not self._state.adding:
                    original_category_id = (
                        type(self)
                        .objects.filter(pk=self.pk)
                        .values_list("category_id", flat=True)
                        .first()
                    )
                if original_category_id != self.category_id:
                    errors["category"] = "Choose an active category."
        if errors:
            raise ValidationError(errors)


class Transaction(OwnerImmutableModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        POSTED = "posted", "Posted"

    class CategorySource(models.TextChoices):
        MANUAL = "manual", "Manual"
        RULE = "rule", "Rule"
        UNCATEGORIZED = "uncategorized", "Uncategorized"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.RESTRICT,
        related_name="transactions",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.RESTRICT,
        related_name="transactions",
        null=True,
        blank=True,
    )
    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.SET_NULL,
        related_name="transactions",
        null=True,
        blank=True,
    )
    category_source = models.CharField(
        max_length=15, choices=CategorySource.choices, default=CategorySource.UNCATEGORIZED
    )
    matched_rule = models.ForeignKey(
        CategorizationRule,
        on_delete=models.SET_NULL,
        related_name="transactions",
        null=True,
        blank=True,
    )
    transaction_date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Positive amounts are inflows; negative amounts are outflows.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    notes = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ["-transaction_date", "-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(amount=0),
                name="transaction_amount_nonzero",
            ),
        ]
        indexes = [
            models.Index(
                fields=["owner", "-transaction_date"],
                name="txn_owner_date_idx",
            ),
            models.Index(
                fields=["account", "-transaction_date"],
                name="txn_account_date_idx",
            ),
            models.Index(
                fields=["owner", "category", "-transaction_date"],
                name="txn_owner_category_date_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.transaction_date}: {self.description}"

    def clean(self) -> None:
        super().clean()
        errors = {}

        if (
            self._state.adding
            and self.category_id
            and self.category_source == self.CategorySource.UNCATEGORIZED
        ):
            self.category_source = self.CategorySource.MANUAL

        if self.owner_id and self.account_id and self.account.owner_id != self.owner_id:
            errors["account"] = "Account must belong to the transaction owner."

        if self.owner_id and self.category_id and self.category.owner_id != self.owner_id:
            errors["category"] = "Category must belong to the transaction owner."

        if self.owner_id and self.import_batch_id and self.import_batch.owner_id != self.owner_id:
            errors["import_batch"] = "Import batch must belong to the transaction owner."

        if self.owner_id and self.matched_rule_id and self.matched_rule.owner_id != self.owner_id:
            errors["matched_rule"] = "Matched rule must belong to the transaction owner."

        if errors:
            raise ValidationError(errors)
