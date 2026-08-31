from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.finance.models import Category, FinancialAccount, Transaction

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("route_name", ["account-list", "category-list", "transaction-list"])
def test_finance_endpoints_require_authentication(route_name):
    response = APIClient().get(reverse(route_name))

    assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}


def test_account_creation_assigns_authenticated_owner(api_client, user, other_user):
    response = api_client.post(
        reverse("account-list"),
        {
            "name": "  Emergency   Savings ",
            "account_type": FinancialAccount.AccountType.SAVINGS,
            "institution": "Demo Credit Union",
            "currency": "usd",
            "opening_balance": "250.00",
            "owner": str(other_user.id),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    account = FinancialAccount.objects.get(pk=response.data["id"])
    assert account.owner == user
    assert account.name == "Emergency Savings"
    assert account.currency == "USD"


def test_category_creation_assigns_authenticated_owner(api_client, user):
    response = api_client.post(
        reverse("category-list"),
        {"name": "Dining", "kind": Category.Kind.EXPENSE},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert Category.objects.get(pk=response.data["id"]).owner == user


def test_account_name_duplicate_is_rejected_case_insensitively(api_client, account):
    response = api_client.post(
        reverse("account-list"),
        {
            "name": account.name.lower(),
            "account_type": FinancialAccount.AccountType.SAVINGS,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "name" in response.data


def test_lists_only_authenticated_users_resources(
    api_client,
    user,
    other_user,
    account,
    category,
    transaction,
):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Private Account",
        account_type=FinancialAccount.AccountType.CHECKING,
    )
    other_category = Category.objects.create(
        owner=other_user,
        name="Private Category",
        kind=Category.Kind.EXPENSE,
    )
    other_transaction = Transaction.objects.create(
        owner=other_user,
        account=other_account,
        category=other_category,
        transaction_date=date(2026, 8, 29),
        description="Private Transaction",
        amount=Decimal("-99.00"),
    )

    expected_ids = {
        "account-list": str(account.id),
        "category-list": str(category.id),
        "transaction-list": str(transaction.id),
    }
    forbidden_ids = {
        "account-list": str(other_account.id),
        "category-list": str(other_category.id),
        "transaction-list": str(other_transaction.id),
    }

    for route_name, expected_id in expected_ids.items():
        response = api_client.get(reverse(route_name))
        returned_ids = {item["id"] for item in response.data["results"]}

        assert response.status_code == status.HTTP_200_OK
        assert expected_id in returned_ids
        assert forbidden_ids[route_name] not in returned_ids


def test_another_users_resource_returns_not_found(api_client, other_user):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Private Account",
        account_type=FinancialAccount.AccountType.CHECKING,
    )

    response = api_client.get(reverse("account-detail", args=[other_account.id]))

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_transaction_creation_returns_related_display_names(
    api_client,
    user,
    account,
    category,
):
    response = api_client.post(
        reverse("transaction-list"),
        {
            "account": str(account.id),
            "category": str(category.id),
            "transaction_date": "2026-08-30",
            "description": "Neighborhood Market",
            "amount": "-42.35",
            "status": Transaction.Status.POSTED,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    created = Transaction.objects.get(pk=response.data["id"])
    assert created.owner == user
    assert response.data["account_name"] == account.name
    assert response.data["currency"] == account.currency
    assert response.data["category_name"] == category.name
    assert response.data["amount"] == "-42.35"


def test_uncategorized_transaction_returns_null_category_name(api_client, account):
    response = api_client.post(
        reverse("transaction-list"),
        {
            "account": str(account.id),
            "category": None,
            "transaction_date": "2026-08-30",
            "description": "Uncategorized transaction",
            "amount": "-15.00",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["category"] is None
    assert response.data["category_name"] is None


def test_transaction_rejects_another_users_account(api_client, other_user, category):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Private Account",
        account_type=FinancialAccount.AccountType.CHECKING,
    )

    response = api_client.post(
        reverse("transaction-list"),
        {
            "account": str(other_account.id),
            "category": str(category.id),
            "transaction_date": "2026-08-30",
            "description": "Forbidden account",
            "amount": "-10.00",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "account" in response.data


def test_transaction_rejects_another_users_category(api_client, other_user, account):
    other_category = Category.objects.create(
        owner=other_user,
        name="Private Category",
        kind=Category.Kind.EXPENSE,
    )

    response = api_client.post(
        reverse("transaction-list"),
        {
            "account": str(account.id),
            "category": str(other_category.id),
            "transaction_date": "2026-08-30",
            "description": "Forbidden category",
            "amount": "-10.00",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "category" in response.data


def test_transaction_update_rejects_another_users_account(
    api_client,
    other_user,
    transaction,
):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Private Account",
        account_type=FinancialAccount.AccountType.CHECKING,
    )

    response = api_client.patch(
        reverse("transaction-detail", args=[transaction.id]),
        {"account": str(other_account.id)},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    transaction.refresh_from_db()
    assert transaction.account != other_account


def test_transaction_rejects_inactive_account(api_client, account):
    account.is_active = False
    account.save(update_fields=["is_active"])

    response = api_client.post(
        reverse("transaction-list"),
        {
            "account": str(account.id),
            "transaction_date": "2026-08-30",
            "description": "Archived account",
            "amount": "-10.00",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "account" in response.data


def test_transaction_can_keep_current_account_after_it_is_archived(
    api_client,
    account,
    transaction,
):
    account.is_active = False
    account.save(update_fields=["is_active"])

    response = api_client.patch(
        reverse("transaction-detail", args=[transaction.id]),
        {
            "account": str(account.id),
            "description": "Updated historical transaction",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert str(response.data["account"]) == str(account.id)


def test_transaction_filters_compose_without_bypassing_isolation(
    api_client,
    user,
    other_user,
    account,
    category,
):
    matching = Transaction.objects.create(
        owner=user,
        account=account,
        category=category,
        transaction_date=date(2026, 8, 15),
        description="Matching",
        amount=Decimal("-25.00"),
        status=Transaction.Status.PENDING,
    )
    Transaction.objects.create(
        owner=user,
        account=account,
        category=category,
        transaction_date=date(2026, 7, 31),
        description="Outside range",
        amount=Decimal("-30.00"),
        status=Transaction.Status.PENDING,
    )
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Private Account",
        account_type=FinancialAccount.AccountType.CHECKING,
    )
    Transaction.objects.create(
        owner=other_user,
        account=other_account,
        transaction_date=date(2026, 8, 15),
        description="Other user",
        amount=Decimal("-40.00"),
        status=Transaction.Status.PENDING,
    )

    response = api_client.get(
        reverse("transaction-list"),
        {
            "account": str(account.id),
            "category": str(category.id),
            "status": Transaction.Status.PENDING,
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in response.data["results"]] == [str(matching.id)]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ({"account": "not-a-uuid"}, "account"),
        ({"date_from": "08/01/2026"}, "date_from"),
        ({"date_from": "2026-02-30"}, "date_from"),
        ({"status": "cleared"}, "status"),
        ({"date_from": "2026-09-01", "date_to": "2026-08-01"}, "date_to"),
    ],
)
def test_transaction_filters_reject_invalid_values(api_client, query, field):
    response = api_client.get(reverse("transaction-list"), query)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.data


def test_transaction_rejects_zero_amount(api_client, account):
    response = api_client.post(
        reverse("transaction-list"),
        {
            "account": str(account.id),
            "transaction_date": "2026-08-30",
            "description": "Invalid transaction",
            "amount": "0.00",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["amount"] == ["Amount must be nonzero."]


def test_account_with_transactions_returns_conflict_on_delete(api_client, account, transaction):
    response = api_client.delete(reverse("account-detail", args=[account.id]))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert FinancialAccount.objects.filter(pk=account.id).exists()


def test_category_with_transactions_returns_conflict_on_delete(api_client, category, transaction):
    response = api_client.delete(reverse("category-detail", args=[category.id]))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert Category.objects.filter(pk=category.id).exists()


def test_user_cannot_update_or_delete_another_users_transaction(
    api_client,
    other_user,
):
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Private Account",
        account_type=FinancialAccount.AccountType.CHECKING,
    )
    other_transaction = Transaction.objects.create(
        owner=other_user,
        account=other_account,
        transaction_date=date(2026, 8, 30),
        description="Private Transaction",
        amount=Decimal("-50.00"),
    )
    url = reverse("transaction-detail", args=[other_transaction.id])

    patch_response = api_client.patch(url, {"description": "Changed"}, format="json")
    delete_response = api_client.delete(url)

    assert patch_response.status_code == status.HTTP_404_NOT_FOUND
    assert delete_response.status_code == status.HTTP_404_NOT_FOUND
    other_transaction.refresh_from_db()
    assert other_transaction.description == "Private Transaction"
