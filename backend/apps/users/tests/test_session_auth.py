import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="session-user",
        email="session@example.com",
        password="A-strong-session-password-2026!",
    )


@pytest.fixture
def csrf_client():
    return APIClient(enforce_csrf_checks=True)


def csrf_token(client: APIClient) -> str:
    response = client.get(reverse("csrf-token"))
    assert response.status_code == status.HTTP_200_OK
    assert response.data if hasattr(response, "data") else response.json()
    return client.cookies["csrftoken"].value


def test_csrf_bootstrap_sets_cookie(csrf_client):
    response = csrf_client.get(reverse("csrf-token"))

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["csrfToken"]
    assert csrf_client.cookies["csrftoken"].value


def test_login_requires_csrf(csrf_client, user):
    response = csrf_client.post(
        reverse("session-login"),
        {"username": user.username, "password": "A-strong-session-password-2026!"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_invalid_login_is_generic(csrf_client, user):
    token = csrf_token(csrf_client)
    response = csrf_client.post(
        reverse("session-login"),
        {"username": user.username, "password": "incorrect"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Invalid username or password."}


def test_session_authenticates_finance_api_and_enforces_current_csrf(csrf_client, user):
    initial_token = csrf_token(csrf_client)
    login_response = csrf_client.post(
        reverse("session-login"),
        {"username": user.username, "password": "A-strong-session-password-2026!"},
        format="json",
        HTTP_X_CSRFTOKEN=initial_token,
    )

    assert login_response.status_code == status.HTTP_200_OK
    assert login_response.json() == {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
    }
    assert csrf_client.cookies["sessionid"]["httponly"] is True

    me_response = csrf_client.get(reverse("current-user"))
    list_response = csrf_client.get(reverse("account-list"))
    missing_csrf_response = csrf_client.post(
        reverse("account-list"),
        {"name": "Checking", "account_type": "checking"},
        format="json",
    )

    assert me_response.status_code == status.HTTP_200_OK
    assert list_response.status_code == status.HTTP_200_OK
    assert missing_csrf_response.status_code == status.HTTP_403_FORBIDDEN

    current_token = csrf_client.cookies["csrftoken"].value
    create_response = csrf_client.post(
        reverse("account-list"),
        {"name": "Checking", "account_type": "checking"},
        format="json",
        HTTP_X_CSRFTOKEN=current_token,
    )

    assert create_response.status_code == status.HTTP_201_CREATED


def test_logout_requires_csrf_and_invalidates_session(csrf_client, user):
    token = csrf_token(csrf_client)
    csrf_client.post(
        reverse("session-login"),
        {"username": user.username, "password": "A-strong-session-password-2026!"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )

    missing_csrf_response = csrf_client.post(reverse("session-logout"), format="json")
    assert missing_csrf_response.status_code == status.HTTP_403_FORBIDDEN
    assert csrf_client.get(reverse("current-user")).status_code == status.HTTP_200_OK

    current_token = csrf_client.cookies["csrftoken"].value
    logout_response = csrf_client.post(
        reverse("session-logout"),
        format="json",
        HTTP_X_CSRFTOKEN=current_token,
    )

    assert logout_response.status_code == status.HTTP_204_NO_CONTENT
    assert csrf_client.get(reverse("current-user")).status_code == status.HTTP_401_UNAUTHORIZED


def test_local_cors_allows_configured_origin_with_credentials(csrf_client):
    response = csrf_client.get(reverse("csrf-token"), HTTP_ORIGIN="http://localhost:5173")

    assert response["access-control-allow-origin"] == "http://localhost:5173"
    assert response["access-control-allow-credentials"] == "true"


def test_local_cors_does_not_reflect_untrusted_origin(csrf_client):
    response = csrf_client.get(reverse("csrf-token"), HTTP_ORIGIN="https://attacker.invalid")

    assert "access-control-allow-origin" not in response
