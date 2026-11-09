"""SQLite persistence helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from research_manager.memory.models import Base

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "memory" / "experiments.db"
load_dotenv()


def get_engine(db_path: Path | None = None, database_url: str | None = None):
    url = database_url or os.getenv("RESEARCH_MANAGER_DATABASE_URL") or os.getenv("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return create_engine(url, echo=False, pool_pre_ping=True)

    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(db_path: Path | None = None) -> sessionmaker[Session]:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    # Lightweight migration for older DBs created before project_id columns.
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(experiments)")).fetchall()
            }
            if cols and "project_id" not in cols:
                raise RuntimeError(
                    "Database schema is outdated (experiments.project_id is missing). "
                    "Back up the database and run a proper migration before starting."
                )
    return sessionmaker(bind=engine, expire_on_commit=False)


def reset_db(db_path: Path | None = None) -> sessionmaker[Session]:
    engine = get_engine(db_path)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
