import hashlib
import re

from django.core import signing
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from .csv_parser import MAX_DATA_ROWS as MAX_DATA_ROWS
from .csv_parser import MAX_FILE_BYTES, parse_csv
from .models import FinancialAccount, ImportBatch, Transaction
from .planning import active_rules, assign_category
from .serializers import ImportBatchSerializer

PREVIEW_SALT = "finance.csv.preview.v1"
PREVIEW_MAX_AGE = 900
PREVIEW_ROW_LIMIT = 20
PREVIEW_ERROR_LIMIT = 50


def read_upload(upload) -> tuple[bytes, str, str]:
    try:
        data = upload.read(MAX_FILE_BYTES + 1)
    except (OSError, ValueError) as error:
        raise ValidationError({"detail": "Unable to read the CSV file."}) from error
    if len(data) > MAX_FILE_BYTES:
        raise ValidationError({"detail": "CSV files must be 256 KiB or smaller."})

    file_name = str(getattr(upload, "name", "") or "transactions.csv")
    file_name = file_name.replace("\\", "/").rsplit("/", 1)[-1]
    file_name = re.sub(r"[\x00-\x1f\x7f]", "", file_name).strip()[:255]
    if file_name in {"", ".", ".."}:
        file_name = "transactions.csv"
    return data, file_name, hashlib.sha256(data).hexdigest()


def parse_upload(data: bytes):
    parsed = parse_csv(data)
    if parsed.row_count == 0:
        raise ValidationError({"detail": "The CSV must contain at least one transaction row."})
    return parsed


def preview_import(owner, account, upload) -> dict:
    data, file_name, file_hash = read_upload(upload)
    parsed = parse_upload(data)
    existing = (
        ImportBatch.objects.select_related("account")
        .filter(
            owner=owner,
            account=account,
            file_hash=file_hash,
        )
        .first()
    )
    preview_token = None
    if not parsed.errors:
        preview_token = signing.dumps(
            {
                "version": 1,
                "owner": str(owner.pk),
                "account": str(account.pk),
                "sha256": file_hash,
            },
            salt=PREVIEW_SALT,
        )

    return {
        "account": str(account.pk),
        "file_name": file_name,
        "row_count": parsed.row_count,
        "valid_count": len(parsed.rows),
        "error_count": len(parsed.errors),
        "errors": parsed.errors[:PREVIEW_ERROR_LIMIT],
        "errors_truncated": len(parsed.errors) > PREVIEW_ERROR_LIMIT,
        "rows": [
            {
                **row,
                "transaction_date": row["transaction_date"].isoformat(),
                "amount": format(row["amount"], ".2f"),
            }
            for row in parsed.rows[:PREVIEW_ROW_LIMIT]
        ],
        "preview_truncated": len(parsed.rows) > PREVIEW_ROW_LIMIT,
        "preview_token": preview_token,
        "already_imported": ImportBatchSerializer(existing).data if existing else None,
        "can_commit": not parsed.errors and existing is None and account.is_active,
    }


def commit_import(owner, account, upload, preview_token: str) -> tuple[ImportBatch, bool]:
    data, file_name, file_hash = read_upload(upload)
    try:
        approved = signing.loads(preview_token, salt=PREVIEW_SALT, max_age=PREVIEW_MAX_AGE)
    except signing.BadSignature as error:
        raise ValidationError(
            {"detail": "The preview has expired or is invalid. Preview the file again."}
        ) from error
    if approved != {
        "version": 1,
        "owner": str(owner.pk),
        "account": str(account.pk),
        "sha256": file_hash,
    }:
        raise ValidationError(
            {"detail": "The file or account differs from the preview. Preview the file again."}
        )

    parsed = parse_upload(data)
    if parsed.errors:
        raise ValidationError(
            {"detail": "The CSV contains invalid rows. Correct every error and preview it again."}
        )

    try:
        with transaction.atomic():
            locked_account = (
                FinancialAccount.objects.select_for_update()
                .filter(
                    pk=account.pk,
                    owner=owner,
                )
                .first()
            )
            if locked_account is None:
                raise ValidationError({"account": "Choose one of your financial accounts."})
            existing = (
                ImportBatch.objects.select_related("account")
                .filter(
                    owner=owner,
                    account=locked_account,
                    file_hash=file_hash,
                )
                .first()
            )
            if existing:
                return existing, True
            if not locked_account.is_active:
                raise ValidationError({"account": "Restore this account before importing a file."})

            batch = ImportBatch.objects.create(
                owner=owner,
                account=locked_account,
                file_name=file_name,
                file_hash=file_hash,
                row_count=parsed.row_count,
            )
            rules = active_rules(owner)
            Transaction.objects.bulk_create(
                [
                    assign_category(
                        Transaction(
                            owner=owner,
                            account=locked_account,
                            import_batch=batch,
                            **{field: value for field, value in row.items() if field != "row"},
                        ),
                        rules,
                    )
                    for row in parsed.rows
                ]
            )
            return batch, False
    except IntegrityError:
        existing = (
            ImportBatch.objects.select_related("account")
            .filter(
                owner=owner,
                account_id=account.pk,
                file_hash=file_hash,
            )
            .first()
        )
        if existing:
            return existing, True
        raise
