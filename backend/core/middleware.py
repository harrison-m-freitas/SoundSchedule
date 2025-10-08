from __future__ import annotations
import threading
from typing import Optional, Any
import json
import logging
import uuid

from urllib.parse import quote, urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import resolve, Resolver404

_local = threading.local()

def get_current_user() -> Optional[Any]:
    """Retorna o usuário atual armazenado no thread-local, ou None se não houver."""
    return getattr(_local, "user", None)

def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

def _redact_mapping(data):
    SENSITIVE = {"password", "passwd", "senha", "token", "authorization", "csrfmiddlewaretoken"}
    out = {}
    try:
        items = (data or {}).items()
    except Exception:
        return {}
    for k, v in items:
        key = str(k).lower()
        if key in SENSITIVE:
            out[k] = "***redacted***"
        else:
            # evita objetos não serializáveis
            out[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
    return out


class CurrentUserMiddleware:
    """Armazena o request.user num thread-local para ser lido pelos signals/serviços."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        try:
            return self.get_response(request)
        finally:
            _local.user = None

class LoginRequiredMiddleware:
    """Redireciona usuários não autenticados para a página de login."""
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt = tuple(getattr(settings, "LOGIN_EXEMPT_PREFIXES", []))

    def __call__(self, request):
        path = request.path_info or "/"
        if path.startswith(getattr(settings, "STATIC_URL", "/static/")):
            return self.get_response(request)
        if path.startswith(getattr(settings, "MEDIA_URL", "/media/")):
            return self.get_response(request)
        if any(path.startswith(p) for p in self.exempt):
            return self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return self.get_response(request)
        login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
        next_param = quote(request.get_full_path() or "/")
        return redirect(f"{login_url}?next={next_param}")

class StrictSlashRedirectMiddleware:
    """Redireciona URLs sem barra final para a versão com barra final, se aplicável."""
    SAFE_METHODS = {"GET", "HEAD"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or "/"
        method = request.method.upper()

        if path != "/" and not path.endswith("/") and method in self.SAFE_METHODS:
            if path.startswith(getattr(settings, "STATIC_URL", "/static/")):
                return self.get_response(request)
            if path.startswith(getattr(settings, "MEDIA_URL", "/media/")):
                return self.get_response(request)

            try:
                resolve(path)
            except Resolver404:
                try:
                    resolve(f"{path}/")
                    q = request.META.get("QUERY_STRING", "")
                    suffix = f"?{q}" if q else ""
                    return redirect(f"{path}/{suffix}", permanent=True)
                except Resolver404:
                    pass
        return self.get_response(request)

class ErrorLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("django.request")

    def __call__(self, request):
        req_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request._request_id = req_id
        try:
            response = self.get_response(request)
        except Exception:
            self._log_exception(request)
            raise
        if getattr(response, "status_code", 200) >= 500:
            self._log_5xx(request, response)
        return response

    def _build_context(self, request):
        content_type = request.META.get("CONTENT_TYPE", "")
        body_excerpt = None

        if "application/json" in content_type:
            try:
                body_excerpt = (request.body or b"")[:2048].decode("utf-8", errors="replace")
            except Exception:
                body_excerpt = "<unavailable>"

        user = getattr(request, "user", None)
        username = (user.username or "<unavailable>") if user and user.is_authenticated else "Anonymous"

        return {
            "id": getattr(request, "_request_id", None),
            "method": request.method,
            "path": request.get_full_path(),
            "ip": _client_ip(request),
            "user": username,
            "ua": request.META.get("HTTP_USER_AGENT", ""),
            "referer": request.META.get("HTTP_REFERER", ""),
            "get": _redact_mapping(getattr(request, "GET", {})),
            "post": _redact_mapping(getattr(request, "POST", {})),
            "json_body_excerpt": body_excerpt,
        }

    def _log_exception(self, request):
        ctx = self._build_context(request)
        self.logger.error(
            "Unhandled exception | ctx=%s",
            json.dumps(ctx, ensure_ascii=False),
            exc_info=True,
        )

    def _log_5xx(self, request, response):
        ctx = self._build_context(request)
        ctx["status_code"] = getattr(response, "status_code", None)
        self.logger.error(
            "5xx response | ctx=%s",
            json.dumps(ctx, ensure_ascii=False),
        )
