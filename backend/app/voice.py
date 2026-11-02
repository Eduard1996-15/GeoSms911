"""Llamadas de voz con Twilio: puente entre tutor y menor, y TwiML."""

from __future__ import annotations

import logging
import secrets
from xml.sax.saxutils import escape

from .config import settings
from .sms import normalize_phone, twilio_client

logger = logging.getLogger(__name__)


class VoiceError(RuntimeError):
    pass


def create_call(to: str | None, twiml_url: str) -> str:
    """Inicia una llamada saliente hacia `to` y devuelve el SID."""
    client = twilio_client()
    if client is None:
        raise VoiceError(
            "Twilio no esta configurado. Completa TWILIO_* en el archivo .env del backend."
        )
    number = normalize_phone(to)
    if not number:
        raise VoiceError("El telefono de destino no es valido (formato E.164).")

    call = client.calls.create(
        to=number,
        from_=settings.twilio_from_number,
        url=twiml_url,
        method="POST",
        timeout=25,
    )
    logger.info("Llamada creada hacia %s (sid=%s)", number, call.sid)
    return call.sid


def conference_twiml(room: str, who: str) -> str:
    """TwiML que une a ambos participantes en una sala de conferencia."""
    who_text = "padre o tutor" if who == "guardian" else "tu familiar"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="es-UY" voice="Polly.Mia">Conectando con {escape(who_text)}. Espere un momento por favor.</Say>
  <Dial>
    <Conference startConferenceOnEnter="true" endConferenceOnExit="true" beep="false"
                waitUrl="http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical">
      {escape(room)}
    </Conference>
  </Dial>
</Response>"""


def bridge_twiml(target_number: str) -> str:
    """TwiML para conectar una llamada entrante con otro numero (oculta el numero real)."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="es-UY" voice="Polly.Mia">Conectando con el telefono de tu familiar.</Say>
  <Dial timeout="30" callerId="{escape(settings.twilio_from_number)}">
    <Number>{escape(target_number)}</Number>
  </Dial>
</Response>"""


def reject_twiml(message: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="es-UY" voice="Polly.Mia">{escape(message)}</Say>
  <Hangup/>
</Response>"""


def message_twiml(message: str) -> str:
    """Respuesta automatica a un SMS entrante."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{escape(message)}</Message>
</Response>"""


def start_bridge(guardian_phone: str, device_phone: str, device_id: str) -> dict[str, str]:
    """Llama a ambos telefonos y los une en una sala de conferencia."""
    room = f"geosms-{device_id}-{secrets.token_hex(3)}"
    twiml_url = f"{settings.public_base_url_clean}/webhooks/twilio/voice/conference"
    guardian_sid = create_call(guardian_phone, f"{twiml_url}?room={room}&who=guardian")
    device_sid = create_call(device_phone, f"{twiml_url}?room={room}&who=device")
    return {"room": room, "guardian_call_sid": guardian_sid, "device_call_sid": device_sid}
