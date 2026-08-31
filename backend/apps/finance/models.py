import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
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
    }


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


class Transaction(OwnerImmutableModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        POSTED = "posted", "Posted"

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

        if self.owner_id and self.account_id and self.account.owner_id != self.owner_id:
            errors["account"] = "Account must belong to the transaction owner."

        if self.owner_id and self.category_id and self.category.owner_id != self.owner_id:
            errors["category"] = "Category must belong to the transaction owner."

        if errors:
            raise ValidationError(errors)
