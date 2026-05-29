"""add is_editorial_recall to futures_markets

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-05-29
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Add the precomputed boolean column (defaults to false).
    op.add_column(
        "futures_markets",
        sa.Column(
            "is_editorial_recall",
            sa.Boolean(),
            server_default="false",
            nullable=True,
        ),
    )

    # Backfill existing markets that match the 44 editorial-recall patterns.
    # This runs once; after this, polling tasks set the flag at ingest time.
    op.execute(
        """
        UPDATE futures_markets SET is_editorial_recall = true
        WHERE
            name ILIKE '%aliens%'
            OR name ILIKE '%ufo%'
            OR name ILIKE '%extraterrestrial%'
            OR name ILIKE '%taylor swift%'
            OR name ILIKE '%bridesmaid%'
            OR name ILIKE '%bridesmaids%'
            OR name ILIKE '%wedding%'
            OR name ILIKE '%engaged%'
            OR name ILIKE '%engagement%'
            OR name ILIKE '%pregnant%'
            OR name ILIKE '%pregnancy%'
            OR name ILIKE '%beyonce%'
            OR name ILIKE '%kardashian%'
            OR name ILIKE '%xi jinping%'
            OR name ILIKE '%openai%'
            OR name ILIKE '%anthropic%'
            OR name ILIKE '%claude%'
            OR name ILIKE '%gpt%'
            OR name ILIKE '%gemini%'
            OR name ILIKE '%deepseek%'
            OR name ILIKE '%spacex%'
            OR name ILIKE '%starship%'
            OR name ILIKE '%best ai%'
            OR name ILIKE '%met gala%'
            OR name ILIKE '%attorney general%'
            OR name ILIKE '%fbi director%'
            OR name ILIKE '%save act%'
            OR name ILIKE '%recession%'
            OR name ILIKE '%eurovision%'
            OR name ILIKE '%oscars%'
            OR name ILIKE '%academy award%'
            OR name ILIKE '%grammy%'
            OR name ILIKE '%emmy%'
            OR name ILIKE '%survivor%'
            OR name ILIKE '%netflix%'
            OR name ILIKE '%spotify%'
            OR name ILIKE '%billboard%'
            OR name ILIKE '%rotten tomatoes%'
            OR name ILIKE '%hurricane%'
            OR name ILIKE '%earthquake%'
            OR name ILIKE '%wildfire%'
            OR name ILIKE '%outbreak%'
            OR name ILIKE '%pandemic%'
            OR name ILIKE '%hantavirus%'
        """
    )


def downgrade() -> None:
    op.drop_column("futures_markets", "is_editorial_recall")
