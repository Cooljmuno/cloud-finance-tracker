import csv
import hashlib
import io
import time
from decimal import Decimal

import pytest
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APIClient

from apps.finance.imports import PREVIEW_SALT
from apps.finance.models import FinancialAccount, ImportBatch, Transaction, TransactionQuerySet

pytestmark = pytest.mark.django_db

HEADERS = ["transaction_date", "description", "amount", "status", "notes"]
PREVIEW_URL = "/api/v1/imports/preview/"
COMMIT_URL = "/api/v1/imports/commit/"
HISTORY_URL = "/api/v1/imports/"
VALID_ROW = ["2026-10-17", "Synthetic market", "-12.50", "posted", "Sample purchase"]


def csv_bytes(rows=None, headers=None):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(HEADERS if headers is None else headers)
    writer.writerows([VALID_ROW] if rows is None else rows)
    return buffer.getvalue().encode("utf-8")


def post_import(client, url, account, content, token=None, name="statement.csv"):
    payload = {
        "account": str(account.id),
        "file": SimpleUploadedFile(name, content, content_type="text/csv"),
    }
    if token is not None:
        payload["preview_token"] = token
    return client.post(url, payload, format="multipart")


def preview_token(client, account, content):
    response = post_import(client, PREVIEW_URL, account, content)
    assert response.status_code == 200, response.data
    assert response.data["can_commit"] is True, response.data
    return response.data["preview_token"]


def create_account(owner, name="Another account"):
    return FinancialAccount.objects.create(owner=owner, name=name, account_type="checking")


@pytest.mark.parametrize("url", [PREVIEW_URL, COMMIT_URL, HISTORY_URL])
def test_import_endpoints_require_authentication(url, account):
    client = APIClient()
    response = (
        client.get(url)
        if url == HISTORY_URL
        else post_import(client, url, account, csv_bytes(), "untrusted-token")
    )

    assert response.status_code in {401, 403}
    assert ImportBatch.objects.count() == 0
    assert Transaction.objects.count() == 0


def test_preview_normalizes_valid_rows_without_writing_finance_data(api_client, account):
    content = b"\xef\xbb\xbf" + csv_bytes(
        [
            ["2026-10-17", "  Synthetic\t market  ", "-12.5", "", "Sample note"],
            ["2026-10-18", "Salary", "2500", "pending", ""],
        ]
    )

    response = post_import(api_client, PREVIEW_URL, account, content)

    assert response.status_code == 200
    report = response.data
    assert report["account"] == str(account.id)
    assert report["row_count"] == report["valid_count"] == 2
    assert report["error_count"] == 0
    assert report["errors"] == []
    assert report["preview_truncated"] is False
    assert report["can_commit"] is True
    assert report["preview_token"]
    assert report["already_imported"] is None
    assert report["rows"][0] == {
        "row": 2,
        "transaction_date": "2026-10-17",
        "description": "Synthetic market",
        "amount": "-12.50",
        "status": "posted",
        "notes": "Sample note",
    }
    assert report["rows"][1]["amount"] == "2500.00"
    assert ImportBatch.objects.count() == 0
    assert Transaction.objects.count() == 0


def test_preview_limits_displayed_rows_without_limiting_the_import(api_client, account):
    content = csv_bytes([VALID_ROW] * 25)

    preview = post_import(api_client, PREVIEW_URL, account, content)

    assert preview.status_code == 200
    assert preview.data["row_count"] == preview.data["valid_count"] == 25
    assert len(preview.data["rows"]) == 20
    assert preview.data["preview_truncated"] is True
    saved = post_import(api_client, COMMIT_URL, account, content, preview.data["preview_token"])
    assert saved.status_code == 201
    assert saved.data["batch"]["row_count"] == 25
    assert Transaction.objects.count() == 25


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transaction_date", "2026-2-03"),
        ("transaction_date", "2026-02-30"),
        ("transaction_date", "20261017"),
        ("description", " \t "),
        ("description", "x" * 256),
        ("amount", "0.00"),
        ("amount", "NaN"),
        ("amount", "Infinity"),
        ("amount", "1e2"),
        ("amount", "+1.00"),
        ("amount", "1.001"),
        ("amount", "1000000000000.00"),
        ("status", "cleared"),
        ("notes", "x" * 1001),
    ],
)
def test_invalid_row_has_useful_error_and_cannot_be_committed(api_client, account, field, value):
    invalid_row = VALID_ROW.copy()
    invalid_row[HEADERS.index(field)] = value
    response = post_import(api_client, PREVIEW_URL, account, csv_bytes([invalid_row]))

    assert response.status_code == 200
    assert response.data["row_count"] == 1
    assert response.data["valid_count"] == 0
    assert response.data["error_count"] >= 1
    assert any(
        error["row"] == 2 and error["field"] == field and error["message"]
        for error in response.data["errors"]
    )
    assert response.data["can_commit"] is False
    assert response.data["preview_token"] is None
    assert ImportBatch.objects.count() == 0
    assert Transaction.objects.count() == 0


def test_invalid_preview_keeps_valid_rows_and_counts_all_errors(api_client, account):
    invalid_row = [*VALID_ROW[:2], "0", *VALID_ROW[3:]]
    response = post_import(
        api_client, PREVIEW_URL, account, csv_bytes([invalid_row] * 60 + [VALID_ROW])
    )

    assert response.status_code == 200
    assert response.data["row_count"] == 61
    assert response.data["valid_count"] == 1
    assert response.data["error_count"] == 60
    assert len(response.data["errors"]) == 50
    assert response.data["errors_truncated"] is True
    assert response.data["rows"][0]["row"] == 62
    assert response.data["preview_token"] is None
    assert response.data["can_commit"] is False


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"\xff\xfe\x80",
        csv_bytes([]),
        csv_bytes(headers=["date", *HEADERS[1:]]),
        csv_bytes(headers=[HEADERS[1], HEADERS[0], *HEADERS[2:]]),
        csv_bytes(headers=HEADERS[:-1]),
        csv_bytes(headers=[*HEADERS, "extra"]),
        (",".join(HEADERS) + '\n2026-10-17,"unterminated,-12.50,posted,\n').encode(),
        b"x" * (256 * 1024 + 1),
        csv_bytes([VALID_ROW] * 501),
    ],
    ids=[
        "empty",
        "bad-utf8",
        "header-only",
        "wrong-header",
        "reordered-header",
        "missing-header",
        "extra-header",
        "malformed-quoting",
        "oversize",
        "too-many-rows",
    ],
)
def test_invalid_files_return_a_request_error_without_writes(api_client, account, content):
    response = post_import(api_client, PREVIEW_URL, account, content)

    assert response.status_code == 400
    assert response.data["detail"]
    assert ImportBatch.objects.count() == 0
    assert Transaction.objects.count() == 0


def test_blank_records_are_ignored_and_quoted_notes_preserve_newlines(api_client, account):
    content = csv_bytes(
        [[], ["2026-10-17", "Synthetic market", "-1.00", "posted", "First\nSecond"], []]
    )

    response = post_import(api_client, PREVIEW_URL, account, content)

    assert response.status_code == 200
    assert response.data["row_count"] == 1
    assert response.data["rows"][0]["row"] == 3
    assert response.data["rows"][0]["notes"] == "First\nSecond"


@pytest.mark.parametrize("url", [PREVIEW_URL, COMMIT_URL])
def test_another_users_account_cannot_receive_imports(api_client, other_user, url):
    private_account = create_account(other_user)
    response = post_import(api_client, url, private_account, csv_bytes(), "untrusted-token")

    assert response.status_code == 404
    assert ImportBatch.objects.count() == 0
    assert Transaction.objects.count() == 0


def test_commit_saves_all_rows_with_receipt_and_preserves_identical_purchases(
    api_client, user, account
):
    content = csv_bytes([VALID_ROW, VALID_ROW])
    token = preview_token(api_client, account, content)

    response = post_import(api_client, COMMIT_URL, account, content, token)

    assert response.status_code == 201
    assert response.data["duplicate"] is False
    receipt = response.json()["batch"]
    batch = ImportBatch.objects.get(pk=receipt["id"])
    assert batch.owner == user
    assert batch.account == account
    assert batch.file_name == "statement.csv"
    assert batch.file_hash == hashlib.sha256(content).hexdigest()
    assert batch.row_count == receipt["row_count"] == 2
    assert receipt["account"] == str(account.id)
    assert receipt["account_name"] == account.name
    assert receipt["created_at"]
    assert Transaction.objects.filter(owner=user, account=account, import_batch=batch).count() == 2
    assert set(Transaction.objects.values_list("amount", flat=True)) == {Decimal("-12.50")}
    assert not Transaction.objects.exclude(category=None).exists()


def test_repeated_identical_file_returns_original_receipt_even_when_renamed(api_client, account):
    content = csv_bytes()
    token = preview_token(api_client, account, content)
    created = post_import(api_client, COMMIT_URL, account, content, token)

    repeated = post_import(api_client, COMMIT_URL, account, content, token, name="renamed.csv")
    preview = post_import(api_client, PREVIEW_URL, account, content, name="renamed.csv")

    assert created.status_code == 201
    assert repeated.status_code == 200
    assert repeated.data == {"batch": created.data["batch"], "duplicate": True}
    assert preview.status_code == 200
    assert preview.data["already_imported"] == created.data["batch"]
    assert preview.data["can_commit"] is False
    assert ImportBatch.objects.count() == Transaction.objects.count() == 1


def test_same_bytes_in_another_account_and_overlapping_statements_are_separate_imports(
    api_client, user, account
):
    second_account = create_account(user)
    first_content = csv_bytes([VALID_ROW, VALID_ROW])
    overlapping_content = csv_bytes(
        [VALID_ROW, ["2026-10-18", "Different purchase", "-8.00", "posted", ""]]
    )

    for target, content in (
        (account, first_content),
        (second_account, first_content),
        (account, overlapping_content),
    ):
        token = preview_token(api_client, target, content)
        response = post_import(api_client, COMMIT_URL, target, content, token)
        assert response.status_code == 201

    assert ImportBatch.objects.count() == 3
    assert Transaction.objects.filter(account=account).count() == 4
    assert Transaction.objects.filter(account=second_account).count() == 2


@pytest.mark.parametrize("token", [None, "invalid-preview-token"])
def test_commit_requires_a_valid_preview_token(api_client, account, token):
    response = post_import(api_client, COMMIT_URL, account, csv_bytes(), token)

    assert response.status_code == 400
    assert ImportBatch.objects.count() == Transaction.objects.count() == 0


@pytest.mark.parametrize("change", ["file", "account", "user"])
def test_preview_token_is_bound_to_exact_bytes_account_and_user(
    api_client, user, other_user, account, change
):
    content = csv_bytes()
    token = preview_token(api_client, account, content)
    client = api_client
    target = account
    if change == "file":
        content += b"\r\n"
    elif change == "account":
        target = create_account(user)
    else:
        target = create_account(other_user)
        client = APIClient()
        client.force_authenticate(user=other_user)

    response = post_import(client, COMMIT_URL, target, content, token)

    assert response.status_code == 400
    assert ImportBatch.objects.count() == Transaction.objects.count() == 0


def test_preview_token_expires_after_fifteen_minutes(api_client, account, monkeypatch):
    content = csv_bytes()
    token = preview_token(api_client, account, content)
    later = time.time() + 901
    monkeypatch.setattr(signing.time, "time", lambda: later)

    response = post_import(api_client, COMMIT_URL, account, content, token)

    assert response.status_code == 400
    assert ImportBatch.objects.count() == Transaction.objects.count() == 0


def test_commit_rejects_a_signed_preview_from_an_unsupported_format_version(api_client, account):
    content = csv_bytes()
    token = preview_token(api_client, account, content)
    approval = signing.loads(token, salt=PREVIEW_SALT)
    assert approval["version"] == 1
    approval["version"] = 2
    future_token = signing.dumps(approval, salt=PREVIEW_SALT)

    response = post_import(api_client, COMMIT_URL, account, content, future_token)

    assert response.status_code == 400
    assert ImportBatch.objects.count() == Transaction.objects.count() == 0


def test_commit_revalidates_rows_even_with_a_matching_signed_approval(api_client, account):
    token = preview_token(api_client, account, csv_bytes())
    invalid_content = csv_bytes([VALID_ROW, ["2026-10-18", "Invalid amount", "0", "posted", ""]])
    approval = signing.loads(token, salt=PREVIEW_SALT)
    approval["sha256"] = hashlib.sha256(invalid_content).hexdigest()
    signed_approval = signing.dumps(approval, salt=PREVIEW_SALT)

    response = post_import(api_client, COMMIT_URL, account, invalid_content, signed_approval)

    assert response.status_code == 400
    assert response.data["detail"]
    assert ImportBatch.objects.count() == Transaction.objects.count() == 0


def test_archiving_account_after_preview_rejects_new_import_but_preserves_exact_retry(
    api_client, account
):
    saved_content = csv_bytes()
    saved_token = preview_token(api_client, account, saved_content)
    saved = post_import(api_client, COMMIT_URL, account, saved_content, saved_token)
    new_content = csv_bytes([["2026-10-18", "New purchase", "-9.00", "posted", ""]])
    new_token = preview_token(api_client, account, new_content)
    account.is_active = False
    account.save(update_fields=["is_active"])

    rejected = post_import(api_client, COMMIT_URL, account, new_content, new_token)
    retry = post_import(api_client, COMMIT_URL, account, saved_content, saved_token)

    assert saved.status_code == 201
    assert rejected.status_code == 400
    assert retry.status_code == 200
    assert retry.data["batch"]["id"] == saved.data["batch"]["id"]
    assert retry.data["duplicate"] is True
    assert ImportBatch.objects.count() == Transaction.objects.count() == 1


def test_failure_after_inserting_transactions_rolls_back_rows_and_receipt(
    api_client, account, monkeypatch
):
    content = csv_bytes([VALID_ROW, VALID_ROW])
    token = preview_token(api_client, account, content)
    original_bulk_create = TransactionQuerySet.bulk_create

    def insert_then_fail(queryset, objects, **kwargs):
        original_bulk_create(queryset, objects, **kwargs)
        assert Transaction.objects.count() == 2
        raise RuntimeError("Synthetic late storage failure")

    monkeypatch.setattr(TransactionQuerySet, "bulk_create", insert_then_fail)

    with pytest.raises(RuntimeError, match="Synthetic late storage failure"):
        post_import(api_client, COMMIT_URL, account, content, token)

    assert ImportBatch.objects.count() == 0
    assert Transaction.objects.count() == 0


def test_database_rejects_duplicate_receipt_for_the_same_account(api_client, account):
    content = csv_bytes()
    token = preview_token(api_client, account, content)
    response = post_import(api_client, COMMIT_URL, account, content, token)
    assert response.status_code == 201
    batch = ImportBatch.objects.get()

    with pytest.raises(IntegrityError), transaction.atomic():
        ImportBatch._base_manager.bulk_create(
            [
                ImportBatch(
                    owner=batch.owner,
                    account=account,
                    file_name="duplicate.csv",
                    file_hash=batch.file_hash,
                    row_count=batch.row_count,
                )
            ]
        )

    assert ImportBatch.objects.count() == 1


def test_import_history_is_private_and_read_only(api_client, account, other_user):
    content = csv_bytes()
    token = preview_token(api_client, account, content)
    created = post_import(api_client, COMMIT_URL, account, content, token)
    batch_id = created.data["batch"]["id"]
    detail_url = f"{HISTORY_URL}{batch_id}/"
    history = api_client.get(HISTORY_URL)

    assert history.status_code == 200
    assert history.data["count"] == 1
    assert history.data["results"] == [created.data["batch"]]
    assert api_client.get(detail_url).data == created.data["batch"]
    assert api_client.patch(detail_url, {"row_count": 100}, format="json").status_code == 405
    assert api_client.delete(detail_url).status_code == 405
    assert api_client.post(HISTORY_URL, {}, format="json").status_code == 405

    outsider = APIClient()
    outsider.force_authenticate(user=other_user)
    assert outsider.get(HISTORY_URL).data["count"] == 0
    assert outsider.get(detail_url).status_code == 404


def test_receipt_prevents_account_deletion_after_imported_transactions_are_deleted(
    api_client, account
):
    content = csv_bytes()
    token = preview_token(api_client, account, content)
    created = post_import(api_client, COMMIT_URL, account, content, token)
    assert created.status_code == 201
    imported = Transaction.objects.get()
    assert api_client.delete(reverse("transaction-detail", args=[imported.id])).status_code == 204

    response = api_client.delete(reverse("account-detail", args=[account.id]))

    assert response.status_code == 409
    assert FinancialAccount.objects.filter(pk=account.id).exists()
    assert ImportBatch.objects.count() == 1


def test_transaction_api_cannot_forge_or_remove_import_provenance(api_client, account):
    content = csv_bytes()
    token = preview_token(api_client, account, content)
    created = post_import(api_client, COMMIT_URL, account, content, token)
    batch_id = created.data["batch"]["id"]
    imported = Transaction.objects.get()

    edited = api_client.patch(
        reverse("transaction-detail", args=[imported.id]),
        {"description": "Reviewed purchase", "import_batch": None},
        format="json",
    )
    manual = api_client.post(
        reverse("transaction-list"),
        {
            "account": str(account.id),
            "transaction_date": "2026-10-18",
            "description": "Manual purchase",
            "amount": "-8.00",
            "import_batch": batch_id,
        },
        format="json",
    )

    assert edited.status_code == 200
    assert str(edited.data["import_batch"]) == batch_id
    imported.refresh_from_db()
    assert str(imported.import_batch_id) == batch_id
    assert manual.status_code == 201
    assert manual.data["import_batch"] is None
    assert Transaction.objects.get(pk=manual.data["id"]).import_batch_id is None


def test_transaction_model_rejects_another_users_import_batch(user, account, other_user):
    private_account = create_account(other_user)
    private_batch = ImportBatch.objects.create(
        owner=other_user,
        account=private_account,
        file_name="private-statement.csv",
        file_hash=hashlib.sha256(csv_bytes()).hexdigest(),
        row_count=1,
    )

    with pytest.raises(ValidationError, match="Import batch must belong"):
        Transaction.objects.create(
            owner=user,
            account=account,
            import_batch=private_batch,
            transaction_date="2026-10-17",
            description="Invalid provenance",
            amount=Decimal("-12.50"),
        )

    assert Transaction.objects.count() == 0
