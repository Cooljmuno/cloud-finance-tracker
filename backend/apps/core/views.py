from django.db import connection
from django.db.utils import DatabaseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):  # noqa: ARG002
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            return Response(
                {"service": "api", "status": "degraded", "database": "unavailable"},
                status=HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"service": "api", "status": "ok", "database": "ok"},
            status=HTTP_200_OK,
        )
