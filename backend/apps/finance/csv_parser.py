import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from rest_framework.exceptions import ValidationError

MAX_FILE_BYTES = 256 * 1024
MAX_DATA_ROWS = 500
HEADER = ["transaction_date", "description", "amount", "status", "notes"]

csv.field_size_limit(MAX_FILE_BYTES)

DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
AMOUNT_PATTERN = re.compile(r"-?[0-9]{1,12}(?:\.[0-9]{1,2})?")


@dataclass
class ParsedCsv:
    row_count: int
    rows: list[dict]
    errors: list[dict]


def parse_csv(data: bytes) -> ParsedCsv:
    if len(data) > MAX_FILE_BYTES:
        raise ValidationError({"detail": "CSV file must be 256 KiB or smaller."})

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError({"detail": "CSV file must use UTF-8 encoding."}) from None

    if "\x00" in text:
        raise ValidationError({"detail": "CSV file must not contain null characters."})

    result = ParsedCsv(row_count=0, rows=[], errors=[])
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)

    try:
        header = next(reader, None)
        if header is None:
            raise ValidationError({"detail": "CSV file is empty."})
        if header != HEADER:
            raise ValidationError({"detail": f"CSV header must be: {','.join(HEADER)}."})

        for row_number, fields in enumerate(reader, start=2):
            if all(not field.strip() for field in fields):
                continue

            result.row_count += 1
            if result.row_count > MAX_DATA_ROWS:
                raise ValidationError(
                    {"detail": "CSV file may contain at most 500 nonblank data rows."}
                )
            if len(fields) != len(HEADER):
                raise ValidationError(
                    {"detail": f"CSV row {row_number} must contain exactly 5 fields."}
                )

            date_text, description, amount_text, status, notes = (field.strip() for field in fields)
            row_errors = []
            transaction_date = None
            amount = None

            try:
                if not DATE_PATTERN.fullmatch(date_text):
                    raise ValueError
                transaction_date = date.fromisoformat(date_text)
            except ValueError:
                row_errors.append(
                    {
                        "row": row_number,
                        "field": "transaction_date",
                        "message": "Use a valid date in YYYY-MM-DD format.",
                    }
                )

            description = " ".join(description.split())
            if not description or len(description) > 255:
                row_errors.append(
                    {
                        "row": row_number,
                        "field": "description",
                        "message": "Description must contain between 1 and 255 characters.",
                    }
                )

            if not AMOUNT_PATTERN.fullmatch(amount_text):
                row_errors.append(
                    {
                        "row": row_number,
                        "field": "amount",
                        "message": "Use an amount with at most 12 whole and 2 decimal digits.",
                    }
                )
            else:
                amount = Decimal(amount_text).quantize(Decimal("0.01"))
                if amount == 0:
                    row_errors.append(
                        {
                            "row": row_number,
                            "field": "amount",
                            "message": "Amount must be nonzero.",
                        }
                    )

            status = status or "posted"
            if status not in {"pending", "posted"}:
                row_errors.append(
                    {
                        "row": row_number,
                        "field": "status",
                        "message": "Status must be pending or posted.",
                    }
                )

            if len(notes) > 1000:
                row_errors.append(
                    {
                        "row": row_number,
                        "field": "notes",
                        "message": "Notes must contain at most 1000 characters.",
                    }
                )

            result.errors.extend(row_errors)
            if not row_errors:
                result.rows.append(
                    {
                        "row": row_number,
                        "transaction_date": transaction_date,
                        "description": description,
                        "amount": amount,
                        "status": status,
                        "notes": notes,
                    }
                )
    except csv.Error:
        raise ValidationError({"detail": "CSV file contains malformed CSV records."}) from None

    return result
