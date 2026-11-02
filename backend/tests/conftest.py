"""Configuracion de las pruebas: base de datos temporal y cliente de la API."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP_DIR = Path(tempfile.mkdtemp(prefix="geosms911-test-"))

os.environ["DATABASE_URL"] = f"sqlite:///{(TMP_DIR / 'test.db').as_posix()}"
os.environ["APP_SECRET"] = "clave-de-pruebas-suficientemente-larga-123456"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["TWILIO_AUTH_TOKEN"] = ""
os.environ["TWILIO_FROM_NUMBER"] = ""
os.environ["TWILIO_VALIDATE_SIGNATURE"] = "false"
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["SMS_FALLBACK_AFTER_SECONDS"] = "90"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import (  # noqa: E402
    command_limiter,
    login_limiter,
    pairing_limiter,
    register_limiter,
)

GUARDIAN = {
    "email": "tutor@example.com",
    "name": "Tutor de prueba",
    "phone": "+59891111111",
    "password": "contrasena-segura-123",
}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _fresh_state():
    for limiter in (login_limiter, register_limiter, pairing_limiter, command_limiter):
        limiter.reset()
    with Session(engine) as session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    yield


@pytest.fixture
def guardian(client):
    response = client.post("/api/auth/register", json=GUARDIAN)
    assert response.status_code == 201, response.text
    data = response.json()
    return {
        "token": data["access_token"],
        "user": data["user"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


@pytest.fixture
def device(client, guardian):
    code_response = client.post("/api/devices/pairing-code", json={}, headers=guardian["headers"])
    assert code_response.status_code == 200, code_response.text
    code = code_response.json()["code"]

    response = client.post(
        "/api/devices/register",
        json={
            "code": code,
            "name": "Telefono de Mateo",
            "phone": "+59892222222",
            "platform": "android",
            "model_name": "Pixel 6a",
            "app_version": "1.0.0",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return {
        "id": data["device_id"],
        "token": data["device_token"],
        "sms_secret": data["sms_secret"],
        "headers": {
            "X-Device-Id": data["device_id"],
            "X-Device-Token": data["device_token"],
        },
    }
