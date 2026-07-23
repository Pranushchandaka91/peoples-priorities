"""
Engine/session setup. Dialect-neutral SQLAlchemy — SQLite for dev,
Postgres in prod via DATABASE_URL env var.
"""
import os
from urllib.parse import urlsplit
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./peoples_priorities.db")

_parsed = urlsplit(DATABASE_URL)
_safe_url = f"{_parsed.scheme}://{_parsed.hostname}:{_parsed.port}{_parsed.path}" if _parsed.hostname else DATABASE_URL
print(f"db: creating engine for {_safe_url}", flush=True)

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {"connect_timeout": 10}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
)
print("db: engine created", flush=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    print("get_db: opening session", flush=True)
    db = SessionLocal()
    try:
        yield db
    finally:
        print("get_db: closing session", flush=True)
        db.close()
