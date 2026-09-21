from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class SampleOut(BaseModel):
    id: int
    name: str
    description: str
    is_broken: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    sampleId: int | None = None
    fastqText: str | None = Field(default=None, alias="fastqText")

    model_config = {"populate_by_name": True}


class StageOut(BaseModel):
    id: int
    actor_name: str
    stage_order: int
    status: str
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: int
    sample_id: int | None
    sample_name: str
    status: str
    created_by: str
    metrics: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    stages: list[StageOut] = []

    model_config = {"from_attributes": True}


class JobListItem(BaseModel):
    id: int
    sample_id: int | None
    sample_name: str
    status: str
    created_by: str
    metrics: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class HealthOut(BaseModel):
    status: str
    service: str


class QualityGateOut(BaseModel):
    min_mean_quality: float
    max_n_rate: float
    updated_by: str
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class QualityGateUpdate(BaseModel):
    min_mean_quality: float = Field(ge=0, le=93)
    max_n_rate: float = Field(ge=0, le=1)


class GateViolationDetailOut(BaseModel):
    field: str
    rule: str
    threshold_value: float
    actual_value: float
    message: str


class GateViolationOut(BaseModel):
    job_id: int
    sample_name: str
    created_by: str
    mean_quality: float | None
    n_rate: float | None
    violations: list[GateViolationDetailOut]
    message: str
    job_created_at: datetime
    triggered_at: datetime
