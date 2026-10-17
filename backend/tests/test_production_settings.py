import subprocess
import sys
from pathlib import Path
from textwrap import dedent, indent


def run_production(code: str, *, missing: tuple[str, ...] = ()):
    environment = {
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "production-boundary-test-only-secret-key-never-used-for-deployment",
        "DJANGO_ALLOWED_HOSTS": "testserver",
        "COGNITO_REGION": "us-east-1",
        "COGNITO_USER_POOL_ID": "us-east-1_boundary",
        "COGNITO_APP_CLIENT_ID": "boundary-test-client",
        "POSTGRES_DB": "boundary_test",
        "POSTGRES_USER": "boundary_test",
        "POSTGRES_PASSWORD": "boundary-test-only-password",
        "POSTGRES_HOST": "database.invalid",
        "POSTGRES_SSLROOTCERT": "/unused/boundary-test-ca.pem",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for name in missing:
        environment.pop(name)

    script = dedent(
        """
        import django
        from unittest.mock import patch

        with (
            patch(
                "django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection",
                side_effect=AssertionError("Unexpected database connection"),
            ),
            patch("socket.socket.connect", side_effect=AssertionError("Unexpected network call")),
        ):
            django.setup()
        """
    )
    script += indent(dedent(code), "    ")
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_production_requires_cognito_configuration():
    result = run_production("", missing=("COGNITO_APP_CLIENT_ID",))

    assert result.returncode != 0
    assert "Missing required environment variable: COGNITO_APP_CLIENT_ID" in result.stderr


def test_production_disables_local_routes_and_demo_seed():
    result = run_production(
        """
        from io import StringIO

        from django.core.management import CommandError, call_command
        from django.urls import Resolver404, resolve

        for path in (
            "/admin/",
            "/api/v1/auth/csrf/",
            "/api/v1/auth/login/",
            "/api/v1/auth/logout/",
        ):
            try:
                resolve(path)
            except Resolver404:
                pass
            else:
                raise AssertionError(f"Local route is available in production: {path}")

        try:
            call_command("seed_demo_data", stdout=StringIO())
        except CommandError as error:
            assert str(error) == "Demo data is disabled in this environment."
        else:
            raise AssertionError("Demo seed was accepted in production")
        """
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_production_current_user_requires_bearer_authentication():
    result = run_production(
        """
        from rest_framework.test import APIClient

        response = APIClient().get("/api/v1/auth/me/", secure=True)

        assert response.status_code == 401, response.content
        assert response["WWW-Authenticate"] == "Bearer"
        """
    )

    assert result.returncode == 0, result.stdout + result.stderr
