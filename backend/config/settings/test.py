import os

from . import base
from .base import *  # noqa: F403

SECRET_KEY = "test-only-secret-key"

if not os.getenv("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

ENABLE_LOCAL_AUTH = True
ENABLE_DEMO_DATA = True
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173"]

REST_FRAMEWORK = {
    **base.REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.SessionAuthenticationWith401",
    ],
}
