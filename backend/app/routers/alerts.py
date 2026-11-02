"""Bandeja de alertas del tutor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from .. import audit, serializers
from ..db import get_session
from ..events import bus
from ..models import Alert, Device, User, utcnow
from ..schemas import AlertUpdateIn
from ..security import current_user

router = APIRouter(prefix="/api/alerts", tags=["alertas"])


@router.get("")
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    device_id: str | None = None,
    limit: int = 100,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    limit = max(1, min(limit, 300))
    statement = (
        select(Alert, Device)
        .join(Device, Alert.device_id == Device.id)
        .where(Device.user_id == user.id)
    )
    if status_filter:
        statement = statement.where(Alert.status == status_filter)
    if device_id:
        statement = statement.where(Alert.device_id == device_id)
    statement = statement.order_by(Alert.created_at.desc()).limit(limit)

    rows = session.exec(statement).all()
    return {
        "alerts": [serializers.alert_public(alert, device.name) for alert, device in rows],
        "open_count": sum(1 for alert, _ in rows if alert.status == "open"),
    }


@router.post("/{alert_id}")
def update_alert(
    alert_id: str,
    payload: AlertUpdateIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    row = session.exec(
        select(Alert, Device)
        .join(Device, Alert.device_id == Device.id)
        .where(Alert.id == alert_id, Device.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")

    alert, device = row
    alert.status = payload.status
    if payload.status == "acknowledged":
        alert.ack_at = alert.ack_at or utcnow()
    else:
        alert.resolved_at = utcnow()
        alert.resolved_by = user.email
    session.add(alert)
    session.commit()
    session.refresh(alert)

    audit.record(
        session,
        "alert.update",
        user_id=user.id,
        actor=user.email,
        detail=f"{alert.id} -> {payload.status}" + (f" ({payload.note})" if payload.note else ""),
    )
    bus.publish("alert", serializers.alert_public(alert, device.name) | {"user_id": user.id})
    return serializers.alert_public(alert, device.name)
