import re
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from .models import Category, MonthlyBudget, Transaction

ZERO = Decimal("0.00")


def parse_month(value, *, require_trend=False):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
        raise ValidationError({"month": "Use a valid month in YYYY-MM format."})
    try:
        month = date(int(value[:4]), int(value[5:]), 1)
    except ValueError as error:
        raise ValidationError({"month": "Use a valid month in YYYY-MM format."}) from error
    if require_trend and month < date(1, 6, 1):
        raise ValidationError({"month": "Choose June 0001 or a later month."})
    return month


def normalize_currency(value):
    normalized = value.strip().upper() if isinstance(value, str) else ""
    if not re.fullmatch(r"[A-Z]{3}", normalized):
        raise ValidationError({"currency": "Use a three-letter currency code such as USD."})
    return normalized


def month_label(value):
    return f"{value.year:04d}-{value.month:02d}"


def month_before(value, distance):
    index = (value.year - 1) * 12 + value.month - 1 - distance
    return date(index // 12 + 1, index % 12 + 1, 1)


def money(value):
    return format(value if value else ZERO, ".2f")


def monthly_report(owner, month, currency):
    months = [month_before(month, offset) for offset in range(5, -1, -1)]
    entries = (
        Transaction.objects.filter(
            owner=owner,
            account__currency=currency,
            transaction_date__gte=months[0],
            transaction_date__lte=month.replace(day=monthrange(month.year, month.month)[1]),
        )
        .filter(Q(category__isnull=True) | ~Q(category__kind=Category.Kind.TRANSFER))
        .select_related("category")
    )
    trend = {value: {"income": ZERO, "spending": ZERO} for value in months}
    category_rows = {}
    counts = {"transaction_count": 0, "pending_count": 0}
    uncategorized = ZERO
    for entry in entries:
        entry_month = entry.transaction_date.replace(day=1)
        if entry_month not in trend:
            continue
        if entry.status == Transaction.Status.PENDING:
            if entry_month == month:
                counts["pending_count"] += 1
            continue
        if entry_month == month:
            counts["transaction_count"] += 1
        kind = entry.category.kind if entry.category_id else None
        income = entry.amount if kind == Category.Kind.INCOME else ZERO
        spending = -entry.amount if kind == Category.Kind.EXPENSE else ZERO
        if kind is None:
            income = max(entry.amount, ZERO)
            spending = -min(entry.amount, ZERO)
        trend[entry_month]["income"] += income
        trend[entry_month]["spending"] += spending
        if entry_month != month:
            continue
        if kind == Category.Kind.EXPENSE or (kind is None and entry.amount < 0):
            category_rows.setdefault(
                entry.category_id,
                {
                    "category": str(entry.category_id) if entry.category_id else None,
                    "category_name": entry.category.name if entry.category_id else "Uncategorized",
                    "spending": ZERO,
                    "budget": None,
                    "remaining": None,
                    "budget_id": None,
                },
            )["spending"] += spending
            if kind is None:
                uncategorized += spending
    for budget in MonthlyBudget.objects.filter(
        owner=owner, month=month, currency=currency
    ).select_related("category"):
        row = category_rows.setdefault(
            budget.category_id,
            {
                "category": str(budget.category_id),
                "category_name": budget.category.name,
                "spending": ZERO,
                "budget": None,
                "remaining": None,
                "budget_id": None,
            },
        )
        row["budget"] = budget.amount
        row["remaining"] = budget.amount - row["spending"]
        row["budget_id"] = str(budget.pk)
    ordered = sorted(
        category_rows.values(),
        key=lambda row: (-row["spending"], row["category_name"].casefold(), row["category"] or ""),
    )
    for row in ordered:
        for field in ("spending", "budget", "remaining"):
            if row[field] is not None:
                row[field] = money(row[field])
    income, spending = trend[month]["income"], trend[month]["spending"]
    return {
        "month": month_label(month),
        "currency": currency,
        **counts,
        "totals": {
            "income": money(income),
            "spending": money(spending),
            "net": money(income - spending),
            "uncategorized_spending": money(uncategorized),
        },
        "categories": ordered,
        "trend": [
            {"month": month_label(value), **{key: money(total) for key, total in totals.items()}}
            for value, totals in trend.items()
        ],
    }
