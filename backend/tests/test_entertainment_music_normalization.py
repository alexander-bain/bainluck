"""A Spotify-race market publishes its OWN leading probability.

`_market_row` puts `prob` on the 0-100 scale (`current_probability * 100`), and every
consumer reads it that way — `GenericMarketCard` renders it through `ProbPct`/`EntProbBar`.

`_build_music` used to divide every `spotify_race` row by the sum of the others, in the
*feed's* 0-1 form (`sum > 1.05`, divide with no `* 100`).  Measured on production
2026-08-31, `GET /api/entertainment` published:

    spotify_race[0].prob = 0.8   while its own leading outcome read 86.0
    spotify_race[1].prob = 0.2   while its own leading outcome read 21.5

Correcting only the arithmetic (0-100: `> 105`, `/ sum * 100`) is NOT the fix — it
publishes 80.0/20.0 for that same pair while their own outcomes still read 86.0/21.5, and
the card labels the altered shares with the original outcome names (CERT-560).

Normalizing across MARKETS is meaningful only when the markets partition one question —
politics `_normalize_outcome_probs` over the candidates of a single race.  `spotify_race`
membership comes from the `kxspotify` ticker prefix, so it collects unrelated questions
with no shared 100% to divide.  The cross-market step is therefore gone, and the invariant
these tests pin is the simple one:

    a row's published `prob` IS its own leading outcome's `prob`.
"""

import io
import itertools
import tokenize
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.routes.entertainment import _build_music


# ---------------------------------------------------------------------------
# Fakes — duck-typed to what `_market_row` / `_classify_kind` actually read
# ---------------------------------------------------------------------------


#: #8083 gave `_market_row` a per-outcome refusal, so an outcome fake now needs
#: the `id` the real column has. Counted rather than hashed: distinct ids keep
#: the fake honest about being distinct rows.
_OUTCOME_IDS = itertools.count(1)


def _outcome(name: str, prob: float, delta: float = 0.0):
    """`prob` here is the RAW 0-1 probability, as stored on FuturesOutcome."""
    return SimpleNamespace(
        id=next(_OUTCOME_IDS),
        name=name,
        current_probability=prob,
        probability_change_24h=delta,
    )


def _spotify_market(market_id: int, name: str, outcomes: list):
    # `kxspotify` is the ticker prefix `_classify_kind` maps to kind "spotify",
    # which is what routes a market into `spotify_race`.
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=f"kxspotify-{market_id}",
        source="kalshi",
        outcomes=outcomes,
        volume_24h=1000,
        resolution_date=None,
        updated_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        image_url=None,
        hook_description=None,
    )


def _race(*pairs):
    """Build the `themed` input for a Spotify race from (name, leading 0-1 prob) pairs."""
    markets = [
        _spotify_market(i + 1, name, [_outcome(f"Yes {i + 1}", prob)])
        for i, (name, prob) in enumerate(pairs)
    ]
    return {"music": markets}


def _probs(result):
    return [r["prob"] for r in result["spotify_race"]]


PRODUCTION_PAIR = (
    ("When will Spotify release 2026 Wrapped?", 0.86),
    ("Will Playboi Carti release BABY BOI this year?", 0.215),
)


# ---------------------------------------------------------------------------
# The production case, reproduced exactly
# ---------------------------------------------------------------------------


class TestSpotifyRowKeepsItsOwnNumber:
    def test_production_pair_publishes_its_own_probabilities(self):
        """The exact 2026-08-31 production pair: 86.0 and 21.5.

        NOT 0.8 / 0.2 (the shipped bug) and NOT 80.0 / 20.0 (the scale-only repair
        CERT-560 blocked — a share of an unrelated market's total).
        """
        result = _build_music(_race(*PRODUCTION_PAIR))
        assert _probs(result) == [86.0, 21.5]

    def test_the_headline_equals_the_market_s_own_leading_outcome(self):
        """The invariant that makes the whole class impossible to reintroduce.

        Whatever normalization anyone adds later, a row's headline and its own top
        outcome must not disagree — that disagreement is exactly what a reader sees.
        """
        result = _build_music(_race(*PRODUCTION_PAIR))
        for row in result["spotify_race"]:
            assert row["prob"] == row["top_outcomes"][0]["prob"], row["q"]

    def test_the_displayed_integer_matches_the_market_s_own_outcome(self):
        """The user-visible symptom, at display precision: `ProbPct` rounds.

        Stated as "never renders 0%" this would MISS the real production case — the
        shipped bug published 0.8 for the Wrapped market and `round(0.8)` is 1, so that
        row rendered `1%`, not `0%`. Only the Carti row (0.2) rendered `0%`. The
        invariant that catches both is that the printed integer must agree with the
        market's own outcome. (The battery's mutant A survived the weaker phrasing.)
        """
        result = _build_music(_race(*PRODUCTION_PAIR))
        for row in result["spotify_race"]:
            assert round(row["prob"]) == round(row["top_outcomes"][0]["prob"]), row["q"]

    def test_every_published_prob_stays_on_the_percent_scale(self):
        result = _build_music(_race(("A", 0.80), ("B", 0.60), ("C", 0.40), ("D", 0.30)))
        for p in _probs(result):
            assert 1.0 <= p <= 100.0, f"{p} is not a percent"

    def test_relative_ordering_is_preserved(self):
        result = _build_music(_race(("A", 0.80), ("B", 0.60), ("C", 0.40), ("D", 0.30)))
        probs = _probs(result)
        assert probs == sorted(probs, reverse=True)


class TestNoCrossMarketRescaling:
    """Every row is left alone, at every total — that is the point.

    The old code's threshold made the behaviour depend on what OTHER markets happened
    to be in the list. Each of these rows would have been rewritten under some version
    of that rule; none may be rewritten now.
    """

    def test_a_race_summing_far_over_100_is_untouched(self):
        # Under the 0-100 repair this became 44.4 / 33.3 / 22.2.
        result = _build_music(_race(("A", 0.80), ("B", 0.60), ("C", 0.40)))
        assert _probs(result) == [80.0, 60.0, 40.0]

    def test_a_race_summing_over_200_is_untouched(self):
        # A "gentler" rescale that only fires on wild totals is the same class of bug.
        # Without this row the battery's mutant C survives every behavioural guard and
        # is caught only by the structural one.
        result = _build_music(_race(("A", 0.90), ("B", 0.80), ("C", 0.70)))
        assert _probs(result) == [90.0, 80.0, 70.0]

    def test_a_race_summing_just_over_105_is_untouched(self):
        result = _build_music(_race(("A", 0.86), ("B", 0.215)))
        assert _probs(result) == [86.0, 21.5]

    def test_a_race_summing_under_100_is_untouched(self):
        result = _build_music(_race(("A", 0.08), ("B", 0.03)))
        assert _probs(result) == [8.0, 3.0]

    def test_a_single_market_race_is_untouched(self):
        # The 0-1 form turned a lone 42% market into 1.0; the 0-100 form into 100.0.
        result = _build_music(_race(("A", 0.42)))
        assert _probs(result) == [42.0]

    def test_adding_an_unrelated_market_does_not_move_the_others(self):
        """The defect stated as a property: a row must not depend on its neighbours."""
        alone = _probs(_build_music(_race(("Wrapped", 0.86))))
        with_neighbour = _probs(
            _build_music(_race(("Wrapped", 0.86), ("Unrelated", 0.215)))
        )
        assert alone[0] == with_neighbour[0] == 86.0


# ---------------------------------------------------------------------------
# Class guard — no 0-1 normalization threshold on a 0-100 `prob` field
# ---------------------------------------------------------------------------

# These three routes all normalize a field that `_market_row` (or its local equivalent)
# has already multiplied by 100, so any threshold they carry must be the percent one.
# `feed.py` is deliberately NOT in this list: `_normalize_feed_probabilities` operates on
# raw 0-1 probabilities, where `1.05` is the correct constant.
_PERCENT_SCALE_ROUTES = ("entertainment.py", "politics.py", "economics.py")

_ROUTES_DIR = Path(__file__).resolve().parents[1] / "app" / "routes"


def _strip_comments(source: str) -> str:
    """Return `source` with comments removed and all other tokens' text preserved.

    A source-scanning guard that does not do this fails on its own documentation — the
    rationale comment for this very fix quotes the banned `> 1.05` form — and the cheap
    way to make it pass is to delete the explanation.
    """
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            continue
        out.append(tok.string)
    return "\n".join(out)


class TestCommentStripper:
    """Non-vacuity, both directions: it must remove a comment AND keep the code."""

    def test_removes_a_comment(self):
        assert "1.05" not in _strip_comments("x = 1  # threshold was 1.05 once\n")

    def test_keeps_code_on_the_same_line_as_a_comment(self):
        stripped = _strip_comments("threshold = 105  # percent scale\n")
        assert "105" in stripped and "threshold" in stripped

    def test_keeps_a_string_literal_that_looks_like_a_comment(self):
        assert "1.05" in _strip_comments('s = "# 1.05"\n')


class TestPercentScaleThresholdClass:
    def test_no_route_on_the_percent_scale_uses_the_0_1_threshold(self):
        offenders = []
        for filename in _PERCENT_SCALE_ROUTES:
            path = _ROUTES_DIR / filename
            code = _strip_comments(path.read_text())
            if "1.05" in code:
                offenders.append(filename)
        assert not offenders, (
            f"{offenders} normalize a 0-100 `prob` field but still carry the feed's "
            f"0-1 threshold constant 1.05"
        )

    def test_the_guard_can_see_a_planted_offender(self):
        """Non-vacuity: the scan must actually fail when the 0-1 form is present."""
        planted = _strip_comments("if spotify_sum > 1.05:\n    pass\n")
        assert "1.05" in planted

    def test_entertainment_no_longer_rescales_across_markets_at_all(self):
        """A structural guard: the divisor itself is gone, not merely rescaled.

        Comments are stripped first, so this cannot be satisfied or broken by the
        rationale above the deleted block.
        """
        code = _strip_comments((_ROUTES_DIR / "entertainment.py").read_text())
        assert "spotify_sum" not in code


class TestOrderedEntertainmentBuckets12093:
    """#12093 (Defect 4): box office gross buckets and album sales ladders sit in
    quantity/threshold order rather than probability rank."""

    def test_box_office_gross_buckets_ordered_by_dollar_range(self):
        from app.routes.entertainment import _market_row

        market = _spotify_market(
            1,
            '"The Cat in the Hat" Opening Weekend Box Office',
            [
                _outcome("14m-16m", 0.30),
                _outcome("12m-14m", 0.25),
                _outcome("16m-18m", 0.18),
                _outcome("18m-20m", 0.12),
                _outcome("<12m", 0.09),
                _outcome("20m+", 0.06),
            ],
        )
        row = _market_row(market, max_outcomes=8)
        assert [o["name"] for o in row["top_outcomes"]] == [
            "<12m",
            "12m-14m",
            "14m-16m",
            "16m-18m",
            "18m-20m",
            "20m+",
        ]

    def test_album_sales_thresholds_ordered_by_threshold(self):
        from app.routes.entertainment import _market_row

        market = _spotify_market(
            2,
            "REBECCA: First Week Pure Album Sales",
            [
                _outcome("Above 4K", 0.90),
                _outcome("Above 8K", 0.65),
                _outcome("Above 5K", 0.60),
                _outcome("Above 6K", 0.55),
            ],
        )
        row = _market_row(market, max_outcomes=8)
        assert [o["name"] for o in row["top_outcomes"]] == [
            "Above 4K",
            "Above 5K",
            "Above 6K",
            "Above 8K",
        ]

    def test_named_contenders_preserve_probability_order(self):
        from app.routes.entertainment import _market_row

        market = _spotify_market(
            3,
            "Which movie has biggest opening weekend in 2026?",
            [
                _outcome("Avengers: Doomsday", 0.52),
                _outcome("Spider-Man: Brand New Day", 0.28),
                _outcome("Toy Story 5", 0.20),
            ],
        )
        row = _market_row(market, max_outcomes=8)
        assert [o["name"] for o in row["top_outcomes"]] == [
            "Avengers: Doomsday",
            "Spider-Man: Brand New Day",
            "Toy Story 5",
        ]


class TestBillboardThresholdGrouping12093:
    """#12093 (Defect 6): `_group_threshold_markets` groups only genuine threshold
    questions (matching `_THRESHOLD_NUM_RE`), leaving non-threshold song chart-week
    markets in `ungrouped` so Billboard Watch renders `BillboardHeatmap` instead of
    `"ALL I` headers in `RTHeatmap`."""

    def test_non_threshold_quoted_song_markets_remain_ungrouped(self):
        from app.routes.entertainment import _group_threshold_markets

        rows = [
            {
                "q": '"All I Want for Christmas Is You" #1 on Billboard Hot 100 for week of Dec 20?',
                "prob": 62.0,
                "market_id": 101,
                "image_url": None,
            },
            {
                "q": '"All I Want for Christmas Is You" #1 on Billboard Hot 100 for week of Dec 27?',
                "prob": 78.0,
                "market_id": 102,
                "image_url": None,
            },
        ]
        groups, ungrouped = _group_threshold_markets(rows)
        assert groups == []
        assert [r["market_id"] for r in ungrouped] == [101, 102]

    def test_threshold_markets_group_and_order_by_threshold_value(self):
        from app.routes.entertainment import _group_threshold_markets

        rows = [
            {
                "q": 'Will "Wicked: For Good" score at least 80 on Rotten Tomatoes?',
                "prob": 72.0,
                "market_id": 201,
                "image_url": None,
            },
            {
                "q": 'Will "Wicked: For Good" score at least 60 on Rotten Tomatoes?',
                "prob": 91.0,
                "market_id": 202,
                "image_url": None,
            },
            {
                "q": 'Will "Wicked: For Good" score at least 90 on Rotten Tomatoes?',
                "prob": 34.0,
                "market_id": 203,
                "image_url": None,
            },
        ]
        groups, ungrouped = _group_threshold_markets(rows)
        assert ungrouped == []
        assert len(groups) == 1
        assert [t["label"] for t in groups[0]["thresholds"]] == ["≥60", "≥80", "≥90"]


class TestEntertainmentAtlasGuards11949:
    """#11949 Order 10 + #12126/#12128 guards on /entertainment."""

    def test_one_winner_field_normalizes_only_when_exclusive_complete_and_at_least_90_pct(self):
        from app.routes.entertainment import _market_row

        m_norm = _spotify_market(
            10,
            "Best Picture Winner",
            [
                _outcome("Anora", 0.60),
                _outcome("The Brutalist", 0.40),
                _outcome("Conclave", 0.20),
            ],
        )
        m_norm.mutually_exclusive = True
        row_norm = _market_row(m_norm, max_outcomes=6)
        assert row_norm["prob"] == 50.0
        assert [o["prob"] for o in row_norm["top_outcomes"]] == [50.0, 33.3, 16.7]

        # Non-exclusive stays raw
        m_non_excl = _spotify_market(
            11,
            "Best Picture Nominees",
            [
                _outcome("Anora", 0.60),
                _outcome("The Brutalist", 0.40),
                _outcome("Conclave", 0.20),
            ],
        )
        m_non_excl.mutually_exclusive = False
        row_non_excl = _market_row(m_non_excl, max_outcomes=6)
        assert row_non_excl["prob"] == 60.0
        assert [o["prob"] for o in row_non_excl["top_outcomes"]] == [60.0, 40.0, 20.0]

    def test_blank_outcome_label_refused_and_missing_source_stays_none(self):
        from app.routes.entertainment import _market_row

        m = _spotify_market(
            12,
            "Best Director Winner",
            [
                _outcome("   ", 0.80),
                _outcome("Sean Baker", 0.55),
                _outcome("Brady Corbet", 0.45),
            ],
        )
        m.source = ""
        m.external_id = ""
        m.mutually_exclusive = True
        row = _market_row(m, max_outcomes=6)
        assert row is not None
        assert row["src"] is None
        assert [o["name"] for o in row["top_outcomes"]] == ["Sean Baker", "Brady Corbet"]
        # Blank outcome marks field incomplete so raw probabilities are preserved
        assert [o["prob"] for o in row["top_outcomes"]] == [55.0, 45.0]


