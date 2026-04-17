"""WrestleMania 42 prediction game tables.

Revision ID: add_wrestlemania
Revises: widen_team_abbrev
Create Date: 2026-04-17
"""

revision = "add_wrestlemania"
down_revision = "widen_team_abbrev"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade():
    op.create_table(
        "wrestlemania_matches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("match_order", sa.Integer, nullable=False),
        sa.Column("night", sa.Integer, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("match_type", sa.String(100), nullable=False),
        sa.Column("participants", JSONB, default=list),
        sa.Column("lock_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("polymarket_event_id", sa.String(200)),
        sa.Column("polymarket_condition_id", sa.String(200)),
        sa.Column("storyline", sa.Text),
        sa.Column("winner_outcome_id", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "wrestlemania_outcomes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("wrestlemania_matches.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("polymarket_token_id", sa.String(200)),
        sa.Column("wikipedia_image_url", sa.Text),
        sa.Column("case_text", sa.Text),
        sa.Column("probability", sa.Numeric(5, 4)),
        sa.Column("decimal_odds", sa.Numeric(8, 3)),
        sa.Column("is_winner", sa.Boolean),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Deferred FK for winner_outcome_id (circular ref)
    op.create_foreign_key(
        "fk_wm_match_winner",
        "wrestlemania_matches",
        "wrestlemania_outcomes",
        ["winner_outcome_id"],
        ["id"],
    )

    op.create_table(
        "wrestlemania_odds_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("outcome_id", sa.Integer, sa.ForeignKey("wrestlemania_outcomes.id"), nullable=False),
        sa.Column("probability", sa.Numeric(5, 4), nullable=False),
        sa.Column("source", sa.String(50), server_default="seed"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "wrestlemania_players",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("display_name", sa.String(100), unique=True, nullable=False),
        sa.Column("player_token", sa.String(64), nullable=False),
        sa.Column("bankroll", sa.Numeric(12, 2), server_default="1000000"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "wrestlemania_picks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("wrestlemania_players.id"), nullable=False),
        sa.Column("outcome_id", sa.Integer, sa.ForeignKey("wrestlemania_outcomes.id"), nullable=False),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("wrestlemania_matches.id"), nullable=False),
        sa.Column("stake", sa.Numeric(12, 2), nullable=False),
        sa.Column("decimal_odds_at_pick", sa.Numeric(8, 3), nullable=False),
        sa.Column("result", sa.String(20)),
        sa.Column("payout", sa.Numeric(12, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("player_id", "match_id", name="uq_one_pick_per_match"),
    )


def downgrade():
    op.drop_table("wrestlemania_picks")
    op.drop_table("wrestlemania_players")
    op.drop_table("wrestlemania_odds_snapshots")
    op.drop_constraint("fk_wm_match_winner", "wrestlemania_matches", type_="foreignkey")
    op.drop_table("wrestlemania_outcomes")
    op.drop_table("wrestlemania_matches")
