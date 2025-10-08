from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q

from scheduling.domain.models import Assignment, AssignmentStatus, Member, Service, ScheduleMonth
from scheduling.domain.repositories import (
    MemberRepository,
    AvailabilityRepository,
    ServiceRepository,
    AssignmentRepository,
    ProjectionRepository,
)

PENALTY_RECENT_DAYS = 14
HARD_BLOCK_SCORE = -10_000

# ===== Data Classes =====

@dataclass
class SimulationState:
    """Estado da simulação de escalas do mês."""
    members: List[Member]
    last_assignment: Dict[int, Optional[datetime]] = field(default_factory=dict)
    month_count: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    day_block: Dict[date, Set[int]] = field(default_factory=lambda: defaultdict(set))
    _confirmed_sorted: List[Tuple[datetime, int]] = field(default_factory=list)
    _conf_index: int = 0

    def update_to_datetime(self, current_dt: datetime):
        """Atualiza o estado da simulação até a data e hora especificadas."""
        while (self._conf_index < len(self._confirmed_sorted) and
               self._confirmed_sorted[self._conf_index][0] < current_dt):
            dt, member_id = self._confirmed_sorted[self._conf_index]
            prev = self.last_assignment.get(member_id)
            if prev is None or dt > prev:
                self.last_assignment[member_id] = dt
            self._conf_index += 1

    def register_assignment(self, member_id: int, service_date: date, service_dt: datetime):
        """Registra uma atribuição simulada para um membro em um serviço."""
        self.day_block[service_date].add(member_id)
        self.month_count[member_id] = self.month_count.get(member_id, 0) + 1
        self.last_assignment[member_id] = service_dt

    @classmethod
    def initialize_for_month(cls, year: int, month: int, services: List[Service]) -> SimulationState:
        """Inicializa o estado da simulação para um mês específico."""
        members = list(MemberRepository.actives())
        first_dt = datetime.combine(services[0].date, services[0].time)
        real_last_dt: Dict[int, Optional[datetime]] = AssignmentRepository.baseline_last_confirmed_before(first_dt)
        sim_last_dt: Dict[int, Optional[datetime]] = dict(real_last_dt)
        sim_month_count: Dict[int, int] = AssignmentRepository.month_confirmed_counts(year, month)
        day_block: Dict[date, Set[int]] = AssignmentRepository.day_block_for_month(year, month)
        confirmed_month_sorted: List[Tuple[datetime, int]] = ProjectionRepository.confirmed_month_sorted(year, month)

        return cls(
            members=members,
            last_assignment=sim_last_dt,
            month_count=sim_month_count,
            day_block=day_block,
            _confirmed_sorted=confirmed_month_sorted,
        )

@dataclass
class CandidateScore:
    """Representa a pontuação e o estado de um candidato para uma atribuição."""
    member: Member
    score: int
    days_since_last: int
    age_minutes: int
    blocked: bool
    reason: Optional[str] = None
    last_assignment_dt: Optional[datetime] = None

    @property
    def recent_penalty(self) -> int:
        if 0 <= self.days_since_last < PENALTY_RECENT_DAYS:
            return PENALTY_RECENT_DAYS - self.days_since_last
        return 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "member": self.member,
            "score": self.score,
            "components": {
                "base_days_since": self.days_since_last,
                "recent_penalty": self.recent_penalty,
                "last_assignment": (self.last_assignment_dt.isoformat() if self.last_assignment_dt else None),
            },
            "blocked": self.blocked,
            "reason": self.reason,
            "age_minutes": self.age_minutes,
        }

class ServiceRanker:
    """Responsável por ranquear os candidatos para um serviço específico."""
    def __init__(self, service: Service, state: SimulationState):
        self.service = service
        self.state = state
        self.current_dt = datetime.combine(service.date, service.time)
        self.weekday = service.date.weekday()
        self.shift = service.shift

    def rank_candidates(self, limit: int = 5) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        """Ranqueia os candidatos para o serviço."""
        candidates = [self._score_member(m) for m in self.state.members]
        valid = [c for c in candidates if not c.blocked]
        blocked = [c for c in candidates if c.blocked]

        valid.sort(key=lambda c: (c.score, c.age_minutes), reverse=True)
        blocked.sort(key=lambda c: (-c.score, -c.age_minutes, c.member.name))
        ranked = (valid + blocked)[:limit]
        best_id = valid[0].member.id if valid else None
        return [c.to_dict() for c in ranked], best_id

    def _score_member(self, member: Member) -> CandidateScore:
        """Calcula a pontuação de um membro para o serviço."""
        blocked, reason = self._check_blocks(member)
        last_dt = self.state.last_assignment.get(member.id)
        days_since, age_minutes = self._calculate_time_since(last_dt)
        if blocked:
            score = HARD_BLOCK_SCORE
        else:
            score = self._calculate_score(days_since)
        return CandidateScore(
            member=member,
            score=score,
            days_since_last=days_since,
            age_minutes=age_minutes,
            blocked=blocked,
            reason=reason,
            last_assignment_dt=last_dt,
        )

    def _check_blocks(self, member: Member) -> Tuple[bool, Optional[str]]:
        """Verifica se o membro está bloqueado para este serviço."""
        if not AvailabilityRepository.is_available(member, self.weekday, self.shift):
            return True, "indisponível no turno"
        if member.id in self.state.day_block.get(self.service.date, set()):
            return True, "já escalado no mesmo dia"
        limit = MemberRepository.monthly_limit(member)
        if self.state.month_count.get(member.id, 0) >= limit:
            return True, "atingiu limite mensal"
        return False, None

    def _calculate_time_since(self, last_dt: Optional[datetime]) -> Tuple[int, int]:
        """Calcula os dias e minutos desde a última atribuição."""
        if last_dt is None:
            return 365, 10**12
        days_since = max((self.service.date - last_dt.date()).days, 0)
        age_minutes = int((self.current_dt - last_dt).total_seconds() // 60)
        return days_since, age_minutes

    def _calculate_score(self, days_since: int) -> int:
        """Calcula o score baseado nos dias desde a última atribuição."""
        if 0 <= days_since < PENALTY_RECENT_DAYS:
            return days_since - (PENALTY_RECENT_DAYS - days_since)
        return days_since

# ===== Suggestion Functions =====

@transaction.atomic
def suggest_for_month(year: int, month: int, user: User | None = None) -> Tuple[int, int]:
    """Sugere membros para um mês específico.

    Returns:
        Tuple[int, int]: (mês criado? 1:0, número de sugestões criadas)
    """
    sched, created = ScheduleMonth.objects.get_or_create(
        year=year, month=month, defaults={"generated_by": user}
    )
    services: List[Service] = ProjectionRepository.month_services_with_prefetch(
        year, month, include_extra=getattr(settings, "SUGGEST_FOR_EXTRA", False)
    )
    if not services:
        return (1 if created else 0, 0)
    state = SimulationState.initialize_for_month(year, month, services)
    plan: List[Assignment] = []
    for service in services:
        current_dt = datetime.combine(service.date, service.time)
        state.update_to_datetime(current_dt)
        confirmed_qs = service.assignments.filter(status=AssignmentStatus.CONFIRMED)
        if confirmed_qs.exists():
            for assignment in confirmed_qs:
                state.register_assignment(assignment.member_id, service.date, current_dt)
            continue
        ranker = ServiceRanker(service, state)
        _, best_member_id = ranker.rank_candidates(limit=1)
        if best_member_id is None:
            continue
        chosen = next(m for m in state.members if m.id == best_member_id)
        state.register_assignment(chosen.id, service.date, current_dt)
        plan.append(Assignment(
            service=service,
            member=chosen,
            status=AssignmentStatus.SUGGESTED,
            created_by=user
        ))
    if plan:
        Assignment.objects.bulk_create(plan, ignore_conflicts=True)
    return (1 if created else 0, len(plan))

def resuggest_month(
    year: int,
    month: int,
    user: User | None = None,
    from_service: Service | None = None
) -> List[int]:
    """Refaz as sugestões para um mês, preservando CONFIRMED e (opcionalmente) substituindo REPLACED
    a partir de um serviço. Não exclui assignments: reusa registros, promove/demove status.

    Returns:
        List[int]: IDs dos serviços que foram alterados
    """
    services = ProjectionRepository.month_services_with_prefetch(
        year, month, include_extra=getattr(settings, "SUGGEST_FOR_EXTRA", False)
    )
    if not services:
        return []

    reprocess_start_index = _find_service_index(services, from_service)
    if reprocess_start_index >= len(services):
        return []

    state = SimulationState.initialize_for_month(year, month, services)
    member_by_id = {m.id: m for m in state.members}
    locked = _get_locked_services(services)
    existing_before = Assignment.objects.filter(
        service_id__in=[s.id for s in services[:reprocess_start_index]]
    ).select_related("service", "member")

    for assignment in existing_before:
        current_dt = datetime.combine(assignment.service.date, assignment.service.time)
        state.update_to_datetime(current_dt)
        state.register_assignment(assignment.member_id, assignment.service.date, current_dt)

    new_suggestions: Dict[int, Optional[int]] = {}
    for idx, service in enumerate(services):
        current_dt = datetime.combine(service.date, service.time)
        state.update_to_datetime(current_dt)

        if idx < reprocess_start_index:
            locked_info = locked.get(service.id)
            if locked_info:
                member_id, _ = locked_info
                state.register_assignment(member_id, service.date, current_dt)
            else:
                sug = service.assignments.filter(status=AssignmentStatus.SUGGESTED).first()
                if sug:
                    state.register_assignment(sug.member_id, service.date, current_dt)
            continue

        if service.id in locked:
            member_id, st = locked[service.id]
            if st == AssignmentStatus.CONFIRMED or (st == AssignmentStatus.REPLACED and not from_service):
                new_suggestions[service.id] = None
                state.register_assignment(member_id, service.date, current_dt)
                continue
        ranker = ServiceRanker(service, state)
        _, best_member_id = ranker.rank_candidates(limit=5)
        new_suggestions[service.id] = best_member_id
        if best_member_id:
            state.register_assignment(best_member_id, service.date, current_dt)
    changed_ids = _apply_suggestion_changes(
        services=services,
        locked=locked,
        new_suggestions=new_suggestions,
        member_by_id=member_by_id,
        user=user,
        override_replaced=bool(from_service),
        reprocess_start_index=reprocess_start_index,
    )
    return changed_ids

def ranking_monthly_candidates(year: int, month: int, limit: int = 5) -> Dict[int, List[Dict]]:
    """Retorna ranking de candidatos para cada serviço do mês."""
    services = ProjectionRepository.month_services_with_prefetch(
        year, month, include_extra=getattr(settings, "SUGGEST_FOR_EXTRA", False)
    )
    if not services:
        return {}

    state = SimulationState.initialize_for_month(year, month, services)
    locked = _get_locked_services(services)
    results: Dict[int, List[Dict]] = {}

    for service in services:
        current_dt = datetime.combine(service.date, service.time)
        state.update_to_datetime(current_dt)

        if service.id in locked and locked[service.id][1] == "confirmed":
            member_id, _ = locked[service.id]
            state.register_assignment(member_id, service.date, current_dt)
            results[service.id] = []
            continue

        ranker = ServiceRanker(service, state)
        ranked, best_id = ranker.rank_candidates(limit=limit)
        results[service.id] = ranked

        if service.id in locked and locked[service.id][1] == "replaced":
            member_id, _ = locked[service.id]
            state.register_assignment(member_id, service.date, current_dt)
        elif best_id:
            state.register_assignment(best_id, service.date, current_dt)

    return results

# ===== Helper Functions =====

def _find_service_index(services: List[Service], target: Optional[Service]) -> int:
    """Encontra o índice de um serviço na lista."""
    if not target:
        return 0
    for idx, service in enumerate(services):
        if service.id == target.id:
            return idx + 1 if  idx + 1 < len(services) else idx
    return 0

def _get_locked_services(services: Iterable[Service]) -> Dict[int, Tuple[int, str]]:
    """Identifica serviços com membros bloqueados (confirmed/replaced)."""
    locked: Dict[int, Tuple[int, str]] = {}
    for service in services:
        confirmed_ids = list(ServiceRepository.confirmed_member_ids(service))
        if confirmed_ids:
            locked[service.id] = (confirmed_ids[0], "confirmed")
            continue

        replaced_ids = list(ServiceRepository.replaced_member_ids(service))
        if replaced_ids:
            locked[service.id] = (replaced_ids[0], "replaced")

    return locked

@transaction.atomic
def _apply_suggestion_changes(
    services: List[Service],
    locked: Dict[int, Tuple[int, str]],
    new_suggestions: Dict[int, Optional[int]],
    member_by_id: Dict[int, Member],
    user: Optional[User],
    override_replaced: bool,
    reprocess_start_index: int,
) -> List[int]:
    """Aplica as mudanças nas sugestões e retorna IDs dos serviços alterados."""
    changed: Set[int] = set()
    service_ids = [s.id for s in services]

    assignments = (
        Assignment.objects
        .select_for_update(skip_locked=True)
        .filter(service_id__in=service_ids)
        .select_related("service", "member")
        .order_by("id")
    )

    by_service: Dict[int, List[Assignment]] = _index_by_service(assignments)

    for idx, service in enumerate(services):
        if idx < reprocess_start_index:
            continue
        svc_id = service.id
        svc_assignments = by_service.get(svc_id, [])
        lock = _effective_lock(service_id=svc_id, locked=locked.copy(), override_replaced=override_replaced)
        if lock:
            locked_member_id, locked_status = lock
            if _apply_locked(service, svc_assignments, locked_member_id, locked_status, user):
                changed.add(svc_id)
            if _demote_all_suggested(svc_assignments):
                changed.add(svc_id)
            continue
        new_member_id = new_suggestions.get(svc_id)
        if new_member_id is None:
            if _demote_current_suggested(svc_assignments):
                changed.add(svc_id)
            continue
        if _promote_matching_replaced(svc_assignments, new_member_id, user):
            if _demote_extra_suggested(svc_assignments):
                changed.add(svc_id)
            changed.add(svc_id)
            continue
        if _update_existing_suggested(svc_assignments, new_member_id, user):
            if _demote_extra_suggested(svc_assignments):
                changed.add(svc_id)
            changed.add(svc_id)
            continue
        if _reuse_replaced_as_suggested(svc_assignments, new_member_id, user):
            changed.add(svc_id)
            continue

        check_existing = any(a.member_id == new_member_id and a.status == AssignmentStatus.SUGGESTED for a in svc_assignments)
        if check_existing:
            continue

        Assignment.objects.create(
            service=service,
            member=member_by_id[new_member_id],
            status=AssignmentStatus.SUGGESTED,
            created_by=user
        )
        changed.add(svc_id)
    return [sid for sid in service_ids if sid in changed]

# =========================
# Helpers (pequenos e focados)
# =========================

def _index_by_service(assignments: Iterable[Assignment]) -> Dict[int, List[Assignment]]:
    index: Dict[int, List[Assignment]] = {}
    for a in assignments:
        index.setdefault(a.service_id, []).append(a)
    return index

def _effective_lock(
    locked: Dict[int, Tuple[int, str]],
    service_id: int,
    override_replaced: bool
) -> Optional[Tuple[int, str]]:
    """Retorna (member_id, status) quando o serviço está de fato travado."""

    info = locked.get(service_id)
    if not info:
        return None
    member_id, status = info
    if status == AssignmentStatus.CONFIRMED:
        return member_id, status
    if status == AssignmentStatus.REPLACED and not override_replaced:
        return member_id, status
    return None

def _apply_locked(
    service: Service,
    assignments: List[Assignment],
    locked_member_id: int,
    locked_status: str,
    user: Optional[User],
) -> bool:
    """
    Garante um único registro refletindo o estado travado (CONFIRMED/REPLACED),
    reusando registros existentes antes de criar um novo.
    """
    target = _first_with_status(assignments, locked_status)
    if target:
        return _ensure_fields(target, locked_member_id, locked_status, user)

    reuse = _first_with_any(assignments, (AssignmentStatus.SUGGESTED, AssignmentStatus.REPLACED))
    if reuse:
        changed = False
        changed |= _set_member_id(reuse, locked_member_id)
        changed |= _set_status(reuse, locked_status)
        changed |= _set_created_by(reuse, user)
        if changed:
            _save(reuse, user, fields=("member_id", "status", "created_by"))
        return changed

    Assignment.objects.create(
        service=service,
        member_id=locked_member_id,
        status=locked_status,
        created_by=user
    )
    return True

def _demote_all_suggested(assignments: List[Assignment]) -> bool:
    """Em contexto travado: nenhum SUGGESTED deve restar."""
    changed = False
    for a in assignments:
        if a.status == AssignmentStatus.SUGGESTED:
            a.status = AssignmentStatus.REPLACED
            a.save(update_fields=["status"])
            changed = True
    return changed

def _demote_current_suggested(assignments: List[Assignment]) -> bool:
    """Quando não há nova sugestão: rebaixa o único SUGGESTED (se existir)."""
    sug = _first_with_status(assignments, AssignmentStatus.SUGGESTED)
    if not sug:
        return False
    if sug.status == AssignmentStatus.REPLACED:
        return False
    sug.status = AssignmentStatus.REPLACED
    sug.save(update_fields=["status"])
    return True

def _promote_matching_replaced(assignments: List[Assignment], member_id: int, user: Optional[User]) -> bool:
    """Promove para SUGGESTED um REPLACED que já é do novo membro, se não houver SUGGESTED atual."""
    if _first_with_status(assignments, AssignmentStatus.SUGGESTED):
        return False
    rep = _first(lambda a: a.status == AssignmentStatus.REPLACED and a.member_id == member_id, assignments)
    if not rep:
        return False
    rep.status = AssignmentStatus.SUGGESTED
    if user:
        rep.created_by = user
        rep.save(update_fields=["status", "created_by"])
    else:
        rep.save(update_fields=["status"])
    return True

def _update_existing_suggested(assignments: List[Assignment], member_id: int, user: Optional[User]) -> bool:
    """Atualiza o membro do SUGGESTED existente (sem criar duplicata)."""
    sug = _first_with_status(assignments, AssignmentStatus.SUGGESTED)
    if not sug:
        return False
    if sug.member_id == member_id:
        return False
    sug.member_id = member_id
    if user:
        sug.created_by = user
        sug.save(update_fields=["member_id", "created_by"])
    else:
        sug.save(update_fields=["member_id"])
    return True

def _reuse_replaced_as_suggested(assignments: List[Assignment], member_id: int, user: Optional[User]) -> bool:
    """Reusa um REPLACED para virar SUGGESTED do novo membro."""
    rep = _first_with_status(assignments, AssignmentStatus.REPLACED)
    if not rep:
        return False
    rep.member_id = member_id
    rep.status = AssignmentStatus.SUGGESTED
    if user:
        rep.created_by = user
        rep.save(update_fields=["member_id", "status", "created_by"])
    else:
        rep.save(update_fields=["member_id", "status"])
    return True

def _demote_extra_suggested(assignments: List[Assignment]) -> bool:
    """
    Em estado aberto: manter NO MÁXIMO 1 SUGGESTED.
    Se houver mais de um, o(s) excedente(s) vira(m) REPLACED.
    """
    suggested = [a for a in assignments if a.status == AssignmentStatus.SUGGESTED]
    if len(suggested) <= 1:
        return False
    # preserva o primeiro; rebaixa os demais
    changed = False
    keeper_id = suggested[0].id
    for a in suggested[1:]:
        a.status = AssignmentStatus.REPLACED
        a.save(update_fields=["status"])
        changed = True
    return changed

def _first_with_status(assignments: List[Assignment], status: str) -> Optional[Assignment]:
    return _first(lambda a: a.status == status, assignments)

def _first_with_any(assignments: List[Assignment], statuses: Tuple[str, ...]) -> Optional[Assignment]:
    return _first(lambda a: a.status in statuses, assignments)

def _first(pred, items):
    for it in items:
        if pred(it):
            return it
    return None

def _ensure_fields(a: Assignment, member_id: int, status: str, user: Optional[User]) -> bool:
    changed = False
    changed |= _set_member_id(a, member_id)
    changed |= _set_status(a, status)
    changed |= _set_created_by(a, user)
    if not changed:
        return False
    _save(a, user, fields=("member_id", "status", "created_by"))
    return True

def _set_member_id(a: Assignment, member_id: int) -> bool:
    if a.member_id == member_id:
        return False
    a.member_id = member_id
    return True

def _set_status(a: Assignment, status: str) -> bool:
    if a.status == status:
        return False
    a.status = status
    return True

def _set_created_by(a: Assignment, user: Optional[User]) -> bool:
    if not user:
        return False
    if getattr(a, "created_by_id", None) == user.id:
        return False
    a.created_by = user
    return True

def _save(a: Assignment, user: Optional[User], fields: Tuple[str, ...]) -> None:
    update_fields = list(fields)
    if not user and "created_by" in update_fields:
        update_fields.remove("created_by")
    a.save(update_fields=update_fields or None)
