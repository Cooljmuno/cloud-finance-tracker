from datetime import date
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.finance.management.commands.seed_demo_data import DEMO_USERNAME, fixture_id
from apps.finance.models import Category, FinancialAccount, Transaction

pytestmark = pytest.mark.django_db

DEMO_PASSWORD = "Portfolio-fixture-password-2026!"


def seed(monkeypatch, *args):
    monkeypatch.setenv("DEMO_USER_PASSWORD", DEMO_PASSWORD)
    output = StringIO()
    call_command("seed_demo_data", *args, stdout=output)
    return output.getvalue()


def test_seed_creates_complete_synthetic_dataset_without_printing_password(monkeypatch):
    output = seed(monkeypatch, "--as-of", "2026-08-31")
    user = get_user_model().objects.get(username=DEMO_USERNAME)

    assert user.check_password(DEMO_PASSWORD)
    assert FinancialAccount.objects.filter(owner=user).count() == 3
    assert Category.objects.filter(owner=user).count() == 10
    assert Transaction.objects.filter(owner=user).count() == 24
    assert Transaction.objects.filter(owner=user, amount__gt=0).exists()
    assert Transaction.objects.filter(owner=user, amount__lt=0).exists()
    assert Transaction.objects.filter(owner=user, status="pending").exists()
    assert Transaction.objects.filter(owner=user, category=None).exists()
    assert DEMO_PASSWORD not in output
    assert "synthetic portfolio data" in output.lower()


def test_seed_is_idempotent_and_moves_dates_without_duplicate_rows(monkeypatch):
    seed(monkeypatch, "--as-of", "2026-08-31")
    original_ids = set(Transaction.objects.values_list("id", flat=True))
    paycheck_id = fixture_id("transaction", "paycheck-1")
    original_date = Transaction.objects.get(pk=paycheck_id).transaction_date

    seed(monkeypatch, "--as-of", "2026-09-01")

    assert set(Transaction.objects.values_list("id", flat=True)) == original_ids
    assert Transaction.objects.count() == 24
    assert Transaction.objects.get(pk=paycheck_id).transaction_date == date(2026, 8, 29)
    assert original_date == date(2026, 8, 28)


def test_reset_is_scoped_to_demo_user(monkeypatch):
    seed(monkeypatch, "--as-of", "2026-08-31")
    other_user = get_user_model().objects.create_user(username="other")
    other_account = FinancialAccount.objects.create(
        owner=other_user,
        name="Other checking",
        account_type="checking",
    )
    demo_user = get_user_model().objects.get(username=DEMO_USERNAME)
    FinancialAccount.objects.create(
        owner=demo_user,
        name="Temporary demo account",
        account_type="cash",
    )

    seed(monkeypatch, "--as-of", "2026-08-31", "--reset")

    assert FinancialAccount.objects.filter(owner=demo_user).count() == 3
    assert FinancialAccount.objects.filter(pk=other_account.pk).exists()


def test_invalid_reference_date_is_rejected(monkeypatch):
    monkeypatch.setenv("DEMO_USER_PASSWORD", DEMO_PASSWORD)

    with pytest.raises(CommandError, match="YYYY-MM-DD"):
        call_command("seed_demo_data", "--as-of", "08/31/2026")


def test_seed_does_not_take_over_an_existing_reserved_username(monkeypatch):
    existing_user = get_user_model().objects.create_user(
        username=DEMO_USERNAME,
        email="existing@example.com",
        password="Existing-account-password-2026!",
    )
    monkeypatch.setenv("DEMO_USER_PASSWORD", DEMO_PASSWORD)

    with pytest.raises(CommandError, match="reserved username"):
        call_command("seed_demo_data")

    existing_user.refresh_from_db()
    assert existing_user.email == "existing@example.com"
    assert existing_user.check_password("Existing-account-password-2026!")
    assert not FinancialAccount.objects.filter(owner=existing_user).exists()


@override_settings(ENABLE_DEMO_DATA=False)
def test_seed_is_blocked_when_demo_data_is_disabled(monkeypatch):
    monkeypatch.setenv("DEMO_USER_PASSWORD", DEMO_PASSWORD)

    with pytest.raises(CommandError, match="disabled"):
        call_command("seed_demo_data")
