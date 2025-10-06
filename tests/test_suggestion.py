import pytest
from datetime import date, time, timedelta
from scheduling.models import Member, Availability, Service, Assignment
from scheduling.services.suggestion import suggest_for_month
from scheduling.services.calendar import ensure_month_services

@pytest.mark.django_db
def test_suggestion_basic():
    m1 = Member.objects.create(name="A", monthly_limit=2)
    m2 = Member.objects.create(name="B", monthly_limit=2)
    Availability.objects.create(member=m1, weekday=6, shift="morning", active=True)
    Availability.objects.create(member=m1, weekday=6, shift="evening", active=True)
    Availability.objects.create(member=m2, weekday=6, shift="morning", active=True)
    Availability.objects.create(member=m2, weekday=6, shift="evening", active=True)

    ensure_month_services(2025, 10)
    created, count = suggest_for_month(2025, 10, user=None)
    assert count > 0
