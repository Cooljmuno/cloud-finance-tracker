from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from rest_framework.test import APIClient

from apps.finance.models import CategorizationRule, Category, Transaction
from apps.finance.serializers import TransactionSerializer
from apps.users.models import User

pytestmark = pytest.mark.django_db

RULES_URL = "/api/v1/rules/"
APPLY_URL = f"{RULES_URL}apply/"


def make_rule(owner, category, **fields):
    values = {"name": "Market purchases", "match_text": "market", "priority": 100}
    values.update(fields)
    return CategorizationRule.objects.create(owner=owner, category=category, **values)


def transaction_payload(account, **fields):
    values = {
        "account": str(account.id),
        "transaction_date": "2026-10-18",
        "description": "Neighborhood Market",
        "amount": "-12.50",
    }
    values.update(fields)
    return values


def create_transaction(client, account, **fields):
    response = client.post(
        reverse("transaction-list"), transaction_payload(account, **fields), format="json"
    )
    assert response.status_code == 201, response.data
    return response


def test_rule_crud_normalizes_names_and_keeps_history_until_explicit_apply(
    api_client, account, category
):
    entry = create_transaction(api_client, account)
    response = api_client.post(
        RULES_URL,
        {
            "name": "  Market\t purchases  ",
            "match_text": "  Neighborhood\t Market  ",
            "category": str(category.id),
            "priority": 20,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["name"] == "Market purchases"
    assert response.data["match_text"] == "Neighborhood Market"
    assert response.data["category_name"] == category.name
    saved = Transaction.objects.get(pk=entry.data["id"])
    assert saved.category is None
    assert saved.category_source == "uncategorized"
    assert api_client.get(RULES_URL).data["results"] == [response.data]

    detail = f"{RULES_URL}{response.data['id']}/"
    edited = api_client.patch(detail, {"priority": 5, "is_active": False}, format="json")
    assert edited.status_code == 200
    assert edited.data["priority"] == 5
    assert edited.data["is_active"] is False
    assert api_client.delete(detail).status_code == 204
    assert api_client.get(RULES_URL).data["count"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"name": "  "},
        {"match_text": "\t "},
        {"priority": 0},
        {"priority": 10000},
        {"priority": "1.5"},
    ],
)
def test_rule_validation_rejects_unusable_matchers(api_client, category, change):
    response = api_client.post(
        RULES_URL,
        {"name": "Market", "match_text": "market", "category": str(category.id), **change},
        format="json",
    )

    assert response.status_code == 400
    assert CategorizationRule.objects.count() == 0


def test_rule_names_are_case_insensitively_unique_only_for_the_owner(
    api_client, user, other_user, category
):
    make_rule(user, category)
    private_category = Category.objects.create(owner=other_user, name="Food", kind="expense")
    make_rule(other_user, private_category)

    duplicate = api_client.post(
        RULES_URL,
        {
            "name": "MARKET PURCHASES",
            "match_text": "another store",
            "category": str(category.id),
        },
        format="json",
    )

    assert duplicate.status_code == 400
    assert "name" in duplicate.data
    assert api_client.get(RULES_URL).data["count"] == 1


def test_first_matching_rule_uses_priority_then_older_creation_order(
    api_client, user, account, category
):
    alternative = Category.objects.create(owner=user, name="Shopping", kind="expense")
    make_rule(user, alternative, name="Broad low priority", match_text="market", priority=200)
    first = make_rule(user, category, name="First tied rule", priority=10)
    make_rule(user, alternative, name="Newer tied rule", priority=10)

    created = create_transaction(api_client, account, description="  NEIGHBORHOOD\t MARKET  ")

    assert created.data["description"] == "NEIGHBORHOOD MARKET"
    assert created.data["category"] == category.id
    assert created.data["category_source"] == "rule"
    assert created.data["matched_rule"] == first.id
    assert created.data["matched_rule_name"] == first.name
    assert api_client.get(RULES_URL).data["results"][0]["id"] == str(first.id)


def test_disabled_and_archived_category_rules_do_not_match(api_client, user, account, category):
    make_rule(user, category, name="Disabled", priority=1, is_active=False)
    archived = Category.objects.create(owner=user, name="Old food", kind="expense")
    make_rule(user, archived, name="Archived category", priority=2)
    archived.is_active = False
    archived.save(update_fields=["is_active"])
    expected = make_rule(user, category, name="Eligible", priority=3)

    created = create_transaction(api_client, account)

    assert created.data["matched_rule"] == expected.id
    assert created.data["category"] == category.id


def test_rule_match_text_is_a_literal_substring_not_a_regular_expression(
    api_client, user, account, category
):
    rule = make_rule(user, category, match_text="market.*")

    ordinary = create_transaction(api_client, account)
    literal = create_transaction(api_client, account, description="Payment MARKET.* purchase")

    assert ordinary.data["category"] is None
    assert ordinary.data["category_source"] == "uncategorized"
    assert literal.data["matched_rule"] == rule.id


@pytest.mark.parametrize("manual_category", [None, "category"])
def test_explicit_category_including_null_is_a_manual_choice(
    api_client, user, account, category, manual_category
):
    make_rule(user, category)
    selected = str(category.id) if manual_category else None
    created = create_transaction(api_client, account, category=selected)
    detail = reverse("transaction-detail", args=[created.data["id"]])

    changed = api_client.patch(detail, {"description": "Another Market"}, format="json")

    assert created.data["category_source"] == changed.data["category_source"] == "manual"
    if selected:
        assert str(changed.data["category"]) == selected
    else:
        assert changed.data["category"] is None
    assert changed.data["matched_rule"] is None


def test_description_changes_reapply_automatic_choices_but_notes_edits_preserve_them(
    api_client, user, account, category
):
    rule = make_rule(user, category)
    created = create_transaction(api_client, account)
    detail = reverse("transaction-detail", args=[created.data["id"]])
    rule.match_text = "bakery"
    rule.save(update_fields=["match_text"])

    notes_edit = api_client.patch(detail, {"notes": "Reviewed receipt"}, format="json")
    assert notes_edit.status_code == 200
    assert notes_edit.data["matched_rule"] == rule.id
    assert notes_edit.data["category"] == category.id

    no_match = api_client.patch(detail, {"description": "Train ticket"}, format="json")
    assert no_match.status_code == 200
    assert no_match.data["category"] is None
    assert no_match.data["category_source"] == "uncategorized"
    assert no_match.data["matched_rule"] is None

    matched = api_client.patch(detail, {"description": "Corner bakery"}, format="json")
    assert matched.status_code == 200
    assert matched.data["category_source"] == "rule"
    assert matched.data["matched_rule"] == rule.id


def test_modes_can_reenable_automatic_or_preserve_a_category_as_manual(
    api_client, user, account, category
):
    rule = make_rule(user, category)
    created = create_transaction(api_client, account, category=None)
    detail = reverse("transaction-detail", args=[created.data["id"]])

    automatic = api_client.patch(detail, {"category_mode": "automatic"}, format="json")
    assert automatic.status_code == 200
    assert automatic.data["matched_rule"] == rule.id
    manual = api_client.patch(detail, {"category_mode": "manual"}, format="json")
    assert manual.status_code == 200
    assert manual.data["category"] == category.id
    assert manual.data["category_source"] == "manual"
    assert manual.data["matched_rule"] is None


@pytest.mark.parametrize(
    "stale_edit", [{"notes": "Reviewed receipt"}, {"description": "Another market"}]
)
def test_validated_stale_edit_preserves_a_newer_manual_uncategorized_choice(
    api_client, user, account, category, stale_edit
):
    make_rule(user, category)
    created = create_transaction(api_client, account)
    stale_entry = Transaction.objects.get(pk=created.data["id"])
    serializer = TransactionSerializer(
        stale_entry,
        data=stale_edit,
        partial=True,
        context={"request": SimpleNamespace(user=user)},
    )
    assert serializer.is_valid(), serializer.errors
    manual = api_client.patch(
        reverse("transaction-detail", args=[stale_entry.id]), {"category": None}, format="json"
    )
    assert manual.status_code == 200

    saved = serializer.save()

    assert saved.category_id is None
    assert saved.category_source == "manual"
    assert saved.matched_rule_id is None
    for field, expected in stale_edit.items():
        assert getattr(saved, field) == expected


def test_automatic_mode_rejects_a_conflicting_explicit_category(api_client, account, category):
    response = api_client.post(
        reverse("transaction-list"),
        transaction_payload(account, category=str(category.id), category_mode="automatic"),
        format="json",
    )

    assert response.status_code == 400
    assert Transaction.objects.count() == 0


def test_transaction_provenance_is_read_only(api_client, user, account, category):
    rule = make_rule(user, category)
    response = create_transaction(
        api_client,
        account,
        description="Train ticket",
        category_source="rule",
        matched_rule=str(rule.id),
    )

    assert response.data["category_source"] == "uncategorized"
    assert response.data["matched_rule"] is None


def test_apply_changes_only_unassigned_automatic_entries(api_client, user, account, category):
    manual_null = create_transaction(api_client, account, category=None)
    manual_category = create_transaction(api_client, account, category=str(category.id))
    eligible = create_transaction(api_client, account)
    unmatched = create_transaction(api_client, account, description="Bus ticket")
    first_rule = make_rule(user, category)
    already_assigned = create_transaction(api_client, account)
    replacement = Category.objects.create(owner=user, name="New food", kind="expense")
    first_rule.category = replacement
    first_rule.save(update_fields=["category"])

    applied = api_client.post(APPLY_URL, {}, format="json")

    assert applied.status_code == 200
    assert applied.data == {"examined": 2, "updated": 1}
    records = {str(row.id): row for row in Transaction.objects.all()}
    assert records[eligible.data["id"]].category_id == replacement.id
    assert records[unmatched.data["id"]].category is None
    assert records[manual_null.data["id"]].category is None
    assert records[manual_null.data["id"]].category_source == "manual"
    assert records[manual_category.data["id"]].category_id == category.id
    assert records[already_assigned.data["id"]].category_id == category.id
    assert api_client.post(APPLY_URL, {}, format="json").data == {"examined": 1, "updated": 0}


def test_apply_failure_after_a_write_rolls_back_every_category_change(
    api_client, user, account, category, monkeypatch
):
    create_transaction(api_client, account)
    create_transaction(api_client, account)
    make_rule(user, category)
    original_save = Transaction.save
    writes = 0

    def save_then_fail_second_entry(entry, *args, **kwargs):
        nonlocal writes
        result = original_save(entry, *args, **kwargs)
        if entry.category_source == "rule":
            writes += 1
            if writes == 2:
                assert Transaction.objects.filter(category_source="rule").count() == 2
                raise RuntimeError("Synthetic category storage failure")
        return result

    monkeypatch.setattr(Transaction, "save", save_then_fail_second_entry)

    with pytest.raises(RuntimeError, match="Synthetic category storage failure"):
        api_client.post(APPLY_URL, {}, format="json")

    assert writes == 2
    assert Transaction.objects.filter(category_source="uncategorized", category=None).count() == 2
    assert not Transaction.objects.filter(category_source="rule").exists()


def test_import_evaluates_current_rules_at_commit_and_exact_retry_preserves_result(
    api_client, user, account, category
):
    content = (
        b"transaction_date,description,amount,status,notes\n"
        b"2026-10-18,Neighborhood Market,-12.50,posted,\n"
    )

    def upload(url, token=None):
        payload = {
            "account": str(account.id),
            "file": SimpleUploadedFile("rules.csv", content, content_type="text/csv"),
        }
        if token:
            payload["preview_token"] = token
        return api_client.post(url, payload, format="multipart")

    preview = upload("/api/v1/imports/preview/")
    assert preview.status_code == 200
    assert Transaction.objects.count() == 0
    rule = make_rule(user, category)
    committed = upload("/api/v1/imports/commit/", preview.data["preview_token"])
    assert committed.status_code == 201
    imported = Transaction.objects.get()
    assert imported.category_id == category.id
    assert imported.category_source == "rule"
    assert imported.matched_rule_id == rule.id
    alternative = Category.objects.create(owner=user, name="Other food", kind="expense")
    rule.category = alternative
    rule.save(update_fields=["category"])

    duplicate = upload("/api/v1/imports/commit/", preview.data["preview_token"])

    assert duplicate.status_code == 200
    assert duplicate.data["duplicate"] is True
    imported.refresh_from_db()
    assert imported.category_id == category.id
    assert Transaction.objects.count() == 1


def test_rules_cannot_reference_foreign_or_newly_archived_categories(
    api_client, user, other_user, category
):
    own_rule = make_rule(user, category)
    private = Category.objects.create(owner=other_user, name="Private", kind="expense")
    archived = Category.objects.create(owner=user, name="Archived", kind="expense", is_active=False)
    detail = f"{RULES_URL}{own_rule.id}/"
    for invalid_category in (private, archived):
        rejected = api_client.patch(detail, {"category": str(invalid_category.id)}, format="json")
        assert rejected.status_code == 400
        assert "category" in rejected.data

    category.is_active = False
    category.save(update_fields=["is_active"])
    historical = api_client.patch(
        detail, {"name": "Reviewed rule", "category": str(category.id)}, format="json"
    )
    assert historical.status_code == 200


def test_rule_history_blocks_category_deletion_and_rule_deletion_preserves_transaction(
    api_client, user, account, category
):
    rule = make_rule(user, category)
    assert api_client.delete(reverse("category-detail", args=[category.id])).status_code == 409
    created = create_transaction(api_client, account)
    assert api_client.delete(f"{RULES_URL}{rule.id}/").status_code == 204

    saved = Transaction.objects.get(pk=created.data["id"])
    assert saved.category_id == category.id
    assert saved.category_source == "rule"
    assert saved.matched_rule_id is None


def test_rule_endpoints_scope_every_operation_to_the_owner(
    api_client, user, other_user, account, category
):
    private_category = Category.objects.create(owner=other_user, name="Private", kind="expense")
    private_rule = make_rule(other_user, private_category)
    detail = f"{RULES_URL}{private_rule.id}/"
    assert api_client.get(RULES_URL).data["count"] == 0
    assert api_client.get(detail).status_code == 404
    assert api_client.patch(detail, {"name": "Changed"}, format="json").status_code == 404
    assert api_client.delete(detail).status_code == 404
    create_transaction(api_client, account)
    assert api_client.post(APPLY_URL, {}, format="json").data == {"examined": 1, "updated": 0}

    for url in (RULES_URL, APPLY_URL):
        anonymous = APIClient()
        response = anonymous.post(url, {}, format="json")
        assert response.status_code == 401


def test_rule_and_transaction_model_guards_prevent_cross_owner_relations(
    user, other_user, account, category
):
    private = Category.objects.create(owner=other_user, name="Private", kind="expense")
    with pytest.raises(ValidationError):
        make_rule(user, private)
    invalid = CategorizationRule(owner=user, category=private, name="Bulk", match_text="market")
    with pytest.raises(ValidationError):
        CategorizationRule.objects.bulk_create([invalid])

    private_rule = make_rule(other_user, private)
    invalid_entry = Transaction(
        owner=user,
        account=account,
        category=category,
        category_source="rule",
        matched_rule=private_rule,
        transaction_date=date(2026, 10, 18),
        description="Neighborhood Market",
        amount=Decimal("-1.00"),
    )
    with pytest.raises(ValidationError):
        Transaction.objects.bulk_create([invalid_entry])
    own_rule = make_rule(user, category)
    with pytest.raises(ValueError, match="ownership changes"):
        CategorizationRule.objects.filter(pk=own_rule.pk).update(category=private)
    own_rule.owner = other_user
    with pytest.raises(ValidationError, match="Owner cannot be changed"):
        own_rule.save()


def test_matched_rule_cannot_be_changed_with_unchecked_queryset_or_bulk_update(
    user, account, category
):
    rule = make_rule(user, category)
    entry = Transaction.objects.create(
        owner=user,
        account=account,
        category=category,
        transaction_date=date(2026, 10, 18),
        description="Neighborhood Market",
        amount=Decimal("-1.00"),
    )

    with pytest.raises(ValueError, match="ownership changes"):
        Transaction.objects.filter(pk=entry.pk).update(matched_rule=rule)
    entry.matched_rule = rule
    entry.category_source = "rule"
    with pytest.raises(ValueError, match="ownership changes"):
        Transaction.objects.bulk_update([entry], ["matched_rule", "category_source"])


@pytest.mark.django_db(transaction=True)
def test_phase4_migration_preserves_legacy_categories_and_uncategorized_manual_choices():
    previous = ("finance", "0002_importbatch_transaction_import_batch_and_more")
    current = ("finance", "0003_transaction_category_source_categorizationrule_and_more")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([previous])
        old_apps = executor.loader.project_state([previous]).apps
        old_user = old_apps.get_model("users", "User").objects.create(
            username="legacy-category-migration"
        )
        old_account = old_apps.get_model("finance", "FinancialAccount").objects.create(
            owner_id=old_user.id, name="Legacy checking", account_type="checking"
        )
        old_category = old_apps.get_model("finance", "Category").objects.create(
            owner_id=old_user.id, name="Legacy groceries", kind="expense"
        )
        old_transaction = old_apps.get_model("finance", "Transaction")
        base = {
            "owner_id": old_user.id,
            "account_id": old_account.id,
            "transaction_date": date(2026, 10, 17),
            "description": "Legacy market purchase",
            "amount": Decimal("-5.00"),
        }
        categorized = old_transaction.objects.create(category_id=old_category.id, **base)
        uncategorized = old_transaction.objects.create(**base)
        MigrationExecutor(connection).migrate([current])

        preserved_category = Transaction.objects.get(pk=categorized.id)
        preserved_null = Transaction.objects.get(pk=uncategorized.id)
        assert preserved_category.category_id == old_category.id
        assert preserved_null.category_id is None
        assert preserved_category.category_source == preserved_null.category_source == "manual"
        assert preserved_category.matched_rule_id is preserved_null.matched_rule_id is None
        owner = User.objects.get(pk=old_user.id)
        category = Category.objects.get(pk=old_category.id)
        make_rule(owner, category)
        client = APIClient()
        client.force_authenticate(user=owner)
        assert client.post(APPLY_URL, {}, format="json").data == {"examined": 0, "updated": 0}
        new_entry = create_transaction(client, old_account, description="Train ticket")
        assert new_entry.data["category_source"] == "uncategorized"
    finally:
        MigrationExecutor(connection).migrate([current])
