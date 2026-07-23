"""
FastAPI app — BUILD_BRIEF.md §4 (API contract).
"""
import json
import os
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

import divergence as dv
import nlp
import scoring
from db import Base, engine, get_db
from models import (
    Asset, Complaint, Dispute, DisputeComplaint, SourceTrust, VerificationTask,
    WeightAuditLog, Ward,
)

DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
SEED_SNAPSHOT_PATH = "seed_snapshot.json"

app = FastAPI(title="People's Priorities")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Deliberately does no database work — Render needs the port bound
    immediately, and DATABASE_URL can point at a Postgres instance that
    isn't reachable yet. Tables are created and seeded via POST /admin/seed."""
    pass


@app.exception_handler(OperationalError)
@app.exception_handler(ProgrammingError)
async def db_not_initialized_handler(request: Request, exc):
    return JSONResponse(
        status_code=503,
        content={"detail": "database is not initialized — call POST /admin/seed"},
    )


@app.get("/config")
def get_config():
    """Lets the frontend discover whether demo-only affordances (reality
    peek, reset button) should render, without baking the flag into the
    frontend build."""
    return dict(demo_mode=DEMO_MODE)


# ── schemas ──────────────────────────────────────────────────────────────

class ComplaintIn(BaseModel):
    ward_id: str
    sector: str
    raw_text: str
    asset_id: str | None = None
    reported_status: Literal["not_working", "degraded"] | None = None
    duration_weeks: int | None = None


class VerificationCloseIn(BaseModel):
    outcome: Literal["fixed", "confirmed_broken"]
    note: str | None = None


class WeightsIn(BaseModel):
    w_demand: float
    w_need: float
    w_equity: float
    w_cost: float
    changed_by: str = "demo_user"


class ParseIn(BaseModel):
    raw_text: str


# ── §4: complaints ───────────────────────────────────────────────────────

@app.post("/complaints")
def post_complaint(body: ComplaintIn, db: Session = Depends(get_db)):
    complaint, dispute_created = dv.register_complaint(
        db, ward_id=body.ward_id, sector=body.sector, raw_text=body.raw_text,
        asset_id=body.asset_id, reported_status=body.reported_status,
        duration_weeks=body.duration_weeks,
    )
    return dict(
        complaint_id=complaint.complaint_id, ward_id=complaint.ward_id,
        sector=complaint.sector, raw_text=complaint.raw_text,
        asset_id=complaint.asset_id, reported_status=complaint.reported_status,
        duration_weeks=complaint.duration_weeks,
        created_at=complaint.created_at.isoformat(),
        dispute_created=dispute_created,
    )


# ── §4: ranking ──────────────────────────────────────────────────────────

@app.get("/ranking")
def get_ranking(budget_lakh: float = 200.0, db: Session = Depends(get_db)):
    scored = scoring.score(db)
    alloc = scoring.allocate(scored, budget_lakh)
    funded = set(alloc.get("funded", []))

    out = []
    for rank, (work_id, row) in enumerate(scored.iterrows(), start=1):
        out.append(dict(
            work_id=work_id, name=row["name"], ward_id=row["ward"], sector=row["sector"],
            cost_lakh=float(row["cost"]), beneficiaries=int(row["beneficiaries"]),
            demand=float(row["demand"]), need_low=float(row["need_low"]),
            need_high=float(row["need_high"]), need_used=float(row["need_used"]),
            equity=float(row["equity"]), cost_pen=float(row["cost_pen"]),
            priority=float(row["priority"]), funded=work_id in funded, rank=rank,
            data_flags=row["data_flags"],
        ))
    return out


# ── §4: rationale ────────────────────────────────────────────────────────

@app.get("/works/{work_id}/rationale")
def get_rationale(work_id: str, db: Session = Depends(get_db)):
    scored = scoring.score(db)
    if work_id not in scored.index:
        raise HTTPException(404, f"no such work: {work_id}")
    weights = scoring.current_weights(db)
    return scoring.rationale_data(db, work_id, scored, weights)


# Not in §4's endpoint list verbatim, but required by §6's intake form
# ("optional asset select, filtered by ward+sector"). actual_status (§9b's
# hidden reality layer) is never exposed here.
@app.get("/assets")
def get_assets(ward_id: str, sector: str, db: Session = Depends(get_db)):
    rows = db.query(Asset).filter_by(ward_id=ward_id, sector=sector).all()
    return [
        dict(asset_id=a.asset_id, descriptor=a.descriptor, kind=a.kind,
             recorded_status=a.recorded_status)
        for a in rows
    ]


# ── §4: disputes ─────────────────────────────────────────────────────────

@app.get("/disputes")
def get_disputes(ward_id: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Dispute).join(Asset, Dispute.asset_id == Asset.asset_id)
    if ward_id:
        q = q.filter(Asset.ward_id == ward_id)
    if status:
        q = q.filter(Dispute.status == status)
    out = []
    for d in q.order_by(Dispute.created_at.desc()).all():
        asset = db.query(Asset).filter_by(asset_id=d.asset_id).first()
        out.append(dict(
            dispute_id=d.dispute_id, asset_id=d.asset_id, ward_id=asset.ward_id,
            sector=asset.sector, descriptor=asset.descriptor,
            complaint_id=d.complaint_id, created_at=d.created_at.isoformat(),
            status=d.status,
        ))
    return out


# ── §4: verification tasks ───────────────────────────────────────────────

@app.get("/verification-tasks")
def get_verification_tasks(status: str | None = "pending", db: Session = Depends(get_db)):
    q = db.query(VerificationTask)
    if status:
        q = q.filter(VerificationTask.status == status)
    out = []
    for t in q.order_by(VerificationTask.created_at.asc()).all():
        asset = db.query(Asset).filter_by(asset_id=t.asset_id).first()
        open_disputes = db.query(Dispute).filter_by(asset_id=t.asset_id, status="open").count()
        out.append(dict(
            task_id=t.task_id, asset_id=t.asset_id, ward_id=asset.ward_id,
            sector=asset.sector, descriptor=asset.descriptor,
            created_at=t.created_at.isoformat(), status=t.status, note=t.note,
            dispute_count=open_disputes,
        ))
    return out


@app.post("/verification-tasks/{task_id}/close")
def close_verification_task(task_id: str, body: VerificationCloseIn, db: Session = Depends(get_db)):
    try:
        task = dv.close_verification_task(db, task_id, outcome=body.outcome, note=body.note)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return dict(task_id=task.task_id, status=task.status, note=task.note)


# ── §4: weights ──────────────────────────────────────────────────────────

@app.get("/weights")
def get_weights(db: Session = Depends(get_db)):
    current = scoring.current_weights(db)
    log = db.query(WeightAuditLog).order_by(WeightAuditLog.changed_at.asc(), WeightAuditLog.id.asc()).all()
    return dict(
        current=current,
        audit_log=[
            dict(id=r.id, changed_at=r.changed_at.isoformat(), w_demand=r.w_demand,
                 w_need=r.w_need, w_equity=r.w_equity, w_cost=r.w_cost, changed_by=r.changed_by)
            for r in log
        ],
    )


@app.post("/weights")
def post_weights(body: WeightsIn, db: Session = Depends(get_db)):
    total = body.w_demand + body.w_need + body.w_equity + body.w_cost
    if not (0.9 <= total <= 1.1):
        raise HTTPException(400, f"weights must sum to 0.9-1.1, got {total:.3f}")
    row = WeightAuditLog(
        w_demand=body.w_demand, w_need=body.w_need, w_equity=body.w_equity,
        w_cost=body.w_cost, changed_by=body.changed_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return dict(id=row.id, changed_at=row.changed_at.isoformat(), w_demand=row.w_demand,
               w_need=row.w_need, w_equity=row.w_equity, w_cost=row.w_cost,
               changed_by=row.changed_by)


# ── §9a: natural-language complaint extraction (live demo mode) ─────────

@app.post("/complaints/parse")
def post_parse_complaint(body: ParseIn, db: Session = Depends(get_db)):
    return nlp.parse_complaint(db, body.raw_text)


# ── §9b: hidden reality layer ────────────────────────────────────────────

@app.get("/admin/reality/{asset_id}")
def get_reality(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter_by(asset_id=asset_id).first()
    if asset is None:
        raise HTTPException(404, f"no such asset: {asset_id}")
    return dict(asset_id=asset.asset_id, actual_status=asset.actual_status)


# ── admin: schema + seed (deferred out of startup so the port binds) ────

@app.post("/admin/seed")
def post_admin_seed(db: Session = Depends(get_db)):
    print("admin/seed: entered", flush=True)
    if not DEMO_MODE:
        raise HTTPException(403, "seeding is only available in demo mode")

    print("admin/seed: before create_all", flush=True)
    Base.metadata.create_all(engine)

    print("admin/seed: before Ward count query", flush=True)
    needs_seed = db.query(Ward).count() == 0
    # Release this session's read transaction before seed() touches the
    # tables — otherwise its held lock blocks (and deadlocks against) the
    # writes seed() issues on this same connection.
    db.commit()
    print("admin/seed: read transaction committed", flush=True)
    if needs_seed:
        print("admin/seed: before import seed", flush=True)
        import seed
        print("admin/seed: after import seed", flush=True)
        print("admin/seed: before seed.seed(db)", flush=True)
        seed.seed(db)
        print("admin/seed: seed.seed(db) returned", flush=True)
        return dict(status="seeded")
    print("admin/seed: already_seeded, returning", flush=True)
    return dict(status="already_seeded")


# ── §9c: demo reset ──────────────────────────────────────────────────────

@app.post("/admin/reset")
def post_admin_reset(db: Session = Depends(get_db)):
    db.query(DisputeComplaint).delete()
    db.query(Dispute).delete()
    db.query(VerificationTask).delete()
    db.query(Complaint).delete()

    for row in db.query(SourceTrust).all():
        row.trust = 1.0

    if os.path.exists(SEED_SNAPSHOT_PATH):
        with open(SEED_SNAPSHOT_PATH) as f:
            snapshot = json.load(f)
        for asset in db.query(Asset).all():
            if asset.asset_id in snapshot:
                asset.recorded_status = snapshot[asset.asset_id]

    db.commit()
    return dict(status="reset")


@app.get("/health")
def health():
    return {"status": "ok"}
