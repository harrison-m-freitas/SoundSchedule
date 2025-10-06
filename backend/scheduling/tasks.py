from __future__ import annotations

import logging
from datetime import timedelta
from typing import Iterable, List, Optional, Tuple

from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.mail import send_mail
from django.utils import timezone

from scheduling.services.calendar import ensure_month_services
from scheduling.services.suggestion import suggest_for_month
from scheduling.domain.models import Assignment, Service

log = logging.getLogger(__name__)

# =========================
# Helpers
# =========================

def _next_year_month(y: int, m: int) -> Tuple[int, int]:
    return (y + 1, 1) if m == 12 else (y, m + 1)

def _distinct_valid_emails(users: Iterable[User]) -> List[str]:
    emails = {u.email.strip().lower() for u in users if getattr(u, "email", None)}
    return [e for e in emails if e]

# =========================
# Tasks
# =========================

@shared_task
def monthly_draft_generation() -> str:
    """Generate the monthly draft schedule.

    Returns:
        str: A message indicating the result of the draft generation.
    """
    now = timezone.localtime()
    if now.day != settings.SCHEDULE_GENERATION_DAY or now.hour != settings.SCHEDULE_GENERATION_HOUR:
        return "Not the scheduled time."
    year, month = _next_year_month(now.year, now.month)
    log.info("Monthly draft generation: ensuring services for %04d-%02d", year, month)
    created_count = ensure_month_services(year, month)

    created_flag, assignments = suggest_for_month(year, month, user=None)
    log.info(
        "Monthly draft: services_created=%s, suggestions=%s (created_flag=%s)",
        created_count,
        assignments,
        created_flag,
    )

    try:
        notify_month_generated.delay(year, month)
    except Exception:
        log.exception("Failed to enqueue notify_month_generated task")
    return f"Draft generated for {year}-{month:02d} (services+suggestions)"

@shared_task
def notify_month_generated(year: int, month: int) -> int:
    """Notifica os usuários sobre a geração do rascunho da escala mensal.

    Args:
        year (int): Ano do mês gerado.
        month (int): Mês do mês gerado.

    Returns:
        int: Número de destinatários notificados.
    """
    subject = f"Escala {year}-{month:02d} gerada (rascunho)"
    msg = f"Acesse o sistema e revise o rascunho do mês {month:02d}/{year}."
    try:
        group = Group.objects.filter(name="Coordinator").first()
        users = group.user_set.all() if group else []
        recipients = _distinct_valid_emails(users)
    except Exception:  # pragma: no cover
        log.exception("Erro ao coletar destinatários do grupo Coordinator")
        recipients = []
    if not recipients:
        log.info("notify_month_generated: nenhum destinatário encontrado.")
        return 0
    try:
        send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
        log.info("notify_month_generated: enviado para %d destinatário(s).", len(recipients))
    except Exception:  # pragma: no cover
        log.exception("Falha ao enviar notify_month_generated.")
        return 0
    return len(recipients)

@shared_task
def notify_assignment(member_email: str, service_id: int, status: str) -> None:
    """Notifica um membro sobre a atribuição de um serviço.

    Args:
        member_email (str): Email do membro a ser notificado.
        service_id (int): ID do serviço associado à atribuição.
        status (str): Status da atribuição ("confirmed").
    """
    if not member_email:
        return
    if status not in ("confirmed"):
        return

    try:
        s = Service.objects.get(id=service_id)
    except Service.DoesNotExist:
        log.warning("notify_assignment: Service %s não existe mais.", service_id)
        return

    human = "confirmado" if status == "confirmed" else status
    subject = f"Você foi {human} para {s.date} {s.time.strftime('%H:%M')}"
    msg = f"Serviço: {s.type} em {s.date} às {s.time.strftime('%H:%M')}."

    try:
        send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, [member_email], fail_silently=True)
    except Exception:  # pragma: no cover
        log.exception("Falha ao enviar notify_assignment para %s (service=%s).", member_email, service_id)

@shared_task
def daily_reminder():
    """Envia lembrete diário para serviços nos próximos 7 dias aos membros confirmados.

    Returns:
        int: Número de lembretes enfileirados.
    """
    today = timezone.localdate()
    end = today + timedelta(days=7)

    qs = (
        Assignment.objects
        .filter(status="confirmed", service__date__gte=today, service__date__lte=end)
        .select_related("member", "service")
    )

    count = 0
    for a in qs:
        email = getattr(a.member, "email", None)
        if not email:
            continue
        notify_assignment.delay(email, a.service_id, "confirmed")
        count += 1

    log.info("daily_reminder: %d lembrete(s) enfileirado(s).", count)
    return count
