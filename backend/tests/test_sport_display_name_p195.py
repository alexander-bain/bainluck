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

import ast
import pathlib
import re

import pytest

from app.utils.sport_keys import (
    SPORT_PREFIX_DISPLAY_NAME,
    curated_sport_name,
    name_reads_as_a_key,
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

#: CERT-487 [P1]: a `Sport` row is also born from two SQLAlchemy Core upserts,
#: which write `Sport.name` without ever spelling `Sport(`. The census below
#: used to scan source lines for that literal, so these two were invisible to it
#: — the ship claimed exactly three creation paths and there were five.
CORE_UPSERT_SITES = (
    "backend/app/routes/sports.py",
    "backend/app/tasks/sports.py",
)

#: Every creation path names its row through this contract. `sport_display_name`
#: stays legal because it IS the curated word; `curated_sport_name` is the
#: boundary wrapper that also refuses a caller-supplied key-shaped name.
NAMING_CONTRACT = frozenset({"curated_sport_name", "sport_display_name"})


def _creation_sites(kind, model: str) -> set[str]:
    """Every file under `backend/app` that creates a `model` row, by AST.

    Two shapes, selected by `kind`:

    * ``ast.Name`` — the ORM constructor, ``Sport(...)``.
    * ``"insert"`` — a Core insert, ``insert(Sport)...``, which never spells the
      constructor and so is invisible to any scan looking for one.

    `class Sport(Base)` is a `ClassDef`, not a `Call`, so it needs no special
    case — which is the point of doing this structurally.
    """
    found: set[str] = set()
    for path in (REPO / "backend/app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            if kind == "insert":
                hit = (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "insert"
                    and any(
                        isinstance(a, ast.Name) and a.id == model
                        for a in node.args
                    )
                )
            else:
                hit = isinstance(node.func, ast.Name) and node.func.id == model
            if hit:
                found.add(str(path.relative_to(REPO)))
    return found


def _sport_name_arguments(rel: str) -> list[ast.AST]:
    """Every expression that can reach the `name=` of a `Sport(...)` in `rel`.

    One level of local binding is resolved: `admin_events.py` computes
    `display_name` a line above and passes `name=display_name`, so a scan that
    stopped at the argument would see a bare `Name` and conclude the helper is
    not used — a false red that would push the next author to weaken the arm.

    Resolution is deliberately shallow and scoped to the enclosing function. It
    is not a general dataflow analysis and must not grow into one; if a fourth
    site ever needs two levels, inline the call at that site instead.
    """
    tree = ast.parse((REPO / rel).read_text())

    functions = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    def enclosing(call: ast.Call):
        return [f for f in functions if any(n is call for n in ast.walk(f))]

    out: list[ast.AST] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Sport"
        ):
            continue
        for kw in node.keywords:
            if kw.arg != "name":
                continue
            if not isinstance(kw.value, ast.Name):
                out.append(kw.value)
                continue
            # A bare local — resolve it to every assignment in scope. An
            # unresolvable name yields nothing, which reds rather than passes.
            target = kw.value.id
            for func in enclosing(node):
                for stmt in ast.walk(func):
                    if isinstance(stmt, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == target
                        for t in stmt.targets
                    ):
                        out.append(stmt.value)
    return out


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
        """Structural, not textual — read the `name=` argument, not the file.

        `CERT-483` blocked a sibling ship on precisely the weakness a textual
        version of this arm would have: `{false && <Component/>}` left every
        containment check green because the scan saw the tag while the user
        could not reach it. The Python spelling is the same trick — leave a dead
        `sport_display_name(...)` call somewhere in the module, name the row with
        a literal, and a `"sport_display_name(" in src` assertion never notices.

        So this parses the file and walks to the `name=` keyword of the actual
        `Sport(...)` construction. Dead code elsewhere in the module is invisible
        to it, because it is not looking at the module — it is looking at the
        argument. `admin_events.py` wraps the call in `sport_name or ...`, hence
        `ast.walk` over the argument's own subtree rather than an identity check.
        """
        calls = _sport_name_arguments(rel)
        assert calls, f"no Sport(name=...) construction found in {rel}"
        for node in calls:
            named_by = [
                n
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id in NAMING_CONTRACT
            ]
            assert named_by, (
                f"{rel}: a Sport(...) row is named by "
                f"`{ast.unparse(node)}`, which never calls "
                f"{' or '.join(sorted(NAMING_CONTRACT))}"
            )

    def test_the_ast_scan_sees_every_construction(self):
        """Vacuity companion for the arm above.

        A parse that finds nothing passes a `for node in []` loop silently. There
        is exactly one `Sport(...)` construction per site; if that stops being
        true, the arm above is checking a subset and does not know it.
        """
        found = {rel: len(_sport_name_arguments(rel)) for rel in AUTO_CREATE_SITES}
        assert found == {rel: 1 for rel in AUTO_CREATE_SITES}, found

    def test_there_are_no_other_sport_constructions_to_miss(self):
        """The scan above is only complete if these are all of them.

        Counted rather than assumed: a fourth ORM construction anywhere in the
        app means this file is guarding a subset and does not know it.

        STRUCTURAL, not textual, and CERT-487 is the reason twice over. The
        textual version missed two Core upserts because they never spell the
        constructor — and then it flagged three files whose only offence was a
        COMMENT quoting the constructor while explaining that very hole. A scan
        that cannot tell code from prose about code was never a census.
        """
        found = _creation_sites(ast.Name, "Sport")
        assert sorted(found) == sorted(AUTO_CREATE_SITES), sorted(found)

    def test_the_census_also_sees_the_core_upserts(self):
        """CERT-487 [P1]: a Core upsert is a creation path too.

        The arm above answers "where is the constructor written", a question
        about the ORM. This one asks where a `Sport` ROW is born, which is the
        question the ship actually depends on — and the two answers differed by
        two live upsert paths for the whole of UX-P195.
        """
        found = _creation_sites("insert", "Sport")
        assert sorted(found) == sorted(CORE_UPSERT_SITES), sorted(found)

    @pytest.mark.parametrize("rel", CORE_UPSERT_SITES)
    def test_the_core_upsert_names_its_row_through_the_contract(self, rel):
        """Every `name=` reaching an `insert(Sport)` routes through the contract.

        Reads the `.values(...)` keyword and the `on_conflict_do_update` `set_`
        mapping — BOTH, because an upsert that curates on insert and writes the
        raw provider title on conflict is the same bug on the second run.
        """
        tree = ast.parse((REPO / rel).read_text())
        functions = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        def resolve(expr, call):
            """Follow one level of local binding, as the ORM scan does."""
            if not isinstance(expr, ast.Name):
                return [expr]
            out = []
            for func in functions:
                if not any(n is call for n in ast.walk(func)):
                    continue
                for stmt in ast.walk(func):
                    if isinstance(stmt, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == expr.id
                        for t in stmt.targets
                    ):
                        out.append(stmt.value)
            return out

        names: list[ast.AST] = []
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "insert"
                and any(
                    isinstance(a, ast.Name) and a.id == "Sport" for a in node.args
                )
            ):
                continue
            # `.values(name=...)` and `.on_conflict_do_update(set_={"name": ...})`
            # both hang off the same enclosing statement.
            enclosing = [
                f for f in functions if any(n is node for n in ast.walk(f))
            ]
            for func in enclosing:
                for sub in ast.walk(func):
                    if isinstance(sub, ast.Call) and isinstance(
                        sub.func, ast.Attribute
                    ):
                        if sub.func.attr == "values":
                            for kw in sub.keywords:
                                if kw.arg == "name":
                                    names += resolve(kw.value, node)
                        elif sub.func.attr == "on_conflict_do_update":
                            for kw in sub.keywords:
                                if kw.arg != "set_" or not isinstance(
                                    kw.value, ast.Dict
                                ):
                                    continue
                                for k, v in zip(kw.value.keys, kw.value.values):
                                    if (
                                        isinstance(k, ast.Constant)
                                        and k.value == "name"
                                    ):
                                        names += resolve(v, node)

        assert names, f"no insert(Sport) name= found in {rel}"
        for node in names:
            named_by = [
                n
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id in NAMING_CONTRACT
            ]
            assert named_by, (
                f"{rel}: an insert(Sport) row is named by "
                f"`{ast.unparse(node)}`, which never calls "
                f"{' or '.join(sorted(NAMING_CONTRACT))}"
            )

    def test_the_core_upsert_scan_is_not_vacuous(self):
        """Vacuity companion: both arms of both upserts must be found.

        `values(name=)` + `set_["name"]` at each of the two sites = four. A
        parse that silently found nothing would pass the arm above.
        """
        counts = {}
        for rel in CORE_UPSERT_SITES:
            src = (REPO / rel).read_text()
            counts[rel] = src.count("name=sport_name") + src.count(
                '"name": sport_name'
            )
        assert counts == {rel: 2 for rel in CORE_UPSERT_SITES}, counts


# ---------------------------------------------------------------------------
# CERT-487 — the contract, driven at the call sites
# ---------------------------------------------------------------------------


class TestTheContractItself:
    """`curated_sport_name` is the boundary every creation path names through."""

    def test_a_caller_supplied_key_is_refused(self):
        """CERT-487 [P1] verbatim: the attack that made the AST guard a liar.

        `sport_name or sport_display_name(sport_key)` kept one branch calling the
        helper, so the structural scan stayed green while this exact request
        minted the row the whole ship exists to delete.
        """
        assert curated_sport_name("tennis_other", "tennis_other") == "Tennis"

    @pytest.mark.parametrize("key", sorted(MEASURED_KEY_SHAPED_ROWS))
    def test_no_measured_row_can_be_supplied_back_in(self, key):
        out = curated_sport_name(key, key)
        assert out == MEASURED_KEY_SHAPED_ROWS[key]
        assert not name_reads_as_a_key(out, key)

    def test_a_real_provider_title_survives_untouched(self):
        """The refusal must stay narrow.

        The fallback title-cases the KEY, so over-refusing replaces the Odds
        API's "EPL" with "Soccer Epl" — a worse name. This is the arm that fails
        if someone widens `name_reads_as_a_key` to "any lowercase string".
        """
        assert curated_sport_name("soccer_epl", "EPL") == "EPL"
        assert curated_sport_name("soccer_epl", "Premier League") == "Premier League"

    def test_an_absent_name_still_gets_the_curated_word(self):
        assert curated_sport_name("tennis_other") == "Tennis"
        assert curated_sport_name("soccer_epl") == "Soccer Epl"

    def test_the_fallback_is_still_the_helper_verbatim(self):
        """The wrapper must not become a second, drifting naming rule."""
        for key in ("soccer_epl", "tennis_other", "esports", "curling_other"):
            assert curated_sport_name(key, None) == sport_display_name(key)


class _CapturingSession:
    """Stub AsyncSession that records what the upsert actually bound."""

    def __init__(self, scalar_result=None):
        self.statements = []
        self.added = []
        self._scalar_result = scalar_result

    async def execute(self, stmt):
        self.statements.append(stmt)

        class _R:
            def scalar_one_or_none(_self):
                return None

            def all(_self):
                return []

            def scalars(_self):
                return _self

            def first(_self):
                return None

        return _R()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _upsert_name_values(stmt) -> dict[str, object]:
    """The `name` this upsert sends on BOTH arms: insert, and on-conflict.

    The two arms do not look alike once compiled. `.values(name=...)` keeps the
    column name as its bind key, while `on_conflict_do_update(set_=...)` renders
    an ANONYMOUS `%(param_N)s` — so the obvious `params["name"]` reads the insert
    arm and silently reports nothing for the update arm.

    UX-P197's own mutant M7 survived its first draft for exactly that reason:
    curate on insert, write the raw provider title on conflict, and a test that
    only read `params["name"]` stayed green. Which is this file's recurring
    lesson one more time — the thing under test was present, but it was not what
    ran. So the SET clause is located in the compiled SQL and its bind resolved.
    """
    import re as _re

    from sqlalchemy.dialects import postgresql

    compiled = stmt.compile(dialect=postgresql.dialect())
    sql, params = str(compiled), compiled.params

    out: dict[str, object] = {}
    if "name" in params:
        out["insert"] = params["name"]
    m = _re.search(
        r"DO UPDATE SET[^%]*?\bname\s*=\s*%\((\w+)\)s", sql, _re.S
    )
    if m:
        out["on_conflict"] = params.get(m.group(1))
    return out


#: A provider payload whose `title` IS its key. The Odds API has not been
#: observed emitting this, which is exactly why nothing caught the path: the
#: guard proved a property of today's feed, not of the code.
_KEY_SHAPED_FEED = [{"key": "tennis_other", "title": "tennis_other",
                     "group": "Tennis", "active": True}]


class TestTheCoreUpsertsAreDrivenNotJustScanned:
    """CERT-487 [P1], asserted on BEHAVIOUR at the call site.

    The lesson this file keeps paying for: a helper can be defined, imported and
    green across all of its own unit tests while the call site quietly uses
    something else. So these drive the real functions and read the value the
    statement would actually send.
    """

    @pytest.mark.asyncio
    async def test_the_task_upsert_curates_the_name(self, monkeypatch):
        import app.tasks.sports as mod

        class _Svc:
            async def get_sports(self):
                return _KEY_SHAPED_FEED

            async def close(self):
                pass

        session = _CapturingSession()
        monkeypatch.setattr(mod, "OddsAPIService", lambda: _Svc())
        monkeypatch.setattr(mod, "get_task_session", lambda: session)

        result = await mod._sync_sports()

        assert result == {"synced": 1}
        assert session.statements, "the upsert never ran — the arm is vacuous"
        names = _upsert_name_values(session.statements[0])
        assert set(names) == {"insert", "on_conflict"}, names
        assert names == {"insert": "Tennis", "on_conflict": "Tennis"}, names

    @pytest.mark.asyncio
    async def test_the_route_upsert_curates_the_name(self, monkeypatch):
        import app.routes.sports as mod

        class _Svc:
            async def get_sports(self):
                return _KEY_SHAPED_FEED

            async def close(self):
                pass

        session = _CapturingSession()
        monkeypatch.setattr(mod, "OddsAPIService", lambda: _Svc())
        monkeypatch.setattr(mod, "_check_admin_secret", lambda *a, **k: None)

        result = await mod.sync_sports_from_api(
            request=None, secret="x", db=session
        )

        assert result["synced"] == 1
        assert session.statements, "the upsert never ran — the arm is vacuous"
        names = _upsert_name_values(session.statements[0])
        assert set(names) == {"insert", "on_conflict"}, names
        assert names == {"insert": "Tennis", "on_conflict": "Tennis"}, names


class TestTheAdminCreationPathIsDriven:
    """CERT-487 [P1] on `admin_events.py`, driven rather than parsed."""

    @pytest.mark.asyncio
    async def test_a_posted_key_shaped_sport_name_does_not_reach_the_row(
        self, monkeypatch
    ):
        import app.routes.admin_events as mod
        from app.models.models import Sport

        monkeypatch.setattr(mod, "_check_admin_secret", lambda *a, **k: None)
        session = _CapturingSession()

        await mod.create_event_manually(
            request=None,
            secret="x",
            home_team="A",
            away_team="B",
            sport_key="tennis_other",
            sport_name="tennis_other",   # the CERT-487 attack, as a query param
            commence_time=None,
            status="live",
            db=session,
        )

        sports = [o for o in session.added if isinstance(o, Sport)]
        assert len(sports) == 1, session.added
        assert sports[0].name == "Tennis"
        assert not name_reads_as_a_key(sports[0].name, "tennis_other")
