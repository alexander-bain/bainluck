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
import tokenize
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.routes.entertainment import _build_music


# ---------------------------------------------------------------------------
# Fakes — duck-typed to what `_market_row` / `_classify_kind` actually read
# ---------------------------------------------------------------------------


def _outcome(name: str, prob: float, delta: float = 0.0):
    """`prob` here is the RAW 0-1 probability, as stored on FuturesOutcome."""
    return SimpleNamespace(
        name=name, current_probability=prob, probability_change_24h=delta
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
