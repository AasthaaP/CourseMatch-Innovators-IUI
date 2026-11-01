import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway database before backend.app is imported.
_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ.setdefault("COURSEMATCH_DB", str(_tmp))


@pytest.fixture
def mem_db():
    """A fresh in-memory database with every table (spec 16.2 "using an in memory database")."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from backend.app import models  # noqa: F401  (registers tables)
    from backend.app.db import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db


def add_course(db, code, title=None, prereq_raw="", recommendable=1, description=None):
    from backend.app.models import Course

    db.add(Course(code=code, title=title or f"Course {code}", level="graduate" if code[5] >= "6" else "undergraduate",
                  department=code.split()[0], credits_raw="3", credits_num=3.0,
                  description=description or f"About {code}.", prereq_raw=prereq_raw, is_recommendable=recommendable))


def add_groups(db, code, groups):
    """groups: list of (kind, [alternatives])."""
    import json

    from backend.app.models import PrereqGroup

    for i, (kind, alts) in enumerate(groups):
        db.add(PrereqGroup(course_code=code, group_index=i, kind=kind, alternatives=json.dumps(alts), raw_text=""))
