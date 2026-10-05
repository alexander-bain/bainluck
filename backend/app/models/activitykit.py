"""Account-owned ActivityKit registrations, separate from generic device tokens."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.services.database import Base


class ActivityKitRegistration(Base):
    __tablename__ = "activitykit_registrations"

    activity_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Transport credential: never returned, logged or retained on a tombstone.
    push_token: Mapped[str | None] = mapped_column(Text)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    mutation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
