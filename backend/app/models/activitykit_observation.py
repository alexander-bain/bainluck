"""Immutable canonical observations; no credentials or user identity."""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.services.database import Base


class ActivityKitObservation(Base):
    __tablename__ = "activitykit_observations"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_activitykit_observation_sequence"),
    )
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
