import pytest
from django.contrib.auth.models import User

@pytest.mark.django_db
def test_calendar_view(client):
    user = User.objects.create_user("u","u@example.com","pw")
    client.login(username="u", password="pw")
    resp = client.get("/")
    assert resp.status_code == 200
