"""Engine, session factory and FastAPI dependency. Spec Section 8.

Run `python -m backend.app.db` to create data/processed/coursematch.db with every table.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL, DB_PATH


class Base(DeclarativeBase):
    pass


def make_engine(url: str = DATABASE_URL):
    eng = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(eng=None):
    from . import models  # noqa: F401  (registers tables)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(eng or engine)


if __name__ == "__main__":
    # Re-import through the package so models register on the same Base as the app.
    from sqlalchemy import inspect

    from backend.app import db as pkg_db

    pkg_db.init_db()
    names = sorted(inspect(pkg_db.engine).get_table_names())
    print(f"{DB_PATH}: {len(names)} tables")
    for n in names:
        print("  ", n)
