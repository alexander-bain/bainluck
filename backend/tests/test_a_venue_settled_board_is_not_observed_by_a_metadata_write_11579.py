"""#11579 — a metadata write is not somebody observing a board the venue has closed.

WHAT A READER SAW (Hawks team page, 390px, 2026-10-24 02:12Z): Season Futures row 1
read "Nickeil Alexander-Walker · Most Improved Player Winner · >99%", and
``/futures/412`` printed the same 99.5% as a live question. Market 412,
``KXNBAMIMP-26``, is last season's award: Kalshi titles the event "2025-26
season" and serves 0 markets for it. Every one of its 59 legs was last written
2026-04-24 22:46:10, and ``market_metadata.price_refresh_venue_settled_since``
reads ``2026-09-06T04:54:36``.

#8011's parent clause acquitted it because ``updated_at`` read 00:53:16Z that
day — the Discover LLM pass (``generated_at`` 00:53:05Z), not a price poll.
``board_touched_at`` caps that stamp at the venue's "over" marker, and every
caller of the rule now reads the parent stamp through it.

Dates are offsets from one anchor, never branches on the clock (gotcha #44).
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.routes import prop_families as prop_families_route
from app.routes.user import _query_team_futures
from app.utils.futures_liveness import VENUE_SETTLED_KEY
from app.utils.market_staleness import (
    BOARD_UNOBSERVED_DAYS,
    board_cannot_be_unobserved,
    board_touched_at,
    unobserved_board_keys,
)

HAWKS = 1
NOW = datetime.now(timezone.utc).replace(microsecond=0)
#: The specimen's measured gaps, as offsets: the LLM write 1h ago, the venue's
#: "over" 48 days ago, the legs 182 days ago.
TOUCHED = NOW - timedelta(hours=1)
VENUE_OVER = NOW - timedelta(days=48)
LEGS = NOW - timedelta(days=182)


def _marker(at: datetime) -> dict:
    # Written as `futures_liveness` writes it: naive ISO-8601 UTC, no offset.
    return {VENUE_SETTLED_KEY: at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}


def _outcome(oid, name, prob, bid, ask, *, stamp, team_id=None, rank=1,
             is_winner=False, resolution_source=None):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=bid, current_yes_ask=ask,
        resolution_source=resolution_source, is_winner=is_winner,
        volume_24h=None, volume_24h_at=None, last_updated=stamp,
        price_changed_at=None, volume=None, team_id=team_id,
        external_id=f"KXNBAMIMP-26-{oid}", probability_change_24h=None, rank=rank,
        current_american_odds=None, rank_change_24h=None,
        opening_probability=None, opening_american_odds=None, team=None,
    )


def _mip(*, metadata, legs=LEGS, touched=TOUCHED):
    """Production shape of market 412 (db-query 2026-10-24 02:18Z), four legs."""
    return SimpleNamespace(
        id=412, name="Most Improved Player Winner", description=None,
        category="championship", source="kalshi", external_id="KXNBAMIMP-26",
        group_id="kalshi:KXNBAMIMP-26", status="open",
        llm_sport_category="basketball", sport=None, sport_id=None,
        resolution_date=datetime(2027, 4, 12, 14, tzinfo=timezone.utc),
        commence_time=None, created_at=None, market_metadata=metadata,
        market_type="field", mutually_exclusive=True, event_id=None,
        market_tier=3, canonical_market_key="basketball::mip:2027",
        hook_description=None, image_url=None, category_tags=[],
        updated_at=touched,
        outcomes=[
            _outcome(1, "Nickeil Alexander-Walker", 0.995, 0.99, 1.00,
                     stamp=legs, team_id=HAWKS),
            _outcome(2, "Jalen Duren", 0.02, 0.01, 0.03, stamp=legs, rank=2),
            _outcome(3, "Derrick White", 0.01, 0.0, 0.02, stamp=legs, rank=3),
            _outcome(4, "Max Christie", 0.01, 0.0, 0.02, stamp=legs, rank=4),
        ],
    )


def _observations(market):
    return [(o.id, o.last_updated) for o in market.outcomes]


class TestTheParentStamp:
    def test_the_venue_marker_caps_a_later_metadata_write(self):
        assert board_touched_at(_mip(metadata=_marker(VENUE_OVER))) == VENUE_OVER

    def test_no_marker_reads_updated_at_exactly_as_before(self):
        assert board_touched_at(_mip(metadata=None)) == TOUCHED
        assert board_touched_at(_mip(metadata={"shape": {"v": 2}})) == TOUCHED

    def test_the_marker_only_ever_moves_the_stamp_earlier(self):
        later = _marker(TOUCHED + timedelta(hours=2))
        assert board_touched_at(_mip(metadata=later)) == TOUCHED

    @pytest.mark.parametrize("raw", ["", "not-a-date", "2026-13-40T00:00:00", 17, None])
    def test_an_unreadable_marker_fails_open_to_updated_at(self, raw):
        market = _mip(metadata={VENUE_SETTLED_KEY: raw})
        assert board_touched_at(market) == TOUCHED

    def test_no_updated_at_stays_unreadable_whatever_the_marker_says(self):
        # The marker is a cap, never a stamp of its own: a row with no poller
        # stamp keeps failing open in the rule, as #8011 requires.
        assert board_touched_at(_mip(metadata=_marker(VENUE_OVER), touched=None)) is None

    def test_a_naive_updated_at_is_read_as_utc(self):
        naive = TOUCHED.replace(tzinfo=None)
        assert board_touched_at(_mip(metadata=_marker(VENUE_OVER), touched=naive)) == VENUE_OVER


class TestTheRuleNowSeesTheSpecimen:
    def test_the_specimen_withholds_every_leg(self):
        market = _mip(metadata=_marker(VENUE_OVER))
        assert unobserved_board_keys(
            _observations(market),
            board_touched_at=board_touched_at(market),
            fleet_newest_observation=NOW,
        ) == {1, 2, 3, 4}

    def test_strawman_the_bare_column_acquits_it(self):
        """The defect as shipped: the LLM write reads as an observation."""
        market = _mip(metadata=_marker(VENUE_OVER))
        assert unobserved_board_keys(
            _observations(market),
            board_touched_at=market.updated_at,
            fleet_newest_observation=NOW,
        ) == set()

    def test_the_prefilter_no_longer_skips_the_read(self):
        market = _mip(metadata=_marker(VENUE_OVER))
        assert board_cannot_be_unobserved(
            _observations(market), board_touched_at=market.updated_at, now=NOW,
        ) is True  # the old stamp: the fleet read was skipped
        assert board_cannot_be_unobserved(
            _observations(market), board_touched_at=board_touched_at(market), now=NOW,
        ) is False

    def test_a_recent_venue_marker_is_still_inside_the_floor(self):
        """A venue blip 29 days behind the fleet cannot qualify — and one good
        price would have cleared the marker long before that."""
        market = _mip(metadata=_marker(NOW - timedelta(days=BOARD_UNOBSERVED_DAYS - 1)))
        assert unobserved_board_keys(
            _observations(market),
            board_touched_at=board_touched_at(market),
            fleet_newest_observation=NOW,
        ) == set()

    def test_our_own_outage_still_cannot_blank_it(self):
        """The fleet froze the day after the venue said "over": nothing qualifies,
        however long the wall clock runs."""
        market = _mip(metadata=_marker(VENUE_OVER), legs=VENUE_OVER - timedelta(days=60))
        assert unobserved_board_keys(
            _observations(market),
            board_touched_at=board_touched_at(market),
            fleet_newest_observation=VENUE_OVER + timedelta(days=1),
        ) == set()

    def test_live_legs_keep_the_board_whatever_the_marker_says(self):
        """The leg clause is untouched: legs written this week keep their prices."""
        market = _mip(metadata=_marker(VENUE_OVER), legs=NOW - timedelta(days=2))
        assert unobserved_board_keys(
            _observations(market),
            board_touched_at=board_touched_at(market),
            fleet_newest_observation=NOW,
        ) == set()

    def test_a_graded_board_is_a_result_and_stays(self):
        market = _mip(metadata=_marker(VENUE_OVER))
        assert unobserved_board_keys(
            _observations(market),
            board_touched_at=board_touched_at(market),
            fleet_newest_observation=NOW,
            board_has_a_verdict=True,
        ) == set()


class TestTheMarketPage:
    """`/api/futures/412` — the detail formatter, which reads the stamp itself."""

    def _served(self, market):
        from app.routes import futures as futures_routes

        detail = futures_routes._format_market_detail(
            market, None, set(), fleet_newest_observation=NOW,
        )
        return {r["name"]: r["probability"] for r in detail["outcomes"]}

    def test_the_hero_leg_is_withheld(self):
        served = self._served(_mip(metadata=_marker(VENUE_OVER)))
        assert served["Nickeil Alexander-Walker"] is None
        assert all(p is None for p in served.values()), served

    def test_strawman_without_the_marker_it_prints(self):
        served = self._served(_mip(metadata=None))
        assert served["Nickeil Alexander-Walker"] == pytest.approx(0.995, abs=0.01)


# ─── the Hawks team page, through `_query_team_futures` and the real screen ───


def _result(rows, scalar=None):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    res.scalar_one_or_none.return_value = scalar
    return res


class _Savepoint:
    def __init__(self, db):
        self.db = db

    async def commit(self):
        self.db.savepoint_log.append("commit")

    async def rollback(self):
        self.db.savepoint_log.append("rollback")


class _DB:
    def __init__(self, markets):
        self.markets = markets
        self.savepoint_log: list[str] = []
        self.fleet_reads = 0

    async def begin_nested(self):
        return _Savepoint(self)

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        if "max(futures_outcomes.last_updated)" in sql:
            self.fleet_reads += 1
            return _result([], scalar=NOW)  # the fleet is writing prices today
        if "FROM teams JOIN sports" in sql:
            team = SimpleNamespace(
                id=HAWKS, name="Atlanta Hawks", sport_id=2, espn_id="1",
                roster_players=None, logo_url_small=None, logo_url=None,
                primary_color=None,
            )
            return _result([(team, "basketball_nba")])
        if "futures_outcomes.team_id IN" in sql and "futures_markets" in sql:
            return _result([
                (o, m, "basketball_nba")
                for m in self.markets for o in m.outcomes if o.team_id == HAWKS
            ])
        if "count(*)" in sql.lower() and "GROUP BY" in sql:
            return _result([(m.id, len(m.outcomes), None) for m in self.markets])
        if "FROM futures_markets" in sql and "futures_outcomes" not in sql.split("WHERE")[0]:
            return _result(list(self.markets))
        return _result([])


async def _team_page(markets):
    db = _DB(markets)
    data = await _query_team_futures([HAWKS], db, limit=30)
    return {i["market_id"]: i["probability"] for i in data["items"]}, db


@pytest.mark.asyncio
class TestTheHawksTeamPage:
    async def test_last_seasons_award_leaves_season_futures(self):
        served, db = await _team_page([_mip(metadata=_marker(VENUE_OVER))])
        assert 412 not in served, served
        assert db.fleet_reads == 1
        assert db.savepoint_log == ["commit"]  # a completed screen, not a fail-open

    async def test_strawman_without_the_marker_it_prints_at_99(self):
        served, db = await _team_page([_mip(metadata=None)])
        assert served[412] == pytest.approx(0.995, abs=0.01)
        assert db.fleet_reads == 0  # the recent row stamp skipped the fleet read

    async def test_strawman_without_the_board_rules_it_prints(self):
        async def _nothing(_db, _market):
            return set()

        with patch.object(prop_families_route, "_board_staleness_withheld", _nothing):
            served, _db = await _team_page([_mip(metadata=_marker(VENUE_OVER))])
        assert served[412] == pytest.approx(0.995, abs=0.01)


# ─── the class guard: no caller reads the bare column again ───

APP = Path(__file__).resolve().parents[1] / "app"
RULES = {"unobserved_board_keys", "board_cannot_be_unobserved"}


def _rule_calls():
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in RULES:
                yield path, node


def test_every_caller_reads_the_parent_stamp_through_the_helper():
    calls = list(_rule_calls())
    # #11616 consolidates the search/detail rule calls into one shared helper.
    # Pin every surviving path, and the two delegation edges below, rather than
    # mistaking the old direct-call count for reader coverage.
    expected = {
        "routes/entertainment.py",
        "routes/futures.py",
        "routes/league_futures.py",
        "routes/prop_families.py",
        "utils/futures_outcome_representation.py",
    }
    assert expected <= {str(p.relative_to(APP)) for p, _ in calls}
    for path, call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        stamp = kw.get("board_touched_at")
        assert isinstance(stamp, ast.Call) and getattr(stamp.func, "id", None) == "board_touched_at", (
            f"{path.relative_to(APP.parent)}:{call.lineno} passes "
            f"{ast.unparse(stamp) if stamp is not None else 'nothing'} as board_touched_at"
        )


@pytest.mark.parametrize(
    "path,function,callee",
    [
        (
            "routes/events.py",
            "_search_withheld_price_ids",
            "local_futures_withheld_ids",
        ),
        ("routes/futures.py", "_format_market_detail", "represent_futures_outcomes"),
        (
            "utils/futures_outcome_representation.py",
            "represent_futures_outcomes",
            "local_futures_withheld_ids",
        ),
        (
            "utils/futures_outcome_representation.py",
            "local_futures_withheld_ids",
            "unobserved_board_keys",
        ),
    ],
)
def test_search_and_detail_still_reach_the_capped_parent_stamp(path, function, callee):
    tree = ast.parse((APP / path).read_text())
    func = next(
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function
    )
    assert any(
        isinstance(n, ast.Call) and getattr(n.func, "id", None) == callee
        for n in ast.walk(func)
    ), f"{path}:{function} no longer reaches {callee}"
