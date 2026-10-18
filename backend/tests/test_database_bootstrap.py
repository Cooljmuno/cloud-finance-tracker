from contextlib import nullcontext
from io import StringIO
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import override_settings

from apps.core.management.commands import bootstrap_database


@pytest.fixture
def bootstrap_context(monkeypatch):
    monkeypatch.setenv("ENABLE_DATABASE_BOOTSTRAP", "true")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")
    monkeypatch.setenv("APP_DATABASE_PASSWORD", "valid-password-for-tests-01234567890123456789")
    connection = MagicMock()
    connection.vendor = "postgresql"
    connection.settings_dict = {"USER": "finance_admin"}
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [None, ("finance",)]
    monkeypatch.setattr(bootstrap_database, "connection", connection)
    monkeypatch.setattr(bootstrap_database.transaction, "atomic", lambda: nullcontext())
    return connection, cursor


@pytest.mark.parametrize("flag", [None, "false", "TRUE", "1"])
def test_bootstrap_disabled_by_default(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("ENABLE_DATABASE_BOOTSTRAP", raising=False)
    else:
        monkeypatch.setenv("ENABLE_DATABASE_BOOTSTRAP", flag)
    with pytest.raises(CommandError, match="disabled"):
        call_command("bootstrap_database")


def test_bootstrap_rejects_local_settings(monkeypatch, bootstrap_context):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.local")
    with pytest.raises(CommandError, match="disabled"):
        call_command("bootstrap_database")
    bootstrap_context[0].cursor.assert_not_called()


@override_settings(DEBUG=True)
def test_bootstrap_rejects_debug_logging(bootstrap_context):
    with pytest.raises(CommandError, match="disabled"):
        call_command("bootstrap_database")
    bootstrap_context[0].cursor.assert_not_called()


@pytest.mark.parametrize("password", ["", "short"])
def test_bootstrap_rejects_invalid_password(monkeypatch, bootstrap_context, password):
    monkeypatch.setenv("APP_DATABASE_PASSWORD", password)
    with pytest.raises(CommandError, match="APP_DATABASE_PASSWORD"):
        call_command("bootstrap_database")
    bootstrap_context[0].cursor.assert_not_called()


def test_bootstrap_requires_postgres_and_administrator(bootstrap_context):
    connection, _ = bootstrap_context
    connection.vendor = "sqlite"
    with pytest.raises(CommandError, match="PostgreSQL"):
        call_command("bootstrap_database")
    connection.vendor = "postgresql"
    connection.settings_dict["USER"] = "finance_app"
    with pytest.raises(CommandError, match="administrator"):
        call_command("bootstrap_database")
    connection.cursor.assert_not_called()


def test_bootstrap_creates_only_restricted_role_and_schema_grants(bootstrap_context):
    _, cursor = bootstrap_context
    output = StringIO()
    call_command("bootstrap_database", stdout=output)
    queries = [
        args[0].as_string() if hasattr(args[0], "as_string") else args[0]
        for args, _ in cursor.execute.call_args_list
    ]
    create = next(query for query in queries if query.startswith("CREATE ROLE"))
    for attribute in (
        '"finance_app"',
        "LOGIN",
        "NOSUPERUSER",
        "NOCREATEDB",
        "NOCREATEROLE",
        "NOREPLICATION",
        "NOBYPASSRLS",
        "NOINHERIT",
    ):
        assert attribute in create
    assert 'GRANT CONNECT ON DATABASE "finance" TO "finance_app"' in queries
    assert 'GRANT USAGE, CREATE ON SCHEMA public TO "finance_app"' in queries
    assert not any("DROP " in query or "GRANT ALL" in query for query in queries)
    assert "password-for-tests" not in output.getvalue()
    assert "ready" in output.getvalue()


def test_bootstrap_updates_existing_role_without_recreation(bootstrap_context):
    _, cursor = bootstrap_context
    cursor.fetchone.side_effect = [(False, False, False, False, False), None, ("finance",)]
    call_command("bootstrap_database", stdout=StringIO())
    queries = [
        args[0].as_string() if hasattr(args[0], "as_string") else args[0]
        for args, _ in cursor.execute.call_args_list
    ]
    assert any(
        query.startswith('ALTER ROLE "finance_app" WITH LOGIN NOINHERIT PASSWORD')
        for query in queries
    )
    assert not any(query.startswith("CREATE ROLE") or "NOSUPERUSER" in query for query in queries)


@pytest.mark.parametrize(
    "existing",
    [
        (True, False, False, False, False),
        (False, True, False, False, False),
        (False, False, True, False, False),
        (False, False, False, True, False),
        (False, False, False, False, True),
    ],
)
def test_bootstrap_refuses_existing_privileged_role(bootstrap_context, existing):
    _, cursor = bootstrap_context
    cursor.fetchone.side_effect = [existing]
    with pytest.raises(CommandError, match="unexpected privileges"):
        call_command("bootstrap_database")
    assert len(cursor.execute.call_args_list) == 2


def test_bootstrap_refuses_existing_role_memberships(bootstrap_context):
    _, cursor = bootstrap_context
    cursor.fetchone.side_effect = [(False, False, False, False, False), (1,)]
    with pytest.raises(CommandError, match="unexpected memberships"):
        call_command("bootstrap_database")
    assert len(cursor.execute.call_args_list) == 3


def test_bootstrap_quotes_password_as_sql_literal(monkeypatch, bootstrap_context):
    _, cursor = bootstrap_context
    password = "a-long-password-01234567890123456789'; DROP ROLE postgres; --"
    monkeypatch.setenv("APP_DATABASE_PASSWORD", password)
    call_command("bootstrap_database", stdout=StringIO())
    create = cursor.execute.call_args_list[2].args[0].as_string()
    assert "PASSWORD 'a-long-password-01234567890123456789''; DROP ROLE postgres; --'" in create


def test_bootstrap_does_not_expose_database_error_details(bootstrap_context):
    _, cursor = bootstrap_context
    cursor.execute.side_effect = DatabaseError("database error contains a confidential password")
    with pytest.raises(CommandError, match="administrator permissions") as error:
        call_command("bootstrap_database")
    assert "confidential" not in str(error.value)
