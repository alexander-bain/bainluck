"""#2878 — the sweep, end to end: two cards for one match become one.

This is the file CERT-2142 asked for. That block was right: the previous diff
was a classifier with no caller, so nothing a user could see changed. What is
graded here is the whole path —

    production-shaped rows
      → `repair_2878_tennis_twin_ghosts.build_plan`   (the script's own wiring)
      → `provenance:duplicate-of:<canonical>`
      → the REAL league-page rails from `app.routes.league_futures`
      → one card

— plus the two refusals that stop it hiding a real match.

WHY THE TEST THE BLOCK NAMED IS NOT THE TEST HERE
─────────────────────────────────────────────────
The block asked for `test_us_open_semifinal_appears_once_after_twin_sweep`. That
test cannot be written truthfully, and finding out why changed the ship:

**A semi-final has not been played yet, and the score is the only field that
separates a ghost from its canonical.** Measured on production 2026-09-06 across
172 candidate pairs: 0 ghosts carry a score, but 110 carry prediction markets and
63 carry MORE markets than their own canonical. For the two semi-finals live that
day the ghost held 13 and 17 markets against the canonical's 0 and 1 — so hiding
the ghost would have taken away nearly all the market coverage and left a bare
card. `classify_pair` refuses that pair, correctly, and
`TestTheSemiFinalIsRefusedAndThatIsTheRightAnswer` pins it with those ids.

So the ship this file graded at first was the settled half:
**a US Open match that has been PLAYED appears once on the tour page, not twice.**
162 pairs on production.

UPDATE 2026-09-07 — #2693 LIFTED THAT LIMIT, AND THE TEST THE BLOCK ASKED FOR
─────────────────────────────────────────────────────────────────────────────
Both halves are graded here now, and the semi-final test the block named exists
under `TestTheShip.test_tomorrows_quarter_final_also_appears_once`. Two changes
made it truthful, and neither on its own would have been:

* the PROVIDER ID separates an unplayed pair where the score cannot — 250/250
  tournament-keyed rows carry one, 0/1259 bare rows do
  (`tennis_twin_pairs.row_is_id_anchored`);
* the surviving card now READS the suppressed row's markets, so Cerundolo's 17
  move onto the canonical instead of disappearing
  (`proven_duplicates.folded_event_ids`, graded in
  `test_proven_duplicate_2263.TestTheFold`).

🔴 Note what is still true: **nothing is merged, deleted or repointed.** The
markets are folded at READ time. An `UPDATE futures_markets SET event_id` on a
name-and-time correspondence is what ruling 048 bans, and it is still banned.

WHY BOTH RAILS ARE SEEDED
─────────────────────────
The double print is not one rail printing twice; it is two rails printing one
match each. The canonical is `completed` and lands on RECENT RESULTS; the ghost
still says `scheduled` long past its own kickoff and lands on NO RESULT REPORTED
(#3211's rail). A test that drove only one of them would have passed against the
bug — `unreported_games_query` was the one rail of the three that did not carry
`not_a_proven_duplicate()`, so 99 of the 162 ghosts kept their card after being
tagged.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.league_futures import (  # noqa: E402
    recent_results_query,
    unreported_games_query,
    upcoming_games_query,
)
from app.services.anchor_channel import duplicate_tag  # noqa: E402
from scripts.repair_2878_tennis_twin_ghosts import build_plan  # noqa: E402

# ── The production specimen, to the id ──────────────────────────────────────
#
# Etcheverry–Michelsen, the pair #3677 published as its cleanest evidence:
#   /sports            /events/15304938  Tomas Martin Etcheverry vs Alex Michelsen
#   /sport/tennis/atp  /events/15304918  M Michelsen / E Etcheverry — No result reported
GHOST_ID = 15304918
CANON_ID = 15304938
S_ATP = 1
S_ATP_US_OPEN = 2

NOW = datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc)
#: The ghost carries the draw-publication midnight, not the match time — 145 of
#: 172 measured ghosts are stamped exactly 00:00:00.
GHOST_TIME = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
CANON_TIME = datetime(2026, 9, 4, 17, 10, tzinfo=timezone.utc)


class _Row:
    """A `load_rows` row, which is a SQLAlchemy Row and not an ORM object.

    Built by hand rather than selected, so the planner wiring is exercised on
    exactly the field names the script's SQL projects. If that SELECT is renamed
    this breaks, which is the point.
    """

    def __init__(
        self,
        *,
        id,
        sport_key,
        home,
        away,
        at,
        hs=None,
        aws=None,
        tags="[]",
        external_id=None,
        espn_id=None,
        statpal_fixture_id=None,
    ):
        self.id = id
        self.sport_key = sport_key
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = at
        self.home_score = hs
        self.away_score = aws
        self.tags_text = tags
        # #2693 — the three provider-id columns `row_is_id_anchored` reads. They
        # default to None (unanchored) because that is what a ghost carries; a
        # canonical sets one explicitly, exactly as production does.
        self.external_id = external_id
        self.espn_id = espn_id
        self.statpal_fixture_id = statpal_fixture_id


def _ghost_row(**kw):
    base = dict(
        id=GHOST_ID,
        sport_key="tennis_atp",
        home="Michelsen",
        away="Etcheverry",
        at=GHOST_TIME,
    )
    return _Row(**{**base, **kw})


def _canon_row(**kw):
    base = dict(
        id=CANON_ID,
        sport_key="tennis_atp_us_open",
        home="Alex Michelsen",
        away="Tomas Martin Etcheverry",
        at=CANON_TIME,
        hs=1,
        aws=3,
        # 250/250 tournament-keyed rows on production carry all three.
        external_id="772774e181b7af9eada58d",
        espn_id="182738",
    )
    return _Row(**{**base, **kw})


# ════════════════════════════════════════════════════════════════════════════
# Part A — the plan, from the script's own wiring
# ════════════════════════════════════════════════════════════════════════════


class TestThePlanTheScriptBuilds:
    def test_the_settled_pair_yields_exactly_one_tag(self):
        plan = build_plan([_ghost_row(), _canon_row()])
        assert len(plan.tags) == 1
        tag = plan.tags[0]
        assert tag.ghost_id == GHOST_ID
        assert tag.canonical_id == CANON_ID

    def test_the_tag_points_at_the_row_that_has_the_result(self):
        """Direction is the whole safety property. Tagging the canonical would
        hide the only row carrying the score."""
        plan = build_plan([_canon_row(), _ghost_row()])  # reversed input order
        assert plan.tags[0].ghost_id == GHOST_ID

    def test_two_bare_rows_for_one_match_both_name_the_same_canonical(self):
        """A star, not a chain — the real shape 12 times on production.
        `Li/Ruzic` exists as two bare rows and one tournament row."""
        second = _ghost_row(id=GHOST_ID + 1, home="A Michelsen", away="T Etcheverry")
        plan = build_plan([_ghost_row(), second, _canon_row()])
        assert {t.ghost_id for t in plan.tags} == {GHOST_ID, GHOST_ID + 1}
        assert {t.canonical_id for t in plan.tags} == {CANON_ID}

    def test_a_row_already_carrying_the_tag_is_not_re_planned(self):
        """Idempotence is in the database (`NOT @>`) AND here, because the
        script filters on `already_tagged_ids` before writing."""
        from scripts.repair_2878_tennis_twin_ghosts import already_tagged_ids

        tagged = _ghost_row(tags=f'["{duplicate_tag(CANON_ID)}"]')
        assert already_tagged_ids([tagged, _canon_row()]) == {GHOST_ID}


class TestTheRefusalsThatStopItHidingARealMatch:
    """Under-tagging is the intended failure direction. Each of these is a case
    where acting would cost a user a real match, and each refuses."""

    def test_a_qualifying_meeting_is_not_folded_into_the_main_draw(self):
        """🔴 The live false-pair hazard, with the production ids.

        `15294924` and `15295192` are bare rows dated 2026-08-28 — US Open
        QUALIFYING week — whose participants agree with a main-draw match played
        2026-09-03 (`15301184`, Bonzi/Buse). Two players CAN meet in qualifying
        and again in the main draw, and that is a real pair of distinct matches
        wearing exactly the shape of a twin. The block key is a global
        `(surname, surname)` pair with no time component, so only the separation
        fence stands between this and a real match being hidden.
        """
        far = _ghost_row(at=CANON_TIME - timedelta(hours=165))
        plan = build_plan([far, _canon_row()])
        assert plan.tags == ()
        assert any("fence" in r for r in plan.refusals)

    def test_a_ghost_claimed_by_two_canonicals_is_refused_entirely(self):
        """If the block key HAS fused two fixtures, no label can be written
        without choosing between them, so none is."""
        other = _canon_row(
            id=CANON_ID + 1, at=CANON_TIME + timedelta(hours=2), hs=3, aws=0
        )
        plan = build_plan([_ghost_row(), _canon_row(), other])
        assert plan.tags == ()
        assert any("fused two fixtures" in r for r in plan.refusals)

    def test_a_bare_row_that_was_itself_settled_is_left_alone(self):
        plan = build_plan([_ghost_row(hs=3, aws=1), _canon_row()])
        assert plan.tags == ()

    def test_a_futures_title_in_the_team_column_is_never_a_candidate(self):
        title = _ghost_row(home="Black Desert Resort (Men's Doubles) Winner", away="Yes")
        plan = build_plan([title, _canon_row()])
        assert plan.tags == ()


class TestTheUnplayedMatchTheScoreCouldNotReach:
    """#2693 — the limit this file used to pin, and how it was lifted.

    Until 2026-09-07 this class was
    ``TestTheSemiFinalIsRefusedAndThatIsTheRightAnswer`` and it asserted
    ``plan.tags == ()`` for an unplayed pair. That was correct at the time: the
    score was the only field that separated ghost from canonical, and the market
    books were on the GHOST —

        ghost 15305538 Andreeva/Potapova  13 markets → canonical 15305579   0
        ghost 15305553 Cerundolo/Blockx   17 markets → canonical 15305578   1

    — so tagging would have removed the only card with prices on it.

    Two changes lifted it, and BOTH are load-bearing:

    1. ``row_is_id_anchored`` — the provider id separates an unplayed pair.
       250/250 tournament-keyed rows carry one, 0/1259 bare rows do.
    2. ``proven_duplicates.folded_event_ids`` in ``_build_game_markets`` — the
       surviving card reads the suppressed row's markets, so the 17 move rather
       than vanish. Pinned in ``test_proven_duplicate_2263.TestTheFold``.

    🔴 The refusals below are what keeps (1) honest. Under-tagging is still the
    intended failure direction.
    """

    def test_an_unplayed_match_is_now_decided_by_the_provider_id(self):
        """THE #2693 SHIP, through the script's own wiring: 6 QFs, 6 tags."""
        plan = build_plan([_ghost_row(), _canon_row(hs=None, aws=None)])
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (GHOST_ID, CANON_ID)
        ]

    def test_an_unplayed_pair_with_no_provider_id_anywhere_is_still_refused(self):
        """Nothing separates them, so nothing is written — and the refusal names
        both rows, so whoever looks next can find them."""
        plan = build_plan(
            [
                _ghost_row(),
                _canon_row(hs=None, aws=None, external_id=None, espn_id=None),
            ]
        )
        assert plan.tags == ()
        assert any(
            str(GHOST_ID) in r and str(CANON_ID) in r and "provider id" in r
            for r in plan.refusals
        )

    def test_an_unplayed_pair_whose_bare_row_carries_an_id_is_refused(self):
        """🔴 The tripwire. 0/1259 bare rows carried a provider id when this was
        measured; if one does, the structure the judgement rests on has changed
        and the sweep stops rather than falling back on the sport key alone."""
        plan = build_plan(
            [_ghost_row(espn_id="182738"), _canon_row(hs=None, aws=None)]
        )
        assert plan.tags == ()
        assert any("carries a provider id" in r for r in plan.refusals)


# ════════════════════════════════════════════════════════════════════════════
# Part B — the full path, executed against a real engine
# ════════════════════════════════════════════════════════════════════════════


def _event(row, status):
    return Event(
        id=row.id,
        sport_id=S_ATP if row.sport_key == "tennis_atp" else S_ATP_US_OPEN,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
        commence_time=row.commence_time,
        status=status,
        home_score=row.home_score,
        away_score=row.away_score,
        event_tags=None,
    )


@pytest.fixture
def engine():
    """The two rows exactly as production holds them.

    The ghost is `scheduled` two days after its own kickoff — it never completes,
    which is why it reads "No result reported" forever — and the canonical is
    `completed` with the score.
    """
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_ATP, key="tennis_atp", name="ATP"))
        s.add(Sport(id=S_ATP_US_OPEN, key="tennis_atp_us_open", name="US Open (ATP)"))
        s.add(_event(_ghost_row(), "scheduled"))
        s.add(_event(_canon_row(), "completed"))
        s.commit()
    return eng


def _cards_on_the_tour_page(eng):
    """Every card `/sport/tennis/atp` shows for this match, across all rails.

    Both sport keys, because that is what #3677's widening does — a tour page
    that also shows its tournament children. Without the widening the page shows
    ONLY the ghost, which is #3677's headline: no US Open match on the ATP tour
    page for the whole fortnight.
    """
    ids = []
    with Session(eng) as s:
        for key in ("tennis_atp", "tennis_atp_us_open"):
            for build in (
                upcoming_games_query,
                recent_results_query,
                unreported_games_query,
            ):
                ids += [e.id for e in s.execute(build(key, NOW)).scalars().all()]
    return sorted(ids)


def _apply(eng, plan):
    """Write the plan's tags. The production writer is Postgres jsonb `||`, so
    what this asserts is that the LABEL the plan produced is honoured by the real
    rails; that the real SQL writes that label is
    `tests/integration/test_tennis_twin_sweep_pg.py`."""
    with Session(eng) as s:
        for tag in plan.tags:
            event = s.get(Event, tag.ghost_id)
            event.event_tags = list(event.event_tags or []) + [
                duplicate_tag(tag.canonical_id)
            ]
        s.commit()


class TestTheShip:
    def test_before_the_sweep_one_match_is_two_cards(self, engine):
        """The bug, driven through the real rails. The ghost is on NO RESULT
        REPORTED and the canonical on RECENT RESULTS."""
        assert _cards_on_the_tour_page(engine) == sorted([GHOST_ID, CANON_ID])

    def test_a_settled_us_open_match_appears_once_after_the_sweep(self, engine):
        """THE SHIP. One match, one card, and it is the one with the result.

        This is CERT-2142's `test_us_open_semifinal_appears_once_after_twin_sweep`
        under the name the measurement supports — a PLAYED match, not a
        semi-final. See this module's docstring and
        `TestTheSemiFinalIsRefusedAndThatIsTheRightAnswer`.
        """
        _apply(engine, build_plan([_ghost_row(), _canon_row()]))
        assert _cards_on_the_tour_page(engine) == [CANON_ID]

    def test_the_card_that_survives_is_the_one_carrying_the_score(self, engine):
        _apply(engine, build_plan([_ghost_row(), _canon_row()]))
        with Session(engine) as s:
            survivor = s.get(Event, _cards_on_the_tour_page(engine)[0])
            assert survivor.home_score is not None
            assert survivor.status == "completed"

    def test_tomorrows_quarter_final_also_appears_once(self, engine):
        """#2693's half of the ship, driven through the same real rails.

        The pair is unplayed on both rows — no score anywhere — and the tour page
        still collapses to one card, because the provider id decided it. This is
        the test CERT-2142 originally asked for and that #2878 could not write
        truthfully; it can be written now.
        """
        with Session(engine) as s:
            canonical = s.get(Event, CANON_ID)
            canonical.home_score = canonical.away_score = None
            canonical.status = "scheduled"
            canonical.commence_time = NOW + timedelta(hours=3)
            s.commit()
        plan = build_plan(
            [_ghost_row(), _canon_row(hs=None, aws=None, at=NOW + timedelta(hours=3))]
        )
        _apply(engine, plan)
        assert _cards_on_the_tour_page(engine) == [CANON_ID]

    def test_a_refused_pair_still_shows_both_cards(self, engine):
        """A refusal must leave the page exactly as it was.

        An ambiguous verdict that quietly hid one of them is the failure mode
        this whole design is built to avoid, so the refusal is driven all the way
        through the rails rather than asserted on the plan alone.
        """
        with Session(engine) as s:
            canonical = s.get(Event, CANON_ID)
            canonical.home_score = canonical.away_score = None
            canonical.status = "scheduled"
            canonical.commence_time = NOW + timedelta(hours=3)
            s.commit()
        plan = build_plan(
            [
                _ghost_row(),
                _canon_row(
                    hs=None,
                    aws=None,
                    at=NOW + timedelta(hours=3),
                    external_id=None,
                    espn_id=None,
                ),
            ]
        )
        assert plan.tags == ()
        _apply(engine, plan)
        assert _cards_on_the_tour_page(engine) == sorted([GHOST_ID, CANON_ID])

    def test_an_untagged_bystander_is_never_dropped(self, engine):
        """The trap `not_a_proven_duplicate` exists for: `event_tags` is nullable
        and `NULL NOT LIKE x` is NULL, not TRUE, so a naive predicate empties the
        rail. Both rows here are untagged and both must survive."""
        assert len(_cards_on_the_tour_page(engine)) == 2


class TestEveryLeagueRailConsumesTheProof:
    """A tag the rail ignores is a tag that fixes nothing.

    99 of the 162 measured ghosts are `scheduled` and land on
    `unreported_games_query`, which was the one rail of the three that did not
    carry the predicate — #2263 added it to the other two, and #3211 created this
    rail afterwards, for exactly this population.
    """

    def test_all_three_league_rails_carry_the_predicate(self):
        import inspect

        from app.routes import league_futures

        source = inspect.getsource(league_futures)
        assert source.count("not_a_proven_duplicate()") == 3, (
            "a league rail has lost the #2263 predicate — the tennis ghosts "
            "(#2878) live on the unreported rail and keep their card without it"
        )

    @pytest.mark.parametrize(
        "build", [upcoming_games_query, recent_results_query, unreported_games_query]
    )
    def test_each_rail_compiles_with_the_duplicate_clause(self, build):
        from sqlalchemy.dialects import postgresql

        from app.services.anchor_channel import DUPLICATE_TAG_PREFIX

        compiled = str(
            build("tennis_atp", NOW).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert DUPLICATE_TAG_PREFIX in compiled

    def test_the_real_postgres_write_gate_is_wired_into_ci(self):
        """A guard suite nobody runs is a guard suite that proves nothing.

        Every case in `tests/integration/test_tennis_twin_sweep_pg.py` is
        `skipif`-gated on `SEARCH_TEST_DATABASE_URL`, so the whole file SKIPS in
        the four `backend-tests` shards and pytest exits 0. It grades something
        only inside the `search-recall` job, which names its integration files
        one by one.

        🔴 This assertion lives HERE, in the always-run suite, and not in that
        file — a wiring check inside the skip-gated file is circular: unwire the
        file and the test that would have caught it stops running too. The
        parent suite's
        `test_the_behavioural_search_gate_exists_and_is_wired_into_ci` is on
        record about a gate that existed and never ran.
        """
        import pathlib

        workflow = (
            pathlib.Path(__file__).resolve().parents[2]
            / ".github"
            / "workflows"
            / "ci.yml"
        ).read_text()
        assert "tests/integration/test_tennis_twin_sweep_pg.py" in workflow, (
            "the #2878 real-Postgres write/undo gate is not named in ci.yml — it "
            "would skip in every shard and never run anywhere. The jsonb append "
            "and its `NOT @>` idempotence cannot be graded under sqlite."
        )
