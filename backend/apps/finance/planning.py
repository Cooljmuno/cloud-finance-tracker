from django.db import transaction

from .models import CategorizationRule, Transaction


def active_rules(owner):
    return list(
        CategorizationRule.objects.select_related("category").filter(
            owner=owner, is_active=True, category__is_active=True
        )
    )


def assign_category(entry, rules=None):
    candidates = active_rules(entry.owner) if rules is None else rules
    description = " ".join(entry.description.split()).casefold()
    entry.category = None
    entry.matched_rule = None
    entry.category_source = Transaction.CategorySource.UNCATEGORIZED
    for rule in candidates:
        if rule.match_text.casefold() in description:
            entry.category = rule.category
            entry.matched_rule = rule
            entry.category_source = Transaction.CategorySource.RULE
            break
    return entry


def apply_rules(owner):
    with transaction.atomic():
        entries = list(
            Transaction.objects.select_for_update()
            .filter(
                owner=owner,
                category_source=Transaction.CategorySource.UNCATEGORIZED,
                category__isnull=True,
            )
            .order_by("id")
        )
        rules = active_rules(owner)
        updated = 0
        for entry in entries:
            assign_category(entry, rules)
            if entry.matched_rule_id:
                entry.save(
                    update_fields=["category", "category_source", "matched_rule", "updated_at"]
                )
                updated += 1
        return {"updated": updated, "examined": len(entries)}
