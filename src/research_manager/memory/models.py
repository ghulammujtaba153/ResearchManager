"""Persistent memory schema for Research Experiment Manager.

Authoritative store: SQLite (memory/experiments.db).
Excel/CSV exports are review views only and must never overwrite supervisor decisions.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    """Isolated research project / user namespace."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(128), default="researcher")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    experiments: Mapped[list[Experiment]] = relationship(back_populates="project")
    facts: Mapped[list[FactVersion]] = relationship(back_populates="project")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(64), default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="experiments")
    runs: Mapped[list[Run]] = relationship(back_populates="experiment")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("project_id", "run_key", name="uq_project_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    run_key: Mapped[str] = mapped_column(String(128))
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    artifacts_path: Mapped[str] = mapped_column(String(512), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    experiment: Mapped[Experiment] = relationship(back_populates="runs")
    decisions: Mapped[list[Decision]] = relationship(back_populates="run")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    decision_type: Mapped[str] = mapped_column(String(64))
    rationale: Mapped[str] = mapped_column(Text, default="")
    next_params_json: Mapped[str] = mapped_column(Text, default="{}")
    agent_suggested: Mapped[bool] = mapped_column(Boolean, default=True)
    supervisor_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    supervisor_comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped[Run] = relationship(back_populates="decisions")


class FactVersion(Base):
    """Versioned long-term facts (baselines, prefs, approved metric names).

    Later decisions must use is_current=True rows only. Superseded rows are retained.
    """

    __tablename__ = "fact_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    fact_key: Mapped[str] = mapped_column(String(128))
    value_json: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    approved_by: Mapped[str] = mapped_column(String(128), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="facts")


class Checkpoint(Base):
    """Working-state checkpoint for resume after process restart."""

    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    experiment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ActionLog(Base):
    """Append-only log of tool calls, memory R/W, outcomes, errors."""

    __tablename__ = "action_logs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_action_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(128), default="")
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    outcome: Mapped[str] = mapped_column(String(64), default="ok")
    error: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
