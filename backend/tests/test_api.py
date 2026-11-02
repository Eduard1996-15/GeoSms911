"""Pruebas de extremo a extremo de la API de GeoSms911."""

from __future__ import annotations

from twilio.request_validator import RequestValidator

from app.config import settings

CASA = {"lat": -34.9011, "lng": -56.1645}
LEJOS = {"lat": -34.9200, "lng": -56.1900}
TEST_TOKEN = "token-de-prueba"
TEST_BASE_URL = "http://testserver"


def configure_fake_twilio(monkeypatch) -> None:
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest00000000000000000000000000")
    monkeypatch.setattr(settings, "twilio_auth_token", TEST_TOKEN)
    monkeypatch.setattr(settings, "twilio_from_number", "+15005550006")
    monkeypatch.setattr(settings, "twilio_validate_signature", True)


def twilio_signature(params: dict[str, str], path: str = "/webhooks/twilio/sms") -> dict[str, str]:
    signature = RequestValidator(TEST_TOKEN).compute_signature(
        f"{TEST_BASE_URL}{path}", params
    )
    return {"X-Twilio-Signature": signature}


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_register_login_and_me(client, guardian):
    login = client.post(
        "/api/auth/login",
        json={"email": "tutor@example.com", "password": "contrasena-segura-123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["phone"] == "+59891111111"


def test_duplicate_email_is_rejected(client, guardian):
    response = client.post("/api/auth/register", json={**guardian["user"], "password": "x" * 12})
    assert response.status_code in (409, 422)


def test_login_with_wrong_password(client, guardian):
    response = client.post(
        "/api/auth/login", json={"email": "tutor@example.com", "password": "incorrecta"}
    )
    assert response.status_code == 401


def test_pairing_code_is_single_use(client, device):
    # El codigo ya fue consumido por el fixture.
    response = client.post(
        "/api/devices/register",
        json={"code": "000000", "name": "Otro", "platform": "android"},
    )
    assert response.status_code == 404


def test_device_requires_valid_token(client, device):
    response = client.get(
        "/api/ingest/me",
        headers={"X-Device-Id": device["id"], "X-Device-Token": "token-falso"},
    )
    assert response.status_code == 401

    missing = client.get("/api/ingest/me")
    assert missing.status_code == 422


def test_panic_alert_flow(client, guardian, device):
    location = client.post(
        "/api/ingest/location",
        json={**CASA, "accuracy": 12.5, "battery": 74, "source": "app"},
        headers=device["headers"],
    )
    assert location.status_code == 201, location.text

    alert = client.post(
        "/api/ingest/alert",
        json={"kind": "panic", "lat": CASA["lat"], "lng": CASA["lng"], "battery": 74},
        headers=device["headers"],
    )
    assert alert.status_code == 201, alert.text
    alert_id = alert.json()["alert"]["id"]

    listing = client.get("/api/alerts", headers=guardian["headers"])
    assert listing.status_code == 200
    alerts = listing.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["status"] == "open"
    assert alerts[0]["device_name"] == "Telefono de Mateo"
    assert alerts[0]["maps_url"].startswith("https://www.google.com/maps?q=")

    sms = client.get("/api/messages", headers=guardian["headers"]).json()["messages"]
    assert any("ALERTA GeoSms911" in message["body"] for message in sms)

    resolved = client.post(
        f"/api/alerts/{alert_id}",
        json={"status": "resolved", "note": "Ya esta en casa"},
        headers=guardian["headers"],
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    opened = client.get("/api/alerts?status=open", headers=guardian["headers"]).json()
    assert opened["alerts"] == []


def test_commands_round_trip(client, guardian, device):
    created = client.post(
        f"/api/devices/{device['id']}/commands",
        json={"kind": "locate"},
        headers=guardian["headers"],
    )
    assert created.status_code == 201, created.text
    command_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    polled = client.get("/api/ingest/commands?wait=1", headers=device["headers"])
    assert polled.status_code == 200
    commands = polled.json()["commands"]
    assert len(commands) == 1
    assert commands[0]["id"] == command_id
    assert commands[0]["status"] == "sent"

    ack = client.post(
        f"/api/ingest/commands/{command_id}/ack",
        json={
            "status": "acked",
            "result": {"lat": CASA["lat"], "lng": CASA["lng"], "accuracy": 8, "battery": 71},
        },
        headers=device["headers"],
    )
    assert ack.status_code == 200

    device_info = client.get(
        f"/api/devices/{device['id']}", headers=guardian["headers"]
    ).json()
    assert device_info["last_lat"] == CASA["lat"]
    assert device_info["last_battery"] == 71

    history = client.get(
        f"/api/devices/{device['id']}/commands", headers=guardian["headers"]
    ).json()["commands"]
    assert history[0]["status"] == "acked"


def test_geofence_exit_creates_alert(client, guardian, device):
    zone = client.post(
        "/api/geofences",
        json={"name": "Casa", "lat": CASA["lat"], "lng": CASA["lng"], "radius_m": 300},
        headers=guardian["headers"],
    )
    assert zone.status_code == 201, zone.text

    inside = client.post(
        "/api/ingest/location", json={**CASA, "battery": 60}, headers=device["headers"]
    )
    assert inside.status_code == 201

    outside = client.post(
        "/api/ingest/location", json={**LEJOS, "battery": 59}, headers=device["headers"]
    )
    assert outside.status_code == 201

    alerts = client.get("/api/alerts", headers=guardian["headers"]).json()["alerts"]
    kinds = [alert["kind"] for alert in alerts]
    assert "geofence_exit" in kinds

    zones = client.get("/api/geofences", headers=guardian["headers"]).json()["geofences"]
    assert zones[0]["last_state"] == "outside"


def test_second_guardian_cannot_access_other_devices(client, guardian, device):
    other = client.post(
        "/api/auth/register",
        json={
            "email": "otro@example.com",
            "name": "Otro tutor",
            "phone": "+59893333333",
            "password": "otra-contrasena-123",
        },
    )
    assert other.status_code == 201
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    assert client.get(f"/api/devices/{device['id']}", headers=headers).status_code == 404
    assert client.get("/api/devices", headers=headers).json()["devices"] == []
    assert client.get("/api/alerts", headers=headers).json()["alerts"] == []


def test_twilio_inbound_sms_queues_command(client, guardian, device, monkeypatch):
    configure_fake_twilio(monkeypatch)
    params = {
        "From": "+59891111111",
        "To": "+15005550006",
        "Body": "donde",
        "MessageSid": "SM123",
    }
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=twilio_signature(params),
    )
    assert response.status_code == 200, response.text
    assert "Buscando la ubicacion" in response.text

    commands = client.get(
        f"/api/devices/{device['id']}/commands", headers=guardian["headers"]
    ).json()["commands"]
    assert any(command["kind"] == "locate" for command in commands)

    inbound = client.get("/api/messages", headers=guardian["headers"]).json()["messages"]
    bodies = [message["body"] for message in inbound]
    assert "donde" in bodies


def test_twilio_inbound_sms_from_unknown_number(client, device, monkeypatch):
    configure_fake_twilio(monkeypatch)
    params = {"From": "+59899999999", "Body": "SOS", "MessageSid": "SM999"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=twilio_signature(params),
    )
    assert response.status_code == 200
    assert "no esta autorizado" in response.text


def test_twilio_webhooks_are_closed_without_configuration(client):
    """Sin Twilio configurado nadie puede inyectar SMS falsos."""
    response = client.post(
        "/webhooks/twilio/sms",
        data={"From": "+59891111111", "Body": "SOS", "MessageSid": "SM1"},
    )
    assert response.status_code == 403


def test_twilio_signature_is_enforced(client, monkeypatch):
    configure_fake_twilio(monkeypatch)

    response = client.post(
        "/webhooks/twilio/sms",
        data={"From": "+59891111111", "Body": "ESTADO", "MessageSid": "SM1"},
        headers={"X-Twilio-Signature": "firma-invalida"},
    )
    assert response.status_code == 403


def test_delete_account_removes_everything(client, guardian, device):
    location = client.post(
        "/api/ingest/location", json={**CASA, "battery": 50}, headers=device["headers"]
    )
    assert location.status_code == 201

    response = client.delete("/api/auth/me", headers=guardian["headers"])
    assert response.status_code == 200

    # El token deja de servir y las credenciales ya no existen.
    assert client.get("/api/devices", headers=guardian["headers"]).status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"email": "tutor@example.com", "password": "contrasena-segura-123"},
    )
    assert login.status_code == 401


def test_status_endpoint_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["twilio_configured"] is False
