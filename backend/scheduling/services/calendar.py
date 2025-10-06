from __future__ import annotations

from datetime import date, time
import calendar as pycal
from typing import Iterable, List, Sequence, Tuple

from django.conf import settings
from django.db import transaction

from scheduling.domain.models import Service, ServiceType

# ========= Utilidades tradicionais =========

def _parse_time(s: str | time) -> time:
    """Padroniza a entrada como time.

    Args:
        s (str | time): String no formato "HH:MM" ou objeto time.

    Returns:
        time: Objeto time correspondente.
    """
    if isinstance(s, time):
        return s
    hh, mm = str(s).split(":")
    return time(hour=int(hh), minute=int(mm))

def _default_times() -> Tuple[time, time]:
    """Retorna os horários padrão de manhã e à noite.

    Returns:
        Tuple[time, time]: Horários padrão de manhã e à noite.
    """
    return _parse_time(settings.DEFAULT_MORNING_TIME), _parse_time(settings.DEFAULT_EVENING_TIME)

def sundays_in_month(year: int, month: int) -> List[date]:
    """Lista os domingos (weekday=6) do mês/ano informados.

    Args:
        year (int): Ano do mês a ser verificado.
        month (int): Mês a ser verificado.

    Returns:
        List[date]: Lista de domingos do mês/ano informados.
    """
    cal = pycal.Calendar(firstweekday=0)
    return [
        d for d in cal.itermonthdates(year, month)
        if d.month == month and d.weekday() == 6
    ]

# ========= Operações principais =========


@transaction.atomic
def ensure_month_services(year: int, month: int) -> int:
    """Garante que existam serviços agendados para todos os domingos do mês.

    Args:
        year (int): Ano do mês a ser verificado.
        month (int): Mês a ser verificado.

    Returns:
        int: Número de serviços criados.
    """
    morning, evening = _default_times()
    dates = sundays_in_month(year, month)
    return _ensure_services_for_dates(
        dates=dates,
        times=[morning, evening],
        service_type=ServiceType.CULTO,
        label=None
    )

def ensure_date_services(
    d: date, *,
    morning: time | str | None = None,
    evening: time | str | None = None,
    service_type: str = ServiceType.CULTO,
    label: str | None = None
) -> int:
    """Garante que exista um serviço agendado para a data informada.

    Args:
        d (date): Data do serviço.
        morning (time | str | None, optional): Horário da manhã. Defaults to None.
        evening (time | str | None, optional): Horário da noite. Defaults to None.
        service_type (str, optional): Tipo de serviço. Defaults to "Culto".
        label (str | None, optional): Rótulo do serviço. Defaults to None.

    Returns:
        int: Número de serviços criados.
    """
    m, e = _default_times()
    morning_time = _parse_time(morning) if morning else m
    evening_time = _parse_time(evening) if evening else e
    times = [morning_time, evening_time]
    return _ensure_services_for_dates(
        dates=[d],
        times=times,
        service_type=service_type,
        label=label
    )

@transaction.atomic
def _ensure_services_for_dates(
    dates: Sequence[date],
    times: Sequence[time],
    *,
    service_type: str = ServiceType.CULTO,
    label: str | None = None
) -> int:
    """Garante que existam serviços agendados para as datas e horários informados.

    Args:
        dates (Sequence[date]): Lista de datas para as quais os serviços devem ser garantidos.
        times (Sequence[time]): Lista de horários para os quais os serviços devem ser garantidos.
        service_type (str, optional): Tipo de serviço a ser garantido. Defaults to ServiceType.CULTO.
        label (str | None, optional): Rótulo do serviço a ser garantido. Defaults to None.

    Returns:
        int: Número de serviços criados.
    """
    if not dates or not times:
        return 0

    existing_keys = set(
        Service.objects
        .filter(date__in=dates, time__in=times)
        .values_list("date", "time")
    )

    missing = []
    for d in dates:
        for t in times:
            key = (d, t)
            if key not in existing_keys:
                missing.append(Service(date=d, time=t, type=service_type, label=label))

    if not missing:
        return 0

    Service.objects.bulk_create(missing, ignore_conflicts=True)
    return len(missing)
