import pytest
from scheduling.services.calendar import ensure_month_services
from scheduling.models import Service

@pytest.mark.django_db
def test_calendar_generation():
    n = ensure_month_services(2025, 10)
    assert Service.objects.filter(date__year=2025, date__month=10).count() > 0
