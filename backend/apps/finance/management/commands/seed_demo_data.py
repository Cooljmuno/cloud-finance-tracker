import getpass
import os
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as database_transaction
from django.utils import timezone

from apps.finance.models import (
    CategorizationRule,
    Category,
    FinancialAccount,
    ImportBatch,
    MonthlyBudget,
    Transaction,
)

DEMO_USERNAME = "portfolio-demo"
DEMO_EMAIL = "demo@local.invalid"
DEMO_NAMESPACE = uuid.UUID("73ca24de-8c86-4fbb-8294-3f988b795af1")

ACCOUNT_FIXTURES = {
    "checking": {
        "name": "Everyday Checking",
        "account_type": FinancialAccount.AccountType.CHECKING,
        "institution": "Northstar Community Bank",
        "opening_balance": Decimal("2840.00"),
    },
    "savings": {
        "name": "Goal Savings",
        "account_type": FinancialAccount.AccountType.SAVINGS,
        "institution": "Harborline Credit Union",
        "opening_balance": Decimal("6200.00"),
    },
    "credit": {
        "name": "Cedar Rewards Card",
        "account_type": FinancialAccount.AccountType.CREDIT_CARD,
        "institution": "Cedar Financial",
        "opening_balance": Decimal("0.00"),
    },
}

CATEGORY_FIXTURES = {
    "income": ("Paycheck", Category.Kind.INCOME),
    "groceries": ("Groceries", Category.Kind.EXPENSE),
    "housing": ("Housing", Category.Kind.EXPENSE),
    "dining": ("Dining", Category.Kind.EXPENSE),
    "transport": ("Transportation", Category.Kind.EXPENSE),
    "utilities": ("Utilities", Category.Kind.EXPENSE),
    "health": ("Health", Category.Kind.EXPENSE),
    "shopping": ("Shopping", Category.Kind.EXPENSE),
    "entertainment": ("Entertainment", Category.Kind.EXPENSE),
    "transfer": ("Transfer", Category.Kind.TRANSFER),
}

# key, days before reference date, account, category, description, amount, status
TRANSACTION_FIXTURES = [
    ("paycheck-1", 3, "checking", "income", "Northwind Labs payroll", "2450.00", "posted"),
    ("market-1", 4, "credit", "groceries", "Juniper Market", "-86.24", "posted"),
    ("coffee-1", 5, "credit", "dining", "Elm Street Coffee", "-6.75", "posted"),
    ("fuel-1", 7, "credit", "transport", "Metro Fuel", "-42.18", "pending"),
    ("internet-1", 9, "checking", "utilities", "Lighthouse Internet", "-64.99", "posted"),
    ("cinema-1", 11, "credit", "entertainment", "Orchard Cinema", "-28.00", "posted"),
    ("pharmacy-1", 13, "credit", "health", "Willow Pharmacy", "-19.43", "posted"),
    ("market-2", 15, "credit", "groceries", "Juniper Market", "-112.67", "posted"),
    ("restaurant-1", 17, "credit", "dining", "Saffron Table", "-47.50", "posted"),
    ("rent-1", 20, "checking", "housing", "Pine Terrace rent", "-1325.00", "posted"),
    ("transfer-out", 21, "checking", "transfer", "Transfer to Goal Savings", "-500.00", "posted"),
    (
        "transfer-in",
        21,
        "savings",
        "transfer",
        "Transfer from Everyday Checking",
        "500.00",
        "posted",
    ),
    ("paycheck-2", 32, "checking", "income", "Northwind Labs payroll", "2450.00", "posted"),
    ("market-3", 34, "credit", "groceries", "Juniper Market", "-74.91", "posted"),
    ("transit-1", 35, "checking", "transport", "City transit pass", "-68.00", "posted"),
    ("power-1", 37, "checking", "utilities", "North County Power", "-91.36", "posted"),
    ("books-1", 39, "credit", "shopping", "Paper Trail Books", "-34.20", "posted"),
    ("lunch-1", 41, "credit", "dining", "Garden Lunchroom", "-18.65", "posted"),
    ("market-4", 43, "credit", "groceries", "Juniper Market", "-96.12", "posted"),
    ("clinic-1", 46, "checking", "health", "Riverside Clinic", "-35.00", "posted"),
    ("rent-2", 50, "checking", "housing", "Pine Terrace rent", "-1325.00", "posted"),
    ("refund-1", 52, "credit", "shopping", "Cedar merchant refund", "26.40", "posted"),
    ("uncategorized-1", 54, "checking", None, "ACH adjustment", "-12.00", "posted"),
    ("music-1", 56, "credit", "entertainment", "Sonora Music", "-10.99", "posted"),
]


def fixture_id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(DEMO_NAMESPACE, f"{kind}:{key}")


class Command(BaseCommand):
    help = "Create an idempotent, synthetic local portfolio dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--as-of",
            dest="as_of",
            help="Reference date in YYYY-MM-DD format (defaults to today).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete this demo user's finance records before recreating fixtures.",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Prompt for a new demo password without accepting it as a command argument.",
        )

    def handle(self, *args, **options):
        if not settings.ENABLE_DEMO_DATA:
            raise CommandError("Demo data is disabled in this environment.")

        reference_date = self._parse_reference_date(options.get("as_of"))
        user_model = get_user_model()
        expected_user_id = fixture_id("user", DEMO_USERNAME)
        user_by_name = user_model.objects.filter(username=DEMO_USERNAME).first()
        user_by_id = user_model.objects.filter(pk=expected_user_id).first()
        if user_by_name and user_by_name.pk != expected_user_id:
            raise CommandError(f"The reserved username {DEMO_USERNAME!r} is already in use.")
        if user_by_id and user_by_id.username != DEMO_USERNAME:
            raise CommandError("The reserved demo user ID is already in use.")
        existing_user = user_by_name or user_by_id
        password = os.getenv("DEMO_USER_PASSWORD")

        if (existing_user is None or options["reset_password"]) and not password:
            if not sys.stdin.isatty():
                raise CommandError(
                    "Set DEMO_USER_PASSWORD or run this command interactively "
                    "to create the demo user."
                )
            password = getpass.getpass("Demo password: ")
            confirmation = getpass.getpass("Confirm demo password: ")
            if password != confirmation:
                raise CommandError("Passwords do not match.")

        if password:
            candidate = existing_user or user_model(username=DEMO_USERNAME, email=DEMO_EMAIL)
            try:
                validate_password(password, user=candidate)
            except ValidationError as error:
                raise CommandError("Demo password does not satisfy password policy.") from error

        with database_transaction.atomic():
            user, created = user_model.objects.get_or_create(
                username=DEMO_USERNAME,
                defaults={
                    "id": expected_user_id,
                    "email": DEMO_EMAIL,
                },
            )
            if created or password:
                user.email = DEMO_EMAIL
                user.set_password(password)
                user.save(update_fields=["email", "password", "updated_at"])

            if options["reset"]:
                Transaction.objects.filter(owner=user).delete()
                ImportBatch.objects.filter(owner=user).delete()
                CategorizationRule.objects.filter(owner=user).delete()
                MonthlyBudget.objects.filter(owner=user).delete()
                Category.objects.filter(owner=user).delete()
                FinancialAccount.objects.filter(owner=user).delete()

            accounts = self._seed_accounts(user)
            categories = self._seed_categories(user)
            self._seed_transactions(user, accounts, categories, reference_date)

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded synthetic portfolio data for "
                f"{DEMO_USERNAME} as of {reference_date.isoformat()}: "
                f"{len(accounts)} accounts, {len(categories)} categories, "
                f"{len(TRANSACTION_FIXTURES)} transactions."
            )
        )

    @staticmethod
    def _parse_reference_date(value: str | None) -> date:
        if not value:
            return timezone.localdate()
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise CommandError("--as-of must use YYYY-MM-DD.") from error

    @staticmethod
    def _seed_accounts(user) -> dict[str, FinancialAccount]:
        accounts = {}
        for key, fixture in ACCOUNT_FIXTURES.items():
            account, _ = FinancialAccount.objects.update_or_create(
                id=fixture_id("account", key),
                defaults={
                    "owner": user,
                    "currency": "USD",
                    "is_active": True,
                    **fixture,
                },
            )
            accounts[key] = account
        return accounts

    @staticmethod
    def _seed_categories(user) -> dict[str, Category]:
        categories = {}
        for key, (name, kind) in CATEGORY_FIXTURES.items():
            category, _ = Category.objects.update_or_create(
                id=fixture_id("category", key),
                defaults={
                    "owner": user,
                    "name": name,
                    "kind": kind,
                    "is_active": True,
                },
            )
            categories[key] = category
        return categories

    @staticmethod
    def _seed_transactions(user, accounts, categories, reference_date: date) -> None:
        for (
            key,
            days_ago,
            account_key,
            category_key,
            description,
            amount,
            status,
        ) in TRANSACTION_FIXTURES:
            Transaction.objects.update_or_create(
                id=fixture_id("transaction", key),
                defaults={
                    "owner": user,
                    "account": accounts[account_key],
                    "category": categories.get(category_key),
                    "category_source": Transaction.CategorySource.MANUAL,
                    "matched_rule": None,
                    "transaction_date": reference_date - timedelta(days=days_ago),
                    "description": description,
                    "amount": Decimal(amount),
                    "status": status,
                    "notes": "Synthetic portfolio demonstration data.",
                },
            )
