"""SQLAlchemy 2.0 models. Spec Section 8 — column names are part of the contract."""
from sqlalchemy import REAL as Real, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# ---------------------------------------------------------------- course side (8.1)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # "CSCE 633"
    title: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text)  # graduate | undergraduate
    department: Mapped[str] = mapped_column(Text)  # CSCE ECEN MATH STAT
    credits_raw: Mapped[str] = mapped_column(Text, default="")
    credits_num: Mapped[float | None] = mapped_column(Real, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    prereq_raw: Mapped[str] = mapped_column(Text, default="")
    cross_listing_raw: Mapped[str] = mapped_column(Text, default="")
    restrictions_raw: Mapped[str] = mapped_column(Text, default="")
    is_recommendable: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str] = mapped_column(Text, default="")


class PrereqGroup(Base):
    __tablename__ = "prereq_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(Text, index=True)
    group_index: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)  # course | classification | approval | unparsed
    alternatives: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    raw_text: Mapped[str] = mapped_column(Text, default="")


class CourseTopic(Base):
    __tablename__ = "course_topics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(Text, index=True)
    topic: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)  # covers | assumes
    source: Mapped[str] = mapped_column(Text)  # keyword | embedding | llm


class ProgramRequirement(Base):
    __tablename__ = "program_requirements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_code: Mapped[str] = mapped_column(Text)  # MSCS
    bucket: Mapped[str] = mapped_column(Text)  # core | elective | seminar
    course_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MockOffering(Base):
    __tablename__ = "mock_offerings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(Text, index=True)
    term: Mapped[str] = mapped_column(Text)  # 2027SP | 2027FA
    days: Mapped[str] = mapped_column(Text)  # MWF | TR
    start_time: Mapped[str] = mapped_column(Text)
    seats: Mapped[int] = mapped_column(Integer)
    simulated: Mapped[int] = mapped_column(Integer, default=1)


class MockWorkload(Base):
    __tablename__ = "mock_workload"
    course_code: Mapped[str] = mapped_column(Text, primary_key=True)
    difficulty: Mapped[int] = mapped_column(Integer)
    hours_per_week: Mapped[int] = mapped_column(Integer)
    simulated: Mapped[int] = mapped_column(Integer, default=1)


# ---------------------------------------------------------------- student side (8.2)


class Student(Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # s_ + 8 hex
    created_at: Mapped[str] = mapped_column(Text)
    is_sample: Mapped[int] = mapped_column(Integer, default=0)
    sample_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str] = mapped_column(Text, default="system")  # system | baseline
    profile_version: Mapped[int] = mapped_column(Integer, default=1)


class StudentStated(Base):
    __tablename__ = "student_stated"
    student_id: Mapped[str] = mapped_column(String, primary_key=True)
    program: Mapped[str | None] = mapped_column(Text, nullable=True)
    graduation_term: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_per_term: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_days: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    updated_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class StudentCourse(Base):
    __tablename__ = "student_courses"
    __table_args__ = (UniqueConstraint("student_id", "course_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String, index=True)
    course_code: Mapped[str] = mapped_column(Text)


class StudentInterest(Base):
    __tablename__ = "student_interests"
    __table_args__ = (UniqueConstraint("student_id", "topic"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String, index=True)
    topic: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Real, default=1.0)
    source: Mapped[str] = mapped_column(Text, default="stated")


class Inference(Base):
    __tablename__ = "inferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(Text, default="interest")
    value: Mapped[str] = mapped_column(Text)  # a taxonomy topic
    weight: Mapped[float] = mapped_column(Real)  # signed
    evidence: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of strings
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text)


class SavedCourse(Base):
    __tablename__ = "saved_courses"
    __table_args__ = (UniqueConstraint("student_id", "course_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String, index=True)
    course_code: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)  # saved | dismissed
    updated_at: Mapped[str] = mapped_column(Text)


class Interaction(Base):
    __tablename__ = "interactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[str] = mapped_column(Text)
    condition: Mapped[str] = mapped_column(Text)
    event: Mapped[str] = mapped_column(Text)
    course_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
