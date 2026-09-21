from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.auth import authenticate_user, create_access_token, get_current_user, require_bioops
from app.database import SessionLocal, get_db
from app.models import Job, JobStage, QualityGateViolation, Sample
from app.pipeline.runner import create_job_stages, run_pipeline_sync
from app.quality_gate import describe_violation, get_or_create_gate
from app.schemas import (
    GateViolationDetailOut,
    GateViolationOut,
    HealthOut,
    JobCreate,
    JobListItem,
    JobOut,
    LoginRequest,
    QualityGateOut,
    QualityGateUpdate,
    SampleOut,
    StageOut,
    TokenResponse,
)


router = APIRouter(prefix="/api")


def _run_job_background(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            run_pipeline_sync(db, job)
    finally:
        db.close()


@router.get("/health", response_model=HealthOut)
def health():
    return HealthOut(status="ok", service="fastq-qc-pipeline")


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = authenticate_user(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.get("/samples", response_model=list[SampleOut])
def list_samples(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Sample).order_by(Sample.id).all()


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobCreate,
    background: BackgroundTasks,
    user: dict = Depends(require_bioops),
    db: Session = Depends(get_db),
):
    sample_id = body.sampleId
    fastq_text = (body.fastqText or "").strip() if body.fastqText else ""
    sample_name = "自定义输入"
    sample = None

    if sample_id is not None:
        sample = db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            raise HTTPException(status_code=404, detail="样例不存在")
        fastq_text = sample.fastq_content
        sample_name = sample.name
    elif not fastq_text:
        raise HTTPException(status_code=400, detail="请提供 sampleId 或 fastqText")

    job = Job(
        sample_id=sample.id if sample else None,
        sample_name=sample_name,
        status="pending",
        created_by=user["username"],
        fastq_snapshot=fastq_text,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    create_job_stages(db, job.id)
    background.add_task(_run_job_background, job.id)

    job = (
        db.query(Job)
        .options(joinedload(Job.stages))
        .filter(Job.id == job.id)
        .first()
    )
    return job


@router.get("/jobs", response_model=list[JobListItem])
def list_jobs(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Job).order_by(Job.id.desc()).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(Job)
        .options(joinedload(Job.stages))
        .filter(Job.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    return job


@router.get("/jobs/{job_id}/stages", response_model=list[StageOut])
def get_job_stages(
    job_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    return (
        db.query(JobStage)
        .filter(JobStage.job_id == job_id)
        .order_by(JobStage.stage_order)
        .all()
    )


@router.get("/quality-gate", response_model=QualityGateOut)
def get_quality_gate(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_or_create_gate(db)


@router.put("/quality-gate", response_model=QualityGateOut)
def update_quality_gate(
    body: QualityGateUpdate,
    user: dict = Depends(require_bioops),
    db: Session = Depends(get_db),
):
    gate = get_or_create_gate(db)
    gate.min_mean_quality = body.min_mean_quality
    gate.max_n_rate = body.max_n_rate
    gate.updated_by = user["username"]
    db.commit()
    db.refresh(gate)
    return gate


@router.get("/quality-gate/violations", response_model=list[GateViolationOut])
def list_gate_violations(
    _user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Dedicated list: successful jobs that tripped the gate, grouped per job."""
    rows = (
        db.query(QualityGateViolation, Job)
        .join(Job, QualityGateViolation.job_id == Job.id)
        .order_by(QualityGateViolation.created_at.desc(), QualityGateViolation.id.desc())
        .all()
    )
    grouped: dict[int, GateViolationOut] = {}
    order: list[int] = []
    for v, job in rows:
        if job.id not in grouped:
            metrics = job.metrics or {}
            grouped[job.id] = GateViolationOut(
                job_id=job.id,
                sample_name=job.sample_name,
                created_by=job.created_by,
                mean_quality=metrics.get("mean_quality"),
                n_rate=metrics.get("n_rate"),
                violations=[],
                message="",
                job_created_at=job.created_at,
                triggered_at=v.created_at,
            )
            order.append(job.id)
        grouped[job.id].violations.append(
            GateViolationDetailOut(
                field=v.field,
                rule=v.rule,
                threshold_value=v.threshold_value,
                actual_value=v.actual_value,
                message=describe_violation(v),
            )
        )

    result: list[GateViolationOut] = []
    for job_id in order:
        item = grouped[job_id]
        item.message = "；".join(d.message for d in item.violations)
        result.append(item)
    return result
