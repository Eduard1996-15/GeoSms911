"""Envio de SMS mediante Twilio, con registro local de cada mensaje."""

from __future__ import annotations

import logging
import re

from sqlmodel import Session
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from .config import settings
from .models import MessageLog

logger = logging.getLogger(__name__)
_client: Client | None = None


def twilio_client() -> Client | None:
    global _client
    if not settings.twilio_configured:
        return None
    if _client is None:
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def normalize_phone(value: str | None) -> str | None:
    """Devuelve el numero en formato E.164 o None si no es valido."""
    if not value:
        return None
    cleaned = re.sub(r"[^\d+]", "", value.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        return None
    digits = cleaned[1:]
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        return None
    return "+" + digits


def send_sms(
    session: Session,
    to: str | None,
    body: str,
    *,
    user_id: str | None = None,
    device_id: str | None = None,
) -> MessageLog:
    """Envia un SMS (o solo lo registra si Twilio no esta configurado)."""
    normalized = normalize_phone(to)
    log = MessageLog(
        user_id=user_id,
        device_id=device_id,
        direction="outbound",
        to=normalized or to,
        body=body,
    )

    if not normalized:
        log.status = "failed"
        log.error = "Numero de destino invalido (se requiere formato E.164, ej. +59891234567)"
        session.add(log)
        session.commit()
        session.refresh(log)
        return log

    client = twilio_client()
    if client is None:
        log.status = "logged"
        log.error = "Twilio no configurado: el mensaje solo quedo registrado"
        session.add(log)
        session.commit()
        session.refresh(log)
        logger.warning("SMS sin enviar (Twilio no configurado) a %s: %s", normalized, body[:80])
        return log

    try:
        message = client.messages.create(
            to=normalized,
            from_=settings.twilio_from_number,
            body=body,
        )
        log.sid = message.sid
        log.status = message.status or "queued"
    except TwilioRestException as exc:
        log.status = "failed"
        log.error = f"Twilio {exc.code}: {exc.msg}"
        logger.error("Fallo el envio de SMS a %s: %s", normalized, exc)
    except Exception as exc:  # pragma: no cover - errores de red inesperados
        log.status = "failed"
        log.error = str(exc)
        logger.exception("Fallo inesperado al enviar SMS a %s", normalized)

    session.add(log)
    session.commit()
    session.refresh(log)
    return log
