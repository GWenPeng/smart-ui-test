"""SQLAlchemy models - SQLite compatible."""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    target_url = Column(String(2048), nullable=False)
    natural_input = Column(Text, nullable=False)
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    steps = relationship("TestStep", back_populates="case", cascade="all, delete-orphan", order_by="TestStep.step_order")
    runs = relationship("TestRun", back_populates="case", cascade="all, delete-orphan")


class TestStep(Base):
    __tablename__ = "test_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False)
    step_order = Column(Integer, nullable=False)
    action = Column(String(50), nullable=False)
    target = Column(Text, nullable=False)
    value = Column(String(2048))
    locator_strategy = Column(String(50))
    locator_value = Column(Text)
    iframe_hint = Column(String(255))
    timeout_ms = Column(Integer, default=10000)
    raw_text = Column(Text)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("TestCase", back_populates="steps")
    results = relationship("StepResult", back_populates="step")


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="queued")
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    duration_ms = Column(Integer)
    error_message = Column(Text)
    browser_info = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("TestCase", back_populates="runs")
    step_results = relationship("StepResult", back_populates="run", cascade="all, delete-orphan")


class StepResult(Base):
    __tablename__ = "step_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(Integer, ForeignKey("test_steps.id", ondelete="CASCADE"), nullable=False)
    step_order = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    duration_ms = Column(Integer)
    error_message = Column(Text)
    screenshot_path = Column(String(512))
    iframe_path = Column(JSON)
    element_info = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("TestRun", back_populates="step_results")
    step = relationship("TestStep", back_populates="results")


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    category = Column(String(20), nullable=False)
    url_pattern = Column(String(512))
    rules = Column(JSON, nullable=False)
    priority = Column(Integer, default=0)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IframeCache(Base):
    __tablename__ = "iframe_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url_pattern = Column(String(512), nullable=False)
    iframe_tree = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
