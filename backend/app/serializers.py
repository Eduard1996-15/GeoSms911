"""Funciones para convertir modelos en respuestas JSON estables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import settings
from .geo import google_maps_url
from .models import Alert, Command, Device, Geofence, Location, MessageLog, User, utcnow

ONLINE_WINDOW_SECONDS = 120


def iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def user_public(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "phone": user.phone,
        "created_at": iso_z(user.created_at),
    }


def device_public(device: Device, *, include_secret: bool = False) -> dict[str, Any]:
    now = utcnow()
    seconds_since_seen = (
        int((now - device.last_seen_at).total_seconds()) if device.last_seen_at else None
    )
    data: dict[str, Any] = {
        "id": device.id,
        "name": device.name,
        "phone": device.phone,
        "platform": device.platform,
        "model_name": device.model_name,
        "app_version": device.app_version,
        "location_sharing": device.location_sharing,
        "emergency_number": device.emergency_number,
        "online": bool(
            seconds_since_seen is not None and seconds_since_seen <= ONLINE_WINDOW_SECONDS
        ),
        "seconds_since_seen": seconds_since_seen,
        "last_seen_at": iso_z(device.last_seen_at),
        "last_location_at": iso_z(device.last_location_at),
        "last_lat": device.last_lat,
        "last_lng": device.last_lng,
        "last_accuracy": device.last_accuracy,
        "last_battery": device.last_battery,
        "last_speed": device.last_speed,
        "last_location_maps_url": (
            google_maps_url(device.last_lat, device.last_lng)
            if device.last_lat is not None and device.last_lng is not None
            else None
        ),
        "created_at": iso_z(device.created_at),
        "revoked_at": iso_z(device.revoked_at),
    }
    if include_secret:
        data["sms_secret"] = device.sms_secret
    return data


def location_public(location: Location) -> dict[str, Any]:
    return {
        "id": location.id,
        "device_id": location.device_id,
        "lat": location.lat,
        "lng": location.lng,
        "accuracy": location.accuracy,
        "speed": location.speed,
        "bearing": location.bearing,
        "battery": location.battery,
        "source": location.source,
        "created_at": iso_z(location.created_at),
    }


def alert_public(alert: Alert, device_name: str | None = None) -> dict[str, Any]:
    return {
        "id": alert.id,
        "device_id": alert.device_id,
        "device_name": device_name,
        "kind": alert.kind,
        "status": alert.status,
        "message": alert.message,
        "lat": alert.lat,
        "lng": alert.lng,
        "accuracy": alert.accuracy,
        "battery": alert.battery,
        "maps_url": (
            google_maps_url(alert.lat, alert.lng)
            if alert.lat is not None and alert.lng is not None
            else None
        ),
        "notified": alert.notified,
        "created_at": iso_z(alert.created_at),
        "ack_at": iso_z(alert.ack_at),
        "resolved_at": iso_z(alert.resolved_at),
        "resolved_by": alert.resolved_by,
    }


def command_public(command: Command) -> dict[str, Any]:
    return {
        "id": command.id,
        "device_id": command.device_id,
        "kind": command.kind,
        "payload": command.payload or {},
        "status": command.status,
        "channel": command.channel,
        "created_by": command.created_by,
        "created_at": iso_z(command.created_at),
        "sent_at": iso_z(command.sent_at),
        "acked_at": iso_z(command.acked_at),
        "result": command.result,
        "error": command.error,
    }


def geofence_public(zone: Geofence) -> dict[str, Any]:
    return {
        "id": zone.id,
        "user_id": zone.user_id,
        "device_id": zone.device_id,
        "name": zone.name,
        "lat": zone.lat,
        "lng": zone.lng,
        "radius_m": zone.radius_m,
        "notify_on_exit": zone.notify_on_exit,
        "enabled": zone.enabled,
        "last_state": zone.last_state,
        "created_at": iso_z(zone.created_at),
    }


def message_public(message: MessageLog) -> dict[str, Any]:
    return {
        "id": message.id,
        "device_id": message.device_id,
        "direction": message.direction,
        "to": message.to,
        "from_number": message.from_number,
        "body": message.body,
        "provider": message.provider,
        "sid": message.sid,
        "status": message.status,
        "error": message.error,
        "created_at": iso_z(message.created_at),
    }


def server_info() -> dict[str, Any]:
    return {
        "app": settings.app_name,
        "public_base_url": settings.public_base_url_clean,
        "twilio_configured": settings.twilio_configured,
        "signature_validation": settings.twilio_validate_signature,
        "allow_registration": settings.allow_registration,
    }
