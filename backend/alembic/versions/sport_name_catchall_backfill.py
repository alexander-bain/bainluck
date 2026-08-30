"""Backfill the fifteen `sports` rows whose curated display name is their own key.

## The defect, in one sentence

`Sport.name` is the CURATED display name — "MLB", "NFL" — and fifteen rows were
holding their own key in it, so `tennis_other` printed as the category on a US
Open set-winner card.

Measured against production on 2026-08-30, before writing this file:

    SELECT key, name FROM sports WHERE name = key ORDER BY key;
    -- americanfootball_other, baseball_other, basketball_other, boxing_other,
    -- cricket_other, esports, esports_other, golf_other, icehockey_other,
    -- lacrosse_other, mma_other, motorsport_other, rugby_other, soccer_other,
    -- tennis_other                                          (15 rows of 176)

Zero rows are key-shaped in any other way: it is one clean family — the `*_other`
catch-all buckets the Odds API uses for "this sport, league not otherwise mapped",
plus bare `esports`.

## Why this is user-visible, and not a little bit

`Sport.name` is served raw as `sport_name` by thirteen route payloads (feed,
futures, events, teams, market-moves, …), and the frontend's
`getMarketCategoryLabel()` returns it verbatim when present. So the key reached
the category chip on Discover cards, the futures detail page, the daily page and
the OpenGraph card image. Verified live before the fix:

    GET /api/futures/59632706
      name       = "Set 2 Winner: Fery vs Kovacevic"
      sport_name = "tennis_other"

The population is not marginal. Counted the same day: `soccer_other` carries
4,193 open futures markets, `americanfootball_other` 381, `tennis_other` 220 —
the last of those being US Open set winners, during the US Open.

## Why a data migration and not a display rule

A rule at the read boundary would have to be applied at thirteen serialization
sites and would still miss the native clients, which consume the same field. The
name is wrong in one place — the row — and fixing it there fixes every reader at
once, including the ones nobody has enumerated. Fifteen rows is small enough that
the blast radius is fully knowable.

The three code paths that auto-create a `Sport` were changed in the same commit
to call `app.utils.sport_keys.sport_display_name()`, so this backfill is not
re-opened by the next poll of a new league.

## Why these particular words

They are not new words. Each is the `name` the frontend's `SPORT_CATEGORIES`
table already renders for the same sport, so a backfilled row reads the same as
every other card in its category. `tests/test_sport_display_name_p195.py` binds
`BACKFILL` below to `sport_display_name()` — a mismatch reds rather than silently
letting a fresh database diverge from what production got.

The names are frozen as literals here ON PURPOSE. Editing
`SPORT_PREFIX_DISPLAY_NAME` later must not retroactively change what this already
-applied revision means; a fresh database replaying the chain has to land on the
same rows production has. That is the lesson `add_prov_play_value` was written to
record, applied to data instead of to an enum.

## Why the `AND name = key` guard on every statement

It makes the revision idempotent and strictly non-destructive: a row someone has
since curated by hand keeps the curated name, and a re-run is a no-op. The guard
is also what makes `downgrade()` below exact rather than approximate.

Revision ID: sport_name_catchall_backfill
Revises: anchors_and_captures
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic. (<=32 chars — gotcha #1.)
revision = "sport_name_catchall_backfill"
down_revision = "anchors_and_captures"
branch_labels = None
depends_on = None

#: The exact (key, curated name) pairs this revision applies, frozen. Every key
#: here was measured as `name = key` in production on 2026-08-30; every name is
#: what `app.utils.sport_keys.sport_display_name()` returns for that key, which
#: `tests/test_sport_display_name_p195.py` asserts in both directions.
BACKFILL: tuple[tuple[str, str], ...] = (
    ("americanfootball_other", "Football"),
    ("baseball_other", "Baseball"),
    ("basketball_other", "Basketball"),
    ("boxing_other", "Boxing"),
    ("cricket_other", "Cricket"),
    ("esports", "Esports"),
    ("esports_other", "Esports"),
    ("golf_other", "Golf"),
    ("icehockey_other", "Hockey"),
    ("lacrosse_other", "Lacrosse"),
    ("mma_other", "MMA"),
    ("motorsport_other", "Motorsport"),
    ("rugby_other", "Rugby"),
    ("soccer_other", "Soccer"),
    ("tennis_other", "Tennis"),
)

_UPGRADE_SQL = "UPDATE sports SET name = :name WHERE key = :key AND name = key"

#: The inverse is guarded on the name this revision WROTE, not on the key alone,
#: so a downgrade cannot clobber a name curated after the upgrade ran.
_DOWNGRADE_SQL = "UPDATE sports SET name = key WHERE key = :key AND name = :name"


def upgrade() -> None:
    bind = op.get_bind()
    for key, name in BACKFILL:
        bind.execute(sa.text(_UPGRADE_SQL), {"key": key, "name": name})


def downgrade() -> None:
    """Restore `name = key` for exactly the rows `upgrade()` rewrote.

    Reversible on purpose, unlike most data migrations: the pre-state is
    recoverable from the key itself, so there is nothing to reconstruct and no
    reason to leave a rollback with a no-op it would have to work around.
    """
    bind = op.get_bind()
    for key, name in BACKFILL:
        bind.execute(sa.text(_DOWNGRADE_SQL), {"key": key, "name": name})
