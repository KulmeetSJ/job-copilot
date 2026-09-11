"""SQLAlchemy ORM model for Phase 4 / Phase 9 Recommendations and Scores."""

from typing import TYPE_CHECKING, Optional
from sqlalchemy import Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_copilot.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from job_copilot.models.job import Job


class RecommendationRecord(Base, TimestampMixin):
    """Persists evaluation results, priority scores, and category breakdowns."""
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id_ref: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    priority_band: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    recommended_strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    category_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    explanation_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="recommendation")

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_recommendation_job_id"),
    )

    def __repr__(self) -> str:
        return f"<RecommendationRecord(job_id='{self.job_id}', rec='{self.recommendation}', score={self.match_score})>"
