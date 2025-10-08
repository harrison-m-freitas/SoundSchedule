from __future__ import annotations
import threading
from typing import Optional, Any

from urllib.parse import quote, urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import resolve, Resolver404

_local = threading.local()

def get_current_user() -> Optional[Any]:
    """Retorna o usuário atual armazenado no thread-local, ou None se não houver."""
    return getattr(_local, "user", None)

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
        if getattr(request, "user", None) and not request.user.is_authenticated:
            return self.get_response(request)
        if any(path.startswith(e) for e in self.exempt):
            return self.get_response(request)
        if path.startswith(settings.STATIC_URL):
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
