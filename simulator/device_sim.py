#!/usr/bin/env python3
"""Simulador del telefono del menor.

Sirve para probar todo el flujo (emparejamiento, ubicacion, ordenes y panico)
sin necesidad de un telefono Android ni de credenciales de Twilio.

Ejemplos:
    python simulator/device_sim.py --code 123456 --panic
    python simulator/device_sim.py --code 123456 --lat -34.9011 --lng -56.1645
    python simulator/device_sim.py --code 123456 --no-walk --interval 30
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from pathlib import Path

import httpx

STATE_FILE = Path(__file__).resolve().parent / ".device.json"


def log(message: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def save_state(data: dict) -> None:
    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        STATE_FILE.chmod(0o600)
    except OSError:
        pass


def load_state() -> dict | None:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def pair(client: httpx.Client, code: str, name: str, phone: str | None) -> dict:
    payload = {
        "code": code,
        "name": name,
        "platform": "simulator",
        "model_name": "Simulador Python",
        "app_version": "1.0.0",
    }
    if phone:
        payload["phone"] = phone
    response = client.post("/api/devices/register", json=payload)
    if response.status_code != 201:
        raise SystemExit(f"No se pudo emparejar: {response.status_code} {response.text}")
    return response.json()


def build_client(server: str, credentials: dict) -> httpx.Client:
    return httpx.Client(
        base_url=server.rstrip("/"),
        timeout=httpx.Timeout(40.0, connect=10.0),
        headers={
            "X-Device-Id": credentials["device_id"],
            "X-Device-Token": credentials["device_token"],
        },
    )


def send_location(client: httpx.Client, lat: float, lng: float, battery: int) -> bool:
    try:
        response = client.post(
            "/api/ingest/location",
            json={
                "lat": lat,
                "lng": lng,
                "accuracy": random.uniform(5, 25),
                "speed": random.uniform(0, 1.5),
                "battery": battery,
                "source": "simulator",
            },
        )
    except httpx.HTTPError as exc:
        log(f"Sin conexion con el servidor: {exc}")
        return False
    if response.status_code not in (200, 201):
        log(f"Error al enviar ubicacion: {response.status_code} {response.text[:120]}")
        return False
    return True


def send_alert(client: httpx.Client, lat: float, lng: float, battery: int) -> None:
    try:
        response = client.post(
            "/api/ingest/alert",
            json={
                "kind": "panic",
                "message": "Boton de panico activado desde el simulador",
                "lat": lat,
                "lng": lng,
                "battery": battery,
            },
        )
    except httpx.HTTPError as exc:
        log(f"Sin conexion con el servidor: {exc}")
        return
    if response.status_code == 201:
        log("ALERTA DE PANICO enviada correctamente")
    else:
        log(f"Error al enviar alerta: {response.status_code} {response.text[:120]}")


def command_worker(
    client: httpx.Client,
    credentials: dict,
    position: dict,
    battery: dict,
    stop: threading.Event,
) -> None:
    """Consulta ordenes con long-poll y responde como lo haria la app Android."""
    while not stop.is_set():
        try:
            response = client.get("/api/ingest/commands", params={"wait": 20})
        except httpx.HTTPError as exc:
            log(f"Sin conexion con el servidor: {exc}")
            stop.wait(5)
            continue

        if response.status_code != 200:
            log(f"Error al consultar ordenes: {response.status_code}")
            stop.wait(5)
            continue

        for command in response.json().get("commands", []):
            kind = command["kind"]
            log(f"Orden recibida: {kind} ({command['id']})")
            result: dict = {}
            status = "acked"

            if kind == "locate":
                send_location(client, position["lat"], position["lng"], battery["level"])
                result = {
                    "lat": position["lat"],
                    "lng": position["lng"],
                    "accuracy": 9.5,
                    "battery": battery["level"],
                }
            elif kind == "ring":
                log("  >> TIMBRE SONANDO (simulado) durante 5 segundos")
                time.sleep(5)
                log("  >> Timbre detenido")
            elif kind == "stop_ring":
                log("  >> Timbre silenciado")
            elif kind == "alert_screen":
                log("  >> Pantalla de emergencia mostrada (simulada)")
            elif kind == "call_parent":
                log("  >> Llamada al tutor sugerida en pantalla")
            elif kind == "sync":
                send_location(client, position["lat"], position["lng"], battery["level"])

            try:
                client.post(
                    f"/api/ingest/commands/{command['id']}/ack",
                    json={"status": status, "result": result},
                )
            except httpx.HTTPError as exc:
                log(f"No se pudo confirmar la orden: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulador del telefono de GeoSms911")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="URL del backend")
    parser.add_argument("--code", help="Codigo de emparejamiento de 6 digitos")
    parser.add_argument("--name", default="Telefono simulado", help="Nombre del dispositivo")
    parser.add_argument("--phone", default=None, help="Numero del telefono simulado (E.164)")
    parser.add_argument("--lat", type=float, default=-34.9011, help="Latitud inicial")
    parser.add_argument("--lng", type=float, default=-56.1645, help="Longitud inicial")
    parser.add_argument("--interval", type=int, default=15, help="Segundos entre ubicaciones")
    parser.add_argument("--battery", type=int, default=78, help="Bateria inicial")
    parser.add_argument("--no-walk", action="store_true", help="No simular movimiento")
    parser.add_argument("--panic", action="store_true", help="Enviar una alerta de panico al iniciar")
    parser.add_argument("--once", action="store_true", help="Enviar un solo punto y salir")
    parser.add_argument("--reset", action="store_true", help="Olvidar credenciales guardadas")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()

    credentials = None if args.code else load_state()
    with httpx.Client(base_url=args.server.rstrip("/"), timeout=20.0) as bootstrap:
        if credentials is None:
            if not args.code:
                print(
                    "No hay credenciales guardadas.\n"
                    "Genera un codigo en el dashboard (Emparejar) y ejecuta:\n"
                    "  python simulator/device_sim.py --code 123456 --panic",
                    file=sys.stderr,
                )
                return 1
            log(f"Emparejando con {args.server}…")
            credentials = pair(bootstrap, args.code, args.name, args.phone)
            save_state(credentials)
            log(f"Emparejado. device_id={credentials['device_id']}")
        else:
            log(f"Usando credenciales guardadas: {credentials['device_id']}")

    client = build_client(args.server, credentials)
    position = {"lat": args.lat, "lng": args.lng}
    battery = {"level": max(1, min(100, args.battery))}

    log(f"Servidor: {args.server} | envio cada {args.interval}s | Ctrl+C para salir")
    send_location(client, position["lat"], position["lng"], battery["level"])

    if args.panic:
        send_alert(client, position["lat"], position["lng"], battery["level"])

    if args.once:
        client.close()
        return 0

    stop = threading.Event()
    worker = threading.Thread(
        target=command_worker,
        args=(client, credentials, position, battery, stop),
        daemon=True,
    )
    worker.start()

    try:
        while True:
            time.sleep(max(3, args.interval))
            if not args.no_walk:
                position["lat"] += random.uniform(-0.00035, 0.00035)
                position["lng"] += random.uniform(-0.00035, 0.00035)
            battery["level"] = max(3, battery["level"] - 1)
            send_location(client, position["lat"], position["lng"], battery["level"])
            log(
                f"Ubicacion enviada: {position['lat']:.5f}, {position['lng']:.5f} "
                f"(bateria {battery['level']}%)"
            )
    except KeyboardInterrupt:
        log("Cerrando simulador…")
    finally:
        stop.set()
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
