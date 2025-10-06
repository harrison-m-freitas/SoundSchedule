from __future__ import annotations

from typing import Optional

from django import template
from django.utils.html import mark_safe, format_html
from django.utils.safestring import SafeString

register = template.Library()

@register.filter(name="trim")
def trim(value: Optional[str]) -> str:
    """
    Remove espaços em branco no início e no fim.
    Uso: {{ texto|trim }}
    """
    if value is None:
        return ""
    return str(value).strip()

@register.filter(name="ltrim")
def ltrim(value: Optional[str]) -> str:
    """Remove espaços no início."""
    if value is None:
        return ""
    return str(value).lstrip()

@register.filter(name="rtrim")
def rtrim(value: Optional[str]) -> str:
    """Remove espaços no fim."""
    if value is None:
        return ""
    return str(value).rstrip()

@register.filter(name="truncate_middle")
def truncate_middle(value: Optional[str], max_len: int = 20) -> str:
    """
    Corta mantendo início e fim: "abcdefghij" -> "abc…hij".
    Uso: {{ texto|truncate_middle:30 }}
    """
    if not value:
        return ""
    s = str(value)
    if len(s) <= max_len or max_len < 5:
        return s
    half = (max_len - 1) // 2
    return s[:half] + "…" + s[-half:]

@register.filter(name="add_class", is_safe=True)
def add_class(field, css_class: str) -> SafeString:
    """
    Adiciona classe a um BoundField (útil em forms).
    Uso: {{ form.campo|add_class:"w-full" }}
    """
    # field já rende HTML; como apenas injeta atributo, marcamos como seguro
    return mark_safe(str(field).replace('class="', f'class="{css_class} '))  # simples/efetivo

@register.simple_tag
def concat(*args) -> str:
    """
    Concatena strings com segurança de escape padrão do template (ver Sessão 4).
    Uso: {% concat a b c as out %}{{ out }}
    """
    return "".join("" if a is None else str(a) for a in args)

@register.simple_tag(takes_context=True)
def strong(context, text: str) -> str:
    text = "" if text is None else text
    return format_html("<strong>{}</strong>", text)
