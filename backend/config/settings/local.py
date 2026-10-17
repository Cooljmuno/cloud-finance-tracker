import os

from . import base
from .base import *  # noqa: F403
from .base import env_list

DEBUG = True
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key")
ENABLE_LOCAL_AUTH = True
ENABLE_DEMO_DATA = True
ENABLE_DJANGO_ADMIN = True
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")

REST_FRAMEWORK = {
    **base.REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.SessionAuthenticationWith401",
    ],
}
