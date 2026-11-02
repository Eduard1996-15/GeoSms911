"""Registro, inicio de sesion y perfil del tutor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from .. import audit, serializers
from ..config import settings
from ..db import get_session
from ..models import User
from ..schemas import LoginIn, RegisterIn, UserPatch
from ..security import (
    client_ip,
    create_access_token,
    current_user,
    hash_password,
    login_limiter,
    register_limiter,
    verify_password,
)
from ..sms import normalize_phone

router = APIRouter(prefix="/api/auth", tags=["autenticacion"])


def _session_payload(user: User) -> dict:
    token, expires_in = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": serializers.user_public(user),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterIn,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El registro esta deshabilitado")
    ip = client_ip(request)
    if not register_limiter.allow(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos, espera un rato")

    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese correo ya esta registrado")

    phone = None
    if payload.phone:
        phone = normalize_phone(payload.phone)
        if not phone:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Telefono invalido: usa formato internacional, por ejemplo +59891234567",
            )

    user = User(
        email=payload.email,
        name=payload.name.strip(),
        phone=phone,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    audit.record(session, "auth.register", user_id=user.id, actor=user.email, ip=ip)
    return _session_payload(user)


@router.post("/login")
def login(
    payload: LoginIn,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    ip = client_ip(request)
    if not login_limiter.allow(f"{ip}:{payload.email}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos, espera 5 minutos")

    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        audit.record(
            session, "auth.login_failed", actor=payload.email, detail="Credenciales invalidas", ip=ip
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contrasena incorrectos")

    audit.record(session, "auth.login", user_id=user.id, actor=user.email, ip=ip)
    return _session_payload(user)


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return serializers.user_public(user)


@router.patch("/me")
def update_me(
    payload: UserPatch,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.phone is not None:
        normalized = normalize_phone(payload.phone)
        if not normalized:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Telefono invalido: usa formato internacional, por ejemplo +59891234567",
            )
        user.phone = normalized
    session.add(user)
    session.commit()
    session.refresh(user)
    return serializers.user_public(user)


@router.delete("/me")
def delete_me(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Borra la cuenta y todos los datos asociados (derecho de supresion)."""
    from sqlmodel import delete

    from ..models import (
        Alert,
        AuditLog,
        Command,
        Device,
        Geofence,
        Location,
        MessageLog,
        PairingCode,
    )

    devices = session.exec(select(Device).where(Device.user_id == user.id)).all()
    device_ids = [device.id for device in devices]

    if device_ids:
        session.exec(delete(Location).where(Location.device_id.in_(device_ids)))  # type: ignore[attr-defined]
        session.exec(delete(Command).where(Command.device_id.in_(device_ids)))  # type: ignore[attr-defined]
        session.exec(delete(Alert).where(Alert.device_id.in_(device_ids)))  # type: ignore[attr-defined]

    session.exec(delete(Geofence).where(Geofence.user_id == user.id))
    session.exec(delete(MessageLog).where(MessageLog.user_id == user.id))
    session.exec(delete(PairingCode).where(PairingCode.user_id == user.id))
    if device_ids:
        session.exec(delete(MessageLog).where(MessageLog.device_id.in_(device_ids)))  # type: ignore[attr-defined]
        session.exec(delete(Device).where(Device.user_id == user.id))

    session.exec(delete(AuditLog).where(AuditLog.user_id == user.id))
    session.delete(user)
    session.commit()

    return {"ok": True, "message": "Cuenta y datos eliminados"}
