"""Motor y sesiones de base de datos (SQLite por defecto)."""

from collections.abc import Generator

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - infraestructura
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def init_db() -> None:
    # Importar los modelos antes de crear las tablas.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def purge_old_locations() -> int:
    """Elimina puntos de ubicacion mas antiguos que la retencion configurada."""
    from .models import utcnow
    from datetime import timedelta

    cutoff = utcnow() - timedelta(days=settings.location_retention_days)
    with Session(engine) as session:
        result = session.execute(
            text("DELETE FROM location WHERE created_at < :cutoff"), {"cutoff": cutoff}
        )
        session.commit()
        return int(result.rowcount or 0)
