from unittest.mock import patch

import pytest
from django.db.utils import DatabaseError
from django.urls import reverse


@pytest.mark.django_db
def test_health_endpoint_reports_api_and_database_status(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {
        "service": "api",
        "status": "ok",
        "database": "ok",
    }


def test_health_endpoint_reports_an_unavailable_database(client):
    with patch("apps.core.views.connection.cursor", side_effect=DatabaseError):
        response = client.get(reverse("health"))

    assert response.status_code == 503
    assert response.json() == {
        "service": "api",
        "status": "degraded",
        "database": "unavailable",
    }
