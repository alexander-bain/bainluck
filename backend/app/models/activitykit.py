"""ActivityKit registrations, separate from generic device tokens.

Owned by an account, or (177-A) by a phone with no account: at least one of
``user_id`` and ``device_id`` is set.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.services.database import Base


class ActivityKitRegistration(Base):
    __tablename__ = "activitykit_registrations"

    activity_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    device_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("push_devices.device_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
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
    # First server authorization only; rotation cannot renew this horizon.
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR device_id IS NOT NULL",
            name="ck_activitykit_registrations_owner",
        ),
    )
