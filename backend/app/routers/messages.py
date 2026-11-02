"""Historial de SMS y envio de mensajes de prueba."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from .. import serializers
from ..config import settings
from ..db import get_session
from ..events import bus
from ..models import MessageLog, User
from ..schemas import SmsTestIn
from ..security import current_user
from ..sms import send_sms

router = APIRouter(prefix="/api/messages", tags=["mensajes"])


@router.get("")
def list_messages(
    limit: int = 100,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    limit = max(1, min(limit, 300))
    rows = session.exec(
        select(MessageLog)
        .where(MessageLog.user_id == user.id)
        .order_by(MessageLog.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "twilio_configured": settings.twilio_configured,
        "messages": [serializers.message_public(m) for m in rows],
    }


@router.post("/test", status_code=status.HTTP_201_CREATED)
def send_test(
    payload: SmsTestIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    target = payload.to or user.phone
    if not target:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No hay numero de destino: configura tu telefono en el perfil o indica uno.",
        )
    log = send_sms(session, target, payload.body, user_id=user.id)
    bus.publish("message", serializers.message_public(log) | {"user_id": user.id})
    return serializers.message_public(log)
