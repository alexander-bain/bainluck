"""UX-P273 / #2674 — the recession card answers the question it asks.

`/economics` printed a hardcoded "Recession by end of 2026" above a number
supplied by whichever binary recession market the theme loop happened to see
LAST, on a query with no ``ORDER BY``. Measured on production 2026-09-02 the
card read **13%**, which is market ``109350`` *"Will the IMF declare a global
recession before 2027?"* at 12.5% — wrong country, wrong body, wrong year —
while ``113012`` *"US recession by end of 2026?"*, the market the label
actually asks about, read 12.0% and was nowhere on the card.

═══ WHERE THESE ASSERTIONS LOOK ═══

The load-bearing tests call ``get_economics`` and read
``result["themes"]["recession"]``. That dict IS the published payload — it is
what the precompute task JSON-serializes into the cache and what the endpoint
returns — so there is no transform between the assertion point and the bytes
the page receives. Asserting on ``select_recession_headline`` alone would stop
one step short of the pairing, which is the whole defect: the ranking can be
perfect and the card can still lie if the route does not ship the question.

═══ THREE WAYS THESE GUARDS COULD HAVE BEEN VACUOUS ═══

1. **Substring.** ``"US recession by end of 2026?"`` contains
   ``"recession by end of 2026"``, the old hardcoded label. Any containment
   assertion on the question would therefore pass on a card that still prints
   the literal. Every question claim below is an **equality**.

2. **The clock.** The route calls ``datetime.now(timezone.utc)`` and the
   ranking keys off the current year, so an unpinned test would change meaning
   on 2027-01-01 and the year arm would quietly stop testing anything
   (gotcha #44). ``datetime`` is patched to a fixed instant in every run.

3. **Order.** A fixture listing the right answer last would be green under the
   old "last one wins" code. ``_PRODUCTION_POOL`` deliberately puts the winner
   in the MIDDLE, and ``test_shuffling_the_query_order_cannot_change_the_
   headline`` runs the whole route over 40 permutations.
"""

from datetime import datetime, timezone
from itertools import permutations
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.economics import get_economics
from app.utils.economics_headline import (
    RecessionCandidate,
    select_recession_headline,
)

# Mid-year so no "end of 2026" market is anywhere near its own deadline, which
# keeps `is_title_implied_stale` out of the story.
FIXED_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _yes(prob: float):
    return SimpleNamespace(id=1, name="Yes", current_probability=prob, rank=1)


def _market(mid: int, name: str, prob: float, source: str = "kalshi"):
    """A binary recession market shaped as `get_economics` reads it."""
    return SimpleNamespace(
        id=mid,
        name=name,
        source=source,
        external_id=f"kxrecession-{mid}",
        outcomes=[_yes(prob)],
        status="open",
        llm_sport_category="economics",
        group_id=None,
        volume=10_000.0,
    )


# The eight binary recession markets open on production 2026-09-02, measured
# by db-query. `113304 Canada recession before 2027?` (99.6%) is deliberately
# ABSENT: its leader probability exceeds PROBABILITY_EXTREME_HIGH (0.98) so
# `should_exclude_from_featured` drops it before the theme loop ever sees it —
# a hazard checked and found to be nil, recorded here so it is not re-guessed.
#
# NOTE the order: the eventual winner (113012) sits at index 2, NOT last. Under
# the old "last one wins" code this pool yields 52.0 from `US recession by end
# of 2027?`, so a fix that only reshuffles cannot pass by accident.
_PRODUCTION_POOL = [
    (109350, "Will the IMF declare a global recession before 2027?", 12.5),
    (12777832, "UK Recession in 2026?", 16.5),
    (113012, "US recession by end of 2026?", 12.0),
    (16755442, "Canada recession in 2026?", 31.0),
    (108622, "Recession this year?", 7.0),
    (12832719, "Japan recession in 2026?", 9.5),
    (12924898, "Recession in 2027?", 27.5),
    (58605173, "US recession by end of 2027?", 52.0),
]


def _production_markets():
    return [_market(mid, name, pct / 100.0) for mid, name, pct in _PRODUCTION_POOL]


async def _run(markets):
    """Call the builder and return the published recession theme."""
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt:
        dt.now.return_value = FIXED_NOW
        payload = await get_economics(db)
    return payload["themes"]["recession"]


# ---------------------------------------------------------------------------
# Non-vacuity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheSeedIsReal:
    """If the fixtures stop reaching the recession theme, everything below is
    a loop over nothing. These fail loudly instead."""

    async def test_the_pool_reaches_the_recession_theme(self):
        rec = await _run(_production_markets())
        assert rec["count"] == len(_PRODUCTION_POOL), (
            "the seeded markets no longer classify as `recession` — every "
            "assertion in this file is vacuous until this passes"
        )

    async def test_the_pool_produces_a_headline_at_all(self):
        rec = await _run(_production_markets())
        assert rec["main_prob"] is not None
        assert rec["main_q"]


# ---------------------------------------------------------------------------
# The ship: the question and the number name the same market
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheHeadlineNamesItsOwnMarket:

    async def test_the_published_question_is_the_selected_markets_own_name(self):
        """The binding. Equality, not containment — see vacuity note 1."""
        rec = await _run(_production_markets())
        assert rec["main_q"] == "US recession by end of 2026?"
        assert rec["main_prob"] == 12.0
        assert rec["main_market_id"] == 113012

    async def test_the_reported_defect_does_not_reproduce(self):
        """#2674's exact screen: 12.5 (rendered 13%) from the IMF market."""
        rec = await _run(_production_markets())
        assert rec["main_prob"] != 12.5
        assert rec["main_market_id"] != 109350
        assert "IMF" not in (rec["main_q"] or "")

    async def test_the_question_and_the_number_come_from_one_market(self):
        """Stated as an invariant over the pool, not as one expected string:
        whatever is selected, its published probability must be that market's
        own. This survives the ranking being changed for good reasons."""
        rec = await _run(_production_markets())
        by_id = {mid: (name, pct) for mid, name, pct in _PRODUCTION_POOL}
        name, pct = by_id[rec["main_market_id"]]
        assert rec["main_q"] == name
        assert rec["main_prob"] == pct

    async def test_a_foreign_market_never_headlines_a_us_macro_card(self):
        rec = await _run(_production_markets())
        for token in ("UK", "Japan", "Canada", "global"):
            assert token.lower() not in (rec["main_q"] or "").lower()


# ---------------------------------------------------------------------------
# The defect class: order dependence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheHeadlineDoesNotDependOnQueryOrder:

    async def test_shuffling_the_query_order_cannot_change_the_headline(self):
        """The strongest guard here. The query has no ORDER BY, so this is the
        property the old code actually lacked — not merely 'it picked a bad
        market' but 'the market it picks is undefined'."""
        seen = set()
        pool = _production_markets()
        for perm in list(permutations(pool, len(pool)))[:40]:
            rec = await _run(perm)
            seen.add((rec["main_market_id"], rec["main_prob"], rec["main_q"]))
        assert seen == {(113012, 12.0, "US recession by end of 2026?")}, (
            f"the headline moved with query order across 40 permutations: {seen}"
        )

    async def test_the_headline_is_not_simply_the_last_market_processed(self):
        """Pin the old rule directly: put the worst candidate last and assert
        the card does not adopt it."""
        pool = _production_markets()
        last = pool[-1]
        rec = await _run(pool)
        assert last.name == "US recession by end of 2027?"
        assert rec["main_market_id"] != last.id
        assert rec["main_prob"] != 52.0


# ---------------------------------------------------------------------------
# No duplication, and fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheHeadlineIsNotAlsoARowBeneathItself:

    async def test_the_selected_market_is_absent_from_the_side_rows(self):
        """#2674 opens with 13% sitting above a contradicting 7% — the headline
        was one arbitrary member of the list printed under it."""
        rec = await _run(_production_markets())
        side_ids = [r["market_id"] for r in rec["side_markets"]]
        assert rec["main_market_id"] not in side_ids

    async def test_every_other_candidate_is_still_offered_as_a_row(self):
        """Excluding the headline must not delete anything else. `side_markets`
        is capped at 6, so compare against the pool minus the headline, capped
        the same way."""
        rec = await _run(_production_markets())
        expected = [mid for mid, _, _ in _PRODUCTION_POOL if mid != 113012][:6]
        assert [r["market_id"] for r in rec["side_markets"]] == expected


@pytest.mark.asyncio
class TestFailClosedWhenThereIsNoCandidate:

    async def test_no_recession_market_publishes_a_null_question_and_number(self):
        """A number with no question is the same defect with the label missing,
        so the route publishes neither and the page renders no headline."""
        gdp_only = [_market(1, "GDP growth in Q3 2026?", 0.4)]
        rec = await _run(gdp_only)
        assert rec["main_prob"] is None
        assert rec["main_q"] is None
        assert rec["main_market_id"] is None


# ---------------------------------------------------------------------------
# CONTROLS — green on master too. Their job is to prove the fix narrowed the
# selection rather than changing what the rest of the card renders.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheRestOfTheCardIsUnchanged:

    async def test_control_side_rows_keep_their_shape_and_values(self):
        """CONTROL (green on master too). Every non-headline row still carries
        its own question and its own probability."""
        rec = await _run(_production_markets())
        by_id = {mid: (name, pct) for mid, name, pct in _PRODUCTION_POOL}
        assert rec["side_markets"]
        for row in rec["side_markets"]:
            name, pct = by_id[row["market_id"]]
            assert row["q"] == name
            assert row["prob"] == pct

    async def test_control_the_count_still_reports_the_whole_theme(self):
        """CONTROL (green on master too). `count` is the theme size, not the
        rendered row count — excluding the headline from the rows must not
        shrink it."""
        rec = await _run(_production_markets())
        assert rec["count"] == 8

    async def test_control_gdp_quarters_are_untouched(self):
        """CONTROL (green on master too). The GDP arm shares the loop."""
        markets = _production_markets()
        gdp = SimpleNamespace(
            id=999, name="GDP growth in Q3 2026?", source="kalshi",
            external_id="kxgdp-999", status="open",
            llm_sport_category="economics", group_id=None, volume=1.0,
            outcomes=[
                SimpleNamespace(id=1, name="Above 3%", current_probability=0.2, rank=1),
                SimpleNamespace(id=2, name="Above 2%", current_probability=0.5, rank=2),
                SimpleNamespace(id=3, name="Above 1%", current_probability=0.8, rank=3),
            ],
        )
        rec = await _run(markets + [gdp])
        assert rec["gdp_quarters"], "the GDP arm stopped producing brackets"
        assert rec["gdp_quarters"][0]["market_id"] == 999


# ---------------------------------------------------------------------------
# The ranking itself
# ---------------------------------------------------------------------------


def _c(mid: int, name: str, pct: float = 10.0):
    return RecessionCandidate(market_id=mid, name=name, prob_pct=pct)


class TestTheRanking:

    def test_us_scope_beats_a_better_year_abroad(self):
        chosen = select_recession_headline(
            [_c(1, "Japan recession in 2026?"), _c(2, "US recession by end of 2027?")],
            current_year=2026,
        )
        assert chosen.market_id == 2

    def test_the_current_year_beats_a_year_less_question(self):
        chosen = select_recession_headline(
            [_c(1, "Recession this year?"), _c(2, "US recession by end of 2026?")],
            current_year=2026,
        )
        assert chosen.market_id == 2

    def test_a_year_less_question_beats_another_year(self):
        chosen = select_recession_headline(
            [_c(1, "Recession in 2027?"), _c(2, "Recession this year?")],
            current_year=2026,
        )
        assert chosen.market_id == 2

    def test_before_next_year_is_the_current_year_window(self):
        """'before 2027' closes at the end of 2026 — the same window as 'by end
        of 2026', and the phrasing Kalshi reaches for most often."""
        chosen = select_recession_headline(
            [_c(1, "Recession this year?"), _c(2, "US recession before 2027?")],
            current_year=2026,
        )
        assert chosen.market_id == 2

    def test_ties_break_on_market_id_not_input_order(self):
        a = _c(500, "US recession by end of 2026?")
        b = _c(100, "American recession by end of 2026?")
        assert select_recession_headline([a, b], current_year=2026).market_id == 100
        assert select_recession_headline([b, a], current_year=2026).market_id == 100

    def test_an_empty_pool_selects_nothing(self):
        assert select_recession_headline([], current_year=2026) is None

    def test_current_year_is_required_and_has_no_default(self):
        """A default of `datetime.now().year` would hand every future call site
        a clock dependency its author never chose, and would make the year arm
        of this suite change meaning on Jan 1 (gotcha #44)."""
        import inspect

        sig = inspect.signature(select_recession_headline)
        param = sig.parameters["current_year"]
        assert param.default is inspect.Parameter.empty
        assert param.kind is inspect.Parameter.KEYWORD_ONLY


class TestScopeMarkersMatchOnWordBoundaries:
    """A substring test cannot be used for scope: 'us' occurs inside 'August'
    and 'because', and 'uk' inside 'Sukkur'. These pin the boundary."""

    def test_a_us_market_is_not_read_as_foreign_via_an_embedded_token(self):
        chosen = select_recession_headline(
            [
                _c(1, "Japan recession in 2026?"),
                _c(2, "Recession by August 2026 because of tariffs?"),
            ],
            current_year=2026,
        )
        assert chosen.market_id == 2, "an embedded token was read as a scope marker"

    def test_a_genuinely_foreign_market_is_still_ranked_down(self):
        """The counter-case to the test above: if the boundary check were
        loosened into 'never match', this one goes red."""
        chosen = select_recession_headline(
            [_c(1, "UK Recession in 2026?"), _c(2, "Recession in 2029?")],
            current_year=2026,
        )
        assert chosen.market_id == 2
