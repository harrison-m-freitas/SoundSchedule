from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Dict, Iterable, List, Optional, Set, Tuple

from django.db.models import Q, QuerySet

from scheduling.domain.models import (
    Member,
    Availability,
    Service,
    Assignment,
)
from scheduling.utils import _get_setting

# ==========================================================
# Helpers de política (clássico: sem “surpresa” em cada chamada)
# ==========================================================
def _count_extra_in_last_served() -> bool:
    """Verifica se deve contar serviços extras no último atendido.

    Returns:
        bool: True se deve contar serviços extras, False caso contrário.
    """
    return _get_setting("COUNT_EXTRA_IN_LAST_SERVED", False)

# ==========================================================
# Member Repository
# ==========================================================
class MemberRepository:
    """Repositório para operações relacionadas a Member."""

    @classmethod
    def all_members(cls) -> QuerySet[Member]:
        """Retorna todos os membros.

        Returns:
            QuerySet[Member]: Todos os membros.
        """
        return Member.objects.all().order_by("name")

    @classmethod
    def actives(cls) -> QuerySet[Member]:
        """Retorna os membros ativos.

        Returns:
            QuerySet[Member]: Os membros ativos.
        """
        return Member.objects.filter(active=True).order_by("name")

    @classmethod
    def by_ids(cls, ids: Iterable[int]) -> QuerySet[Member]:
        """Retorna os membros com os IDs especificados.

        Args:
            ids (Iterable[int]): Os IDs dos membros a serem retornados.

        Returns:
            QuerySet[Member]: Os membros correspondentes aos IDs fornecidos.
        """
        return Member.objects.filter(id__in=ids).order_by("name")

    @classmethod
    def monthly_limit(cls, member: Member) -> int:
        """Retorna o limite mensal de um membro.

        Args:
            member (Member): O membro cujo limite mensal será retornado.

        Returns:
            int: O limite mensal do membro.
        """
        return member.monthly_limit or _get_setting("DEFAULT_MONTHLY_LIMIT", 2)

# ==========================================================
# Availability Repository
# ==========================================================
class AvailabilityRepository:
    """Repositório para operações relacionadas a Availability."""

    @classmethod
    def for_member(cls, member: Member, active_only: bool = True) -> QuerySet[Availability]:
        """Retorna as disponibilidades de um membro.

        Args:
            member (Member): O membro cujas disponibilidades serão retornadas.
            active_only (bool, optional): Se deve filtrar apenas as disponibilidades ativas. Defaults to True.

        Returns:
            QuerySet[Availability]: As disponibilidades do membro.
        """
        qs = Availability.objects.filter(member=member)
        if active_only:
            qs = qs.filter(active=True)
        return qs

    @classmethod
    def is_available(cls, member: Member, weekday: int, shift: str) -> bool:
        """Verifica se um membro está disponível em um determinado dia e turno.

        Args:
            member (Member): O membro a ser verificado.
            weekday (int): O dia da semana (0=domingo, 6=sábado).
            shift (str): O turno a ser verificado.

        Returns:
            bool: True se o membro estiver disponível, False caso contrário.
        """
        base_qs = Availability.objects.filter(member=member, active=True)
        if not base_qs.exists():
            return True
        return base_qs.filter(weekday=weekday, shift=shift).exists()

# ==========================================================
# Service Repository
# ==========================================================
class ServiceRepository:
    """Repositório para operações relacionadas a Service."""

    @classmethod
    def month_services(cls, year: int, month: int, include_extra: bool = True) -> QuerySet[Service]:
        """Retorna os serviços para um mês específico.

        Args:
            year (int): O ano a ser considerado.
            month (int): O mês a ser considerado.
            include_extra (bool, optional): Se deve incluir serviços extras. Defaults to True.

        Returns:
            QuerySet[Service]: Os serviços para o mês e ano especificados.
        """
        qs = (
            Service.objects
            .filter(date__year=year, date__month=month)
            .order_by("date", "time")
            .prefetch_related("assignments", "assignments__member")
        )
        if not include_extra and not _get_setting("SUGGEST_FOR_EXTRA", False):
            qs = qs.filter(type="Culto")
        return qs

    @classmethod
    def confirmed_member_ids(cls, s: Service, only_first: bool = False) -> Set[int]:
        """Retorna os IDs dos membros confirmados para um serviço específico.

        Args:
            s (Service): O serviço a ser considerado.
            only_first (bool, optional): Se deve retornar apenas o primeiro ID. Defaults to False.

        Returns:
            Set[int]: Um conjunto de IDs dos membros confirmados para o serviço.
        """
        if only_first:
            mid = s.assignments.filter(status="confirmed").values_list("member_id", flat=True).first()
            return {mid} if mid is not None else set()
        return set(s.assignments.filter(status="confirmed").values_list("member_id", flat=True))

    @classmethod
    def replaced_member_ids(cls, s: Service, only_first: bool = False) -> Set[int]:
        """Retorna os IDs dos membros que foram substituídos em um serviço específico.

        Args:
            s (Service): O serviço a ser considerado.
            only_first (bool, optional): Se deve retornar apenas o primeiro ID. Defaults to False.

        Returns:
            Set[int]: Um conjunto de IDs dos membros substituídos no serviço.
        """
        if only_first:
            mid = s.assignments.filter(status="replaced").values_list("member_id", flat=True).first()
            return {mid} if mid is not None else set()
        return set(s.assignments.filter(status="replaced").values_list("member_id", flat=True))


    @classmethod
    def for_day(cls, d: date) -> QuerySet[Service]:
        """Retorna os serviços para um dia específico.

        Args:
            d (date): A data a ser considerada.

        Returns:
            QuerySet[Service]: Os serviços para o dia especificado.
        """
        return Service.objects.filter(date=d).order_by("time")

# ==========================================================
# Assignment Repository
# ==========================================================
class AssignmentRepository:
    """Repositório para operações relacionadas a Assignment."""

    @classmethod
    def confirmed_qs(cls, include_extra: bool | None = None) -> QuerySet[Assignment]:
        """Retorna as atribuições confirmadas.

        Args:
            include_extra (bool | None, optional): Se deve incluir serviços extras. Defaults to None.

        Returns:
            QuerySet[Assignment]: As atribuições confirmadas.
        """
        qs = Assignment.objects.filter(status="confirmed").select_related("member", "service")
        if not include_extra and not _get_setting("SUGGEST_FOR_EXTRA", False):
            qs = qs.filter(service__type="Culto")
        return qs

    @classmethod
    def month_confirmed(cls, year: int, month: int, include_extra: bool | None = None) -> QuerySet[Assignment]:
        """Retorna as atribuições confirmadas para um mês específico.

        Args:
            year (int): O ano da escala.
            month (int): O mês da escala.
            include_extra (bool | None, optional): Se deve incluir serviços extras. Defaults to None.

        Returns:
            QuerySet[Assignment]: As atribuições confirmadas para o mês específico.
        """
        qs = (
            AssignmentRepository.confirmed_qs(include_extra=include_extra)
            .filter(service__date__year=year, service__date__month=month)
            .order_by("service__date", "service__time", "member__name")
        )
        return qs

    @classmethod
    def month_suggested(cls, year: int, month: int, include_extra: bool | None = None) -> QuerySet[Assignment]:
        """Retorna as atribuições sugeridas para um mês específico.

        Args:
            year (int): O ano da escala.
            month (int): O mês da escala.
            include_extra (bool | None, optional): Se deve incluir serviços extras. Defaults to None.
        Returns:
            QuerySet[Assignment]: As atribuições sugeridas para o mês específico.
        """
        qs = Assignment.objects.filter(status="suggested").select_related("member", "service")
        if not include_extra and not _get_setting("SUGGEST_FOR_EXTRA", False):
            qs = qs.filter(service__type="Culto")
        qs = qs.filter(service__date__year=year, service__date__month=month)
        return qs.order_by("service__date", "service__time", "member__name")

    @classmethod
    def month_confirmed_counts(cls, year: int, month: int, include_extra: bool | None = None) -> Dict[int, int]:
        """Retorna um dicionário com a contagem de atribuições confirmadas por membro em um mês específico.

        Args:
            year (int): O ano da escala.
            month (int): O mês da escala.
            include_extra (bool | None, optional): Se deve incluir serviços extras. Defaults to None.

        Returns:
            Dict[int, int]: Um dicionário onde a chave é o ID do membro e o valor é a contagem de atribuições confirmadas.
        """
        out: Dict[int, int] = defaultdict(int)
        for mid in AssignmentRepository.month_confirmed(year, month, include_extra=include_extra)\
                                 .values_list("member_id", flat=True):
            out[int(mid)] += 1
        return out

    @classmethod
    def has_same_day(cls, member: Member, d: date) -> bool:
        """Verifica se o membro já tem qualquer assignment no dia (independe do status).

        Args:
            member (Member): O membro a ser verificado.
            d (date): A data a ser verificada.

        Returns:
            bool: True se o membro tiver um assignment na data, False caso contrário.
        """
        return Assignment.objects.filter(member=member, service__date=d).exists()

    @classmethod
    def last_confirmed_before(cls, member: Member, ref_date: date, ref_time: time) -> Optional[Assignment]:
        """Retorna o último assignment confirmado do membro antes de (ref_date, ref_time).

        Args:
            member (Member): O membro a ser verificado.
            ref_date (date): A data de referência.
            ref_time (time): A hora de referência.

        Returns:
            Optional[Assignment]: O último assignment confirmado do membro antes de (ref_date, ref_time), ou None se não houver.
        """
        qs = AssignmentRepository.confirmed_qs().filter(member=member)
        qs = qs.filter(Q(service__date__lt=ref_date) | Q(service__date=ref_date, service__time__lt=ref_time))
        return qs.order_by("-service__date", "-service__time").first()

    @classmethod
    def last_confirmed_dt_before(cls, member: Member, ref_date: date, ref_time: time) -> Optional[datetime]:
        """Retorna a data e hora da última atribuição confirmada antes da data e hora de referência.

        Args:
            member (Member): O membro a ser verificado.
            ref_date (date): A data de referência.
            ref_time (time): A hora de referência.

        Returns:
            Optional[datetime]: A data e hora da última atribuição confirmada antes da data e hora de referência, ou None se não houver.
        """
        a = AssignmentRepository.last_confirmed_before(member, ref_date, ref_time)
        if not a:
            return None
        return datetime.combine(a.service.date, a.service.time)

    @classmethod
    def baseline_last_confirmed_before(cls, first_dt: datetime) -> Dict[int, Optional[datetime]]:
        """Retorna um dicionário com a data e hora da última atribuição confirmada antes de first_dt.

        Args:
            first_dt (datetime): A data e hora de referência.

        Returns:
            Dict[int, Optional[datetime]]: Um dicionário onde a chave é o ID do membro e o valor é a data e hora da última atribuição confirmada antes de first_dt, ou None se não houver.
        """
        out: Dict[int, Optional[datetime]] = {}
        qs = (
            AssignmentRepository.confirmed_qs()
            .filter(
                Q(service__date__lt=first_dt.date()) |
                Q(service__date=first_dt.date(), service__time__lt=first_dt.time())
            )
            .select_related("service")
            .order_by("member_id", "-service__date", "-service__time")
        )
        seen: Set[int] = set()
        for a in qs:
            mid = int(a.member_id)
            if mid in seen:
                continue
            out[mid] = datetime.combine(a.service.date, a.service.time)
            seen.add(mid)

        for mid in MemberRepository.actives().values_list("id", flat=True):
            out.setdefault(int(mid), None)
        return out

    @classmethod
    def day_block_for_month(cls, year: int, month: int) -> Dict[date, Set[int]]:
        """Retorna um dicionário onde a chave é a data e o valor é um conjunto de IDs de membros que têm atribuições nessa data.

        Args:
            year (int): O ano a ser considerado.
            month (int): O mês a ser considerado.

        Returns:
            Dict[date, Set[int]]: Um dicionário onde a chave é a data e o valor é um conjunto de IDs de membros que têm atribuições nessa data.
        """
        block: Dict[date, Set[int]] = defaultdict(set)
        qs = AssignmentRepository.month_confirmed(year, month)
        for mid, d in qs.values_list("member_id", "service__date"):
            block[d].add(int(mid))
        return block

# ==========================================================
# Projeções auxiliares (úteis pro ranking/sugestão)
# ==========================================================
@dataclass(frozen=True)
class LastBefore:
    """Representa a última atribuição confirmada antes de uma determinada data/hora."""
    member_id: int
    last_dt: Optional[datetime]


class ProjectionRepository:
    """Repositório para operações relacionadas a projeções."""

    @classmethod
    def days_since_last_for_service(cls, member: Member, s: Service) -> Tuple[int, Optional[datetime]]:
        """Retorna o número de dias desde a última atribuição confirmada para um serviço específico.

        Args:
            member (Member): O membro para o qual verificar a última atribuição.
            s (Service): O serviço para o qual verificar a última atribuição.

        Returns:
            Tuple[int, Optional[datetime]]: O número de dias desde a última atribuição e a data/hora da última atribuição, se existir.
        """
        last = AssignmentRepository.last_confirmed_before(member, s.date, s.time)
        if not last:
            return (365, None)
        last_dt = datetime.combine(last.service.date, last.service.time)
        days = (s.date - last.service.date).days
        return (max(days, 0), last_dt)

    @classmethod
    def month_services_with_prefetch(cls, year: int, month: int, include_extra: bool = True) -> List[Service]:
        """Retorna uma lista de serviços do mês, já com prefetch de atribuições para membros.

        Args:
            year (int): O ano a ser considerado.
            month (int): O mês a ser considerado.
            include_extra (bool, optional): Se deve incluir serviços extras. Defaults to True.

        Returns:
            List[Service]: Uma lista de serviços do mês, já com prefetch de atribuições para membros.
        """
        return list(ServiceRepository.month_services(year, month, include_extra=include_extra))

    @classmethod
    def confirmed_month_sorted(cls, year: int, month: int) -> List[Tuple[datetime, int]]:
        """Retorna uma lista de tuplas (data/hora, id do membro) dos serviços confirmados no mês, ordenados por data/hora.

        Args:
            year (int): O ano a ser considerado.
            month (int): O mês a ser considerado.

        Returns:
            List[Tuple[datetime, int]]: Uma lista de tuplas (data/hora, id do membro) dos serviços confirmados no mês, ordenados por data/hora.
        """
        items: List[Tuple[datetime, int]] = []
        for mid, d, t in AssignmentRepository.month_confirmed(year, month)\
                                       .values_list("member_id", "service__date", "service__time"):
            items.append((datetime.combine(d, t), int(mid)))
        items.sort(key=lambda x: x[0])
        return items
