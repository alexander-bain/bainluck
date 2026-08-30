"""UX-P191 — the weather page prints the same percentage as the rest of the site.

`/api/weather` rounded every probability with Python's built-in `round()`. That
is BANKER'S rounding: it breaks a `.5` tie toward the EVEN neighbour, so
`round(78.5)` is 78. Every other runtime in this product breaks it upward —
`Math.round(78.5)` is 79 on web, `(78.5).rounded()` is 79 on native, and the
server's own `rendered_percent` (`app/utils/graded_card.py`, #1933,
`contracts/rendered_percent.json`) is 79. Weather was the one surface that
disagreed, and it disagreed in one direction: always a point LOW.

═══ THE READER COUNT ═══

Measured on production 2026-08-30, banked in
`backend/tests/fixtures/uxp191_printed_percent.json`:

    442  open weather markets the route serves
    203  whose leading outcome sits exactly on a `.5` boundary
     81  where banker's printed a point below the site's own answer   (18.3%)

  2,650  priced outcomes across those markets
    373  printed a point low                                          (14.1%)

And against the numbers actually ON THE PAGE — every value carrying a market id
in `GET /api/weather/{featured,cities,rain,events,climate,wildcards}`:

    500  served numbers sampled
     71  change                                                       (14.2%)

Two of the five featured heroes are in that 71. "Where will it rain on Aug 29,
2026?" is priced 0.785 and printed **78%**.

Four of them are worse than a point: temperature buckets priced 0.005 printed a
bare **0%** over a live, actively-quoted price. Half-up prints 1%.

═══ WHAT EVERY TEST HERE DOES ═══

Drives the real route through the real FastAPI app and reads the payload a
reader's page is built from. Nothing re-derives the percentage — the guard that
used to live in `test_weather_featured_leader_uxp186.py` recomputed the expected
value with `round()`, which is the defect's own arithmetic, so it agreed with
the bug and could never have caught it. That line is now driven through
`rendered_percent` too.

    python3 -m pytest tests/integration/test_weather_printed_percent_uxp191.py -v
"""

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.utils.graded_card import rendered_percent

# No `pytestmark = pytest.mark.asyncio`: pytest.ini runs asyncio in AUTO mode, so
# the async tests here are collected without one — and a blanket mark warns on
# every SYNC test in the file (this one has six).


FIXTURE = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "uxp191_printed_percent.json"
    ).read_text(encoding="utf-8")
)
CENSUS = FIXTURE["weather_census"]
SERVED_CHANGED = FIXTURE["weather_served_changed"]
SPECIMENS = FIXTURE["weather_specimens"]


# ---------------------------------------------------------------------------
# Helpers — the same shapes test_weather_featured_leader_uxp186.py uses.
# ---------------------------------------------------------------------------


def _outcome(name, probability, *, outcome_id=1):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=None,
        rank=1,
    )


def _soon() -> str:
    """A date label a week out, written the way production writes one.

    OFFSET FIRST, then format (gotcha #44). These market names are read by
    `is_title_implied_stale`, which drops a market whose TITLE says it is over —
    so a hard-coded "Aug 28, 2026" is a test that passes until the date passes.
    The first draft of this file did exactly that and two tests served an empty
    payload.
    """
    d = datetime.now(timezone.utc) + timedelta(days=7)
    return f"{d:%b} {d.day}, {d.year}"


def _market(*, market_id=1, name, outcomes, source="kalshi", resolution_date=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=f"kx{market_id}",
        source=source,
        category="weather",
        llm_sport_category="weather",
        outcomes=outcomes,
        resolution_date=resolution_date or now + timedelta(days=14),
        updated_at=now,
        status="open",
    )


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars


def _serve(mock_db, markets):
    mock_db.execute.return_value = _MockResult(markets)


# ═══ 1 · the fixture really is the defect, and the instrument works ═══════════


class TestTheBankedStateIsGenuinelyBroken:
    def test_the_census_is_the_one_the_docstring_quotes(self):
        assert CENSUS == {
            "open_weather_markets": 442,
            "markets_leader_on_half_boundary": 203,
            "markets_where_bankers_prints_low": 81,
            "priced_open_weather_outcomes": 2650,
            "outcomes_where_bankers_prints_low": 373,
            "served_numbers_sampled": 500,
            "served_numbers_that_change": 71,
        }
        # The disagreeing set is a SUBSET of the boundary set — every market
        # that rounds differently must first be sitting on a `.5`. If this ever
        # inverts, one of the two counts is measuring something else.
        assert (
            CENSUS["markets_where_bankers_prints_low"]
            <= CENSUS["markets_leader_on_half_boundary"]
            <= CENSUS["open_weather_markets"]
        )
        assert len(SERVED_CHANGED) == CENSUS["served_numbers_that_change"]

    def test_the_two_rules_really_do_disagree_on_the_banked_specimens(self):
        """Prove the instrument before trusting any assertion built on it.

        Postgres numeric is exact but Python floats are not, so a probability
        sitting on a `.5` in the DATABASE does not necessarily sit on one after
        `float(p) * 100` — `0.135` becomes `13.500000000000002`, where the two
        rules agree. Only the specimens that survive that conversion are real,
        and the census above counts exactly those.
        """
        for spec in SPECIMENS:
            v = float(spec["probability"]) * 100
            assert round(v) == spec["before"], "banker's, the shipped-before rule"
            assert math.floor(v + 0.5) == spec["after"], "half-up, the site's rule"
            assert spec["after"] == spec["before"] + 1

    def test_every_banked_change_is_upward_by_exactly_one(self):
        """A systematic direction, not noise. Banker's only ever breaks a tie
        toward the even neighbour, and on the `.5` grid that is always DOWN
        relative to half-up — so no reader has ever seen weather round a number
        UP against the rest of the site."""
        for row in SERVED_CHANGED:
            assert row["after"] == row["before"] + 1, row
            # ...and the number the live API served really was the wrong one.
            assert row["served_printed"] == row["before"], row

    def test_the_change_reaches_the_hero_and_the_zero_boundary(self):
        featured = [r for r in SERVED_CHANGED if r["surface"] == "featured"]
        assert len(featured) == 2, "two of the five rotating heroes"
        assert any(r["market_id"] == 59704867 for r in featured), "the rain hero"

        # The sharpest rows: a live price rendered as a flat zero.
        zeros = [r for r in SERVED_CHANGED if r["before"] == 0]
        assert len(zeros) == 4
        for r in zeros:
            assert r["probability"] > 0, "actively quoted, not absent"
            assert r["after"] == 1


# ═══ 2 · the ship, driven through the real routes ════════════════════════════


_SEATTLE_LOW = [
    # "Lowest temperature in Seattle on Aug 28, 2026?" — market 59708196, whose
    # leader is priced 0.985 and printed 98%.
    _outcome("54°F or above", 0.985, outcome_id=1),
    _outcome("53°F", 0.010, outcome_id=2),
    _outcome("52°F or below", 0.005, outcome_id=3),
]


class TestTheFeaturedHeroRoundsHalfUp:
    async def test_the_biggest_number_on_the_page_matches_the_contract(
        self, client, mock_db
    ):
        _serve(mock_db, [
            _market(
                market_id=59708196,
                name=f"Lowest temperature in Seattle on {_soon()}?",
                outcomes=_SEATTLE_LOW,
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        assert item["prob"] == 99, "0.985 half-up; banker's printed 98"
        assert item["prob"] == rendered_percent(0.985)

    async def test_the_wildcards_rail_uses_the_same_rule(self, client, mock_db):
        """`_highest_prob` feeds four surfaces. Fixing one and not the rest
        would leave the same market printing two different numbers depending on
        which rail a reader met it on."""
        _serve(mock_db, [
            _market(
                market_id=59699701,
                name="Major volcano eruption in 2026?",
                outcomes=[
                    _outcome("At least 1", 0.110, outcome_id=11),
                    _outcome("At least 2", 0.885, outcome_id=12),
                ],
            )
        ])

        item = (await client.get("/api/weather/wildcards")).json()[0]

        assert item["prob"] == 89, "0.885 half-up; banker's printed 88"

    async def test_a_value_off_the_boundary_is_untouched(self, client, mock_db):
        """THE CONTROL, and it matters more than the finding. Half-up and
        banker's differ ONLY on an exact `.5`. If a probability that is nowhere
        near a tie moved, the change is not a rounding-rule swap — it is a
        different number, and the whole claim of this queue is false."""
        _serve(mock_db, [
            _market(
                market_id=1,
                name=f"Where will it rain on {_soon()}?",
                outcomes=[
                    _outcome("Seattle", 0.740, outcome_id=1),
                    _outcome("Miami", 0.7201, outcome_id=2),
                    _outcome("New York City", 0.045, outcome_id=3),
                ],
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        assert item["prob"] == 74, "0.740 rounds to 74 under either rule"

    async def test_the_named_leader_did_not_move(self, client, mock_db):
        """The other control. UX-P186 coupled `_highest_prob` to
        `_leader_outcome_name` so the printed number and the printed name always
        come from the same row. Changing the ROUNDING must not disturb the
        SELECTION — the scan that picks the leader compares raw probabilities
        and never sees a percent."""
        _serve(mock_db, [
            _market(
                market_id=59708196,
                name=f"Lowest temperature in Seattle on {_soon()}?",
                outcomes=_SEATTLE_LOW,
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        assert item["leader"] == "54°F or above"
        assert item["prob"] == 99


class TestTheCityDistributionRoundsHalfUp:
    async def test_every_temperature_bucket_matches_the_contract(
        self, client, mock_db
    ):
        """The city panel rounds each bucket separately, in its own loop — a
        third call site that had its own copy of `round(p * 100)`."""
        _serve(mock_db, [
            _market(
                market_id=59803955,
                name=f"Highest temperature in Los Angeles on {_soon()}?",
                outcomes=[
                    _outcome("86°F", 0.125, outcome_id=1),
                    _outcome("87°F", 0.445, outcome_id=2),
                    _outcome("88°F", 0.325, outcome_id=3),
                    _outcome("89°F or higher", 0.105, outcome_id=4),
                ],
            )
        ])

        city = (await client.get("/api/weather/cities")).json()[0]
        dist = {d["label"]: d["prob"] for d in city["high"]["dist"]}

        # All four sit on a `.5`; banker's printed 12 / 44 / 32 / 10.
        assert dist == {
            "86°F": 13,
            "87°F": 45,
            "88°F": 33,
            "89°F or higher": 11,
        }

    async def test_a_live_price_stops_printing_a_flat_zero(self, client, mock_db):
        """Four buckets on the deployed page are priced 0.005 and print `0%`.
        To a reader `0%` does not mean unlikely, it means IMPOSSIBLE — printed
        over a price the market is actively quoting. Half-up prints 1%.

        This is not a special case in the code: it falls out of the same rule.
        A genuinely negligible price still prints 0, which is why the second
        assertion is here.
        """
        _serve(mock_db, [
            _market(
                market_id=59803982,
                name=f"Highest temperature in Chicago on {_soon()}?",
                outcomes=[
                    _outcome("75°F or below", 0.005, outcome_id=1),
                    _outcome("76°F", 0.0004, outcome_id=2),
                    _outcome("77°F", 0.9946, outcome_id=3),
                ],
            )
        ])

        city = (await client.get("/api/weather/cities")).json()[0]
        dist = {d["label"]: d["prob"] for d in city["high"]["dist"]}

        assert dist["75°F or below"] == 1, "a quoted price is not zero"
        assert dist["76°F"] == 0, "0.04% really does round to nothing"


class TestTheRainCardRoundsHalfUp:
    async def test_the_yes_leg_matches_the_contract(self, client, mock_db):
        _serve(mock_db, [
            _market(
                market_id=59704000,
                name=f"Will it rain in NYC on {_soon()}?",
                outcomes=[
                    _outcome("Yes", 0.635, outcome_id=1),
                    _outcome("No", 0.365, outcome_id=2),
                ],
            )
        ])

        body = (await client.get("/api/weather/rain")).json()

        assert body["daily"][0]["prob"] == 64, "0.635 half-up; banker's printed 63"

    async def test_both_branches_of_the_yes_lookup_agree(self, client, mock_db):
        """`_yes_probability` has a named-"Yes" branch and a highest-outcome
        fallback. They must round by the same rule, or the rain card prints a
        different number for the same price depending on whether the market
        happened to label its leg "Yes"."""
        priced = 0.635

        _serve(mock_db, [
            _market(
                market_id=1,
                name=f"Will it rain in NYC on {_soon()}?",
                outcomes=[
                    _outcome("Yes", priced, outcome_id=1),
                    _outcome("No", 0.365, outcome_id=2),
                ],
            )
        ])
        named = (await client.get("/api/weather/rain")).json()["daily"][0]["prob"]

        _serve(mock_db, [
            _market(
                market_id=2,
                name=f"Will it rain in NYC on {_soon()}?",
                outcomes=[
                    # No leg called "Yes" anywhere — the fallback path.
                    _outcome("Rain recorded", priced, outcome_id=3),
                    _outcome("Dry", 0.365, outcome_id=4),
                ],
            )
        ])
        fallback = (await client.get("/api/weather/rain")).json()["daily"][0]["prob"]

        assert named == fallback == rendered_percent(priced) == 64


# ═══ 3 · the rule cannot come back ═══════════════════════════════════════════


class TestTheOpenCodedRoundingIsGone:
    """A route test proves the number is right TODAY. It stays green when
    someone adds a fifth call site with a fresh `round(p * 100)` in it, because
    no test drives that surface yet. Three copies of this expression already
    existed in one file; the guard that matters is the source scan.
    """

    SOURCE = (
        Path(__file__).resolve().parents[2] / "app" / "routes" / "weather.py"
    ).read_text(encoding="utf-8")

    # Docstrings and comments stripped, because a source-grepping guard hits
    # PROSE ABOUT the code as readily as the code: `_highest_prob`'s new
    # docstring quotes the very expression this scan bans, in the sentence
    # explaining why it was removed, and the first run of this test failed on
    # it. The scan is a claim about what executes.
    CODE = re.sub(
        r"(?m)#.*$",
        "",
        re.sub(r"'''.*?'''", "", re.sub(r'""".*?"""', "", SOURCE, flags=re.S), flags=re.S),
    )

    def test_no_probability_is_rounded_with_the_builtin(self):
        # `round(<anything> * 100)` with no `ndigits` — the shape all three call
        # sites shared. Deliberately does NOT match `round(x, 1)` (the delta and
        # unit-conversion helpers, which are not whole-percent decisions) and
        # does not match `rendered_percent(...)`.
        offenders = re.findall(r"[^_\w]round\([^)]*\*\s*100\s*\)", self.CODE)
        assert offenders == [], (
            "weather.py is rounding a probability with Python's banker's "
            f"round() again: {offenders}"
        )

    def test_the_route_actually_imports_the_contract(self):
        """Vacuity companion. Without this, deleting every percentage from the
        file would satisfy the scan above."""
        assert "from app.utils.graded_card import rendered_percent" in self.SOURCE
        # UX-P192 collapsed the three separate `rendered_percent(...)` calls into
        # ONE — `_printed`, which emits the integer and the value it came from as
        # a pair so the two cannot describe different outcomes. So the count that
        # means "every printed number goes through the contract" moved with it:
        # it is now the number of payload shapes calling `_printed`, not the
        # number of places calling `rendered_percent`.
        assert self.CODE.count("rendered_percent(") >= 1, "the one home still calls it"
        assert self.CODE.count("_printed(") >= 7, (
            "every weather payload shape must build its number through `_printed`: "
            f"found {self.CODE.count('_printed(')}"
        )
