from apps.users.models import User


def test_user_string_prefers_email():
    user = User(username="jonathan", email="jonathan@example.com")

    assert str(user) == "jonathan@example.com"


def test_user_string_falls_back_to_username():
    user = User(username="jonathan")

    assert str(user) == "jonathan"
