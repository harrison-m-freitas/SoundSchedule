from __future__ import annotations

from typing import Optional
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from scheduling.tasks import (
    monthly_draft_generation,
    daily_reminder,
    notify_month_generated,
)


class Command(BaseCommand):
    help = (
        "Dispara tasks do Celery manualmente para testes.\n"
        "Use --sync para executar a task no mesmo processo (sem Celery)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "name",
            choices=["monthly_draft", "daily_reminder", "notify_month", "all"],
            help="Nome da task a enfileirar/executar.",
        )
        parser.add_argument("--year", type=int, help="Ano (para notify_month).")
        parser.add_argument("--month", type=int, help="Mês (1-12) para notify_month.")
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Executa a task de forma síncrona (sem broker/worker).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=10,
            help="Segundos para aguardar o resultado (modo assíncrono).",
        )

    # ====== Helpers ======

    def _run_sync(self, name: str, *, year: Optional[int], month: Optional[int]) -> None:
        """Executa a task diretamente no processo atual."""
        if name == "monthly_draft":
            result = monthly_draft_generation()
            self.stdout.write(self.style.SUCCESS(f"[sync] monthly_draft_generation → {result}"))
        elif name == "daily_reminder":
            result = daily_reminder()
            self.stdout.write(self.style.SUCCESS(f"[sync] daily_reminder → {result}"))
        elif name == "notify_month":
            now = timezone.localtime()
            y = year or now.year
            m = month or now.month
            result = notify_month_generated(y, m)
            self.stdout.write(self.style.SUCCESS(f"[sync] notify_month_generated({y},{m}) → {result}"))
        elif name == "all":
            # Executa todas em sequência
            self._run_sync("monthly_draft", year=year, month=month)
            self._run_sync("daily_reminder", year=year, month=month)
            self._run_sync("notify_month", year=year, month=month)
        else:
            raise CommandError(f"Task desconhecida: {name}")

    def _enqueue(self, name: str, *, year: Optional[int], month: Optional[int], timeout: int) -> None:
        """Enfileira via Celery e tenta obter resultado rapidamente (se disponível)."""
        try:
            if name == "monthly_draft":
                res = monthly_draft_generation.delay()
                self.stdout.write(self.style.SUCCESS(f"[async] enfileirada monthly_draft_generation: {res.id}"))
            elif name == "daily_reminder":
                res = daily_reminder.delay()
                self.stdout.write(self.style.SUCCESS(f"[async] enfileirada daily_reminder: {res.id}"))
            elif name == "notify_month":
                now = timezone.localtime()
                y = year or now.year
                m = month or now.month
                res = notify_month_generated.delay(y, m)
                self.stdout.write(self.style.SUCCESS(f"[async] enfileirada notify_month_generated({y},{m}): {res.id}"))
            elif name == "all":
                # Enfileira as três
                self._enqueue("monthly_draft", year=year, month=month, timeout=timeout)
                self._enqueue("daily_reminder", year=year, month=month, timeout=timeout)
                self._enqueue("notify_month", year=year, month=month, timeout=timeout)
                return
            else:
                raise CommandError(f"Task desconhecida: {name}")

            # Opcional: tentar pegar o resultado rapidamente
            try:
                out = res.get(timeout=timeout)
                self.stdout.write(self.style.HTTP_INFO(f"[async] result {res.id} → {out!r}"))
            except Exception:
                # Sem problema: o worker pode não ter processado ainda.
                pass

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Falha ao enfileirar '{name}': {e}"))
            self.stderr.write("Dica: use --sync para executar sem Celery.")
            raise SystemExit(2)

    # ====== Entry point ======

    def handle(self, *args, **opts):
        name: str = opts["name"]
        year: Optional[int] = opts.get("year")
        month: Optional[int] = opts.get("month")
        sync: bool = bool(opts.get("sync"))
        timeout: int = int(opts.get("timeout") or 10)

        if name == "monthly_draft":
            res = monthly_draft_generation.delay()
            self.stdout.write(self.style.SUCCESS(f"Enfileirada monthly_draft_generation: {res.id}"))
        elif name == "daily_reminder":
            res = daily_reminder.delay()
            self.stdout.write(self.style.SUCCESS(f"Enfileirada daily_reminder: {res.id}"))
        elif name == "notify_month":
            now = timezone.localtime()
            year = year or now.year
            month = month or now.month
            res = notify_month_generated.delay(year, month)
            self.stdout.write(self.style.SUCCESS(f"Enfileirada notify_month_generated({year},{month}): {res.id}"))
