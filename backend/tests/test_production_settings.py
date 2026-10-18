import subprocess
import sys
from pathlib import Path
from textwrap import dedent, indent

import pytest


def run_production(
    code: str, *, missing: tuple[str, ...] = (), overrides: dict[str, str] | None = None
):
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
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    environment.update(overrides or {})
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


@pytest.mark.parametrize(
    "secret",
    ["unsafe-default-key", "a" * 60, "django-insecure-" + "unique-secret-" * 5],
)
def test_production_rejects_weak_signing_secrets(secret):
    result = run_production("", overrides={"DJANGO_SECRET_KEY": secret})

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY must be a strong, unique production secret" in result.stderr


@pytest.mark.parametrize("hosts", ["", "*", "testserver,*", ".example.com"])
def test_production_requires_explicit_hosts(hosts):
    result = run_production("", overrides={"DJANGO_ALLOWED_HOSTS": hosts})

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS must contain explicit, non-wildcard hosts" in result.stderr


def test_production_uses_bundled_rds_ca_and_hostname_verification():
    result = run_production(
        """
        import ssl
        from pathlib import Path

        from django.conf import settings

        options = settings.DATABASES["default"]["OPTIONS"]
        assert options["sslmode"] == "verify-full"
        assert options["connect_timeout"] == 5
        assert Path(options["sslrootcert"]).name == "global-bundle.pem"
        context = ssl.create_default_context(cafile=options["sslrootcert"])
        assert context.cert_store_stats()["x509_ca"] > 0
        """
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_production_rejects_missing_database_ca_bundle():
    result = run_production("", overrides={"POSTGRES_SSLROOTCERT": "/missing/rds-ca.pem"})

    assert result.returncode != 0
    assert "POSTGRES_SSLROOTCERT must reference a readable RDS CA bundle" in result.stderr


def test_production_trusts_only_cloudfront_viewer_protocol():
    result = run_production(
        """
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.get("/api/v1/auth/me/", HTTP_X_FORWARDED_PROTO="https")
        assert response.status_code == 301, response.content
        assert response["Location"] == "https://testserver/api/v1/auth/me/"

        response = client.get(
            "/api/v1/auth/me/",
            HTTP_CLOUDFRONT_FORWARDED_PROTO="https",
            HTTP_X_FORWARDED_PROTO="http",
        )
        assert response.status_code == 401, response.content
        assert response["WWW-Authenticate"] == "Bearer"
        assert response["Strict-Transport-Security"].startswith("max-age=31536000")

        response = client.get(
            "/api/v1/auth/me/",
            HTTP_CLOUDFRONT_FORWARDED_PROTO="https",
            HTTP_HOST="attacker.invalid",
        )
        assert response.status_code == 400, response.content
        """
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_production_load_balancer_readiness_keeps_private_hosts_scoped_to_health():
    result = run_production(
        """
        from unittest.mock import MagicMock, patch

        from django.db.utils import DatabaseError
        from rest_framework.test import APIClient

        client = APIClient()
        cursor = MagicMock()
        cursor.__enter__.return_value.fetchone.return_value = (1,)
        with patch("apps.core.views.connection.cursor", return_value=cursor):
            response = client.get("/api/v1/health/", HTTP_HOST="10.0.1.23:8000")
            assert response.status_code == 200, response.content
            assert response.json()["database"] == "ok"
            assert "Location" not in response

            response = client.head("/api/v1/health/", HTTP_HOST="10.0.1.23:8000")
            assert response.status_code == 200, response.content
            assert response.content == b""

            response = client.get("/api/v1/health/", HTTP_HOST="127.0.0.1:8000")
            assert response.status_code == 200, response.content

        with patch(
            "apps.core.views.connection.cursor", side_effect=DatabaseError("private detail")
        ):
            response = client.get("/api/v1/health/", HTTP_HOST="10.0.1.23:8000")
            assert response.status_code == 503, response.content
            assert response.json()["database"] == "unavailable"
            assert b"private detail" not in response.content

        for path in ("/api/v1/auth/me/", "/api/v1/health/extra/", "/api/v1/health"):
            response = client.get(
                path,
                HTTP_HOST="10.0.1.23:8000",
                HTTP_CLOUDFRONT_FORWARDED_PROTO="https",
            )
            assert response.status_code == 400, (path, response.status_code)

        for host in ("attacker.invalid", "8.8.8.8:8000", "0.0.0.0:8000"):
            response = client.get("/api/v1/health/", HTTP_HOST=host)
            assert response.status_code == 400, (host, response.status_code)
        """
    )

    assert result.returncode == 0, result.stdout + result.stderr
