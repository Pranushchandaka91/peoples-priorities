"""
The divergence detector — BUILD_BRIEF.md §5.

Complaints that contradict official records generate disputes. Disputes
decay trust in the specific (source, ward) pair that produced the record.
Decayed trust later widens uncertainty on need scores (scoring.py) and,
past a threshold, spawns verification tasks for field staff to resolve.
"""
import json
from datetime import datetime, timedelta

from models import Asset, Complaint, Dispute, DisputeComplaint, SourceTrust, VerificationTask, Ward, DataSource

DISPUTE_TRUST_STEP = 0.07
TRUST_FLOOR = 0.3
TASK_THRESHOLD = 3
RESTORE_STEP = 0.15
TRUST_CEILING = 1.0

DUPLICATE_WINDOW_DAYS = 14
CONTRADICTING_STATUSES = ("not_working", "degraded")

# ward attribute each sector's ranking need is drawn from (core.py need_scores)
SECTOR_ATTR = {
    "water":      ("tap_coverage_pct", lambda w: f"{w.tap_coverage_pct:.0f}%"),
    "sanitation": ("toilet_coverage_pct", lambda w: f"{w.toilet_coverage_pct:.0f}%"),
    "health":     ("km_to_phc", lambda w: f"{w.km_to_phc:.1f}km"),
    "education":  ("dropout_pct", lambda w: f"{w.dropout_pct:.0f}%"),
    "roads":      ("road_km_per_sqkm", lambda w: f"{w.road_km_per_sqkm:.1f}km/sqkm"),
}


# ── trust lookup ─────────────────────────────────────────────────────────

def get_trust(db, source_id: str, ward_id: str) -> float:
    row = db.query(SourceTrust).filter_by(source_id=source_id, ward_id=ward_id).first()
    return row.trust if row else TRUST_CEILING


def _get_or_create_trust_row(db, source_id: str, ward_id: str) -> SourceTrust:
    row = db.query(SourceTrust).filter_by(source_id=source_id, ward_id=ward_id).first()
    if row is None:
        row = SourceTrust(source_id=source_id, ward_id=ward_id, trust=TRUST_CEILING)
        db.add(row)
        db.flush()
    return row


def informing_source(db, sector: str) -> DataSource | None:
    """Which data_source informs this sector — most specific match wins,
    ties broken by most recent as_of_date. (census covers every sector as
    a stale fallback; a sector-specific source like jal_jeevan wins over it.)
    """
    matches = [s for s in db.query(DataSource).all() if sector in json.loads(s.sectors)]
    if not matches:
        return None
    matches.sort(key=lambda s: (len(json.loads(s.sectors)), -s.as_of_date.toordinal()))
    return matches[0]


# ── step 1 + 2 + 3: complaint intake ─────────────────────────────────────

def _find_attachable_dispute(db, asset_id: str) -> Dispute | None:
    cutoff = datetime.utcnow() - timedelta(days=DUPLICATE_WINDOW_DAYS)
    return (
        db.query(Dispute)
        .filter(Dispute.asset_id == asset_id, Dispute.status == "open", Dispute.created_at >= cutoff)
        .order_by(Dispute.created_at.desc())
        .first()
    )


def _decay_trust(db, source_id: str, ward_id: str) -> None:
    row = _get_or_create_trust_row(db, source_id, ward_id)
    row.trust = max(TRUST_FLOOR, row.trust - DISPUTE_TRUST_STEP)


def _maybe_spawn_verification_tasks(db, ward_id: str, sector: str) -> None:
    open_disputes = (
        db.query(Dispute)
        .join(Asset, Dispute.asset_id == Asset.asset_id)
        .filter(Asset.ward_id == ward_id, Asset.sector == sector, Dispute.status == "open")
        .all()
    )
    if len(open_disputes) < TASK_THRESHOLD:
        return
    disputed_asset_ids = {d.asset_id for d in open_disputes}
    for asset_id in disputed_asset_ids:
        pending = db.query(VerificationTask).filter_by(asset_id=asset_id, status="pending").first()
        if not pending:
            db.add(VerificationTask(asset_id=asset_id, status="pending"))


def register_complaint(
    db, ward_id: str, sector: str, raw_text: str,
    asset_id: str | None = None, reported_status: str | None = None,
    duration_weeks: int | None = None,
) -> tuple[Complaint, bool]:
    """Insert a complaint; if it names an asset and contradicts the official
    record, fire the divergence detector (steps 1-3). Returns (complaint,
    dispute_created) — dispute_created is True whenever this complaint is
    associated with a dispute, whether newly opened or attached to an
    existing one."""
    complaint = Complaint(
        ward_id=ward_id, sector=sector, raw_text=raw_text, asset_id=asset_id,
        reported_status=reported_status, duration_weeks=duration_weeks,
    )
    db.add(complaint)
    db.flush()

    dispute_created = False
    if asset_id and reported_status in CONTRADICTING_STATUSES:
        asset = db.query(Asset).filter_by(asset_id=asset_id).first()
        if asset and asset.recorded_status == "functional":
            dispute_created = True
            existing = _find_attachable_dispute(db, asset_id)
            if existing:
                db.add(DisputeComplaint(dispute_id=existing.dispute_id, complaint_id=complaint.complaint_id))
            else:
                dispute = Dispute(asset_id=asset_id, complaint_id=complaint.complaint_id, status="open")
                db.add(dispute)
                db.flush()
                _decay_trust(db, asset.source_id, asset.ward_id)
                _maybe_spawn_verification_tasks(db, asset.ward_id, asset.sector)

    db.commit()
    db.refresh(complaint)
    return complaint, dispute_created


# ── step 4: task closure ─────────────────────────────────────────────────

def close_verification_task(db, task_id: str, outcome: str, note: str | None = None) -> VerificationTask:
    task = db.query(VerificationTask).filter_by(task_id=task_id).first()
    if task is None:
        raise ValueError(f"no such verification task: {task_id}")
    asset = db.query(Asset).filter_by(asset_id=task.asset_id).first()
    open_disputes = db.query(Dispute).filter_by(asset_id=asset.asset_id, status="open").all()

    if outcome == "confirmed_broken":
        for d in open_disputes:
            d.status = "verified_complaint_right"
        asset.recorded_status = "non_functional"
        # trust unchanged — the record was wrong; decay already applied stands
        task.status = "closed_disputed"
    elif outcome == "fixed":
        for d in open_disputes:
            d.status = "verified_record_right"
        row = _get_or_create_trust_row(db, asset.source_id, asset.ward_id)
        row.trust = min(TRUST_CEILING, row.trust + RESTORE_STEP)
        task.status = "closed_fixed"
    else:
        raise ValueError(f"unknown outcome: {outcome!r} (expected 'fixed' or 'confirmed_broken')")

    task.note = note
    db.commit()
    db.refresh(task)
    return task


# ── step 5: surfacing ─────────────────────────────────────────────────────

def _attribute_for_sector(db, ward_id: str, sector: str) -> tuple[str, str]:
    ward = db.query(Ward).filter_by(ward_id=ward_id).first()
    label, fmt = SECTOR_ATTR.get(sector, (sector, lambda w: "—"))
    return label, fmt(ward)


def data_flags(db, ward_id: str, sector: str) -> list[str]:
    """GET /ranking data_flags for a ward-sector whose informing source's
    trust has decayed below 0.9 (§5 step 5)."""
    source = informing_source(db, sector)
    if source is None:
        return []
    trust = get_trust(db, source.source_id, ward_id)
    if trust >= 0.9:
        return []

    disputes = (
        db.query(Dispute)
        .join(Asset, Dispute.asset_id == Asset.asset_id)
        .filter(Asset.ward_id == ward_id, Asset.sector == sector, Asset.source_id == source.source_id)
        .all()
    )
    if not disputes:
        return []

    n_reports = 0
    for d in disputes:
        n_reports += 1  # the complaint that opened the dispute
        n_reports += db.query(DisputeComplaint).filter_by(dispute_id=d.dispute_id).count()
    earliest = min(d.created_at for d in disputes)

    attribute, value = _attribute_for_sector(db, ward_id, sector)
    text = (
        f"{attribute} {value} per {source.name} ({source.as_of_date.year}) — "
        f"disputed by {n_reports} field reports since {earliest.date().isoformat()}"
    )
    return [text]
