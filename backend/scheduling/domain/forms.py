from __future__ import annotations

from typing import Optional

from django import forms

from scheduling.domain.models import Service, Member, Availability, ShiftChoices
from scheduling.utils import _get_setting

# ===== Utilidades simples =====

WEEKDAY_CHOICES = [
    (0, "Segunda"),
    (1, "Terça"),
    (2, "Quarta"),
    (3, "Quinta"),
    (4, "Sexta"),
    (5, "Sábado"),
    (6, "Domingo"),
]

BASE_CLS_INPUT = "block w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"

# ===== Service =====

class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["date", "time", "type", "label"]
        widgets = {
            "date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": BASE_CLS_INPUT, "required": True}
            ),
            "time": forms.TimeInput(
                format="%H:%M",
                attrs={"type": "time", "class": BASE_CLS_INPUT, "required": True,  'x-ref': 'time'}
            ),
            'type': forms.Select(attrs={"class": BASE_CLS_INPUT}),
            "label": forms.TextInput(attrs={
                "placeholder": "Ex.: Culto especial, Ceia, Conferência...",
                "class": BASE_CLS_INPUT
            }),
        }
        help_texts = {
            "type": "Selecione o tipo do serviço.",
            "label": "Rótulo opcional para diferenciar (aparece nas exportações).",
        }

    def clean(self):
        data = super().clean()
        d = data.get("date")
        t = data.get("time")
        if d and t:
            qs = Service.objects.filter(date=d, time=t).exclude(pk=self.instance.pk or 0)
            if qs.exists():
                raise forms.ValidationError("Já existe um serviço cadastrado para esta data e hora.")
        return data

    def clean_label(self) -> Optional[str]:
        label = self.cleaned_data.get("label")
        return (label or "").strip() or None


# ===== Member =====

class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["name", "nickname", "email", "phone", "active", "monthly_limit", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"autofocus": True , "class": BASE_CLS_INPUT}),
            "nickname": forms.TextInput(attrs={"class": BASE_CLS_INPUT}),
            "email": forms.EmailInput(attrs={"class": BASE_CLS_INPUT}),
            "phone": forms.TextInput(attrs={"class": BASE_CLS_INPUT, "placeholder": "(31) 9xxxx-xxxx"}),
            "active": forms.CheckboxInput(attrs={"class": "sr-only peer"}),
            "monthly_limit": forms.NumberInput(attrs={"class": BASE_CLS_INPUT + " w-24 text-center", "min": 1, "step": 1, 'x-ref': 'limit'}),
            "notes": forms.Textarea(attrs={"class": BASE_CLS_INPUT, "rows": 3, "placeholder": "Observações internas (ex.: preferências, restrições, etc.)"}),
        }
        help_texts = {
            "monthly_limit": "Limite de confirmações por mês (≥ 1). Padrão: "
                             f"{_get_setting('DEFAULT_MONTHLY_LIMIT', 2)}",
        }

    def clean_name(self) -> str:
        return (self.cleaned_data.get("name") or "").strip()

    def clean_nickname(self) -> Optional[str]:
        nick = self.cleaned_data.get("nickname")
        return (nick or "").strip() or None

    def clean_email(self) -> Optional[str]:
        email = self.cleaned_data.get("email")
        return (email or "").strip().lower() or None

    def clean_phone(self) -> Optional[str]:
        phone = self.cleaned_data.get("phone")
        return (phone or "").strip() or None

    def clean_monthly_limit(self) -> int:
        val = int(self.cleaned_data.get("monthly_limit") or 0)
        if val < 1:
            raise forms.ValidationError("O limite mensal deve ser pelo menos 1.")
        return val


# ===== Availability (útil para telas de manutenção e admin custom) =====

class AvailabilityForm(forms.ModelForm):
    weekday = forms.ChoiceField(choices=WEEKDAY_CHOICES)

    class Meta:
        model = Availability
        fields = ["member", "weekday", "shift", "active"]
        widgets = {
            "member": forms.Select(attrs={"data-autocomplete": "on"}),
            "shift": forms.Select(choices=ShiftChoices.choices),
        }
        help_texts = {
            "weekday": "0=Segunda ... 6=Domingo",
            "shift": "Turno de disponibilidade.",
        }

    def clean(self):
        data = super().clean()
        member = data.get("member")
        weekday = data.get("weekday")
        shift = data.get("shift")

        # Normaliza weekday vindo do ChoiceField (str -> int)
        if isinstance(weekday, str) and weekday.isdigit():
            weekday = int(weekday)
            data["weekday"] = weekday

        if member is not None and weekday is not None and shift:
            exists = (Availability.objects
                      .filter(member=member, weekday=weekday, shift=shift)
                      .exclude(pk=self.instance.pk or 0)
                      .exists())
            if exists:
                raise forms.ValidationError("Já existe uma disponibilidade para este membro neste dia/turno.")
        return data
