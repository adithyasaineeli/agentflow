import uuid
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    api_key_hash = Column(String(255), unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trajectories = relationship("Trajectory", back_populates="agent", cascade="all, delete-orphan")


class Trajectory(Base):
    __tablename__ = "trajectories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    task_goal = Column(Text, nullable=False)
    error_trace = Column(Text, nullable=True)
    playbook = Column(JSON, nullable=False)
    status = Column(String(50), default="completed", nullable=False, index=True)

    # 1536-dimensional vector for standard semantic embeddings (e.g. OpenAI, text-embedding-3-small)
    embedding = Column(Vector(1536), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)

    agent = relationship("Agent", back_populates="trajectories")


class QueueTask(Base):
    """Backing table for PostgresSkipLockedQueue."""
    __tablename__ = "queue_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_type = Column(String(100), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, PROCESSING, COMPLETED, FAILED
    attempts = Column(Integer, default=0, nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(100), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)
