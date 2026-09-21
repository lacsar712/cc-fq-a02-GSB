from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    is_broken: Mapped[bool] = mapped_column(Boolean, default=False)
    fastq_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"), nullable=True)
    sample_name: Mapped[str] = mapped_column(String(128), default="自定义输入")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fastq_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    stages: Mapped[list["JobStage"]] = relationship(
        "JobStage", back_populates="job", cascade="all, delete-orphan", order_by="JobStage.stage_order"
    )
    sample: Mapped[Sample | None] = relationship("Sample")


class JobStage(Base):
    __tablename__ = "job_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/running/success/failed/skipped
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship("Job", back_populates="stages")


class QualityGate(Base):
    """Singleton (id=1) quality-gate thresholds; updated by bioops only."""

    __tablename__ = "quality_gates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    min_mean_quality: Mapped[float] = mapped_column(Float, nullable=False)
    max_n_rate: Mapped[float] = mapped_column(Float, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), default="系统默认")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QualityGateViolation(Base):
    """One row per over-limit metric of a *successful* job (evaluated at finish time)."""

    __tablename__ = "quality_gate_violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    field: Mapped[str] = mapped_column(String(32), nullable=False)  # mean_quality / n_rate
    rule: Mapped[str] = mapped_column(String(8), nullable=False)  # min / max
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped[Job] = relationship("Job")
