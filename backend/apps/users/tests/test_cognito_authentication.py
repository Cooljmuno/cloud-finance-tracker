from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.test import override_settings
from jwt.exceptions import PyJWKClientError
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from apps.users.authentication import CognitoJWTAuthentication

pytestmark = pytest.mark.django_db

ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example"
CLIENT_ID = "portfolio-client-id"


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65_537, key_size=2048)


def claims(**overrides):
    now = datetime.now(UTC)
    values = {
        "sub": "opaque-cognito-subject",
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "iat": now,
        "exp": now + timedelta(minutes=10),
        "email": "verified@example.com",
        "email_verified": True,
    }
    values.update(overrides)
    return values


def encode_token(private_key, token_claims=None, algorithm="RS256"):
    return jwt.encode(
        token_claims or claims(),
        private_key,
        algorithm=algorithm,
        headers={"kid": "test-key"},
    )


def request_with_token(token: str):
    return APIRequestFactory().get("/api/v1/auth/me/", HTTP_AUTHORIZATION=f"Bearer {token}")


def jwks_mock(public_key):
    client = Mock()
    client.get_signing_key_from_jwt.return_value = SimpleNamespace(key=public_key)
    return patch("apps.users.authentication.get_jwks_client", return_value=client)


@override_settings(COGNITO_ISSUER=ISSUER, COGNITO_APP_CLIENT_ID=CLIENT_ID)
def test_valid_access_token_creates_passwordless_user(private_key):
    token = encode_token(private_key)

    with jwks_mock(private_key.public_key()):
        user, returned_claims = CognitoJWTAuthentication().authenticate(request_with_token(token))

    assert user.cognito_sub == "opaque-cognito-subject"
    assert user.email == "verified@example.com"
    assert not user.has_usable_password()
    assert returned_claims["token_use"] == "access"


@override_settings(COGNITO_ISSUER=ISSUER, COGNITO_APP_CLIENT_ID=CLIENT_ID)
def test_repeat_token_reuses_subject_and_never_links_by_email(private_key):
    local_user = get_user_model().objects.create_user(
        username="local-user",
        email="verified@example.com",
        password="local-only-password",
    )
    token = encode_token(private_key)

    with jwks_mock(private_key.public_key()):
        first_user, _ = CognitoJWTAuthentication().authenticate(request_with_token(token))
        second_user, _ = CognitoJWTAuthentication().authenticate(request_with_token(token))

    assert first_user == second_user
    assert first_user != local_user
    assert get_user_model().objects.filter(cognito_sub="opaque-cognito-subject").count() == 1


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"iss": "https://issuer.invalid"},
        {"client_id": "wrong-client"},
        {"token_use": "id"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"sub": ""},
        {"sub": "x" * 256},
    ],
)
@override_settings(COGNITO_ISSUER=ISSUER, COGNITO_APP_CLIENT_ID=CLIENT_ID)
def test_invalid_claims_are_rejected(private_key, claim_overrides):
    token = encode_token(private_key, claims(**claim_overrides))

    with jwks_mock(private_key.public_key()), pytest.raises(AuthenticationFailed):
        CognitoJWTAuthentication().authenticate(request_with_token(token))


@override_settings(COGNITO_ISSUER=ISSUER, COGNITO_APP_CLIENT_ID=CLIENT_ID)
def test_missing_required_claim_is_rejected(private_key):
    token_claims = claims()
    del token_claims["client_id"]
    token = encode_token(private_key, token_claims)

    with jwks_mock(private_key.public_key()), pytest.raises(AuthenticationFailed):
        CognitoJWTAuthentication().authenticate(request_with_token(token))


@override_settings(COGNITO_ISSUER=ISSUER, COGNITO_APP_CLIENT_ID=CLIENT_ID)
def test_bad_signature_is_rejected(private_key):
    attacker_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    token = encode_token(attacker_key)

    with jwks_mock(private_key.public_key()), pytest.raises(AuthenticationFailed):
        CognitoJWTAuthentication().authenticate(request_with_token(token))


@override_settings(COGNITO_ISSUER=ISSUER, COGNITO_APP_CLIENT_ID=CLIENT_ID)
def test_jwks_failure_is_rejected_without_leaking_details(private_key):
    token = encode_token(private_key)
    client = Mock()
    client.get_signing_key_from_jwt.side_effect = PyJWKClientError("private network detail")

    with (
        patch("apps.users.authentication.get_jwks_client", return_value=client),
        pytest.raises(AuthenticationFailed, match="Invalid bearer token"),
    ):
        CognitoJWTAuthentication().authenticate(request_with_token(token))


def test_non_bearer_header_is_ignored():
    request = APIRequestFactory().get(
        "/api/v1/auth/me/",
        HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz",
    )

    assert CognitoJWTAuthentication().authenticate(request) is None


def test_malformed_bearer_header_is_rejected():
    request = APIRequestFactory().get(
        "/api/v1/auth/me/",
        HTTP_AUTHORIZATION="Bearer token extra",
    )

    with pytest.raises(AuthenticationFailed, match="Invalid bearer token"):
        CognitoJWTAuthentication().authenticate(request)


@override_settings(COGNITO_ISSUER=ISSUER, COGNITO_APP_CLIENT_ID=CLIENT_ID)
def test_inactive_local_subject_is_rejected(private_key):
    get_user_model().objects.create(
        username="disabled-cognito-user",
        cognito_sub="opaque-cognito-subject",
        is_active=False,
    )
    token = encode_token(private_key)

    with jwks_mock(private_key.public_key()), pytest.raises(AuthenticationFailed):
        CognitoJWTAuthentication().authenticate(request_with_token(token))
