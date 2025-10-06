from __future__ import annotations

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings

from scheduling.domain.models import Member, Availability, ShiftChoices

DEFAULT_NAMES = [
    "Vitor", "Gabriel B", "Euler", "Gabriel R", "Davi F",
    "Lucas", "Guilherme", "Harrison", "Rodrigo R", "David",
]

class Command(BaseCommand):
    help = "Seed demo data (admin + membros + disponibilidade domingo manhã/noite). Idempotente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=getattr(settings, "DEFAULT_MONTHLY_LIMIT", 2),
            help="Limite mensal por membro (default: settings.DEFAULT_MONTHLY_LIMIT).",
        )
        parser.add_argument(
            "--names",
            type=str,
            help="Lista de nomes separada por vírgula. Ex.: 'Ana,Beto,Caio'. "
                 "Se omitido, usa uma lista padrão.",
        )
        parser.add_argument(
            "--admin-user",
            type=str,
            default="admin",
            help="Username do superusuário demo (default: admin).",
        )
        parser.add_argument(
            "--admin-email",
            type=str,
            default="admin@example.com",
            help="Email do superusuário demo (default: admin@example.com).",
        )
        parser.add_argument(
            "--admin-pass",
            type=str,
            default="admin",
            help="Senha do superusuário demo (default: admin).",
        )

    def handle(self, *args, **kwargs):
        limit = kwargs["limit"]
        names_arg = kwargs.get("names")
        admin_user = kwargs["admin_user"]
        admin_email = kwargs["admin_email"]
        admin_pass = kwargs["admin_pass"]


        if not User.objects.filter(username=admin_user).exists():
            User.objects.create_superuser(admin_user, admin_email, admin_pass)
            self.stdout.write(self.style.SUCCESS(f"Created superuser {admin_user}:{admin_pass}"))
        else:
            self.stdout.write(self.style.WARNING(f"Superuser {admin_user} already exists."))

        if names_arg:
            names = [n.strip() for n in names_arg.split(",") if n.strip()]
        else:
            names = DEFAULT_NAMES

        created_count = 0
        updated_count = 0

        for n in names:
            m, created = Member.objects.get_or_create(
                name=n,
                defaults={"active": True, "monthly_limit": limit}
            )
            if created:
                created_count += 1
            else:
                to_update = []
                if m.monthly_limit != limit:
                    m.monthly_limit = limit
                    to_update.append("monthly_limit")
                if not m.active:
                    m.active = True
                    to_update.append("active")
                if to_update:
                    m.save(update_fields=to_update)
                    updated_count += 1

            Availability.objects.get_or_create(
                member=m, weekday=6, shift=ShiftChoices.MORNING,
                defaults={"active": True},
            )
            Availability.objects.get_or_create(
                member=m, weekday=6, shift=ShiftChoices.EVENING,
                defaults={"active": True},
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seed completed. members: created={created_count}, updated={updated_count}, "
            f"limit={limit}, total={Member.objects.count()}."
        ))
