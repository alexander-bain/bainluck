"""UX-P165: the /search category browser stops labelling markets "Other 100%"
and "Candidate Z 100%".

`GET /api/futures/browse` was the FOURTH divergent copy of the display rules —
the one `app/utils/outcome_display.py`'s docstring was written to prevent. It
filtered only the legacy `player AB` regex and then sorted RAW, so an unrankable
outcome could hold position 0.

WHY POSITION 0 IS THE WHOLE STORY ON THIS SURFACE, and why this is not a smaller
re-run of UX-P164. `CompactMarketCard` (`frontend/components/CategoryBrowser.tsx`,
rendered by `app/search/page.tsx:353`) reads `market.top_outcomes[0]` and NOTHING
else. There is no list for a bad row to sit at the end of. The artifact is not a
wasted row — it is the market's entire one-line description.

MEASURED ON THE DEPLOYED BUILD, 2026-08-29, over ALL 21,441 browse markets. A
100% sweep, not a sample; the directive that handed this over had checked the
default page only (`limit=100`, ordered `resolution_date ASC`) and read 0 of 100,
because the soonest-resolving markets are the healthy ones.

    leader is a dominant field row (>= _FIELD_DOMINANT_MIN)   181
    leader is an anonymized reserved slot                     505
    leader is a field outcome BELOW the threshold (plurality)   9
    ------------------------------------------------------------
                                                              695   (3.24%)

Real cards a reader saw:

    "FedEx Cup Playoffs: Winner"                        -> Other 100%
    "2026 Men's US Open Winner (Tennis)"                -> Other 100%
    "WNBA: 2026 MVP"                                    -> Other 100%
    "Massachusetts Governor Republican Primary Winner"  -> Candidate Z 100%
    "Which club will Cristiano Ronaldo play for next?"  -> Team B 100%
    "Fed decisions (Jun-Sep)"                           -> Other 51%   (9-way)

THE PLACEMENT ANSWER FOR THE FOURTH CALLER. The three existing callers do not
agree, deliberately: the feed drops BEFORE its display scale (the divisor was the
bug), detail and search drop AFTER `normalize_display_probs` (because
`_FIELD_DOMINANT_MIN` judges the number RENDERED). Browse has no basis step to
sit either side of — it serves raw prices — so the raw price IS the rendered
number and judging it satisfies the documented rule directly.

`normalize_display_probs` is deliberately NOT added here. That is a scope
decision with a measured cost, asserted below so a later queue has to argue with
a number rather than an omission: 386 browse markets whose whole field is visible
in the served top 3 sum >1.02, and browse cannot tell a coherent one-winner field
from a threshold ladder or a golf make-cut family at that slice. The
#199/#1200/#1201 guards exist because squeezing the wrong family is worse than
leaving raw prices alone.

These tests drive the REAL route function, not a reconstruction of its pipeline.
A pure-library guard stays green when the render drops the fix.
"""

import inspect
import json
from pathlib import Path

import pytest

from app.routes import futures
from app.routes.futures import browse_futures
from app.utils.outcome_display import (
    _FIELD_DOMINANT_MIN,
    is_field_outcome,
    is_placeholder_outcome_name,
)


class FakeOutcome:
    def __init__(self, oid, name, prob, movement=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.probability_change_24h = movement


class FakeMarket:
    def __init__(self, mid, name, outcomes, category="politics"):
        self.id = mid
        self.name = name
        self.outcomes = outcomes
        self.llm_sport_category = category
        self.source = "polymarket"
        self.resolution_date = None


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def unique(self):
        return self

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalar(self):
        return len(self._rows)

    def scalars(self):
        return _Scalars(self._rows)


class FakeDB:
    """Returns the same rows for the count query and the page query, which is all
    `browse_futures` asks of the session."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _query):
        return _Result(self._rows)


async def _browse(markets):
    """Drive the real route and return its `items`.

    `limit`/`offset` are passed explicitly: calling a FastAPI endpoint as a plain
    function leaves the `Query(...)` defaults bound as `Query` objects, which
    SQLAlchemy then tries to coerce to an int.
    """
    payload = await browse_futures(
        category=None, q=None, limit=50, offset=0, db=FakeDB(markets)
    )
    return payload["items"]


def _executable_source(fn):
    """Source with comment lines and the docstring removed.

    Asserting a token is ABSENT from raw source is the negative twin of anchoring
    on a bare name (UX-P164): this module's own comments discuss the normalizer by
    name on purpose, and a raw `not in` would fail on a CORRECT file. Slice to the
    code, then assert.
    """
    src = inspect.getsource(fn)
    if '"""' in src:
        head, _, rest = src.partition('"""')
        _, _, tail = rest.partition('"""')
        src = head + tail
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )


def _leader(item):
    return item["top_outcomes"][0]


# ---------------------------------------------------------------------------
# REAL rows, not reconstructions. `tests/fixtures/uxp165_browse_leaders.json`
# holds the actual `futures_outcomes` rows for two live markets (pulled
# 2026-08-29 via /api/admin/db-query) together with the payload the shipped
# pre-fix formatter builds from them — which is asserted below to be byte-equal
# to what production served.
# ---------------------------------------------------------------------------

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "uxp165_browse_leaders.json").read_text()
)


def _fixture_market(mid):
    spec = next(m for m in FIXTURE["markets"] if m["id"] == mid)
    return spec, FakeMarket(
        spec["id"],
        spec["name"],
        [
            FakeOutcome(r["id"], r["name"], r["probability"], r["movement"])
            for r in spec["db_rows"]
        ],
        category=spec["llm_sport_category"],
    )


FEDEX_SPEC, FEDEX = _fixture_market(10853985)  # -> Other 100%
MASS_GOV_SPEC, MASS_GOV = _fixture_market(113738)  # -> Candidate Z 100%

FED_DECISIONS = FakeMarket(  # -> Other 51% on a 9-way market
    16624246,
    "Fed decisions (Jun-Sep)",
    [
        FakeOutcome(20, "Other", 0.51),
        FakeOutcome(21, "One 25 bps cut", 0.31),
        FakeOutcome(22, "No change", 0.11),
        FakeOutcome(23, "Two 25 bps cuts", 0.07),
    ],
    category="economics",
)


class TestThePreFixDiagnosisIsWhatItClaims:
    """Pin the DIAGNOSIS. If a raw sort stops producing these leaders, the comments
    explaining why this fix exists are describing a payload that no longer occurs."""

    @pytest.mark.parametrize(
        "spec,expected",
        [(FEDEX_SPEC, "Other"), (MASS_GOV_SPEC, "Candidate Z")],
    )
    def test_the_fixture_reproduces_what_production_served(self, spec, expected):
        # Verified against the 21,441-market live sweep: these `before` rows are
        # byte-equal to the payload `/api/futures/browse` returned on 2026-08-29.
        assert spec["before"]["top_outcomes"][0]["name"] == expected
        assert spec["before"]["top_outcomes"][0]["probability"] == 1.0

    @pytest.mark.parametrize(
        "market,expected",
        [(FEDEX, "Other"), (MASS_GOV, "Candidate Z"), (FED_DECISIONS, "Other")],
    )
    def test_a_raw_probability_sort_puts_the_unrankable_row_first(self, market, expected):
        raw_first = max(market.outcomes, key=lambda o: o.current_probability or 0)
        assert raw_first.name == expected

    def test_the_legacy_regex_this_replaced_caught_none_of_them(self):
        # `_GARBAGE_OUTCOME_RE` only ever matched "player AB". Every leader above
        # sailed through it, which is why browse served them.
        for market in (FEDEX, MASS_GOV, FED_DECISIONS):
            for o in market.outcomes:
                assert not futures._GARBAGE_OUTCOME_RE.match(o.name or "")


class TestTheFixOnTheRealRoute:
    @pytest.mark.asyncio
    async def test_a_dominant_field_row_never_leads(self):
        item = (await _browse([FEDEX]))[0]
        assert _leader(item)["name"] == "Scottie Scheffler"
        assert _leader(item)["probability"] == 0.23

    @pytest.mark.asyncio
    async def test_a_dominant_field_row_is_not_served_at_all(self):
        # Not merely demoted: browse slices [:3] off a list whose mean length is
        # 6.3, so "the end" is frequently still inside the slice (UX-P163).
        item = (await _browse([FEDEX]))[0]
        assert "Other" not in [o["name"] for o in item["top_outcomes"]]

    @pytest.mark.asyncio
    async def test_an_anonymized_reserved_slot_never_leads(self):
        # 26 of this market's 30 rows are "Candidate A".."Candidate Z", every one
        # priced at exactly 1.0. The card was describing a governor's primary by
        # naming an anonymized slot.
        item = (await _browse([MASS_GOV]))[0]
        assert _leader(item)["name"] == "Michael Minogue"
        assert _leader(item)["probability"] == 0.981
        assert not any(
            is_placeholder_outcome_name(o["name"]) for o in item["top_outcomes"]
        )

    @pytest.mark.asyncio
    async def test_a_sub_threshold_field_outcome_is_demoted_below_the_top_name(self):
        # 0.51 is under `_FIELD_DOMINANT_MIN`, so it is NOT dropped — its share
        # stays visible. It just must not headline a 9-way market.
        item = (await _browse([FED_DECISIONS]))[0]
        assert _leader(item)["name"] == "One 25 bps cut"
        names = [o["name"] for o in item["top_outcomes"]]
        assert "Other" in names
        assert names.index("Other") > 0

    @pytest.mark.asyncio
    async def test_the_surviving_answers_keep_their_book_prices(self):
        # The fix narrows WHAT IS SHOWN. It must not restate a single number.
        item = (await _browse([FEDEX]))[0]
        assert [(o["name"], o["probability"]) for o in item["top_outcomes"]] == [
            ("Scottie Scheffler", 0.23),
            ("Chris Gotterup", 0.109),
            ("Collin Morikawa", 0.105),
        ]

    @pytest.mark.asyncio
    async def test_no_served_leader_is_unrankable_across_every_specimen(self):
        for item in await _browse([FEDEX, MASS_GOV, FED_DECISIONS]):
            ldr = _leader(item)
            assert not is_placeholder_outcome_name(ldr["name"])
            assert not (
                is_field_outcome(ldr["name"])
                and (ldr["probability"] or 0) >= _FIELD_DOMINANT_MIN
            )


class TestItNeverEmpties:
    """An honest-empty decision belongs to the surface, not to a display filter.
    A card with no subtitle at all is a worse artifact than a labelled one — the
    same rule `display_rank_order` and `drop_dominant_field_outcomes` both state."""

    @pytest.mark.asyncio
    async def test_an_all_placeholder_market_still_renders_rows(self):
        market = FakeMarket(
            1,
            "Sachsen-Anhalt Parliamentary Election Winner",
            [FakeOutcome(1, "Party P", 1.0), FakeOutcome(2, "Party S", 0.4)],
        )
        item = (await _browse([market]))[0]
        assert len(item["top_outcomes"]) == 2
        assert _leader(item)["name"] == "Party P"

    @pytest.mark.asyncio
    async def test_an_all_dominant_field_market_still_renders_rows(self):
        market = FakeMarket(
            2, "Nothing but field", [FakeOutcome(1, "Other", 1.0), FakeOutcome(2, "TBD", 0.95)]
        )
        item = (await _browse([market]))[0]
        assert len(item["top_outcomes"]) == 2

    @pytest.mark.asyncio
    async def test_a_market_with_no_outcomes_does_not_raise(self):
        item = (await _browse([FakeMarket(3, "Empty", [])]))[0]
        assert item["top_outcomes"] == []


class TestTheScopeDecisionIsAsserted:
    """`normalize_display_probs` is deliberately absent. Pinned so that adding it
    is a decision someone makes on purpose, against the measured 386."""

    @pytest.mark.asyncio
    async def test_browse_does_not_normalize_a_field_that_sums_past_one(self):
        # A threshold ladder: "Above 0" / "Above 1" / "Above 2" are independent
        # YES prices and their raw values are the honest ones (gotcha #17/#23).
        market = FakeMarket(
            58728645,
            "How many Executive Orders will Trump sign this week?",
            [
                FakeOutcome(1, "Above 0", 0.705),
                FakeOutcome(2, "Above 1", 0.395),
                FakeOutcome(3, "Above 2", 0.095),
            ],
            category="politics",
        )
        item = (await _browse([market]))[0]
        assert [o["probability"] for o in item["top_outcomes"]] == [0.705, 0.395, 0.095]

    def test_the_route_does_not_call_the_normalizer(self):
        assert "normalize_display_probs" not in _executable_source(futures.browse_futures)

    def test_that_absence_assertion_is_not_vacuous(self):
        # The comments DO name the normalizer, deliberately. If the stripper ever
        # stops working, the test above would pass for the wrong reason.
        assert "normalize_display_probs" in inspect.getsource(futures.browse_futures)


class TestOutcomeCountBasis:
    @pytest.mark.asyncio
    async def test_outcome_count_is_the_placeholder_filtered_count(self):
        # Matches search's basis (`events.py`), so the two answer surfaces count
        # the same way. The badge no longer includes rows the card cannot show:
        # 30 raw rows, 26 of them anonymized slots, so the honest count is 4.
        item = (await _browse([MASS_GOV]))[0]
        assert len(MASS_GOV.outcomes) == 30
        assert item["outcome_count"] == 4

    @pytest.mark.asyncio
    async def test_outcome_count_is_taken_before_the_dominant_field_drop(self):
        # The drop is a DISPLAY rule about position 0; it must not silently shrink
        # a count the reader reads as "how big is this market". FedEx has no
        # placeholders, so its 31 rows survive the count even though "Other" is
        # dropped from the served top-3.
        item = (await _browse([FEDEX]))[0]
        assert item["outcome_count"] == 31
        assert "Other" not in [o["name"] for o in item["top_outcomes"]]


class TestSourceLevelOrdering:
    """Anchor on the CALL SITE, not a bare token (UX-P163), and slice to the call
    before asserting absence (UX-P164 — `"outcome_count": len(...)` is a different
    and legitimate use of the same substring)."""

    def test_the_drop_runs_before_the_slice(self):
        src = inspect.getsource(futures.browse_futures)
        drop_at = src.index("display_outcomes = drop_dominant_field_outcomes(")
        slice_at = src.index("top3 = display_outcomes[:3]")
        assert drop_at < slice_at

    def test_leader_pick_runs_after_the_drop_and_before_the_slice(self):
        src = inspect.getsource(futures.browse_futures)
        drop_at = src.index("display_outcomes = drop_dominant_field_outcomes(")
        pick_at = src.index("leader_pick_order(display_outcomes)")
        slice_at = src.index("top3 = display_outcomes[:3]")
        assert drop_at < pick_at < slice_at

    def test_the_placeholder_filter_uses_the_shared_predicate(self):
        src = inspect.getsource(futures.browse_futures)
        body = src[src.index("real_outcomes = ["):src.index("sorted_outcomes = sorted(")]
        assert "is_placeholder_outcome_name(o.name)" in body
        assert "_GARBAGE_OUTCOME_RE" not in body
