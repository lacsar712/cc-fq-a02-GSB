from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api import router
from app.database import Base, engine


def _ensure_gate_columns(target_engine=engine) -> None:
    """
    Lightweight idempotent migration: add gate columns to a pre-existing jobs
    table (create_all only creates missing tables, never alters existing ones).
    """
    inspector = inspect(target_engine)
    if "jobs" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("jobs")}
    is_pg = target_engine.dialect.name == "postgresql"
    wanted = {
        "gate_passed": "BOOLEAN" if is_pg else "BOOLEAN",
        "gate_violations": "JSON" if is_pg else "TEXT",
        "gate_thresholds": "JSON" if is_pg else "TEXT",
    }
    with target_engine.begin() as conn:
        for name, col_type in wanted.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {col_type}"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_gate_columns(engine)
    yield


app = FastAPI(title="FASTQ QC Pipeline Console", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
