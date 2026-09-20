"""#7392 — the /entertainment hero counts what the page can REACH.

Production, read 2026-09-20 07:25Z. The hero advertises **925** markets:

    🎤 Entertainment & Culture
    925 active markets · Updated 3m ago

and the page's own sections reach 453 — music 254 + movies_tv 149 +
tech_culture 50. The other **472** are accepted by the route and surface, at
most, as a 20-row `cultural_moments` feed that prints no count at all. A 2.0x
over-claim in the headline, and again in the footer, which reads the same key.

═══ THIS IS NOT #6978's DEFECT, WHICH IS WHY IT WAS LEFT OUT OF THAT FIX ═══

#6978 repaired `/politics` and `/economics`, whose heroes were
`len(all_markets)` — the PRE-GATE pool, counting rows the route had already
dropped for reading settled or stale, and calling them "active". That issue
records `/entertainment` as "NOT affected" and about *that* defect it is right:
this route's total was already `sum(len(v) for v in themed.values())`, the
ACCEPTED set, so it counted no dropped row and the word "active" was honest.

The gap here is section EXPOSURE. `_classify_theme` files markets into eight
buckets; the payload serves counts for three. `awards`, `celebrity`, `viral`
and `other` are accepted by the loop and reach a reader only through
`cultural_moments`.

═══ FOUR CANDIDATE FORMULAS, AND THE FIXTURE SEPARATES ALL FOUR ═══

This is the whole reason the fixture below is shaped the way it is. On it:

    pre-gate pool                      9   `len(all_markets)`  (#6978's defect,
                                           never this route's — pinned anyway)
    sum(len(v) for v in themed)        7   what this route DID  (over-claims)
    sum(served section counts)         3   the mechanical port  (under-claims)
    sections + cultural rows served    6   the ship

The mechanical port is the trap worth naming. Applying #6978's sentence — "the
hero is the sum of the sections the payload serves" — to this route without
reading the render prints 453 and silently stops counting the cultural rows the
page does show. `/economics`'s `other` bucket is served by NOTHING, so summing
sections was the complete answer there; here the cultural buckets are served,
just capped. `TestTheMechanicalPortOf6978UnderCounts` is the arm that tells
those two apart, and without it this file passes on a fix that is still wrong.

═══ WHY NOT GIVE `cultural_moments` A COUNT INSTEAD ═══

Because 472 printed beside 20 reachable rows restates the same over-claim in a
new field, which is exactly what #6978 refused on `/economics`. The issue body
floated that option before the render had been read; `CulturalMoments`
(`frontend/app/entertainment/page.tsx:1154`) maps its rows and publishes no
number, so the rows are what the page tells the reader about.

═══ THE BOUNDARY, STATED SO NOBODY "FINISHES THE JOB" ═══

A section `count` is its BUCKET size, not its rendered row count — music
publishes 254 and renders twelve — and this file pins that deliberately in
`TestASectionCountIsItsBucketNotItsRenderedRows`. `TechCultureSidebar` prints
"{count} markets" to the reader, so the bucket size is the page's own published
accounting and the hero summing it is consistent. `cultural_moments` publishes
no such number, so for that one the served rows ARE the accounting. A later
reader who "corrects" the sections to rendered-row counts breaks that arm and
should read this paragraph before deleting it.

═══ NON-VACUITY ═══

Three controls, because three different degenerate fixes would satisfy a bare
"hero == 5" assertion:

* `TestTheFixtureActuallyDropsSomething` — the pre-gate pool is strictly
  larger, so the assertion cannot also hold for `len(all_markets)`.
* `TestTheRetiredFormulaFailsThisFile` — re-runs the ship's assertion under the
  formula this replaced and requires it to FAIL. If that test ever passes, the
  rest of this file is measuring nothing.
* `TestTheCulturalPoolIsLargerThanWhatIsServed` — the cultural buckets hold 4
  markets and serve 3, so `+ len(cultural_moments)` is distinguishable from
  `+ len(the cultural pool)`. Without this the two formulas tie on the fixture
  and the guard would not notice a fix that re-published the 472.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import entertainment as entertainment_module


# ---------------------------------------------------------------------------
# Mocks — the shared idiom from
# test_category_hero_counts_what_the_page_reaches_6978
# ---------------------------------------------------------------------------


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars

    def all(self):
        return self._scalars.all()

    def first(self):
        return self._scalars.first()


def _market(*, market_id, name, probability=0.35, external_id=None):
    """A single-outcome entertainment market.

    ``probability`` is on the 0-1 scale the column uses; `_market_row` multiplies
    by 100, so the two gates below read it on different scales and the fixture
    has to respect both:

    * ``should_exclude_from_featured`` sees the RAW leader (0-1) and drops it
      outside ``(0.02, 0.98)``.
    * ``_is_interesting`` sees the PERCENT (0-100) and drops
      ``outcome_count <= 2 and prob > 95``.

    So 0.97 survives the first and is dropped by the second, which is the only
    reason the cultural pool can be larger than the cultural rows served.
    """
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id or f"mock{market_id}",
        source="kalshi",
        category="news",
        llm_sport_category="entertainment",
        outcomes=[
            SimpleNamespace(
                id=market_id * 10,
                name="Yes",
                current_probability=probability,
                probability_change_24h=0,
                rank=1,
                is_winner=None,
                resolution_source=None,
            )
        ],
        market_metadata=None,
        resolution_date=now + timedelta(days=30),
        updated_at=now,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


def _fixture():
    """Eight markets: three served sections, three cultural, two dropped.

    Every name below is checked against `_classify_theme`'s real ordered
    pattern list by `TestTheFixtureLandsWhereItClaims`, so a later edit to those
    regexes cannot silently move a row and leave the counts asserting nothing.
    """
    return [
        # ── REACHABLE, and each in a DIFFERENT served section, so the section
        #    sum is over more than one term.
        _market(market_id=301, name="Which album will debut at #1 on the Billboard chart?"),          # music
        _market(market_id=302, name="What will the opening weekend box office be?"),                  # movies
        _market(market_id=303, name="How many YouTube subscribers will the channel have?"),           # social_media
        # ── CULTURAL: accepted, served by no counted section, reachable only
        #    through the 20-row feed. Two survive `_is_interesting`.
        #    All four cultural buckets are represented, `other` included: it is
        #    the catch-all and the biggest of them in production.
        _market(market_id=304, name="Who will win the Emmy for Best Drama?"),                         # awards
        _market(market_id=305, name="Will Drake release a surprise project?"),                        # celebrity
        _market(market_id=309, name="Will the hot dog eating record be broken this year?"),           # other
        # ── CULTURAL but NOT SERVED — 0.97 clears the featured gate (< 0.98)
        #    and `_is_interesting` drops it (97 > 95). This row is what makes
        #    "count the pool" and "count the rows served" different numbers.
        _market(market_id=306, name="Will the royal wedding take place this year?",                   # viral
                probability=0.97),
        # ── DROPPED by the featured gate — a dead extreme.
        _market(market_id=307, name="Will the concert tour be announced?", probability=0.995),
        # ── DROPPED by `_classify_theme` — off-topic for this page, so it is in
        #    `all_markets` and in no bucket at all.
        _market(market_id=308, name="What will the celebrity's net worth be?"),
    ]


# The four candidate formulas, evaluated on the fixture above. Kept as one
# table so an arm can name the one it is separating from the ship.
PRE_GATE_POOL = 9
THEMED_BUCKET_SUM = 7      # what this route served before the fix
SERVED_SECTION_SUM = 3     # the mechanical port of #6978
CULTURAL_POOL = 4          # awards + celebrity + viral + other
CULTURAL_SERVED = 3        # one is dropped by `_is_interesting`
THE_HERO = 6               # sections (3) + cultural rows served (3)


async def _payload(client, mock_db, markets=None):
    mock_db.execute.return_value = _MockResult(
        _fixture() if markets is None else markets
    )
    resp = await client.get("/api/entertainment")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "themes" in body, (
        "the route fell through to its timeout/error shape, so every count "
        f"below would be vacuous: {body}"
    )
    return body


def _section_sum(payload):
    return sum(t["count"] for t in payload["themes"].values())


# ============================================================================
# The ship
# ============================================================================


class TestTheHeroEqualsWhatThePageReaches:
    async def test_total_markets_is_the_sections_plus_the_cultural_rows(
        self, client, mock_db
    ):
        payload = await _payload(client, mock_db)
        reachable = _section_sum(payload) + len(payload["cultural_moments"])
        assert payload["total_markets"] == reachable, (
            f"/entertainment advertises {payload['total_markets']} markets "
            f"while the page reaches {reachable} — "
            f"{_section_sum(payload)} through its counted sections and "
            f"{len(payload['cultural_moments'])} through the cultural feed, "
            "which publishes no count of its own (#7392)."
        )

    async def test_the_hero_is_the_exact_number_this_fixture_can_reach(
        self, client, mock_db
    ):
        """Pins the value, not just the relationship.

        The arm above is a self-consistency check and would pass if a later
        change dropped rows from BOTH the hero and the sections together.
        """
        payload = await _payload(client, mock_db)
        assert payload["total_markets"] == THE_HERO


# ============================================================================
# Telling the ship from the three formulas that look like it
# ============================================================================


class TestTheRetiredFormulaFailsThisFile:
    """If this passes, every assertion above is measuring nothing."""

    async def test_summing_every_themed_bucket_over_claims(self, client, mock_db):
        payload = await _payload(client, mock_db)
        assert payload["total_markets"] != THEMED_BUCKET_SUM, (
            "the hero still equals `sum(len(v) for v in themed.values())`, the "
            "formula #7392 replaced — it counts the cultural buckets in full "
            "while the page can reach only the rows in the feed."
        )


class TestTheMechanicalPortOf6978UnderCounts:
    """The trap: #6978's sentence applied here without reading the render."""

    async def test_the_sections_alone_are_not_the_whole_answer(
        self, client, mock_db
    ):
        payload = await _payload(client, mock_db)
        assert payload["total_markets"] != SERVED_SECTION_SUM, (
            "the hero equals the served section counts alone, which stops "
            "counting the cultural rows this page DOES render. That is the "
            "complete answer on /economics, whose `other` bucket is served by "
            "nothing, and the wrong one here."
        )
        assert payload["total_markets"] > SERVED_SECTION_SUM


class TestTheFixtureActuallyDropsSomething:
    """Without this, the ship's arms would also hold for `len(all_markets)`."""

    async def test_the_pre_gate_pool_is_strictly_larger(self, client, mock_db):
        markets = _fixture()
        payload = await _payload(client, mock_db, markets)
        assert len(markets) == PRE_GATE_POOL
        assert payload["total_markets"] < len(markets), (
            "the fixture is not discriminating: the route reached "
            f"{payload['total_markets']} of {len(markets)} markets, so an "
            "assertion about the hero would also hold for the pre-gate pool."
        )


class TestTheCulturalPoolIsLargerThanWhatIsServed:
    """Separates `+ len(cultural_moments)` from `+ len(the cultural pool)`.

    Four markets classify into cultural buckets and three are served. If a
    later change published the pool size instead, the hero would read 7 and the
    ship's arms would catch it only because of this gap.
    """

    async def test_one_cultural_market_is_accepted_but_not_served(
        self, client, mock_db
    ):
        payload = await _payload(client, mock_db)
        served = len(payload["cultural_moments"])
        assert served == CULTURAL_SERVED, (
            f"expected {CULTURAL_SERVED} cultural rows served, got {served} — "
            "the 0.97 row is "
            "supposed to clear the featured gate and be dropped by "
            "`_is_interesting`, and if that is no longer true this file's "
            "pool-vs-served gap has closed and the arm below is vacuous."
        )
        assert payload["total_markets"] != SERVED_SECTION_SUM + CULTURAL_POOL, (
            "the hero counts the cultural POOL rather than the rows served — "
            "that republishes the 472 the page cannot reach, in a new place."
        )


class TestASectionCountIsItsBucketNotItsRenderedRows:
    """Pins the boundary the docstring states, so it cannot drift silently.

    `TechCultureSidebar` prints "{count} markets" to the reader, so a section's
    count is its bucket size and the hero summing it is consistent. This arm
    exists so that a later change to rendered-row counts is a deliberate,
    visible decision rather than an accident.
    """

    async def test_tech_culture_publishes_its_bucket_size(self, client, mock_db):
        payload = await _payload(client, mock_db)
        tech = payload["themes"]["tech_culture"]
        assert tech["count"] == 1
        assert tech["count"] >= len(tech["markets"])


# ============================================================================
# The fixture means what it says
# ============================================================================


class TestTheFixtureLandsWhereItClaims:
    """`_classify_theme` is a regex ladder; a later edit could move a row.

    Every count in this file is downstream of these eight classifications, so
    they are asserted directly rather than inferred from the totals they
    produce.
    """

    @pytest.mark.parametrize(
        "market_id,expected_theme",
        [
            (301, "music"),
            (302, "movies"),
            (303, "social_media"),
            (304, "awards"),
            (305, "celebrity"),
            (306, "viral"),
            (307, "music"),      # classified, but dropped earlier by the gate
            (308, "excluded"),
            (309, "other"),
        ],
    )
    def test_each_row_classifies_into_the_bucket_the_fixture_assumes(
        self, market_id, expected_theme
    ):
        market = next(m for m in _fixture() if m.id == market_id)
        assert entertainment_module._classify_theme(market) == expected_theme, (
            f"fixture row {market_id} ({market.name!r}) no longer classifies "
            f"as {expected_theme!r} — the counts in this file are built on that "
            "assumption and are now asserting something else."
        )

    def test_the_dead_extreme_row_is_dropped_before_it_is_themed(self):
        """Row 307 is `probability_extreme`, not a theme miss.

        It classifies as `music`, so if the featured gate ever stopped dropping
        it the music section would gain a market and the hero would move — this
        arm says which gate is load-bearing for that row.
        """
        from app.utils.market_staleness import should_exclude_from_featured

        market = next(m for m in _fixture() if m.id == 307)
        reason = should_exclude_from_featured(
            market.name,
            market.llm_sport_category,
            market.status,
            float(market.outcomes[0].current_probability),
            datetime.now(timezone.utc),
        )
        assert reason == "probability_extreme"
