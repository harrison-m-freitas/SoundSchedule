from __future__ import annotations

import logging
from typing import List

from django.apps import AppConfig
from django.core.checks import Error, Tags, register

from scheduling.utils import _get_setting

log = logging.getLogger(__name__)

# =========================
# System checks (validações de settings)
# =========================

def _validate_time_string(value: str, setting_name: str, error_id: str) -> List[Error]:
    try:
        hh, mm = str(value).split(":")
        h, m = int(hh), int(mm)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except Exception:
        return [
            Error(
                f"{setting_name} deve estar no formato HH:MM (ex.: '09:00'). Valor atual: {value!r}",
                id=error_id,
            )
        ]
    return []

@register(Tags.compatibility)
def scheduling_settings_check(app_configs, **kwargs):
    """Garante que os settings essenciais estejam válidos."""
    errors: List[Error] = []

    errors += _validate_time_string(
        _get_setting("DEFAULT_MORNING_TIME", "09:00"),
        "DEFAULT_MORNING_TIME",
        "scheduling.E001",
    )
    errors += _validate_time_string(
        _get_setting("DEFAULT_EVENING_TIME", "18:00"),
        "DEFAULT_EVENING_TIME",
        "scheduling.E002",
    )

    limit = _get_setting("DEFAULT_MONTHLY_LIMIT", 2)
    if not isinstance(limit, int) or limit < 1:
        errors.append(
            Error(
                "DEFAULT_MONTHLY_LIMIT deve ser um inteiro >= 1.",
                id="schedulingE003",
            )
        )

    return errors

# =========================
# AppConfig
# =========================

class SchedulingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduling'
    verbose_name = "Escala da Mesa de Som"

    def ready(self):
        """Conecta signals do domínio de forma segura."""
        try:
            # importa e registra os signals (Assignment, Service, Member, Availability, Audit)
            from .domain import signals  # noqa: F401
        except Exception:  # pragma: no cover
            log.exception("Falha ao importar scheduling.domain.signals")
