"""
SQLAlchemy models — mirrors the schema in BUILD_BRIEF.md §1 exactly.
Dialect-neutral: runs on SQLite (dev) and Postgres (prod) via db.py's engine.
"""
from datetime import datetime, date
import uuid

from sqlalchemy import (
    String, Integer, Float, Boolean, Date, DateTime, Text, ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Ward(Base):
    __tablename__ = "wards"

    ward_id: Mapped[str] = mapped_column(String, primary_key=True)
    population: Mapped[int] = mapped_column(Integer, nullable=False)
    literacy_pct: Mapped[float] = mapped_column(Float, nullable=False)
    smartphone_pct: Mapped[float] = mapped_column(Float, nullable=False)
    is_urban: Mapped[bool] = mapped_column(Boolean, nullable=False)
    km_to_mp_office: Mapped[float] = mapped_column(Float, nullable=False)
    tap_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False)
    toilet_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False)
    km_to_phc: Mapped[float] = mapped_column(Float, nullable=False)
    dropout_pct: Mapped[float] = mapped_column(Float, nullable=False)
    km_to_school: Mapped[float] = mapped_column(Float, nullable=False)
    road_km_per_sqkm: Mapped[float] = mapped_column(Float, nullable=False)
    sc_st_pct: Mapped[float] = mapped_column(Float, nullable=False)


class DataSource(Base):
    __tablename__ = "data_sources"

    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sectors: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of sectors
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)


class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String, primary_key=True)
    ward_id: Mapped[str] = mapped_column(String, ForeignKey("wards.ward_id"))
    sector: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    descriptor: Mapped[str] = mapped_column(String, nullable=False)
    recorded_status: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, ForeignKey("data_sources.source_id"))
    # §9b hidden reality layer — ground truth, never exposed via list/ranking endpoints
    actual_status: Mapped[str] = mapped_column(String, nullable=False, default="functional")


class Complaint(Base):
    __tablename__ = "complaints"

    complaint_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ward_id: Mapped[str] = mapped_column(String, ForeignKey("wards.ward_id"))
    sector: Mapped[str] = mapped_column(String, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str | None] = mapped_column(String, ForeignKey("assets.asset_id"), nullable=True)
    reported_status: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Dispute(Base):
    __tablename__ = "disputes"

    dispute_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("assets.asset_id"))
    complaint_id: Mapped[str] = mapped_column(String, ForeignKey("complaints.complaint_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    # 'open' | 'verified_complaint_right' | 'verified_record_right'


class DisputeComplaint(Base):
    """Join table: duplicate complaints on the same asset within 14 days
    attach to the existing open dispute (§5 step 1)."""
    __tablename__ = "dispute_complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispute_id: Mapped[str] = mapped_column(String, ForeignKey("disputes.dispute_id"))
    complaint_id: Mapped[str] = mapped_column(String, ForeignKey("complaints.complaint_id"))


class SourceTrust(Base):
    __tablename__ = "source_trust"

    source_id: Mapped[str] = mapped_column(String, ForeignKey("data_sources.source_id"), primary_key=True)
    ward_id: Mapped[str] = mapped_column(String, ForeignKey("wards.ward_id"), primary_key=True)
    trust: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class Work(Base):
    __tablename__ = "works"

    work_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    ward_id: Mapped[str] = mapped_column(String, ForeignKey("wards.ward_id"))
    sector: Mapped[str] = mapped_column(String, nullable=False)
    cost_lakh: Mapped[float] = mapped_column(Float, nullable=False)
    beneficiaries: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    # 'development_plan' | 'derived_from_cluster'
    cluster_submissions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class VerificationTask(Base):
    __tablename__ = "verification_tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("assets.asset_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # 'pending' | 'closed_fixed' | 'closed_disputed'
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class WeightAuditLog(Base):
    __tablename__ = "weight_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    w_demand: Mapped[float] = mapped_column(Float)
    w_need: Mapped[float] = mapped_column(Float)
    w_equity: Mapped[float] = mapped_column(Float)
    w_cost: Mapped[float] = mapped_column(Float)
    changed_by: Mapped[str] = mapped_column(String, nullable=False, default="demo_user")
