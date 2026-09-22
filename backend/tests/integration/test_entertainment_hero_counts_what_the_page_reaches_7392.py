"""#7392 — the /entertainment hero counts the markets the page puts on screen.

Production, read 2026-09-20 07:25Z. The hero advertises **925** markets:

    🎤 Entertainment & Culture
    925 active markets · Updated 3m ago

and the payload renders **112** distinct markets. The footer reads the same
key, so the over-claim is printed twice. `total_markets` was
`sum(len(v) for v in themed.values())` — every bucket `_classify_theme`
accepted, served or not.

═══ THIS IS NOT #6978's DEFECT, WHICH IS WHY IT WAS LEFT OUT OF THAT FIX ═══

#6978 repaired `/politics` and `/economics`, whose heroes were
`len(all_markets)` — the PRE-GATE pool, counting rows the route had already
dropped for reading settled or stale, and calling them "active". That issue
records `/entertainment` as "NOT affected" and about *that* defect it is right:
this route's total was the ACCEPTED set, so it counted no dropped row and the
word "active" was honest. The gap here is section EXPOSURE. `_classify_theme`
files markets into eight buckets; the payload serves three of them, plus a
capped cultural feed.

═══ THE FORMULA THIS FILE SHIPPED WITH FIRST, AND WHY IT IS NOW REFUSED ═══

`a445a1cf4` (withdrawn before merge) printed
`sum(t["count"] for t in themes.values()) + len(cultural_moments)` — **473** on
the same bank. It justified summing bucket counts on the grounds that a section
publishes its count to the reader, which is true of exactly ONE section:
`frontend/app/entertainment/page.tsx` renders `.count` in a single place
(line 1301, `TechCultureSidebar`). `music.count` (254) and `movies_tv.count`
(149) are published to no reader at all, and those sections render 34 and 41
rows. So 403 of the 473 were neither shown nor named — the same over-claim,
4.3x instead of 8.3x. `TestTheBucketCountFormulaIsRefused` is the arm that
stops it being re-derived a third time.

That fix passed a 17-arm version of this file. It passed because the fixture
TIED the ship with the bucket-count formula at 6: every served section's bucket
happened to equal its served rows, so no arm could tell the two apart. Row 310
exists to break that tie and `TestASectionsBucketExceedsItsServedRows` guards
it. A fixture on which two candidate formulas agree cannot say which one the
route is running.

═══ FIVE CANDIDATE FORMULAS, AND THE FIXTURE SEPARATES ALL FIVE ═══

    pre-gate pool                     14   `len(all_markets)`  (#6978's defect,
                                           never this route's — pinned anyway)
    sum(len(v) for v in themed)       12   what this route DID  (over-claims)
    sum(served section counts)         8   the mechanical port  (under-claims)
    section counts + cultural rows    11   the withdrawn fix    (over-claims)
    distinct markets served           10   the ship

═══ WHY NOT GIVE `cultural_moments` A COUNT INSTEAD ═══

Because 472 printed beside 20 reachable rows restates the same over-claim in a
new field, which is what #6978 refused on `/economics`. `CulturalMoments`
(`frontend/app/entertainment/page.tsx:1154`) maps its rows and publishes no
number.

═══ NON-VACUITY ═══

Five controls, because five different degenerate fixes would satisfy a bare
"hero == 10":

* `TestTheFixtureActuallyDropsSomething` — the pre-gate pool is strictly
  larger, so the assertion cannot also hold for `len(all_markets)`.
* `TestTheRetiredFormulaFailsThisFile` — RECOMPUTES the retired formula from
  the fixture rather than trusting its constant, then requires the hero to
  differ from it.
* `TestTheCulturalPoolIsLargerThanWhatIsServed` — the cultural buckets hold 4
  and serve 3, so counting rows is distinguishable from counting the pool.
* `TestASectionsBucketExceedsItsServedRows` — the music bucket holds 3 and
  serves 1, which is what keeps the ship and the withdrawn formula apart. This
  is the control whose absence let the wrong fix through.
* `TestTheSectionsCarryMarketsNoOtherListDoes` — `trending` is capped at 5 and
  re-surfaces section rows, so on a smaller fixture it covered every id the
  sections held and `themes` could be dropped from the count with no arm
  noticing. Rows 311-313 outrun that cap. Found by mutation, not by reading.

═══ THE ONE SURVIVING MUTANT, NAMED RATHER THAN LEFT QUIET ═══

Eleven mutants were run against the route; ten die here. The survivor is
**dropping `cross_source` from the count's call** — this fixture cannot tell.
`cross_source` reads `spotlight_eligible`, so every market it can report is
already themed, and `_cross_source_row_fn` applies `_is_interesting` itself
(`entertainment.py:416`), so unlike `trending` it can never surface a row its
own section refused for being boring. The only way it carries a unique id is a
themed, interesting market sitting BEYOND its section's cap — which needs a
fixture of 13+ music markets built solely to overflow `_build_music`.

An attempt to close it with a genuine Kalshi/Polymarket pair at 96/97% was
measured and reverted: both legs were refused by the `_is_interesting` inside
`_cross_source_row_fn` before the matcher ever saw them, which is the finding
above and is why the pair is not in the fixture.

In production `cross_source` is not inert — it and `trending` add 3 ids over
the sections and the cultural feed on the 07:25Z bank. The hole is in this
fixture, not in the route.
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


def _market(*, market_id, name, probability=0.35, external_id=None,
            volume_24h=1000, source="kalshi"):
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
        source=source,
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
                # #8102: #8011's unobserved-board arm reads this column
                # unguarded, as a real `FuturesOutcome` always carries it. NOW
                # keeps that arm withholding nothing here.
                last_updated=datetime.now(timezone.utc),
            )
        ],
        market_metadata=None,
        resolution_date=now + timedelta(days=30),
        updated_at=now,
        volume_24h=volume_24h,
        image_url=None,
        hook_description=None,
        status="open",
    )


def _fixture():
    """Fourteen markets: three served sections, three cultural rows, a
    trending-only headline, and five dropped before they are served.

    Every name below is checked against `_classify_theme`'s real ordered
    pattern list by `TestTheFixtureLandsWhereItClaims`, so a later edit to those
    regexes cannot silently move a row and leave the counts asserting nothing.

    Two of the four dropped rows are dropped LATE — 306 and 310 earn a theme and
    are then refused by `_is_interesting`. Those are the two gaps the file rests
    on: 306 makes the cultural pool bigger than the cultural rows, and 310 makes
    the music bucket bigger than the music rows. Without them the five candidate
    formulas collapse onto each other.
    """
    return [
        # ── REACHABLE, and each in a DIFFERENT served section, so the section
        #    sum is over more than one term.
        _market(market_id=301, name="Which album will debut at #1 on the Billboard chart?"),          # music
        # ── MUSIC, in the bucket and NOT served: 0.97 clears the featured gate
        #    (< 0.98) and `_is_interesting` drops it (97 > 95). This row is the
        #    only reason a served section's COUNT and its served ROWS are
        #    different numbers on this fixture, which is what separates the ship
        #    from the bucket-count formula it replaced — see
        #    `TestASectionsBucketExceedsItsServedRows`.
        _market(market_id=310, name="Will the Billboard chart record be broken?",                     # music
                probability=0.97),
        #    A SECOND one, and it is load-bearing arithmetic rather than
        #    belt-and-braces: with only 310 the section buckets summed to 9 and
        #    the bucket-count formula landed on 10, tying the ship. Two
        #    late-dropped music rows put it on 11 and the five candidates are
        #    distinct again. `TestTheBucketCountFormulaIsRefused` asserts that
        #    value before it uses it, so a later edit that re-ties them fails
        #    loudly instead of going quiet.
        _market(market_id=314, name="Will the artist top the Hot 100 this month?",                       # music
                probability=0.97),
        _market(market_id=302, name="What will the opening weekend box office be?"),                  # movies
        # ── THREE MORE MOVIES ROWS, and they are here for one reason: to put
        #    more markets in the SECTIONS than `trending` (capped at 5) and the
        #    cultural feed can between them cover. Without them every section id
        #    also appears in trending, `themes` contributes nothing unique, and
        #    `TestEveryServedListReachesTheCount` cannot see `themes` dropped
        #    from the count's call — a surviving mutant, not a passing guard.
        #    `TestTheSectionsCarryMarketsNoOtherListDoes` is the control.
        _market(market_id=311, name='Will the film "Dune Three" gross over $100M?'),                  # movies
        _market(market_id=312, name='Will the film "Wicked Two" gross over $80M?'),                   # movies
        _market(market_id=313, name='Will the film "Avatar Four" gross over $200M?'),                 # movies
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
        # ── DROPPED by `_classify_theme` — off-topic for this page, so it is
        #    in no bucket at all. It is NOT dropped by the featured gate, so it
        #    stays in `featured_eligible` and can still headline TRENDING, and
        #    the volume and the 0.50 leader here are what put it there: 100 for
        #    sitting on the coin-flip plus the full 50 volume bonus tops
        #    `_score_for_trending`.
        #
        #    That makes it the ONLY market `trending` contributes that no
        #    section and no cultural row also carries — which is what lets
        #    `TestEveryServedListReachesTheCount` notice `trending` being
        #    dropped from the count's call. With every trending row mirrored in
        #    a section, that mutant survives.
        #
        #    It also pins the rule: a market in the hero cards and in no section
        #    is still ON THE PAGE, so the count includes it.
        _market(market_id=308, name="What will the celebrity's net worth be?",
                probability=0.50, volume_24h=60000),
    ]


# The five candidate formulas, evaluated on the fixture above, kept as one
# table so every arm can name the one it separates the ship from. They are all
# distinct on purpose: a fixture on which two of them tie cannot tell which one
# the route is running, and the first attempt at this fix shipped precisely
# because the fixture it was built on tied the ship with BUCKET_COUNTS.
PRE_GATE_POOL = 14          # `len(all_markets)` — #6978's defect, never this route's
THEMED_BUCKET_SUM = 12      # what this route served before the fix (over-claims)
SERVED_SECTION_SUM = 8      # the mechanical port of #6978 alone (under-claims)
BUCKET_COUNTS = 11          # sections + cultural rows — WITHDRAWN, see below
CULTURAL_POOL = 4           # awards + celebrity + viral + other
CULTURAL_SERVED = 3         # one is dropped by `_is_interesting`
THE_HERO = 10                # distinct market ids the payload puts on the page


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


def _ids_anywhere_in(node, found=None):
    """Every `market_id` reachable in a served payload, at any depth.

    Deliberately NOT `_distinct_served_market_ids` imported from the route: an
    arm that checks the route against its own helper cannot notice the helper
    being called with the wrong arguments, which is the failure
    `TestEveryServedListReachesTheCount` exists to catch. This walker is
    independent and reads the RESPONSE, not the call.
    """
    found = set() if found is None else found
    if isinstance(node, dict):
        if node.get("market_id") is not None:
            found.add(node["market_id"])
        for value in node.values():
            _ids_anywhere_in(value, found)
    elif isinstance(node, list):
        for item in node:
            _ids_anywhere_in(item, found)
    return found


# ============================================================================
# The ship
# ============================================================================


class TestTheHeroEqualsWhatThePageReaches:
    async def test_total_markets_is_the_distinct_markets_on_the_page(
        self, client, mock_db
    ):
        payload = await _payload(client, mock_db)
        on_the_page = _ids_anywhere_in(
            {k: payload[k] for k in ("trending", "cross_source", "themes",
                                     "cultural_moments")}
        )
        assert payload["total_markets"] == len(on_the_page), (
            f"/entertainment advertises {payload['total_markets']} markets "
            f"while the payload puts {len(on_the_page)} on the page "
            f"({sorted(on_the_page)}). The hero and the footer both print this "
            "key, so it has to mean the markets a reader can reach (#7392)."
        )

    async def test_the_hero_is_the_exact_number_this_fixture_can_reach(
        self, client, mock_db
    ):
        """Pins the value, not just the relationship.

        The arm above is a self-consistency check and would pass if a later
        change dropped rows from BOTH the hero and the served lists together.
        """
        payload = await _payload(client, mock_db)
        assert payload["total_markets"] == THE_HERO


class TestEveryServedListReachesTheCount:
    """A new served list must be added to the count's call.

    The coupling is by argument — `_distinct_served_market_ids(trending,
    cross_source, themes, cultural_moments)` — so a fifth list added to the
    `return` and not to that call would be markets on the page the hero does
    not count. This arm walks the WHOLE response instead of the four keys and
    fails on any market the count never saw.
    """

    async def test_no_market_in_the_response_is_uncounted(
        self, client, mock_db
    ):
        payload = await _payload(client, mock_db)
        everywhere = _ids_anywhere_in(payload)
        assert payload["total_markets"] == len(everywhere), (
            f"the response carries {len(everywhere)} distinct markets and the "
            f"hero counts {payload['total_markets']}. If a served list was just "
            "added, add it to the `_distinct_served_market_ids(...)` call; if a "
            "list was added that the page does NOT render, say so here."
        )

    async def test_the_sections_carry_markets_no_other_list_does(
        self, client, mock_db
    ):
        """The control that makes the arm above able to fail.

        `trending` is capped at 5 and re-surfaces section rows, so on a small
        fixture it can cover every id the sections hold. When it does, dropping
        `themes` from the count's call changes nothing and the arm above passes
        on a count that is missing a whole section — a surviving mutant, which
        is exactly what the first version of this fixture produced. Rows
        311-313 exist to keep this gap open.
        """
        payload = await _payload(client, mock_db)
        others = _ids_anywhere_in(
            {k: payload[k] for k in ("trending", "cross_source",
                                     "cultural_moments")}
        )
        only_in_sections = _ids_anywhere_in(payload["themes"]) - others
        assert only_in_sections, (
            "every market in `themes` also appears in trending, cross_source or "
            "cultural_moments, so the completeness arm above cannot notice "
            "`themes` being dropped from the count. Add served section rows "
            "beyond what trending's cap of 5 can absorb."
        )


# ============================================================================
# Telling the ship from the three formulas that look like it
# ============================================================================


class TestTheRetiredFormulaFailsThisFile:
    """If this passes, every assertion above is measuring nothing."""

    def test_the_retired_formula_is_recomputed_not_remembered(self):
        """`THEMED_BUCKET_SUM` is derived, so the arm below cannot go vacuous.

        `sum(len(v) for v in themed.values())` is every market that clears the
        featured gate AND earns a theme. Asserting the hero merely differs from
        a hard-coded 8 would still pass if a fixture edit moved the real value
        onto the hero's — the failure mode this whole file was rebuilt for.
        """
        from app.utils.market_staleness import should_exclude_from_featured

        now = datetime.now(timezone.utc)
        themed = 0
        for m in _fixture():
            if should_exclude_from_featured(
                m.name, m.llm_sport_category, m.status,
                float(m.outcomes[0].current_probability), now,
            ):
                continue
            if entertainment_module._classify_theme(m) != "excluded":
                themed += 1
        assert themed == THEMED_BUCKET_SUM, (
            f"the retired formula evaluates to {themed} on this fixture, not "
            f"{THEMED_BUCKET_SUM} — update the constant and re-check that it "
            "still differs from THE_HERO."
        )
        assert THEMED_BUCKET_SUM != THE_HERO

    async def test_summing_every_themed_bucket_over_claims(self, client, mock_db):
        payload = await _payload(client, mock_db)
        assert payload["total_markets"] != THEMED_BUCKET_SUM, (
            "the hero still equals `sum(len(v) for v in themed.values())`, the "
            "formula #7392 replaced — it counts every bucket `_classify_theme` "
            "accepted, including the ones this payload never serves."
        )
        assert payload["total_markets"] < THEMED_BUCKET_SUM


class TestTheBucketCountFormulaIsRefused:
    """The formula this fix SHIPPED WITH FIRST, and why it was withdrawn.

    `sum(t["count"] for t in themes.values()) + len(cultural_moments)` reads a
    section's `count` as the page's own published accounting. That is true of
    exactly one section: `frontend/app/entertainment/page.tsx` renders `.count`
    in a single place (line 1301, `TechCultureSidebar`). `music.count` and
    `movies_tv.count` are published to NO reader — those sections render their
    rows and nothing else. On the 2026-09-20 07:25Z bank the formula printed
    **473** over a page rendering **112**, so 403 markets were neither shown nor
    named, which is the same over-claim #7392 was filed about.

    It is an easy formula to arrive at twice, so this arm names it.
    """

    async def test_the_hero_does_not_sum_section_bucket_counts(
        self, client, mock_db
    ):
        payload = await _payload(client, mock_db)
        bucket_formula = _section_sum(payload) + len(payload["cultural_moments"])
        assert bucket_formula == BUCKET_COUNTS, (
            f"the fixture no longer separates the formulas: the bucket-count "
            f"formula evaluates to {bucket_formula}, not {BUCKET_COUNTS}. The "
            "arm below is measuring nothing until that gap is restored — see "
            "`TestASectionsBucketExceedsItsServedRows`."
        )
        assert payload["total_markets"] != bucket_formula, (
            "the hero sums section bucket counts again. A section's `count` is "
            "how many markets `_classify_theme` filed there, not how many the "
            "page renders, and two of the three sections never show that number "
            "to a reader at all."
        )
        assert payload["total_markets"] < bucket_formula


class TestTheMechanicalPortOf6978UnderCounts:
    """The other trap: #6978's sentence applied without reading the render."""

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


class TestASectionsBucketExceedsItsServedRows:
    """The gap the whole file rests on: a bucket is bigger than what it serves.

    Rows 310 and 314 classify as `music`, clear the featured gate at 0.97 and
    are dropped by `_is_interesting` at 97 > 95. So the music bucket holds 3 and
    the music section serves 1, and `BUCKET_COUNTS` and `THE_HERO` are different
    numbers. TWO of them, not one: with a single late-dropped row the formulas
    landed on 10 apiece and tied. Close that gap and the ship ties with the formula it replaced, the
    arms above stop discriminating, and this file passes on the wrong fix —
    which is exactly what happened on the first attempt at #7392.
    """

    async def test_the_music_bucket_is_larger_than_the_rows_it_serves(
        self, client, mock_db
    ):
        payload = await _payload(client, mock_db)
        music = payload["themes"]["music"]
        served = _ids_anywhere_in(
            {k: v for k, v in music.items() if k != "count"}
        )
        assert music["count"] == 3, (
            f"the music bucket holds {music['count']}, expected 3 — rows 310 "
            "and 314 are classified as music and then dropped before the "
            "section serves them."
        )
        assert len(served) == 1, (
            f"the music section serves {len(served)} markets, expected 1."
        )
        assert music["count"] > len(served)


class TestTheCountIsDistinct:
    """One market on the page twice is one market.

    `side_markets` appears under both music and movies_tv in production, and
    `trending` and `cross_source` re-surface section rows — measured on the
    2026-09-20 07:25Z bank, the theme sections alone hold 89 distinct markets,
    the cultural feed adds 20 with one overlap for 109, and trending plus
    cross-source add 3 more for 112. A hero that added up section sizes would
    publish a number larger than the page.

    Exercised on the helper directly because the route's own fixture has no
    duplicate to offer, and a contract nothing tests is a contract that drifts.
    """

    def test_a_market_served_by_two_sections_counts_once(self):
        row = {"market_id": 7, "q": "shared"}
        both = entertainment_module._distinct_served_market_ids(
            {"music": {"side_markets": [row]},
             "movies_tv": {"side_markets": [row]}},
            [row],
        )
        assert both == {7}

    def test_a_grouped_threshold_rung_is_counted(self):
        """`_group_threshold_markets` nests ids under `thresholds[]`.

        A count that sums `len()` over the served lists sees a group as ONE
        entry and misses every rung inside it.
        """
        group = {
            "title": "Some Film",
            "thresholds": [
                {"label": "≥75", "prob": 60.0, "market_id": 11},
                {"label": "≥85", "prob": 20.0, "market_id": 12},
            ],
        }
        found = entertainment_module._distinct_served_market_ids(
            {"movies_tv": {"rt_groups": [group], "rt_markets": []}}
        )
        assert found == {11, 12}

    def test_a_ladders_rungs_are_not_counted_as_markets(self):
        """`top_outcomes` carries no `market_id`, so a ladder is one market."""
        found = entertainment_module._distinct_served_market_ids(
            [{"market_id": 21, "top_outcomes": [
                {"name": "A", "prob": 40.0}, {"name": "B", "prob": 30.0},
                {"name": "C", "prob": 30.0},
            ]}]
        )
        assert found == {21}

    def test_it_counts_only_what_it_is_given(self):
        """Not a corpus count — an unserved bucket is not an argument.

        `themed` holds every classified market (925 on the 07:25Z bank) and the
        payload serves 112. Passing one list must never reach the other.
        """
        assert entertainment_module._distinct_served_market_ids([]) == set()
        assert entertainment_module._distinct_served_market_ids(
            [{"market_id": 1}]
        ) == {1}


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
            (310, "music"),      # classified and served-gated, not theme-gated
            (311, "movies"),     # the three rows that outrun trending's cap
            (312, "movies"),
            (313, "movies"),
            (314, "music"),      # the second late-dropped music row
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
