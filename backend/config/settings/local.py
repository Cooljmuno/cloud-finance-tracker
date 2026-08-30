import os

from .base import *  # noqa: F403
from .base import env_list

DEBUG = True
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key")
