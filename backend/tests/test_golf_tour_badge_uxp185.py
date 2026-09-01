"""UX-P185 — the golf page stops filing a DP World Tour event under PGA Tour.

Production, 2026-08-30. `/api/golf` served the **Omega European Masters** with
`tour: "pga"` and `tour_label: "PGA Tour"`. It is a DP World Tour event, and
Kalshi says so in the market's own ticker: `KXDPWORLDTOUR-OMEM26`.

The badge is the smaller half. `/categories/golf` **groups its sections by
`tour`**, so the mis-classification did not merely put a wrong three words on a
card — it filed the Omega European Masters under the *PGA Tour* heading, one
section away from the **Husqvarna British Masters**, the other DP World Tour
event of the same week, which was filed correctly because DataGolf happened to
cover it. Two events, one tour, one week, two headings.

The cause was a blind default: `_classify_tour` ended `return "pga"`, so every
tournament that no signal claimed was announced as PGA Tour. Three changes, and
the containment property is the point — **all three sit strictly inside what used
to be that default**, so no tournament that resolves to a non-PGA tour today can
move:

1. Kalshi's series ticker is read as a tour signal (the only one a Kalshi-only
   tournament carries).
2. A title that says "PGA" still earns `pga`, so inverting the default cannot
   strip a badge from a market that names the tour itself.
3. The default becomes `None` — the card degrades to `⛳ Golf` rather than naming
   a tour we cannot evidence.

**The refusal is asserted, not just commented.** `KXLIV` would have been the
obvious fourth trusted prefix and it is a false friend: `KXLIVENATIONUS`
("Courts consider Live Nation a monopoly?") shares it. So is any substring test —
`KXECULPGAME` (210 Ecuadorian football markets) contains "LPGA", and
`KXEFLCHAMPIONSHIPGAME` contains "PGA". Both are pinned below.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routes.golf import (
    TOUR_DISPLAY_NAMES,
    _classify_tour,
    _kalshi_series_tour,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "uxp185_golf_tour_badge.json"
BANKED = json.loads(FIXTURE.read_text())
MARKETS = {m["external_id"]: m for m in BANKED["markets"]}

OMEGA = "KXDPWORLDTOUR-OMEM26"
HUSQVARNA = "KXDPWORLDTOUR-HUBMHBSNF26"
TOUR_CHAMPIONSHIP = "datagolf:pga:60:win"
GOLF_MAJOR = "KXGOLFMAJOR-27"
KORN_FERRY = "KXKFTOUR-ADC26"


class TestTheBankedBeforeIsWhatWeClaim:
    """Vacuity companion for the whole file: assert the BEFORE actually held."""

    def test_the_omega_european_masters_was_served_as_a_pga_tour_event(self):
        served = {t["name"]: t for t in BANKED["served_before"]}
        assert served["Omega European Masters"]["tour_label"] == "PGA Tour"
        assert served["Omega European Masters"]["tour"] == "pga"

    def test_its_dp_world_tour_sibling_of_the_same_week_was_filed_correctly(self):
        """This is what makes it a SPLIT and not just a wrong word."""
        served = {t["name"]: t for t in BANKED["served_before"]}
        assert served["Husqvarna British Masters"]["tour"] == "dp_world"
        assert served["Omega European Masters"]["tour"] != served[
            "Husqvarna British Masters"
        ]["tour"], "the two DP World Tour events of one week were in two sections"

    def test_the_ticker_carried_the_answer_all_along(self):
        assert MARKETS[OMEGA]["external_id"].startswith("KXDPWORLDTOUR")
        assert MARKETS[OMEGA]["source"] == "kalshi"


def _classify(external_id: str) -> str | None:
    """Run the real classifier over one banked production row.

    Mirrors the route's own call, including the source scoping: only a Kalshi row's
    id reaches `kalshi_external_ids`.
    """
    row = MARKETS[external_id]
    metadata = row.get("market_metadata") or {}
    return _classify_tour(
        row["name"],
        "banked",
        False,
        False,
        market_external_ids=[row["external_id"]],
        market_metadata_tours=[metadata["tour"]] if metadata.get("tour") else None,
        kalshi_external_ids=(
            [row["external_id"]] if row["source"] == "kalshi" else None
        ),
    )


class TestTheShip:
    def test_the_omega_european_masters_is_a_dp_world_tour_event(self):
        assert _classify(OMEGA) == "dp_world"

    def test_and_therefore_carries_the_dp_world_tour_label(self):
        assert TOUR_DISPLAY_NAMES[_classify(OMEGA)] == "DP World Tour"

    def test_it_now_shares_a_section_with_its_sibling_of_the_same_week(self):
        """The grouping key is `tour`; equal keys are one section."""
        assert _classify(OMEGA) == _classify(HUSQVARNA) == "dp_world"


class TestTheControlsThatMustNotMove:
    """Every authoritative signal still outranks the two new rules."""

    def test_datagolf_metadata_still_wins_and_the_tour_championship_keeps_pga(self):
        assert _classify(TOUR_CHAMPIONSHIP) == "pga"

    def test_a_title_that_says_pga_still_earns_pga(self):
        assert _classify(GOLF_MAJOR) == "pga"

    def test_the_korn_ferry_ticker_is_read_too(self):
        assert _classify(KORN_FERRY) == "korn_ferry"

    def test_a_name_pattern_still_outranks_the_ticker(self):
        """`_TOUR_CLASSIFICATION_PATTERNS` runs first and must keep running first."""
        assert _classify_tour(
            "LIV Golf Adelaide", "liv", False, False,
            kalshi_external_ids=["KXPGATOUR-SOMETHING"],
        ) == "liv"

    def test_major_and_womens_still_short_circuit_ahead_of_everything(self):
        assert _classify_tour(
            "Masters Winner?", "masters", True, False,
            kalshi_external_ids=["KXDPWORLDTOUR-X"],
        ) == "major"
        assert _classify_tour(
            "AIG Women's Open Winner", "aig", False, True,
            kalshi_external_ids=["KXDPWORLDTOUR-X"],
        ) == "lpga"


class TestTheDefaultNoLongerInventsATour:
    def test_an_unevidenced_tournament_is_unknown(self):
        assert _classify_tour("Some Tournament Winner?", "x", False, False) is None

    def test_unknown_serves_no_label_rather_than_a_wrong_one(self):
        """`⛳ Golf` is the frontend's degrade; the payload must carry no tour."""
        tour = _classify_tour("Some Tournament Winner?", "x", False, False)
        assert (TOUR_DISPLAY_NAMES.get(tour) if tour else None) is None

    def test_the_inversion_is_strictly_contained(self):
        """Nothing that resolved to a non-PGA tour before can change.

        Every new rule fires only after all of them have declined, so the set of
        tournaments classified `pga` can only SHRINK and no other tour's set can.
        """
        for external_id, expected in (
            (TOUR_CHAMPIONSHIP, "pga"),
            (HUSQVARNA, "dp_world"),
            (GOLF_MAJOR, "pga"),
        ):
            assert _classify(external_id) == expected, external_id


class TestTheRefusals:
    """A widening fix is measured for what it lets IN. These are what it keeps out."""

    def test_the_live_nation_market_is_not_liv_golf(self):
        assert _kalshi_series_tour(["KXLIVENATIONUS-30"]) is None

    def test_liv_golf_needs_no_ticker_rule_because_the_title_says_it(self):
        """Vacuity companion: LIV is still reachable, just not via the ticker."""
        assert _classify_tour("LIV Golf Andalucia Champion?", "liv", False, False) == "liv"

    @pytest.mark.parametrize(
        "series,what",
        [
            ("KXECULPGAME-X", "Ecuadorian league football, 210 markets, contains LPGA"),
            ("KXEFLCHAMPIONSHIPGAME-X", "English Championship football, contains PGA"),
            ("KXFACUPGAME-X", "FA Cup football, contains PGA"),
            ("KXCONCACAFCCUPGAME-X", "CONCACAF football, contains PGA"),
        ],
    )
    def test_a_football_ticker_is_never_read_as_a_golf_tour(self, series, what):
        assert _kalshi_series_tour([series]) is None, what

    def test_the_match_is_anchored_to_the_series_segment_not_the_whole_id(self):
        """The event segment is attacker-shaped free text; it must not be searched."""
        assert _kalshi_series_tour(["KXNFLGAME-KXDPWORLDTOUR"]) is None

    def test_a_non_kalshi_id_is_never_read_as_a_kalshi_ticker(self):
        assert _kalshi_series_tour(["datagolf:pga:60:win"]) is None
        assert _kalshi_series_tour(["801410"]) is None
        assert _kalshi_series_tour([None, ""]) is None


class TestTheSweepThatJustifiesEachPrefix:
    """The fixture records the census; these assert it says what the fix assumed."""

    def test_every_trusted_prefix_was_swept_and_found_clean(self):
        trusted = BANKED["kalshi_series_sweep_2026_08_30"]["trusted"]
        assert set(trusted) == {"KXDPWORLDTOUR", "KXLPGA", "KXKFTOUR"}
        for prefix, stats in trusted.items():
            assert stats["non_golf"] == 0, prefix
            assert stats["markets"] > 0, f"{prefix}: a zero denominator proves nothing"

    def test_the_refused_prefix_was_refused_because_it_was_dirty(self):
        refused = BANKED["kalshi_series_sweep_2026_08_30"]["refused"]["KXLIV"]
        assert refused["non_golf"] == 1
        assert "KXLIVENATIONUS" in refused["the_contaminant"]


# ---------------------------------------------------------------------------
# The route, not the helper.
#
# Everything above drives a pure function, and a pure-function guard stays green
# if someone deletes the CALL. UX-P168's file already proved this route over
# banked production rows; this reuses that harness shape to assert the payload a
# reader is actually served.
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from app.routes.golf import get_golf  # noqa: E402


#: LAT-P181 — the banked corpus was captured on 2026-08-30 and the route drops a
#: market whose `resolution_date` is more than 7 days behind `datetime.now()`
#: (`app/routes/golf.py`). The Husqvarna British Masters resolved 2026-08-31, so
#: this file was measured to go red on **2026-09-08** — the corpus does not rot,
#: the calendar walks away from it.
#:
#: Rewriting the dates would cost the thing the corpus is FOR: these are the real
#: rows of a real week, and `_what` says so. So the corpus is re-based instead of
#: edited. Every date is shifted by the same amount, mapping the capture instant
#: onto now, which preserves every interval in the data exactly — Omega still
#: starts 21 days after capture, Husqvarna still resolved the day after — while
#: leaving no calendar date for the route's rolling window to overtake.
_CORPUS_CAPTURED = datetime.fromisoformat(
    BANKED["_source"].rsplit(", ", 1)[1] + "T00:00:00+00:00"
)
_CORPUS_SHIFT = (
    datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    - _CORPUS_CAPTURED
)


def _dt(value):
    """A banked timestamp, re-based so the corpus is always 'this week'."""
    return datetime.fromisoformat(value) + _CORPUS_SHIFT if value else None


class _Outcome:
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.current_probability = row["current_probability"]
        self.opening_probability = row["current_probability"]
        self.is_winner = None
        self.american_odds = None
        self.outcome_metadata = None
        self.probability_change_24h = None
        self.previous_probability = None
        self.last_updated = None


class _Market:
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.source = row["source"]
        self.external_id = row["external_id"]
        self.llm_sport_category = row["llm_sport_category"]
        self.status = row["status"]
        self.commence_time = _dt(row["commence_time"])
        self.resolution_date = _dt(row["resolution_date"])
        self.market_metadata = row.get("market_metadata")
        self.group_id = None
        self.market_tier = 3
        self.outcomes = [_Outcome(o) for o in row["outcomes"]]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _Session:
    """First execute returns the golf markets; every later one returns nothing."""

    def __init__(self, markets):
        self._markets = markets
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        return _Result(self._markets if self.calls == 1 else [])


@pytest.fixture
def served(monkeypatch):
    """Run the real route over the banked production markets."""

    async def _no_schedule():
        return []

    monkeypatch.setattr("app.routes.golf._get_golf_schedule", _no_schedule)

    async def _run():
        session = _Session([_Market(m) for m in BANKED["markets"]])
        return await get_golf(session)

    import asyncio

    return asyncio.run(_run())


def _by_name(served, needle):
    matches = [t for t in served["tournaments"] if needle in t["name"]]
    assert matches, f"{needle!r} was not served at all: {[t['name'] for t in served['tournaments']]}"
    return matches[0]


class TestTheServedGolfPage:
    def test_the_route_served_something(self, served):
        """Denominator guard: every assertion below is vacuous on an empty page."""
        assert served["tournaments"], "the route served no tournaments"

    def test_the_omega_european_masters_is_served_as_dp_world_tour(self, served):
        card = _by_name(served, "Omega European Masters")
        assert card["tour"] == "dp_world"
        assert card["tour_label"] == "DP World Tour"

    def test_it_is_grouped_with_the_other_dp_world_event_of_the_week(self, served):
        """`/categories/golf` sections on `tour` — equal keys are one heading."""
        omega = _by_name(served, "Omega European Masters")
        husqvarna = _by_name(served, "Husqvarna British Masters")
        assert omega["tour"] == husqvarna["tour"] == "dp_world"

    def test_no_served_tournament_claims_a_tour_it_cannot_evidence(self, served):
        """The whole point: a label is either true or absent, never invented."""
        for card in served["tournaments"]:
            if card["tour"] is None:
                assert card["tour_label"] is None, card["name"]
            else:
                assert card["tour_label"] == TOUR_DISPLAY_NAMES[card["tour"]], card["name"]

    def test_the_pga_tour_events_keep_their_badge(self, served):
        """Vacuity companion: the page was not emptied of PGA Tour to pass."""
        pga = [t for t in served["tournaments"] if t["tour"] == "pga"]
        assert pga, [(t["name"], t["tour"]) for t in served["tournaments"]]


class TestTheTickerIsOnlyReadOffTheSourceThatIssuesIt:
    """The scoping is done at the call site, so only the ROUTE can prove it holds.

    Every guard above is built from production rows, and the served population
    carries no market that is Kalshi-shaped on a non-Kalshi source — so deleting
    the `source == "kalshi"` filter passes all of them. That is a guard gap, not a
    false positive, so the specimen is synthetic and says so in the fixture.
    """

    @pytest.fixture
    def served_probe(self, monkeypatch):
        async def _no_schedule():
            return []

        monkeypatch.setattr("app.routes.golf._get_golf_schedule", _no_schedule)
        row = BANKED["synthetic_source_scoping_probe"]["market"]

        async def _run():
            return await get_golf(_Session([_Market(row)]))

        import asyncio

        return asyncio.run(_run())

    def test_the_probe_reaches_the_page_at_all(self, served_probe):
        """Denominator: an empty page would pass the assertion below vacuously."""
        assert len(served_probe["tournaments"]) == 1, served_probe["tournaments"]

    def test_a_kalshi_shaped_ticker_on_a_polymarket_row_is_not_read(self, served_probe):
        card = served_probe["tournaments"][0]
        assert (card["tour"], card["tour_label"]) == (None, None), (
            "the DP World ticker was read off a row Kalshi did not issue — the "
            "call-site source scoping is gone"
        )


# ---------------------------------------------------------------------------
# The Discover feed reads the same two fields, and BOTH of its readers had a
# latent None trap. Neither is on the golf page, so neither is covered above.
# ---------------------------------------------------------------------------

from app.routes.feed import (  # noqa: E402
    _DEFAULT_FEED_TOURS,
    _compute_user_feed_tours,
)


class TestTheDiscoverFeedSurvivesAnUnknownTour:
    """`tour: None` must un-badge a card, never delete it.

    Under the old blind default an unevidenced tournament arrived at the feed as
    `"pga"`, so it passed the tour filter and printed a "PGA Tour:" reason. Saying
    "unknown" honestly is only an improvement if neither of those silently breaks.
    """

    def test_an_unknown_tour_is_still_eligible_for_the_default_audience(self):
        """The filter is `t.get("tour") not in feed_tours` — None must be a member."""
        assert None in _DEFAULT_FEED_TOURS, (
            "a tournament whose tour we cannot evidence would be dropped from "
            "Discover entirely rather than merely losing its badge"
        )

    def test_the_named_tours_are_all_still_eligible(self):
        """Vacuity companion: None was added, nothing was traded away for it."""
        assert {"pga", "major", "dp_world", "lpga", "liv"} <= _DEFAULT_FEED_TOURS

    def test_an_anonymous_reader_gets_the_default_set(self):
        assert _compute_user_feed_tours(None) == set(_DEFAULT_FEED_TOURS)

    def test_a_user_who_picked_specific_tours_is_not_given_unknown_ones(self):
        """The other direction: None must NOT leak into a per-tour preference."""
        ctx = SimpleNamespace(
            is_authenticated=True,
            sport_affinities={"golf_dp_world": 0.9, "golf_pga": 0.0},
        )
        tours = _compute_user_feed_tours(ctx)
        assert tours == {"dp_world"}, tours
        assert None not in tours


#: LAT-P181 — this was the literal `datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)`
#: and it was measured to go red on **2026-09-08**, seven days after it was found.
#:
#: The specimen below is an event that starts `_FEED_NOW + 1 day` and resolves
#: `+ 4 days`, and the page only serves tournaments that have not finished. Pinned
#: to a literal, that window is a calendar window: it opened on 2026-09-04, and on
#: 2026-09-08 the Omega European Masters became a tournament that ended in the
#: past, dropped out of the served page, and four tests that had nothing to do
#: with dates started failing on code nobody had touched.
#:
#: Gotcha #44 — offset FIRST, then truncate. Derived from the clock, the window is
#: always "tomorrow through four days out" and there is no date for it to reach.
_FEED_NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)


def _feed_tournament(key: str, tour: str | None, tour_label: str | None) -> dict:
    """One golf-base entry, shaped as `get_golf_base` publishes it."""
    return {
        "key": key,
        "name": "Omega European Masters",
        "slug": "omega-european-masters",
        "tour": tour,
        "tour_label": tour_label,
        "is_major": False,
        "is_tour_event": True,
        "commence_time": (_FEED_NOW + timedelta(days=1)).isoformat(),
        "resolution_date": (_FEED_NOW + timedelta(days=4)).isoformat(),
        "start_date": (_FEED_NOW + timedelta(days=1)).isoformat(),
        "end_date": (_FEED_NOW + timedelta(days=4)).isoformat(),
        "market_names": ["Omega European Masters Winner"],
        "market_ids": [1],
        "golfers": [
            {
                "id": 1,
                "name": "Adrian Meronk",
                "probability": 0.10,
                "movement_24h": 0.0,
                "probability_change_24h": 0.0,
                "american_odds": None,
                "is_winner": None,
                "rank": 1,
            }
        ],
    }


def _score_feed(monkeypatch, tournaments: list[dict]) -> list[dict]:
    """Drive the REAL `_score_golf_tournaments` over a stubbed golf base.

    Not a replay of the reason expression: an earlier version of this guard
    rebuilt the f-string itself and stayed green when the fix was reverted.
    """
    import asyncio

    import app.utils.golf_base as golf_base
    from app.routes import feed as feed_module

    async def _fake_base(db, now, stages=None):
        return (tournaments, "fresh")

    monkeypatch.setattr(golf_base, "get_golf_base", _fake_base)
    return asyncio.run(
        feed_module._score_golf_tournaments(None, _FEED_NOW, None, None)
    )


class TestTheDiscoverReasonLineNeverPrintsNone:
    def test_an_unknown_tour_reads_golf_not_none(self, monkeypatch):
        items = _score_feed(monkeypatch, [_feed_tournament("unknown", None, None)])
        assert len(items) == 1, "the card was dropped, so the reason is untested"
        assert items[0]["reason"] == "Golf: Adrian Meronk leads at 10.0%"
        assert "None" not in items[0]["reason"]

    def test_a_known_tour_still_names_itself(self, monkeypatch):
        """Vacuity companion: the fallback did not swallow the real labels."""
        items = _score_feed(
            monkeypatch, [_feed_tournament("dpw", "dp_world", "DP World Tour")]
        )
        assert len(items) == 1
        assert items[0]["reason"].startswith("DP World Tour: ")

    def test_the_unknown_card_reaches_the_feed_at_all(self, monkeypatch):
        """The eligibility half, driven rather than asserted on the constant."""
        items = _score_feed(
            monkeypatch,
            [
                _feed_tournament("unknown", None, None),
                _feed_tournament("dpw", "dp_world", "DP World Tour"),
            ],
        )
        assert len(items) == 2, [i.get("reason") for i in items]
