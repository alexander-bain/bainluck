"""UX-P127 — the two F4 residuals, and their one shared root cause.

F4 (UX-P126) stopped `_normalize_tournament` from folding six unrelated events onto
`masters`. It did not finish the job, and the report named two remnants. Both were
re-measured red-side against production on 2026-08-24 (22 open markets, the exact
names used below):

  RESIDUAL 1 — the British Masters is ONE event served under TWO keys.
    `british_masters`                                    7 polymarket markets
    `husqvarna_british_masters_hosted_by_sir_nick_faldo` 5 datagolf + 1 kalshi
  Two cards for one tournament, each with half the field.

  RESIDUAL 2 — key `liv` is THREE different things in one bucket, 9 markets:
    a corporate-shutdown question, a Q1-2027 eligibility question,
    LIV Golf New York (2), and LIV Golf Indianapolis (5).

THE SHARED ROOT: `_get_golf_schedule` calls `get_schedule(tour="pga")` and nothing
else. Priority-2 is the only rung of `_normalize_tournament` that folds two naming
shapes of one event together, and it can only do that for events the schedule knows
about. Every DP World Tour and LIV event is therefore invisible to it — the two
British Masters spellings fall through to different rungs (P3 chrome-strip vs P4
generic slug) and land on different keys, and the LIV events never get the chance
because Priority-1's bare `liv\\s+golf` pattern claims them for the tour first.

So the fix is two-sided and both sides are required:
  A. Priority-1's `liv` arm gains an EVENT discriminator, so "LIV Golf <city>" falls
     through to earn its own key while tour-level questions keep the tour key.
  B. The schedule loads `euro` and `liv` alongside `pga`, so there is an authority
     for A to fall through to — and so the British Masters inherits real dates
     instead of being dropped by `_filter_stale_tournaments`.

Every test asserts BOTH directions (gotcha #43): the event splits/folds correctly
AND the neighbours F4 taught us to refuse are still refused.
"""

import re

import pytest

from app.routes.golf import (
    _SPONSOR_SUFFIX_RE,
    _normalize_tournament,
)


def _entry(name: str, *, start: str, end: str, tour: str) -> dict:
    """Build a schedule entry exactly the way `_get_golf_schedule` does."""
    clean = _SPONSOR_SUFFIX_RE.sub("", name)
    key = re.sub(r"[^a-z0-9]+", "_", clean.lower()).strip("_")
    return {
        "name": name,
        "key": key,
        "start_date": f"{start}T00:00:00+00:00",
        "end_date": f"{end}T00:00:00+00:00",
        "venue": "",
        "location": "",
        "status": "",
        "round": "",
        "tour": tour,
    }


# The schedule as it must look once Fix B lands: three tours, not one.
MULTITOUR_SCHEDULE = [
    _entry("TOUR Championship", start="2026-08-27", end="2026-08-30", tour="pga"),
    _entry("Masters Tournament", start="2026-04-09", end="2026-04-12", tour="pga"),
    _entry(
        "Husqvarna British Masters hosted by Sir Nick Faldo",
        start="2026-08-27",
        end="2026-08-30",
        tour="euro",
    ),
    _entry("LIV Golf Indianapolis", start="2026-08-28", end="2026-08-30", tour="liv"),
    _entry("LIV Golf New York", start="2026-09-04", end="2026-09-06", tour="liv"),
]

# Today's schedule: PGA only. Used to prove the current behaviour is the red side
# and that the fixes degrade conservatively when DataGolf is unavailable.
PGA_ONLY_SCHEDULE = [e for e in MULTITOUR_SCHEDULE if e["tour"] == "pga"]

BRITISH_MASTERS_KEY = _entry(
    "Husqvarna British Masters hosted by Sir Nick Faldo",
    start="2026-08-27",
    end="2026-08-30",
    tour="euro",
)["key"]
LIV_INDIANAPOLIS_KEY = _entry(
    "LIV Golf Indianapolis", start="2026-08-28", end="2026-08-30", tour="liv"
)["key"]
LIV_NEW_YORK_KEY = _entry(
    "LIV Golf New York", start="2026-09-04", end="2026-09-06", tour="liv"
)["key"]


# ---------------------------------------------------------------------------
# RESIDUAL 1 — one event, one key
# ---------------------------------------------------------------------------

# Live production names, 2026-08-24. Polymarket spells it "DP World Tour: British
# Masters"; DataGolf and Kalshi spell it with the sponsor and the host.
BRITISH_MASTERS_MARKETS = [
    ("DP World Tour: British Masters Winner", "polymarket", "904532"),
    ("DP World Tour: British Masters First Round Leader", "polymarket", "904536"),
    ("DP World Tour: British Masters Second Round Leader", "polymarket", "904537"),
    ("DP World Tour: British Masters Third Round Leader", "polymarket", "904546"),
    ("DP World Tour: British Masters Top 5", "polymarket", "904533"),
    ("DP World Tour: British Masters Top 10", "polymarket", "904534"),
    ("DP World Tour: British Masters Top 20", "polymarket", "904535"),
    (
        "Husqvarna British Masters hosted by Sir Nick Faldo - Winner",
        "datagolf",
        "datagolf:euro:2026133:win",
    ),
    (
        "Husqvarna British Masters hosted by Sir Nick Faldo - Make the Cut",
        "datagolf",
        "datagolf:euro:2026133:make_cut",
    ),
    (
        "Husqvarna British Masters hosted by Sir Nick Faldo - Top 5 Finish",
        "datagolf",
        "datagolf:euro:2026133:top_5",
    ),
    (
        "Husqvarna British Masters hosted by Sir Nick Faldo - Top 10 Finish",
        "datagolf",
        "datagolf:euro:2026133:top_10",
    ),
    (
        "Husqvarna British Masters hosted by Sir Nick Faldo - Top 20 Finish",
        "datagolf",
        "datagolf:euro:2026133:top_20",
    ),
    (
        "Husqvarna British Masters hosted by Sir Nick Faldo Winner",
        "kalshi",
        "KXDPWORLDTOUR-HUBMHBSNF26",
    ),
]


@pytest.mark.parametrize("name,source,external_id", BRITISH_MASTERS_MARKETS)
def test_british_masters_all_thirteen_land_on_one_key(name, source, external_id):
    """All 13 markets for one tournament must share a key, whoever named them."""
    assert (
        _normalize_tournament(name, MULTITOUR_SCHEDULE, external_id)
        == BRITISH_MASTERS_KEY
    ), f"{source} spelling stranded on its own card"


def test_british_masters_split_is_what_the_pga_only_schedule_produces():
    """Red-side proof: without the euro schedule the two spellings diverge.

    This is not a wish — it is the production defect, pinned. If a later change makes
    the PGA-only schedule fold them anyway, this test fails and tells you the fix
    landed somewhere other than where this cycle put it.
    """
    poly = _normalize_tournament(
        "DP World Tour: British Masters Winner", PGA_ONLY_SCHEDULE, "904532"
    )
    datagolf = _normalize_tournament(
        "Husqvarna British Masters hosted by Sir Nick Faldo - Winner",
        PGA_ONLY_SCHEDULE,
        "datagolf:euro:2026133:win",
    )
    assert poly != datagolf


# The neighbours F4 taught us to refuse. Adding the euro schedule must not give any
# of them a new way onto the British Masters card.
NOT_THE_BRITISH_MASTERS = [
    "New Zealand Darts Masters",
    "Asia Masters 2026 Winner",
    "Most kills on a single map at Masters London 2026?",
    "Masters Tournament Winner",
    "The Masters Winner",
]


@pytest.mark.parametrize("name", NOT_THE_BRITISH_MASTERS)
def test_masters_neighbours_still_refuse_the_british_masters_card(name):
    assert _normalize_tournament(name, MULTITOUR_SCHEDULE, None) != BRITISH_MASTERS_KEY


def test_augusta_still_folds_onto_the_masters():
    """The both-directions half: refusing neighbours must not refuse the real major."""
    assert _normalize_tournament("The Masters Winner", MULTITOUR_SCHEDULE, None) == "masters"


# ---------------------------------------------------------------------------
# RESIDUAL 2 — `liv` is a tour, not an event
# ---------------------------------------------------------------------------

LIV_EVENT_MARKETS = [
    ("LIV Golf Indianapolis End of Round 1 Leader", "KXLIVR1LEAD-IND26", LIV_INDIANAPOLIS_KEY),
    ("LIV Golf Indianapolis End of Round 2 Leader", "KXLIVR2LEAD-IND26", LIV_INDIANAPOLIS_KEY),
    ("LIV Golf Indianapolis End of Round 3 Leader", "KXLIVR3LEAD-IND26", LIV_INDIANAPOLIS_KEY),
    ("Liv Golf Indianapolis: Top 10 Finishers", "KXLIVTOP10-IND26", LIV_INDIANAPOLIS_KEY),
    ("Liv Golf Indianapolis: Top 5 Finishers", "KXLIVTOP5-IND26", LIV_INDIANAPOLIS_KEY),
    ("Liv Golf New York: Top 10 Finishers", "KXLIVTOP10-YOR26", LIV_NEW_YORK_KEY),
    ("Liv Golf New York: Top 5 Finishers", "KXLIVTOP5-YOR26", LIV_NEW_YORK_KEY),
]


@pytest.mark.parametrize("name,external_id,expected", LIV_EVENT_MARKETS)
def test_liv_event_markets_earn_their_own_key(name, external_id, expected):
    """A named LIV event is an event. Two of them are two cards, not one bucket."""
    assert _normalize_tournament(name, MULTITOUR_SCHEDULE, external_id) == expected


def test_liv_new_york_and_indianapolis_do_not_share_a_card():
    ind = _normalize_tournament(
        "LIV Golf Indianapolis End of Round 1 Leader", MULTITOUR_SCHEDULE, "KXLIVR1LEAD-IND26"
    )
    nyc = _normalize_tournament(
        "Liv Golf New York: Top 5 Finishers", MULTITOUR_SCHEDULE, "KXLIVTOP5-YOR26"
    )
    assert ind != nyc
    assert "liv" not in {ind, nyc}


# The other direction: a question ABOUT the tour is not a question about an event.
LIV_TOUR_MARKETS = [
    ("Will LIV Golf announce shutdown in 2026? ", "382484"),
    ("Golfers to Compete in a LIV Golf Tournament in Q1 2027", "KXLIVCOMPETE-27APR"),
]


@pytest.mark.parametrize("name,external_id", LIV_TOUR_MARKETS)
def test_liv_tour_level_questions_keep_the_tour_key(name, external_id):
    assert _normalize_tournament(name, MULTITOUR_SCHEDULE, external_id) == "liv"


def test_a_new_in_the_name_does_not_forge_a_new_york_claim():
    """'New' alone must not buy a LIV Golf New York card.

    A single shared token is how F4's original defect worked — `masters` claimed six
    events on one word. A two-token event name must be matched on both tokens.
    """
    assert (
        _normalize_tournament(
            "Will LIV Golf announce a new team franchise in 2026?",
            MULTITOUR_SCHEDULE,
            "382999",
        )
        == "liv"
    )


def test_liv_events_keep_the_tour_key_when_the_schedule_is_unavailable():
    """Conservative degrade: no authority, no split.

    `_get_golf_schedule` returns [] when DataGolf is down. The discriminator is
    schedule-anchored on purpose — with nothing to anchor to it must reproduce
    today's behaviour rather than invent keys from a regex.
    """
    for name, external_id, _ in LIV_EVENT_MARKETS:
        assert _normalize_tournament(name, [], external_id) == "liv"
        assert _normalize_tournament(name, PGA_ONLY_SCHEDULE, external_id) == "liv"


# ---------------------------------------------------------------------------
# THE SHARED ROOT — the schedule loader must cover more than one tour
# ---------------------------------------------------------------------------


class _FakeService:
    """Stands in for DataGolfAPIService, one canned schedule per tour."""

    def __init__(self, by_tour: dict, fail: frozenset = frozenset()):
        self.by_tour = by_tour
        self.fail = fail
        self.calls: list[str] = []
        self.closed = False

    async def get_schedule(self, tour: str = "pga", season=None):
        self.calls.append(tour)
        if tour in self.fail:
            raise RuntimeError(f"{tour} upstream 503")
        return self.by_tour.get(tour, [])

    async def close(self):
        self.closed = True


def _dg(name: str, tour: str, event_id: str = "1"):
    from app.services.datagolf_api import DataGolfTournament

    return DataGolfTournament(
        event_id=event_id,
        event_name=name,
        tour=tour,
        start_date="2026-08-27",
        end_date="2026-08-30",
        status="upcoming",
    )


CANNED = {
    "pga": [_dg("TOUR Championship", "pga", "1")],
    "euro": [_dg("Husqvarna British Masters hosted by Sir Nick Faldo", "euro", "2026133")],
    "liv": [_dg("LIV Golf Indianapolis", "liv", "3"), _dg("LIV Golf New York", "liv", "4")],
}


@pytest.fixture
def fresh_schedule_cache(monkeypatch):
    """The loader caches in-process for an hour; each test needs a cold one."""
    from app.routes import golf as golf_mod

    monkeypatch.setitem(golf_mod._golf_schedule_cache, "data", None)
    monkeypatch.setitem(golf_mod._golf_schedule_cache, "ts", 0)
    return golf_mod


async def _load(golf_mod, monkeypatch, service):
    import app.services.datagolf_api as dg_mod

    monkeypatch.setattr(dg_mod, "DataGolfAPIService", lambda *a, **k: service)
    return await golf_mod._get_golf_schedule()


@pytest.mark.asyncio
async def test_schedule_loads_dp_world_and_liv_not_just_pga(
    fresh_schedule_cache, monkeypatch
):
    """The residuals' shared root: `get_schedule(tour="pga")` and nothing else."""
    service = _FakeService(CANNED)
    result = await _load(fresh_schedule_cache, monkeypatch, service)

    assert service.calls == ["pga", "euro", "liv"]
    tours = {e["tour"] for e in result}
    assert tours == {"pga", "euro", "liv"}
    assert BRITISH_MASTERS_KEY in {e["key"] for e in result}
    assert {LIV_INDIANAPOLIS_KEY, LIV_NEW_YORK_KEY} <= {e["key"] for e in result}
    assert service.closed


@pytest.mark.asyncio
async def test_one_tour_failing_does_not_empty_the_schedule(
    fresh_schedule_cache, monkeypatch
):
    """Fault isolation. The old loader returned [] for the whole route on any error,
    so a DP World blip would have cost every PGA tournament its dates."""
    service = _FakeService(CANNED, fail=frozenset({"euro"}))
    result = await _load(fresh_schedule_cache, monkeypatch, service)

    keys = {e["key"] for e in result}
    assert BRITISH_MASTERS_KEY not in keys
    assert "tour_championship" in keys
    assert {LIV_INDIANAPOLIS_KEY, LIV_NEW_YORK_KEY} <= keys


@pytest.mark.asyncio
async def test_every_tour_failing_returns_empty_not_a_crash(
    fresh_schedule_cache, monkeypatch
):
    service = _FakeService(CANNED, fail=frozenset({"pga", "euro", "liv"}))
    assert await _load(fresh_schedule_cache, monkeypatch, service) == []


@pytest.mark.asyncio
async def test_a_key_present_on_two_tours_is_not_served_twice(
    fresh_schedule_cache, monkeypatch
):
    """Co-sanctioned events appear on both schedules; one key must mean one entry,
    and PGA wins because it is loaded first."""
    canned = dict(CANNED)
    canned["euro"] = canned["euro"] + [_dg("TOUR Championship", "euro", "9")]
    service = _FakeService(canned)
    result = await _load(fresh_schedule_cache, monkeypatch, service)

    matches = [e for e in result if e["key"] == "tour_championship"]
    assert len(matches) == 1
    assert matches[0]["tour"] == "pga"


# ---------------------------------------------------------------------------
# THE USER-VISIBLE PAYOFF — one dated card, not two undated ones
# ---------------------------------------------------------------------------


def test_merged_british_masters_inherits_real_dates_and_survives_the_stale_filter():
    """F4 stopped the British Masters inheriting Augusta's April dates. This is the
    other half: it now inherits its OWN dates, from the DP World schedule.

    `now` is passed in, so this test never reads the wall clock (gotcha #44).
    """
    from datetime import datetime, timezone

    from app.routes.golf import _enrich_with_schedule, _filter_stale_tournaments

    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    schedule_by_key = {e["key"]: e for e in MULTITOUR_SCHEDULE}

    card = {"key": BRITISH_MASTERS_KEY, "name": "British Masters", "golfers": []}
    _enrich_with_schedule([card], schedule_by_key)

    assert card["start_date"].startswith("2026-08-27")
    assert card["end_date"].startswith("2026-08-30")
    # #1077: resolution_date keys off the real end date, not a Kalshi close artifact.
    assert card["resolution_date"] == card["end_date"]
    assert _filter_stale_tournaments([card], now) == [card]


def test_liv_indianapolis_card_is_dated_from_the_liv_schedule():
    from datetime import datetime, timezone

    from app.routes.golf import _enrich_with_schedule, _filter_stale_tournaments

    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    schedule_by_key = {e["key"]: e for e in MULTITOUR_SCHEDULE}

    card = {"key": LIV_INDIANAPOLIS_KEY, "name": "LIV Golf Indianapolis", "golfers": []}
    _enrich_with_schedule([card], schedule_by_key)

    assert card["start_date"].startswith("2026-08-28")
    assert _filter_stale_tournaments([card], now) == [card]


def test_a_genuinely_finished_event_is_still_dropped():
    """Both directions: giving euro/liv events dates must not make them immortal."""
    from datetime import datetime, timezone

    from app.routes.golf import _enrich_with_schedule, _filter_stale_tournaments

    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    finished = _entry("LIV Golf Chicago", start="2026-07-01", end="2026-07-04", tour="liv")
    card = {"key": finished["key"], "name": "LIV Golf Chicago", "golfers": []}
    _enrich_with_schedule([card], {finished["key"]: finished})

    assert _filter_stale_tournaments([card], now) == []
