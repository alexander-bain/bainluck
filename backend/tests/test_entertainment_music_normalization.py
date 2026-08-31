"""Spotify race probabilities are published as percents, not fractions.

`_market_row` puts `prob` on the 0-100 scale (`current_probability * 100`), and every
consumer of the entertainment payload reads it that way — `GenericMarketCard` renders it
through `ProbPct`/`EntProbBar` directly.  The music builder's normalization step was
written in the *feed's* 0-1 form (`sum > 1.05`, divide with no `* 100`), so it fired on
essentially every non-empty race and divided percents by a percent sum.  Measured on
production 2026-08-31, `GET /api/entertainment` published:

    spotify_race[0].prob = 0.8   while its own leading outcome read 86.0
    spotify_race[1].prob = 0.2   while its own leading outcome read 21.5

(86.0 + 21.5 = 107.5; each was divided by 107.5 and never scaled back up.)

Politics `_normalize_outcome_probs` and economics `_brackets_from_outcomes` implement the
same rule correctly on the 0-100 scale.  These tests pin the entertainment builder to that
rule, in both directions — it must normalize an over-100 race, and it must leave a race
that already sums sanely alone.
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


# ---------------------------------------------------------------------------
# The production case, reproduced exactly
# ---------------------------------------------------------------------------


class TestSpotifyRaceScale:
    def test_production_race_publishes_percents_not_fractions(self):
        """The exact 2026-08-31 production pair: 86.0 / 21.5 -> 80.0 / 20.0, not 0.8 / 0.2."""
        result = _build_music(
            _race(
                ("When will Spotify release 2026 Wrapped?", 0.86),
                ("Will Playboi Carti release BABY BOI this year?", 0.215),
            )
        )
        assert _probs(result) == [80.0, 20.0]

    def test_a_leading_market_never_renders_as_zero_percent(self):
        """The user-visible symptom: `ProbPct` rounds the published number for display.

        A market whose own leading outcome reads 86% must not be printed as 0%.
        """
        result = _build_music(
            _race(
                ("When will Spotify release 2026 Wrapped?", 0.86),
                ("Will Playboi Carti release BABY BOI this year?", 0.215),
            )
        )
        row = result["spotify_race"][0]
        assert row["top_outcomes"][0]["prob"] == 86.0  # the market's own reading
        assert round(row["prob"]) != 0, "headline rendered as 0% beside an 86% outcome"

    def test_normalized_race_sums_to_about_100(self):
        result = _build_music(
            _race(("A", 0.80), ("B", 0.60), ("C", 0.40), ("D", 0.30))
        )
        total = sum(_probs(result))
        assert 99.0 <= total <= 101.0, f"expected ~100%, got {total}%"

    def test_every_published_prob_stays_on_the_percent_scale(self):
        result = _build_music(
            _race(("A", 0.80), ("B", 0.60), ("C", 0.40), ("D", 0.30))
        )
        for p in _probs(result):
            assert 1.0 <= p <= 100.0, f"{p} is not a percent"

    def test_relative_ordering_is_preserved(self):
        result = _build_music(
            _race(("A", 0.80), ("B", 0.60), ("C", 0.40), ("D", 0.30))
        )
        probs = _probs(result)
        assert probs == sorted(probs, reverse=True)


class TestSpotifyRaceThreshold:
    """The other direction: a race that already sums sanely must be left ALONE.

    This is the direction the 0-1 threshold got wrong — `> 1.05` is true of any race
    containing a single market above 1.05%, so normalization fired unconditionally.
    """

    def test_sane_race_under_the_threshold_is_untouched(self):
        # 60 + 42 = 102: under 105, and deliberately NOT exactly 100.  A race that already
        # sums to 100 is useless here — normalizing it is the identity, so such a test
        # passes whether or not the threshold fires.  (The battery's mutant B survived
        # that version of this row.)
        result = _build_music(_race(("A", 0.60), ("B", 0.42)))
        assert _probs(result) == [60.0, 42.0]

    def test_race_at_exactly_105_is_untouched(self):
        result = _build_music(_race(("A", 0.65), ("B", 0.40)))
        assert _probs(result) == [65.0, 40.0]

    def test_small_race_well_under_100_is_untouched(self):
        """Two long shots must stay long shots, not get inflated or divided."""
        result = _build_music(_race(("A", 0.08), ("B", 0.03)))
        assert _probs(result) == [8.0, 3.0]

    def test_single_market_race_is_untouched(self):
        result = _build_music(_race(("A", 0.42)))
        assert _probs(result) == [42.0]


# ---------------------------------------------------------------------------
# Class guard — no 0-1 normalization threshold on a 0-100 `prob` field
# ---------------------------------------------------------------------------

# These three routes all normalize a field that `_market_row` (or its local equivalent)
# has already multiplied by 100, so their threshold must be the percent one.  `feed.py` is
# deliberately NOT in this list: `_normalize_feed_probabilities` operates on raw 0-1
# probabilities, where `1.05` is the correct constant.
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
