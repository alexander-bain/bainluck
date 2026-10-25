"""#11488 — a container's first-half leg never prices the full-game totals ladder.

THE DEFECT, SEEN ON PRODUCTION (2026-10-23 03:14Z, `/events/15195971/game-markets`,
Nuggets @ Thunder, live Q3, DEN 58 – OKC 55; Authority's retained packet
`artifacts/authority-403-15195971-live-capture-20261023T0315Z/`). All 36 rows of
`totals[]` — 29 Kalshi `KXNBATOTAL-26OCT22DENOKC` rungs and 7 Polymarket O/U
rungs — were served at `over_probability: 0.0005`, `observed_at
03:06:02.336371Z`, `observed_at_basis: capped_to_sibling`, while each row's own
`source_evidence` in the same body read 0.605 at 204.5 falling to 0.01 by 248.5.
The native page printed "<1%" on every line. No served row carried 0.0005 on
its own, so the donor was not in the array.

THE DONOR, FROM THE PACKET. `outcome_revision_at` names exactly nine outcomes at
03:06:02.336371, and `outcome_market_ids` puts all nine in market 66104350 — a
56-leg Polymarket market no served row comes from: the game container, named
for the matchup, one leg per sub-market (`_parent_outcome_data`). "Nuggets vs.
Thunder" types as `game_total` (th·UNDER·r), so its numbered legs entered the
totals bucket; its "1H O/U 122.5" copy sits inside basketball's band, sorts
below every full-game rung, and 7b copied its answered-first-half 0.0005 and
its clock up the ladder. Then the container left the payload.

The fixture below is that page: the Kalshi ladder and the Polymarket rungs at
the retained `source_evidence` values, the first-half sub-market and the
container. Before the fix it reproduces all 36 rows at 0.0005 / capped.

🔴 THE CONTROLS ARE THE POINT. "No row is capped" is satisfied by deleting the
cap. So a real cross-source violation is still capped with its donor's clock, a
non-monotone full-game rung is still capped, a 0% live rung is still dropped,
and a period leg can no longer evict the real rung at its own line.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import _game_markets_cache, get_game_markets

EVENT_ID = 15195971
GROUP = "polymarket:nba-den-okc-2026-10-22"
KALSHI_ID = 66190673
KALSHI_TICKER = "KXNBATOTAL-26OCT22DENOKC"
CONTAINER_ID = 66104350
FIRST_HALF_ID = 67023949
CAPTURED = datetime(2026, 10, 23, 3, 14, tzinfo=timezone.utc)
#: The donor's clock on production — the one every capped row carried.
DONOR_SEEN = datetime(2026, 10, 23, 3, 6, 2, 336371, tzinfo=timezone.utc)

#: `source_evidence[].raw_probability` per Kalshi rung, verbatim from the packet.
KALSHI_LADDER = [
    (204.5, 0.605), (206.5, 0.525), (208.5, 0.465), (210.5, 0.415),
    (212.5, 0.345), (214.5, 0.285), (216.5, 0.235), (218.5, 0.185),
    (220.5, 0.145), (222.5, 0.125), (224.5, 0.115), (226.5, 0.095),
    (228.5, 0.075), (230.5, 0.055), (232.5, 0.05), (234.5, 0.045),
    (236.5, 0.035), (238.5, 0.025), (240.5, 0.02), (242.5, 0.015),
    (244.5, 0.015), (246.5, 0.015), (248.5, 0.01), (250.5, 0.01),
    (252.5, 0.01), (254.5, 0.01), (256.5, 0.01), (258.5, 0.01), (260.5, 0.01),
]
#: (line, Under raw_probability, market id) per Polymarket rung, from the packet.
PM_RUNGS = [
    (221.5, 0.84, 66873537), (227.5, 0.92, 66832952), (233.5, 0.955, 66832955),
    (235.5, 0.96, 66596458), (237.5, 0.9785, 66832956), (243.5, 0.985, 66873544),
    (249.5, 0.9945, 66873546),
]


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _event(period="3rd Quarter", home=55, away=58):
    event = MagicMock()
    event.id = EVENT_ID
    event.home_team_name = "Oklahoma City Thunder"
    event.away_team_name = "Denver Nuggets"
    event.status = "live"
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "basketball_nba"
    event.commence_time = datetime(2026, 10, 23, 1, 30, tzinfo=timezone.utc)
    event.home_score = home
    event.away_score = away
    event.period = period
    event.game_clock = "7:13"
    event.box_score_data = None
    return event


def _market(id, name, external_id, source, group_id=None):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = external_id
    market.event_id = EVENT_ID
    market.category = "game_prop"
    market.status = "open"
    market.source = source
    market.sport_id = None
    market.llm_sport_category = "basketball"
    market.commence_time = datetime(2026, 10, 23, 1, 30, tzinfo=timezone.utc)
    market.market_type = None
    market.group_id = group_id
    market.group_type = None
    return market


def _outcome(id, market_id, name, probability, external_id):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.external_id = external_id
    outcome.current_probability = probability
    outcome.opening_probability = None
    outcome.resolution_source = None
    outcome.is_winner = None
    return outcome


def _kalshi_id(line):
    return 248812000 + int(line)


def _page(*, kalshi=None, first_half_over=0.0005, container=True,
          container_is_a_leg_copy=True, container_copies_the_rungs=True,
          first_half_line=122.5):
    """The 15195971 page. Returns (markets, outcomes, {outcome_id: observed_at})."""
    kalshi = KALSHI_LADDER if kalshi is None else kalshi
    markets, outcomes = [], []
    if container:
        # First in the list on purpose: on a tie at one line the incumbent row
        # keeps it, so the container's leg is given every chance to evict.
        markets.append(
            _market(CONTAINER_ID, "Nuggets vs. Thunder", "nba-den-okc-2026-10-22",
                    "polymarket", GROUP)
        )
        outcomes.append(
            _outcome(251722476, CONTAINER_ID, f"1H O/U {first_half_line}",
                     first_half_over, f"0x1h{first_half_line}")
        )
        for line, under, mid in PM_RUNGS if container_copies_the_rungs else ():
            outcomes.append(
                _outcome(mid * 10 + 9, CONTAINER_ID, f"O/U {line}",
                         round(1 - under, 4), f"0xou{line}")
            )
        if not container_is_a_leg_copy:
            # One leg naming no sibling: no longer a #5273 candidate, so the
            # redundant-parent pass never removes its rows.
            outcomes.append(
                _outcome(251722999, CONTAINER_ID, "Nuggets", 0.44, "0xmoneyline")
            )
    markets.append(
        _market(KALSHI_ID, "Denver vs Oklahoma City: Total Points", KALSHI_TICKER, "kalshi")
    )
    for line, over in kalshi:
        outcomes.append(
            _outcome(_kalshi_id(line), KALSHI_ID, f"Over {line} points", over,
                     f"{KALSHI_TICKER}-{int(line)}")
        )
    for line, under, mid in PM_RUNGS:
        markets.append(
            _market(mid, f"Nuggets vs. Thunder: O/U {line}", f"0xou{line}",
                    "polymarket", GROUP)
        )
        outcomes += [
            _outcome(mid * 10 + 1, mid, "Over", round(1 - under, 4), f"0xou{line}_yes"),
            _outcome(mid * 10 + 2, mid, "Under", under, f"0xou{line}_no"),
        ]
    markets.append(
        _market(FIRST_HALF_ID, f"Nuggets vs. Thunder: 1H O/U {first_half_line}",
                f"0x1h{first_half_line}", "polymarket", GROUP)
    )
    outcomes += [
        _outcome(FIRST_HALF_ID * 10 + 1, FIRST_HALF_ID, "Over", first_half_over,
                 f"0x1h{first_half_line}_yes"),
        _outcome(FIRST_HALF_ID * 10 + 2, FIRST_HALF_ID, "Under",
                 round(1 - first_half_over, 4), f"0x1h{first_half_line}_no"),
    ]
    # Distinct per outcome, so a row serving another leg's clock is visible —
    # and keyed on the id alone, so one leg reads the same clock on every page.
    seen = {o.id: CAPTURED - timedelta(seconds=o.id % 9973 + 1) for o in outcomes}
    seen[251722476] = DONOR_SEEN
    return markets, outcomes, seen


def _payload(event=None, **page):
    event = event or _event()
    markets, outcomes, seen = _page(**page)
    observations = [
        SimpleNamespace(
            id=oid, observed_at=at, price_changed_at=None,
            resolution_source=None, current_probability=None,
        )
        for oid, at in seen.items()
    ]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=event),
            _result(rows=[]),             # #2693 folded_event_ids
            _result(rows=markets),
            _result(all_rows=[]),         # polymarket parent groups
            _result(rows=[]),             # unlinked fallback
            _result(rows=outcomes),
            _result(all_rows=observations),  # #4970 the observation load
        ]
        + [_result(all_rows=[]) for _ in range(20)]
    )
    _game_markets_cache.clear()
    return asyncio.run(get_game_markets(event.id, db)), seen


def _totals_by_line(payload):
    return {row["threshold"]: row for row in payload["totals"]}


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


class TestTheSpecimenLadderServesItsOwnQuotes:
    def test_every_kalshi_rung_serves_its_own_quote(self):
        payload, _seen = _payload()
        rows = _totals_by_line(payload)
        served = {line: rows[line]["over_probability"] for line, _ in KALSHI_LADDER}
        # The ladder is monotone on its own down to 236.5, so nothing there may
        # be touched; above it a Polymarket rung legitimately caps a few.
        for line, over in KALSHI_LADDER:
            if line <= 236.5:
                assert served[line] == over, (
                    f"Over {line} served {served[line]}, its own quote is {over}"
                )
                assert rows[line].get("observed_at_basis") is None, rows[line]
        assert served[204.5] == 0.605

    def test_no_row_is_served_at_the_answered_first_half_price(self):
        payload, _seen = _payload()
        flattened = [r for r in payload["totals"] if r["over_probability"] == 0.0005]
        assert flattened == [], f"rows still carry the first-half leg's 0.0005: {flattened}"

    def test_no_row_carries_the_first_half_legs_clock(self):
        payload, _seen = _payload()
        donor_clock = DONOR_SEEN.isoformat()
        stamped = [r for r in payload["totals"] if r.get("observed_at") == donor_clock]
        assert stamped == [], f"rows still carry the donor's clock: {stamped}"

    def test_every_uncapped_row_carries_its_own_clock(self):
        payload, seen = _payload()
        for row in payload["totals"]:
            if row.get("observed_at_basis") is None:
                (own,) = row["contributor_outcome_ids"]
                assert row["observed_at"] == seen[own].isoformat(), row

    def test_the_first_half_leg_is_not_a_full_game_rung(self):
        payload, _seen = _payload()
        assert 122.5 not in _totals_by_line(payload)
        assert not [r for r in payload["totals"] if "1H" in (r.get("outcome_name") or "")]

    def test_the_ladder_matches_the_same_page_without_the_container(self):
        def shape(payload):
            return [
                (r["threshold"], r["source"], r["over_probability"],
                 r.get("observed_at"), r.get("observed_at_basis"), r["_market_id"])
                for r in payload["totals"]
            ]

        with_container, _ = _payload()
        without, _ = _payload(container=False)
        assert len(without["totals"]) == 36
        assert shape(with_container) == shape(without)


class TestTheCapStillDoesItsJob:
    def test_a_real_cross_source_violation_is_still_capped_with_its_donors_clock(self):
        # Polymarket Under 221.5 at 0.84 is Over 0.16, above Kalshi's 220.5 at
        # 0.145 — a genuine inversion between two venues on one ladder.
        payload, seen = _payload()
        rows = _totals_by_line(payload)
        assert rows[221.5]["over_probability"] == 0.145
        assert rows[221.5]["observed_at_basis"] == "capped_to_sibling"
        assert rows[221.5]["observed_at"] == seen[_kalshi_id(220.5)].isoformat()

    def test_a_non_monotone_full_game_rung_is_still_capped(self):
        ladder = [(line, 0.70 if line == 206.5 else over) for line, over in KALSHI_LADDER]
        payload, seen = _payload(kalshi=ladder)
        row = _totals_by_line(payload)[206.5]
        assert row["over_probability"] == 0.605
        assert row["observed_at_basis"] == "capped_to_sibling"
        assert row["observed_at"] == seen[_kalshi_id(204.5)].isoformat()

    def test_an_unpriced_live_rung_is_still_dropped(self):
        ladder = [(line, 0.0 if line == 208.5 else over) for line, over in KALSHI_LADDER]
        payload, _seen = _payload(kalshi=ladder)
        assert 208.5 not in _totals_by_line(payload)
        assert _totals_by_line(payload)[210.5]["over_probability"] == 0.415


class TestAnOpenFirstHalfLegDoesNotCapTheGame:
    def test_during_the_first_half_the_game_ladder_keeps_its_own_quotes(self):
        # Second quarter: the first-half line is still trading at 0.45, and the
        # game's low rungs sit far above it. Before the fix every one of them
        # was served at ≤ 0.45 for the whole first half.
        ladder = [(204.5, 0.93), (206.5, 0.91), (208.5, 0.88), (210.5, 0.84)]
        payload, _seen = _payload(
            event=_event(period="2nd Quarter", home=30, away=31),
            kalshi=ladder,
            first_half_over=0.45,
        )
        rows = _totals_by_line(payload)
        for line, over in ladder:
            assert rows[line]["over_probability"] == over, rows[line]
            assert rows[line].get("observed_at_basis") is None, rows[line]


class TestAPeriodLegNeverEvictsARealRung:
    def test_the_full_game_rung_at_the_legs_own_line_is_served(self):
        # The container here is not a leg-copy candidate, so the one-row-per-
        # line pick gives it no lower standing — the incumbent keeps the line.
        payload, seen = _payload(
            container_is_a_leg_copy=False,
            container_copies_the_rungs=False,
            first_half_line=227.5,
        )
        row = _totals_by_line(payload).get(227.5)
        assert row is not None, "the 227.5 full-game rung left the page"
        assert row["_market_id"] == 66832952, row
        assert row["over_probability"] == 0.08
        (own,) = row["contributor_outcome_ids"]
        assert own in (66832952 * 10 + 1, 66832952 * 10 + 2), row
        assert row["observed_at"] == seen[own].isoformat()


class TestWhichLegsArePeriods:
    @pytest.mark.parametrize(
        "name",
        ["1H O/U 122.5", "2H O/U 112.5", "1Q O/U 55.5", "1st Half O/U 110.5",
         "First 5 Innings O/U 4.5"],
    )
    def test_a_leg_naming_a_period_is_refused(self, name):
        from app.routes.events import _game_total_leg_prices_a_period

        assert _game_total_leg_prices_a_period(name) is True

    @pytest.mark.parametrize(
        "name",
        ["Over 204.5 points", "Over", "Under", "O/U 221.5", "Yes", "205+",
         "Over 2.5 goals", "Under 8.5 runs", None],
    )
    def test_a_full_game_leg_is_kept(self, name):
        from app.routes.events import _game_total_leg_prices_a_period

        assert _game_total_leg_prices_a_period(name) is False
