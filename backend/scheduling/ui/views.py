from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Set, Tuple, Any, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.db import transaction
from django.template.loader import render_to_string

from scheduling.domain.models import Assignment, AssignmentStatus, Member, Service
from scheduling.domain.forms import MemberForm, ServiceForm
from scheduling.domain.repositories import MemberRepository, ServiceRepository
from scheduling.services.calendar import ensure_month_services
from scheduling.services.suggestion import suggest_for_month, ranking_monthly_candidates, resuggest_month
from scheduling.utils import _get_ym_from_request, _get_setting

# =========================
# HTMX Response Builder
# =========================

@dataclass
class HTMXUpdate:
    """Representa uma atualização fora de banda (OOB) para HTMX."""
    element_id: str
    content: str
    swap_mode: str = "innerHTML"

class HTMXResponseBuilder:
    """Construtor para respostas HTTP compatíveis com HTMX."""
    def __init__(self, main_html: str = ""):
        self.main_html = main_html
        self.oob_updates: List[HTMXUpdate] = []
        self.triggers: List[str] = []

    def add_oob_update(self, element_id: str, content: str, swap_mode: str = "innerHTML") -> None:
        self.oob_updates.append(HTMXUpdate(element_id, content, swap_mode))
        return self

    def add_trigger(self, event_name: str) -> None:
        self.triggers.append(event_name)
        return self

    def add_service_card_update(self, service_id: int, request: HttpRequest | None = None) -> None:
        html = _render_service_card_html(service_id, request=request)
        self.add_oob_update(f"service-{service_id}", html)
        return self

    def add_ranking_loader(self, year: int, month: int) -> None:
        url = reverse("ranking_candidates") + f"?year={year}&month={month}"
        loader_html = (
            f'<div id="ranking-monthly-loader" '
            f'     hx-get="{url}" '
            f'     hx-trigger="load" '
            f'     hx-swap="none" '
            f'     hx-swap-oob="true"></div>'
        )
        self.add_oob_update("ranking-monthly-loader", loader_html, swap_mode="outerHTML")
        return self

    def build(self) -> HttpResponse:
        oob_html_parts = []
        for update in self.oob_updates:
            if update.swap_mode == "outerHTML":
                oob_html_parts.append(update.content)
            else:
                oob_html_parts.append(
                    f'<div id="{update.element_id}" hx-swap-oob="true">{update.content}</div>'
                )
        response = HttpResponse(self.main_html + "".join(oob_html_parts))
        if self.triggers:
            response["HX-Trigger-After-Swap"] = ", ".join(self.triggers)
        return response

# =========================
# Service Layer
# =========================

class AssignmentService:
    """Serviço de negócio para operações de atribuição."""

    @staticmethod
    def confirm(assignment_id: int, user: User | None = None) -> Assignment:
        """Confirma uma atribuição."""
        assignment = get_object_or_404(Assignment, id=assignment_id)
        assignment.status = "confirmed"
        assignment.save(update_fields=["status"])
        return assignment

    @staticmethod
    @transaction.atomic
    def swap_member(assignment_id: int, new_member_id: int, user: User | None = None) -> Tuple[Assignment, Set[int]]:
        """Substitui o membro de uma atribuição e reprocessa sugestões."""
        assignment = get_object_or_404(Assignment, id=assignment_id)
        new_member = get_object_or_404(Member, id=new_member_id)
        assignment.member = new_member
        assignment.status = "replaced"
        assignment.save()

        year, month = assignment.service.date.year, assignment.service.date.month
        changed_ids = resuggest_month(year, month, user=user, from_service=assignment.service)
        return assignment, changed_ids

    @staticmethod
    def add_or_update(service_id: int, member_id: int, user: User | None = None) -> Tuple[Assignment, Set[int]]:
        """Adiciona ou atualiza uma atribuição e reprocessa sugestões."""
        service = get_object_or_404(Service, id=service_id)
        member = get_object_or_404(Member, id=member_id)

        assignment, created = Assignment.objects.get_or_create(
            service=service,
            member=member,
            defaults={"status": AssignmentStatus.CONFIRMED, "created_by": user},
        )

        if not created and assignment.status != AssignmentStatus.CONFIRMED:
            assignment.status = AssignmentStatus.CONFIRMED
            assignment.save(update_fields=["status"])

        resuggest_when_add = assignment.service.type != "Extra" and _get_setting("RESUGGEST_ON_ADD", False)
        if resuggest_when_add:
            changed_ids = resuggest_month(service.date.year, service.date.month, user=user, from_service=service)
        return assignment, changed_ids

# =========================
# Helper Functions
# =========================

def _render_service_card_html(service_id: int, request: HttpRequest | None = None) -> str:
    """Renderiza o HTML de um card de serviço."""
    service = Service.objects.filter(id=service_id).prefetch_related(
        "assignments", "assignments__member"
    ).first()
    if not service:
        return ""
    members = MemberRepository.actives()
    return render_to_string(
        "partials/service_card.html",
        {"s": service, "members": members},
        request=request,
    )

def _get_calendar_referrer(request: HttpRequest) -> str:
    """Obtém URL de referência ou padrão do calendário."""
    return request.META.get("HTTP_REFERRER") or reverse("calendar")

def _build_service_card_response(
    service_id: int,
    updated_service_ids: Optional[Iterable[int]] = None,
    request: HttpRequest | None = None,
) -> HttpResponse:
    """Constrói resposta HTMX com card principal e atualizações OOB."""
    main_html = _render_service_card_html(service_id, request=request)
    builder = HTMXResponseBuilder(main_html)
    if updated_service_ids:
        for sid in updated_service_ids:
            if sid != service_id:
                builder.add_service_card_update(sid, request=request)
    service = Service.objects.filter(id=service_id).values("date").first()
    if service:
        year, month = service["date"].year, service["date"].month
        builder.add_ranking_loader(year, month)
    return builder.build()

# =========================
# Views
# =========================

@login_required
def month_view(request: HttpRequest) -> HttpResponse:
    """Exibe a visão mensal do calendário."""
    year, month, err = _get_ym_from_request(request)
    if err:
        messages.error(request, err)
        return redirect(reverse("calendar"))
    ensure_month_services(year, month)
    services = ServiceRepository.month_services(year, month)
    members = MemberRepository.actives()
    grid: Dict[int, Dict[str, Any]] = {}
    for service in services:
        day = service.date.day
        grid.setdefault(day, {"services": []})["services"].append(service)
    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)
    month_label = date_format(date(year, month, 1), "F")
    context = {
        "year": year,
        "month": month,
        "month_name": month_label,
        "days": sorted(grid.items(), key=lambda x: x[0]),
        "members": members,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "months_select":  [(i, date_format(date(2000, i, 1), 'F')) for i in range(1, 13)],
        "years_select": [y for y in range(date.today().year - 5, date.today().year + 6)],
        "today_year": date.today().year,
        "today_month": date.today().month,
    }
    return render(request, "calendar.html", context)

@login_required
@permission_required("scheduling.change_assignment", raise_exception=True)
def confirm_assignment(request: HttpRequest, assignment_id: int) -> HttpResponse:
    """Confirma uma atribuição de serviço."""
    assignment = AssignmentService.confirm(assignment_id, user=request.user)
    if request.headers.get("HX-Request"):
        return _build_service_card_response(assignment.service_id, request=request)
    messages.success(request, f"{assignment.member} confirmado em {assignment.service}")
    return redirect(_get_calendar_referrer(request))

@login_required
@permission_required("scheduling.change_assignment", raise_exception=True)
@transaction.atomic
def swap_assignment(request: HttpRequest, assignment_id: int) -> HttpResponse:
    """Substitui o membro em uma atribuição."""
    member_id = int(request.POST.get("member_id"))
    assignment, changed_ids = AssignmentService.swap_member(
        assignment_id, member_id, user=request.user
    )
    if request.headers.get("HX-Request"):
        return _build_service_card_response(assignment.service_id, changed_ids, request=request)
    messages.success(request, "Substituição realizada.")
    return redirect(_get_calendar_referrer(request))

@login_required
@permission_required("scheduling.add_assignment", raise_exception=True)
@require_POST
def assignment_add(request: HttpRequest, service_id: int) -> HttpResponse:
    """Adiciona uma nova atribuição de serviço."""
    member_id = int(request.POST.get("member_id"))
    assignment, changed_ids = AssignmentService.add_or_update(
        service_id=service_id, member_id=member_id, user=request.user
    )
    if request.headers.get("HX-Request"):
        return _build_service_card_response(assignment.service_id, changed_ids, request=request)
    return redirect(_get_calendar_referrer(request))

@login_required
@permission_required("scheduling.add_assignment", raise_exception=True)
def generate_schedule_view(request: HttpRequest) -> HttpResponse:
    """Gera sugestões automáticas para o mês."""
    year, month, err = _get_ym_from_request(request)
    if err:
        messages.error(request, err)
        return redirect(reverse("calendar"))

    _, count = suggest_for_month(year, month, user=request.user)

    messages.info(request, f"Sugestões geradas: {count} slots.")
    return redirect(reverse("calendar") + f"?year={year}&month={month}")

@login_required
def ranking_candidates_view(request: HttpRequest) -> HttpResponse:
    """Retorna o ranking de candidatos para cada serviço do mês (HTMX)."""
    year = int(request.GET.get("year"))
    month = int(request.GET.get("month"))
    if not year or not month:
        return HttpResponse("Year and Month are required.", status=400)
    services = ServiceRepository.month_services(year, month)
    if not services:
        return HttpResponse("No services found for the specified month.", status=404)
    ranking_map = ranking_monthly_candidates(year, month, limit=5)
    parts: List[str] = []
    for service in services:
        if service.type == "Extra" or service.assignments.filter(status="confirmed").exists():
            parts.append(f'<div id="rank-svc-{service.id}" hx-swap-oob="true"></div>')
            continue
        ranking = ranking_map.get(service.id, [])
        current_suggested_id = service.assignments.values_list("member_id", flat=True).first()
        inner = render_to_string("partials/ranking_candidates_panel.html", {
            "ranking": ranking,
            "current_suggested_id": current_suggested_id,
            "service": service,
        })
        parts.append(f'<div id="rank-svc-{service.id}" hx-swap-oob="true">{inner}</div>')
    return HttpResponse("".join(parts))

# =========================
# CRUD Views - Service
# =========================

@login_required
@permission_required("scheduling.add_service", raise_exception=True)
def service_create(request: HttpRequest) -> HttpResponse:
    """Cria um novo serviço."""
    if request.method == "POST":
        form = ServiceForm(request.POST)
        if form.is_valid():
            service = form.save()
            messages.success(request, f"Serviço '{service}' criado.")
            year, month = service.date.year, service.date.month
            return redirect(reverse("calendar") + f"?year={year}&month={month}")
    else:
        form = ServiceForm(initial={"type": "Extra"})

    return render(request, "service_form.html", {"form": form})

@login_required
@permission_required("scheduling.change_service", raise_exception=True)
def service_edit(request: HttpRequest, service_id: int) -> HttpResponse:
    """Edita um serviço existente."""
    service = get_object_or_404(Service, id=service_id)

    if request.method == "POST":
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            service = form.save()
            messages.success(request, f"Serviço '{service}' atualizado.")
            year, month = service.date.year, service.date.month
            return redirect(reverse("calendar") + f"?year={year}&month={month}")
    else:
        form = ServiceForm(instance=service)

    return render(request, "service_form.html", {"form": form, "service": service})

@login_required
@permission_required("scheduling.delete_service", raise_exception=True)
def service_delete(request: HttpRequest, service_id: int) -> HttpResponse:
    """Exclui um serviço existente."""
    service = get_object_or_404(Service, id=service_id)
    year, month = service.date.year, service.date.month
    service.delete()

    messages.success(request, f"Serviço '{service}' excluído.")
    return redirect(reverse("calendar") + f"?year={year}&month={month}")

# =========================
# CRUD Views - Member
# =========================

@login_required
@permission_required("scheduling.view_member", raise_exception=True)
def members_list(request: HttpRequest) -> HttpResponse:
    """Exibe a lista de membros."""
    members = MemberRepository.all_members()
    return render(request, "members_list.html", {"members": members})

@login_required
@permission_required("scheduling.change_member", raise_exception=True)
def member_edit(request: HttpRequest, member_id: int) -> HttpResponse:
    """Edita um membro existente."""
    member = get_object_or_404(Member, id=member_id)
    if request.method == "POST":
        form = MemberForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, "Membro atualizado.")
            return redirect("members_list")
    else:
        form = MemberForm(instance=member)

    return render(request, "member_form.html", {"form": form, "member": member})
