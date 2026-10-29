"""SQLite persistence helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from research_manager.memory.models import Base

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "memory" / "experiments.db"


def get_engine(db_path: Path | None = None):
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", echo=False)


def init_db(db_path: Path | None = None) -> sessionmaker[Session]:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    # Lightweight migration for older DBs created before project_id columns.
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(experiments)")).fetchall()}
        if cols and "project_id" not in cols:
            # Recreate is safer for course demo; wipe and rebuild schema.
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def reset_db(db_path: Path | None = None) -> sessionmaker[Session]:
    engine = get_engine(db_path)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
