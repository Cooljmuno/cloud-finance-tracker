import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import BASE_DIR, MIDDLEWARE, env_list


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


SECRET_KEY = required_env("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong, unique production secret")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

if not ALLOWED_HOSTS or any("*" in host or host.startswith(".") for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit, non-wildcard hosts")

COGNITO_REGION = required_env("COGNITO_REGION")
COGNITO_USER_POOL_ID = required_env("COGNITO_USER_POOL_ID")
COGNITO_APP_CLIENT_ID = required_env("COGNITO_APP_CLIENT_ID")
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"

POSTGRES_SSLROOTCERT = Path(
    os.getenv("POSTGRES_SSLROOTCERT", str(BASE_DIR / "certs" / "global-bundle.pem"))
)
if not POSTGRES_SSLROOTCERT.is_file():
    raise ImproperlyConfigured("POSTGRES_SSLROOTCERT must reference a readable RDS CA bundle")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required_env("POSTGRES_DB"),
        "USER": required_env("POSTGRES_USER"),
        "PASSWORD": required_env("POSTGRES_PASSWORD"),
        "HOST": required_env("POSTGRES_HOST"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "sslmode": "verify-full",
            "sslrootcert": str(POSTGRES_SSLROOTCERT),
            "connect_timeout": 5,
        },
    }
}

MIDDLEWARE = [
    "apps.core.middleware.ProductionCommonMiddleware"
    if middleware == "django.middleware.common.CommonMiddleware"
    else middleware
    for middleware in MIDDLEWARE
]

SECURE_PROXY_SSL_HEADER = ("HTTP_CLOUDFRONT_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.CognitoJWTAuthentication",
    ],
}
