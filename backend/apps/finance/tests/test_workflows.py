import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status

from apps.finance.models import Category, FinancialAccount, Transaction
from apps.finance.serializers import CategorySerializer, FinancialAccountSerializer

pytestmark = pytest.mark.django_db

NAMED_RESOURCES = [
    (
        FinancialAccount,
        FinancialAccountSerializer,
        "account",
        {"account_type": "checking"},
        "You already have an account with this name.",
    ),
    (
        Category,
        CategorySerializer,
        "category",
        {"kind": "expense"},
        "You already have a category with this name.",
    ),
]


def test_empty_user_can_manage_finance_history(api_client):
    for route in ("account-list", "category-list", "transaction-list"):
        response = api_client.get(reverse(route))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    account_response = api_client.post(
        reverse("account-list"),
        {"name": "Starter Checking", "account_type": "checking"},
        format="json",
    )
    category_response = api_client.post(
        reverse("category-list"),
        {"name": "Everyday Expenses", "kind": "expense"},
        format="json",
    )
    assert account_response.status_code == status.HTTP_201_CREATED
    assert category_response.status_code == status.HTTP_201_CREATED
    account_id = account_response.data["id"]
    category_id = category_response.data["id"]
    account_url = reverse("account-detail", args=[account_id])
    category_url = reverse("category-detail", args=[category_id])

    transaction_payload = {
        "account": account_id,
        "category": category_id,
        "transaction_date": "2026-10-18",
        "description": "Synthetic market purchase",
        "amount": "-15.00",
        "status": "pending",
    }
    created = api_client.post(reverse("transaction-list"), transaction_payload, format="json")
    assert created.status_code == status.HTTP_201_CREATED
    transaction_id = created.data["id"]
    transaction_url = reverse("transaction-detail", args=[transaction_id])

    renamed_account = api_client.patch(
        account_url,
        {"name": "Daily Checking", "institution": "Synthetic Credit Union"},
        format="json",
    )
    renamed_category = api_client.patch(category_url, {"name": "Groceries"}, format="json")
    assert renamed_account.status_code == status.HTTP_200_OK
    assert renamed_account.data["institution"] == "Synthetic Credit Union"
    assert renamed_category.status_code == status.HTTP_200_OK

    edited = api_client.patch(
        transaction_url,
        {"amount": "-18.75", "description": "Corrected market purchase", "status": "posted"},
        format="json",
    )
    assert edited.status_code == status.HTTP_200_OK
    assert edited.data["account_name"] == "Daily Checking"
    assert edited.data["category_name"] == "Groceries"
    assert edited.data["amount"] == "-18.75"
    assert edited.data["status"] == "posted"

    for resource_url in (account_url, category_url):
        archived = api_client.patch(resource_url, {"is_active": False}, format="json")
        assert archived.status_code == status.HTTP_200_OK
        assert archived.data["is_active"] is False
        assert api_client.delete(resource_url).status_code == status.HTTP_409_CONFLICT

    rejected = api_client.post(reverse("transaction-list"), transaction_payload, format="json")
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST
    assert "account" in rejected.data
    assert "category" in rejected.data

    historical_edit = api_client.patch(
        transaction_url,
        {"account": account_id, "category": category_id, "notes": "Reviewed synthetic record"},
        format="json",
    )
    assert historical_edit.status_code == status.HTTP_200_OK
    assert historical_edit.data["notes"] == "Reviewed synthetic record"
    assert historical_edit.data["amount"] == "-18.75"

    assert api_client.delete(transaction_url).status_code == status.HTTP_204_NO_CONTENT
    assert not Transaction.objects.filter(pk=transaction_id).exists()
    assert api_client.delete(account_url).status_code == status.HTTP_204_NO_CONTENT
    assert api_client.delete(category_url).status_code == status.HTTP_204_NO_CONTENT

    for route in ("account-list", "category-list", "transaction-list"):
        assert api_client.get(reverse(route)).data["count"] == 0


@pytest.mark.parametrize(("model", "serializer", "route", "fields", "message"), NAMED_RESOURCES)
def test_account_and_category_mutations_hide_other_users_resources(
    api_client, user, other_user, model, serializer, route, fields, message
):
    resource = model.objects.create(owner=other_user, name="Private resource", **fields)
    resource_url = reverse(f"{route}-detail", args=[resource.id])

    edited = api_client.patch(
        resource_url,
        {"name": "Changed", "is_active": False, "owner": str(user.id)},
        format="json",
    )
    deleted = api_client.delete(resource_url)

    assert edited.status_code == status.HTTP_404_NOT_FOUND
    assert deleted.status_code == status.HTTP_404_NOT_FOUND
    resource.refresh_from_db()
    assert resource.name == "Private resource"
    assert resource.is_active is True
    assert resource.owner == other_user


@pytest.mark.parametrize(("model", "serializer", "route", "fields", "message"), NAMED_RESOURCES)
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("collision_stage", ["model_validation", "database_constraint"])
def test_name_collision_after_validation_returns_field_error(
    api_client,
    user,
    monkeypatch,
    model,
    serializer,
    route,
    fields,
    message,
    operation,
    collision_stage,
):
    resource = None
    if operation == "update":
        resource = model.objects.create(owner=user, name="Original name", **fields)

    original_validate = serializer.validate
    collision_created = False

    def validate_before_competing_write(instance, attrs):
        nonlocal collision_created
        validated = original_validate(instance, attrs)
        if not collision_created:
            collision_created = True
            model.objects.create(owner=user, name="shared name", **fields)
        return validated

    monkeypatch.setattr(serializer, "validate", validate_before_competing_write)
    if collision_stage == "database_constraint":
        original_full_clean = model.full_clean

        def clean_before_database_constraint(instance, *args, **kwargs):
            kwargs["validate_constraints"] = False
            return original_full_clean(instance, *args, **kwargs)

        monkeypatch.setattr(model, "full_clean", clean_before_database_constraint)

    if operation == "create":
        response = api_client.post(
            reverse(f"{route}-list"),
            {"name": "Shared Name", **fields},
            format="json",
        )
    else:
        response = api_client.patch(
            reverse(f"{route}-detail", args=[resource.id]),
            {"name": "Shared Name"},
            format="json",
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["name"] == message
    assert model.objects.filter(owner=user, name__iexact="shared name").count() == 1
    if resource:
        resource.refresh_from_db()
        assert resource.name == "Original name"


def test_unrelated_integrity_error_is_not_reported_as_duplicate(api_client, monkeypatch):
    def reject_save(instance, *args, **kwargs):
        raise IntegrityError("Unexpected storage failure")

    monkeypatch.setattr(Category, "save", reject_save)

    with pytest.raises(IntegrityError, match="Unexpected storage failure"):
        api_client.post(
            reverse("category-list"),
            {"name": "Groceries", "kind": "expense"},
            format="json",
        )
