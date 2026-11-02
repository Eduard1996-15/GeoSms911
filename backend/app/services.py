"""Logica de negocio compartida: ubicaciones, alertas, ordenes y geocercas."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from . import notifications, serializers
from .config import settings
from .events import bus
from .geo import haversine_m
from .models import Alert, Command, Device, Geofence, Location, utcnow
from .schemas import AlertIn, LocationIn

logger = logging.getLogger(__name__)


def _naive_utc(value: datetime | None) -> datetime:
    if value is None:
        return utcnow()
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def device_offline(device: Device) -> bool:
    if device.last_seen_at is None:
        return True
    return (utcnow() - device.last_seen_at).total_seconds() > settings.sms_fallback_after_seconds


def record_location(
    session: Session,
    device: Device,
    point: LocationIn,
    *,
    commit: bool = True,
) -> Location:
    """Guarda un punto, actualiza el estado del telefono y evalua geocercas."""
    moment = _naive_utc(point.captured_at)
    location = Location(
        device_id=device.id,
        lat=point.lat,
        lng=point.lng,
        accuracy=point.accuracy,
        speed=point.speed,
        bearing=point.bearing,
        battery=point.battery,
        source=point.source,
        created_at=moment,
    )
    session.add(location)

    device.last_location_at = moment
    device.last_lat = point.lat
    device.last_lng = point.lng
    device.last_accuracy = point.accuracy
    device.last_speed = point.speed
    if point.battery is not None:
        device.last_battery = point.battery
    device.last_seen_at = utcnow()
    session.add(device)

    triggered: list[Alert] = evaluate_geofences(session, device, point.lat, point.lng)

    if commit:
        session.commit()
        session.refresh(location)

    bus.publish(
        "location",
        {
            "user_id": device.user_id,
            "device_id": device.id,
            "device_name": device.name,
            "lat": point.lat,
            "lng": point.lng,
            "accuracy": point.accuracy,
            "battery": device.last_battery,
            "speed": point.speed,
            "created_at": serializers.iso_z(moment),
        },
    )

    for alert in triggered:
        _finish_alert(session, device, alert)
    return location


def create_alert(session: Session, device: Device, payload: AlertIn) -> Alert:
    """Registra una alerta (panico o geocerca) y avisa al tutor."""
    alert = Alert(
        device_id=device.id,
        kind=payload.kind,
        message=payload.message,
        lat=payload.lat,
        lng=payload.lng,
        accuracy=payload.accuracy,
        battery=payload.battery,
        created_at=utcnow(),
    )
    if payload.lat is not None and payload.lng is not None:
        record_location(
            session,
            device,
            LocationIn(
                lat=payload.lat,
                lng=payload.lng,
                accuracy=payload.accuracy,
                battery=payload.battery,
                source="alert",
            ),
            commit=False,
        )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    _finish_alert(session, device, alert)
    return alert


def _finish_alert(session: Session, device: Device, alert: Alert) -> None:
    try:
        notifications.notify_alert(session, device, alert)
    except Exception:  # pragma: no cover - nunca romper la ingesta por un fallo de SMS
        logger.exception("No se pudo notificar la alerta %s", alert.id)


def create_command(
    session: Session,
    device: Device,
    kind: str,
    payload: dict[str, Any] | None = None,
    created_by: str | None = None,
) -> Command:
    command = Command(
        device_id=device.id,
        kind=kind,
        payload=payload or {},
        created_by=created_by,
    )
    session.add(command)
    session.commit()
    session.refresh(command)
    bus.publish("command", serializers.command_public(command) | {"user_id": device.user_id})

    if device_offline(device):
        notifications.send_command_sms(session, device, command)
        session.refresh(command)
    return command


def evaluate_geofences(
    session: Session, device: Device, lat: float, lng: float
) -> list[Alert]:
    """Devuelve alertas nuevas por salida de una zona segura."""
    zones = session.exec(
        select(Geofence).where(
            Geofence.user_id == device.user_id,
            Geofence.enabled == True,  # noqa: E712
        )
    ).all()

    created: list[Alert] = []
    for zone in zones:
        if zone.device_id and zone.device_id != device.id:
            continue
        distance = haversine_m(lat, lng, zone.lat, zone.lng)
        inside = distance <= zone.radius_m
        previous = zone.last_state
        zone.last_state = "inside" if inside else "outside"
        session.add(zone)

        if previous == "inside" and not inside:
            alert = Alert(
                device_id=device.id,
                kind="geofence_exit",
                message=f"Salio de la zona segura '{zone.name}' ({distance:.0f} m del centro).",
                lat=lat,
                lng=lng,
                battery=device.last_battery,
                created_at=utcnow(),
            )
            session.add(alert)
            created.append(alert)
        elif previous == "outside" and inside:
            bus.publish(
                "geofence",
                {"zone": serializers.geofence_public(zone), "state": "inside", "device_id": device.id, "user_id": device.user_id},
            )

    if created:
        session.flush()
    return created


def acknowledge_alerts(session: Session, device: Device) -> int:
    alerts = session.exec(
        select(Alert).where(Alert.device_id == device.id, Alert.status == "open")
    ).all()
    for alert in alerts:
        alert.status = "acknowledged"
        alert.ack_at = utcnow()
        session.add(alert)
    session.commit()
    for alert in alerts:
        bus.publish("alert", serializers.alert_public(alert, device.name) | {"user_id": device.user_id})
    return len(alerts)
