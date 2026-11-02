"""Construccion y envio de notificaciones al tutor (SMS) y al dashboard."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlmodel import Session

from . import serializers
from .config import settings
from .events import bus
from .geo import google_maps_url
from .models import Alert, Command, Device, User, utcnow
from .sms import send_sms

logger = logging.getLogger(__name__)


def _local_time(moment: datetime) -> str:
    return moment.replace(tzinfo=timezone.utc).astimezone().strftime("%d/%m %H:%M")


def alert_sms_text(device: Device, alert: Alert) -> str:
    if alert.kind == "geofence_exit":
        headline = f"GeoSms911: {device.name} salio de una zona segura."
    elif alert.kind == "geofence_enter":
        headline = f"GeoSms911: {device.name} entro a una zona segura."
    elif alert.kind == "low_battery":
        headline = f"GeoSms911: bateria baja en el telefono de {device.name}."
    elif alert.kind == "test":
        headline = f"GeoSms911: alerta de prueba de {device.name}."
    else:
        headline = f"ALERTA GeoSms911: {device.name} activo el boton de emergencia."

    lines = [headline]
    if alert.lat is not None and alert.lng is not None:
        lines.append(f"Ubicacion: {google_maps_url(alert.lat, alert.lng)}")
        if alert.accuracy:
            lines.append(f"Precision aproximada: {alert.accuracy:.0f} m")
    else:
        lines.append("Ubicacion no disponible todavia.")
    if alert.battery is not None:
        lines.append(f"Bateria: {alert.battery}%")
    lines.append(f"Hora: {_local_time(alert.created_at)}")
    if alert.message:
        lines.append(f"Mensaje: {alert.message[:120]}")
    lines.append("Responde OK para confirmar, DONDE para ubicacion o TIMBRE para la alarma.")
    return "\n".join(lines)


def notify_alert(session: Session, device: Device, alert: Alert) -> None:
    """Avisa al tutor por SMS y empuja la alerta al dashboard."""
    bus.publish("alert", serializers.alert_public(alert, device.name) | {"user_id": device.user_id})

    user = session.get(User, device.user_id)
    if user is None:
        return

    if not user.phone:
        logger.warning("El tutor %s no tiene telefono configurado; no se envia SMS", user.email)
        return

    log = send_sms(
        session,
        user.phone,
        alert_sms_text(device, alert),
        user_id=user.id,
        device_id=device.id,
    )
    alert.notified = log.status in {"queued", "sent", "delivered", "accepted"}
    session.add(alert)
    session.commit()
    bus.publish("message", serializers.message_public(log) | {"user_id": user.id})


def command_sms_text(device: Device, command: Command) -> str:
    base = (
        f"{settings.sms_command_prefix} {device.sms_secret} CMD "
        f"{command.id} {command.kind}"
    )
    if command.kind in {"alert_screen", "ring"}:
        base += f"\nAbre GeoSms911: {settings.public_base_url_clean}/a"
    return base


def send_command_sms(session: Session, device: Device, command: Command) -> None:
    """Respaldo por SMS cuando el telefono no esta consultando ordenes."""
    if not device.phone:
        return
    log = send_sms(
        session,
        device.phone,
        command_sms_text(device, command),
        user_id=device.user_id,
        device_id=device.id,
    )
    if log.status in {"queued", "sent", "delivered", "accepted"}:
        command.channel = "sms"
        command.sent_at = utcnow()
        session.add(command)
        session.commit()
    bus.publish("message", serializers.message_public(log) | {"user_id": device.user_id})
