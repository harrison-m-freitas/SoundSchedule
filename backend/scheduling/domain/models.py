from __future__ import annotations

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

# =========================
# Choices canônicos (clássico, legível e seguro)
# =========================

class ShiftChoices(models.TextChoices):
    MORNING = "morning", "Manhã"
    EVENING = "evening", "Noite"

class ServiceType(models.TextChoices):
    CULTO = "Culto", "Culto"
    EXTRA = "Extra", "Extra"

class AssignmentStatus(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmado"
    SUGGESTED = "suggested", "Sugerido"
    REPLACED = "replaced", "Substituído"

# =========================
# Modelos
# =========================

class Member(models.Model):
    """Representa um membro da equipe."""
    name = models.CharField(max_length=120, db_index=True)
    nickname = models.CharField(max_length=60, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    active = models.BooleanField(default=True, db_index=True)
    date_joined = models.DateField(blank=True, null=True)
    last_served_at = models.DateField(blank=True, null=True, db_index=True)
    monthly_limit = models.PositiveIntegerField(default=2, validators=[MinValueValidator(1)])
    notes = models.TextField(blank=True, null=True)
    user = models.OneToOneField(User, blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = "Membro"
        verbose_name_plural = "Membros"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["active"], name="member_active_idx"),
            models.Index(fields=["last_served_at"], name="member_last_served_idx"),
        ]

    def __str__(self):
        return self.nickname or self.name

class Availability(models.Model):
    """Representa a disponibilidade semanal de um membro."""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="availabilities")
    weekday = models.IntegerField(
        help_text="0=Seg ... 6=Domingo",
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        db_index=True,
    )
    shift = models.CharField(max_length=10, choices=ShiftChoices.choices, db_index=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Disponibilidade"
        verbose_name_plural = "Disponibilidades"
        constraints = [
            models.UniqueConstraint(
                fields=("member", "weekday", "shift"), name="uniq_availability_member_day_shift"
            ),
        ]
        indexes = [
            models.Index(fields=["member", "active"], name="availability_member_active_idx"),
            models.Index(fields=["weekday", "shift", "active"], name="availability_wsa_idx"),
        ]

    def __str__(self):
        return f"{self.member} {self.weekday} {self.shift}"

class Service(models.Model):
    """Representa um serviço (culto ou extra) em uma data e hora específicas."""
    date = models.DateField(db_index=True)
    time = models.TimeField(db_index=True)
    type = models.CharField(
        max_length=12, choices=ServiceType.choices, default=ServiceType.CULTO, db_index=True
    )
    label = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "Serviço"
        verbose_name_plural = "Serviços"
        ordering = ["date", "time"]
        constraints = [
            models.UniqueConstraint(fields=("date", "time"), name="uniq_service_date_time"),
        ]
        indexes = [
            models.Index(fields=["date", "time"], name="service_date_time_idx"),
            models.Index(fields=["type", "date"], name="service_type_date_idx"),
        ]

    def __str__(self):
        return f"{self.date} {self.time} {self.type}"

    @property
    def shift(self) -> str:
        """Deriva o turno a partir da hora (morning/evening) — útil para ranking."""
        return ShiftChoices.MORNING if self.time.hour < 12 else ShiftChoices.EVENING

class ScheduleMonth(models.Model):
    """Representa uma escala mensal gerada."""
    year = models.PositiveIntegerField(db_index=True)
    month = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], db_index=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Escala Mensal"
        verbose_name_plural = "Escalas Mensais"
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(fields=("year", "month"), name="uniq_schedule_month"),
        ]
        indexes = [
            models.Index(fields=["year", "month"], name="schedule_year_month_idx"),
        ]

    def __str__(self):
        return f"{self.year}-{self.month:02d}"

class Assignment(models.Model):
    """Representa a atribuição de um membro a um serviço."""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="assignments")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="assignments")
    status = models.CharField(
        max_length=12, choices=AssignmentStatus.choices, default=AssignmentStatus.SUGGESTED, db_index=True
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Atribuição"
        verbose_name_plural = "Atribuições"
        constraints = [
            models.UniqueConstraint(fields=("service", "member"), name="uniq_assignment_service_member"),
        ]
        indexes = [
            models.Index(fields=["service", "status"], name="assignment_service_status_idx"),
            models.Index(fields=["member", "status"], name="assignment_member_status_idx"),
            models.Index(fields=["status", "created_at"], name="assignment_status_created_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.service} -> {self.member} ({self.status})"

class AuditLog(models.Model):
    """Registra ações de criação, atualização e exclusão em outros modelos."""
    action = models.CharField(max_length=50, db_index=True)
    table = models.CharField(max_length=50, db_index=True)
    record_id = models.CharField(max_length=50)
    before = models.JSONField(blank=True, null=True)
    after = models.JSONField(blank=True, null=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        verbose_name = "Auditoria"
        verbose_name_plural = "Auditorias"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["table", "created_at"], name="audit_table_created_idx"),
            models.Index(fields=["action", "created_at"], name="audit_action_created_idx"),
        ]
        unique_together = ("table", "record_id", "created_at")

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} | {self.table}:{self.record_id} | {self.action}"
