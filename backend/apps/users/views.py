import json
from json import JSONDecodeError

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def user_payload(user) -> dict[str, str]:
    return {
        "id": str(user.id),
        "username": user.get_username(),
        "email": user.email,
    }


@require_GET
@never_cache
@ensure_csrf_cookie
def csrf_token(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"csrfToken": get_token(request)})


@require_POST
@csrf_protect
def session_login(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body)
    except JSONDecodeError, UnicodeDecodeError:
        return JsonResponse({"detail": "Request body must be valid JSON."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"detail": "Request body must be a JSON object."}, status=400)

    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return JsonResponse({"detail": "Username and password are required."}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"detail": "Invalid username or password."}, status=401)

    login(request, user)
    return JsonResponse(user_payload(user))


@require_POST
@csrf_protect
def session_logout(request: HttpRequest) -> HttpResponse:
    logout(request)
    return HttpResponse(status=204)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_payload(request.user))
