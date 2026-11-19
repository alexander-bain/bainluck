"""177-A / 178-B: one row per phone, no account needed.

The phone sends its whole state at once: its notification token, its Live
Activity push-to-start token (iOS 17.2+), and the games and markets it has
pinned. The pins live on the row as two integer arrays rather than in a second
table: 177-A is "one new table", the phone always replaces its whole list, and
the kickoff sender's question ("which phones pinned game 123?") is
``pinned_event_ids @> ARRAY[123]``, which the GIN index answers.

A device id alone never authorizes a write. The app keeps a random secret next
to the id in its keychain; the first write stores the secret's SHA-256 and every
later one must match it.

Both tokens are transport credentials: never returned, never logged — the same
rule as ``activitykit_registrations.push_token``.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.services.database import Base

#: The most pins of each kind one phone may register. The PUT refuses a longer
#: list; there is no CHECK for it because the test schema is built on SQLite,
#: which has no `cardinality()`.
MAX_PINS_PER_KIND = 200
#: `appclip` (176-A) is the App Clip, a separate app to Apple: its token takes
#: the clip's own push topic, it lives 8 hours, and it never shows a Live
#: Activity.
PLATFORMS = ("ios", "ipados", "macos", "appclip")
APNS_ENVS = ("production", "sandbox")


class PushDevice(Base):
    __tablename__ = "push_devices"

    device_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    # TestFlight and App Store builds talk to Apple's production push server,
    # Xcode builds to sandbox; a token sent to the other one is refused.
    apns_env: Mapped[str] = mapped_column(String(10), nullable=False)
    notification_token: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    la_start_token: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    la_start_token_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    # 18 and up gets `input-push-token: 1` on a start push.
    os_major: Mapped[Optional[int]] = mapped_column(SmallInteger)
    app_version: Mapped[Optional[str]] = mapped_column(String(20))
    pinned_event_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'")
    )
    pinned_market_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'")
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "platform IN ('ios', 'ipados', 'macos', 'appclip')", name="ck_push_devices_platform"
        ),
        CheckConstraint(
            "apns_env IN ('production', 'sandbox')", name="ck_push_devices_apns_env"
        ),
        CheckConstraint(
            "platform <> 'appclip' OR la_start_token IS NULL",
            name="ck_push_devices_appclip_no_la",
        ),
        Index(
            "ix_push_devices_pinned_event_ids",
            "pinned_event_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_push_devices_pinned_market_ids",
            "pinned_market_ids",
            postgresql_using="gin",
        ),
    )
