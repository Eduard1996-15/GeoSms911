"""Esquemas de entrada de la API (validacion con Pydantic)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

CommandKind = Literal["locate", "ring", "stop_ring", "alert_screen", "call_parent", "sync"]
AlertKind = Literal["panic", "geofence_exit", "geofence_enter", "low_battery", "test"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str = Field(max_length=160)
    name: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=24)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Correo electronico invalido")
        return value


class LoginIn(BaseModel):
    email: str = Field(max_length=160)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().lower()


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=24)


class PairingCodeIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)


class DeviceRegisterIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)
    name: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=24)
    platform: str = Field(default="android", max_length=20)
    model_name: str | None = Field(default=None, max_length=80)
    app_version: str | None = Field(default=None, max_length=40)


class DevicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=24)
    location_sharing: bool | None = None
    emergency_number: str | None = Field(default=None, max_length=8)


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100_000)
    speed: float | None = Field(default=None, ge=0, le=400)
    bearing: float | None = Field(default=None, ge=0, le=360)
    battery: int | None = Field(default=None, ge=0, le=100)
    source: str = Field(default="app", max_length=20)
    captured_at: datetime | None = None


class LocationBatchIn(BaseModel):
    points: list[LocationIn] = Field(min_length=1, max_length=200)


class AlertIn(BaseModel):
    kind: AlertKind = "panic"
    message: str | None = Field(default=None, max_length=500)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100_000)
    battery: int | None = Field(default=None, ge=0, le=100)


class CommandIn(BaseModel):
    kind: CommandKind
    payload: dict[str, Any] = Field(default_factory=dict)


class CommandAckIn(BaseModel):
    status: Literal["acked", "failed", "done"] = "acked"
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=500)


class AlertUpdateIn(BaseModel):
    status: Literal["acknowledged", "resolved", "false_alarm"]
    note: str | None = Field(default=None, max_length=500)


class GeofenceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=300, ge=50, le=20_000)
    device_id: str | None = None
    notify_on_exit: bool = True
    enabled: bool = True


class GeofencePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    radius_m: int | None = Field(default=None, ge=50, le=20_000)
    notify_on_exit: bool | None = None
    enabled: bool | None = None


class HeartbeatIn(BaseModel):
    battery: int | None = Field(default=None, ge=0, le=100)
    app_version: str | None = Field(default=None, max_length=40)
    location_sharing: bool | None = None


class SmsTestIn(BaseModel):
    to: str | None = Field(default=None, max_length=24)
    body: str = Field(default="Prueba de GeoSms911", min_length=1, max_length=300)
