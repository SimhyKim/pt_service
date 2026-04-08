"""SQLAlchemy models"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserInferenceLog(Base):
    """Stores each analyst request"""

    __tablename__ = "user_inference_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    raw_line: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cluster_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    distance_to_centroid: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ClusterStat(Base):
    """Running counts per cluster for events seen via the api post-training"""

    __tablename__ = "cluster_stats"

    cluster_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
