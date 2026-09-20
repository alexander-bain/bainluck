"""A POLITICS QUESTION STOPS BEING ANSWERED "CONFERENCE". #7369.

═══ WHAT WAS MEASURED ═══

Production `GET /api/events/typeahead`, 2026-09-20 04:45Z. Every futures row's
second line, on three ordinary reader queries:

    q=trump    Conference   Will Trump acquire Greenland before 2027?
    q=trump    Conference   Trump out as President before 2027?
    q=fed      Conference   How many Fed rate cuts in 2026?
    q=fed      Conference   What will Levi's say during their next earnings call?
    q=bitcoin  Conference   Will China unban Bitcoin by 2027?
    q=oscars   Championship Oscars 2027: Best Picture Winner

The Levi's row is the sharpest of them: an earnings *call* badged a
*conference*. The label reaches the web dropdown
(`lib/searchSuggestionDisplay.ts:210`, via `SearchBar` / `MobileSearchOverlay`)
and the iOS search row (`SearchView.swift:575` renders `marketTypeLabel`
verbatim), so both clients printed it.

Population, counted the same night over `status='open'`:

    tier 2 -> "Conference"      11,766 rows   (politics 5,801 · economics 2,448
                                               · entertainment 1,404 · tech 950
                                               · weather 581 · geopolitics 565 …)
    tier 1 -> "Championship"     1,745 rows
    tier 4 -> "Division"            31 rows
                                ──────────
                                13,542 rows

═══ THE MECHANISM: THE RUNG IS TWO POPULATIONS, THE LABEL IS ONE WORD ═══

`compute_market_tier` says so itself, in its own docstring:

    2 = Conference winner / non-sports top-level
    …
    Non-sports markets (politics, crypto, entertainment, etc.) default to tier 2
    since they have no championship/conference hierarchy

Both search serializers then print one word for the whole rung —
`_TIER_LABELS` (typeahead) and `_TIER_LABELS_SEARCH` (`/search`), the same five
literals twice.

🔴 The repair was already WRITTEN and has never once run. `events.py` reads:

    label = _TIER_LABELS.get(market.market_tier, None)
    if not label and market.sport_id is None:
        label = (market.llm_sport_category or market.category or "Market")…title()

`_TIER_LABELS` covers all five tiers, so `not label` is true only for a NULL
tier. The non-sport arm is unreachable for precisely the rows it was written
for. This ship asks the question FIRST rather than adding a sixth literal.

═══ WHY THE PREDICATE IS THE CATEGORY AND NOT THE FK ═══

The dead arm keyed on `market.sport_id is None`. Measured over the same open
tier-1/2/4 population, that and `category in _NON_SPORT_CATEGORIES` **disagree
on 1,224 rows** — rows with no sport FK but a real sport category. The specimen
is in the app's own fixtures (`BainLuckTests/SearchProdFixture.swift`): "Will
Jasmine Paolini advance to the Quarterfinals in Women's Singles at the 2026 US
Open?", `llm_sport_category: "tennis"`, `sport: null`, tier 2. Reviving the arm
on the FK would have relabelled 1,224 tennis and soccer rows "Tennis"/"Soccer".

So `non_sport_topic_label` asks the EXACT expression that assigned the tier —
`(sport_category or category) in _NON_SPORT_CATEGORIES`, `compute_market_tier`'s
own `effective_category` — and can only undo the arm that created the label.
`TestTheFkIsNotThePredicate` is that 1,224-row class, and it is the assertion
that fails if anyone re-keys this on `sport_id`.

═══ WHAT MUST NOT CHANGE, AND WHY THOSE TWO TIERS ARE LEFT ═══

Only the three tier words that name a rung of a SPORTS hierarchy are false off
the field: Championship, Conference, Division. Tier 3 is "Awards / MVP /
individual honors" and tier 5 is "Props / other" — both nouns stay true for a
non-sport row, so an Oscar reading **Award** (128 open rows) and a politics
novelty reading **Prop** (136) are deliberately UNTOUCHED. Fixing words that
are already true would be a bigger diff and a worse payload; the two controls
below hold that line.

Also unchanged: real conference markets (276 open rows with a sport category on
tier 2) still read "Conference", every other key of the `/search` card payload
is byte-identical, and both NULL-tier fallback arms are exactly as they were —
the helper returns `None` for every row it does not own, so each call site keeps
its own chain.

═══ WHAT THIS FILE CAN AND CANNOT SEE ═══

`/search`'s arm is exercised through the REAL serializer,
`_format_futures_for_search`. The typeahead's arm is three inline lines in an
async route body with no seam, so it is guarded by source inspection — the
house pattern for this exact block (`test_typeahead_futures_pool_ordering_4723`
reads the same function's source). That guard proves the call and its ORDER,
not its output; the output is proven once, on the helper, and the two call sites
are asserted to pass the same three arguments in the same order so the surfaces
cannot drift.
"""

import inspect
import re

import pytest

from app.routes import events
from app.routes.events import _format_futures_for_search
from app.utils.market_label_normalization import (
    _NON_SPORT_CATEGORIES,
    compute_market_tier,
    non_sport_topic_label,
)


class _Market:
    """The attributes `_format_futures_for_search` reads off an ORM row."""

    def __init__(self, tier, llm_sport_category, category, **kw):
        self.market_tier = tier
        self.llm_sport_category = llm_sport_category
        self.category = category
        self.outcomes = []
        self.id = kw.get("id", 1)
        self.name = kw.get("name", "A market")
        self.sport = kw.get("sport", None)
        self.market_type = kw.get("market_type", None)
        self.status = "open"
        self.source = "polymarket"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = True


def _served_label(tier, llm_sport_category, category, **kw) -> str:
    """The second line `/search` actually serves for this row."""
    return _format_futures_for_search(
        _Market(tier, llm_sport_category, category, **kw)
    )["market_type_label"]


# ---------------------------------------------------------------------------
# The production specimens, each on the surface that printed them.
# ---------------------------------------------------------------------------


class TestTheMeasuredSpecimens:
    @pytest.mark.parametrize(
        "name,category,expected",
        [
            ("Will Trump acquire Greenland before 2027?", "politics", "Politics"),
            ("Trump out as President before 2027?", "politics", "Politics"),
            ("How many Fed rate cuts in 2026?", "economics", "Economics"),
            (
                "What will Levi's say during their next earnings call?",
                "economics",
                "Economics",
            ),
            ("Will China unban Bitcoin by 2027?", "politics", "Politics"),
        ],
    )
    def test_a_tier_two_non_sport_row_names_its_topic(self, name, category, expected):
        """The 11,766. Each of these answered "Conference" on 2026-09-20."""
        assert _served_label(2, category, "championship", name=name) == expected

    def test_the_earnings_call_is_no_longer_a_conference(self):
        """The sharpest of the five, asserted as the negative it actually is."""
        label = _served_label(
            2, "economics", "championship",
            name="What will Levi's say during their next earnings call?",
        )
        assert label != "Conference"

    def test_a_tier_one_non_sport_row_is_not_a_championship(self):
        """The 1,745. An election is not a championship."""
        assert _served_label(1, "politics", "championship") == "Politics"

    def test_a_tier_four_non_sport_row_is_not_a_division(self):
        """The 31. Weather has no divisions."""
        assert _served_label(4, "weather", "weather") == "Weather"

    def test_every_non_sport_category_is_covered(self):
        """Not five hand-picked topics — the whole vocabulary the tier arm uses.

        `_NON_SPORT_CATEGORIES` is the set `compute_market_tier` defaults to tier
        2 on. If a category is added there and not handled here, a new topic
        starts printing "Conference" the day it ships.
        """
        for category in _NON_SPORT_CATEGORIES:
            label = _served_label(2, category, "championship")
            assert label != "Conference", category
            assert label == category.replace("_", " ").title(), category


# ---------------------------------------------------------------------------
# The 1,224-row class the obvious fix would have broken.
# ---------------------------------------------------------------------------


class TestTheFkIsNotThePredicate:
    def test_a_sport_row_with_no_sport_fk_keeps_its_tier_word(self):
        """`SearchProdFixture.swift`'s Paolini row: tennis, `sport: null`, tier 2.

        The dead arm in `events.py` keyed on `sport_id is None`, which is TRUE
        here. Re-key this repair on the FK and this assertion is what fails.
        """
        label = _served_label(
            2, "tennis", "game_prop", sport=None,
            name=(
                "Will Jasmine Paolini advance to the Quarterfinals in "
                "Women's Singles at the 2026 US Open?"
            ),
        )
        assert label == "Conference"

    @pytest.mark.parametrize("category", ["tennis", "soccer", "basketball", "football"])
    def test_no_sport_category_is_ever_relabelled(self, category):
        """The class, not the one specimen. 1,224 open rows sit here."""
        assert non_sport_topic_label(2, "game_prop", category) is None
        assert _served_label(2, category, "game_prop", sport=None) == "Conference"

    def test_a_real_conference_market_still_reads_conference(self):
        """The 276 rows the word was written for. It must survive its own fix."""
        assert _served_label(
            2, "football", "championship", name="AFC Conference Winner 2027"
        ) == "Conference"


# ---------------------------------------------------------------------------
# The two tiers deliberately left alone.
# ---------------------------------------------------------------------------


class TestTheTrueWordsAreLeft:
    def test_an_entertainment_award_still_reads_award(self):
        """128 open rows. An Oscar IS an award — there is nothing to repair."""
        assert _served_label(3, "entertainment", "championship") == "Award"

    def test_a_non_sport_prop_still_reads_prop(self):
        """136 open rows. "Prop" is the catch-all and stays true off the field."""
        assert _served_label(5, "politics", "championship") == "Prop"

    @pytest.mark.parametrize("tier", [3, 5])
    def test_the_helper_declines_the_tiers_it_does_not_own(self, tier):
        for category in _NON_SPORT_CATEGORIES:
            assert non_sport_topic_label(tier, "championship", category) is None


# ---------------------------------------------------------------------------
# The helper's own edges, and the fallbacks it must not disturb.
# ---------------------------------------------------------------------------


class TestTheHelperEdges:
    def test_the_category_column_answers_when_the_llm_column_is_empty(self):
        """`compute_market_tier` reads `sport_category or category`; so does this."""
        assert non_sport_topic_label(2, "politics", None) == "Politics"
        assert _served_label(2, None, "politics") == "Politics"

    def test_the_llm_column_wins_when_both_are_set(self):
        """Polymarket writes `category='championship'` on everything; the
        `llm_sport_category` is the one that decided the tier."""
        assert non_sport_topic_label(2, "championship", "politics") == "Politics"

    @pytest.mark.parametrize("tier", [None, 0, 6, 99])
    def test_a_tier_outside_the_hierarchy_is_declined(self, tier):
        assert non_sport_topic_label(tier, "politics", "politics") is None

    def test_a_null_tier_row_keeps_the_existing_fallback(self):
        """The helper owns none of this, so `/search`'s own chain still answers."""
        assert _served_label(None, "politics", "politics", market_type="Range") == "Range"
        assert _served_label(None, "politics", "politics") == "Market"

    @pytest.mark.parametrize("blank", ["", None, "   "])
    def test_a_blank_category_is_declined_not_blanked(self, blank):
        """A blank second line is a worse row than a wrong word; never return ""."""
        assert non_sport_topic_label(2, blank, blank) is None

    def test_underscores_never_reach_the_reader(self):
        """The one shape in the set that title-casing alone would leave as a key."""
        assert non_sport_topic_label(2, None, "geo_politics") is None  # not in the set
        assert "_" not in (non_sport_topic_label(2, None, "geopolitics") or "")

    def test_the_label_undoes_the_arm_that_assigned_the_tier(self):
        """The two functions agree by construction, not by coincidence.

        `compute_market_tier` reaches tier 2 for these names only through its
        non-sport default; `non_sport_topic_label` must own exactly that arm.
        """
        for category in _NON_SPORT_CATEGORIES:
            assert compute_market_tier("A top-level question", None, category) == 2
            assert non_sport_topic_label(2, None, category) is not None


# ---------------------------------------------------------------------------
# The payload control, and the surface this file cannot execute.
# ---------------------------------------------------------------------------


class TestNothingElseMoved:
    def test_every_other_search_card_key_is_byte_identical(self):
        """The cheapest wrong fix rewrites a neighbouring key on the way past."""
        row = _Market(2, "politics", "championship")
        before = _format_futures_for_search(row)
        after = dict(before)
        after.pop("market_type_label")
        # The same row through a tier the helper declines: only the one key may
        # differ between the two payloads.
        control = _format_futures_for_search(_Market(3, "politics", "championship"))
        differing = {
            k for k in before
            if k not in ("market_type_label", "market_tier")
            and before[k] != control[k]
        }
        assert differing == set()
        assert before["market_type_label"] == "Politics"
        assert control["market_type_label"] == "Award"
        assert set(after) | {"market_type_label"} == set(before)


class TestTheTypeaheadAsksItFirst:
    """Source guards — the typeahead's label chain has no callable seam.

    These prove the call and its POSITION. The output is proven on the helper
    above; what can still go wrong here is ordering, and ordering is the entire
    defect (`_TIER_LABELS` covering all five tiers is why the written repair
    never ran).
    """

    @staticmethod
    def _typeahead_src() -> str:
        return inspect.getsource(events.typeahead_search)

    def test_the_typeahead_calls_the_shared_helper(self):
        assert "non_sport_topic_label(" in self._typeahead_src()

    def test_the_helper_is_asked_before_the_tier_map(self):
        """If `_TIER_LABELS.get` runs first its answer is truthy for all five
        tiers and the helper can never be reached — which is the shipped bug,
        exactly."""
        src = self._typeahead_src()
        assert src.index("non_sport_topic_label(") < src.index("_TIER_LABELS.get(")

    def test_the_dead_fk_arm_is_still_last_and_still_there(self):
        """It is correct for a NULL tier and this ship does not touch it."""
        src = self._typeahead_src()
        assert "market.sport_id is None" in src
        assert src.index("_TIER_LABELS.get(") < src.index("market.sport_id is None")

    def test_both_surfaces_pass_the_same_three_arguments(self):
        """One question, asked identically twice — or the two search surfaces
        answer the same row differently, which is how this class recurs."""
        pattern = re.compile(
            r"non_sport_topic_label\(\s*"
            r"market\.market_tier,\s*market\.category,\s*market\.llm_sport_category",
            re.S,
        )
        whole = inspect.getsource(events)
        assert len(pattern.findall(whole)) == 2
        assert whole.count("non_sport_topic_label(") == 2
