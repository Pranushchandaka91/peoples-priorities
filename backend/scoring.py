"""
Scoring service — BUILD_BRIEF.md §3.

Wraps core.py's score_works/allocate UNCHANGED. The only modification the
brief allows: trust-adjusted need becomes an interval (need_low, need_high,
need_used) instead of a point, per §3's formula. Priority is then
recomputed with need_used substituted for the point need, using the exact
same weighted-sum formula core.py uses (not a new formula — core.py's,
re-applied once more here because it must run on the adjusted need).
"""
from datetime import date as date_cls

import pandas as pd
from sqlalchemy import func

import core
import divergence as dv
from models import Ward as WardModel, Work as WorkModel, Complaint, WeightAuditLog, Asset, Dispute, DisputeComplaint

DEFAULT_WEIGHTS = dict(w_demand=0.30, w_need=0.40, w_equity=0.20, w_cost=0.10)

WARD_COLUMNS = [
    "population", "literacy_pct", "smartphone_pct", "is_urban", "km_to_mp_office",
    "tap_coverage_pct", "toilet_coverage_pct", "km_to_phc", "dropout_pct",
    "km_to_school", "road_km_per_sqkm", "sc_st_pct",
]

SECTOR_EVIDENCE_FIELDS = {
    "water": ["tap_coverage_pct"],
    "sanitation": ["toilet_coverage_pct"],
    "health": ["km_to_phc"],
    "education": ["dropout_pct", "km_to_school"],
    "roads": ["road_km_per_sqkm"],
}


def current_weights(db) -> dict:
    row = (
        db.query(WeightAuditLog)
        .order_by(WeightAuditLog.changed_at.desc(), WeightAuditLog.id.desc())
        .first()
    )
    if row is None:
        return dict(DEFAULT_WEIGHTS)
    return dict(w_demand=row.w_demand, w_need=row.w_need, w_equity=row.w_equity, w_cost=row.w_cost)


def _wards_dataframe(db) -> pd.DataFrame:
    wards = db.query(WardModel).all()
    observed = dict(
        db.query(Complaint.ward_id, func.count(Complaint.complaint_id)).group_by(Complaint.ward_id).all()
    )
    rows = []
    for w in wards:
        row = {col: getattr(w, col) for col in WARD_COLUMNS}
        row["ward_id"] = w.ward_id
        row["observed_submissions"] = float(observed.get(w.ward_id, 0))
        rows.append(row)
    return pd.DataFrame(rows).set_index("ward_id")


def _works_list(db) -> list[core.Work]:
    rows = db.query(WorkModel).all()
    return [
        core.Work(
            id=w.work_id, name=w.name, ward_id=w.ward_id, sector=w.sector,
            cost_lakh=w.cost_lakh, beneficiaries=w.beneficiaries, source=w.source,
            cluster_submissions=w.cluster_submissions,
        )
        for w in rows
    ]


def score(db, weights: dict | None = None) -> pd.DataFrame:
    weights = weights or current_weights(db)
    wards_df = _wards_dataframe(db)
    works = _works_list(db)

    scored = core.score_works(
        works, wards_df,
        w_demand=weights["w_demand"], w_need=weights["w_need"],
        w_equity=weights["w_equity"], w_cost=weights["w_cost"],
    )

    need_low, need_high, need_used, flags_col = [], [], [], []
    for work_id, row in scored.iterrows():
        ward_id, sector = row["ward"], row["sector"]
        source = dv.informing_source(db, sector)
        t = dv.get_trust(db, source.source_id, ward_id) if source else dv.TRUST_CEILING
        point = float(row["need"])
        lo = point
        hi = point + (1 - t) * 0.5
        used = (lo + hi) / 2
        need_low.append(round(lo, 3))
        need_high.append(round(hi, 3))
        need_used.append(round(used, 3))
        flags_col.append(dv.data_flags(db, ward_id, sector))

    scored["need_low"] = need_low
    scored["need_high"] = need_high
    scored["need_used"] = need_used
    scored["data_flags"] = flags_col

    # Re-apply core.py's exact priority formula with need_used substituted
    # for the point need — the one allowed modification (§3).
    scored["priority"] = (
        weights["w_demand"] * scored["demand"]
        + weights["w_need"] * scored["need_used"]
        + weights["w_equity"] * scored["equity"]
        - weights["w_cost"] * scored["cost_pen"]
    ).round(4)

    return scored.sort_values("priority", ascending=False)


def allocate(scored: pd.DataFrame, budget_lakh: float) -> dict:
    return core.allocate(scored, budget_lakh)


def _work_disputes(db, ward_id: str, sector: str) -> list[dict]:
    disputes = (
        db.query(Dispute)
        .join(Asset, Dispute.asset_id == Asset.asset_id)
        .filter(Asset.ward_id == ward_id, Asset.sector == sector)
        .order_by(Dispute.created_at.asc())
        .all()
    )
    out = []
    for d in disputes:
        asset = db.query(Asset).filter_by(asset_id=d.asset_id).first()
        complaint = db.query(Complaint).filter_by(complaint_id=d.complaint_id).first()
        out.append(dict(
            asset_id=asset.asset_id,
            descriptor=asset.descriptor,
            reported_status=complaint.reported_status if complaint else None,
            weeks=complaint.duration_weeks if complaint else None,
            date=d.created_at.date().isoformat(),
        ))
    return out


def rationale_data(db, work_id: str, scored: pd.DataFrame, weights: dict) -> dict:
    """Structured rationale card — GET /works/{id}/rationale (§4)."""
    row = scored.loc[work_id]
    ward_id, sector = row["ward"], row["sector"]
    ward = db.query(WardModel).filter_by(ward_id=ward_id).first()
    rank = int((scored.index == work_id).argmax()) + 1

    sector_evidence = {f: getattr(ward, f) for f in SECTOR_EVIDENCE_FIELDS.get(sector, [])}

    return dict(
        rank=rank,
        name=row["name"],
        cost_lakh=float(row["cost"]),
        submissions=int(row["raw_submissions"]),
        correction_factor=float(row["correction"]),
        sector_evidence=sector_evidence,
        beneficiaries=int(row["beneficiaries"]),
        cost_per_beneficiary=float(row["cost_per_beneficiary"]),
        priority_breakdown=dict(
            demand=float(row["demand"]), need=float(row["need_used"]),
            equity=float(row["equity"]), cost_pen=float(row["cost_pen"]),
            weights=weights,
        ),
        disputes=_work_disputes(db, ward_id, sector),
    )
