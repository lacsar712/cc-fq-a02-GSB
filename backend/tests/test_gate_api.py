"""API integration tests for the quality gate subsystem (in-memory SQLite)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
import app.api as api_module
import app.main as main_module
from app.main import app


GOOD_FASTQ = """@SEQ1
ACGTACGT
+
IIIIHHHH
@SEQ2
NNNNACGT
+
IIIIIIII
"""

BROKEN_FASTQ = """@SEQ1
ACGT
NOTPLUS
IIII
"""


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Background pipeline tasks build their own session via app.api.SessionLocal.
    monkeypatch.setattr(api_module, "SessionLocal", TestingSession)
    # Lifespan runs create_all against the (real Postgres) module-level engine;
    # redirect it at the in-memory SQLite engine.
    monkeypatch.setattr(main_module, "engine", engine)

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(username, role):
    token = create_access_token(username, role)
    return {"Authorization": f"Bearer {token}"}


BIOOPS = _auth("bioops", "bioops")
AUDITOR = _auth("auditor", "auditor")


def test_settings_are_seeded_with_defaults(client):
    r = client.get("/api/gate/settings", headers=BIOOPS)
    assert r.status_code == 200
    data = r.json()
    assert data["mean_quality_min"] == 20.0
    assert data["n_rate_max"] == 0.10


def test_auditor_cannot_change_gate(client):
    r = client.put(
        "/api/gate/settings",
        headers=AUDITOR,
        json={"mean_quality_min": 30, "n_rate_max": 0.05},
    )
    assert r.status_code == 403


def test_bioops_change_is_persisted_and_invalid_input_rejected(client):
    r = client.put(
        "/api/gate/settings",
        headers=BIOOPS,
        json={"mean_quality_min": 42.5, "n_rate_max": 0.03},
    )
    assert r.status_code == 200
    assert r.json()["mean_quality_min"] == 42.5
    assert r.json()["updated_by"] == "bioops"

    # Re-fetch proves the change landed in the DB.
    again = client.get("/api/gate/settings", headers=AUDITOR).json()
    assert again["mean_quality_min"] == 42.5
    assert again["n_rate_max"] == 0.03

    bad = client.put(
        "/api/gate/settings",
        headers=BIOOPS,
        json={"mean_quality_min": 999, "n_rate_max": -1},
    )
    assert bad.status_code == 400


def _wait_finished(client, job_id):
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}", headers=BIOOPS).json()
        if job["status"] in ("success", "failed"):
            return job
    raise AssertionError("job did not finish")


def test_violation_list_only_shows_successful_jobs_tripping_gate(client):
    # Raise the mean-quality floor above GOOD_FASTQ's mean (39.75); keep N bound permissive.
    client.put(
        "/api/gate/settings",
        headers=BIOOPS,
        json={"mean_quality_min": 50, "n_rate_max": 1.0},
    )

    r = client.post("/api/jobs", headers=BIOOPS, json={"fastqText": GOOD_FASTQ})
    assert r.status_code == 201
    good_id = r.json()["id"]
    good_job = _wait_finished(client, good_id)
    assert good_job["status"] == "success"
    assert good_job["gate_passed"] is False
    assert [v["field"] for v in good_job["gate_violations"]] == ["mean_quality"]
    # Snapshot preserves the thresholds in force at run time.
    assert good_job["gate_thresholds"]["mean_quality_min"] == 50

    # Failed jobs never enter the gate list.
    r = client.post("/api/jobs", headers=BIOOPS, json={"fastqText": BROKEN_FASTQ})
    broken_id = r.json()["id"]
    broken_job = _wait_finished(client, broken_id)
    assert broken_job["status"] == "failed"
    assert broken_job["gate_passed"] is None

    vrows = client.get("/api/gate/violations", headers=AUDITOR).json()
    ids = {row["job_id"] for row in vrows}
    assert good_id in ids
    assert broken_id not in ids

    row = next(row for row in vrows if row["job_id"] == good_id)
    fields = {v["field"] for v in row["violations"]}
    assert fields == {"mean_quality"}
    assert row["mean_quality"] == 39.75


def test_compliant_job_is_absent_from_violation_list(client):
    # Permissive gate: GOOD_FASTQ trips nothing (mean 39.5, n_rate 0.25).
    client.put(
        "/api/gate/settings",
        headers=BIOOPS,
        json={"mean_quality_min": 0, "n_rate_max": 1.0},
    )
    r = client.post("/api/jobs", headers=BIOOPS, json={"fastqText": GOOD_FASTQ})
    job_id = r.json()["id"]
    job = _wait_finished(client, job_id)
    assert job["gate_passed"] is True

    vrows = client.get("/api/gate/violations", headers=BIOOPS).json()
    assert all(row["job_id"] != job_id for row in vrows)
