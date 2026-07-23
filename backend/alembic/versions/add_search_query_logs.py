"""#239 Item 4 — SearchQueryLog: append-only log of /api/events/search queries

Lightweight instrumentation feeding the Instant Answers program (search miss =
the #1 reliability failure class) and the search-sentinel gold set: what people
search for, whether it returned results, and the leading result. Written
fire-and-forget off the search path so it never adds latency.

Plain index creation (no CREATE INDEX CONCURRENTLY, gotcha #31) — the table
starts empty so index builds are instant.

Revision ID: add_search_query_logs
Revises: add_entity_registry
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa

revision = "add_search_query_logs"
down_revision = "add_entity_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_query_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("query", sa.String(length=300), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("top_result_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_search_query_logs_user_id", "search_query_logs", ["user_id"])
    op.create_index(
        "ix_search_query_logs_session_id", "search_query_logs", ["session_id"]
    )
    op.create_index(
        "ix_search_query_logs_created_at", "search_query_logs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_search_query_logs_created_at", table_name="search_query_logs")
    op.drop_index("ix_search_query_logs_session_id", table_name="search_query_logs")
    op.drop_index("ix_search_query_logs_user_id", table_name="search_query_logs")
    op.drop_table("search_query_logs")
