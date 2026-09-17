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
    ContainerMarket,
    ContainerRow,
    family_key,
    holds_base_title,
    plan_container_tags,
)

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


# ── Part A: the judgement finds the fixture the venue split ──────────────────


class TestTheJudgement:
    def test_the_container_row_is_a_duplicate_of_the_base_row(self):
        """The whole finding: `15311852` is a second copy of `15311859`."""
        plan = plan_container_tags(SPLIT_FAMILY)
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [
            (DUP_ID, CANON_ID)
        ]
        assert plan.refusals == []

    def test_the_direction_is_not_reversible(self):
        """The BASE row is canonical, never the container.

        Stated as its own test because the pair is symmetric in every signal the
        key reads — same title, same kickoff, same sport, neither anchored — so
        the only thing choosing a direction is which row holds the base-titled
        market. A change that lost that would still produce one tag per family
        and would fold every fixture's real markets onto its overflow basket.
        """
        plan = plan_container_tags(SPLIT_FAMILY)
        assert plan.tags[0].canonical_id == CANON_ID
        assert plan.tags[0].duplicate_id == DUP_ID

    def test_a_fixture_on_one_row_is_left_entirely_alone(self):
        """The overwhelming majority: 10,749 of 10,932 keys name one event."""
        plan = plan_container_tags(
            [_m(SOLO_ID, BASE), _m(SOLO_ID, f"{BASE} - More Markets")]
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
            ]
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
            ]
        )
        assert plan.tags == []
        assert plan.rows_considered == 0

    def test_player_props_is_a_container_too(self):
        """Both suffixes, because `_strip_more_markets` strips both."""
        plan = plan_container_tags(
            [_m(CANON_ID, BASE), _m(DUP_ID, f"{BASE} - Player Props")]
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
        plan = plan_container_tags([_m(CANON_ID, BASE), _m(DUP_ID, BASE)])
        assert plan.tags == []
        assert len(plan.refusals) == 1
        assert plan.refusals[0].startswith(REFUSE_AMBIGUOUS)

    def test_an_anchored_duplicate_is_refused(self):
        """7 of 180. Tagging an anchored row as a copy of an id-less one is
        backwards under ruling 048, which argues for keeping the anchored row."""
        plan = plan_container_tags(
            SPLIT_FAMILY,
            {DUP_ID: ContainerRow(DUP_ID, espn_id="401882870")},
        )
        assert plan.tags == []
        assert plan.refusals[0].startswith(REFUSE_ANCHORED)

    def test_a_statpal_id_anchors_a_row_just_as_an_espn_id_does(self):
        plan = plan_container_tags(
            SPLIT_FAMILY,
            {DUP_ID: ContainerRow(DUP_ID, statpal_fixture_id="99123")},
        )
        assert plan.refusals[0].startswith(REFUSE_ANCHORED)

    def test_an_anchored_canonical_does_not_block_its_own_family(self):
        """The refusal is about DIRECTION, not about anchors being present.

        Without this the rule would read "refuse whenever anything is anchored"
        and would decline the families it is most confident about.
        """
        plan = plan_container_tags(
            SPLIT_FAMILY,
            {
                CANON_ID: ContainerRow(CANON_ID, espn_id="401882870"),
                DUP_ID: ContainerRow(DUP_ID),
            },
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
            {
                DUP_ID: ContainerRow(
                    DUP_ID, venue_game_starts=frozenset({KICKOFF, OTHER_KICKOFF})
                )
            },
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
            {DUP_ID: ContainerRow(DUP_ID, venue_game_starts=frozenset({KICKOFF}))},
        )
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [
            (DUP_ID, CANON_ID)
        ]

    def test_the_verdict_names_are_not_interchangeable(self):
        assert len({NOT_A_TWIN, REFUSE_AMBIGUOUS, REFUSE_ANCHORED,
                    REFUSE_MIXED_KICKOFF}) == 4


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

        _apply_plan(split_family_engine, plan_container_tags(SPLIT_FAMILY))

        assert _folded(split_family_engine, CANON_ID) == [CANON_ID, DUP_ID]

    def test_the_duplicate_does_not_swallow_the_canonical_in_reverse(
        self, split_family_engine
    ):
        """The fold is directional: the hidden row gains nothing.

        Without this a symmetric implementation would pass the test above and
        also serve the canonical's markets on the duplicate's page, which is the
        duplicate card coming back with prices on it.
        """
        _apply_plan(split_family_engine, plan_container_tags(SPLIT_FAMILY))
        assert _folded(split_family_engine, DUP_ID) == [DUP_ID]

    def test_a_refused_family_changes_nothing_on_the_page(
        self, split_family_engine
    ):
        """A refusal is not a quiet half-repair — it leaves the page as it was."""
        ambiguous = [_m(CANON_ID, BASE), _m(DUP_ID, BASE)]
        _apply_plan(split_family_engine, plan_container_tags(ambiguous))
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
