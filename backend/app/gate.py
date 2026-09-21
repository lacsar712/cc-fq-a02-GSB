"""Quality gate policy: thresholds, evaluation, and settings persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    DEFAULT_MEAN_QUALITY_MIN,
    DEFAULT_N_RATE_MAX,
    QualityGateChange,
    QualityGateSettings,
)

# Validation bounds for threshold updates.
MEAN_QUALITY_MIN_BOUNDS = (0.0, 93.0)
N_RATE_MAX_BOUNDS = (0.0, 1.0)


@dataclass(frozen=True)
class GateThresholds:
    mean_quality_min: float
    n_rate_max: float

    def as_dict(self) -> dict[str, float]:
        return {
            "mean_quality_min": self.mean_quality_min,
            "n_rate_max": self.n_rate_max,
        }


def get_thresholds(db: Session) -> GateThresholds:
    """Return current thresholds, creating the singleton row with defaults if absent."""
    row = db.query(QualityGateSettings).filter(QualityGateSettings.id == 1).first()
    if row is None:
        row = QualityGateSettings(
            id=1,
            mean_quality_min=DEFAULT_MEAN_QUALITY_MIN,
            n_rate_max=DEFAULT_N_RATE_MAX,
            updated_by="system",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return GateThresholds(
        mean_quality_min=row.mean_quality_min,
        n_rate_max=row.n_rate_max,
    )


def update_thresholds(
    db: Session, mean_quality_min: float, n_rate_max: float, changed_by: str
) -> GateThresholds:
    """Persist new thresholds and append a change-history record."""
    row = db.query(QualityGateSettings).filter(QualityGateSettings.id == 1).first()
    if row is None:
        row = QualityGateSettings(id=1, updated_by="system")
        db.add(row)
    row.mean_quality_min = mean_quality_min
    row.n_rate_max = n_rate_max
    row.updated_by = changed_by
    db.add(
        QualityGateChange(
            mean_quality_min=mean_quality_min,
            n_rate_max=n_rate_max,
            changed_by=changed_by,
        )
    )
    db.commit()
    db.refresh(row)
    return GateThresholds(row.mean_quality_min, row.n_rate_max)


def validate_thresholds(mean_quality_min: Any, n_rate_max: Any) -> list[str]:
    """Return human-readable validation errors; empty list means the values are valid."""
    errors: list[str] = []

    def _num(value: Any, label: str) -> float | None:
        if isinstance(value, bool):  # bool is an int subclass — reject explicitly
            errors.append(f"{label} 必须是数字")
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            errors.append(f"{label} 必须是数字")
            return None

    mq = _num(mean_quality_min, "平均质量下限")
    nr = _num(n_rate_max, "N 率上限")

    if mq is not None and not (MEAN_QUALITY_MIN_BOUNDS[0] <= mq <= MEAN_QUALITY_MIN_BOUNDS[1]):
        lo, hi = MEAN_QUALITY_MIN_BOUNDS
        errors.append(f"平均质量下限需在 {lo:g} ~ {hi:g} 之间")
    if nr is not None and not (N_RATE_MAX_BOUNDS[0] <= nr <= N_RATE_MAX_BOUNDS[1]):
        lo, hi = N_RATE_MAX_BOUNDS
        errors.append(f"N 率上限需在 {lo:g} ~ {hi:g} 之间")
    return errors


def evaluate_gate(
    metrics: dict[str, Any] | None, thresholds: GateThresholds
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Evaluate QC metrics against thresholds.

    Returns (passed, violations). Each violation describes one over-limit field,
    its actual value, the threshold it crossed, and a ready-to-show Chinese label.
    """
    violations: list[dict[str, Any]] = []
    if not metrics:
        return False, [
            {
                "field": "metrics",
                "label": "质控指标",
                "message": "作业未产出质控指标，无法判定门禁",
            }
        ]

    mean_quality = metrics.get("mean_quality")
    if mean_quality is not None and mean_quality < thresholds.mean_quality_min:
        violations.append(
            {
                "field": "mean_quality",
                "label": "平均质量分",
                "actual": mean_quality,
                "threshold": thresholds.mean_quality_min,
                "operator": "<",
                "message": (
                    f"平均质量分 {mean_quality} 低于下限 {thresholds.mean_quality_min:g}"
                ),
            }
        )

    n_rate = metrics.get("n_rate")
    if n_rate is not None and n_rate > thresholds.n_rate_max:
        violations.append(
            {
                "field": "n_rate",
                "label": "N 率",
                "actual": n_rate,
                "threshold": thresholds.n_rate_max,
                "operator": ">",
                "message": f"N 率 {n_rate} 高于上限 {thresholds.n_rate_max:g}",
            }
        )

    return len(violations) == 0, violations
