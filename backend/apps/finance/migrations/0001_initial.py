import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("expense", "Expense"),
                            ("income", "Income"),
                            ("transfer", "Transfer"),
                        ],
                        max_length=10,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="categories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["kind", "name", "id"],
                "indexes": [
                    models.Index(
                        fields=["owner", "is_active"],
                        name="category_owner_active_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        Lower("name"),
                        "owner",
                        name="unique_category_name_per_owner",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="FinancialAccount",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                (
                    "account_type",
                    models.CharField(
                        choices=[
                            ("checking", "Checking"),
                            ("savings", "Savings"),
                            ("credit_card", "Credit card"),
                            ("cash", "Cash"),
                            ("investment", "Investment"),
                            ("loan", "Loan"),
                            ("other", "Other"),
                        ],
                        max_length=20,
                    ),
                ),
                ("institution", models.CharField(blank=True, max_length=100)),
                (
                    "currency",
                    models.CharField(
                        default="USD",
                        max_length=3,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Currency must be a three-letter uppercase code.",
                                regex="^[A-Z]{3}$",
                            ),
                        ],
                    ),
                ),
                (
                    "opening_balance",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="financial_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["name", "id"],
                "indexes": [
                    models.Index(
                        fields=["owner", "is_active"],
                        name="account_owner_active_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        Lower("name"),
                        "owner",
                        name="unique_account_name_per_owner",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Transaction",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("transaction_date", models.DateField()),
                ("description", models.CharField(max_length=255)),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Positive amounts are inflows; negative amounts are outflows.",
                        max_digits=14,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("posted", "Posted")],
                        default="posted",
                        max_length=10,
                    ),
                ),
                ("notes", models.TextField(blank=True, max_length=1000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="transactions",
                        to="finance.financialaccount",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="transactions",
                        to="finance.category",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-transaction_date", "-created_at", "-id"],
                "indexes": [
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
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=~models.Q(amount=0),
                        name="transaction_amount_nonzero",
                    ),
                ],
            },
        ),
    ]
