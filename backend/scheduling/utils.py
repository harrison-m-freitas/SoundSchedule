from typing import Tuple, Any
import json

from django.http import HttpRequest
from django.utils import timezone
from django.conf import settings

# =========================
# Helpers
# =========================

def _get_ym_from_request(request: HttpRequest, default_today: bool = True) -> Tuple[int, int, str | None]:
    """Extrai ano e mês da query string."""
    if hasattr(request, "query_params"):
        qp = request.query_params
        dp = getattr(request, "data", {}) or {}
    else:
        qp = getattr(request, "GET", {}) or {}
        dp = getattr(request, "GET", {}) or {}
        if not dp and request.META.get("CONTENT_TYPE", "").startswith("application/json"):
            try:
                dp = json.loads((request.body or b"{}").decode("utf-8")) or {}
            except Exception:
                dp = {}
    y = qp.get("year") or qp.get("ano") or dp.get("year") or dp.get("ano")
    m = qp.get("month") or qp.get("mes") or dp.get("month") or dp.get("mes")

    if y is None or m is None:
        if not default_today:
            return None, None, "Parâmetros 'year/ano' e 'month/mes' são obrigatórios."
        today = timezone.localdate()
        y = y or today.year
        m = m or today.month
    try:
        y = int(y)
        m = int(m)
    except Exception:
        return None, None, "Parâmetros 'year' e 'month' devem ser números inteiros."
    if not (1 <= m <= 12):
        return None, None, "Parâmetro 'month' deve estar entre 1 e 12."
    return y, m, None

def _get_setting(name: str, default: Any = None) -> Any:
    """Obtém uma configuração do Django settings com um valor padrão."""
    return getattr(settings, name, default)
