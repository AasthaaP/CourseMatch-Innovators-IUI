"""log(...): interaction logging that never fails the caller.

Spec: S17 (Section 23.2). Owner: Shubham. Every row carries `condition`.
"""
import json
import sys
from datetime import datetime, timezone

from .models import Interaction, Student


def log(student_id, condition, event, course_code=None, query=None, payload=None, db=None):
    """Write one interactions row. Swallows every error (stderr only). Pass `db` to reuse a session;
    otherwise a short-lived one is opened. When condition is None it is read from the student row."""
    from .db import SessionLocal

    own = db is None
    try:
        db = db or SessionLocal()
        if condition is None:
            st = db.get(Student, student_id)
            condition = st.condition if st else "system"
        db.add(Interaction(student_id=student_id, ts=datetime.now(timezone.utc).isoformat(), condition=condition,
                           event=event, course_code=course_code, query=query,
                           payload=json.dumps(payload) if payload is not None else None))
        db.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[events] dropped {event} for {student_id}: {e}", file=sys.stderr)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        if own and db is not None:
            db.close()
