"""Utilidades de seguridad: contrasenas, tokens, autenticacion y limites."""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from .config import settings
from .db import get_session
from .models import Device, User, utcnow

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_access_token(user_id: str) -> tuple[str, int]:
    now = utcnow()
    expires = now + timedelta(minutes=settings.access_token_minutes)
    token = jwt.encode(
        {"sub": user_id, "iat": now, "exp": expires},
        settings.app_secret,
        algorithm="HS256",
    )
    return token, int(settings.access_token_minutes * 60)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.app_secret, algorithms=["HS256"])
        return str(payload.get("sub") or "") or None
    except jwt.PyJWTError:
        return None


bearer_scheme = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesion requerida")
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalido o vencido")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inexistente")
    return user


def current_device(
    x_device_id: str = Header(..., alias="X-Device-Id"),
    x_device_token: str = Header(..., alias="X-Device-Token"),
    session: Session = Depends(get_session),
) -> Device:
    device = session.get(Device, x_device_id)
    if device is None or device.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Dispositivo no autorizado")
    if not hmac.compare_digest(device.token_hash, sha256_hex(x_device_token)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de dispositivo invalido")
    device.last_seen_at = utcnow()
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


class SlidingWindowLimiter:
    """Limite simple en memoria, suficiente para un despliegue familiar."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


login_limiter = SlidingWindowLimiter(limit=10, window_seconds=300)
register_limiter = SlidingWindowLimiter(limit=10, window_seconds=3600)
pairing_limiter = SlidingWindowLimiter(limit=20, window_seconds=3600)
command_limiter = SlidingWindowLimiter(limit=60, window_seconds=60)
