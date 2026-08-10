"""
Database engine and session management for the job-agent SQLite store.
"""
from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from server.config import settings

# Import models so SQLModel.metadata is aware of all tables before create_all().
from server.db import models  # noqa: F401

_engine = create_engine(
    f"sqlite:///{settings.DATABASE_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},  # MCP tools may run off the main thread
)


def init_db() -> None:
    """Creates all tables if they don't already exist. Safe to call repeatedly."""
    SQLModel.metadata.create_all(_engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Usage: `with get_session() as session: ...`"""
    session = Session(_engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
