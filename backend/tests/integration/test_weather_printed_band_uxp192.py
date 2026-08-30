"""UX-P192 — a live price on `/weather` stops printing as impossible.

UX-P191 fixed WHICH integer this route rounds to. This is about what the integer
cannot say.

`rendered_percent` is lossy exactly where it matters most. A temperature bucket
quoted at 0.0015 renders to `0`, and the weather page printed that `0` raw. `0%`
does not read as "unlikely" to anyone; it reads as **impossible** — printed over
a price a market is actively making, on the one surface whose entire job is to
print prices. The rest of the product has had the answer since UX-P046
(`formatProbabilityPercent` on web, `formatProbability` on native): a value
strictly inside (0, 1) may never print as `0%` or `100%`. `/weather` was the one
surface that never adopted it, and it could not have: **the wire carried only the
rounded integer, and an integer cannot be un-rounded.**

So the ship is the pair. Every weather number now travels as `prob` (the integer
the server decided) plus `probability` (the value it was decided from), built
together by `_printed` so they cannot come to describe different outcomes.

═══ THE READER COUNT ═══

Measured on production 2026-08-30, banked in
`backend/tests/fixtures/uxp192_printed_band.json`:

  POPULATION — one atomic query over every outcome the route can reach:

      444  open weather markets
    2,663  priced outcomes
      288  strictly inside (0, 1) and rendering to 0
       21  strictly below 1 and rendering to 100
        0  exact zeros
        0  unpriced

  The last two lines are the ship. **There is no honest `0%` on this page.**

  SERVED — the six payloads a reader's page is built from:

      571  numbers
      130  printing `0%`   (22.8% of the page)

Los Angeles, market 59803955, on the served `/cities` payload: four of its eleven
temperature buckets printed `0%`, priced 0.0015, 0.003, 0.003 and 0.0015. The
market's own favourite is 43.5%. A reader saw four impossibilities in a
distribution that has none.

═══ WHY THE CENSUS IS ONE QUERY ═══

The first pass took the two interior counts thirty minutes apart and got 281 and
288 for the same population. Weather prices are polled every two minutes. A
census assembled from separate queries is not a census, and UX-P191 banked the
neighbouring version of this lesson (a `.5` in Postgres numeric is not a `.5`
after `float(p) * 100`). Both are the same rule: **say which measurement you are
quoting, and take it in one breath.**

    python3 -m pytest tests/integration/test_weather_printed_band_uxp192.py -v
"""

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.utils.graded_card import rendered_percent

# No `pytestmark`: pytest.ini runs asyncio in AUTO mode, and a blanket mark warns
# on every sync test in the file.

FIXTURE = json.loads(
    (
        Path(__file__).resolve().parents[1] / "fixtures" / "uxp192_printed_band.json"
    ).read_text(encoding="utf-8")
)
POPULATION = FIXTURE["population"]
SERVED = FIXTURE["served"]
SPECIMENS = FIXTURE["specimens"]


# ---------------------------------------------------------------------------
# Helpers — the same shapes UX-P191's file uses.
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
    """A date label a week out, OFFSET FIRST then formatted (gotcha #44).

    A hard-coded date in a market NAME is a clock branch in disguise:
    `is_title_implied_stale` reads these titles and drops a market whose title
    says it is over. UX-P191 lost two tests to exactly that.
    """
    d = datetime.now(timezone.utc) + timedelta(days=7)
    return f"{d:%b} {d.day}, {d.year}"


def _market(*, market_id=1, name, outcomes, source="polymarket", resolution_date=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=f"px{market_id}",
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


def _specimen(city):
    return next(s for s in SPECIMENS if s["city"] == city)


def _specimen_market(city, *, name=None):
    spec = _specimen(city)
    return _market(
        market_id=spec["market_id"],
        name=name or spec["name"],
        source=spec["source"],
        outcomes=[
            _outcome(o["label"], o["probability"], outcome_id=1000 + i)
            for i, o in enumerate(spec["outcomes"])
        ],
    )


def _all_prob_pairs(payload):
    """Every `(prob, probability)` pair anywhere in a weather payload.

    Walks the whole structure rather than naming paths, so a shape that ships a
    number the author of this test did not think of is still covered — which is
    the failure mode the whole queue is about (`/weather` was the surface nobody
    remembered when `formatProbabilityPercent` was adopted everywhere else).
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            if "prob" in node:
                found.append((node["prob"], node.get("probability", "__missing__")))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return found


# ═══ 1 · the banked state is genuinely broken, and the instrument works ══════


class TestTheBankedStateIsGenuinelyBroken:
    def test_the_census_is_the_one_the_docstring_quotes(self):
        assert POPULATION == {
            "markets": 444,
            "priced_outcomes": 2663,
            "interior_prints_zero": 288,
            "interior_prints_hundred": 21,
            "exact_zero": 0,
            "unpriced": 0,
            "exact_one": 3,
        }

    def test_there_is_no_honest_zero_in_the_population(self):
        """The claim the whole ship rests on, stated as its own assertion.

        If `exact_zero` were nonzero, some of the 130 served zeros would be
        correct and the fix would need a way to tell the two apart. It is zero,
        so it does not.
        """
        assert POPULATION["exact_zero"] == 0
        assert POPULATION["unpriced"] == 0
        assert POPULATION["interior_prints_zero"] > 0, "and the defect is real"

    def test_the_served_totals_add_up(self):
        """A per-endpoint table whose total is typed by hand is a table that can
        disagree with itself."""
        total = SERVED["total"]
        for key in ("numbers", "zeros", "hundreds"):
            assert total[key] == sum(
                v[key] for k, v in SERVED.items() if k != "total"
            ), key
        assert total["zeros"] > 0

    def test_the_upper_arm_is_marked_as_unexercised_on_the_served_page(self):
        """Honesty about what was MEASURED versus what was reasoned about.

        No served number was 100 on the day of measurement, so the `>99%` arm
        ships on population evidence rather than page evidence. If a later
        measurement ever finds one, this assertion is the place that has to be
        re-read rather than a sentence in a report nobody opens.
        """
        assert SERVED["total"]["hundreds"] == 0
        assert POPULATION["interior_prints_hundred"] > 0

    def test_every_specimen_row_was_computed_rather_than_asserted(self):
        """The fixture's `before` / `after` strings are derivable, so derive
        them. UX-P191's own guard was written in the defect's arithmetic and
        agreed with the bug; a fixture asserted by hand can do the same."""
        for spec in SPECIMENS:
            for o in spec["outcomes"]:
                p = o["probability"]
                integer = rendered_percent(p)
                assert o["before"] == f"{integer}%", (spec["city"], o)
                if integer <= 0 and p > 0:
                    expected = "<1%"
                elif integer >= 100 and p < 1:
                    expected = ">99%"
                else:
                    expected = f"{integer}%"
                assert o["after"] == expected, (spec["city"], o)

    def test_the_specimens_contain_both_a_defect_and_a_control(self):
        """A specimen with no unchanged rows cannot prove the fix is narrow."""
        for spec in SPECIMENS:
            changed = [o for o in spec["outcomes"] if o["before"] != o["after"]]
            same = [o for o in spec["outcomes"] if o["before"] == o["after"]]
            assert len(changed) >= 2, spec["city"]
            assert len(same) >= 5, spec["city"]


# ═══ 2 · the wire carries the pair, on every shape ═══════════════════════════


class TestEveryPayloadShipsThePair:
    """`prob` alone is unprintable. Seven payload shapes; all seven, or the one
    that was missed is the one a reader is looking at."""

    async def test_featured(self, client, mock_db):
        _serve(mock_db, [_specimen_market("Los Angeles")])
        item = (await client.get("/api/weather/featured")).json()[0]
        assert item["probability"] == 0.435
        assert item["prob"] == 44

    async def test_every_city_bucket(self, client, mock_db):
        _serve(mock_db, [_specimen_market("Los Angeles")])
        city = (await client.get("/api/weather/cities")).json()[0]
        buckets = {b["label"]: b for b in city["high"]["dist"]}
        assert len(buckets) == 11
        for o in _specimen("Los Angeles")["outcomes"]:
            assert buckets[o["label"]]["probability"] == o["probability"], o["label"]

    async def test_rain_daily_and_monthly(self, client, mock_db):
        _serve(
            mock_db,
            [
                _market(
                    market_id=1,
                    name=f"Will it rain in NYC on {_soon()}?",
                    outcomes=[_outcome("Yes", 0.003, outcome_id=1),
                              _outcome("No", 0.997, outcome_id=2)],
                ),
                _market(
                    market_id=2,
                    name="Rain in Denver in Dec 2026?",
                    outcomes=[_outcome("Yes", 0.0015, outcome_id=3),
                              _outcome("No", 0.9985, outcome_id=4)],
                ),
            ],
        )
        body = (await client.get("/api/weather/rain")).json()
        assert body["daily"][0]["probability"] == 0.003
        assert body["daily"][0]["prob"] == 0
        # By city, not by index: the mocked db returns BOTH markets to BOTH
        # queries (a `SimpleNamespace` result cannot honour a WHERE clause), so
        # the monthly list also carries a row derived from the daily market and
        # the sort order is not the assertion's business.
        denver = next(m for m in body["monthly"] if m["city"] == "Denver")
        assert denver["probability"] == 0.0015
        assert denver["prob"] == 0

    async def test_events(self, client, mock_db):
        _serve(
            mock_db,
            [
                _market(
                    market_id=3,
                    name="Will a hurricane make landfall in Florida?",
                    outcomes=[_outcome("Yes", 0.0025, outcome_id=5)],
                )
            ],
        )
        item = (await client.get("/api/weather/events")).json()["hurricane"][0]
        assert item["probability"] == 0.0025
        assert item["prob"] == 0

    async def test_climate(self, client, mock_db):
        _serve(
            mock_db,
            [
                _market(
                    market_id=4,
                    name="Hottest year on record by 2050?",
                    outcomes=[_outcome("Yes", 0.995, outcome_id=6)],
                )
            ],
        )
        item = (await client.get("/api/weather/climate")).json()[0]
        assert item["probability"] == 0.995
        assert item["prob"] == 100

    async def test_wildcards(self, client, mock_db):
        _serve(
            mock_db,
            [
                _market(
                    market_id=5,
                    name="Will a supervolcano erupt before 2050?",
                    outcomes=[_outcome("Yes", 0.0005, outcome_id=7)],
                )
            ],
        )
        item = (await client.get("/api/weather/wildcards")).json()[0]
        assert item["probability"] == 0.0005
        assert item["prob"] == 0

    async def test_no_shape_anywhere_ships_prob_without_probability(
        self, client, mock_db
    ):
        """The generalised version of the six above.

        Walks every payload for a key named `prob` and demands its partner. A
        seventh shape added later is covered by this without anyone remembering
        to extend the list — and forgetting a surface is precisely how this page
        came to be the only one without the band.
        """
        markets = [
            _specimen_market("Los Angeles"),
            _specimen_market("Beijing", name="Highest temperature in Beijing on Sep 1?"),
            _market(
                market_id=10,
                name=f"Will it rain in NYC on {_soon()}?",
                outcomes=[_outcome("Yes", 0.42, outcome_id=20)],
            ),
            _market(
                market_id=11,
                name="Rain in Denver in Dec 2026?",
                outcomes=[_outcome("Yes", 0.31, outcome_id=21)],
            ),
            _market(
                market_id=12,
                name="Will a hurricane make landfall in Florida?",
                outcomes=[_outcome("Yes", 0.62, outcome_id=22)],
            ),
            _market(
                market_id=13,
                name="Hottest year on record by 2050?",
                outcomes=[_outcome("Yes", 0.77, outcome_id=23)],
            ),
            _market(
                market_id=14,
                name="Will a supervolcano erupt before 2050?",
                outcomes=[_outcome("Yes", 0.02, outcome_id=24)],
            ),
        ]

        seen = 0
        for endpoint in ("featured", "cities", "rain", "events", "climate", "wildcards"):
            _serve(mock_db, markets)
            body = (await client.get(f"/api/weather/{endpoint}")).json()
            pairs = _all_prob_pairs(body)
            for prob, probability in pairs:
                assert probability != "__missing__", (
                    f"/{endpoint} ships a `prob` with no `probability`; "
                    "the client cannot print `<1%` from an integer"
                )
                assert rendered_percent(probability) == prob, (
                    f"/{endpoint}: {probability} does not render to {prob} — the "
                    "pair has come to describe different outcomes"
                )
            seen += len(pairs)

        # Vacuity companion: a walker that found nothing would pass every
        # assertion above (#53 — an absent signal read as a clean one).
        assert seen >= 40, f"only {seen} numbers walked; the scan is not reaching them"


# ═══ 3 · the number itself is unchanged where it must be ═════════════════════


class TestTheIntegerDidNotMove:
    """The control that matters more than the fix.

    Adding `probability` must not perturb a single served integer. If a bucket
    nowhere near a boundary moved, this was not an adoption of the band — it was
    a change to the rounding, and the claim in the docstring is false.
    """

    async def test_every_specimen_integer_is_byte_identical(self, client, mock_db):
        for city in ("Los Angeles", "Beijing"):
            _serve(mock_db, [_specimen_market(city)])
            served = (await client.get("/api/weather/cities")).json()[0]
            buckets = {b["label"]: b["prob"] for b in served["high"]["dist"]}
            for o in _specimen(city)["outcomes"]:
                assert buckets[o["label"]] == int(o["before"].rstrip("%")), (
                    city,
                    o["label"],
                )

    async def test_the_leader_integer_is_unchanged(self, client, mock_db):
        """`_highest_prob` was refactored onto `_leader_probability`. Same
        answer, including its first-of-a-tie behaviour."""
        _serve(
            mock_db,
            [
                _market(
                    market_id=1,
                    name="Where will it rain tomorrow?",
                    outcomes=[
                        _outcome("Minneapolis", 0.29, outcome_id=1),
                        _outcome("Chicago", 0.29, outcome_id=2),
                        _outcome("Denver", 0.11, outcome_id=3),
                    ],
                )
            ],
        )
        item = (await client.get("/api/weather/events")).json()
        _serve(
            mock_db,
            [
                _market(
                    market_id=1,
                    name="Where will it rain tomorrow?",
                    outcomes=[
                        _outcome("Minneapolis", 0.29, outcome_id=1),
                        _outcome("Chicago", 0.29, outcome_id=2),
                        _outcome("Denver", 0.11, outcome_id=3),
                    ],
                )
            ],
        )
        wild = (await client.get("/api/weather/climate")).json()
        del item, wild  # both routes exercised; the assertion is the next line
        _serve(
            mock_db,
            [
                _market(
                    market_id=1,
                    name="Where will it rain tomorrow?",
                    outcomes=[
                        _outcome("Minneapolis", 0.29, outcome_id=1),
                        _outcome("Chicago", 0.29, outcome_id=2),
                    ],
                )
            ],
        )
        featured = (await client.get("/api/weather/featured")).json()[0]
        assert featured["prob"] == 29
        assert featured["probability"] == 0.29
        assert featured["leader"] == "Minneapolis", "first of a tie, as before"


# ═══ 4 · the pair cannot be un-paired ════════════════════════════════════════


_SOURCE = (
    Path(__file__).resolve().parents[2] / "app" / "routes" / "weather.py"
).read_text(encoding="utf-8")

# Docstrings and comments stripped — a source scan that reads its own prose is a
# scan of the wrong thing. UX-P190 and UX-P191 each shipped one and each caught it
# on the first run; `_printed`'s own docstring names every expression below.
_CODE = re.sub(
    r"(?m)#.*$",
    "",
    re.sub(r"'''.*?'''", "", re.sub(r'""".*?"""', "", _SOURCE, flags=re.S), flags=re.S),
)

# `_cross_source_row` is excluded, and the exclusion is itself asserted below.
# Its `prob` is a ONE-DECIMAL float used to rank a disagreement
# (`round(p * 100, 1)`), not a whole percent any surface prints — and its
# endpoint, `/api/weather/cross-source`, has no consumer on the page at all
# (parked as UX-P192-1, the weather twin of UX-P187-1). Folding it into
# `_printed` would change a ranking key to buy nothing a reader can see.
_HEAD, _REST = _CODE.split("def _cross_source_row(", 1)
_PAGE_CODE = _HEAD + _REST.split("\ndef ", 1)[1]


class TestTheOneHomeStaysTheOneHome:
    SOURCE = _SOURCE
    CODE = _CODE
    PAGE_CODE = _PAGE_CODE

    def test_no_payload_writes_a_bare_prob_key(self):
        """`"prob": <expr>` written by hand is the shape that ships an
        unprintable number. There must be exactly one — `_printed`'s own."""
        offenders = re.findall(r'"prob"\s*:', self.PAGE_CODE)
        assert len(offenders) == 1, (
            f"weather.py writes {len(offenders)} `prob` keys outside the "
            "cross-source ranking row — every page shape must take its number "
            "from `_printed`, which emits it with the probability the client "
            "needs in order to print `<1%`"
        )
        home = self.PAGE_CODE.split("def _printed(", 1)[1].split("\ndef ", 1)[0]
        assert '"prob":' in home, "and the one that remains is the one home's"

    def test_the_excluded_function_is_the_one_it_claims_to_be(self):
        """An exclusion nobody checks is a hole. This pins WHAT was excluded and
        WHY it is not a printed percent — a one-decimal ranking key."""
        assert "def _cross_source_row(" in self.CODE
        body = self.CODE.split("def _cross_source_row(", 1)[1].split("\ndef ", 1)[0]
        assert body.count('"prob"') == 2, "the row and its top_outcomes"
        assert "* 100, 1)" in body, "one decimal — not a whole percent"
        assert "_printed(" not in body

    def test_the_one_home_emits_both_keys(self):
        assert '"prob"' in self.SOURCE and '"probability"' in self.SOURCE
        # And it is the ONLY place either is written.
        assert self.CODE.count('"probability":') == 1

    def test_every_shape_calls_it(self):
        assert self.CODE.count("_printed(") >= 7, (
            "seven payload shapes ship a number; "
            f"only {self.CODE.count('_printed(')} go through `_printed`"
        )

    def test_the_home_rounds_with_the_contract(self):
        """Vacuity companion. Without it, a `_printed` that returned
        `{"prob": 0, "probability": p}` would satisfy every scan above."""
        body = self.CODE.split("def _printed(", 1)[1].split("\ndef ", 1)[0]
        assert "rendered_percent(probability)" in body
        assert "return {" in body

    def test_the_fixture_and_the_contract_agree_on_the_band(self):
        """The band is implemented in the CLIENTS, so nothing in this file can
        assert it directly. What this file can assert is that the fixture's
        `after` column is the same rule `contracts/rendered_percent.json` states
        — so a change to the contract that this fixture missed goes red here."""
        contract = json.loads(
            (
                Path(__file__).resolve().parents[3] / "contracts" / "rendered_percent.json"
            ).read_text(encoding="utf-8")
        )
        by_prob = {c["probability"]: c["printed"] for c in contract["printed_cases"]}
        checked = 0
        for spec in SPECIMENS:
            for o in spec["outcomes"]:
                if o["probability"] in by_prob:
                    assert by_prob[o["probability"]] == o["after"], o
                    checked += 1
        assert checked >= 1, "no specimen price appears in the contract table"
        # And the rule itself, over the whole contract table.
        for row in contract["printed_cases"]:
            p = row["probability"]
            integer = math.floor(p * 100 + 0.5)
            if integer <= 0 and p > 0:
                expected = "<1%"
            elif integer >= 100 and p < 1:
                expected = ">99%"
            else:
                expected = f"{integer}%"
            assert row["printed"] == expected, row
