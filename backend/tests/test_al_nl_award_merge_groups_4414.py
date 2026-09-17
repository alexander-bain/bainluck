"""#4414 — an AL/NL award race must not render twice with two numbers.

THE DEFECT, on screen. Event 15313117 (NYY @ MIN), Season Futures → Ben Rice:

    AL MVP     1%
    AL MVP    <1%

Behind the two rows: Kalshi market 216 `AL MVP Winner?` (0.0100) and Polymarket
market 132768 `MLB: 2026 AL MVP` (0.0095). Both clean to the SAME label,
"AL MVP" — the normalizer was never the gap. `get_merge_group` returned None for
both, because the award rules take an optional FOUR-LETTER LEAGUE prefix
(`NBA MVP`, `NFL MVP`) and an MLB award is scoped by league WITHIN the sport.

THE RIDER THAT SHAPES THE FIX. Adding `AL|NL` to that prefix alternation would
map `AL MVP` and `NL MVP` both to `mvp` and fuse two genuinely different races.
That is strictly worse: a duplicate is visibly odd, a wrong merge is invisibly
wrong. So the league word is CAPTURED (`al_mvp` / `nl_mvp`), and
`test_al_and_nl_are_never_the_same_group` is the assertion that keeps it that
way.

WHY THE AWARD NAMES ARE ENUMERATED AND NOT MATCHED BY GRAMMAR. Measured on
production: 152 futures rows begin `AL ` or `NL `, and most of them are SOCCER
CLUBS arriving in uppercase — "AL Ahly SC (Egy) vs Club Africain", "AL Suqoor vs
Al-Fateh", "AL Wakrah SC vs. Al Rayyan SC", "AL Bataeh vs Al Ain". A
`^(AL|NL)\\s+(.+)$` rule would mint a merge group for every one of them.
`test_uppercase_al_clubs_gain_no_merge_group` is that population, by name.
"""

import pytest

from app.utils.market_label_normalization import get_merge_group, normalize_market_label
from app.utils.related_futures import dedup_by_merge_group


def mg(raw_name: str) -> str | None:
    """Merge group for a RAW venue name, through the same two calls the route makes."""
    return get_merge_group(normalize_market_label(raw_name))


# The measured cross-source pairs: (kalshi raw name, polymarket raw name).
# Trailing double spaces are verbatim from the `futures_markets.name` column.
MEASURED_PAIRS = [
    ("AL MVP Winner?", "MLB: 2026 AL MVP  "),
    ("NL MVP Winner?", "MLB: 2026 NL MVP"),
    ("AL Cy Young Winner?", "MLB: 2026 AL Cy Young Winner"),
    ("NL Cy Young Winner?", "MLB: 2026 NL Cy Young Winner"),
    ("AL Hank Aaron Award Winner?", "MLB: 2026 AL Hank Aaron Winner"),
    ("NL Hank Aaron Award Winner?", "MLB: 2026 NL Hank Aaron Winner"),
]

# Kalshi-only today, but the same league-scoped shape: a Polymarket twin must
# land in the group rather than mint a second row the day it is listed.
KALSHI_ONLY_AWARDS = [
    "AL Manager of the Year Winner?",
    "NL Manager of the Year Winner?",
    "AL Reliever of the Year Winner?",
    "NL Reliever of the Year Winner?",
    "AL Comeback Player of the Year Winner?",
    "NL Comeback Player of the Year Winner?",
    "AL All-Star Selection",
    "NL All-Star Selection",
]


class TestTheReaderDefect:
    def test_the_two_al_mvp_rows_now_share_one_merge_group(self):
        """The specimen from #4414, by its production raw names."""
        kalshi, poly = mg("AL MVP Winner?"), mg("MLB: 2026 AL MVP  ")
        assert kalshi == poly == "al_mvp"

    def test_the_label_was_never_the_gap(self):
        """Both sources already cleaned to one label — only the group was missing."""
        assert normalize_market_label("AL MVP Winner?") == "AL MVP"
        assert normalize_market_label("MLB: 2026 AL MVP  ") == "AL MVP"

    @pytest.mark.parametrize("kalshi_name,poly_name", MEASURED_PAIRS)
    def test_every_measured_cross_source_pair_merges(self, kalshi_name, poly_name):
        a, b = mg(kalshi_name), mg(poly_name)
        assert a is not None, f"{kalshi_name!r} still has no merge group"
        assert a == b, f"{kalshi_name!r} -> {a!r} but {poly_name!r} -> {b!r}"

    @pytest.mark.parametrize("raw_name", KALSHI_ONLY_AWARDS)
    def test_the_single_source_awards_are_grouped_too(self, raw_name):
        key = mg(raw_name)
        assert key is not None, f"{raw_name!r} still has no merge group"
        assert key.startswith(("al_", "nl_"))

    def test_hank_aaron_canonicalizes_across_two_spellings(self):
        """Kalshi says "Hank Aaron Award", Polymarket says "Hank Aaron".

        The labels differ, so the group key — not the label — is what has to
        agree. A `\\1_\\2` capture alone would have produced `al_hank_aaron_award`
        beside `al_hank_aaron` and left the duplicate on screen.
        """
        assert mg("AL Hank Aaron Award Winner?") == "al_hank_aaron"
        assert mg("MLB: 2026 AL Hank Aaron Winner") == "al_hank_aaron"


class TestScopeIsPreserved:
    """The half that matters more than the merge: AL ≠ NL, always."""

    @pytest.mark.parametrize("award", [
        "MVP Winner?",
        "Cy Young Winner?",
        "Rookie of the Year Winner?",
        "Manager of the Year Winner?",
        "Reliever of the Year Winner?",
        "Comeback Player of the Year Winner?",
        "Hank Aaron Award Winner?",
        "All-Star Selection",
    ])
    def test_al_and_nl_are_never_the_same_group(self, award):
        al, nl = mg(f"AL {award}"), mg(f"NL {award}")
        assert al is not None and nl is not None
        assert al != nl, f"AL and NL {award!r} collapsed into one race: {al!r}"
        assert al.startswith("al_") and nl.startswith("nl_")

    def test_two_leagues_of_one_award_survive_the_dedup_as_two_rows(self):
        """Keys alone are not the proof — run them through the route's dedup."""
        rows = [
            _row("al_mvp", "Ben Rice", "kalshi", 0.0100),
            _row("nl_mvp", "Ben Rice", "kalshi", 0.0400),
        ]
        assert len(dedup_by_merge_group(rows)) == 2


class TestNothingElseGainedAGroup:
    # Verbatim from `futures_markets.name` — clubs whose names arrive uppercase.
    @pytest.mark.parametrize("raw_name", [
        "AL Ahly SC (Egy) vs Club Africain",
        "AL Bataeh vs Al Ain",
        "AL Duhail vs Al Ahli Saudi",
        "AL Suqoor vs Al-Fateh",
        "AL Suqoor at Al Nassr: Spreads",
        "AL Suqoor vs Al Arabi Doha: Total Goals",
        "AL Wakrah SC vs. Al Rayyan SC",
        "AL Wakrah SC vs. Al-Shamal - Halftime Result",
    ])
    def test_uppercase_al_clubs_gain_no_merge_group(self, raw_name):
        assert mg(raw_name) is None, f"{raw_name!r} was minted a merge group"

    @pytest.mark.parametrize("raw_name", [
        "AL vs NL: Spread",
        "AL vs NL: Total Runs",
        "AL vs NL: First 5 Innings",
    ])
    def test_the_all_star_game_props_gain_no_merge_group(self, raw_name):
        assert mg(raw_name) is None, f"{raw_name!r} was minted a merge group"

    @pytest.mark.parametrize("raw_name,expected", [
        ("AL East Division Winner", "al_east"),
        ("MLB: 2026 AL East Champion", "al_east"),
        ("AL West Division Winner", "al_west"),
        ("NL Central Division Winner", "nl_central"),
        ("MLB: 2026 NL Central Champion ", "nl_central"),
        ("AL Champion", "al_champion"),
        ("NL Champion", "nl_champion"),
    ])
    def test_the_division_and_pennant_keys_are_unchanged(self, raw_name, expected):
        """These already worked. The new rules sit beside them and must not shadow."""
        assert mg(raw_name) == expected

    @pytest.mark.parametrize("raw_name,expected", [
        ("NBA MVP", "mvp"),
        ("NHL MVP", "mvp"),
        ("MLB MVP", "mvp"),
        ("NBA Finals MVP", "finals_mvp"),
        ("6th Man of the Year", "6moy"),
    ])
    def test_the_four_letter_league_awards_are_unchanged(self, raw_name, expected):
        assert mg(raw_name) == expected


class TestTheRowsCollapseOnThePage:
    """The defect is two ROWS, so the last assertion is about rows."""

    def test_ben_rice_renders_once_with_both_sources(self):
        rows = [
            _row("al_mvp", "Ben Rice", "kalshi", 0.0100),
            _row("al_mvp", "Ben Rice", "polymarket", 0.0095),
        ]
        out = dedup_by_merge_group(rows)
        assert len(out) == 1, [r["outcome_name"] for r in out]
        assert sorted(out[0]["all_sources"]) == ["kalshi", "polymarket"]

    def test_two_different_candidates_still_render_as_two_rows(self):
        """A merge group is not a licence to fuse the field into one row."""
        rows = [
            _row("al_mvp", "Ben Rice", "kalshi", 0.0100),
            _row("al_mvp", "Aaron Judge", "kalshi", 0.2200),
        ]
        assert len(dedup_by_merge_group(rows)) == 2

    def test_the_pair_was_two_rows_before_the_fix(self):
        """Non-vacuity: with no merge group these same rows do NOT collapse.

        Without this, every assertion above would still pass on a build where
        `dedup_by_merge_group` had quietly become a no-op.
        """
        rows = [
            _row(None, "Ben Rice", "kalshi", 0.0100),
            _row(None, "Ben Rice", "polymarket", 0.0095),
        ]
        assert len(dedup_by_merge_group(rows)) == 2


def _row(merge_group, outcome_name, source, probability):
    """A season-futures entry with the fields `dedup_by_merge_group` reads.

    `last_updated` is a fixed recent stamp resolved against an injected `now` in
    the caller's default — dedup only uses it to demote stale entries, and both
    sides of every pair here carry the same one, so freshness never decides.
    """
    return {
        "merge_group": merge_group,
        "outcome_name": outcome_name,
        "source": source,
        "probability": probability,
        "market_id": 216 if source == "kalshi" else 132768,
        "bookmaker_count": 1,
        "last_updated": None,
    }
