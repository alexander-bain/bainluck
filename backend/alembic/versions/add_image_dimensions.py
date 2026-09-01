"""Store the true pixel dimensions of enriched market artwork.

A market's image_url is a rendered URL, not a raster: Pexels serves through
imgix, so "?h=350" pins only the height and the delivered width varies with the
source photo's aspect. Consumers that must know the real width — srcset
descriptors, aspect-ratio boxes — cannot read it off the URL, so it is stored.

Both columns are nullable with no default and no index: ADD COLUMN is then a
metadata-only operation in Postgres 11+ and does not rewrite the table, which
matters because futures_markets is large and the Heroku release phase times out
around five minutes. NULL means "not measured yet" and every consumer falls
back to its previous behaviour, so the deploy is safe with the columns empty.

Revision ID: add_image_dimensions
Revises: anchors_and_captures
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_image_dimensions"
down_revision = "anchors_and_captures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "futures_markets", sa.Column("image_width", sa.Integer(), nullable=True)
    )
    op.add_column(
        "futures_markets", sa.Column("image_height", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("futures_markets", "image_height")
    op.drop_column("futures_markets", "image_width")
