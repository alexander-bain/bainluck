"""Durable single-activity state; credentials remain in the registration table."""

from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.services.database import Base


class ActivityKitDelivery(Base):
    __tablename__ = "activitykit_deliveries"
    activity_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("activitykit_registrations.activity_id", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    registration_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_id: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
