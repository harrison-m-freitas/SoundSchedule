from __future__ import annotations

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


SCHED_APP = "scheduling"

COORDINATOR_PERMS = {
    # Member
    "view_member", "add_member", "change_member",
    # Availability
    "view_availability", "add_availability", "change_availability",
    # Service
    "view_service", "add_service", "change_service", "delete_service",
    # Assignment
    "view_assignment", "add_assignment", "change_assignment", "delete_assignment",
    # ScheduleMonth (somente leitura)
    "view_schedulemonth",
    # AuditLog (somente leitura)
    "view_auditlog",
}

OPERATOR_PERMS = {
    # Leituras gerais
    "view_member", "view_availability", "view_service", "view_assignment",
    "view_schedulemonth",
    # Pode confirmar/substituir (change) assignments
    "change_assignment",
}


class Command(BaseCommand):
    help = "Create/Sync RBAC roles: Admin, Coordinator, Operator"

    def handle(self, *args, **kwargs):
        admin, _ = Group.objects.get_or_create(name="Admin")
        coord, _ = Group.objects.get_or_create(name="Coordinator")
        oper, _ = Group.objects.get_or_create(name="Operator")

        # ===== Admin: recebe TODAS as permissões =====
        all_perms = Permission.objects.all()
        admin.permissions.set(all_perms)
        self.stdout.write(self.style.SUCCESS(f"[Admin] total perms: {all_perms.count()}"))

        # ===== Coordinator: permissões do app scheduling conforme lista =====
        coord_perms = Permission.objects.filter(
            content_type__app_label=SCHED_APP,
            codename__in=COORDINATOR_PERMS,
        )
        coord.permissions.set(coord_perms)
        missing_coord = COORDINATOR_PERMS - set(coord_perms.values_list("codename", flat=True))
        self.stdout.write(self.style.SUCCESS(f"[Coordinator] applied perms: {coord_perms.count()}"))
        if missing_coord:
            self.stdout.write(
                self.style.WARNING(f"[Coordinator] missing codenames (confira migrações/models): {sorted(missing_coord)}")
            )

        # ===== Operator: leitura + change_assignment =====
        oper_perms = Permission.objects.filter(
            content_type__app_label=SCHED_APP,
            codename__in=OPERATOR_PERMS,
        )
        oper.permissions.set(oper_perms)
        missing_oper = OPERATOR_PERMS - set(oper_perms.values_list("codename", flat=True))
        self.stdout.write(self.style.SUCCESS(f"[Operator] applied perms: {oper_perms.count()}"))
        if missing_oper:
            self.stdout.write(
                self.style.WARNING(f"[Operator] missing codenames (confira migrações/models): {sorted(missing_oper)}")
            )

        self.stdout.write(self.style.SUCCESS("Roles created/updated."))
