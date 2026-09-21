"""Unit tests for quality gate evaluation and threshold validation (no DB)."""

from app.gate import GateThresholds, evaluate_gate, validate_thresholds


def test_evaluate_gate_passes_when_within_thresholds():
    metrics = {"mean_quality": 35.2, "n_rate": 0.02}
    passed, violations = evaluate_gate(
        metrics, GateThresholds(mean_quality_min=20.0, n_rate_max=0.1)
    )
    assert passed is True
    assert violations == []


def test_evaluate_gate_flags_low_mean_quality():
    metrics = {"mean_quality": 18.5, "n_rate": 0.01}
    passed, violations = evaluate_gate(
        metrics, GateThresholds(mean_quality_min=20.0, n_rate_max=0.1)
    )
    assert passed is False
    assert len(violations) == 1
    assert violations[0]["field"] == "mean_quality"
    assert violations[0]["actual"] == 18.5
    assert violations[0]["threshold"] == 20.0
    assert "低于下限" in violations[0]["message"]


def test_evaluate_gate_flags_high_n_rate():
    metrics = {"mean_quality": 35.0, "n_rate": 0.25}
    passed, violations = evaluate_gate(
        metrics, GateThresholds(mean_quality_min=20.0, n_rate_max=0.1)
    )
    assert passed is False
    assert [v["field"] for v in violations] == ["n_rate"]
    assert "高于上限" in violations[0]["message"]


def test_evaluate_gate_flags_both_fields():
    metrics = {"mean_quality": 5.0, "n_rate": 0.9}
    passed, violations = evaluate_gate(
        metrics, GateThresholds(mean_quality_min=20.0, n_rate_max=0.1)
    )
    assert passed is False
    assert {v["field"] for v in violations} == {"mean_quality", "n_rate"}


def test_evaluate_gate_boundary_values_pass():
    # Equality is compliant: min is a lower bound (>=), max is an upper bound (<=).
    passed, _ = evaluate_gate(
        {"mean_quality": 20.0, "n_rate": 0.1},
        GateThresholds(mean_quality_min=20.0, n_rate_max=0.1),
    )
    assert passed is True


def test_validate_thresholds_accepts_valid_numbers():
    assert validate_thresholds(30, 0.05) == []
    assert validate_thresholds("25", "0.1") == []


def test_validate_thresholds_rejects_out_of_bounds_and_non_numbers():
    errors = validate_thresholds(100, 2)
    assert len(errors) == 2
    assert any("平均质量" in e for e in errors)
    assert any("N 率" in e for e in errors)

    errors = validate_thresholds("abc", None)
    assert len(errors) == 2

    # bool must not sneak through as a numeric threshold
    assert validate_thresholds(True, 0.1)
