"""#8613 — the MLB stat model read the ±1.5 run line as an expected run margin.

`/events/15318166` (Mets at Rangers, 2026-09-25) opened at 0.5457 — the page
printed "55% pregame" — but the served `stat_model` line read 0.7325 at 0–0 in
the Top 1st and 80%+ through the 5th while Kalshi, Polymarket, ESPN and the MLB
model read 55–70%. For baseball the stored `opening_home_spread` is the run
line: a handicap that sits at ±1.5 whatever the matchup (88 of 140 MLB games
in a week). The model took it as "home wins by 1.5 runs on average", made every
favourite a 1.5-run favourite, and never used the opening price at all.

The fix: baseball's stored spread is never the model's prior
(`model_pregame_spread`); the opening price is, and the prior is solved so the
model opens AT that price. Every other sport's spread is a real point spread
and still wins over the price. Both stat-model writers normalise the spread
before the #8522 priorless check, so a run line alone is "no prior" there too.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event

from app.services.espn_api import ESPNEvent, ESPNTeam
from app.utils.win_probability import (
    compute_baseball_win_prob,
    compute_statistical_win_prob,
    model_pregame_spread,
    priorless_model_defers_to_market,
)
from tests.test_priorless_stat_model_defers_to_market_8522 import (
    _portable_probability_writer,  # noqa: F401 - shared autouse SQLite writer seam
)

from tests.test_priorless_stat_model_defers_to_market_8522 import (  # noqa: F401 — registers the sqlite JSONB/ARRAY compilers
    KALSHI_JUST_BEFORE,
    STAMP,
    _AsyncShim,
)

SPECIMEN_OPENING = 0.5457  # /events/15318166 opening_home_probability
SPECIMEN_RUN_LINE = -1.5  # its opening_home_spread
SPECIMEN_SERVED_BEFORE = 0.7325  # stat_model at 18:37:04Z, Top 1st, 0–0


def _first_pitch(sport_key="baseball_mlb", **prior):
    return compute_statistical_win_prob(
        home_score=0,
        away_score=0,
        clock=None,
        period="Top 1st",
        sport_key=sport_key,
        **prior,
    )


# ---------------------------------------------------------------------------
# 1. The rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("run_line", [-1.5, 1.5, -2.5, 2.5, "-1.5"])
@pytest.mark.parametrize(
    "sport_key", ["baseball_mlb", "baseball_mlb_preseason", "baseball_ncaa"]
)
def test_a_baseball_run_line_is_never_the_models_prior_8613(sport_key, run_line):
    assert model_pregame_spread(sport_key, run_line) is None


@pytest.mark.parametrize(
    "sport_key,spread",
    [
        ("americanfootball_nfl", -7.0),
        ("basketball_nba", 4.5),
        ("icehockey_nhl", -1.5),  # the puck line looks like a run line; not ours to drop
    ],
)
def test_every_other_sports_spread_passes_through_8613(sport_key, spread):
    assert model_pregame_spread(sport_key, spread) == spread


def test_no_spread_is_no_spread_8613():
    assert model_pregame_spread("americanfootball_nfl", None) is None
    assert model_pregame_spread("baseball_mlb", None) is None


# ---------------------------------------------------------------------------
# 2. The model
# ---------------------------------------------------------------------------


# "Top 1st" is parsed as 1.5 outs into the half with the away side scoreless,
# which is worth ~3 points to the home side on its own. That is the model's
# reading of the label, not the prior; the prior is pinned at a true first
# pitch below.
TOP_FIRST_ALLOWANCE = 0.04


@pytest.fixture
def true_first_pitch(monkeypatch):
    """No outs, nine half-innings each — the state the prior must reproduce."""
    from app.utils import win_probability

    monkeypatch.setattr(
        win_probability,
        "parse_baseball_state",
        lambda _p: {
            "inning": 1,
            "is_top": True,
            "outs_in_half": 0.0,
            "home_half_innings_remaining": 9.0,
            "away_half_innings_remaining": 9.0,
            "outs_remaining": 54.0,
        },
    )


def test_the_specimen_opens_at_its_opening_price_8613():
    """THE GUARD. Before the fix: 0.7325 at Top 1st, 19 points above the price."""
    first_pitch = _first_pitch(
        pregame_spread=SPECIMEN_RUN_LINE,
        opening_home_probability=SPECIMEN_OPENING,
    )
    assert SPECIMEN_OPENING <= first_pitch < SPECIMEN_OPENING + TOP_FIRST_ALLOWANCE
    assert abs(first_pitch - SPECIMEN_SERVED_BEFORE) > 0.15


@pytest.mark.parametrize("run_line", [-1.5, 1.5, None])
def test_the_run_lines_sign_and_presence_change_nothing_8613(run_line):
    with_prob = _first_pitch(
        pregame_spread=run_line, opening_home_probability=SPECIMEN_OPENING
    )
    assert with_prob == pytest.approx(
        _first_pitch(opening_home_probability=SPECIMEN_OPENING)
    )


@pytest.mark.parametrize("opening", [0.30, 0.45, SPECIMEN_OPENING, 0.70, 0.85])
def test_a_true_first_pitch_reads_the_opening_price_8613(true_first_pitch, opening):
    """The opening price already carries home field; the margin adds it too.

    Before the fix a 0.5457 prior read ~0.563 here: the prior was solved
    without home field, then home field was added on top of it.
    """
    assert _first_pitch(opening_home_probability=opening) == pytest.approx(
        opening, abs=0.005
    )
    assert compute_baseball_win_prob(
        0, 0, "Top 1st", opening_home_probability=opening
    ) == pytest.approx(opening, abs=0.005)


@pytest.mark.parametrize("opening", [0.30, 0.45, SPECIMEN_OPENING, 0.70, 0.85])
def test_top_of_the_first_stays_within_the_labels_allowance_8613(opening):
    top_first = _first_pitch(
        pregame_spread=SPECIMEN_RUN_LINE, opening_home_probability=opening
    )
    assert opening <= top_first < opening + TOP_FIRST_ALLOWANCE


def test_the_prior_still_fades_as_the_game_is_played_8613():
    """A 55% favourite down four in the 8th is not rescued by its price."""
    late = compute_statistical_win_prob(
        home_score=1,
        away_score=5,
        clock=None,
        period="Top 8th",
        sport_key="baseball_mlb",
        pregame_spread=SPECIMEN_RUN_LINE,
        opening_home_probability=SPECIMEN_OPENING,
    )
    assert late < 0.05


def test_the_wall_clock_fallback_drops_the_run_line_too_8613():
    """No inning string: the generic model runs, and must not read ±1.5 either."""
    start = datetime.now(timezone.utc) - timedelta(minutes=1)
    kwargs = dict(
        home_score=0,
        away_score=0,
        clock=None,
        period=None,
        sport_key="baseball_mlb",
        commence_time=start,
        opening_home_probability=SPECIMEN_OPENING,
    )
    assert compute_statistical_win_prob(
        pregame_spread=SPECIMEN_RUN_LINE, **kwargs
    ) == pytest.approx(compute_statistical_win_prob(**kwargs))


def test_control_a_football_spread_still_outranks_the_price_8613():
    """The #8613 rule is baseball's; an NFL -7 still wins over a 30% price."""
    both = compute_statistical_win_prob(
        0, 0, "15:00", "Q1", "americanfootball_nfl",
        pregame_spread=-7, opening_home_probability=0.30,
    )
    spread_only = compute_statistical_win_prob(
        0, 0, "15:00", "Q1", "americanfootball_nfl", pregame_spread=-7
    )
    assert both == pytest.approx(spread_only)
    assert both > 0.6


# ---------------------------------------------------------------------------
# 3. The ESPN writer, end to end on a real row
# ---------------------------------------------------------------------------


def _team(espn_id, display_name, abbreviation, location):
    return ESPNTeam(
        espn_id=espn_id,
        name=display_name.split()[-1],
        abbreviation=abbreviation,
        display_name=display_name,
        short_name=display_name.split()[-1],
        nickname=location,
        primary_color=None,
        secondary_color=None,
        logo_url=None,
        logo_url_dark=None,
        record=None,
        location=location,
    )


RANGERS = _team("13", "Texas Rangers", "TEX", "Texas")
METS = _team("21", "New York Mets", "NYM", "New York")


def _first_pitch_board_row():
    """ESPN's MLB board row at 0–0 in the Top 1st, as `_parse_event` returns it."""
    return ESPNEvent(
        espn_id="401815318",
        name="New York Mets at Texas Rangers",
        short_name="NYM @ TEX",
        date=None,
        status="in",
        status_detail="Top 1st",
        period=1,
        clock=None,
        home_team=RANGERS,
        away_team=METS,
        home_score=0,
        away_score=0,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


def _mlb_row_on_disk(*, sources, opening_home_probability, opening_home_spread):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.models import Base, Event, Sport, WinProbSnapshot

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Event.__table__, Sport.__table__, WinProbSnapshot.__table__],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="baseball_mlb", name="MLB")
    session.add(sport)
    session.flush()
    event = Event(
        sport_id=sport.id,
        home_team_name="Texas Rangers",
        away_team_name="New York Mets",
        commence_time=datetime.now(timezone.utc) - timedelta(minutes=3),
        status="live",
        espn_id="401815318",
        commence_time_source="espn",
        opening_home_probability=opening_home_probability,
        opening_home_spread=opening_home_spread,
        win_probability_sources=sources,
    )
    session.add(event)
    session.commit()
    return session, event


async def _run_espn_writer(session, event):
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.espn_helpers import compute_and_write_stat_model

    stats: dict = {}
    wrote = await compute_and_write_stat_model(
        _AsyncShim(session), event, _first_pitch_board_row(), "baseball_mlb", stats
    )
    session.commit()
    session.expire_all()
    return wrote, stats, session.execute(select(Event)).scalar_one()


@pytest.mark.asyncio
async def test_the_espn_writer_stores_the_opening_price_at_first_pitch_8613():
    """The specimen's row as stored: run line -1.5, opening 0.5457."""
    session, event = _mlb_row_on_disk(
        sources={},
        opening_home_probability=SPECIMEN_OPENING,
        opening_home_spread=SPECIMEN_RUN_LINE,
    )
    wrote, _, row = await _run_espn_writer(session, event)

    assert wrote is True
    stored = row.win_probability_sources["stat_model"]["value"]
    assert SPECIMEN_OPENING <= stored < SPECIMEN_OPENING + TOP_FIRST_ALLOWANCE, (
        "the model reads the run line as a 1.5-run margin and opens at 0.73 (#8613)"
    )


@pytest.mark.asyncio
async def test_a_run_line_alone_is_no_prior_so_the_model_defers_to_kalshi_8613():
    """#8522's rule, reached through a baseball row whose only 'prior' is ±1.5.

    Before the fix the run line counted as a prior, so the model did not defer
    and wrote its 0.73 beside Kalshi at weight 1.0.
    """
    assert priorless_model_defers_to_market(
        model_pregame_spread("baseball_mlb", SPECIMEN_RUN_LINE),
        None,
        {"kalshi": KALSHI_JUST_BEFORE},
    )
    session, event = _mlb_row_on_disk(
        sources={"kalshi": {"value": KALSHI_JUST_BEFORE, "updated_at": STAMP}},
        opening_home_probability=None,
        opening_home_spread=SPECIMEN_RUN_LINE,
    )
    wrote, stats, row = await _run_espn_writer(session, event)

    assert wrote is False
    assert stats.get("stat_model_priorless_deferred") == 1
    assert "stat_model" not in row.win_probability_sources


# ---------------------------------------------------------------------------
# 4. The odds-poll writer (events without an ESPN link)
# ---------------------------------------------------------------------------


def test_the_odds_poll_writer_normalises_the_spread_and_hands_over_the_price_8613():
    """Its loop is a live HTTP poll; the 8522 behaviour rig drives it for NHL.

    Here the source is read: the spread must come through
    `model_pregame_spread` before the #8522 ask, and the model call must be
    handed the opening price — baseball's only prior once the run line is gone.
    """
    from app.tasks import odds_polling

    src = inspect.getsource(odds_polling)
    ask = src.index("if priorless_model_defers_to_market(")
    model = src.index("stat_wp = compute_statistical_win_prob(")
    spread = src.rindex("pregame_spread = model_pregame_spread(", 0, ask)
    assert spread < ask < model
    assert "float(event_obj.opening_home_spread)" not in src[spread - 400 : ask]
    call = src[model : src.index(")\n", src.index("commence_time=", model))]
    assert "opening_home_probability=" in call
