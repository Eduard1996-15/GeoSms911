"""Zonas seguras (geocercas) del tutor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from .. import serializers
from ..db import get_session
from ..models import Device, Geofence, User
from ..schemas import GeofenceIn, GeofencePatch
from ..security import current_user

router = APIRouter(prefix="/api/geofences", tags=["zonas"])


def _own_zone(zone_id: str, user: User, session: Session) -> Geofence:
    zone = session.get(Geofence, zone_id)
    if zone is None or zone.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zona no encontrada")
    return zone


@router.get("")
def list_geofences(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    zones = session.exec(select(Geofence).where(Geofence.user_id == user.id)).all()
    return {"geofences": [serializers.geofence_public(zone) for zone in zones]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_geofence(
    payload: GeofenceIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    if payload.device_id:
        device = session.get(Device, payload.device_id)
        if device is None or device.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo no encontrado")

    zone = Geofence(
        user_id=user.id,
        device_id=payload.device_id,
        name=payload.name.strip(),
        lat=payload.lat,
        lng=payload.lng,
        radius_m=payload.radius_m,
        notify_on_exit=payload.notify_on_exit,
        enabled=payload.enabled,
    )
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return serializers.geofence_public(zone)


@router.patch("/{zone_id}")
def update_geofence(
    zone_id: str,
    payload: GeofencePatch,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    zone = _own_zone(zone_id, user, session)
    if payload.name is not None:
        zone.name = payload.name.strip()
    if payload.radius_m is not None:
        zone.radius_m = payload.radius_m
    if payload.notify_on_exit is not None:
        zone.notify_on_exit = payload.notify_on_exit
    if payload.enabled is not None:
        zone.enabled = payload.enabled
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return serializers.geofence_public(zone)


@router.delete("/{zone_id}")
def delete_geofence(
    zone_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    zone = _own_zone(zone_id, user, session)
    session.delete(zone)
    session.commit()
    return {"ok": True}
