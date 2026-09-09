"""#4402 — a four-winner season market is not scaled as if one golfer wins.

WHAT A READER SAW
-----------------
A golf hero on Discover page one, 390px, 2026-09-09 09:35 PT::

    ⛳ GOLF
                      6%
                Scottie Scheffler
    Golfers To Win A PGA Tour Major In 2027

Kalshi's own price for Scheffler on that market is **56.5%**. `GET /api/futures/56775495`
returns 112 outcomes summing to **9.346**, and every golfer the feed served was the
venue's price divided by 9.346 — `_golf_winner_renorm_factor` returning `1/9.346`.

WHY THE RULE WAS WRONG HERE AND RIGHT EVERYWHERE ELSE
-----------------------------------------------------
A single tournament's winner field oversums because independent per-golfer binaries
carry vig; exactly one golfer wins, so scaling to 1.0 recovers a real field (#926,
gotcha #23). A **season** holds four majors, so four golfers win. A sum near 9 is not
vig, and no factor makes that field sum to 1.0 honestly.

The name cannot tell the two apart — `_WINNER_MARKET_RE` matches "win" in both. The
database can: `futures_markets.mutually_exclusive`, which this rule never read.

THE PRODUCTION CENSUS THIS IS BUILT ON (`db-query`, 2026-09-09, status='open')
------------------------------------------------------------------------------
75 open golf markets: 44 ``false``, 31 ``true``, **0 null**.

The 16 winner-matching fields with >=4 priced outcomes, in full — the whole blast
radius of the rule, not just the defect's own population::

    excl  n     sum      source      market
    ----- ----- -------- ----------- -------------------------------------------------
    False    60   31.480 kalshi      Golfers to win a PGA Tour Major before 2030   <- DEFECT
    False    30   30.000 datagolf    Biltmore Championship Asheville - Make the Cut
    False    30   20.000 datagolf    Biltmore Championship Asheville - Top 20 Finish
    False    30   10.000 datagolf    Biltmore Championship Asheville - Top 10 Finish
    False   112    9.346 kalshi      Golfers to win a PGA Tour Major in 2027       <- DEFECT
    False    30    5.000 datagolf    Biltmore Championship Asheville - Top 5 Finish
    True     16    3.825 polymarket  New Zealand Darts Masters: Winner
    True      7    2.570 polymarket  Asia Masters 2026 Winner
    True    197    1.152 odds_api    PGA Championship Winner
    True    144    1.105 kalshi      Amgen Irish Open Winner
    True    205    1.101 odds_api    US Open Winner
    True    205    1.100 odds_api    The Open Winner
    True    147    1.077 odds_api    Masters Tournament Winner
    True    138    1.000 datagolf    Amgen Irish Open - Winner
    True    145    1.000 datagolf    Simmons Bank Open for the Snedeker Foundation - Winner
    True     30    1.000 datagolf    Biltmore Championship Asheville - Winner

Every genuine single-tournament field is ``true`` AND sums 1.00-1.15 — under the 1.5
early return, so untouched either way. The `Top N` / `Make the Cut` rows are already
refused by `_NON_WINNER_MARKET_RE`. **The gate moves the two defect rows and nothing
else in the live population**, which is what the controls below assert.

UNKNOWN IS NOT NO
-----------------
The parameter defaults to ``None`` and only ``False`` refuses. Absence of the flag is
not evidence of non-exclusivity, and over-refusing costs a card that vanishes.
"""

import pytest

from app.routes.golf import _golf_winner_renorm_factor


# The two defect rows, exactly as production holds them.
MAJOR_IN_2027 = ("Golfers to win a PGA Tour Major in 2027 ", 112, 9.346)
MAJOR_BEFORE_2030 = ("Golfers to win a PGA Tour Major before 2030 ", 60, 31.480)


class TestTheDefect:
    def test_the_season_market_is_refused_instead_of_scaled(self):
        name, n, s = MAJOR_IN_2027
        assert _golf_winner_renorm_factor(name, n, s, mutually_exclusive=False) is None

    def test_scheffler_is_no_longer_divided_by_the_whole_field(self):
        """The number the reader saw, stated as the arithmetic that produced it."""
        name, n, s = MAJOR_IN_2027
        before = _golf_winner_renorm_factor(name, n, s)  # the pre-#4402 call
        assert before is not None
        assert round(0.565 * before, 3) == 0.06, "the 6% on the hero, reproduced"

        after = _golf_winner_renorm_factor(name, n, s, mutually_exclusive=False)
        assert after is None, "and it is not produced any more"

    def test_the_worse_sibling_too(self):
        name, n, s = MAJOR_BEFORE_2030
        assert _golf_winner_renorm_factor(name, n, s) == pytest.approx(1 / 31.480)
        assert _golf_winner_renorm_factor(name, n, s, mutually_exclusive=False) is None


class TestTheControls:
    """Each of these fails if the gate is wider than the defect."""

    @pytest.mark.parametrize(
        "name,n,s",
        [
            ("PGA Championship Winner", 197, 1.152),
            ("Amgen Irish Open Winner", 144, 1.105),
            ("US Open Winner", 205, 1.101),
            ("The Open Winner", 205, 1.100),
            ("Masters Tournament Winner", 147, 1.077),
            ("Amgen Irish Open - Winner", 138, 1.000),
            ("Biltmore Championship Asheville - Winner", 30, 1.000),
        ],
    )
    def test_every_real_single_tournament_field_is_untouched(self, name, n, s):
        """All seven are `mutually_exclusive=True` in production and sum under 1.5.

        They take the early return, so the gate can never reach them — but pass the
        flag anyway, because a test that only exercises the path it likes proves the
        path it likes.
        """
        assert _golf_winner_renorm_factor(name, n, s, mutually_exclusive=True) == 1.0
        assert _golf_winner_renorm_factor(name, n, s) == 1.0

    def test_an_oversumming_EXCLUSIVE_field_is_still_renormalized(self):
        """The two `excl=true` oversumming rows in the census keep today's behaviour.

        Without this the gate could be 'refuse everything over 1.5' and still pass
        every arm above, which would drop the only markets #926 exists to save.
        """
        assert _golf_winner_renorm_factor(
            "New Zealand Darts Masters: Winner", 16, 3.825, mutually_exclusive=True
        ) == pytest.approx(1 / 3.825)
        assert _golf_winner_renorm_factor(
            "KLM Open Winner", 157, 5.338, mutually_exclusive=True
        ) == pytest.approx(1 / 5.338)

    def test_unknown_exclusivity_keeps_the_pre_4402_path(self):
        """Zero golf rows are null today; the default is graceful degradation, not policy."""
        assert _golf_winner_renorm_factor(
            "KLM Open Winner", 157, 5.338, mutually_exclusive=None
        ) == pytest.approx(1 / 5.338)

    def test_participation_markets_are_still_refused_by_the_name_rule(self):
        """The four datagolf rows the census shows as `false` and oversumming.

        They were already refused before this change, by `_NON_WINNER_MARKET_RE`, and
        must still be refused for that reason — so the new gate is not silently
        carrying work the name rule is supposed to do.
        """
        for name, n, s in [
            ("Biltmore Championship Asheville - Make the Cut", 30, 30.0),
            ("Biltmore Championship Asheville - Top 20 Finish", 30, 20.0),
            ("Biltmore Championship Asheville - Top 10 Finish", 30, 10.0),
            ("Biltmore Championship Asheville - Top 5 Finish", 30, 5.0),
        ]:
            assert _golf_winner_renorm_factor(name, n, s, mutually_exclusive=True) is None
            assert _golf_winner_renorm_factor(name, n, s) is None

    def test_the_under_threshold_early_return_is_unchanged_by_the_flag(self):
        """`prob_sum <= 1.5` fires FIRST and stays name- and flag-blind (UX-P070)."""
        assert _golf_winner_renorm_factor("Second Round Leader", 1, 0.5) == 1.0
        assert (
            _golf_winner_renorm_factor(
                "Second Round Leader", 1, 0.5, mutually_exclusive=False
            )
            == 1.0
        )


# ---------------------------------------------------------------------------
# THE REACH PROOF
#
# Everything above tests the pure rule. A pure function proves nothing about
# whether the call site hands it the flag: the route builds markets and the
# route is what serves the card. So drive `get_golf` itself, with the season
# market and a real exclusive field seeded side by side — the control is what
# makes the first assertion mean anything, because emptying the golf page would
# also pass it. Harness shape borrowed from `test_golf_route_drops_offer_sheet`.
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from app.models.models import FuturesMarket  # noqa: E402
from app.routes.golf import get_golf  # noqa: E402


def _outcome(oid, name, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        current_yes_bid=max(prob - 0.01, 0.0),
        current_yes_ask=prob + 0.01,
        opening_probability=None,
        probability_change_24h=None,
    )


def _market(mid, name, external_id, outcomes, *, mutually_exclusive):
    return SimpleNamespace(
        id=mid,
        name=name,
        source="kalshi",
        external_id=external_id,
        outcomes=outcomes,
        commence_time=None,
        resolution_date=None,
        status="open",
        llm_sport_category="golf",
        market_tier=1,
        market_metadata=None,
        mutually_exclusive=mutually_exclusive,
    )


#: Market 56775495, the real top six of its 112 outcomes at their real prices.
#: Their partial sum is 1.93, already over the 1.5 threshold; the full field sums
#: 9.346, so production's factor was worse than anything this slice can show.
SEASON_MAJORS = _market(
    56775495,
    "Golfers to win a PGA Tour Major in 2027",
    "KXPGAMAJORWINNER-27",
    [
        _outcome(1, "Scottie Scheffler", 0.565),
        _outcome(2, "Rory McIlroy", 0.420),
        _outcome(3, "Jon Rahm", 0.265),
        _outcome(4, "Cameron Young", 0.230),
        _outcome(5, "Xander Schauffele", 0.225),
        _outcome(6, "Bryson DeChambeau", 0.225),
    ],
    mutually_exclusive=False,
)

#: THE CONTROL. A real one-winner field with a real spread, `mutually_exclusive`
#: true, summing over 1.5 so it takes the same branch and must still renormalize.
REAL_FIELD = _market(
    59512401,
    "Husqvarna British Masters Winner",
    "KXDPWORLDTOUR-HBM26",
    [
        _outcome(11, "Marco Penge", 0.55),
        _outcome(12, "Daniel Hillier", 0.50),
        _outcome(13, "Tom McKibbin", 0.45),
        _outcome(14, "Shaun Norris", 0.40),
    ],
    mutually_exclusive=True,
)


@pytest.fixture
def golf_db():
    markets_result = MagicMock()
    markets_result.scalars.return_value.unique.return_value.all.return_value = [
        SEASON_MAJORS,
        REAL_FIELD,
    ]
    empty = MagicMock()
    empty.__iter__ = lambda self: iter(())

    session = AsyncMock()
    calls = {"n": 0}

    async def _execute(*_args, **_kwargs):
        calls["n"] += 1
        return markets_result if calls["n"] == 1 else empty

    session.execute.side_effect = _execute
    return session


@pytest.fixture(autouse=True)
def _no_schedule(monkeypatch):
    async def _empty():
        return []

    monkeypatch.setattr("app.routes.golf._get_golf_schedule", _empty)


class TestTheFlagReachesTheRule:
    def test_the_column_the_route_reads_exists_on_the_model(self):
        """The call site uses `getattr(market, ..., None)` so three suites of
        pre-column `SimpleNamespace` fixtures keep working. That default must never
        become permanent through a rename — this is the thing that would catch it."""
        assert "mutually_exclusive" in FuturesMarket.__table__.columns

    async def test_the_season_market_does_not_reach_the_page(self, golf_db):
        body = await get_golf(golf_db)
        names = [t["name"] for t in body["tournaments"]]

        assert not any("Major" in n for n in names), (
            "the four-winner season market rendered as a tournament; its hero is the "
            f"6%-for-a-56.5%-golfer card. Got: {sorted(names)}"
        )

    async def test_CONTROL_the_real_field_beside_it_still_renders_renormalized(self, golf_db):
        """Emptying the golf page would pass the assertion above."""
        body = await get_golf(golf_db)
        real = next(
            (t for t in body["tournaments"] if "Husqvarna" in t["name"]), None
        )
        assert real is not None, (
            "the exclusive field vanished too — the gate is wider than the defect. "
            f"Got: {sorted(t['name'] for t in body['tournaments'])}"
        )

        golfers = {g["name"]: g["probability"] for g in real["golfers"]}
        # 0.55 / 1.90, i.e. still renormalized: this rule drops fields, it does not
        # stop scaling the ones that earn it.
        assert golfers["Marco Penge"] == pytest.approx(0.55 / 1.90, abs=0.002)

    async def test_no_golfer_from_the_season_market_leaks_into_the_page(self, golf_db):
        body = await get_golf(golf_db)
        served = {
            g["name"]
            for t in body["tournaments"]
            for g in t.get("golfers", [])
        }
        assert "Scottie Scheffler" not in served
        assert "Rory McIlroy" not in served
