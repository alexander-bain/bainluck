"""#10320: /economics and /entertainment stop printing a decided question as live.

Seen on production 2026-10-03 ~20:10Z (payload built 19:25Z):

  * /economics HOUSING printed "Will Canada housing starts go above 275K this
    year?" at **94.5%** (19527952, `KXCANHOUSTART-27JAN18`). Its one leg is
    graded YES (`api_settlement`) and the price sweep stamped it venue-settled
    on 2026-09-06. /politics has hidden that shape since CERT-452; the other
    category routes never asked.

Two changes, each pinned on its own:

  A. `market_reads_settled` no longer counts a RETRACTED leg
     (`ungradeable_result`, #1852) as graded. Without this, A's twin in B
     would have hidden live bundles: "Which sectors will Trump tariff in
     2026?" (109271) has Pharmaceuticals graded YES and four sectors still
     priced that day, every one carrying the retraction. Measured the same
     day, the old read hid 17 open politics/geopolitics bundles from /politics
     and would have hidden 87 economics/entertainment ones.
  B. /economics and /entertainment ask `market_reads_settled` above the
     append that feeds every section and the spotlight.

HOW THESE GUARDS COULD HAVE BEEN VACUOUS

  1. A fixture another gate already refuses (0.945 is under the 0.98 extreme
     bar, and the leg is stamped fresh so #9343's age gate passes it).
     `TestTheDefectIsInTheSeed` switches the new gate off and requires the
     specimen to be SERVED, so every "gone" below is this change's doing.
  2. B passing on A's work or the reverse: the live-bundle arm runs the REAL
     helper through the route, so reverting A turns it red even though the
     route still calls the helper.
  3. The clock: both routes read `datetime.now`; it is patched to a fixed
     instant (gotcha #44) and the venue stamp is an offset from it.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import economics as econ
from app.routes import entertainment as ent
from app.utils import futures_liveness as liveness
from app.utils.kalshi_fabricated_loss import RETRACTION_SOURCE

FIXED_NOW = datetime(2026, 10, 3, 19, 25, 0, tzinfo=timezone.utc)
FRESH = FIXED_NOW - timedelta(minutes=34)
#: Venue-settled well past the confirmation window, like the specimen's 09-06.
SETTLED_STAMP = (
    FIXED_NOW - timedelta(hours=liveness.VENUE_SETTLED_CONFIRM_HOURS * 10)
).strftime("%Y-%m-%dT%H:%M:%S")


def _leg(idx, name, prob, *, winner=False, source=None):
    return SimpleNamespace(
        id=idx, name=name, current_probability=prob, rank=idx, last_updated=FRESH,
        is_winner=winner, resolution_source=source, probability_change_24h=None,
        previous_probability=None,
    )


def _market(mid, ext, name, legs, *, category, metadata=None):
    return SimpleNamespace(
        id=mid,
        name=name,
        source="kalshi",
        external_id=ext,
        outcomes=legs,
        status="open",
        llm_sport_category=category,
        group_id=None,
        volume=100_000,
        volume_24h=5_000,
        resolution_date=datetime(2027, 1, 18, tzinfo=timezone.utc),
        market_metadata=metadata,
        image_url=None,
        hook_description=None,
        market_tier=2,
        event_id=None,
        updated_at=FRESH,
        created_at=FRESH,
    )


# --- production specimens, read from `futures_outcomes` 2026-10-03 ~20:10Z --


def canada_housing(stamp=SETTLED_STAMP, winner=True):
    """19527952: one leg, graded YES, venue-settled since 2026-09-06."""
    return _market(
        19527952, "KXCANHOUSTART-27JAN18",
        "Will Canada housing starts go above 275K this year?",
        [_leg(1, "Yes", 0.945, winner=winner, source="api_settlement" if winner else None)],
        category="economics",
        metadata={liveness.VENUE_SETTLED_KEY: stamp} if stamp else None,
    )


def tariff_sectors():
    """109271: Pharmaceuticals graded YES; four sectors live, each retracted."""
    return _market(
        109271, "KXTARIFFSECTORS-26", "Which sectors will Trump tariff in 2026?",
        [
            _leg(1, "Pharmaceuticals", 0.97, winner=True, source="api_settlement"),
            _leg(2, "Critical minerals", 0.265, source=RETRACTION_SOURCE),
            _leg(3, "Foreign-made films", 0.21, source=RETRACTION_SOURCE),
            _leg(4, "Wind turbines", 0.21, source=RETRACTION_SOURCE),
            _leg(5, "Canadian aircraft", 0.19, source=RETRACTION_SOURCE),
        ],
        category="economics",
    )


def grammy_decided():
    """`KXGRAMMY-BRR69`'s shape with its winner graded: an exclusive field."""
    return _market(
        62368096, "KXGRAMMY-BRR69", "Grammy Winner: Best Remixed Recording",
        [
            _leg(1, "The Fate of Ophelia (Loud Luxury Remix)", 0.62, winner=True,
                 source="api_settlement"),
            _leg(2, "No Broke Boys (Lee Foss Remix)", 0.21),
            _leg(3, "I Wanna Go (John Summit Remix)", 0.17),
        ],
        category="entertainment",
        metadata={"shape": {"expected_winners": 1}},
    )


def drake_venues():
    """108667's shape: one venue graded YES, the rest live and retracted.

    Production prices the graded leg at 1.000, which the extreme-probability
    gate already refuses, so the winner is at 0.97 here (the tariff
    specimen's price) to keep the row past that gate and put the settled read
    alone in charge of it.
    """
    return _market(
        108667, "KXVENUEPERFORMANCEDRAKE-27JAN01", "Where will Drake perform in 2026?",
        [
            _leg(1, "Scotiabank Arena", 0.97, winner=True, source="api_settlement"),
            _leg(2, "Madison Square Garden", 0.335, source=RETRACTION_SOURCE),
            _leg(3, "SoFi Stadium", 0.185, source=RETRACTION_SOURCE),
            _leg(4, "Rogers Centre", 0.115, source=RETRACTION_SOURCE),
        ],
        category="entertainment",
    )


def _db(markets):
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    return db


async def _economics(markets):
    with patch("app.routes.economics.datetime") as dt:
        dt.now.return_value = FIXED_NOW
        return await econ.get_economics(_db(markets))


async def _entertainment(markets):
    with patch("app.routes.entertainment.datetime") as dt, \
            patch.object(ent, "_withheld_price_outcome_ids", AsyncMock(return_value=set())):
        dt.now.return_value = FIXED_NOW
        return await ent.get_entertainment(_db(markets))


def _ids(payload):
    ids = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("market_id", "kalshi_market_id", "main_market_id") and isinstance(v, int):
                    ids.add(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(payload)
    return ids


class TestTheHelperIgnoresARetraction:
    def test_a_winner_beside_retracted_legs_is_still_open(self):
        assert liveness.market_reads_settled(tariff_sectors(), now=FIXED_NOW) is False

    def test_a_winner_beside_real_grades_still_reads_settled(self):
        """The Georgia arm survives: a terminal LOSS grade is a grade."""
        m = tariff_sectors()
        for leg in m.outcomes[1:]:
            leg.resolution_source = "date_passed"
        assert liveness.market_reads_settled(m, now=FIXED_NOW) is True

    def test_one_retracted_leg_keeps_an_otherwise_graded_bundle_open(self):
        m = tariff_sectors()
        for leg in m.outcomes[1:-1]:
            leg.resolution_source = "api_settlement"
        assert liveness.market_reads_settled(m, now=FIXED_NOW) is False

    def test_the_retraction_does_not_mask_the_exclusive_or_venue_arms(self):
        assert liveness.market_reads_settled(grammy_decided(), now=FIXED_NOW) is True
        assert liveness.market_reads_settled(canada_housing(winner=False), now=FIXED_NOW) is True


class TestTheDefectIsInTheSeed:
    """With the gate off, the fixtures reproduce the production pages."""

    @pytest.mark.asyncio
    async def test_economics_serves_the_housing_specimen_without_the_gate(self):
        with patch.object(econ, "market_reads_settled", return_value=False):
            payload = await _economics([canada_housing(), tariff_sectors()])
        assert 19527952 in _ids(payload)
        assert 109271 in _ids(payload)

    @pytest.mark.asyncio
    async def test_entertainment_serves_the_decided_field_without_the_gate(self):
        with patch.object(ent, "market_reads_settled", return_value=False):
            payload = await _entertainment([grammy_decided(), drake_venues()])
        assert 62368096 in _ids(payload)
        assert 108667 in _ids(payload)


class TestEconomics:
    @pytest.mark.asyncio
    async def test_the_decided_housing_question_leaves_the_page(self):
        payload = await _economics([canada_housing(), tariff_sectors()])
        assert 19527952 not in _ids(payload)

    @pytest.mark.asyncio
    async def test_the_live_tariff_bundle_stays(self):
        """Runs the REAL helper: reverting arm A hides this row."""
        payload = await _economics([canada_housing(), tariff_sectors()])
        assert 109271 in _ids(payload)

    @pytest.mark.asyncio
    async def test_a_fresh_venue_stamp_alone_hides_nothing(self):
        """The confirmation window still binds: an ungraded row stamped an hour
        ago stays on the page."""
        fresh = (FIXED_NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        payload = await _economics([canada_housing(stamp=fresh, winner=False)])
        assert 19527952 in _ids(payload)

    @pytest.mark.asyncio
    async def test_the_spotlight_is_not_handed_a_decided_market(self):
        seen = []

        def capture(markets, **kw):
            seen.extend(m.id for m in markets)
            return []

        with patch.object(econ, "find_cross_source_markets", side_effect=capture):
            await _economics([canada_housing(), tariff_sectors()])
        assert 19527952 not in seen
        assert 109271 in seen


class TestEntertainment:
    @pytest.mark.asyncio
    async def test_the_decided_field_leaves_the_page(self):
        payload = await _entertainment([grammy_decided(), drake_venues()])
        assert 62368096 not in _ids(payload)

    @pytest.mark.asyncio
    async def test_the_live_venue_bundle_stays(self):
        payload = await _entertainment([grammy_decided(), drake_venues()])
        assert 108667 in _ids(payload)
