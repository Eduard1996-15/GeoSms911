"""Emparejamiento, gestion de telefonos y envio de ordenes."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from .. import audit, serializers, services
from ..config import settings
from ..db import get_session
from ..deps import owned_device
from ..events import bus
from ..models import Alert, Command, Device, Location, PairingCode, User, utcnow
from ..schemas import AlertIn, CommandIn, DevicePatch, DeviceRegisterIn, PairingCodeIn
from ..security import (
    client_ip,
    command_limiter,
    current_user,
    pairing_limiter,
    sha256_hex,
)
from ..sms import normalize_phone
from ..voice import VoiceError, start_bridge

router = APIRouter(prefix="/api/devices", tags=["dispositivos"])

PAIRING_MINUTES = 10


def _pairing_code(session: Session) -> str:
    for _ in range(25):
        candidate = f"{secrets.randbelow(1_000_000):06d}"
        clash = session.exec(
            select(PairingCode).where(
                PairingCode.code == candidate,
                PairingCode.used_at == None,  # noqa: E712
                PairingCode.expires_at > utcnow(),
            )
        ).first()
        if clash is None:
            return candidate
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No se pudo generar un codigo")


@router.post("/pairing-code")
def create_pairing_code(
    payload: PairingCodeIn,
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    if not pairing_limiter.allow(user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados codigos generados")

    code = _pairing_code(session)
    expires_at = utcnow() + timedelta(minutes=PAIRING_MINUTES)
    session.add(PairingCode(user_id=user.id, code=code, expires_at=expires_at))
    session.commit()
    audit.record(
        session, "device.pairing_code", user_id=user.id, actor=user.email, ip=client_ip(request)
    )
    return {
        "code": code,
        "expires_at": serializers.iso_z(expires_at),
        "expires_in": PAIRING_MINUTES * 60,
        "server_url": settings.public_base_url_clean,
        "device_name_suggestion": payload.name or "Telefono de mi hijo",
        "instructions": (
            "En el telefono del menor abre GeoSms911, escribe la URL del servidor y este codigo."
        ),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceRegisterIn,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Empareja un telefono usando el codigo de 6 digitos. No requiere sesion."""
    ip = client_ip(request)
    if not pairing_limiter.allow(f"register:{ip}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos")

    pairing = session.exec(
        select(PairingCode).where(PairingCode.code == payload.code.strip())
    ).first()
    if pairing is None or pairing.used_at is not None or pairing.expires_at < utcnow():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Codigo invalido o vencido. Genera uno nuevo en el dashboard."
        )

    phone = None
    if payload.phone:
        phone = normalize_phone(payload.phone)
        if not phone:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Telefono invalido: usa formato internacional, por ejemplo +59891234567",
            )

    token = secrets.token_urlsafe(32)
    device = Device(
        user_id=pairing.user_id,
        name=payload.name.strip(),
        phone=phone,
        platform=payload.platform,
        model_name=payload.model_name,
        app_version=payload.app_version,
        token_hash=sha256_hex(token),
        sms_secret=secrets.token_hex(4).upper(),
        last_seen_at=utcnow(),
    )
    pairing.used_at = utcnow()
    session.add(device)
    session.add(pairing)
    session.commit()
    session.refresh(device)

    audit.record(
        session,
        "device.paired",
        user_id=device.user_id,
        actor="device",
        detail=f"{device.name} ({device.platform})",
        ip=ip,
    )
    bus.publish("device", serializers.device_public(device) | {"user_id": device.user_id})

    return {
        "device_id": device.id,
        "device_token": token,
        "sms_secret": device.sms_secret,
        "sms_prefix": settings.sms_command_prefix,
        "emergency_number": device.emergency_number,
        "device": serializers.device_public(device),
        "server_time": serializers.iso_z(utcnow()),
    }


@router.get("")
def list_devices(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    devices = session.exec(
        select(Device).where(Device.user_id == user.id, Device.revoked_at == None)  # noqa: E712
    ).all()
    return {"devices": [serializers.device_public(device) for device in devices]}


@router.get("/{device_id}")
def get_device(device: Device = Depends(owned_device)) -> dict:
    return serializers.device_public(device)


@router.patch("/{device_id}")
def update_device(
    payload: DevicePatch,
    user: User = Depends(current_user),
    device: Device = Depends(owned_device),
    session: Session = Depends(get_session),
) -> dict:
    if payload.name is not None:
        device.name = payload.name.strip()
    if payload.phone is not None:
        normalized = normalize_phone(payload.phone)
        if not normalized:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Telefono invalido")
        device.phone = normalized
    if payload.location_sharing is not None:
        device.location_sharing = payload.location_sharing
    if payload.emergency_number is not None:
        device.emergency_number = payload.emergency_number.strip()
    session.add(device)
    session.commit()
    session.refresh(device)

    audit.record(session, "device.update", user_id=user.id, actor=user.email, detail=device.name)
    bus.publish("device", serializers.device_public(device) | {"user_id": user.id})
    return serializers.device_public(device)


@router.post("/{device_id}/revoke")
def revoke_device(
    user: User = Depends(current_user),
    device: Device = Depends(owned_device),
    session: Session = Depends(get_session),
) -> dict:
    device.revoked_at = utcnow()
    session.add(device)
    session.commit()
    audit.record(session, "device.revoke", user_id=user.id, actor=user.email, detail=device.name)
    bus.publish("device", serializers.device_public(device) | {"user_id": user.id})
    return {"ok": True}


@router.get("/{device_id}/locations")
def device_locations(
    hours: int = 24,
    limit: int = 2000,
    device: Device = Depends(owned_device),
    session: Session = Depends(get_session),
) -> dict:
    hours = max(1, min(hours, 24 * 30))
    limit = max(1, min(limit, 5000))
    cutoff = utcnow() - timedelta(hours=hours)
    rows = session.exec(
        select(Location)
        .where(Location.device_id == device.id, Location.created_at >= cutoff)
        .order_by(Location.created_at.desc())
        .limit(limit)
    ).all()
    rows.reverse()
    return {"device_id": device.id, "count": len(rows), "points": [serializers.location_public(p) for p in rows]}


@router.get("/{device_id}/commands")
def device_commands(
    limit: int = 50,
    device: Device = Depends(owned_device),
    session: Session = Depends(get_session),
) -> dict:
    limit = max(1, min(limit, 200))
    rows = session.exec(
        select(Command)
        .where(Command.device_id == device.id)
        .order_by(Command.created_at.desc())
        .limit(limit)
    ).all()
    return {"commands": [serializers.command_public(c) for c in rows]}


@router.post("/{device_id}/commands", status_code=status.HTTP_201_CREATED)
def send_command(
    payload: CommandIn,
    user: User = Depends(current_user),
    device: Device = Depends(owned_device),
    session: Session = Depends(get_session),
) -> dict:
    if not command_limiter.allow(user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiadas ordenes seguidas")

    command = services.create_command(
        session, device, payload.kind, payload.payload, created_by=user.email
    )
    audit.record(
        session,
        "device.command",
        user_id=user.id,
        actor=user.email,
        detail=f"{device.name}: {payload.kind}",
    )
    return serializers.command_public(command)


@router.post("/{device_id}/call")
def call_device(
    user: User = Depends(current_user),
    device: Device = Depends(owned_device),
    session: Session = Depends(get_session),
) -> dict:
    """Crea un puente telefonico: Twilio llama al tutor y al menor y los une."""
    if not settings.twilio_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Twilio no esta configurado. Completa TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_FROM_NUMBER.",
        )
    if not user.phone:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tu usuario no tiene telefono configurado. Agregalo en tu perfil.",
        )
    if not device.phone:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "El telefono del menor no tiene numero configurado.",
        )

    room = None
    try:
        bridge = start_bridge(user.phone, device.phone, device.id)
        room = bridge["room"]
    except VoiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    audit.record(
        session, "device.call", user_id=user.id, actor=user.email, detail=f"Puente a {device.name}"
    )
    return {
        "ok": True,
        **bridge,
        "message": f"Llamando a {user.phone} y a {device.phone}. Atiende el telefono.",
    }


@router.post("/{device_id}/test-alert", status_code=status.HTTP_201_CREATED)
def test_alert(
    user: User = Depends(current_user),
    device: Device = Depends(owned_device),
    session: Session = Depends(get_session),
) -> dict:
    alert = services.create_alert(
        session,
        device,
        AlertIn(
            kind="test",
            message="Alerta de prueba generada desde el dashboard.",
            lat=device.last_lat,
            lng=device.last_lng,
            accuracy=device.last_accuracy,
            battery=device.last_battery,
        ),
    )
    audit.record(session, "alert.test", user_id=user.id, actor=user.email, detail=device.name)
    return serializers.alert_public(alert, device.name)


@router.get("/{device_id}/alerts")
def device_alerts(
    limit: int = 50,
    device: Device = Depends(owned_device),
    session: Session = Depends(get_session),
) -> dict:
    limit = max(1, min(limit, 200))
    rows = session.exec(
        select(Alert)
        .where(Alert.device_id == device.id)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    ).all()
    return {"alerts": [serializers.alert_public(a, device.name) for a in rows]}
