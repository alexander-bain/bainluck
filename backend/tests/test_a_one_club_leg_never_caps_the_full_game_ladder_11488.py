"""#11488, second entrance — a container's ONE-CLUB leg never prices the full-game ladder.

THE DEFECT, SEEN ON PRODUCTION (2026-10-26 01:52:55Z, `/events/15335537/game-markets`,
Clippers @ Thunder, OKC 108 – LAC 101, total 209; Authority's packet
`artifacts-authority-11488/aftercheck-live-15332690/`). After #11494 went live
(v5889), the full-game rungs 193.5 … 211.5 were all served at
`over_probability: 0.48`, `observed_at 23:40:07.622960Z`, `observed_at_basis:
capped_to_sibling` — lines 193.5–207.5 had already come in, and their own
stored prices read 0.9995 / 0.98. No served row carried 0.48 on its own.

THE DONOR. The Polymarket game container 66535495 "Clippers vs. Thunder" (one leg
per sub-market) carries "Thunder O/U 121.5 … 131.5" — the home club's total.
The container types as `game_total` (th·UNDER·r), so its numbered legs enter the
full-game bucket; #11494 left out the legs naming a PERIOD, but a leg naming one
CLUB still went in. Basketball's band (120–320) admits 121.5+, the legs sort
below every full-game rung, "Thunder O/U 127.5" at 0.48 became the ladder's
floor, and 7b copied its price and clock up to 211.5. Then the container left
the payload.

The fixture is that page: the Polymarket full-game members at their stored
prices, the Thunder team-total members, and the container with copies of both
plus its period leg. Before the fix it serves 193.5–211.5 at 0.48 / capped.

🔴 THE CONTROLS ARE THE POINT. "No row is capped" is satisfied by deleting the
cap, so the genuine 223.5 inversion on this very page is still capped with its
served donor's clock, a leg naming both clubs or none is still a rung, and the
#11494 period leg stays out.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import _game_markets_cache, get_game_markets

EVENT_ID = 15335537
GROUP = "polymarket:1215093"
CONTAINER_ID = 66535495
FIRST_HALF_ID = 67475226
CAPTURED = datetime(2026, 10, 26, 0, 50, tzinfo=timezone.utc)
#: The donor's clock on production — the one every capped row carried.
DONOR_SEEN = datetime(2026, 10, 25, 23, 40, 7, 622960, tzinfo=timezone.utc)
DONOR_LINE = 127.5

#: (line, stored Over, member market id) — `futures_outcomes.current_probability`
#: of each "Clippers vs. Thunder: O/U N" member, read 2026-10-26 01:53Z.
FULL_GAME = [
    (193.5, 0.9995, 67407286), (195.5, 0.9995, 67407287), (197.5, 0.9995, 67407288),
    (199.5, 0.9995, 67407289), (201.5, 0.9995, 67407290), (203.5, 0.9995, 67407291),
    (205.5, 0.9995, 67407292), (207.5, 0.98, 67407293), (209.5, 0.765, 67407294),
    (211.5, 0.525, 67407295), (213.5, 0.305, 67407296), (215.5, 0.22, 67407297),
    (217.5, 0.085, 67407298), (219.5, 0.06, 67407299), (221.5, 0.03, 67407254),
    (223.5, 0.035, 67407300), (225.5, 0.025, 67407301), (227.5, 0.0205, 67407302),
]
#: (line, the container's "Thunder O/U N" leg) — verbatim from market 66535495.
THUNDER = [
    (121.5, 0.74), (123.5, 0.77), (125.5, 0.90), (127.5, 0.48), (129.5, 0.955),
    (131.5, 0.945),
]


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _event():
    event = MagicMock()
    event.id = EVENT_ID
    event.home_team_name = "Oklahoma City Thunder"
    event.away_team_name = "Los Angeles Clippers"
    event.status = "live"
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "basketball_nba"
    event.commence_time = datetime(2026, 10, 25, 23, 0, tzinfo=timezone.utc)
    event.home_score = 88
    event.away_score = 80
    event.period = "4th Quarter"
    event.game_clock = "9:02"
    event.box_score_data = None
    return event


def _market(id, name, external_id, group_id=GROUP):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = external_id
    market.event_id = EVENT_ID
    market.category = "game_prop"
    market.status = "open"
    market.source = "polymarket"
    market.sport_id = None
    market.llm_sport_category = "basketball"
    market.commence_time = datetime(2026, 10, 25, 23, 0, tzinfo=timezone.utc)
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


def _thunder_member_id(line):
    return 67524900 + int(line)


def _page(*, container=True, team_leg_name="Thunder O/U {line}"):
    """The 15335537 page. Returns (markets, outcomes, {outcome_id: observed_at})."""
    markets, outcomes = [], []
    if container:
        # First in the list: on a tie at one line the incumbent keeps it, so the
        # container's leg is given every chance to take a line.
        markets.append(_market(CONTAINER_ID, "Clippers vs. Thunder", "nba-lac-okc-2026-10-25"))
        outcomes.append(_outcome(251720001, CONTAINER_ID, "1H O/U 106.5", 0.0005, "0x1h106.5"))
        for line, over in THUNDER:
            outcomes.append(
                _outcome(251720100 + int(line), CONTAINER_ID,
                         team_leg_name.format(line=line), over, f"0xokc{line}")
            )
        for line, over, mid in FULL_GAME:
            outcomes.append(_outcome(mid * 10 + 9, CONTAINER_ID, f"O/U {line}", over, f"0xou{line}"))
    for line, over, mid in FULL_GAME:
        markets.append(_market(mid, f"Clippers vs. Thunder: O/U {line}", f"0xou{line}"))
        outcomes += [
            _outcome(mid * 10 + 1, mid, "Over", over, f"0xou{line}_yes"),
            _outcome(mid * 10 + 2, mid, "Under", round(1 - over, 4), f"0xou{line}_no"),
        ]
    for line, over in THUNDER:
        mid = _thunder_member_id(line)
        markets.append(_market(mid, f"Thunder Team Total: O/U {line}", f"0xokc{line}"))
        outcomes += [
            _outcome(mid * 10 + 1, mid, "Over", over, f"0xokc{line}_yes"),
            _outcome(mid * 10 + 2, mid, "Under", round(1 - over, 4), f"0xokc{line}_no"),
        ]
    markets.append(_market(FIRST_HALF_ID, "Clippers vs. Thunder: 1H O/U 106.5", "0x1h106.5"))
    outcomes += [
        _outcome(FIRST_HALF_ID * 10 + 1, FIRST_HALF_ID, "Over", 0.0005, "0x1h106.5_yes"),
        _outcome(FIRST_HALF_ID * 10 + 2, FIRST_HALF_ID, "Under", 0.9995, "0x1h106.5_no"),
    ]
    # Distinct per outcome, so a row serving another leg's clock is visible.
    seen = {o.id: CAPTURED - timedelta(seconds=o.id % 9973 + 1) for o in outcomes}
    seen[251720100 + int(DONOR_LINE)] = DONOR_SEEN
    return markets, outcomes, seen


def _payload(page=None, **kw):
    event = _event()
    markets, outcomes, seen = (page or _page)(**kw)
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


class TestTheFullGameLadderKeepsItsOwnPrices:
    def test_the_lines_that_came_in_are_not_served_at_the_team_legs_price(self):
        payload, _seen = _payload()
        rows = _totals_by_line(payload)
        for line, over, _mid in FULL_GAME[:8]:
            assert rows[line]["over_probability"] == over, rows[line]
            assert rows[line].get("observed_at_basis") is None, rows[line]

    def test_no_row_carries_the_team_legs_clock(self):
        payload, _seen = _payload()
        donor_clock = DONOR_SEEN.isoformat()
        stamped = [r for r in payload["totals"] if r.get("observed_at") == donor_clock]
        assert stamped == [], f"rows still carry the donor's clock: {stamped}"

    def test_every_capped_row_names_a_served_donor(self):
        payload, _seen = _payload()
        rows = sorted(payload["totals"], key=lambda r: r["threshold"])
        own = [r for r in rows if r.get("observed_at_basis") is None]
        for r in rows:
            if r.get("observed_at_basis") == "capped_to_sibling":
                assert any(
                    o["threshold"] < r["threshold"]
                    and o["over_probability"] == r["over_probability"]
                    and o["observed_at"] == r["observed_at"]
                    for o in own
                ), r

    def test_no_team_leg_is_a_full_game_rung(self):
        payload, _seen = _payload()
        lines = _totals_by_line(payload)
        for line, _over in THUNDER:
            assert line not in lines
        assert not [r for r in payload["totals"] if "Thunder O/U" in (r.get("outcome_name") or "")]

    def test_the_ladder_matches_the_same_page_without_the_container(self):
        def shape(payload):
            return [
                (r["threshold"], r["source"], r["over_probability"],
                 r.get("observed_at"), r.get("observed_at_basis"), r["_market_id"])
                for r in payload["totals"]
            ]

        with_container, _ = _payload()
        without, _ = _payload(container=False)
        assert len(without["totals"]) == len(FULL_GAME)
        assert shape(with_container) == shape(without)


def _shared_line_page():
    """One container, no members, so no leg is a redundant-parent candidate.

    Its one-club leg and a full-game leg share line 205.5, the one-club leg
    listed first, so on a tie it is the incumbent at that line.
    """
    markets = [_market(CONTAINER_ID, "Clippers vs. Thunder", "nba-lac-okc-2026-10-25")]
    outcomes = [
        _outcome(900001, CONTAINER_ID, "Thunder O/U 205.5", 0.10, "0xokc205.5"),
        _outcome(900002, CONTAINER_ID, "O/U 205.5", 0.9995, "0xou205.5"),
        _outcome(900003, CONTAINER_ID, "O/U 209.5", 0.765, "0xou209.5"),
        _outcome(900004, CONTAINER_ID, "O/U 213.5", 0.305, "0xou213.5"),
    ]
    return markets, outcomes, {o.id: CAPTURED for o in outcomes}


class TestAOneClubLegNeverTakesARealRungsLine:
    def test_the_full_game_rung_at_a_shared_line_is_served(self):
        # Where a team-total line meets the game band (hockey, soccer: 0.5-2.5)
        # the ORDER is the fix: left out after the one-row-per-line pick, the
        # one-club leg would win 205.5 there and then be filtered, taking the
        # real rung's line with it. lane1's M3 on PR #11647.
        payload, _seen = _payload(page=_shared_line_page)
        row = _totals_by_line(payload).get(205.5)
        assert row is not None, "the 205.5 full-game rung left the page"
        assert row["over_probability"] == 0.9995, row
        assert row["outcome_name"] == "O/U 205.5", row


class TestTheCapStillDoesItsJob:
    def test_the_real_223_5_inversion_is_still_capped_with_its_donors_clock(self):
        # 223.5 stored 0.035 sits above 221.5's 0.03 on this page — a genuine
        # inversion between two full-game rungs, still capped.
        payload, seen = _payload()
        row = _totals_by_line(payload)[223.5]
        assert row["over_probability"] == 0.03
        assert row["observed_at_basis"] == "capped_to_sibling"
        donor = _totals_by_line(payload)[221.5]
        assert donor.get("observed_at_basis") is None
        assert row["observed_at"] == donor["observed_at"]


class TestWhichLegsAreRungs:
    @pytest.mark.parametrize(
        "name", ["Clippers vs. Thunder O/U {line}", "O/U {line}", "Total {line}"]
    )
    def test_a_leg_naming_both_clubs_or_none_is_still_a_rung(self, name):
        # Same container, the leg renamed: no longer one club's total, so it
        # stays in the ladder exactly as before this fix (and caps as before).
        payload, _seen = _payload(team_leg_name=name)
        rows = _totals_by_line(payload)
        assert DONOR_LINE in rows or any(
            r.get("observed_at") == DONOR_SEEN.isoformat() for r in payload["totals"]
        ), [(r["threshold"], r["over_probability"]) for r in payload["totals"]]

    def test_the_period_leg_stays_out(self):
        payload, _seen = _payload()
        assert 106.5 not in _totals_by_line(payload)
