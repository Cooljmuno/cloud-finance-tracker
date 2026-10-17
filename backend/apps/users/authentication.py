import hashlib
import hmac
from functools import lru_cache

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request


class SessionAuthenticationWith401(SessionAuthentication):
    """Session authentication that identifies anonymous API responses as 401."""

    def authenticate_header(self, request: Request) -> str:
        return "Session"


@lru_cache(maxsize=8)
def get_jwks_client(jwks_url: str, cache_seconds: int) -> PyJWKClient:
    return PyJWKClient(
        jwks_url,
        cache_jwk_set=True,
        lifespan=cache_seconds,
        timeout=5,
    )


class CognitoJWTAuthentication(BaseAuthentication):
    """Validate Cognito access tokens and provision their local user records."""

    keyword = b"bearer"

    def authenticate(self, request: Request):
        raw_header = request.META.get("HTTP_AUTHORIZATION", "").encode("utf-8")
        if not raw_header:
            return None

        parts = raw_header.split()
        if not parts:
            return None
        if parts[0].lower() != self.keyword:
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid bearer token.")

        try:
            token = parts[1].decode("ascii")
        except UnicodeDecodeError as error:
            raise AuthenticationFailed("Invalid bearer token.") from error

        claims = self._decode_token(token)
        user = self._get_or_create_user(claims)
        if not user.is_active:
            raise AuthenticationFailed("Invalid bearer token.")

        return user, claims

    def authenticate_header(self, request: Request) -> str:
        return "Bearer"

    @staticmethod
    def _decode_token(token: str) -> dict:
        issuer = settings.COGNITO_ISSUER
        app_client_id = settings.COGNITO_APP_CLIENT_ID
        if not issuer or not app_client_id:
            raise AuthenticationFailed("Cognito authentication is not configured.")

        jwks_url = f"{issuer.rstrip('/')}/.well-known/jwks.json"
        try:
            signing_key = get_jwks_client(
                jwks_url,
                settings.COGNITO_JWKS_CACHE_SECONDS,
            ).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=issuer,
                options={
                    "require": ["client_id", "exp", "iat", "sub", "token_use"],
                    "verify_aud": False,
                },
            )
        except (PyJWKClientError, PyJWTError, OSError, TypeError, ValueError) as error:
            raise AuthenticationFailed("Invalid bearer token.") from error

        if claims.get("token_use") != "access":
            raise AuthenticationFailed("Invalid bearer token.")
        if not hmac.compare_digest(str(claims.get("client_id", "")), app_client_id):
            raise AuthenticationFailed("Invalid bearer token.")

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 255:
            raise AuthenticationFailed("Invalid bearer token.")

        return claims

    @staticmethod
    def _get_or_create_user(claims: dict):
        user_model = get_user_model()
        subject = claims["sub"]

        if user := user_model.objects.filter(cognito_sub=subject).first():
            return user

        digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        email = claims.get("email", "")
        if claims.get("email_verified") not in {True, "true"} or not isinstance(email, str):
            email = ""
        email = email[:254]

        # A verified subject is the only identity-linking key. Email remains display data.
        for attempt in range(3):
            username = f"cognito_{digest}" if attempt == 0 else f"cognito_{digest}_{attempt}"
            try:
                with transaction.atomic():
                    user = user_model(
                        username=username,
                        email=email,
                        cognito_sub=subject,
                    )
                    user.set_unusable_password()
                    user.save(force_insert=True)
                    return user
            except IntegrityError:
                if user := user_model.objects.filter(cognito_sub=subject).first():
                    return user

        raise AuthenticationFailed("Unable to provision authenticated user.")
