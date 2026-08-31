import os

from . import base
from .base import *  # noqa: F403
from .base import env_list

DEBUG = True
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key")

REST_FRAMEWORK = {
    **base.REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
}
