from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.finance.models import Category, FinancialAccount, Transaction
from apps.users.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(username="jonathan", password="test-password")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other-user", password="test-password")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def account(user):
    return FinancialAccount.objects.create(
        owner=user,
        name="Primary Checking",
        account_type=FinancialAccount.AccountType.CHECKING,
        institution="Demo Credit Union",
        opening_balance=Decimal("1000.00"),
    )


@pytest.fixture
def category(user):
    return Category.objects.create(owner=user, name="Groceries", kind=Category.Kind.EXPENSE)


@pytest.fixture
def transaction(user, account, category):
    return Transaction.objects.create(
        owner=user,
        account=account,
        category=category,
        transaction_date=date(2026, 8, 30),
        description="Neighborhood Market",
        amount=Decimal("-42.35"),
    )
