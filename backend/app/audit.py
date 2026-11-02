"""Registro de auditoria de acciones sensibles."""

from __future__ import annotations

from sqlmodel import Session

from .models import AuditLog


def record(
    session: Session,
    action: str,
    *,
    user_id: str | None = None,
    actor: str = "system",
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    session.add(AuditLog(user_id=user_id, action=action, actor=actor, detail=detail, ip=ip))
    session.commit()
