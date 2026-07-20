"""
Unit tests for divergence.py — BUILD_BRIEF.md §5, steps 1-4.
Written before wiring the API, per the brief.
"""
import sys
import os
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Base
from models import Ward, DataSource, Asset, Complaint, Dispute, SourceTrust, VerificationTask
import divergence as dv


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def make_ward(db, ward_id="W14"):
    w = Ward(
        ward_id=ward_id, population=10500, literacy_pct=61, smartphone_pct=47,
        is_urban=False, km_to_mp_office=18, tap_coverage_pct=61, toilet_coverage_pct=58,
        km_to_phc=5.4, dropout_pct=18, km_to_school=8.4, road_km_per_sqkm=1.9, sc_st_pct=34,
    )
    db.add(w)
    db.commit()
    return w


def make_source(db, source_id="jal_jeevan", sectors='["water"]', as_of=date(2022, 6, 1)):
    s = DataSource(source_id=source_id, name="Jal Jeevan Mission", sectors=sectors, as_of_date=as_of)
    db.add(s)
    db.commit()
    return s


def make_asset(db, asset_id, ward_id="W14", sector="water", source_id="jal_jeevan",
                recorded_status="functional"):
    a = Asset(
        asset_id=asset_id, ward_id=ward_id, sector=sector, kind="handpump",
        descriptor=f"handpump {asset_id}", recorded_status=recorded_status,
        source_id=source_id, actual_status="non_functional",
    )
    db.add(a)
    db.commit()
    return a


def get_trust(db, source_id, ward_id):
    row = db.query(SourceTrust).filter_by(source_id=source_id, ward_id=ward_id).first()
    return row.trust if row else 1.0


# ── Step 1: dispute creation ────────────────────────────────────────────

def test_no_dispute_when_no_asset_named(db):
    make_ward(db)
    make_source(db)
    complaint, created = dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="no water for days",
        asset_id=None, reported_status=None, duration_weeks=None,
    )
    assert created is False
    assert db.query(Dispute).count() == 0


def test_no_dispute_when_status_agrees_with_record(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-1", recorded_status="functional")
    # complaint doesn't contradict — reported_status None
    complaint, created = dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="fine here",
        asset_id="HP-1", reported_status=None, duration_weeks=None,
    )
    assert created is False
    assert db.query(Dispute).count() == 0


def test_dispute_created_on_contradiction(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-1", recorded_status="functional")
    complaint, created = dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="handpump broken",
        asset_id="HP-1", reported_status="not_working", duration_weeks=4,
    )
    assert created is True
    disputes = db.query(Dispute).all()
    assert len(disputes) == 1
    assert disputes[0].asset_id == "HP-1"
    assert disputes[0].status == "open"


def test_degraded_also_contradicts_functional(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-1", recorded_status="functional")
    _, created = dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="degraded",
        asset_id="HP-1", reported_status="degraded", duration_weeks=2,
    )
    assert created is True


def test_no_dispute_when_record_already_non_functional(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-1", recorded_status="non_functional")
    _, created = dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="still broken",
        asset_id="HP-1", reported_status="not_working", duration_weeks=2,
    )
    assert created is False
    assert db.query(Dispute).count() == 0


def test_duplicate_complaint_within_14_days_attaches_to_existing_dispute(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-1", recorded_status="functional")
    dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="first report",
        asset_id="HP-1", reported_status="not_working", duration_weeks=4,
    )
    _, created2 = dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="second report same asset",
        asset_id="HP-1", reported_status="not_working", duration_weeks=5,
    )
    assert created2 is True  # still "disputes the record" from the caller's POV
    assert db.query(Dispute).count() == 1  # but no NEW dispute row
    dispute = db.query(Dispute).first()
    # first complaint lives on disputes.complaint_id; duplicates go in the join table
    links = db.query(dv.DisputeComplaint).filter_by(dispute_id=dispute.dispute_id).all()
    assert len(links) == 1
    total_linked = 1 + len(links)  # dispute.complaint_id + join-table rows
    assert total_linked == 2


def test_duplicate_after_14_days_creates_new_dispute(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-1", recorded_status="functional")
    dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="first report",
        asset_id="HP-1", reported_status="not_working", duration_weeks=4,
    )
    old_dispute = db.query(Dispute).first()
    old_dispute.created_at = datetime.utcnow() - timedelta(days=20)
    db.commit()

    dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="new report, way later",
        asset_id="HP-1", reported_status="not_working", duration_weeks=1,
    )
    assert db.query(Dispute).count() == 2


# ── Step 2: trust decay ─────────────────────────────────────────────────

def test_trust_decays_by_step_on_new_dispute(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-1", recorded_status="functional")
    dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="broken",
        asset_id="HP-1", reported_status="not_working", duration_weeks=4,
    )
    assert get_trust(db, "jal_jeevan", "W14") == pytest.approx(1.0 - dv.DISPUTE_TRUST_STEP)


def test_trust_does_not_decay_again_on_duplicate_attach(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-1", recorded_status="functional")
    dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="broken",
        asset_id="HP-1", reported_status="not_working", duration_weeks=4,
    )
    dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="still broken",
        asset_id="HP-1", reported_status="not_working", duration_weeks=5,
    )
    assert get_trust(db, "jal_jeevan", "W14") == pytest.approx(1.0 - dv.DISPUTE_TRUST_STEP)


def test_trust_floors_at_0_3(db):
    make_ward(db)
    make_source(db)
    for i in range(20):
        make_asset(db, f"HP-{i}", recorded_status="functional")
        dv.register_complaint(
            db, ward_id="W14", sector="water", raw_text=f"broken {i}",
            asset_id=f"HP-{i}", reported_status="not_working", duration_weeks=4,
        )
    assert get_trust(db, "jal_jeevan", "W14") == pytest.approx(dv.TRUST_FLOOR)


def test_trust_is_per_source_per_ward_not_global(db):
    make_ward(db, "W14")
    make_ward(db, "W07")
    make_source(db)
    make_asset(db, "HP-14", ward_id="W14", recorded_status="functional")
    dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="broken",
        asset_id="HP-14", reported_status="not_working", duration_weeks=4,
    )
    assert get_trust(db, "jal_jeevan", "W14") == pytest.approx(1.0 - dv.DISPUTE_TRUST_STEP)
    assert get_trust(db, "jal_jeevan", "W07") == pytest.approx(1.0)


# ── Step 3: verification task spawn ─────────────────────────────────────

def test_no_task_below_threshold(db):
    make_ward(db)
    make_source(db)
    for i in range(dv.TASK_THRESHOLD - 1):
        make_asset(db, f"HP-{i}", recorded_status="functional")
        dv.register_complaint(
            db, ward_id="W14", sector="water", raw_text=f"broken {i}",
            asset_id=f"HP-{i}", reported_status="not_working", duration_weeks=4,
        )
    assert db.query(VerificationTask).count() == 0


def test_task_spawned_at_threshold_for_each_disputed_asset(db):
    make_ward(db)
    make_source(db)
    for i in range(dv.TASK_THRESHOLD):
        make_asset(db, f"HP-{i}", recorded_status="functional")
        dv.register_complaint(
            db, ward_id="W14", sector="water", raw_text=f"broken {i}",
            asset_id=f"HP-{i}", reported_status="not_working", duration_weeks=4,
        )
    tasks = db.query(VerificationTask).all()
    assert len(tasks) == dv.TASK_THRESHOLD
    asset_ids = {t.asset_id for t in tasks}
    assert asset_ids == {"HP-0", "HP-1", "HP-2"}
    assert all(t.status == "pending" for t in tasks)


def test_task_not_duplicated_for_asset_with_pending_task(db):
    make_ward(db)
    make_source(db)
    for i in range(dv.TASK_THRESHOLD):
        make_asset(db, f"HP-{i}", recorded_status="functional")
        dv.register_complaint(
            db, ward_id="W14", sector="water", raw_text=f"broken {i}",
            asset_id=f"HP-{i}", reported_status="not_working", duration_weeks=4,
        )
    assert db.query(VerificationTask).count() == dv.TASK_THRESHOLD
    # one more dispute in the same ward-sector, on an asset already disputed
    dv.register_complaint(
        db, ward_id="W14", sector="water", raw_text="broken again elsewhere",
        asset_id="HP-0", reported_status="not_working", duration_weeks=10,
    )
    # still just 3 tasks — HP-0 already has a pending one, no new dispute created anyway
    assert db.query(VerificationTask).count() == dv.TASK_THRESHOLD


def test_task_spawned_for_new_asset_crossing_threshold_later(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-0", recorded_status="functional")
    make_asset(db, "HP-1", recorded_status="functional")
    dv.register_complaint(db, ward_id="W14", sector="water", raw_text="a",
                          asset_id="HP-0", reported_status="not_working", duration_weeks=4)
    dv.register_complaint(db, ward_id="W14", sector="water", raw_text="b",
                          asset_id="HP-1", reported_status="not_working", duration_weeks=4)
    assert db.query(VerificationTask).count() == 0  # below threshold (2 < 3)

    make_asset(db, "HP-2", recorded_status="functional")
    dv.register_complaint(db, ward_id="W14", sector="water", raw_text="c",
                          asset_id="HP-2", reported_status="not_working", duration_weeks=4)
    assert db.query(VerificationTask).count() == 3  # now at threshold, all 3 get tasks


# ── Step 4: task closure ────────────────────────────────────────────────

def _spawn_one_task(db):
    make_ward(db)
    make_source(db)
    for i in range(dv.TASK_THRESHOLD):
        make_asset(db, f"HP-{i}", recorded_status="functional")
        dv.register_complaint(
            db, ward_id="W14", sector="water", raw_text=f"broken {i}",
            asset_id=f"HP-{i}", reported_status="not_working", duration_weeks=4,
        )
    return db.query(VerificationTask).filter_by(asset_id="HP-0").first()


def test_confirmed_broken_flips_asset_and_verifies_dispute(db):
    task = _spawn_one_task(db)
    trust_before = get_trust(db, "jal_jeevan", "W14")
    dv.close_verification_task(db, task.task_id, outcome="confirmed_broken", note="checked in person")

    asset = db.query(Asset).filter_by(asset_id="HP-0").first()
    assert asset.recorded_status == "non_functional"

    dispute = db.query(Dispute).filter_by(asset_id="HP-0").first()
    assert dispute.status == "verified_complaint_right"

    task_after = db.query(VerificationTask).filter_by(task_id=task.task_id).first()
    assert task_after.status == "closed_disputed"
    assert task_after.note == "checked in person"

    # trust unchanged by closure (decay already applied stands)
    assert get_trust(db, "jal_jeevan", "W14") == pytest.approx(trust_before)


def test_fixed_restores_trust_and_verifies_dispute(db):
    task = _spawn_one_task(db)
    trust_before = get_trust(db, "jal_jeevan", "W14")
    dv.close_verification_task(db, task.task_id, outcome="fixed", note="repaired")

    dispute = db.query(Dispute).filter_by(asset_id="HP-0").first()
    assert dispute.status == "verified_record_right"

    task_after = db.query(VerificationTask).filter_by(task_id=task.task_id).first()
    assert task_after.status == "closed_fixed"

    assert get_trust(db, "jal_jeevan", "W14") == pytest.approx(
        min(dv.TRUST_CEILING, trust_before + dv.RESTORE_STEP)
    )


def test_trust_restore_caps_at_ceiling(db):
    make_ward(db)
    make_source(db)
    make_asset(db, "HP-0", recorded_status="functional")
    dv.register_complaint(db, ward_id="W14", sector="water", raw_text="broken",
                          asset_id="HP-0", reported_status="not_working", duration_weeks=4)
    # manually bump trust near ceiling
    row = db.query(SourceTrust).filter_by(source_id="jal_jeevan", ward_id="W14").first()
    row.trust = 0.98
    db.commit()

    task = VerificationTask(asset_id="HP-0", status="pending")
    db.add(task)
    db.commit()

    dv.close_verification_task(db, task.task_id, outcome="fixed", note=None)
    assert get_trust(db, "jal_jeevan", "W14") == pytest.approx(dv.TRUST_CEILING)


# ── Step 5: surfacing helper ─────────────────────────────────────────────

def test_data_flags_empty_when_trust_high(db):
    make_ward(db)
    make_source(db)
    flags = dv.data_flags(db, "W14", "water")
    assert flags == []


def test_data_flags_present_when_trust_below_0_9(db):
    make_ward(db)
    make_source(db)
    for i in range(dv.TASK_THRESHOLD + 1):
        make_asset(db, f"HP-{i}", recorded_status="functional")
        dv.register_complaint(
            db, ward_id="W14", sector="water", raw_text=f"broken {i}",
            asset_id=f"HP-{i}", reported_status="not_working", duration_weeks=4,
        )
    flags = dv.data_flags(db, "W14", "water")
    assert len(flags) == 1
    assert "disputed by" in flags[0]
    assert "field reports" in flags[0]
