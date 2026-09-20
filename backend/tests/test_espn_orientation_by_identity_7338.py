"""#7338 — a card stops showing the losing team winning.

WHAT A READER SAW
=================
Discover page one, phone width, production v4792 `7b020707`, 2026-09-19 ~19:10
PDT, card text verbatim:

    🏈 NCAAF   ● LIVE   🔥 TRENDING
     [UVA crest] 28      End of 3rd Quarter      21  [WVU crest]
    Virginia Cavaliers @ West Virginia Mountaineers
    42%            Win Probability            58%
    West Virginia Mountaineers chance rose from 22% to 58%

The card credits Virginia with 28 and West Virginia with 21, then gives the team
it has just shown losing by seven a 58% chance and the TRENDING flame. It
contradicts itself on its own face — and the underlying fact is the exact
reverse: **West Virginia was winning 28–21.**

WHAT IT ACTUALLY WAS
====================
ESPN's own record for the `espn_id` we store on that row (401856802) has
Virginia at HOME with 21 and West Virginia AWAY with 28. Our row has them the
other way round. The scores followed ESPN's *slot*:

                      ESPN (authority)                our row (15308929)
    home              Virginia Cavaliers, 21          West Virginia, 21
    away              West Virginia, 28               Virginia Cavaliers, 28
    venue             neutralSite: true               venue NULL
    home win %        0.3828 (Virginia's)             stored as West Virginia's

`match_event_to_espn` arm 2 compares home-to-home AND away-to-away, so a
name-matched row is oriented by construction. **Arm 1 — the `espn_id` anchor —
compares nothing**, and its docstring says so in as many words: "an id-anchored
hit already carries ESPN's own identity". That is true of the FIXTURE and false
of the SIDES. Everything downstream then copies by slot (`home_score=
ee.home_score`) with no check anywhere that ESPN's home team is the team sitting
in our `home_team_name`.

WHY A NEUTRAL SITE IS THE PREDICTOR
===================================
Because there is no true home side for the two providers to agree about, so
whoever minted our row (the Odds API here) is free to nominate the opposite side
to ESPN. Measured over today's NCAAF, 70 rows whose `espn_id` ESPN also serves:
62 aligned, 7 unjudgeable on spelling, **1 swapped — and that one is the only
judgeable neutral-site game in the window.** 0 of 61 non-neutral rows are
swapped. Bowl games, neutral-site openers, NFL international games and cup
finals at a neutral ground are the population.

WHY THE FIX ORIENTS RATHER THAN REFUSES
=======================================
Refusing every row we cannot read would stop live scores for the 7-in-70 cohort
whose names our matcher merely cannot spell — a far larger population than the
one being repaired, and a much worse regression than the defect. So the resolver
moves a row only when it can POSITIVELY show it is reversed, counts the ones it
cannot read, and leaves those writing exactly what they write today. The counter
is what a later refusal gets to be argued from; the silence is what let this one
reach page one.

BOTH DIRECTIONS (gotcha #43)
============================
Every re-orientation below has a twin asserting an ALIGNED payload still lands
untouched. A suite that only proved swaps would pass with ESPN's writer
commented out entirely.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.espn_api import ESPNEvent, ESPNTeam
from app.utils.espn_helpers import (
    ESPN_ORIENTATION_ALIGNED,
    ESPN_ORIENTATION_SWAPPED,
    ESPN_ORIENTATION_UNRESOLVED,
    espn_orientation_verdict,
    orient_espn_event_to_row,
)


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


# ---------------------------------------------------------------------------
# The specimen, built from the real dataclasses
#
# ⚠️ REAL `ESPNEvent`/`ESPNTeam`, NEVER A `SimpleNamespace`. The production
# object is a dataclass and the correction is a `dataclasses.replace`; a
# hand-rolled stand-in would both miss that and quietly satisfy assertions the
# real type could not. The team payloads carry the fields
# `espn_identity_corresponds` actually reads.
# ---------------------------------------------------------------------------

UVA = ESPNTeam(
    espn_id="258", name="Cavaliers", abbreviation="UVA",
    display_name="Virginia Cavaliers", short_name="Virginia",
    nickname="Virginia", primary_color=None, secondary_color=None,
    logo_url=None, logo_url_dark=None, record="2-1", location="Virginia",
)
WVU = ESPNTeam(
    espn_id="277", name="Mountaineers", abbreviation="WVU",
    display_name="West Virginia Mountaineers", short_name="West Virginia",
    nickname="West Virginia", primary_color=None, secondary_color=None,
    logo_url=None, logo_url_dark=None, record="2-1", location="West Virginia",
)


def _espn_board_row(*, home_team, away_team, home_score, away_score,
                    home_win_probability=None, status="in",
                    status_detail="3rd Quarter", clock="0:00"):
    """ESPN's board row exactly as `_parse_event` returns it."""
    return ESPNEvent(
        espn_id="401856802",
        name="Virginia Cavaliers at West Virginia Mountaineers",
        short_name="WVU VS UVA",
        date=None,
        status=status,
        status_detail=status_detail,
        period=3,
        clock=clock,
        home_team=home_team,
        away_team=away_team,
        home_score=home_score,
        away_score=away_score,
        venue=None,
        broadcasts=[],
        home_win_probability=home_win_probability,
    )


class _OurRow:
    """Our row's naming surface, as `get_event_name_variations` reads it."""

    def __init__(self, home_team_name="West Virginia Mountaineers",
                 away_team_name="Virginia Cavaliers"):
        self.id = 15308929
        self.home_team_name = home_team_name
        self.away_team_name = away_team_name
        self.home_team_normalized = None
        self.away_team_normalized = None
        self.home_team_alt_names = None
        self.away_team_alt_names = None


# ---------------------------------------------------------------------------
# 1. The verdict
# ---------------------------------------------------------------------------


def test_the_specimens_orientation_is_read_as_swapped_7338():
    """ESPN's home is Virginia; ours is West Virginia. That is the defect."""
    verdict = espn_orientation_verdict(
        _OurRow(),
        _espn_board_row(home_team=UVA, away_team=WVU,
                        home_score=21, away_score=28),
    )
    assert verdict == ESPN_ORIENTATION_SWAPPED


def test_an_agreeing_board_row_is_read_as_aligned_7338():
    """The 62-in-70 majority must not be disturbed."""
    verdict = espn_orientation_verdict(
        _OurRow(),
        _espn_board_row(home_team=WVU, away_team=UVA,
                        home_score=28, away_score=21),
    )
    assert verdict == ESPN_ORIENTATION_ALIGNED


def test_a_row_we_cannot_spell_is_unresolved_not_swapped_7338():
    """The 7-in-70 cohort. Unreadable is not evidence of a reversal."""
    verdict = espn_orientation_verdict(
        _OurRow(home_team_name="Hokies of VA Tech",
                away_team_name="Tar Heels of NC"),
        _espn_board_row(home_team=UVA, away_team=WVU,
                        home_score=21, away_score=28),
    )
    assert verdict == ESPN_ORIENTATION_UNRESOLVED


def test_a_payload_that_matches_both_ways_is_unresolved_7338():
    """Ambiguity is not a verdict.

    Both of our sides correspond to both of ESPN's, so the payload has told us
    nothing about orientation and must not be allowed to move a score.
    """
    verdict = espn_orientation_verdict(
        _OurRow(home_team_name="Virginia Cavaliers",
                away_team_name="Virginia Cavaliers"),
        _espn_board_row(home_team=UVA, away_team=UVA,
                        home_score=21, away_score=28),
    )
    assert verdict == ESPN_ORIENTATION_UNRESOLVED


def test_a_board_row_with_no_competitors_is_unresolved_7338():
    verdict = espn_orientation_verdict(
        _OurRow(),
        _espn_board_row(home_team=None, away_team=None,
                        home_score=21, away_score=28),
    )
    assert verdict == ESPN_ORIENTATION_UNRESOLVED


def test_the_two_name_readers_agree_on_a_real_event_7338():
    """The mirror cannot drift from the matcher's own reader.

    `espn_row_name_variations` exists to degrade to silence on a row it cannot
    read, which `get_event_name_variations` does not do. That is the ONLY
    difference they are allowed to have: on a real `Event` — populated or
    sparse — they must return the same names in the same order, or the
    orientation verdict is being taken on a different vocabulary from the match
    that produced the row.
    """
    from app.models.models import Event
    from app.tasks.espn_sync import get_event_name_variations
    from app.utils.espn_helpers import espn_row_name_variations

    populated = Event(
        home_team_name="West Virginia Mountaineers",
        away_team_name="Virginia Cavaliers",
        home_team_normalized="west virginia",
        away_team_normalized="virginia",
        home_team_alt_names=["WVU", "Mountaineers"],
        away_team_alt_names=["UVA", "Cavaliers"],
    )
    assert espn_row_name_variations(populated) == get_event_name_variations(populated)

    sparse = Event(
        home_team_name="West Virginia Mountaineers",
        away_team_name="Virginia Cavaliers",
    )
    assert espn_row_name_variations(sparse) == get_event_name_variations(sparse)


def test_a_row_that_cannot_be_read_at_all_does_not_raise_7338():
    """The reason the mirror exists.

    A partial row reaching the live writer must produce "I cannot tell", never
    an `AttributeError` inside a writer whose failure mode should be silence.
    """
    from app.utils.espn_helpers import espn_row_name_variations

    class _PartialRow:
        home_team_name = "West Virginia Mountaineers"
        away_team_name = "Virginia Cavaliers"

    assert espn_row_name_variations(_PartialRow()) == (
        ["West Virginia Mountaineers"], ["Virginia Cavaliers"],
    )

    class _NamelessRow:
        pass

    assert espn_row_name_variations(_NamelessRow()) == ([], [])
    assert espn_orientation_verdict(
        _NamelessRow(),
        _espn_board_row(home_team=UVA, away_team=WVU,
                        home_score=21, away_score=28),
    ) == ESPN_ORIENTATION_UNRESOLVED


# ---------------------------------------------------------------------------
# 2. The correction itself
# ---------------------------------------------------------------------------


def test_the_correction_moves_scores_teams_and_the_probability_together_7338():
    """A half-applied swap is an inverted blend, not a repaired one."""
    stats: dict = {}
    oriented = orient_espn_event_to_row(
        _OurRow(),
        _espn_board_row(home_team=UVA, away_team=WVU,
                        home_score=21, away_score=28,
                        home_win_probability=0.3828),
        stats,
    )

    # Our home side is West Virginia, who are winning 28–21 with ESPN's 61.72%.
    assert oriented.home_score == 28
    assert oriented.away_score == 21
    assert oriented.home_team is WVU
    assert oriented.away_team is UVA
    assert oriented.home_win_probability == pytest.approx(0.6172)
    assert stats["espn_orientation_swapped"] == 1


def test_the_correction_leaves_an_aligned_row_completely_alone_7338():
    stats: dict = {}
    board = _espn_board_row(home_team=WVU, away_team=UVA,
                            home_score=28, away_score=21,
                            home_win_probability=0.6172)
    oriented = orient_espn_event_to_row(_OurRow(), board, stats)

    assert oriented is board
    assert stats == {}


def test_an_unresolved_row_writes_what_it_writes_today_and_is_counted_7338():
    """No refusal — but the silence ends."""
    stats: dict = {}
    board = _espn_board_row(home_team=UVA, away_team=WVU,
                            home_score=21, away_score=28)
    oriented = orient_espn_event_to_row(
        _OurRow(home_team_name="Hokies of VA Tech",
                away_team_name="Tar Heels of NC"),
        board,
        stats,
    )

    assert oriented is board
    assert stats["espn_orientation_unresolved"] == 1


def test_a_swap_with_no_probability_does_not_invent_one_7338():
    oriented = orient_espn_event_to_row(
        _OurRow(),
        _espn_board_row(home_team=UVA, away_team=WVU,
                        home_score=21, away_score=28,
                        home_win_probability=None),
    )
    assert oriented.home_win_probability is None
    assert oriented.home_score == 28


# ---------------------------------------------------------------------------
# 3. Driven through the real writers, read back from the DATABASE
#
# The acceptance criterion is about the ROW, not the helper: "an ESPN payload
# whose homeAway orientation is the reverse of the stored row must not produce a
# row where home_score belongs to the away team". A helper-only assertion would
# pass with the call sites never wired up.
# ---------------------------------------------------------------------------


class _AsyncShim:
    """The writers are async and this engine is not; nothing else is shimmed."""

    def __init__(self, inner):
        self._s = inner

    async def execute(self, statement):
        return self._s.execute(statement)

    def add(self, obj):
        self._s.add(obj)

    async def flush(self):
        self._s.flush()

    async def commit(self):
        self._s.commit()


def _live_row_on_disk():
    """A real `Event` for the specimen, committed to a real database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, ESPNSnapshot, Event, ScoreSnapshot, Sport, WinProbSnapshot,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__, Sport.__table__, ScoreSnapshot.__table__,
            ESPNSnapshot.__table__, WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="americanfootball_ncaaf", name="NCAAF")
    session.add(sport)
    session.flush()

    event = Event(
        sport_id=sport.id,
        # Our row's orientation — the reverse of ESPN's.
        home_team_name="West Virginia Mountaineers",
        away_team_name="Virginia Cavaliers",
        commence_time=datetime.now(timezone.utc) - timedelta(hours=3),
        status="live",
        period=3,
        game_clock="0:00",
        home_score=None,
        away_score=None,
        espn_id="401856802",
        commence_time_source="espn",
        win_probability_sources={},
    )
    session.add(event)
    session.commit()
    return session, event


@pytest.mark.asyncio
async def test_a_reversed_board_row_does_not_land_on_the_wrong_team_7338():
    """THE GUARD. West Virginia is winning 28–21, so our home score is 28."""
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.espn_helpers import update_event_fields_from_espn

    session, event = _live_row_on_disk()
    stats: dict = {}

    await update_event_fields_from_espn(
        _AsyncShim(session),
        event,
        _espn_board_row(home_team=UVA, away_team=WVU,
                        home_score=21, away_score=28),
        set(),
        stats,
    )
    session.commit()
    session.expire_all()

    row = session.execute(select(Event)).scalar_one()
    assert row.home_team_name == "West Virginia Mountaineers"
    assert row.home_score == 28, (
        "our home side is West Virginia, who are winning 28–21; a 21 here is "
        "ESPN's home slot written onto the wrong team (#7338)"
    )
    assert row.away_score == 21
    assert stats.get("espn_orientation_swapped") == 1


@pytest.mark.asyncio
async def test_an_agreeing_board_row_still_writes_its_scores_7338():
    """The twin. A guard that froze live scores would be worse than the bug."""
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.espn_helpers import update_event_fields_from_espn

    session, event = _live_row_on_disk()
    stats: dict = {}

    await update_event_fields_from_espn(
        _AsyncShim(session),
        event,
        _espn_board_row(home_team=WVU, away_team=UVA,
                        home_score=28, away_score=21),
        set(),
        stats,
    )
    session.commit()
    session.expire_all()

    row = session.execute(select(Event)).scalar_one()
    assert row.home_score == 28
    assert row.away_score == 21
    assert "espn_orientation_swapped" not in stats


@pytest.mark.asyncio
async def test_the_espn_probability_leg_lands_on_our_home_team_7338():
    """ESPN said Virginia 38.28%; our home side is West Virginia, so 61.72%."""
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.espn_helpers import write_espn_win_probability

    session, event = _live_row_on_disk()
    stats: dict = {}

    await write_espn_win_probability(
        _AsyncShim(session),
        event,
        _espn_board_row(home_team=UVA, away_team=WVU,
                        home_score=21, away_score=28,
                        home_win_probability=0.3828),
        "espn_id",
        set(),
        stats,
    )
    session.commit()
    session.expire_all()

    row = session.execute(select(Event)).scalar_one()
    # `espn_win_prob_home` is Numeric, so it reads back as Decimal (#7338 rail).
    assert float(row.espn_win_prob_home) == pytest.approx(0.6172), (
        "storing 0.3828 points the blend's ESPN leg at Virginia while every "
        "venue leg points at West Virginia (#7338)"
    )
    assert float(
        row.win_probability_sources["espn"]["value"]
    ) == pytest.approx(0.6172)


@pytest.mark.asyncio
async def test_the_stat_model_is_not_computed_from_the_wrong_sides_score_7338():
    """The third call site.

    The model is fed `home_score`/`away_score` and returns a HOME win
    probability, so a swapped feed inverts it one step downstream — the
    specimen read `stat_model` 0.0762 for a team up seven in the fourth. Our
    home side is up 28–21, so its modelled chance must be above even.
    """
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.espn_helpers import compute_and_write_stat_model

    session, event = _live_row_on_disk()
    stats: dict = {}

    wrote = await compute_and_write_stat_model(
        _AsyncShim(session),
        event,
        _espn_board_row(home_team=UVA, away_team=WVU,
                        home_score=21, away_score=28,
                        status="in", status_detail="4th Quarter", clock="2:00"),
        "americanfootball_ncaaf",
        stats,
    )
    session.commit()
    session.expire_all()

    assert wrote, "the rail must actually reach the model, or it proves nothing"
    row = session.execute(select(Event)).scalar_one()
    modelled = float(row.win_probability_sources["stat_model"]["value"])
    assert modelled > 0.5, (
        f"West Virginia is our home side and is up 28–21; a modelled "
        f"{modelled} is ESPN's slot fed to the model backwards (#7338)"
    )


@pytest.mark.asyncio
async def test_the_stat_model_still_reads_an_agreeing_row_the_same_way_7338():
    """The twin — the correction must not reach an aligned row."""
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.espn_helpers import compute_and_write_stat_model

    session, event = _live_row_on_disk()
    stats: dict = {}

    await compute_and_write_stat_model(
        _AsyncShim(session),
        event,
        _espn_board_row(home_team=WVU, away_team=UVA,
                        home_score=28, away_score=21,
                        status="in", status_detail="4th Quarter", clock="2:00"),
        "americanfootball_ncaaf",
        stats,
    )
    session.commit()
    session.expire_all()

    row = session.execute(select(Event)).scalar_one()
    assert float(row.win_probability_sources["stat_model"]["value"]) > 0.5


@pytest.mark.asyncio
async def test_an_agreeing_board_row_stores_its_probability_unchanged_7338():
    """The twin, so the complement cannot be applied to everybody."""
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.espn_helpers import write_espn_win_probability

    session, event = _live_row_on_disk()
    stats: dict = {}

    await write_espn_win_probability(
        _AsyncShim(session),
        event,
        _espn_board_row(home_team=WVU, away_team=UVA,
                        home_score=28, away_score=21,
                        home_win_probability=0.6172),
        "espn_id",
        set(),
        stats,
    )
    session.commit()
    session.expire_all()

    row = session.execute(select(Event)).scalar_one()
    assert float(row.espn_win_prob_home) == pytest.approx(0.6172)
