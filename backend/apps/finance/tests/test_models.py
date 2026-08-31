from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction as db_transaction

from apps.finance.models import Category, FinancialAccount, Transaction

pytestmark = pytest.mark.django_db


def test_account_name_is_case_insensitively_unique_per_owner(user, account):
    with pytest.raises(ValidationError, match="unique_account_name_per_owner"):
        FinancialAccount.objects.create(
            owner=user,
            name=account.name.lower(),
            account_type=FinancialAccount.AccountType.SAVINGS,
        )


def test_category_name_can_be_reused_by_different_users(user, other_user):
    Category.objects.create(owner=user, name="Income", kind=Category.Kind.INCOME)

    category = Category.objects.create(
        owner=other_user,
        name="Income",
        kind=Category.Kind.INCOME,
    )

    assert category.owner == other_user


def test_account_owner_cannot_be_changed_with_save(account, other_user):
    account.owner = other_user

    with pytest.raises(ValidationError, match="Owner cannot be changed"):
        account.save()

    account.refresh_from_db()
    assert account.owner != other_user


def test_category_owner_cannot_be_changed_with_queryset_update(category, other_user):
    with pytest.raises(ValueError, match="ownership changes"):
        Category.objects.filter(pk=category.pk).update(owner=other_user)

    category.refresh_from_db()
    assert category.owner != other_user


def test_account_owner_cannot_be_changed_with_bulk_update(account, other_user):
    account.owner = other_user

    with pytest.raises(ValueError, match="ownership changes"):
        FinancialAccount.objects.bulk_update([account], ["owner"])

    account.refresh_from_db()
    assert account.owner != other_user


def test_bulk_create_conflict_update_cannot_bypass_owner_guard(account, other_user):
    conflicting = FinancialAccount(
        id=account.id,
        owner=other_user,
        name=account.name,
        account_type=account.account_type,
    )

    with pytest.raises(ValueError, match="Bulk conflict updates"):
        FinancialAccount.objects.bulk_create(
            [conflicting],
            update_conflicts=True,
            update_fields=["owner"],
            unique_fields=["id"],
        )

    account.refresh_from_db()
    assert account.owner != other_user


def test_transaction_amount_cannot_be_zero(transaction):
    with pytest.raises(IntegrityError), db_transaction.atomic():
        Transaction.objects.filter(pk=transaction.pk).update(amount=Decimal("0.00"))


def test_transaction_create_rejects_another_users_account(user, other_user):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Other Checking",
        account_type=FinancialAccount.AccountType.CHECKING,
    )
    with pytest.raises(ValidationError, match="Account must belong"):
        Transaction.objects.create(
            owner=user,
            account=other_account,
            transaction_date=date(2026, 8, 30),
            description="Invalid ownership",
            amount=Decimal("-10.00"),
        )


def test_transaction_create_rejects_another_users_category(
    user,
    other_user,
    account,
):
    other_category = Category.objects.create(
        owner=other_user,
        name="Private Category",
        kind=Category.Kind.EXPENSE,
    )
    with pytest.raises(ValidationError, match="Category must belong"):
        Transaction.objects.create(
            owner=user,
            account=account,
            category=other_category,
            transaction_date=date(2026, 8, 30),
            description="Invalid ownership",
            amount=Decimal("-10.00"),
        )


def test_transaction_bulk_create_validates_ownership(user, other_user):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Other Checking",
        account_type=FinancialAccount.AccountType.CHECKING,
    )
    invalid = Transaction(
        owner=user,
        account=other_account,
        transaction_date=date(2026, 8, 30),
        description="Invalid bulk transaction",
        amount=Decimal("-10.00"),
    )

    with pytest.raises(ValidationError, match="Account must belong"):
        Transaction.objects.bulk_create([invalid])

    assert not Transaction.objects.filter(description="Invalid bulk transaction").exists()


def test_transaction_queryset_update_rejects_ownership_changes(transaction, other_user):
    with pytest.raises(ValueError, match="ownership changes"):
        Transaction.objects.filter(pk=transaction.pk).update(owner=other_user)

    transaction.refresh_from_db()
    assert transaction.owner != other_user


def test_transaction_bulk_update_rejects_relation_changes(transaction, other_user):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Other Checking",
        account_type=FinancialAccount.AccountType.CHECKING,
    )
    transaction.account = other_account

    with pytest.raises(ValueError, match="ownership changes"):
        Transaction.objects.bulk_update([transaction], ["account"])

    transaction.refresh_from_db()
    assert transaction.account != other_account


def test_transaction_owner_cannot_move_with_consistent_relations(transaction, other_user):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Other Checking",
        account_type=FinancialAccount.AccountType.CHECKING,
    )
    transaction.owner = other_user
    transaction.account = other_account
    transaction.category = None

    with pytest.raises(ValidationError, match="Owner cannot be changed"):
        transaction.save()

    transaction.refresh_from_db()
    assert transaction.owner != other_user


def test_user_deletion_cascades_complete_finance_history(user, account, category, transaction):
    user.delete()

    assert not FinancialAccount.objects.filter(pk=account.pk).exists()
    assert not Category.objects.filter(pk=category.pk).exists()
    assert not Transaction.objects.filter(pk=transaction.pk).exists()
