from __future__ import annotations
import threading
from typing import Optional, Any

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
