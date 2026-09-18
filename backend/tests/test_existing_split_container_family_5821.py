"""#5821 — the repair CERT-2793 required, `5821-EXISTING-SPLIT-CONTAINERS-COLLAPSE`.

**SHIP: a match page stops hiding its spread and every total on a duplicate row
the page has already folded away.**

Production specimen, 2026-09-17: Lexington SC vs. Orange County SC, kick-off
2026-09-19 23:00Z, is two event rows. The fold keeps `15311859` (7 markets) and
hides `15311852` (11 — the spread and every O/U total). A 390px LOOK at
`/events/15311859` drew the halftime result, the moneyline and the corners, and
**no spread and no total at all**. We hold those markets and do not show them.

Measured over every Polymarket market carrying `venue_game_start`:

    distinct (base title, venue_game_start) keys           10,932
    …spanning more than one event                             183
    …with exactly one base-title holder                       180
    …with two base holders            (ambiguous, refused)      3
    …with no base holder                                        0
    …spanning three or more events                              0

and over the 180 duplicate rows: 0 hold markets naming two different venue
kickoffs, 0 are already tagged, 7 are fixture-anchored (a refusal class).

🔴 PART C IS THE CERT'S NAMED TEST AND IT IS THE ONLY ONE THAT PROVES THE SHIP.
Parts A and B grade the judgement, which could be perfect while the page is
unchanged — the exact failure CERT-2793 BLOCKed the forward fix for. Part C runs
the real `folded_event_ids` over real rows carrying the tag this sweep writes,
because that call inside `_build_game_markets` IS the reader-visible effect.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# The guard suite executes against SQLite, which has no JSONB. The same DDL
# shim `test_proven_duplicate_2263` installs, and for the same reason: Part C
# has to build real `events` rows to run the real `folded_event_ids` over.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport  # noqa: E402
from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.utils.polymarket_container_twins import (  # noqa: E402
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    REFUSE_ANCHORED,
    REFUSE_MIXED_KICKOFF,
    REFUSE_NO_ELECTION,
    ContainerMarket,
    ContainerRow,
    family_key,
    holds_base_title,
    plan_container_tags,
)

#: Every family needs an election, so the default fixture supplies one in which
#: the BASE row wins — the 96-of-125 majority. Tests that care about the other
#: 29 override it explicitly.

CANON_ID = 15311859
DUP_ID = 15311852
SOLO_ID = 15311853
S_SOCCER = 61

KICKOFF = "2026-09-19T23:00:00Z"
OTHER_KICKOFF = "2026-09-20T23:00:00Z"
BASE = "Lexington SC vs. Orange County SC"

COMMENCE = datetime(2026, 9, 19, 23, 0, tzinfo=timezone.utc)


def _m(event_id: int, name: str, vgs: str = KICKOFF) -> ContainerMarket:
    return ContainerMarket(event_id=event_id, name=name, venue_game_start=vgs)


#: The production family, in the shape the venue publishes it: the base event
#: plus five derivatives on one row, and the `- More Markets` container plus the
#: markets it decomposes into on the other.
SPLIT_FAMILY = [
    _m(CANON_ID, BASE),
    _m(CANON_ID, f"{BASE} - Halftime Result"),
    _m(CANON_ID, f"{BASE} - Exact Score"),
    _m(CANON_ID, f"{BASE} - Total Corners"),
    _m(DUP_ID, f"{BASE} - More Markets"),
    _m(DUP_ID, f"{BASE}: O/U 2.5"),
    _m(DUP_ID, "Spread: Lexington SC (-1.5)"),
]


def _rows(winner: int, loser: int, **overrides) -> dict[int, ContainerRow]:
    """A family whose fold election `winner` wins. Ranks are opaque tuples here.

    The judgement only ever COMPARES ranks, so the fixture does not need to
    reproduce `twin_identity_rank`'s internals — and must not, or it would be
    asserting its own copy of the election rather than that the real one is
    deferred to. The sweep's own test covers that it passes the real function's
    output through.
    """
    rows = {
        winner: ContainerRow(winner, identity_rank=(2,)),
        loser: ContainerRow(loser, identity_rank=(1,)),
    }
    for event_id, row in overrides.items():
        rows[int(event_id)] = row
    return rows


#: The 96-of-125 majority: the base-titled row also wins the fold's election.
BASE_WINS = _rows(CANON_ID, DUP_ID)


# ── Part A: the judgement finds the fixture the venue split ──────────────────


class TestTheJudgement:
    def test_the_container_row_is_a_duplicate_of_the_base_row(self):
        """The whole finding: `15311852` is a second copy of `15311859`."""
        plan = plan_container_tags(SPLIT_FAMILY, BASE_WINS)
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [
            (DUP_ID, CANON_ID)
        ]
        assert plan.refusals == []

    def test_the_direction_follows_the_folds_election_not_the_base_title(self):
        """🔴 THE 29-OF-125 CASE, AND THE WHOLE SAFETY OF THIS SWEEP.

        The base title CONFIRMS the family; it does not choose the survivor.
        `repair_5821_split_container_markets.py` measured the split: of 125
        families **96 are won by the base and 29 by the companion**.

        If the container wins the fold's election, the container is canonical
        and the BASE row is the one tagged. Get this backwards and
        `not_a_proven_duplicate` — which runs BEFORE the fold — suppresses the
        row the fold would have elected and sends the reader to the worse of
        the two. That is a new reader-facing defect traded for the one being
        fixed, so it is pinned from both sides.
        """
        base_wins = plan_container_tags(SPLIT_FAMILY, BASE_WINS)
        assert (base_wins.tags[0].canonical_id, base_wins.tags[0].duplicate_id) == (
            CANON_ID,
            DUP_ID,
        )

        companion_wins = plan_container_tags(
            SPLIT_FAMILY, _rows(winner=DUP_ID, loser=CANON_ID)
        )
        assert (
            companion_wins.tags[0].canonical_id,
            companion_wins.tags[0].duplicate_id,
        ) == (DUP_ID, CANON_ID)

    def test_a_family_with_no_election_is_refused_not_defaulted(self):
        """Fail closed. An absent rank is the empty tuple, which is SMALLER than
        every real one, so a defaulting implementation would silently elect
        whichever row happened to load and tag the other — possibly the better
        row — while looking exactly like a clean pass."""
        plan = plan_container_tags(
            SPLIT_FAMILY,
            {
                CANON_ID: ContainerRow(CANON_ID, identity_rank=(2,)),
                DUP_ID: ContainerRow(DUP_ID),  # no rank
            },
        )
        assert plan.tags == []
        assert plan.refusals[0].startswith(REFUSE_NO_ELECTION)

    def test_the_sweep_hands_the_judgement_the_real_election(self):
        """The judgement compares opaque tuples, so the only thing standing
        between it and a home-grown election is that the SWEEP passes
        `twin_identity_rank` through. Asserted on the sweep's source rather
        than mocked: a re-spelled election here would pass every test above.

        🔴 COMMENTS AND DOCSTRINGS ARE STRIPPED FIRST, AND THAT IS NOT
        TIDINESS. The first version of this test searched the raw source, and
        the eager-load mutation SURVIVED it: the line above the code reads
        "`selectinload(Event.sport)` is REQUIRED, not an optimisation", so
        deleting the actual `.options(...)` call left the assertion satisfied by
        the comment explaining why it must not be deleted. A source-scanning
        guard that can be satisfied by prose about itself is vacuous.
        """
        import ast
        import inspect
        import textwrap

        from app.tasks import polymarket_container_twin_sweep as sweep

        tree = ast.parse(textwrap.dedent(inspect.getsource(sweep.load_rows)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                node.value.value = ""  # drop docstrings; comments are already gone
        code = ast.unparse(tree)

        assert "twin_identity_rank(event)" in code
        assert "from app.utils.event_twin_fold import twin_identity_rank" in code
        # The relationship the election's league rung (#2866) reads must be
        # EAGER-loaded: a lazy load raises on an async session, and an unloaded
        # one would silently change the election.
        assert "selectinload(Event.sport)" in code

    def test_a_fixture_on_one_row_is_left_entirely_alone(self):
        """The overwhelming majority: 10,749 of 10,932 keys name one event."""
        plan = plan_container_tags(
            [_m(SOLO_ID, BASE), _m(SOLO_ID, f"{BASE} - More Markets")],
            {SOLO_ID: ContainerRow(SOLO_ID, identity_rank=(1,))},
        )
        assert plan.tags == []
        assert plan.refusals == []
        assert plan.split_keys_examined == 0

    def test_two_fixtures_sharing_a_title_do_not_fold_across_kickoffs(self):
        """The second venue signal, doing the work it is there for.

        The same two clubs meet again. Title equality alone would call these one
        fixture; `venue_game_start` is what keeps them apart, and it is the only
        thing that does.
        """
        plan = plan_container_tags(
            [
                _m(CANON_ID, BASE),
                _m(DUP_ID, f"{BASE} - More Markets", vgs=OTHER_KICKOFF),
            ],
            BASE_WINS,
        )
        assert plan.tags == []
        assert plan.split_keys_examined == 0

    def test_a_market_without_a_kickoff_is_not_judged_at_all(self):
        """One venue signal missing ⇒ today's behaviour, not a guess.

        The same fall-through the forward fix takes, and the reason rows minted
        before the ingest wrote the field are left alone.
        """
        plan = plan_container_tags(
            [
                ContainerMarket(CANON_ID, BASE, ""),
                ContainerMarket(DUP_ID, f"{BASE} - More Markets", ""),
            ],
            BASE_WINS,
        )
        assert plan.tags == []
        assert plan.rows_considered == 0

    def test_player_props_is_a_container_too(self):
        """Both suffixes, because `_strip_more_markets` strips both."""
        plan = plan_container_tags(
            [_m(CANON_ID, BASE), _m(DUP_ID, f"{BASE} - Player Props")], BASE_WINS
        )
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [
            (DUP_ID, CANON_ID)
        ]

    def test_the_base_title_test_agrees_with_the_stripper(self):
        assert holds_base_title(_m(CANON_ID, BASE)) is True
        assert holds_base_title(_m(DUP_ID, f"{BASE} - More Markets")) is False
        assert family_key(_m(DUP_ID, f"{BASE} - More Markets")) == (BASE, KICKOFF)
        assert family_key(_m(CANON_ID, BASE)) == (BASE, KICKOFF)


# ── Part B: the refusals, which are the safety of the whole sweep ────────────


class TestTheRefusals:
    def test_two_base_holders_are_refused_not_guessed(self):
        """3 of 183 keys. The venue's structure does not say which is the fixture."""
        plan = plan_container_tags([_m(CANON_ID, BASE), _m(DUP_ID, BASE)], BASE_WINS)
        assert plan.tags == []
        assert len(plan.refusals) == 1
        assert plan.refusals[0].startswith(REFUSE_AMBIGUOUS)

    def test_an_anchored_duplicate_is_refused(self):
        """7 of 180. Tagging an anchored row as a copy of an id-less one is
        backwards under ruling 048, which argues for keeping the anchored row."""
        plan = plan_container_tags(
            SPLIT_FAMILY,
            _rows(CANON_ID, DUP_ID,
                  **{str(DUP_ID): ContainerRow(DUP_ID, espn_id="401882870",
                                               identity_rank=(1,))}),
        )
        assert plan.tags == []
        assert plan.refusals[0].startswith(REFUSE_ANCHORED)

    def test_a_statpal_id_anchors_a_row_just_as_an_espn_id_does(self):
        plan = plan_container_tags(
            SPLIT_FAMILY,
            _rows(CANON_ID, DUP_ID,
                  **{str(DUP_ID): ContainerRow(DUP_ID, statpal_fixture_id="99123",
                                               identity_rank=(1,))}),
        )
        assert plan.refusals[0].startswith(REFUSE_ANCHORED)

    def test_an_anchored_canonical_does_not_block_its_own_family(self):
        """The refusal is about DIRECTION, not about anchors being present.

        Without this the rule would read "refuse whenever anything is anchored"
        and would decline the families it is most confident about.
        """
        plan = plan_container_tags(
            SPLIT_FAMILY,
            _rows(CANON_ID, DUP_ID,
                  **{str(CANON_ID): ContainerRow(CANON_ID, espn_id="401882870",
                                                 identity_rank=(2,))}),
        )
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [
            (DUP_ID, CANON_ID)
        ]

    def test_a_duplicate_holding_two_kickoffs_is_refused(self):
        """0 rows today; here for the row that is not.

        Folding a row that holds a SECOND fixture's markets would carry those
        markets onto this page, which is worse than the defect being repaired.
        """
        plan = plan_container_tags(
            SPLIT_FAMILY,
            _rows(CANON_ID, DUP_ID,
                  **{str(DUP_ID): ContainerRow(
                      DUP_ID, identity_rank=(1,),
                      venue_game_starts=frozenset({KICKOFF, OTHER_KICKOFF}))}),
        )
        assert plan.tags == []
        assert plan.refusals[0].startswith(REFUSE_MIXED_KICKOFF)

    def test_one_kickoff_on_the_row_is_the_healthy_case(self):
        """🔴 The NULL-coalesce trap, pinned.

        Counting markets with NO kickoff as a distinct value reads 109 of the
        180 duplicate rows as "mixed" — every one of them a row holding one
        market the ingest stamped and one it did not — and takes the sweep's
        reach from 173 families to 64 for no defect at all. Only NON-NULL
        kickoffs are collected, so a row with one real kickoff is one value.
        """
        plan = plan_container_tags(
            SPLIT_FAMILY,
            _rows(CANON_ID, DUP_ID,
                  **{str(DUP_ID): ContainerRow(DUP_ID, identity_rank=(1,),
                                               venue_game_starts=frozenset({KICKOFF}))}),
        )
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [
            (DUP_ID, CANON_ID)
        ]

    def test_the_verdict_names_are_not_interchangeable(self):
        assert len({NOT_A_TWIN, REFUSE_AMBIGUOUS, REFUSE_ANCHORED,
                    REFUSE_MIXED_KICKOFF, REFUSE_NO_ELECTION}) == 5


# ── Part C: the cert's named test — the page actually gets the markets ───────


class _SyncAsAsync:
    """The one `await db.execute(...)` `folded_event_ids` makes, over a sync Session."""

    def __init__(self, session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


def _event(event_id: int, tags):
    return Event(
        id=event_id,
        sport_id=S_SOCCER,
        home_team_name="Lexington SC",
        away_team_name="Orange County SC",
        commence_time=COMMENCE,
        event_tags=tags,
    )


@pytest.fixture
def split_family_engine():
    """The production pair, untagged, exactly as the sweep finds it."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_SOCCER, key="soccer_usa_usl", name="USL Championship"))
        s.add(_event(CANON_ID, None))
        s.add(_event(DUP_ID, None))
        s.commit()
    return eng


def _apply_plan(eng, plan):
    """Write the sweep's tags the way `write_tags` does, in one place.

    The test applies the PLAN rather than a hand-written tag so that a change to
    what the judgement decides cannot leave this proof passing on a tag the
    sweep would never write.
    """
    with Session(eng) as s:
        for tag in plan.tags:
            row = s.get(Event, tag.duplicate_id)
            row.event_tags = list(row.event_tags or []) + [
                duplicate_tag(tag.canonical_id)
            ]
        s.commit()


def _folded(eng, event_id):
    from app.utils.proven_duplicates import folded_event_ids

    with Session(eng) as s:
        return asyncio.run(folded_event_ids(_SyncAsAsync(s), event_id))


class TestTheSplitFamilyServesOneEvent:
    def test_existing_split_container_family_serves_one_event_5821(
        self, split_family_engine
    ):
        """CERT-2793's named test. The ship, end to end.

        BEFORE: `/events/15311859` reads markets from `[15311859]`, so the
        spread and every total — which live on `15311852` — are not on the page.
        AFTER: it reads from both rows, which is what `_build_game_markets` does
        with this list.
        """
        assert _folded(split_family_engine, CANON_ID) == [CANON_ID]

        _apply_plan(split_family_engine, plan_container_tags(SPLIT_FAMILY, BASE_WINS))

        assert _folded(split_family_engine, CANON_ID) == [CANON_ID, DUP_ID]

    def test_the_duplicate_does_not_swallow_the_canonical_in_reverse(
        self, split_family_engine
    ):
        """The fold is directional: the hidden row gains nothing.

        Without this a symmetric implementation would pass the test above and
        also serve the canonical's markets on the duplicate's page, which is the
        duplicate card coming back with prices on it.
        """
        _apply_plan(split_family_engine, plan_container_tags(SPLIT_FAMILY, BASE_WINS))
        assert _folded(split_family_engine, DUP_ID) == [DUP_ID]

    def test_a_refused_family_changes_nothing_on_the_page(
        self, split_family_engine
    ):
        """A refusal is not a quiet half-repair — it leaves the page as it was."""
        ambiguous = [_m(CANON_ID, BASE), _m(DUP_ID, BASE)]
        _apply_plan(split_family_engine, plan_container_tags(ambiguous, BASE_WINS))
        assert _folded(split_family_engine, CANON_ID) == [CANON_ID]


# ── Part D: the sweep cannot go inert without saying so ──────────────────────


class TestTheSweepReportsItsOwnConsumer:
    def test_fold_is_live_reads_the_real_consumer(self):
        """The tag's ENTIRE user-visible effect is `folded_event_ids` inside
        `_build_game_markets`. If that call is removed this sweep keeps writing
        tags and delivers nothing — a repair that passes its own mechanism and
        ships no ship. The sweep reports the answer on every run, including a
        quiet one."""
        from app.tasks.polymarket_container_twin_sweep import fold_is_live

        assert fold_is_live() is True

    def test_the_backup_table_is_its_own(self):
        """Sharing a sibling's table would make the undos inseparable."""
        from app.tasks.polymarket_container_twin_sweep import BAK_TABLE
        from app.tasks.soccer_ghost_twin_sweep import BAK_TABLE as SOCCER_BAK

        assert BAK_TABLE == "bak_5821_container_twin_tags"
        assert BAK_TABLE != SOCCER_BAK

    def test_already_tagged_rows_are_never_given_a_second_canonical(self):
        """Two `duplicate-of` elements on one row is a state no consumer has a
        rule for, and this sweep must never be the thing that creates it."""
        from app.tasks.polymarket_container_twin_sweep import already_tagged_ids

        assert already_tagged_ids(
            {
                DUP_ID: f'["{duplicate_tag(CANON_ID)}"]',
                CANON_ID: "[]",
                SOLO_ID: '["audience:casual"]',
            }
        ) == {DUP_ID}


# ── Part E: the verdict contract (CERT-3030) ─────────────────────────────────
#
# WHY THIS PART EXISTS. CERT-3030 BLOCKed the first presentation: the mechanism
# in Parts A–D worked and 134 tests passed, and the recurring ship could still
# fail silently. `polymarket_container_twin_sweep` was absent from
# `ENFORCED_TASKS`, and it returned `applied` / `planned` — words that are in
# NEITHER terminal vocabulary — so every run classified as
# `unrecognised:terminal:applied`, non-authoritative, and `_tracked_run`
# advanced `last_success_at` regardless.
#
# That receipt is the one this ship's after-check grades on, so the measurement
# and the thing measured shared a failure mode: a pass whose population read had
# gone dark would have advanced the receipt and been read as proof the fix had
# landed. These tests are the guard for that class.

import contextlib  # noqa: E402

# The import-from form, matching how this module is already aliased at the top
# of Part A. A plain `import app.tasks.polymarket_container_twin_sweep as sweep`
# beside the `from ... import X` lines above trips CodeQL's
# `py/import-and-import-from` (a note, no security severity) for no benefit.
from app.tasks import polymarket_container_twin_sweep as sweep  # noqa: E402
from app.utils.task_verdict import ENFORCED_TASKS, verdict_for  # noqa: E402


def _filler(n: int, *, start: int = 900000):
    """`n` markets on `n` distinct one-holder keys — population, never a plan.

    Each has its own title AND its own event, so every key has exactly one base
    holder and the judgement returns NOT_A_TWIN. They exist only to lift
    `markets_read` over the floor without contributing a tag.
    """
    return [_m(start + i, f"Filler {i} FC vs. Filler {i} United") for i in range(n)]


def _over_floor(extra=()):
    """A population comfortably above `MIN_MARKETS_FLOOR`, plus `extra`."""
    return [*_filler(sweep.MIN_MARKETS_FLOOR), *extra]


def _run(
    markets,
    monkeypatch,
    *,
    rows=None,
    apply=True,
    fold_live=True,
    read_raises=False,
    confirm=None,
    write_failed=(),
):
    """Drive the REAL run function; fake only the database edges.

    `plan_container_tags` is deliberately NOT faked — the plan these tests
    grade is the one production would compute.
    """
    calls: list[str] = []

    known = dict(BASE_WINS)
    for market in markets:
        known.setdefault(market.event_id, ContainerRow(market.event_id, identity_rank=(1,)))
    if rows:
        known.update(rows)

    async def _load_rows(session, *, lookback, lookahead):
        calls.append("load_rows")
        if read_raises:
            raise RuntimeError("relation futures_markets does not exist")
        return list(markets), known, {}

    async def _ensure_backup(session, todo, current_tags):
        calls.append("ensure_backup")
        return len(todo)

    async def _write_tags(session, todo, *, progress_every=0):
        calls.append("write_tags")
        failed = list(write_failed)
        return len([t for t in todo if t.duplicate_id not in failed]), failed

    async def _tagged_now(session, ids):
        calls.append("tagged_now")
        return set(ids) if confirm is None else set(confirm)

    class _Session:
        """Only the edge the run function touches directly: the rollback it
        issues when the population read raises."""

        async def rollback(self):
            calls.append("rollback")

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield _Session()

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)
    monkeypatch.setattr(sweep, "load_rows", _load_rows)
    monkeypatch.setattr(sweep, "ensure_backup", _ensure_backup)
    monkeypatch.setattr(sweep, "write_tags", _write_tags)
    monkeypatch.setattr(sweep, "tagged_now", _tagged_now)
    monkeypatch.setattr(sweep, "fold_is_live", lambda: fold_live)

    summary = asyncio.run(sweep.run_polymarket_container_twin_sweep(apply=apply))
    return summary, calls


def test_it_is_enrolled_in_enforced_tasks():
    """Enrolment is what makes the terminal anybody's alarm. Outside the set
    `verdict_for` returns a non-authoritative `unknown` whatever the run did."""
    assert "polymarket_container_twin_sweep" in ENFORCED_TASKS


class TestTheTerminalsAreInTheVocabulary:
    """The defect CERT-3030 named: a word the contract does not know reads as
    `unrecognised` and never blocks a success."""

    def test_the_applied_path_is_authoritatively_complete(self, monkeypatch):
        summary, _ = _run(_over_floor(SPLIT_FAMILY), monkeypatch)

        assert summary["terminal"] == "complete"
        verdict = verdict_for("polymarket_container_twin_sweep", summary)
        assert verdict.verdict == "complete"
        assert verdict.authoritative is True

    def test_no_terminal_this_task_emits_is_unrecognised(self, monkeypatch):
        """The strawman for the whole part. Every reachable exit is driven and
        each verdict must be authoritative — `unrecognised:` is the string the
        old `applied` and `planned` produced."""
        cases = {
            "applied": _run(_over_floor(SPLIT_FAMILY), monkeypatch),
            "quiet": _run(_over_floor(), monkeypatch),
            "dry_run": _run(_over_floor(SPLIT_FAMILY), monkeypatch, apply=False),
            "thin": _run(_filler(3), monkeypatch),
            "raised": _run(_over_floor(), monkeypatch, read_raises=True),
            "no_fold": _run(_over_floor(SPLIT_FAMILY), monkeypatch, fold_live=False),
            "unconfirmed": _run(_over_floor(SPLIT_FAMILY), monkeypatch, confirm=[]),
        }
        for name, (summary, _) in cases.items():
            verdict = verdict_for("polymarket_container_twin_sweep", summary)
            assert "unrecognised" not in verdict.reason, f"{name}: {verdict.reason}"
            assert verdict.authoritative is True, f"{name}: {verdict.reason}"


class TestTheTwoZerosDoNotShareAVerdict:
    def test_a_drained_backlog_reads_green(self, monkeypatch):
        """🔴 `complete`, not `no_work`, and this is the difference from the
        tennis sibling's plan floor. This backlog DRAINS: after the first
        successful pass every family in the window is labelled and every later
        pass plans zero forever. `no_work` is an authoritative UNKNOWN, so a
        plan floor would make the permanent healthy state permanently not-green.
        """
        summary, calls = _run(_over_floor(), monkeypatch)

        assert summary["terminal"] == "complete"
        assert summary["tagged"] == 0
        assert summary["pairs_found"] == 0
        assert "write_tags" not in calls
        assert verdict_for("polymarket_container_twin_sweep", summary).verdict == "complete"

    def test_a_population_that_collapses_is_failed_not_complete(self, monkeypatch):
        """The same zero for the opposite reason. A lost join or a renamed
        source filter reads a handful of rows and plans nothing, which from
        outside is identical to the drained steady state above and means the
        opposite. Without the floor the task records GREEN forever while every
        split family keeps hiding its spread."""
        summary, calls = _run(_filler(3), monkeypatch)

        assert summary["terminal"] == "failed"
        assert summary["measured"] is False
        assert "below the floor" in summary["reason"]
        assert "write_tags" not in calls
        assert verdict_for("polymarket_container_twin_sweep", summary).verdict == "failed"

    def test_an_empty_read_is_failed_not_no_work(self, monkeypatch):
        """🔴 A DELIBERATE DIVERGENCE FROM THE SOCCER SIBLING, which calls an
        empty window `no_work` because soccer ghosts are episodic. This window
        is ±45 days across every sport Polymarket lists and was measured at
        11,391 and 11,410 markets a week apart. Zero is not a quiet day here;
        it is a broken read."""
        summary, _ = _run([], monkeypatch)

        assert summary["terminal"] == "failed"
        assert summary["markets_read"] == 0

    def test_the_floor_is_not_waived_by_having_found_a_family(self, monkeypatch):
        """A thin window that happens to contain one decidable family is still
        a thin window. Finding a pair earns no veto over the population band —
        that waiver is the hole CERT-2193 found in the tennis sibling."""
        summary, calls = _run([*SPLIT_FAMILY, *_filler(3)], monkeypatch)

        assert summary["terminal"] == "failed"
        assert "write_tags" not in calls

    def test_a_read_that_raises_is_failed_and_unmeasured(self, monkeypatch):
        """"I could not look" is not "there was nothing to do" (gotcha #53)."""
        summary, _ = _run(_over_floor(), monkeypatch, read_raises=True)

        assert summary["terminal"] == "failed"
        assert summary["measured"] is False

    def test_a_dry_run_banks_nothing_and_cannot_vouch(self, monkeypatch):
        """`no_work` — an authoritative unknown. The old `planned` was not in
        the vocabulary at all."""
        summary, calls = _run(_over_floor(SPLIT_FAMILY), monkeypatch, apply=False)

        assert summary["terminal"] == "no_work"
        assert summary["planned"] == 1
        assert "write_tags" not in calls
        assert verdict_for("polymarket_container_twin_sweep", summary).verdict == "unknown"


class TestTheConsumerGatesTheWrite:
    def test_tags_are_withheld_loudly_when_the_fold_is_gone(self, monkeypatch):
        """Previously `fold_live` was REPORTED and not acted on. The tag is
        inert without `folded_event_ids`: it suppresses a card and delivers no
        markets to the canonical page, so writing it is not a partial win."""
        summary, calls = _run(_over_floor(SPLIT_FAMILY), monkeypatch, fold_live=False)

        assert summary["terminal"] == "failed"
        assert summary["tagged"] == 0
        assert "write_tags" not in calls
        assert "ensure_backup" not in calls
        assert "folded_event_ids" in summary["reason"]

    def test_a_quiet_day_is_still_green_without_the_fold(self, monkeypatch):
        """The gate gates WRITES, not the run. With nothing to write there is
        nothing to withhold, and `fold_live` is still reported so the signal is
        visible BEFORE a write is pending rather than only once one is."""
        summary, _ = _run(_over_floor(), monkeypatch, fold_live=False)

        assert summary["terminal"] == "complete"
        assert summary["fold_live"] is False


class TestEveryPlannedTagIsConfirmedOnDisk:
    def test_a_write_that_does_not_land_is_partial(self, monkeypatch):
        """`written` is a sum of rowcounts; `confirmed_on_disk` is a read-back,
        and only the second survives a commit that did not stick. A terminal of
        `complete` here would advance the receipt on a pass that wrote nothing.
        """
        summary, _ = _run(_over_floor(SPLIT_FAMILY), monkeypatch, confirm=[])

        assert summary["terminal"] == "partial"
        assert summary["unconfirmed_count"] == 1
        assert summary["unconfirmed"] == [DUP_ID]
        assert verdict_for("polymarket_container_twin_sweep", summary).verdict == "partial"

    def test_a_write_that_raises_is_partial_and_names_the_row(self, monkeypatch):
        summary, _ = _run(
            _over_floor(SPLIT_FAMILY), monkeypatch, write_failed=[DUP_ID], confirm=[]
        )

        assert summary["terminal"] == "partial"
        assert summary["errors"] == [DUP_ID]

    def test_damage_is_reported_under_the_contracts_own_key(self, monkeypatch):
        """`_ERROR_COLLECTIONS` is ("errors", "failed_chunks", "failed_phases"),
        so a key called `failed` is invisible to `_has_damage`. Naming it
        `errors` means the contract downgrades a `complete` this function got
        wrong, instead of trusting this function to be the only guard."""
        from app.utils.task_verdict import _has_damage

        assert _has_damage({"errors": [DUP_ID]}) == "errors"
        assert _has_damage({"failed": [DUP_ID]}) is None

        summary, _ = _run(_over_floor(SPLIT_FAMILY), monkeypatch)
        assert "errors" in summary


class TestARefusalIsNotDamage:
    def test_a_run_carrying_refusals_is_still_complete(self, monkeypatch):
        """🔴 A PRODUCTION STEADY STATE, not an edge case. The measured window
        holds 7 fixture-anchored families and 3 ambiguous ones that this sweep
        refuses BY DESIGN and will refuse on every pass forever.

        Refusals are reported in the summary, so the question is whether the
        contract reads them as damage. `_ERROR_COLLECTIONS` is
        ("errors", "failed_chunks", "failed_phases") and `refusals` is none of
        them — but that is an argument, and the cost of it being wrong is a task
        that is never green for doing exactly what it was built to do. Pinned.
        """
        ambiguous = [_m(770001, "Ambiguous FC vs. Ambiguous United"),
                     _m(770002, "Ambiguous FC vs. Ambiguous United")]
        summary, _ = _run(
            _over_floor([*SPLIT_FAMILY, *ambiguous]),
            monkeypatch,
            rows={770001: ContainerRow(770001, identity_rank=(2,)),
                  770002: ContainerRow(770002, identity_rank=(1,))},
        )

        assert summary["refusals"] >= 1, "the fixture stopped producing a refusal"
        assert summary["terminal"] == "complete"
        verdict = verdict_for("polymarket_container_twin_sweep", summary)
        assert verdict.verdict == "complete", verdict.reason
