"""Webhooks de Twilio: SMS entrantes, respuestas, estado y voz."""

from __future__ import annotations

import logging
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlmodel import Session, select
from twilio.request_validator import RequestValidator

from .. import serializers, services, voice
from ..config import settings
from ..db import get_session
from ..events import bus
from ..geo import google_maps_url
from ..models import Device, MessageLog, User, utcnow
from ..security import command_limiter
from ..sms import normalize_phone
from ..voice import VoiceError, message_twiml

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])

ROOM_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")

KEYWORDS: dict[str, str] = {
    "DONDE": "locate",
    "UBICACION": "locate",
    "LOCALIZAR": "locate",
    "LOC": "locate",
    "TIMBRE": "ring",
    "ALARMA": "ring",
    "RING": "ring",
    "SILENCIO": "stop_ring",
    "STOP": "stop_ring",
    "SOS": "alert_screen",
    "EMERGENCIA": "alert_screen",
    "ALERTA": "alert_screen",
    "LLAMAR": "call",
    "LLAMA": "call",
    "CALL": "call",
    "ESTADO": "status",
    "STATUS": "status",
    "OK": "ack",
    "RECIBIDO": "ack",
    "ENTERADO": "ack",
    "AYUDA": "help",
    "COMANDOS": "help",
    "HELP": "help",
}

HELP_TEXT = (
    "Comandos GeoSms911: DONDE (ubicacion), TIMBRE (alarma), SILENCIO, "
    "SOS (pantalla de emergencia), LLAMAR (puente telefonico), "
    "ESTADO (bateria y ultima conexion), OK (confirmar alerta)."
)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").upper().strip()


def _signed_url(request: Request) -> str:
    url = f"{settings.public_base_url_clean}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


def _validate_signature(request: Request, params: dict[str, str]) -> bool:
    """Twilio firma cada webhook. Sin firma valida no se procesa nada."""
    if not settings.twilio_configured:
        logger.warning(
            "Webhook de Twilio rechazado: faltan TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN o TWILIO_FROM_NUMBER"
        )
        return False
    if not settings.twilio_validate_signature:
        logger.warning("TWILIO_VALIDATE_SIGNATURE=false: se aceptan webhooks sin firma")
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False
    validator = RequestValidator(settings.twilio_auth_token)
    return bool(validator.validate(_signed_url(request), params, signature))


def _xml(body: str, status_code: int = 200) -> Response:
    return Response(content=body, media_type="application/xml", status_code=status_code)


def _twiml_message(session: Session, user: User, body: str) -> Response:
    """Registra la respuesta y la devuelve como TwiML (Twilio la envia como SMS)."""
    log = MessageLog(
        user_id=user.id,
        direction="outbound",
        to=user.phone,
        body=body,
        status="logged",
        provider="twilio-twiml",
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    bus.publish("message", serializers.message_public(log) | {"user_id": user.id})
    return _xml(message_twiml(body))


def _primary_device(session: Session, user: User) -> Device | None:
    devices = session.exec(
        select(Device).where(Device.user_id == user.id, Device.revoked_at == None)  # noqa: E712
    ).all()
    if not devices:
        return None
    devices.sort(key=lambda d: (not d.is_online, d.created_at))
    return devices[0]


def _status_text(device: Device) -> str:
    parts = [f"Estado de {device.name}:"]
    parts.append(f"Bateria: {device.last_battery}%" if device.last_battery is not None else "Bateria: sin dato")
    if device.last_seen_at:
        parts.append(f"Ultima conexion: {serializers.iso_z(device.last_seen_at)}")
    if device.last_lat is not None and device.last_lng is not None:
        parts.append(f"Ubicacion: {google_maps_url(device.last_lat, device.last_lng)}")
    else:
        parts.append("Ubicacion: sin dato")
    return "\n".join(parts)


@router.post("/sms")
async def inbound_sms(request: Request, session: Session = Depends(get_session)) -> Response:
    form = await request.form()
    params = {str(key): str(value) for key, value in form.items()}

    if not _validate_signature(request, params):
        logger.warning("Firma de Twilio invalida para %s", request.url.path)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Firma de Twilio invalida")

    from_number = normalize_phone(params.get("From"))
    body = (params.get("Body") or "").strip()
    logger.info("SMS entrante de %s: %s", from_number, body[:120])

    user = None
    if from_number:
        user = session.exec(select(User).where(User.phone == from_number)).first()

    incoming = MessageLog(
        user_id=user.id if user else None,
        direction="inbound",
        from_number=from_number,
        body=body,
        status="received",
        provider="twilio",
        sid=params.get("MessageSid"),
    )
    session.add(incoming)
    session.commit()
    session.refresh(incoming)
    if user:
        bus.publish("message", serializers.message_public(incoming) | {"user_id": user.id})

    if user is None:
        return _xml(message_twiml("Este numero no esta autorizado en GeoSms911."))
    if not command_limiter.allow(f"sms:{user.id}"):
        return _xml(message_twiml("Demasiados comandos seguidos. Espera un minuto."))

    action = KEYWORDS.get(_fold(body).split(" ")[0] if body else "", "")
    if action == "help":
        return _twiml_message(session, user, HELP_TEXT)
    if action == "ack":
        total = 0
        devices = session.exec(
            select(Device).where(Device.user_id == user.id, Device.revoked_at == None)  # noqa: E712
        ).all()
        for device in devices:
            total += services.acknowledge_alerts(session, device)
        if total:
            return _twiml_message(session, user, f"Confirmadas {total} alerta(s). Gracias.")
        return _twiml_message(session, user, "No habia alertas pendientes de confirmar.")

    device = _primary_device(session, user)
    if device is None:
        return _twiml_message(
            session, user, "No hay telefonos emparejados. Genera un codigo en el dashboard."
        )

    if not action:
        return _twiml_message(session, user, HELP_TEXT)

    if action == "status":
        return _twiml_message(session, user, _status_text(device))

    if action == "call":
        if not settings.twilio_configured:
            return _twiml_message(session, user, "Twilio no esta configurado en el servidor.")
        if not user.phone or not device.phone:
            return _twiml_message(
                session, user, "Falta un numero de telefono para crear la llamada."
            )
        try:
            voice.start_bridge(user.phone, device.phone, device.id)
        except VoiceError as exc:
            return _twiml_message(session, user, f"No se pudo llamar: {exc}")
        return _twiml_message(
            session, user, f"Te estamos llamando y marcando a {device.name}. Atiende el telefono."
        )

    command = services.create_command(
        session, device, action, {"origin": "sms"}, created_by=user.email
    )
    responses = {
        "locate": f"Buscando la ubicacion de {device.name}...",
        "ring": f"Alarma activada en {device.name}.",
        "stop_ring": f"Alarma detenida en {device.name}.",
        "alert_screen": f"Pantalla de emergencia enviada a {device.name}.",
    }
    note = "" if command.status != "pending" else " (se reintentara cuando el telefono se conecte)"
    return _twiml_message(session, user, responses.get(action, "Orden enviada.") + note)


@router.post("/sms/status")
async def sms_status(request: Request, session: Session = Depends(get_session)) -> Response:
    form = await request.form()
    params = {str(key): str(value) for key, value in form.items()}
    if not _validate_signature(request, params):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Firma de Twilio invalida")

    sid = params.get("MessageSid")
    new_status = params.get("MessageStatus")
    if sid and new_status:
        log = session.exec(select(MessageLog).where(MessageLog.sid == sid)).first()
        if log:
            log.status = new_status
            if params.get("ErrorMessage"):
                log.error = params.get("ErrorMessage")
            session.add(log)
            session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/voice")
async def inbound_voice(request: Request, session: Session = Depends(get_session)) -> Response:
    form = await request.form()
    params = {str(key): str(value) for key, value in form.items()}
    if not _validate_signature(request, params):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Firma de Twilio invalida")

    caller = normalize_phone(params.get("From"))
    if not caller:
        return _xml(voice.reject_twiml("No se pudo identificar el numero de origen."))

    user = session.exec(select(User).where(User.phone == caller)).first()
    if user is not None:
        device = _primary_device(session, user)
        if device is None or not device.phone:
            return _xml(voice.reject_twiml("No hay un telefono de menor configurado."))
        return _xml(voice.bridge_twiml(device.phone))

    device = session.exec(
        select(Device).where(Device.phone == caller, Device.revoked_at == None)  # noqa: E712
    ).first()
    if device is None:
        return _xml(voice.reject_twiml("Numero no autorizado en GeoSms911."))

    guardian = session.get(User, device.user_id)
    if guardian is None or not guardian.phone:
        return _xml(voice.reject_twiml("El tutor no tiene telefono configurado."))
    return _xml(voice.bridge_twiml(guardian.phone))


@router.api_route("/voice/conference", methods=["GET", "POST"])
async def voice_conference(
    request: Request,
    room: str = Query(..., min_length=3, max_length=64),
    who: str = Query(default="guardian"),
) -> Response:
    if not ROOM_RE.match(room):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sala invalida")

    form = await request.form()
    params = {str(key): str(value) for key, value in form.items()}
    if not _validate_signature(request, params):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Firma de Twilio invalida")

    return _xml(voice.conference_twiml(room, who))
