"""UX-P195 — a sport category stops printing as a payload key.

Fifteen of 176 `sports` rows carried their own key in `Sport.name`, which is the
CURATED display name and is served raw as `sport_name` by thirteen route
payloads. `getMarketCategoryLabel()` returns it verbatim when present, so
`GET /api/futures/59632706` — a US Open set winner, during the US Open — served
`sport_name = "tennis_other"` straight onto the category chip.

The fix has three parts and this file guards the joins between them:

* `app.utils.sport_keys.sport_display_name()` — the curated word, one function.
* the three `Sport(...)` auto-create sites — so the backfill is not re-opened.
* `alembic/versions/sport_name_catchall_backfill.py` — the fifteen measured rows.

The arms that matter are the ones that bind two of those together. A test that
only re-asserted the map against a copy of itself would stay green through every
interesting way this can break.
"""

import pathlib
import re

import pytest

from app.utils.sport_keys import (
    SPORT_PREFIX_DISPLAY_NAME,
    sport_display_name,
)

REPO = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = REPO / "backend/alembic/versions/sport_name_catchall_backfill.py"
FRONTEND_CATEGORIES = REPO / "frontend/lib/sportCategories.ts"

#: Measured against production 2026-08-30:
#:     SELECT key FROM sports WHERE name = key;
#: Exactly these fifteen, and zero rows key-shaped in any other way. Written out
#: rather than derived so that a change to the family is a decision somebody
#: makes, not a table that quietly grows.
MEASURED_KEY_SHAPED_ROWS: dict[str, str] = {
    "americanfootball_other": "Football",
    "baseball_other": "Baseball",
    "basketball_other": "Basketball",
    "boxing_other": "Boxing",
    "cricket_other": "Cricket",
    "esports": "Esports",
    "esports_other": "Esports",
    "golf_other": "Golf",
    "icehockey_other": "Hockey",
    "lacrosse_other": "Lacrosse",
    "mma_other": "MMA",
    "motorsport_other": "Motorsport",
    "rugby_other": "Rugby",
    "soccer_other": "Soccer",
    "tennis_other": "Tennis",
}

#: `aussierules` is the one prefix where the backend deliberately does NOT mirror
#: the frontend, which says "AFL". AFL is a single league; a catch-all bucket has
#: to name the sport. Listed here so the cross-runtime arm below stays a real
#: check instead of being weakened to accommodate it.
FRONTEND_DIVERGENCE = {"aussierules"}


def _load_migration():
    """Import the revision by path — versions are not importable modules."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_sport_name_mig", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# The helper itself
# ---------------------------------------------------------------------------


class TestSportDisplayName:
    @pytest.mark.parametrize(
        "key,expected", sorted(MEASURED_KEY_SHAPED_ROWS.items())
    )
    def test_every_measured_row_gets_its_english_word(self, key, expected):
        assert sport_display_name(key) == expected

    @pytest.mark.parametrize("key", sorted(MEASURED_KEY_SHAPED_ROWS))
    def test_no_measured_row_still_reads_as_a_key(self, key):
        """The bug's own shape, stated as the negative.

        Independent of the expectation table above: whatever word we chose, it
        must not be the key, must not carry an underscore, and must not be all
        lowercase — the three tells that made `tennis_other` legible as a payload
        field rather than a category.
        """
        out = sport_display_name(key)
        assert out != key
        assert "_" not in out
        assert out != out.lower()

    @pytest.mark.parametrize(
        "key,expected",
        [
            # A named league key is NOT the catch-all family and must keep the
            # exact title-cased fallback the auto-create paths always used. This
            # is the no-regression arm: the change is a strict superset.
            ("soccer_epl", "Soccer Epl"),
            ("basketball_nba", "Basketball Nba"),
            ("americanfootball_nfl", "Americanfootball Nfl"),
            ("soccer_usa_mls", "Soccer Usa Mls"),
            ("icehockey_nhl", "Icehockey Nhl"),
            # A sport we have no curated word for falls through untouched, in
            # both shapes — so an unknown prefix degrades to today's behaviour
            # rather than to an empty string or a KeyError.
            ("pickleball_other", "Pickleball Other"),
            ("chess", "Chess"),
        ],
    )
    def test_the_fallback_is_unchanged_outside_the_catch_all_family(
        self, key, expected
    ):
        assert sport_display_name(key) == expected

    def test_the_fallback_matches_the_expression_it_replaced_character_for_character(
        self,
    ):
        """Bind the fallback to the literal old code, not to a hand-copied guess.

        `name=sport_key.replace("_", " ").title()` was the expression at all
        three creation sites. For every key outside the curated family the new
        helper must still be that expression exactly — asserted by evaluating it
        here rather than by trusting the parametrized table above.
        """
        for key in (
            "soccer_epl",
            "basketball_nba",
            "tennis_atp_french_open",
            "pickleball_other",
            "some_new_sport_nobody_mapped",
        ):
            assert sport_display_name(key) == key.replace("_", " ").title()

    def test_an_empty_key_does_not_raise(self):
        assert sport_display_name("") == ""


# ---------------------------------------------------------------------------
# Helper <-> migration
# ---------------------------------------------------------------------------


class TestMigrationAgreesWithTheHelper:
    def test_the_backfill_covers_exactly_the_measured_rows(self):
        mod = _load_migration()
        assert {k for k, _ in mod.BACKFILL} == set(MEASURED_KEY_SHAPED_ROWS)

    def test_every_frozen_name_is_what_the_helper_returns_today(self):
        """The join that keeps a fresh database and production on the same rows.

        The migration freezes its names as literals so that editing the map later
        cannot retroactively change what an already-applied revision meant. This
        is the price of that: if the map moves, this reds, and whoever moved it
        has to write a new revision rather than discover the drift in a restore.
        """
        mod = _load_migration()
        for key, name in mod.BACKFILL:
            assert sport_display_name(key) == name, key

    def test_the_backfill_never_overwrites_a_curated_name(self):
        """`AND name = key` is what makes the revision safe to re-run.

        Read off the statement the revision actually executes, so deleting the
        guard from the SQL reds here instead of shipping a migration that would
        stamp on a hand-curated row.
        """
        mod = _load_migration()
        assert "AND name = key" in mod._UPGRADE_SQL

    def test_the_downgrade_is_guarded_on_the_name_it_wrote(self):
        mod = _load_migration()
        assert ":name" in mod._DOWNGRADE_SQL
        assert "name = key" in mod._DOWNGRADE_SQL


# ---------------------------------------------------------------------------
# The revision, executed
# ---------------------------------------------------------------------------


class TestTheRevisionActuallyRuns:
    """Drive the real `upgrade()`/`downgrade()`, not a replica of their SQL.

    Everything above reads the revision's constants. That catches a wrong word
    and a missing guard, and it cannot catch a revision that does not run —
    which is the failure that costs a Heroku release phase. So this drives
    `mod.upgrade()` itself through a real Alembic `MigrationContext`, against an
    in-memory SQLite `sports` table (there is no local Postgres in this sandbox,
    and the statements are plain ANSI `UPDATE` with bound parameters, so the
    dialect carries no meaning here).

    The seeded table deliberately contains three populations: the fifteen
    key-shaped rows, a curated row outside the backfill, and a row that IS in the
    backfill but has already been curated by hand. The last one is the whole
    reason `AND name = key` is on the statement.
    """

    CURATED_OUTSIDE = ("baseball_mlb", "MLB")
    CURATED_INSIDE = ("soccer_other", "Soccer — hand-curated")
    KEY_SHAPED_OUTSIDE = ("tennis_atp", "tennis_atp")

    def _seeded(self, mod):
        import sqlalchemy as sa

        engine = sa.create_engine("sqlite://")
        conn = engine.connect()
        conn.execute(
            sa.text("CREATE TABLE sports (id INTEGER PRIMARY KEY, key TEXT, name TEXT)")
        )
        seed = [(k, k) for k, _ in mod.BACKFILL if k != self.CURATED_INSIDE[0]]
        seed += [self.CURATED_INSIDE, self.CURATED_OUTSIDE, self.KEY_SHAPED_OUTSIDE]
        for i, (key, name) in enumerate(seed):
            conn.execute(
                sa.text("INSERT INTO sports VALUES (:i, :k, :n)"),
                {"i": i, "k": key, "n": name},
            )
        return conn

    @staticmethod
    def _run(mod, conn, direction):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(mod, direction)()

    @staticmethod
    def _names(conn):
        import sqlalchemy as sa

        return dict(conn.execute(sa.text("SELECT key, name FROM sports")).all())

    def test_upgrade_gives_every_key_shaped_row_its_word(self):
        mod = _load_migration()
        conn = self._seeded(mod)
        self._run(mod, conn, "upgrade")
        after = self._names(conn)
        for key, name in mod.BACKFILL:
            if key == self.CURATED_INSIDE[0]:
                continue
            assert after[key] == name, key
            assert after[key] != key

    def test_upgrade_does_not_touch_an_already_curated_row(self):
        """The `AND name = key` guard, executed rather than read."""
        mod = _load_migration()
        conn = self._seeded(mod)
        self._run(mod, conn, "upgrade")
        after = self._names(conn)
        assert after[self.CURATED_INSIDE[0]] == self.CURATED_INSIDE[1]
        assert after[self.CURATED_OUTSIDE[0]] == self.CURATED_OUTSIDE[1]

    def test_upgrade_leaves_rows_outside_the_family_alone(self):
        """A key-shaped row we did NOT measure stays key-shaped.

        Stated because the tempting generalisation — `UPDATE sports SET name =
        <something> WHERE name = key` — would sweep up rows nobody looked at.
        """
        mod = _load_migration()
        conn = self._seeded(mod)
        self._run(mod, conn, "upgrade")
        assert self._names(conn)[self.KEY_SHAPED_OUTSIDE[0]] == self.KEY_SHAPED_OUTSIDE[1]

    def test_upgrade_is_idempotent(self):
        mod = _load_migration()
        conn = self._seeded(mod)
        self._run(mod, conn, "upgrade")
        once = self._names(conn)
        self._run(mod, conn, "upgrade")
        assert self._names(conn) == once

    def test_downgrade_is_an_exact_inverse(self):
        mod = _load_migration()
        conn = self._seeded(mod)
        before = self._names(conn)
        self._run(mod, conn, "upgrade")
        self._run(mod, conn, "downgrade")
        assert self._names(conn) == before


# ---------------------------------------------------------------------------
# Backend <-> frontend vocabulary
# ---------------------------------------------------------------------------


class TestVocabularyMatchesTheFrontend:
    """The words are not invented here; they are the site's existing words.

    UX-P194-3 parked the general version of this complaint: a table
    hand-transcribed from one runtime into another, with nothing holding the two
    copies together, drifts silently. This arm holds THIS table.
    """

    @staticmethod
    def _frontend_names() -> dict[str, str]:
        src = FRONTEND_CATEGORIES.read_text()
        return {
            m.group(1): m.group(2)
            for m in re.finditer(
                r'key:\s*"([a-z_]+)",\s*\n\s*name:\s*"([^"]+)"', src
            )
        }

    def test_the_frontend_table_is_still_parseable(self):
        """Vacuity companion — an empty parse would pass every arm below."""
        names = self._frontend_names()
        assert len(names) >= 20, names
        assert names.get("tennis") == "Tennis"

    def test_every_shared_prefix_uses_the_same_word(self):
        frontend = self._frontend_names()
        shared = (set(SPORT_PREFIX_DISPLAY_NAME) & set(frontend)) - FRONTEND_DIVERGENCE
        assert shared, "no overlap — the parse or the map moved"
        mismatched = {
            p: (SPORT_PREFIX_DISPLAY_NAME[p], frontend[p])
            for p in sorted(shared)
            if SPORT_PREFIX_DISPLAY_NAME[p] != frontend[p]
        }
        assert not mismatched, mismatched

    def test_the_documented_divergence_is_still_a_divergence(self):
        """If the frontend ever renames `aussierules`, stop excusing it.

        An exception list that outlives its reason is how a guard becomes
        decorative.
        """
        frontend = self._frontend_names()
        for prefix in FRONTEND_DIVERGENCE:
            if prefix in frontend and prefix in SPORT_PREFIX_DISPLAY_NAME:
                assert SPORT_PREFIX_DISPLAY_NAME[prefix] != frontend[prefix], (
                    f"{prefix} no longer diverges — drop it from "
                    "FRONTEND_DIVERGENCE so the arm above covers it"
                )


# ---------------------------------------------------------------------------
# The creation sites
# ---------------------------------------------------------------------------


AUTO_CREATE_SITES = (
    "backend/app/tasks/odds_polling.py",
    "backend/app/routes/admin_data_quality.py",
    "backend/app/routes/admin_events.py",
)


class TestNoCreationSiteMintsAKeyShapedName:
    """Residue scan over the three places a `Sport` row is born.

    A backfill that leaves a minting path behind is a backfill with an expiry
    date: the next unmapped league the Odds API returns re-creates the bug. These
    are the only three `Sport(` constructions in the app.
    """

    @pytest.mark.parametrize("rel", AUTO_CREATE_SITES)
    def test_the_old_expression_is_gone(self, rel):
        src = (REPO / rel).read_text()
        assert '.replace("_", " ").title()' not in src, rel

    @pytest.mark.parametrize("rel", AUTO_CREATE_SITES)
    def test_the_helper_is_what_names_the_row(self, rel):
        src = (REPO / rel).read_text()
        assert "sport_display_name(" in src, rel

    def test_there_are_no_other_sport_constructions_to_miss(self):
        """The scan above is only complete if these are all of them.

        Counted rather than assumed: a fourth `Sport(` appearing anywhere in the
        app means this file is guarding a subset and does not know it.
        """
        found = []
        for path in (REPO / "backend/app").rglob("*.py"):
            for line in path.read_text().splitlines():
                if re.search(r"(?<![A-Za-z_])Sport\(", line) and "class Sport" not in line:
                    found.append(str(path.relative_to(REPO)))
        assert sorted(set(found)) == sorted(AUTO_CREATE_SITES), sorted(set(found))
