"""Endpoints que consume la app del telefono del menor."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlmodel import Session, select

from .. import serializers, services
from ..config import settings
from ..db import get_session
from ..events import bus
from ..models import Command, Device, utcnow
from ..schemas import AlertIn, CommandAckIn, HeartbeatIn, LocationBatchIn, LocationIn
from ..security import current_device

router = APIRouter(prefix="/api/ingest", tags=["ingesta"])

MAX_LONG_POLL_SECONDS = 25


@router.get("/me")
def device_me(device: Device = Depends(current_device)) -> dict:
    data = serializers.device_public(device)
    data.update(
        {
            "sms_secret": device.sms_secret,
            "sms_prefix": settings.sms_command_prefix,
            "poll_interval": 20,
            "server_time": serializers.iso_z(utcnow()),
        }
    )
    return data


@router.post("/heartbeat")
def heartbeat(
    payload: HeartbeatIn,
    device: Device = Depends(current_device),
    session: Session = Depends(get_session),
) -> dict:
    if payload.battery is not None:
        device.last_battery = payload.battery
    if payload.app_version:
        device.app_version = payload.app_version
    if payload.location_sharing is not None:
        device.location_sharing = payload.location_sharing
    device.last_seen_at = utcnow()
    session.add(device)
    session.commit()
    session.refresh(device)
    bus.publish("device", serializers.device_public(device) | {"user_id": device.user_id})
    return {"ok": True, "server_time": serializers.iso_z(utcnow())}


@router.post("/location", status_code=status.HTTP_201_CREATED)
def post_location(
    payload: LocationIn,
    device: Device = Depends(current_device),
    session: Session = Depends(get_session),
) -> dict:
    location = services.record_location(session, device, payload)
    return {"ok": True, "id": location.id, "created_at": serializers.iso_z(location.created_at)}


@router.post("/locations", status_code=status.HTTP_201_CREATED)
def post_locations(
    payload: LocationBatchIn,
    device: Device = Depends(current_device),
    session: Session = Depends(get_session),
) -> dict:
    stored = 0
    for index, point in enumerate(payload.points):
        services.record_location(session, device, point, commit=(index == len(payload.points) - 1))
        stored += 1
    return {"ok": True, "stored": stored}


@router.post("/alert", status_code=status.HTTP_201_CREATED)
def post_alert(
    payload: AlertIn,
    device: Device = Depends(current_device),
    session: Session = Depends(get_session),
) -> dict:
    alert = services.create_alert(session, device, payload)
    return {"ok": True, "alert": serializers.alert_public(alert, device.name)}


@router.get("/commands")
def pending_commands(
    wait: int = Query(default=0, ge=0, le=MAX_LONG_POLL_SECONDS),
    device: Device = Depends(current_device),
    session: Session = Depends(get_session),
) -> dict:
    """Long-poll: mantiene la conexion abierta hasta que haya una orden."""
    deadline = time.monotonic() + wait
    commands: list[Command] = []

    while True:
        commands = list(
            session.exec(
                select(Command)
                .where(Command.device_id == device.id, Command.status == "pending")
                .order_by(Command.created_at.asc())
                .limit(20)
            ).all()
        )
        if commands or time.monotonic() >= deadline:
            break
        time.sleep(1.2)
        session.expire_all()

    for command in commands:
        command.status = "sent"
        command.sent_at = utcnow()
        command.channel = command.channel or "poll"
        session.add(command)
    if commands:
        session.commit()
        for command in commands:
            session.refresh(command)
            bus.publish(
                "command", serializers.command_public(command) | {"user_id": device.user_id}
            )

    return {
        "commands": [serializers.command_public(command) for command in commands],
        "poll_interval": 20,
        "server_time": serializers.iso_z(utcnow()),
    }


@router.post("/commands/{command_id}/ack")
def ack_command(
    command_id: str,
    payload: CommandAckIn,
    device: Device = Depends(current_device),
    session: Session = Depends(get_session),
) -> dict:
    command = session.get(Command, command_id)
    if command is None or command.device_id != device.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Orden no encontrada")

    if payload.status == "failed":
        command.status = "failed"
        command.error = payload.error
    else:
        command.status = "acked"
    command.acked_at = utcnow()
    command.result = payload.result
    session.add(command)
    session.commit()
    session.refresh(command)

    if payload.result:
        try:
            lat = payload.result.get("lat")
            lng = payload.result.get("lng")
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                services.record_location(
                    session,
                    device,
                    LocationIn(
                        lat=float(lat),
                        lng=float(lng),
                        accuracy=payload.result.get("accuracy"),
                        battery=payload.result.get("battery"),
                        source="command",
                    ),
                )
        except (ValidationError, TypeError):
            pass

    bus.publish("command", serializers.command_public(command) | {"user_id": device.user_id})
    return {"ok": True}
