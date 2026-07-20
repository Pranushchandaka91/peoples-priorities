"""
Seed script — BUILD_BRIEF.md §2.

Wards + tap/toilet/phc/dropout/school/road/scst columns are copied verbatim
from demo.py's ward table (which itself matches generate.py's WARDS on the
columns they share). Complaints come straight out of generate.py's
generator, inserted as legacy free-text (no asset link). Works are the 8
candidates from demo.py, verbatim. W14 gets 11 water assets recorded
'functional' whose ground truth is broken — the divergence demo's trap.
"""
import json
import random
from datetime import date

from db import Base, engine, SessionLocal
from models import (
    Ward, DataSource, Asset, Complaint, Work, SourceTrust, WeightAuditLog,
)
import generate as gen

random.seed(42)

SNAPSHOT_PATH = "seed_snapshot.json"

# ── wards — demo.py's ward table verbatim ───────────────────────────────
WARDS = [
    # id      pop    lit  phone urban km_off  tap  toilet  phc  drop school road scst
    ["W07", 12000, 82, 78, True, 3, 94, 91, 1.2, 6, 1.1, 4.2, 12],
    ["W11", 9500, 74, 66, True, 7, 88, 84, 2.1, 9, 1.8, 3.4, 19],
    ["W14", 10500, 61, 47, False, 18, 61, 58, 5.4, 18, 8.4, 1.9, 34],
    ["W19", 7200, 55, 38, False, 26, 40, 44, 7.8, 21, 9.6, 1.2, 41],
    ["W22", 9000, 51, 31, False, 31, 22, 37, 9.1, 24, 7.2, 0.9, 58],
    ["W26", 6100, 68, 58, False, 12, 77, 71, 3.3, 12, 4.0, 2.6, 22],
]
WARD_COLUMNS = [
    "ward_id", "population", "literacy_pct", "smartphone_pct", "is_urban",
    "km_to_mp_office", "tap_coverage_pct", "toilet_coverage_pct", "km_to_phc",
    "dropout_pct", "km_to_school", "road_km_per_sqkm", "sc_st_pct",
]

# ── data sources ─────────────────────────────────────────────────────────
DATA_SOURCES = [
    dict(source_id="jal_jeevan", name="Jal Jeevan Mission", sectors=["water"],
         as_of_date=date(2022, 6, 1)),
    dict(source_id="udise", name="UDISE+", sectors=["education"],
         as_of_date=date(2023, 9, 1)),
    dict(source_id="census", name="Census of India",
         sectors=["water", "health", "education", "roads", "sanitation", "drainage"],
         as_of_date=date(2011, 3, 1)),
]

SECTOR_SOURCE = {
    "water": "jal_jeevan", "education": "udise",
    "health": "census", "roads": "census", "sanitation": "census", "drainage": "census",
}

SECTOR_KINDS = {
    "water": ["handpump", "borewell", "tap_stand"],
    "health": ["phc", "sub_center"],
    "education": ["school"],
    "roads": ["road_segment"],
    "sanitation": ["toilet_block"],
    "drainage": ["storm_drain"],
}
LOCATION_PHRASES = [
    "near primary school, north side", "behind panchayat office", "main road junction",
    "colony centre, near temple", "outskirts, past the canal", "bus stand approach road",
    "market road", "near the old well", "hamlet on the hill side", "south colony",
    "near community hall", "opposite the health sub-centre",
]

SECTORS = ["water", "health", "education", "roads", "sanitation", "drainage"]

# ── works — demo.py's 8 candidates, verbatim ────────────────────────────
WORKS = [
    dict(work_id="A", name="Bridge over canal", ward_id="W07", sector="roads",
         cost_lakh=120, beneficiaries=8000, source="development_plan", cluster_submissions=96),
    dict(work_id="B", name="Upgrade Govt High School", ward_id="W14", sector="education",
         cost_lakh=42, beneficiaries=1240, source="development_plan", cluster_submissions=47),
    dict(work_id="C", name="Water pipeline + 3 borewells", ward_id="W22", sector="water",
         cost_lakh=70, beneficiaries=8200, source="derived_from_cluster", cluster_submissions=4),
    dict(work_id="D", name="PHC equipment upgrade", ward_id="W11", sector="health",
         cost_lakh=50, beneficiaries=6400, source="development_plan", cluster_submissions=61),
    dict(work_id="E", name="Vocational training centre", ward_id="W14", sector="livelihood",
         cost_lakh=50, beneficiaries=180, source="development_plan", cluster_submissions=3),
    dict(work_id="F", name="Storm drains, market road", ward_id="W07", sector="drainage",
         cost_lakh=35, beneficiaries=5200, source="development_plan", cluster_submissions=74),
    dict(work_id="G", name="Link road to block HQ", ward_id="W19", sector="roads",
         cost_lakh=65, beneficiaries=4100, source="derived_from_cluster", cluster_submissions=11),
    dict(work_id="H", name="Toilets + water, 4 schools", ward_id="W22", sector="sanitation",
         cost_lakh=28, beneficiaries=2600, source="derived_from_cluster", cluster_submissions=2),
    # Not in demo.py's original 8 — added so the ranking table has a W14+water
    # row at all (§7's acceptance script exercises the point→range need
    # transition on "W14 water", which none of the verbatim 8 works cover).
    dict(work_id="I", name="W14 water system repairs", ward_id="W14", sector="water",
         cost_lakh=18, beneficiaries=3100, source="derived_from_cluster", cluster_submissions=5),
]


def _make_assets_for_ward(ward_id: str, n_per_sector_pool: int) -> list[dict]:
    """8-12 assets spread across sectors, ~85% recorded functional. Ground
    truth (§9b, actual_status) seeded so every ward-sector has demo-able
    material: ~70% honest, ~20% stale-broken, ~10% honestly non-functional."""
    assets = []
    n_total = random.randint(8, 12)
    idx = 0
    while len(assets) < n_total:
        sector = SECTORS[idx % len(SECTORS)]
        idx += 1
        kind = random.choice(SECTOR_KINDS[sector])
        descriptor = f"{kind.replace('_', ' ')} {random.choice(LOCATION_PHRASES)}"
        roll = random.random()
        if roll < 0.85:
            recorded = "functional"
        else:
            recorded = "non_functional"

        truth_roll = random.random()
        if recorded == "non_functional":
            actual = "non_functional"  # honestly non-functional
        elif truth_roll < 0.20 / 0.85:
            actual = "non_functional"  # stale record — divergence material
        else:
            actual = "functional"

        assets.append(dict(
            asset_id=f"{ward_id}-{sector[:3].upper()}-{len(assets)+1:02d}",
            ward_id=ward_id, sector=sector, kind=kind, descriptor=descriptor,
            recorded_status=recorded, source_id=SECTOR_SOURCE[sector], actual_status=actual,
        ))
    return assets


def _w14_water_trap() -> list[dict]:
    """The demo centerpiece: 11 W14 water assets recorded 'functional'
    whose reality is broken. Complaints against these fire the detector."""
    assets = []
    for i in range(11):
        kind = random.choice(SECTOR_KINDS["water"])
        descriptor = f"{kind.replace('_', ' ')} {random.choice(LOCATION_PHRASES)}"
        assets.append(dict(
            asset_id=f"W14-WTR-{i+1:02d}", ward_id="W14", sector="water", kind=kind,
            descriptor=descriptor, recorded_status="functional",
            source_id=SECTOR_SOURCE["water"], actual_status="non_functional",
        ))
    return assets


def seed(db):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    for row in WARDS:
        db.add(Ward(**dict(zip(WARD_COLUMNS, row))))

    for ds in DATA_SOURCES:
        db.add(DataSource(source_id=ds["source_id"], name=ds["name"],
                          sectors=json.dumps(ds["sectors"]), as_of_date=ds["as_of_date"]))

    db.flush()

    all_assets = []
    for row in WARDS:
        ward_id = row[0]
        if ward_id == "W14":
            all_assets += _w14_water_trap()
            # a few assets in W14's other sectors so it isn't water-only
            for sector in ["health", "education", "roads", "sanitation", "drainage"]:
                kind = random.choice(SECTOR_KINDS[sector])
                descriptor = f"{kind.replace('_', ' ')} {random.choice(LOCATION_PHRASES)}"
                all_assets.append(dict(
                    asset_id=f"W14-{sector[:3].upper()}-01", ward_id="W14", sector=sector,
                    kind=kind, descriptor=descriptor, recorded_status="functional",
                    source_id=SECTOR_SOURCE[sector], actual_status="functional",
                ))
        else:
            all_assets += _make_assets_for_ward(ward_id, n_per_sector_pool=len(SECTORS))

    for a in all_assets:
        db.add(Asset(**a))
    db.flush()

    for ds in DATA_SOURCES:
        for row in WARDS:
            db.add(SourceTrust(source_id=ds["source_id"], ward_id=row[0], trust=1.0))

    subs = gen.generate(200)
    for _, r in subs.iterrows():
        db.add(Complaint(
            ward_id=r["ward_id"], sector=r["true_sector"], raw_text=r["raw_text"],
            asset_id=None, reported_status=None, duration_weeks=None,
        ))

    for w in WORKS:
        db.add(Work(**w))

    db.add(WeightAuditLog(w_demand=0.30, w_need=0.40, w_equity=0.20, w_cost=0.10,
                          changed_by="seed"))

    db.commit()

    # snapshot for §9c /admin/reset — recorded_status as-seeded
    snapshot = {a["asset_id"]: a["recorded_status"] for a in all_assets}
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Seeded {len(WARDS)} wards, {len(DATA_SOURCES)} data sources, "
          f"{len(all_assets)} assets, {len(subs)} complaints, {len(WORKS)} works.")
    print(f"W14 water trap: 11 assets, recorded functional, actual non_functional.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
