from __future__ import annotations
from typing import Any, Dict, Iterable, Optional

from django.forms.models import model_to_dict
from django.contrib.auth.models import User

from core.middleware import get_current_user
from scheduling.domain.models import AuditLog

DEFAULT_EXCLUDE = {"id"}

def snapshot_instance(
    instance, *,
    include: Optional[Iterable[str]] = None,
    exclude: Iterable[str] = DEFAULT_EXCLUDE
) -> Dict[str, Any]:
    """Cria um snapshot do estado atual de um modelo Django.

    Args:
        instance (Django Model): A instância do modelo Django a ser capturada.
        include (Optional[Iterable[str]], optional): Campos a serem incluídos no snapshot. Defaults to None.
        exclude (Iterable[str], optional): Campos a serem excluídos do snapshot. Defaults to DEFAULT_EXCLUDE.

    Returns:
        Dict[str, Any]: Um dicionário representando o estado atual do modelo.
    """
    if include:
        return model_to_dict(instance, fields=list(include))
    return model_to_dict(instance, exclude=list(exclude))

# (action: str, instance, *, before=None, after=None, author=None, table: str | None = None, record_id: str | None = None)
def audit(
    action: str,
    instance, *,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    author: Optional[User] = None,
    table: Optional[str] = None,
    record_id: Optional[str] = None,
) -> None:
    """Registra uma ação de auditoria para uma instância de modelo Django.

    Args:
        action (str): A ação realizada (e.g., "create", "update", "delete").
        instance (Django Model): A instância do modelo Django afetada pela ação.
        before (Optional[Dict[str, Any]], optional): O estado do modelo antes da ação. Defaults to None.
        after (Optional[Dict[str, Any]], optional): O estado do modelo após a ação. Defaults to None.
        author (Optional[User], optional): O autor da ação. Se None, tenta obter do middleware. Defaults to None.
        table (Optional[str], optional): O nome da tabela afetada. Se None, usa o nome do modelo. Defaults to None.
        record_id (Optional[str], optional): O ID do registro afetado. Se None, usa o ID da instância. Defaults to None.
    """
    if not table:
        table = instance._meta.db_table
    if not record_id:
        record_id = str(getattr(instance, "id", "unknown"))
    user = author or get_current_user()

    AuditLog.objects.create(
        action=action,
        table=table,
        record_id=record_id,
        before=before,
        after=after,
        author=user if user and user.is_authenticated else None,
    )
