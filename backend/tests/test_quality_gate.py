"""Quality-gate subsystem tests (API + DB, SQLite-backed TestClient)."""

from app.models import Job, QualityGateViolation
from app.pipeline.runner import create_job_stages, run_pipeline_sync
from app.quality_gate import (
    DEFAULT_MAX_N_RATE,
    DEFAULT_MIN_MEAN_QUALITY,
    get_or_create_gate,
)


GOOD_FASTQ = """@SEQ1
ACGTACGTACGTACGTACGT
+
IIIIIIIIIIIIIIIIIIII
@SEQ2
NNACGTACGTACGTACGTAC
+
HHIIIIIIIIIIIIIIIIII
"""
# 40 bases, 2 N → n_rate=0.05; mean Q=39.95 (I=40, H=39). Passes default gate.

HIGH_N_FASTQ = """@SEQ1
NNNNACGT
+
IIIIIIII
"""
# 8 bases, 4 N → n_rate=0.5.

BROKEN_FASTQ = """@SEQ1
ACGT
NOTPLUS
IIII
"""


def _submit_and_wait(client, headers, fastq_text=GOOD_FASTQ):
    resp = client.post("/api/jobs", headers=headers, json={"fastqText": fastq_text})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------- pure gate logic ----------

def test_default_thresholds_seeded(db_session_factory):
    db = db_session_factory()
    gate = get_or_create_gate(db)
    assert gate.id == 1
    assert gate.min_mean_quality == DEFAULT_MIN_MEAN_QUALITY
    assert gate.max_n_rate == DEFAULT_MAX_N_RATE
    assert gate.updated_by == "系统默认"
    # Idempotent singleton
    assert get_or_create_gate(db).id == gate.id
    db.close()


def test_gate_passes_and_trips(db_session_factory):
    db = db_session_factory()
    gate = get_or_create_gate(db)
    # good.fastq-like metrics: mean Q≈39.9, n_rate≈0.021 → pass
    assert not _evaluate({"mean_quality": 39.9, "n_rate": 0.021}, gate)
    # below mean floor trips mean_quality only
    v = _evaluate({"mean_quality": 25.0, "n_rate": 0.01}, gate)
    assert [x["field"] for x in v] == ["mean_quality"]
    # above N ceiling trips n_rate only
    v = _evaluate({"mean_quality": 35.0, "n_rate": 0.2}, gate)
    assert [x["field"] for x in v] == ["n_rate"]
    db.close()


def _evaluate(metrics, gate):
    from app.quality_gate import evaluate_metrics

    return evaluate_metrics(metrics, gate)


# ---------- end-to-end acceptance: raise floor, rerun, list shows the job ----------

def test_raise_floor_rerun_then_violation_listed(client, bioops_headers):
    # 1. Run good sample under default gate → successful but not on gate list
    job_id = _submit_and_wait(client, bioops_headers)
    detail = client.get(f"/api/jobs/{job_id}", headers=bioops_headers).json()
    assert detail["status"] == "success"
    mean_q = detail["metrics"]["mean_quality"]
    assert mean_q >= DEFAULT_MIN_MEAN_QUALITY

    violations = client.get("/api/quality-gate/violations", headers=bioops_headers).json()
    assert all(row["job_id"] != job_id for row in violations)

    # 2. Raise the average-quality floor above this sample's mean
    new_floor = round(mean_q + 1, 3)
    resp = client.put(
        "/api/quality-gate",
        headers=bioops_headers,
        json={"min_mean_quality": new_floor, "max_n_rate": DEFAULT_MAX_N_RATE},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["min_mean_quality"] == new_floor
    assert resp.json()["updated_by"] == "bioops"

    # 3. Rerun → the new job trips the gate and appears in the dedicated list
    rerun_id = _submit_and_wait(client, bioops_headers)
    rows = client.get("/api/quality-gate/violations", headers=bioops_headers).json()
    assert rerun_id in [row["job_id"] for row in rows]
    row = next(r for r in rows if r["job_id"] == rerun_id)
    assert row["mean_quality"] == mean_q
    fields = [v["field"] for v in row["violations"]]
    assert fields == ["mean_quality"]
    assert "mean_quality" in row["message"]
    assert "低于下限" in row["message"]
    # original passing job still absent
    assert job_id not in [r["job_id"] for r in rows]


def test_n_rate_ceiling_violation(client, bioops_headers):
    client.put(
        "/api/quality-gate",
        headers=bioops_headers,
        json={"min_mean_quality": 0.0, "max_n_rate": 0.1},
    )
    # HIGH_N_FASTQ has n_rate 0.5 → trips N ceiling
    job_id = _submit_and_wait(client, bioops_headers, fastq_text=HIGH_N_FASTQ)
    rows = client.get("/api/quality-gate/violations", headers=bioops_headers).json()
    row = next(r for r in rows if r["job_id"] == job_id)
    assert [v["field"] for v in row["violations"]] == ["n_rate"]
    assert "超过上限" in row["message"]


def test_failed_jobs_never_listed(client, bioops_headers):
    job_id = _submit_and_wait(client, bioops_headers, fastq_text=BROKEN_FASTQ)
    detail = client.get(f"/api/jobs/{job_id}", headers=bioops_headers).json()
    assert detail["status"] == "failed"
    rows = client.get("/api/quality-gate/violations", headers=bioops_headers).json()
    assert all(row["job_id"] != job_id for row in rows)


# ---------- RBAC: bioops edits, auditor only reads the list ----------

def test_auditor_can_read_gate_and_list_but_not_edit(client, auditor_headers):
    assert client.get("/api/quality-gate", headers=auditor_headers).status_code == 200
    assert client.get("/api/quality-gate/violations", headers=auditor_headers).status_code == 200
    resp = client.put(
        "/api/quality-gate",
        headers=auditor_headers,
        json={"min_mean_quality": 35, "max_n_rate": 0.05},
    )
    assert resp.status_code == 403


def test_auditor_cannot_submit_jobs(client, auditor_headers):
    resp = client.post(
        "/api/jobs", headers=auditor_headers, json={"fastqText": GOOD_FASTQ}
    )
    assert resp.status_code == 403


def test_gate_validation_bounds(client, bioops_headers):
    resp = client.put(
        "/api/quality-gate",
        headers=bioops_headers,
        json={"min_mean_quality": 99, "max_n_rate": 0.05},
    )
    assert resp.status_code == 422
    resp = client.put(
        "/api/quality-gate",
        headers=bioops_headers,
        json={"min_mean_quality": 30, "max_n_rate": 5},
    )
    assert resp.status_code == 422


# ---------- runner integration via direct DB (no HTTP) ----------

def test_runner_records_violation_rows(db_session_factory):
    db = db_session_factory()
    job = Job(
        sample_id=None,
        sample_name="自定义输入",
        status="pending",
        created_by="bioops",
        fastq_snapshot=GOOD_FASTQ,
    )
    db.add(job)
    db.commit()
    create_job_stages(db, job.id)
    gate = get_or_create_gate(db)
    gate.min_mean_quality = 99.0  # impossible floor
    gate.max_n_rate = 0.0
    db.commit()

    run_pipeline_sync(db, job)
    db.refresh(job)
    assert job.status == "success"
    violations = db.query(QualityGateViolation).filter(
        QualityGateViolation.job_id == job.id
    ).all()
    assert {v.field for v in violations} == {"mean_quality", "n_rate"}
    db.close()
