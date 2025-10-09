from __future__ import annotations

from datetime import datetime, timedelta

from django.utils.timezone import (
    get_current_timezone,
    get_current_timezone_name,
    make_aware,
    now as tz_now,
)
from icalendar import Calendar, Event, vCalAddress, vText

from scheduling.domain.models import Service
from scheduling.utils import _get_setting

def export_schedule_ics(year: int, month: int) -> bytes:
    """Exporta a programação para um arquivo ICS.

    Args:
        year (int): O ano da programação.
        month (int): O mês da programação.

    Returns:
        bytes: O conteúdo do arquivo ICS gerado.
    """
    cal = Calendar()
    cal.add("prodid", "-//Escala Mesa de Som//")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", f"Escala Mesa de Som {year}-{month:02d}")
    cal.add("X-WR-TIMEZONE", get_current_timezone_name())

    tz = get_current_timezone()
    duration_min = int(_get_setting("ICS_EVENT_DURATION_MINUTES", 120))
    now = tz_now()

    services = (
        Service.objects.filter(date__year=year, date__month=month)
        .order_by("date", "time")
        .prefetch_related("assignments__member")
    )

    for s in services:
        ev = Event()

        dtstart = make_aware(datetime.combine(s.date, s.time), tz)
        dtend = dtstart + timedelta(minutes=duration_min)

        # Campos básicos do evento
        ev.add("uid", f"svc-{s.id}@sound-schedule.local")
        ev.add("dtstamp", now)
        ev.add("dtstart", dtstart)
        ev.add("dtend", dtend)
        ev.add("categories", [s.type])

        # Resumo e descrição
        names = ", ".join(str(a.member) for a in s.assignments.all())
        label = f" - {s.label}" if s.label else ""
        summary = f"{s.type}{label}" + (f" — {names}" if names else "")
        ev.add("summary", summary)

        desc_lines = [
            f"Serviço: {s.type}{label}",
            f"Início: {s.date.strftime('%d/%m/%Y')} às {s.time.strftime('%H:%M')}",
        ]
        if names:
            desc_lines.append(f"Escalados: {names}")
        ev.add("description", "\n".join(desc_lines))

        # Local opcional (se configurado)
        loc = _get_setting("CALENDAR_LOCATION", None)
        if loc:
            ev.add("location", loc)

        # Attendees (se possuir e-mail)
        for a in s.assignments.all():
            email = getattr(a.member, "email", None)
            if email:
                attendee = vCalAddress(f"MAILTO:{email}")
                attendee.params["cn"] = vText(str(a.member))
                attendee.params["role"] = vText("REQ-PARTICIPANT")
                ev.add("attendee", attendee, encode=0)

        cal.add_component(ev)

    return cal.to_ical()
