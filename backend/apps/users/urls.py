from django.conf import settings
from django.urls import path

from .views import CurrentUserView, csrf_token, session_login, session_logout

urlpatterns = [
    path("me/", CurrentUserView.as_view(), name="current-user"),
]

if settings.ENABLE_LOCAL_AUTH:
    urlpatterns += [
        path("csrf/", csrf_token, name="csrf-token"),
        path("login/", session_login, name="session-login"),
        path("logout/", session_logout, name="session-logout"),
    ]
