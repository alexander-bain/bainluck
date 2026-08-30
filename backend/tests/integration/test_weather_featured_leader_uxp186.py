"""UX-P186 — the weather page's featured number names the outcome it belongs to.

`/api/weather/featured` and `/api/weather/wildcards` printed `_highest_prob(m)`
and nothing else. That is a complete answer under a binary question and no
answer at all under a multi-outcome one.

Measured on production 2026-08-30, ALL FIVE markets the hero rotates were
multi-outcome, so the biggest number on the weather page never had a referent:

    Where will it rain on Aug 29, 2026?              78%   (Minneapolis, of 22)
    Exceptional drought (D4) by state — week of ...  98%   (Colorado, of 42)
    Highest temperature in Los Angeles on August 31? 45%   (78-79°F, of 11)
    Highest temperature in Jeddah on August 31?      31%   (39°C, of 11)
    Highest temperature in Beijing on August 31?     30%   (30°C, of 11)

That is not an accident of the day's data. The featured scorer is
``len(m.outcomes) / days`` — it RANKS BY OUTCOME COUNT, so it structurally
prefers exactly the markets whose bare number is least legible, and a binary
market can hardly ever reach the hero at all.

The wildcards rail carried the same defect with a sharper edge: "Major volcano
eruption in 2026?" showed 68%, which is the price of the outcome "At least 2" —
not the probability of an eruption happening, which is what the card reads as.

Every test here drives the real route through the real FastAPI app. Nothing
rebuilds the payload by hand: a guard that re-derives what it checks cannot see
the render stop emitting it.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — the same shapes tests/integration/test_route_weather.py uses.
# ---------------------------------------------------------------------------


def _outcome(name, probability, *, outcome_id=1):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=None,
        rank=1,
    )


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


# The Aug 29 rain market exactly as production held it, trimmed to the rows that
# decide the leader plus enough tail to keep it multi-outcome. Minneapolis at
# 0.785 is the real top price; New York City at 0.045 is the real bottom of the
# leaderboard and is here so a mutation that grabs `outcomes[0]` or `[-1]` bites.
_RAIN_OUTCOMES = [
    _outcome("Seattle", 0.740, outcome_id=1),
    _outcome("Minneapolis", 0.785, outcome_id=2),
    _outcome("Miami", 0.720, outcome_id=3),
    _outcome("New York City", 0.045, outcome_id=4),
]

# "Major volcano eruption in 2026?" — the wildcards case. The question reads
# binary; the 68% is the price of "At least 2".
_VOLCANO_OUTCOMES = [
    _outcome("At least 1", 0.110, outcome_id=11),
    _outcome("At least 2", 0.680, outcome_id=12),
    _outcome("At least 3", 0.230, outcome_id=13),
]


# ---------------------------------------------------------------------------
# 1. The ship
# ---------------------------------------------------------------------------


class TestFeaturedNamesItsOutcome:
    async def test_the_hero_says_which_city(self, client, mock_db):
        """The defect, fixed: 78% under "Where will it rain?" is Minneapolis."""
        _serve(mock_db, [
            _market(
                market_id=59704867,
                name="Where will it rain on Aug 29, 2026?",
                outcomes=_RAIN_OUTCOMES,
            )
        ])

        body = (await client.get("/api/weather/featured")).json()

        assert len(body) == 1
        assert body[0]["prob"] == 78
        assert body[0]["leader"] == "Minneapolis"

    async def test_the_hero_says_which_temperature_band(self, client, mock_db):
        """A number whose referent is not a place but a bucket."""
        _serve(mock_db, [
            _market(
                market_id=59746940,
                name="Highest temperature in Los Angeles on August 31?",
                outcomes=[
                    _outcome("76-77°F", 0.205, outcome_id=21),
                    _outcome("78-79°F", 0.450, outcome_id=22),
                    _outcome("80-81°F", 0.280, outcome_id=23),
                ],
            )
        ])

        body = (await client.get("/api/weather/featured")).json()

        assert body[0]["prob"] == 45
        assert body[0]["leader"] == "78-79°F"

    async def test_the_hurricane_rail_says_which_category(self, client, mock_db):
        """The sharpest case on the page, and the one an outcome-COUNT rule
        would have missed.

        "Hurricane Karina category? — 94%" is the price of "Category 1 or
        above". The same card reads as "94% likely to be a hurricane" when the
        question names no category at all, and Karina's own ladder puts
        "Category 4 or above" at 32% and "Category 5 or above" at 9%.

        These are the real rows, 2026-08-30. 39 of the 40 open two-outcome
        weather markets are hurricane-category pairs, so a `len(outcomes) <= 2`
        cutoff would have suppressed the name across almost the entire
        population that needs it most.
        """
        _serve(mock_db, [
            _market(
                market_id=59600001,
                name="Hurricane Karina category?",
                outcomes=[
                    _outcome("Category 1 or above", 0.940, outcome_id=61),
                    _outcome("Category 2 or above", 0.890, outcome_id=62),
                    _outcome("Category 3 or above", 0.715, outcome_id=63),
                    _outcome("Category 4 or above", 0.320, outcome_id=64),
                    _outcome("Category 5 or above", 0.090, outcome_id=65),
                ],
            )
        ])

        body = (await client.get("/api/weather/events")).json()

        assert len(body["hurricane"]) == 1
        assert body["hurricane"][0]["prob"] == 94
        assert body["hurricane"][0]["leader"] == "Category 1 or above"

    async def test_a_cumulative_ladder_tied_at_the_top_names_one_of_them(
        self, client, mock_db
    ):
        """Real, and worth stating plainly rather than discovering later.

        "Hurricane Marie category?" prices "Category 2 or above" and "Category 1
        or above" at 95.0 BOTH — a genuine tie for first, live on 2026-08-30.
        Cumulative ladders do this whenever the lower rungs are already certain.

        Which name is printed is therefore decided by row order, not by price.
        That is arbitrary, but it is not WRONG: at a tie both statements are
        true at the same number, and either is strictly more informative than
        the bare 95% that shipped before. What must not happen is the name and
        the number coming from different rows — that is `_highest_prob`'s tie
        rule, mirrored, and asserted in `TestTheNamedLeaderIsThePrintedNumber`.
        """
        _serve(mock_db, [
            _market(
                market_id=59600002,
                name="Hurricane Marie category?",
                outcomes=[
                    _outcome("Category 2 or above", 0.95, outcome_id=66),
                    _outcome("Category 1 or above", 0.95, outcome_id=67),
                ],
            )
        ])

        row = (await client.get("/api/weather/events")).json()["hurricane"][0]

        assert row["prob"] == 95
        assert row["leader"] == "Category 2 or above", "first of the tie"

    async def test_a_one_character_leader_is_still_named(self, client, mock_db):
        """The question-echo refusal must not eat a digit out of a year.

        "How many large volcano eruptions (VEI >=4) in 2026?" is priced across
        the outcomes "0", "1", "2" and "4" — the leader is "0" at 71.5%, and
        "0" appears inside "2026". A substring test suppresses the one word that
        makes the 72% mean anything ("no eruptions", not "an eruption"). The
        refusal matches whole tokens for exactly this reason.
        """
        _serve(mock_db, [
            _market(
                market_id=59500002,
                name="How many large volcano eruptions (VEI >=4) in 2026?",
                outcomes=[
                    _outcome("0", 0.715, outcome_id=101),
                    _outcome("1", 0.205, outcome_id=102),
                    _outcome("2", 0.034, outcome_id=103),
                    _outcome("4", 0.013, outcome_id=104),
                ],
            )
        ])

        item = (await client.get("/api/weather/wildcards")).json()[0]

        assert item["prob"] == 72
        assert item["leader"] == "0"

    async def test_the_wildcard_rail_says_at_least_2(self, client, mock_db):
        """The card reads as a yes/no. The 68% is the price of "At least 2"."""
        _serve(mock_db, [
            _market(
                market_id=59500001,
                name="Major volcano eruption in 2026?",
                outcomes=_VOLCANO_OUTCOMES,
            )
        ])

        body = (await client.get("/api/weather/wildcards")).json()

        assert len(body) == 1
        assert body[0]["prob"] == 68
        assert body[0]["leader"] == "At least 2"


# ---------------------------------------------------------------------------
# 2. Where naming would be noise
# ---------------------------------------------------------------------------


class TestNothingWorthNaming:
    @pytest.mark.parametrize("endpoint", ["featured", "wildcards"])
    async def test_a_yes_no_market_names_nothing(self, client, mock_db, endpoint):
        """"Will a volcano erupt in Florida? — 72% Yes" adds a word and no
        information. The question already carries its own answer."""
        _serve(mock_db, [
            _market(
                market_id=42,
                name="Will a volcano erupt in Florida?",
                outcomes=[
                    _outcome("Yes", 0.72, outcome_id=31),
                    _outcome("No", 0.28, outcome_id=32),
                ],
            )
        ])

        body = (await client.get(f"/api/weather/{endpoint}")).json()

        assert body[0]["prob"] == 72
        assert body[0]["leader"] is None

    async def test_a_leader_already_spelled_out_in_the_question_is_not_repeated(
        self, client, mock_db
    ):
        """Printing the same words twice in two type sizes is not an answer."""
        _serve(mock_db, [
            _market(
                market_id=46,
                name="Will Tropical Storm Lowell strengthen to a hurricane?",
                outcomes=[
                    _outcome("Tropical Storm Lowell strengthen to a hurricane", 0.88, outcome_id=71),
                    _outcome("Stays a tropical storm", 0.10, outcome_id=72),
                    _outcome("Dissipates", 0.02, outcome_id=73),
                ],
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        assert item["prob"] == 88
        assert item["leader"] is None

    async def test_an_unpriced_market_names_nothing(self, client, mock_db):
        """SYNTHETIC — no weather market in production has every outcome at
        zero (measured 2026-08-30: 0 rows of 40 two-outcome + all others). The
        branch is still reachable the moment a provider stops quoting one, and a
        guard that only covers today's population is not a guard. With no priced
        outcome there is no leader, and `_highest_prob` prints 0."""
        _serve(mock_db, [
            _market(
                market_id=47,
                name="Which city gets the most snow in Jan 2027?",
                outcomes=[
                    _outcome("Buffalo", None, outcome_id=81),
                    _outcome("Denver", 0.0, outcome_id=82),
                    _outcome("Chicago", None, outcome_id=83),
                ],
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        assert item["prob"] == 0
        assert item["leader"] is None

    async def test_a_single_outcome_market_names_nothing(self, client, mock_db):
        """Production carries these — "Will a supervolcano erupt before 2050?"
        has exactly one priced outcome, named "Yes".

        Note it is the NAME that disqualifies it, not the count of one. A
        single-outcome market whose outcome is called something real would be
        named, and should be."""
        _serve(mock_db, [
            _market(
                market_id=43,
                name="Will a supervolcano erupt before 2050?",
                outcomes=[_outcome("Yes", 0.267, outcome_id=41)],
            )
        ])

        body = (await client.get("/api/weather/wildcards")).json()

        assert body[0]["leader"] is None

    async def test_a_yes_no_leader_on_a_MULTI_outcome_market_is_not_named(
        self, client, mock_db
    ):
        """The ``<= 2`` arm does NOT already cover this, and production proves it.

        "Exceptional drought (D4) by state — week of September 1, 2026" carries
        42 outcomes: forty states, plus a bare "No" at 92.5% and a bare "Yes" at
        7.5% that the provider mixed into the same market. Colorado at 98.0
        happens to outrank the "No" today, so the card is fine — but one week of
        drought easing puts "No" on top, and the hero would announce a forty-
        state question with the single word "No". A name that restates the
        question's own framing is never worth printing, however many outcomes
        sit beside it.
        """
        _serve(mock_db, [
            _market(
                market_id=59646564,
                name="Exceptional drought (D4) by state — week of September 1, 2026",
                outcomes=[
                    _outcome("No", 0.925, outcome_id=91),
                    _outcome("Colorado", 0.900, outcome_id=92),
                    _outcome("Oklahoma", 0.879, outcome_id=93),
                    _outcome("Yes", 0.075, outcome_id=94),
                ],
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        # 92, not 93: `_highest_prob` is Python `round()`, which is HALF-EVEN,
        # while the site's rendered-percent convention is HALF-UP. Out of scope
        # here — this test is about the name — but real, and parked as UX-P186-2.
        assert item["prob"] == 92, "the number is still the leader's"
        assert item["leader"] is None

    async def test_a_placeholder_leader_is_not_named(self, client, mock_db):
        """`_GARBAGE_OUTCOME_RE`'s population, reused rather than re-listed. The
        cross-source rail already refuses to print these names; the hero must
        not be the one surface that does."""
        _serve(mock_db, [
            _market(
                market_id=44,
                name="Which candidate wins the weather bet?",
                outcomes=[
                    _outcome("Candidate A", 0.55, outcome_id=51),
                    _outcome("Candidate B", 0.30, outcome_id=52),
                    _outcome("Candidate C", 0.15, outcome_id=53),
                ],
            )
        ])

        body = (await client.get("/api/weather/featured")).json()

        assert body[0]["prob"] == 55
        assert body[0]["leader"] is None

    async def test_the_key_is_always_present_even_when_null(self, client, mock_db):
        """An ABSENT key and a null one are different facts to the reader.

        Absent means "this payload predates the field" — which the hourly Redis
        cache really does serve for up to an hour after a deploy. Null means "we
        looked and there is nothing worth naming". The route must always emit
        the key so the two stay distinguishable; the frontend degrades either
        way, but only one of them is a bug."""
        _serve(mock_db, [
            _market(
                market_id=45,
                name="Will it rain in NYC?",
                outcomes=[
                    _outcome("Yes", 0.6, outcome_id=61),
                    _outcome("No", 0.4, outcome_id=62),
                ],
            )
        ])

        body = (await client.get("/api/weather/featured")).json()

        assert "leader" in body[0]


# ---------------------------------------------------------------------------
# 3. The coupling property — the guard that stops the two scans drifting
# ---------------------------------------------------------------------------


class TestTheNamedLeaderIsThePrintedNumber:
    """`_highest_prob` and `_leader_outcome_name` are two separate scans over
    the same outcomes. Nothing in the type system stops one from picking a
    different row than the other — and if they ever disagree, the card prints a
    number attached to the wrong name, which is strictly worse than printing no
    name at all. This is the containment property, asserted rather than argued.
    """

    @pytest.mark.parametrize("endpoint", ["featured", "wildcards"])
    @pytest.mark.parametrize(
        "name,outcomes",
        [
            ("Where will it rain on Aug 29, 2026?", _RAIN_OUTCOMES),
            ("Major volcano eruption in 2026?", _VOLCANO_OUTCOMES),
            (
                "Min Arctic sea ice extent this summer?",
                # The near-flat ladder: the top four sit within 1.2 points, so
                # any scan that is even slightly different picks a different row.
                [
                    _outcome("4.2-4.4m sq km", 0.161, outcome_id=71),
                    _outcome("4.0-4.2m sq km", 0.164, outcome_id=72),
                    _outcome("<4m sq km", 0.160, outcome_id=73),
                    _outcome("4.4-4.6m sq km", 0.152, outcome_id=74),
                ],
            ),
        ],
    )
    async def test_the_named_leader_is_the_outcome_whose_number_is_printed(
        self, client, mock_db, endpoint, name, outcomes
    ):
        _serve(mock_db, [_market(market_id=99, name=name, outcomes=outcomes)])

        item = (await client.get(f"/api/weather/{endpoint}")).json()[0]

        assert item["leader"] is not None, "these are all multi-outcome"
        named = next(o for o in outcomes if o.name == item["leader"])
        assert round(named.current_probability * 100) == item["prob"]
        assert named.current_probability == max(
            o.current_probability for o in outcomes
        )

    async def test_a_tie_below_the_top_does_not_move_the_leader(self, client, mock_db):
        """Beijing really is tied in production — 29°C and 31°C are both 25.0,
        under 30°C at 30.5. A tie that is not for first place decides nothing."""
        _serve(mock_db, [
            _market(
                market_id=59731168,
                name="Highest temperature in Beijing on August 31?",
                outcomes=[
                    _outcome("29°C", 0.250, outcome_id=81),
                    _outcome("31°C", 0.250, outcome_id=82),
                    _outcome("30°C", 0.305, outcome_id=83),
                    _outcome("28°C", 0.060, outcome_id=84),
                ],
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        assert item["leader"] == "30°C"
        assert item["prob"] == 30

    async def test_a_tie_FOR_THE_TOP_resolves_the_same_way_in_both_scans(
        self, client, mock_db
    ):
        """The case the coupling test above cannot see.

        When two outcomes tie for first, both scans print the SAME number, so an
        assertion that only checks ``round(pct) == prob`` passes whichever row
        each one picked. Only the NAME distinguishes them. ``_highest_prob``
        keeps the first strict maximum, so ``_leader_outcome_name`` must too:
        flipping its comparison to ``>=`` would name 31°C while the number still
        came from 29°C, and nothing else in this file would notice.
        """
        _serve(mock_db, [
            _market(
                market_id=59731169,
                name="Highest temperature in Beijing on September 1?",
                outcomes=[
                    _outcome("29°C", 0.250, outcome_id=85),
                    _outcome("31°C", 0.250, outcome_id=86),
                    _outcome("28°C", 0.060, outcome_id=87),
                ],
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        assert item["prob"] == 25
        assert item["leader"] == "29°C", "first of a tie, exactly as _highest_prob"


# ---------------------------------------------------------------------------
# 4. Nothing else moved
# ---------------------------------------------------------------------------


class TestNothingElseChanged:
    @pytest.mark.parametrize("endpoint", ["featured", "wildcards"])
    async def test_every_other_field_is_untouched(self, client, mock_db, endpoint):
        """`leader` is additive. If this diff moved `prob`, `q`, `tag`, `src` or
        `closes` for any market, it stopped being the change it claims to be."""
        now = datetime.now(timezone.utc)
        _serve(mock_db, [
            _market(
                market_id=59704867,
                name="Where will it rain on Aug 29, 2026?",
                outcomes=_RAIN_OUTCOMES,
                source="kalshi",
                resolution_date=now + timedelta(days=2),
            )
        ])

        item = (await client.get(f"/api/weather/{endpoint}")).json()[0]

        assert item["q"] == "Where will it rain on Aug 29, 2026?"
        assert item["prob"] == 78
        assert item["src"] == "kalshi"
        assert item["tag"] == "Daily rain"
        assert item["closes"] == (now + timedelta(days=2)).strftime(
            "%a, %b %d"
        ).replace(" 0", " ")

    async def test_the_featured_payload_gained_exactly_one_key(self, client, mock_db):
        """The whole diff, stated as a set difference."""
        _serve(mock_db, [
            _market(
                market_id=59704867,
                name="Where will it rain on Aug 29, 2026?",
                outcomes=_RAIN_OUTCOMES,
            )
        ])

        item = (await client.get("/api/weather/featured")).json()[0]

        assert set(item) == {
            "q", "prob", "src", "tag", "closes", "market_id", "leader",
        }
