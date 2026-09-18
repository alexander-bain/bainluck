"""#6941, second half — a group header stops printing our ranking's verdict.

WHAT A READER SAW, banked at 390px while it was live (artifacts-lane1b-362):

  * `/search?q=darts` — ANSWERS (1), and the one group is headed
    **NICHE LOW SIGNAL SPORTS** over five World Series of Darts questions. A
    darts fan is told on their own results that their sport is niche and low
    signal. That key is the page's ONLY family, so failing closed would have
    emptied the answers block outright.
  * `/search?q=Chiefs` — **MINOR SOCCER LEAGUES** over "Lamontville Golden
    Arrows vs. Kaizer Chiefs", one of the biggest clubs in Africa playing in its
    country's top flight. "Minor" is our score's opinion of the market's pull,
    not a fact about the competition.

The first half (#6947, `026b1a741`) fixed the keys that were being un-slugified
into a machine string — `Ufc Event:331` — by giving search the house resolver,
`story_family_label`. It deliberately left these three keys deriving, and said
so: `story:niche_low_signal_sports`, `story:minor_soccer_leagues` and
`story:daily_equity_direction` have no authored name because they are not one
story anyone can ask one sentence about. Deriving them, though, prints the
verdict in the slug.

THE FIX is a third tier between the two: `NEUTRAL_STORY_TITLES`, a display name
for a key that names our ranking. Not `AUTHORED_STORY_TITLES` — membership there
is a claim that the family is one story, and obliges an authored question
(`test_discover_bundle_shared_question_4066.py` pins title ⊆ question) — and the
question resolution is left on exactly the tier it was on, so this moves strings
and nothing else.

DISCOVER IS INERT, twice over: these three are the suppression families, capped
at 1 upstream (`feed_market_quality`, and `test_authored_titles_cover_every_real_story_key`
names them as such), so two of them never bundle; and even if one did, the
`story_title` question tier still fires for them, which is what
`test_the_question_tier_these_keys_fold_on_is_unchanged` holds down. The reader
this ship is for is on `/search`.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import _compose_futures_families
from app.utils.discover_bundles import (
    AUTHORED_STORY_TITLES,
    NEUTRAL_STORY_TITLES,
    _derive_story_title,
    _resolve_story_title,
    resolve_story_question,
    story_family_label,
)
from app.utils.feed_market_quality import _story_key

# The vocabulary a reader may never be handed: our own judgement of how much a
# market is worth to the feed. Matched against every header the resolver can
# serve, so a future key that spells its verdict is caught here and not by a fan.
_VERDICT_WORDS = (
    "niche",
    "low signal",
    "low_signal",
    "minor",
    "filler",
    "junk",
    "garbage",
    "spam",
    "obscure",
    "boring",
    "irrelevant",
)


def _mkt(mid, name, category=""):
    return SimpleNamespace(id=mid, name=name, llm_sport_category=category)


def _headers(markets, expanded):
    """The labels `/api/events/search` would ship for these markets."""
    ids = {m.id for m in markets}
    fams = _compose_futures_families(
        markets, expanded, lambda m: {"id": m.id, "name": m.name}, ids
    )
    return [f["label"] for f in fams]


def _verdicts_in(text):
    low = (text or "").lower()
    return [word for word in _VERDICT_WORDS if word in low]


# ── The two photographed specimens ───────────────────────────────────────────


class TestTheReaderIsNotToldTheirSportIsNiche:
    def test_the_darts_group_is_not_headed_niche_low_signal_sports(self):
        """`/search?q=darts`, reproduced through the composer that served it.

        Member names are the real ones off production (23:18Z), not invented:
        the key is minted from the NAME, so a fixture that stopped matching
        `_LOW_SIGNAL_SPORT_RE` would form no family and leave this asserting
        over an empty list — hence the `== ["Other Sports"]` equality rather
        than a membership check.
        """
        markets = [
            _mkt(1, "World Series of Darts: Motomu Sakai vs Callan Rydz"),
            _mkt(2, "World Series of Darts: Luke Littler vs Danny Noppert"),
            _mkt(3, "World Series of Darts: James Wade vs Damon Heta"),
        ]

        assert _headers(markets, [("darts", None)]) == ["Other Sports"]

    def test_the_kaizer_chiefs_group_is_not_headed_minor_soccer_leagues(self):
        markets = [
            _mkt(4, "Lamontville Golden Arrows vs. Kaizer Chiefs", "soccer"),
            _mkt(5, "Golden Arrows vs Kaizer Chiefs O/U 1.5", "soccer"),
        ]

        assert _headers(markets, [("chiefs", None)]) == ["Soccer"]

    @pytest.mark.parametrize("story_key", sorted(NEUTRAL_STORY_TITLES))
    def test_no_neutral_name_carries_a_verdict_or_a_key_signature(self, story_key):
        label = story_family_label(story_key, [])

        assert label
        assert _verdicts_in(label) == []
        assert ":" not in label and "_" not in label

    @pytest.mark.parametrize(
        "story_key,was_served,verdict",
        [
            ("story:niche_low_signal_sports", "Niche Low Signal Sports", True),
            ("story:minor_soccer_leagues", "Minor Soccer Leagues", True),
            # Not a verdict — desk jargon, which notice 34 keeps off a page just
            # as firmly. Stated separately rather than swept in with the other
            # two, because a control that overstates its own case is not one.
            ("story:daily_equity_direction", "Daily Equity Direction", False),
        ],
    )
    def test_the_string_being_replaced_is_the_one_that_was_served(
        self, story_key, was_served, verdict
    ):
        """The control. Without it, the assertions above pass on a map of keys
        that never said anything wrong, and the file proves nothing about the
        defect it was written for. `_derive_story_title` is still reachable —
        it is what any UNNAMED key gets — so this is the live old behaviour, not
        a reconstruction of it."""
        assert _derive_story_title(story_key) == was_served
        assert bool(_verdicts_in(was_served)) is verdict
        assert story_family_label(story_key, []) != was_served


# ── The class, not the three strings ─────────────────────────────────────────


class TestNoStoryKeyReachesAReaderByStringSurgery:
    def _literal_keys(self):
        import ast
        import inspect

        import app.utils.feed_market_quality as fmq

        tree = ast.parse(inspect.getsource(fmq))
        keys = sorted(
            {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.startswith("story:")
                and not node.value.endswith(":")  # the two dynamic PREFIXES
            }
        )
        assert len(keys) >= 20, f"the scan found only {len(keys)} keys — it broke"
        return keys

    def test_every_key_the_producer_can_mint_is_named_by_a_human(self):
        """Authored or neutral — never un-slugified. This is the arm that makes
        the NEXT key someone adds to the feed machinery a CI failure instead of
        a header on a stranger's results page."""
        unnamed = [
            key
            for key in self._literal_keys()
            if key not in AUTHORED_STORY_TITLES and key not in NEUTRAL_STORY_TITLES
        ]

        assert unnamed == [], (
            "these keys would be title-cased onto a reader's screen; add a name "
            f"to AUTHORED_STORY_TITLES (with its question) or NEUTRAL_STORY_TITLES: {unnamed}"
        )

    def test_no_served_header_carries_a_ranking_verdict(self):
        offenders = {
            key: story_family_label(key, [])
            for key in self._literal_keys()
            if _verdicts_in(story_family_label(key, []))
        }

        assert offenders == {}


# ── Discover: strings move, folding does not ─────────────────────────────────


class TestDiscoverKeepsTheBehaviourItHadToday:
    @pytest.mark.parametrize("story_key", sorted(NEUTRAL_STORY_TITLES))
    def test_the_question_tier_these_keys_fold_on_is_unchanged(self, story_key):
        """A neutral name must not promote a key into the authored tier.

        `resolve_story_question` reads AUTHORED first, then a shared member
        phrase, then the weak `story_title` tier — and that last tier is the one
        these keys have always folded on. If naming them had made them look
        authored, the tier would return `(None, "none")` and a family that folds
        on Discover today would stop folding: a composition change smuggled in
        under a copy fix. So the SOURCE is asserted, not just the sentence.
        """
        question, source = resolve_story_question(story_key, ["Alpha", "Beta"])

        assert source == "story_title"
        assert question is not None
        assert _verdicts_in(question) == []

    @pytest.mark.parametrize("story_key", sorted(NEUTRAL_STORY_TITLES))
    def test_a_neutral_key_is_not_reported_as_authored(self, story_key):
        assert _resolve_story_title(story_key)[1] == "neutral"


class TestTheOtherTiersDoNotMove:
    def test_an_authored_key_still_wins(self):
        assert story_family_label("story:ai", []) == "AI"
        assert _resolve_story_title("story:macro_rates") == ("Fed & Rates", "authored")

    def test_an_unknown_key_still_derives_and_still_logs(self, caplog):
        """The early return must not swallow the ops signal for a key nobody has
        named yet — that log line is how the next one gets named."""
        import logging

        from app.utils import discover_bundles as db_mod

        db_mod._UNKNOWN_STORY_KEYS_LOGGED.discard("story:some_unnamed_topic")

        with caplog.at_level(logging.INFO, logger="app.utils.discover_bundles"):
            label, source = _resolve_story_title("story:some_unnamed_topic")

        assert (label, source) == ("Some Unnamed Topic", "fallback")
        assert [
            r for r in caplog.records if "unknown story_key fallback" in r.getMessage()
        ]

    def test_the_key_minter_still_mints_what_this_file_assumes(self):
        """Asserted rather than assumed: every header test above is worthless if
        these names stop keying the way they key today."""
        assert (
            _story_key("World Series of Darts: Luke Littler vs Danny Noppert", "")
            == "story:niche_low_signal_sports"
        )
        assert (
            _story_key("Lamontville Golden Arrows vs. Kaizer Chiefs", "soccer")
            == "story:minor_soccer_leagues"
        )
