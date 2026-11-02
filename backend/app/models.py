"""Modelos de datos de GeoSms911."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index, Text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Hora UTC sin zona horaria (SQLite la almacena tal cual)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return secrets.token_hex(8)


class User(SQLModel, table=True):
    """Tutor / padre / madre que opera el dashboard."""

    id: str = Field(default_factory=new_id, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str
    phone: Optional[str] = Field(default=None, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow)


class Device(SQLModel, table=True):
    """Telefono del menor, emparejado mediante un codigo."""

    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    name: str = Field(default="Telefono")
    phone: Optional[str] = Field(default=None, index=True)
    platform: str = Field(default="android")
    model_name: Optional[str] = None
    app_version: Optional[str] = None

    token_hash: str
    sms_secret: str = Field(default_factory=lambda: secrets.token_hex(4).upper())

    location_sharing: bool = Field(default=True)
    emergency_number: str = Field(default="911")

    last_seen_at: Optional[datetime] = Field(default=None, index=True)
    last_location_at: Optional[datetime] = None
    last_lat: Optional[float] = None
    last_lng: Optional[float] = None
    last_accuracy: Optional[float] = None
    last_battery: Optional[int] = None
    last_speed: Optional[float] = None

    created_at: datetime = Field(default_factory=utcnow)
    revoked_at: Optional[datetime] = None

    @property
    def is_online(self) -> bool:
        return bool(
            self.last_seen_at is not None
            and (utcnow() - self.last_seen_at).total_seconds() <= 120
        )


class Location(SQLModel, table=True):
    __table_args__ = (Index("ix_location_device_created", "device_id", "created_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True, foreign_key="device.id")
    lat: float
    lng: float
    accuracy: Optional[float] = None
    speed: Optional[float] = None
    bearing: Optional[float] = None
    battery: Optional[int] = None
    source: str = Field(default="app")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Alert(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    device_id: str = Field(index=True, foreign_key="device.id")
    kind: str = Field(default="panic")  # panic | geofence_exit | geofence_enter | low_battery | test
    status: str = Field(default="open", index=True)  # open | acknowledged | resolved | false_alarm
    message: Optional[str] = Field(default=None, sa_column=Column(Text))
    lat: Optional[float] = None
    lng: Optional[float] = None
    accuracy: Optional[float] = None
    battery: Optional[int] = None
    notified: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    ack_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


class Command(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    device_id: str = Field(index=True, foreign_key="device.id")
    kind: str  # locate | ring | stop_ring | alert_screen | call_parent | sync | test
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="pending", index=True)  # pending | sent | acked | failed | expired
    channel: Optional[str] = None  # poll | sms
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
    sent_at: Optional[datetime] = None
    acked_at: Optional[datetime] = None
    result: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None


class Geofence(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    device_id: Optional[str] = Field(default=None, index=True, foreign_key="device.id")
    name: str
    lat: float
    lng: float
    radius_m: int = Field(default=300)
    notify_on_exit: bool = Field(default=True)
    enabled: bool = Field(default=True)
    last_state: Optional[str] = None  # inside | outside
    created_at: datetime = Field(default_factory=utcnow)


class MessageLog(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: Optional[str] = Field(default=None, index=True, foreign_key="user.id")
    device_id: Optional[str] = Field(default=None, index=True, foreign_key="device.id")
    direction: str = Field(default="outbound")  # outbound | inbound
    to: Optional[str] = None
    from_number: Optional[str] = None
    body: str = Field(default="", sa_column=Column(Text, nullable=False))
    provider: str = Field(default="twilio")
    sid: Optional[str] = None
    status: str = Field(default="queued")  # queued | sent | delivered | failed | received | logged
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)


class PairingCode(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    code: str = Field(index=True)
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[str] = Field(default=None, index=True)
    actor: str = Field(default="system")
    action: str
    detail: Optional[str] = Field(default=None, sa_column=Column(Text))
    ip: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
