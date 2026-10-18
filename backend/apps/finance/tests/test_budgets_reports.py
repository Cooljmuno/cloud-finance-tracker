import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections, models
from django.db import transaction as db_transaction
from django.urls import reverse
from rest_framework.test import APIClient

from apps.finance.models import Category, FinancialAccount, MonthlyBudget, Transaction
from apps.finance.planning_serializers import MonthlyBudgetSerializer
from apps.users.models import User

pytestmark = pytest.mark.django_db

BUDGETS_URL = "/api/v1/budgets/"
REPORT_URL = "/api/v1/reports/monthly/"


def make_budget(owner, category, **fields):
    values = {"month": date(2026, 1, 1), "currency": "USD", "amount": Decimal("100.00")}
    values.update(fields)
    return MonthlyBudget.objects.create(owner=owner, category=category, **values)


def add_entry(owner, account, amount, category=None, **fields):
    values = {
        "transaction_date": date(2026, 1, 15),
        "description": "Synthetic report entry",
        "status": "posted",
    }
    values.update(fields)
    return Transaction.objects.create(
        owner=owner, account=account, amount=Decimal(amount), category=category, **values
    )


def test_budget_crud_uses_months_currency_and_decimal_strings(api_client, category):
    created = api_client.post(
        BUDGETS_URL,
        {"category": str(category.id), "month": "2026-01", "currency": "usd", "amount": "120.10"},
        format="json",
    )

    assert created.status_code == 201, created.data
    assert created.data["month"] == "2026-01"
    assert created.data["currency"] == "USD"
    assert created.data["amount"] == "120.10"
    assert created.data["category_name"] == category.name
    assert MonthlyBudget.objects.get().month == date(2026, 1, 1)
    detail = f"{BUDGETS_URL}{created.data['id']}/"
    edited = api_client.patch(detail, {"amount": "130.25"}, format="json")
    assert edited.status_code == 200
    assert edited.data["amount"] == "130.25"
    listing = api_client.get(BUDGETS_URL, {"month": "2026-01", "currency": "usd"})
    assert listing.status_code == 200
    assert listing.data["results"] == [edited.data]
    assert api_client.delete(detail).status_code == 204
    assert not MonthlyBudget.objects.exists()


@pytest.mark.parametrize("amount", ["0", "-0.01", "1.001", "1000000000000.00"])
def test_budget_requires_a_positive_bounded_cent_amount(api_client, category, amount):
    response = api_client.post(
        BUDGETS_URL,
        {"category": str(category.id), "month": "2026-01", "amount": amount},
        format="json",
    )

    assert response.status_code == 400
    assert "amount" in response.data
    assert not MonthlyBudget.objects.exists()


@pytest.mark.parametrize(
    "month", ["2026-1", "2026-00", "2026-13", "2026-01-01", "0000-01", " 2026-01"]
)
def test_budget_month_format_is_strict_for_writes_and_filters(api_client, category, month):
    response = api_client.post(
        BUDGETS_URL,
        {"category": str(category.id), "month": month, "amount": "10.00"},
        format="json",
    )
    filtered = api_client.get(BUDGETS_URL, {"month": month})

    assert response.status_code == filtered.status_code == 400
    assert not MonthlyBudget.objects.exists()


@pytest.mark.parametrize("currency", ["US", "USDX", "U$D", "ÜSD"])
def test_currency_filters_and_budget_writes_reject_non_ascii_currency_codes(
    api_client, category, currency
):
    response = api_client.post(
        BUDGETS_URL,
        {"category": str(category.id), "month": "2026-01", "currency": currency, "amount": "10.00"},
        format="json",
    )

    assert response.status_code == 400
    assert api_client.get(BUDGETS_URL, {"currency": currency}).status_code == 400
    assert api_client.get(REPORT_URL, {"month": "2026-01", "currency": currency}).status_code == 400


def test_budget_categories_must_be_owned_expenses_and_active_for_new_assignments(
    api_client, user, other_user, category
):
    invalid_categories = [
        Category.objects.create(owner=user, name="Salary", kind="income"),
        Category.objects.create(owner=user, name="Transfers", kind="transfer"),
        Category.objects.create(owner=user, name="Old expense", kind="expense", is_active=False),
        Category.objects.create(owner=other_user, name="Private", kind="expense"),
    ]
    for invalid in invalid_categories:
        response = api_client.post(
            BUDGETS_URL,
            {"category": str(invalid.id), "month": "2026-01", "amount": "10.00"},
            format="json",
        )
        assert response.status_code == 400
        assert "category" in response.data

    budget = make_budget(user, category)
    category.is_active = False
    category.save(update_fields=["is_active"])
    edited = api_client.patch(
        f"{BUDGETS_URL}{budget.id}/",
        {"category": str(category.id), "amount": "110.00"},
        format="json",
    )
    assert edited.status_code == 200
    assert edited.data["amount"] == "110.00"


def test_budget_uniqueness_is_per_owner_category_month_and_currency(api_client, user, category):
    make_budget(user, category)
    duplicate = api_client.post(
        BUDGETS_URL,
        {"category": str(category.id), "month": "2026-01", "currency": "USD", "amount": "5.00"},
        format="json",
    )
    assert duplicate.status_code == 400
    make_budget(user, category, month=date(2026, 2, 1))
    make_budget(user, category, currency="EUR")
    assert api_client.get(BUDGETS_URL, {"month": "2026-01"}).data["count"] == 2
    assert api_client.get(BUDGETS_URL, {"currency": "USD"}).data["count"] == 2
    assert api_client.get(BUDGETS_URL, {"month": "2026-02", "currency": "EUR"}).data["count"] == 0

    duplicate_model = MonthlyBudget(
        owner=user,
        category=category,
        month=date(2026, 1, 1),
        currency="USD",
        amount=Decimal("5.00"),
    )
    with pytest.raises(IntegrityError), db_transaction.atomic():
        models.QuerySet.bulk_create(MonthlyBudget.objects.all(), [duplicate_model])
    existing = MonthlyBudget.objects.get(month=date(2026, 1, 1), currency="USD")
    with pytest.raises(IntegrityError), db_transaction.atomic():
        MonthlyBudget.objects.filter(pk=existing.pk).update(amount=Decimal("0.00"))


@pytest.mark.parametrize("operation", ["create", "update"])
def test_budget_collision_after_validation_returns_a_validation_error(
    api_client, user, category, monkeypatch, operation
):
    original = None
    if operation == "update":
        original = make_budget(user, category, month=date(2026, 2, 1))
    original_validate = MonthlyBudgetSerializer.validate
    inserted = False

    def validate_before_competing_write(serializer, attrs):
        nonlocal inserted
        validated = original_validate(serializer, attrs)
        if not inserted:
            inserted = True
            make_budget(user, category)
        return validated

    monkeypatch.setattr(MonthlyBudgetSerializer, "validate", validate_before_competing_write)

    if operation == "create":
        response = api_client.post(
            BUDGETS_URL,
            {"category": str(category.id), "month": "2026-01", "currency": "USD", "amount": "9.00"},
            format="json",
        )
    else:
        response = api_client.patch(
            f"{BUDGETS_URL}{original.id}/", {"month": "2026-01"}, format="json"
        )

    assert response.status_code == 400
    assert MonthlyBudget.objects.filter(month=date(2026, 1, 1), currency="USD").count() == 1
    if original:
        original.refresh_from_db()
        assert original.month == date(2026, 2, 1)


@pytest.mark.django_db(transaction=True)
def test_simultaneous_budget_requests_create_one_budget_and_return_a_useful_conflict(
    user, category, monkeypatch
):
    if connection.vendor != "postgresql":
        pytest.skip("Concurrent budget locking must be verified against PostgreSQL.")
    original_validate = MonthlyBudgetSerializer.validate
    barrier = threading.Barrier(2)
    thread_state = threading.local()

    def validate_before_simultaneous_save(serializer, attrs):
        validated = original_validate(serializer, attrs)
        if not getattr(thread_state, "validated", False):
            thread_state.validated = True
            barrier.wait(timeout=10)
        return validated

    monkeypatch.setattr(MonthlyBudgetSerializer, "validate", validate_before_simultaneous_save)
    owner_id = user.id
    category_id = str(category.id)

    def create_on_independent_connection():
        close_old_connections()
        try:
            owner = User.objects.get(pk=owner_id)
            client = APIClient()
            client.force_authenticate(user=owner)
            response = client.post(
                BUDGETS_URL,
                {"category": category_id, "month": "2026-01", "currency": "USD", "amount": "10.00"},
                format="json",
            )
            return response.status_code, response.data
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create_on_independent_connection) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]

    assert sorted(code for code, _ in results) == [201, 400], results
    assert MonthlyBudget.objects.filter(owner=user, category=category).count() == 1
    rejected = next(payload for code, payload in results if code == 400)
    assert "category" in rejected


def test_category_with_a_budget_cannot_change_kind_or_be_deleted(api_client, user, category):
    make_budget(user, category)
    detail = reverse("category-detail", args=[category.id])

    changed = api_client.patch(detail, {"kind": "income"}, format="json")

    assert changed.status_code == 400
    assert "kind" in changed.data
    assert api_client.delete(detail).status_code == 409
    assert api_client.patch(detail, {"is_active": False}, format="json").status_code == 200
    category.refresh_from_db()
    assert category.kind == "expense"


def test_budget_owner_and_category_guards_apply_to_model_and_bulk_paths(user, other_user, category):
    private_category = Category.objects.create(owner=other_user, name="Private", kind="expense")
    with pytest.raises(ValidationError):
        make_budget(user, private_category)
    invalid = MonthlyBudget(
        owner=user,
        category=private_category,
        month=date(2026, 1, 1),
        amount=Decimal("10.00"),
    )
    with pytest.raises(ValidationError):
        MonthlyBudget.objects.bulk_create([invalid])
    with pytest.raises(ValidationError):
        make_budget(user, category, month=date(2026, 1, 2))

    budget = make_budget(user, category)
    with pytest.raises(ValueError, match="ownership changes"):
        MonthlyBudget.objects.filter(pk=budget.pk).update(category=private_category)
    budget.category = private_category
    with pytest.raises(ValueError, match="ownership changes"):
        MonthlyBudget.objects.bulk_update([budget], ["category"])
    budget.category = category
    budget.owner = other_user
    with pytest.raises(ValidationError, match="Owner cannot be changed"):
        budget.save()


def test_budget_list_detail_and_mutations_are_owner_scoped(api_client, user, other_user):
    private_category = Category.objects.create(owner=other_user, name="Private", kind="expense")
    private_budget = make_budget(other_user, private_category)
    detail = f"{BUDGETS_URL}{private_budget.id}/"

    assert api_client.get(BUDGETS_URL).data["count"] == 0
    assert api_client.get(detail).status_code == 404
    assert api_client.patch(detail, {"amount": "1.00"}, format="json").status_code == 404
    assert api_client.delete(detail).status_code == 404
    anonymous = APIClient()
    assert anonymous.get(BUDGETS_URL).status_code == 401
    assert anonymous.get(REPORT_URL, {"month": "2026-01"}).status_code == 401


@pytest.mark.parametrize(
    "month",
    [None, "2026-1", "2026-00", "2026-13", "2026-01-01", "0000-01", "0001-05", " 2026-01"],
)
def test_report_requires_a_strict_month_with_room_for_six_months(api_client, month):
    params = {} if month is None else {"month": month}
    assert api_client.get(REPORT_URL, params).status_code == 400


def test_report_handles_signed_refunds_income_pending_transfers_archives_and_currencies(
    api_client, user, other_user, account, category
):
    income = Category.objects.create(owner=user, name="Salary", kind="income")
    transfer = Category.objects.create(owner=user, name="Transfers", kind="transfer")
    unused = Category.objects.create(owner=user, name="Rent", kind="expense")
    archived_account = FinancialAccount.objects.create(
        owner=user, name="Retired account", account_type="checking", is_active=False
    )
    euro_account = FinancialAccount.objects.create(
        owner=user, name="Euro account", account_type="checking", currency="EUR"
    )
    foreign_account = FinancialAccount.objects.create(
        owner=other_user, name="Private account", account_type="checking"
    )
    add_entry(user, account, "-100.25", category)
    add_entry(user, account, "20.10", category)
    add_entry(user, archived_account, "-2.20", category)
    add_entry(user, account, "1000.00", income)
    add_entry(user, account, "-50.00", income)
    add_entry(user, account, "-8.35")
    add_entry(user, account, "5.00")
    add_entry(user, account, "-300.00", transfer)
    add_entry(user, account, "300.00", transfer)
    add_entry(user, account, "-99.00", category, status="pending")
    add_entry(user, account, "7.00", status="pending")
    add_entry(user, account, "-33.00", transfer, status="pending")
    add_entry(user, euro_account, "-777.00", category)
    add_entry(other_user, foreign_account, "-111.00")
    add_entry(user, account, "-0.10", category, transaction_date=date(2025, 8, 31))
    add_entry(user, account, "10.00", income, transaction_date=date(2025, 9, 1))
    add_entry(user, account, "3.00", category, transaction_date=date(2025, 11, 15))
    add_entry(user, account, "-0.20", transaction_date=date(2025, 12, 31))
    add_entry(user, account, "-123.00", category, transaction_date=date(2026, 2, 1))
    make_budget(user, category)
    rent_budget = make_budget(user, unused, amount=Decimal("30.00"))
    category.is_active = False
    category.save(update_fields=["is_active"])

    response = api_client.get(REPORT_URL, {"month": "2026-01", "currency": "usd"})

    assert response.status_code == 200, response.data
    report = response.data
    assert report["month"] == "2026-01"
    assert report["currency"] == "USD"
    assert report["transaction_count"] == 7
    assert report["pending_count"] == 2
    assert report["totals"] == {
        "income": "955.00",
        "spending": "90.70",
        "net": "864.30",
        "uncategorized_spending": "8.35",
    }
    assert report["trend"] == [
        {"month": "2025-08", "income": "0.00", "spending": "0.10"},
        {"month": "2025-09", "income": "10.00", "spending": "0.00"},
        {"month": "2025-10", "income": "0.00", "spending": "0.00"},
        {"month": "2025-11", "income": "0.00", "spending": "-3.00"},
        {"month": "2025-12", "income": "0.00", "spending": "0.20"},
        {"month": "2026-01", "income": "955.00", "spending": "90.70"},
    ]
    assert [row["category_name"] for row in report["categories"]] == [
        category.name,
        "Uncategorized",
        "Rent",
    ]
    groceries, uncategorized, rent = report["categories"]
    assert groceries["spending"] == "82.35"
    assert groceries["budget"] == "100.00"
    assert groceries["remaining"] == "17.65"
    assert uncategorized == {
        "category": None,
        "category_name": "Uncategorized",
        "spending": "8.35",
        "budget": None,
        "remaining": None,
        "budget_id": None,
    }
    assert rent["spending"] == "0.00"
    assert rent["budget"] == rent["remaining"] == "30.00"
    assert str(rent["budget_id"]) == str(rent_budget.id)

    euros = api_client.get(REPORT_URL, {"month": "2026-01", "currency": "EUR"})
    assert euros.status_code == 200
    assert euros.data["transaction_count"] == 1
    assert euros.data["totals"]["spending"] == "777.00"
    assert euros.data["categories"][0]["budget"] is None


def test_report_preserves_exact_cents_negative_spending_and_budget_only_rows(
    api_client, user, account, category
):
    refunds = Category.objects.create(owner=user, name="Refunds", kind="expense")
    unused = Category.objects.create(owner=user, name="Unused", kind="expense")
    add_entry(user, account, "-0.10", category)
    add_entry(user, account, "-0.20", category)
    add_entry(user, account, "2.00", refunds)
    make_budget(user, refunds, amount=Decimal("1.00"))
    make_budget(user, unused, amount=Decimal("10.00"))

    report = api_client.get(REPORT_URL, {"month": "2026-01"}).data

    assert report["totals"] == {
        "income": "0.00",
        "spending": "-1.70",
        "net": "1.70",
        "uncategorized_spending": "0.00",
    }
    assert [row["spending"] for row in report["categories"]] == ["0.30", "0.00", "-2.00"]
    refund_row = report["categories"][2]
    assert refund_row["category_name"] == "Refunds"
    assert refund_row["remaining"] == "3.00"


def test_empty_report_is_six_zero_filled_months_and_accepts_the_earliest_supported_month(
    api_client,
):
    response = api_client.get(REPORT_URL, {"month": "0001-06"})

    assert response.status_code == 200
    report = response.data
    assert report["categories"] == []
    assert report["transaction_count"] == report["pending_count"] == 0
    assert report["totals"] == {
        "income": "0.00",
        "spending": "0.00",
        "net": "0.00",
        "uncategorized_spending": "0.00",
    }
    assert report["trend"] == [
        {"month": f"0001-{month:02d}", "income": "0.00", "spending": "0.00"}
        for month in range(1, 7)
    ]
