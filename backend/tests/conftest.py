"""Pytest fixtures: isolated in-memory SQLite behind FastAPI TestClient."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")

import app.api as api_mod
from app.database import Base
from app.main import app


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield testing_session
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session_factory):
    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    # Background pipeline task uses SessionLocal imported into app.api
    original_session_local = api_mod.SessionLocal
    api_mod.SessionLocal = db_session_factory
    app.dependency_overrides[api_mod.get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        api_mod.SessionLocal = original_session_local
        app.dependency_overrides.clear()


@pytest.fixture()
def bioops_headers(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "bioops", "password": "fastq123456"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def auditor_headers(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": "auditor", "password": "audit123456"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
