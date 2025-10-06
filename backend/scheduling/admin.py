from __future__ import annotations

from datetime import date
from django.contrib import admin
from django.db.models import Q, Count

from scheduling.domain.models import (
    Member,
    Availability,
    Service,
    Assignment,
    ScheduleMonth,
    AuditLog,
)

# =========================
# Filtros utilitários
# =========================

class ServiceMonthFilter(admin.SimpleListFilter):
    title = "Mês/Ano"
    parameter_name = "ym"

    def lookups(self, request, model_admin):
        pairs = (
            Service.objects
            .values_list("date__year", "date__month")
            .distinct()
            .order_by("date__year", "date__month")
        )
        return [(f"{y}-{m}", f"{m:02d}/{y}") for (y, m) in pairs]

    def queryset(self, request, qs):
        val = self.value()
        if not val:
            return qs
        y, m = val.split("-")
        return qs.filter(date__year=int(y), date__month=int(m))

class ShiftFilter(admin.SimpleListFilter):
    title = "Turno"
    parameter_name = "shift"

    def lookups(self, request, model_admin):
        return [("morning", "Manhã"), ("evening", "Noite")]

    def queryset(self, request, qs):
        v = self.value()
        if v == "morning":
            return qs.filter(time__hour__lt=12)
        elif v == "evening":
            return qs.filter(time__hour__gte=12)
        return qs

# =========================
# Inlines
# =========================

class AvailabilityInline(admin.TabularInline):
    model = Availability
    extra = 0
    fields = ("weekday", "shift", "active")
    classes = ("collapse",)

class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    fields = ("member", "status", "created_by", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("member",)
    classes = ("collapse",)

# =========================
# Member
# =========================

@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "nickname",
        "active",
        "last_served_at",
        "monthly_limit",
        "email",
        "phone",
    )
    list_filter = ("active",)
    search_fields = ("name", "nickname", "email", "phone")
    ordering = ("name",)
    list_per_page = 50
    inlines = (AvailabilityInline,)

    actions = ["activate_members", "deactivate_members"]

    @admin.action(description="Ativar membros selecionados")
    def activate_members(self, request, qs):
        qs.update(active=True)

    @admin.action(description="Desativar membros selecionados")
    def deactivate_members(self, request, qs):
        qs.update(active=False)

# =========================
# Availability
# =========================

@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ("member", "weekday", "shift", "active")
    list_filter = ("weekday", "shift", "active")
    search_fields = ("member__name", "member__nickname")
    autocomplete_fields = ("member",)
    list_per_page = 50

# =========================
# Service
# =========================

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("date", "time", "type", "label", "confirmed_count", "suggested_count", "shift_display")
    list_filter = ("type", ServiceMonthFilter, ShiftFilter)
    search_fields = ("date", "label")
    date_hierarchy = "date"
    ordering = ("-date", "-time")
    list_per_page = 50
    inlines = (AssignmentInline,)

    @admin.display(description="Confirmados")
    def confirmed_count(self, obj: Service) -> int:
        return obj.assignments.filter(status="confirmed").count()

    @admin.display(description="Sugeridos")
    def suggested_count(self, obj: Service) -> int:
        return obj.assignments.filter(status="suggested").count()

    @admin.display(description="Turno")
    def shift_display(self, obj: Service) -> str:
        return "Manhã" if obj.time.hour < 12 else "Noite"

# =========================
# Assignment
# =========================

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("service", "service_date", "service_time", "member", "status", "created_at", "created_by")
    list_filter = ("status", "service__type", ServiceMonthFilter)
    search_fields = ("service__date", "member__name", "member__nickname")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("service", "member", "created_by")
    autocomplete_fields = ("service", "member", "created_by")
    list_per_page = 50

    actions = ["mark_confirmed", "mark_suggested", "mark_replaced"]

    @admin.display(description="Data")
    def service_date(self, obj: Assignment):
        return obj.service.date

    @admin.display(description="Hora")
    def service_time(self, obj: Assignment):
        return obj.service.time

    @admin.action(description="Marcar como CONFIRMADO")
    def mark_confirmed(self, request, qs):
        qs.update(status="confirmed")

    @admin.action(description="Marcar como SUGERIDO")
    def mark_suggested(self, request, qs):
        qs.update(status="suggested")

    @admin.action(description="Marcar como SUBSTITUÍDO")
    def mark_replaced(self, request, qs):
        qs.update(status="replaced")

# =========================
# ScheduleMonth
# =========================

@admin.register(ScheduleMonth)
class ScheduleMonthAdmin(admin.ModelAdmin):
    list_display = ("year", "month", "generated_at", "generated_by")
    list_filter = ("year", "month")
    search_fields = ("year", "month")
    readonly_fields = ("generated_at",)
    ordering = ("-year", "-month")
    list_per_page = 50

# =========================
# AuditLog
# =========================

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "table", "record_id", "created_at", "author")
    list_filter = ("table", "action")
    search_fields = ("table", "record_id", "author__username")
    readonly_fields = ("action", "table", "record_id", "before", "after", "author", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
