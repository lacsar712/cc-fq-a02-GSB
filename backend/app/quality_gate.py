"""Quality-gate thresholds and over-limit evaluation.

A successful job whose metrics breach the current gate produces
QualityGateViolation rows. Threshold changes persist immediately and apply
to jobs that finish afterwards; they never retroactively re-judge history.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Job, QualityGate, QualityGateViolation

# Defaults chosen so the bundled good.fastq passes (mean_quality≈39.9, n_rate≈0.021).
DEFAULT_MIN_MEAN_QUALITY = 30.0
DEFAULT_MAX_N_RATE = 0.05

FIELD_MEAN_QUALITY = "mean_quality"
FIELD_N_RATE = "n_rate"

FIELD_LABELS = {
    FIELD_MEAN_QUALITY: "平均质量(mean_quality)",
    FIELD_N_RATE: "N 率(n_rate)",
}


def get_or_create_gate(db: Session) -> QualityGate:
    gate = db.query(QualityGate).filter(QualityGate.id == 1).first()
    if gate is None:
        gate = QualityGate(
            id=1,
            min_mean_quality=DEFAULT_MIN_MEAN_QUALITY,
            max_n_rate=DEFAULT_MAX_N_RATE,
            updated_by="系统默认",
        )
        db.add(gate)
        db.commit()
        db.refresh(gate)
    return gate


def evaluate_metrics(
    metrics: dict[str, Any] | None, gate: QualityGate
) -> list[dict[str, Any]]:
    """Return one descriptor per breached field; empty list means the job passes."""
    if not metrics:
        return []
    violations: list[dict[str, Any]] = []

    mean_quality = metrics.get(FIELD_MEAN_QUALITY)
    if isinstance(mean_quality, (int, float)) and mean_quality < gate.min_mean_quality:
        violations.append(
            {
                "field": FIELD_MEAN_QUALITY,
                "rule": "min",
                "threshold_value": gate.min_mean_quality,
                "actual_value": float(mean_quality),
            }
        )

    n_rate = metrics.get(FIELD_N_RATE)
    if isinstance(n_rate, (int, float)) and n_rate > gate.max_n_rate:
        violations.append(
            {
                "field": FIELD_N_RATE,
                "rule": "max",
                "threshold_value": gate.max_n_rate,
                "actual_value": float(n_rate),
            }
        )

    return violations


def record_violations(db: Session, job: Job, gate: QualityGate) -> list[QualityGateViolation]:
    """Evaluate a finished successful job and persist breaches (idempotent per job)."""
    db.query(QualityGateViolation).filter(
        QualityGateViolation.job_id == job.id
    ).delete(synchronize_session=False)

    rows: list[QualityGateViolation] = []
    for item in evaluate_metrics(job.metrics, gate):
        row = QualityGateViolation(job_id=job.id, **item)
        db.add(row)
        rows.append(row)
    return rows


def describe_violation(violation: QualityGateViolation) -> str:
    """Human-readable line for the dedicated gate list."""
    label = FIELD_LABELS.get(violation.field, violation.field)
    if violation.rule == "min":
        return (
            f"{label} 低于下限：实际 {violation.actual_value:g} "
            f"< 阈值 {violation.threshold_value:g}"
        )
    return (
        f"{label} 超过上限：实际 {violation.actual_value:g} "
        f"> 阈值 {violation.threshold_value:g}"
    )
