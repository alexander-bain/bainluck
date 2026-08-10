"""Add token_kind to device_tokens (Queue 311, Item A1 / #1159).

The iOS app captures RAW APNS hex tokens. FCM's ``messaging.send()`` accepts
only Firebase registration tokens and rejects an APNS hex outright, so the
morning digest has reached zero recipients since 7/17: every row in this table
is a token the sender cannot send to, and there was no column that could tell
the sendable rows from the unsendable ones.

``token_kind`` is that discriminator. The ``apns`` server default is the whole
point of doing it this way — it makes every pre-existing row correctly
self-describe as the unsendable APNS token it already is, so no backfill script
is needed and no row is silently reclassified as sendable.

Deliberately NOT an overloaded ``platform="ios_fcm"``: that fits in String(10)
and would have worked, which is what made it tempting, but it would destroy
``platform`` as a platform axis (gotcha #40's class of "one column means two
things").

The unique constraint on ``device_token`` is left alone. One device now
legitimately owns TWO rows — an apns one and an fcm one — because they are two
genuinely different tokens.

Revision ID: add_device_token_kind
Revises: add_disc_int_market_type
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic. (<=32 chars — gotcha #1.)
revision = "add_device_token_kind"
down_revision = "add_disc_int_market_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device_tokens",
        sa.Column(
            "token_kind",
            sa.String(length=10),
            nullable=False,
            server_default="apns",
        ),
    )


def downgrade() -> None:
    op.drop_column("device_tokens", "token_kind")
