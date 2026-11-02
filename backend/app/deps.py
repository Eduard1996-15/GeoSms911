"""Dependencias compartidas de los routers."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from .db import get_session
from .models import Device, User
from .security import current_user


def owned_device(
    device_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Device:
    device = session.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo no encontrado")
    return device
