from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple

from django.conf import settings
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Assignment, Member, Availability, Service
from .repositories import AssignmentRepository, MemberRepository, _count_extra_in_last_served
from scheduling.services.audit import audit, snapshot_instance

# =========================

def _month_tuple(d: date) -> Tuple[int, int]:
    return (d.year, d.month)

def _recalc_last_served(member_id: int) -> None:
    """Atualiza o campo last_served_at do membro com base no último serviço confirmado.

    Args:
        member_id (int): O ID do membro a ser atualizado.
    """
    m = MemberRepository.by_ids([member_id]).first()
    if not m:
        return

    qs = AssignmentRepository.confirmed_qs(include_extra=_count_extra_in_last_served()).filter(member_id=member_id)
    qs = qs.order_by("-service__date", "-service__time")
    last = qs.first()
    new_date = last.service.date if last else None

    if m.last_served_at != new_date:
        m.last_served_at = new_date
        m.save(update_fields=["last_served_at"])

# ========= Assignment: tratar mudanças com segurança =========

@dataclass
class _AssignmentOldState:
    """Estado antigo de uma atribuição, para comparação em pre_save."""
    member_id: Optional[int]
    status: Optional[str]
    service_year: Optional[int]
    service_month: Optional[int]
    before_snapshot: Optional[dict] = None

def _capture_old_assignment_state(instance: Assignment) -> _AssignmentOldState:
    """Captura o estado antigo de uma atribuição antes de ser salva.

    Args:
        instance (Assignment): A instância da atribuição que está sendo salva.

    Returns:
        _AssignmentOldState: O estado antigo capturado.
    """
    if not instance.pk:
        return _AssignmentOldState(None, None, None, None)

    try:
        old = Assignment.objects.select_related("service").get(pk=instance.pk)
        snap = snapshot_instance(old)
        return _AssignmentOldState(
            member_id=old.member_id,
            status=old.status,
            service_year=old.service.date.year,
            service_month=old.service.date.month,
            before_snapshot=snap
        )
    except Assignment.DoesNotExist:
        return _AssignmentOldState(None, None, None, None, None)

@receiver(pre_save, sender=Assignment)
def _assignment_pre_save(sender, instance: Assignment, **kwargs) -> None:
    instance._old_state = _capture_old_assignment_state(instance)

@receiver(post_save, sender=Assignment)
def _assignment_post_save(sender, instance: Assignment, created: bool, **kwargs) -> None:
    _recalc_last_served(instance.member_id)

    old: _AssignmentOldState = getattr(instance, "_old_state", _AssignmentOldState(None, None, None, None, None))
    if old.member_id and old.member_id != instance.member_id:
        _recalc_last_served(old.member_id)

    action = "create" if created else "update"
    after = snapshot_instance(instance)
    audit(action, instance, before=old.before_snapshot, after=after)

@receiver(post_delete, sender=Assignment)
def _assignment_post_delete(sender, instance: Assignment, **kwargs) -> None:
    """Após a exclusão de uma atribuição, recalcula last_served_at e invalida ranking."""
    _recalc_last_served(instance.member_id)

    before = snapshot_instance(instance)
    audit("delete", instance, before=before, after=None)

# ========= Service: editar data/hora/tipo deve invalidar ranking =========

@receiver(pre_save, sender=Service)
def _service_pre_save(sender, instance: Service, **kwargs):
    """Captura o mês antigo do serviço antes de ser salvo."""
    if not instance.pk:
        instance._old_service_month = None
        instance._before_snapshot = None
        return
    try:
        old = Service.objects.get(pk=instance.pk)
        instance._old_service_month = _month_tuple(old.date)
        instance._before_snapshot = snapshot_instance(old)
    except Service.DoesNotExist:
        instance._old_service_month = None
        instance._before_snapshot = None

@receiver(post_save, sender=Service)
def _service_post_save(sender, instance: Service, created: bool, **kwargs):
    action = "create" if created else "update"
    audit(action, instance, before=getattr(instance, "_before_snapshot", None), after=snapshot_instance(instance))


@receiver(post_delete, sender=Service)
def _service_post_delete(sender, instance: Service, **kwargs):
    audit("delete", instance, before=snapshot_instance(instance), after=None)

# ======== Availability ========

@receiver(pre_save, sender=Availability)
def _availability_pre_save(sender, instance: Availability, **kwargs):
    if not instance.pk:
        instance._before_snapshot = None
        return
    try:
        old = Availability.objects.get(pk=instance.pk)
        instance._before_snapshot = snapshot_instance(old)
    except Availability.DoesNotExist:
        instance._before_snapshot = None

@receiver(post_save, sender=Availability)
def _availability_post_save(sender, instance: Availability, created: bool, **kwargs):
    action = "create" if created else "update"
    audit(action, instance, before=getattr(instance, "_before_snapshot", None), after=snapshot_instance(instance))

@receiver(post_delete, sender=Availability)
def _availability_post_delete(sender, instance: Availability, **kwargs):
    audit("delete", instance, before=snapshot_instance(instance), after=None)

# ======== Member ========

@receiver(pre_save, sender=Member)
def _member_pre_save(sender, instance: Member, **kwargs):
    if not instance.pk:
        instance._before_snapshot = None
        return
    try:
        old = Member.objects.get(pk=instance.pk)
        instance._before_snapshot = snapshot_instance(old)
    except Member.DoesNotExist:
        instance._before_snapshot = None

@receiver(post_save, sender=Member)
def _member_post_save(sender, instance: Member, created: bool, **kwargs):
    action = "create" if created else "update"
    audit(action, instance, before=getattr(instance, "_before_snapshot", None), after=snapshot_instance(instance))

@receiver(post_delete, sender=Member)
def _member_post_delete(sender, instance: Member, **kwargs):
    audit("delete", instance, before=snapshot_instance(instance), after=None)
