"""Guards for the regex -> ILIKE prefilter converter.

The class this defends: **a SQL prefilter that cannot match is
indistinguishable from an empty database.** ``ILIKE`` is total on text, so a
malformed pattern does not raise, warn or log — it just returns false for every
row, forever. The playoff grid then renders a tidy "no championship odds
available yet" over markets that are open, tier-1 and freshly priced.

The specimen: the previous inline converter stripped ``\\b`` and ``\\s`` in one
pass, so ``\\s+`` became a bare ``+`` before the ``\\s+ -> %`` rule could fire.
``\\bLa\\s+Liga\\b`` compiled to ``%La+Liga%``. The SQL differs from the correct
form by one character and the broken one reads perfectly well.
"""

import re

import pytest

from app.config.league_configs import LEAGUE_CONFIGS
from app.utils.regex_to_ilike import ilike_can_match_literal, regex_to_ilike


class TestConverterProducesMatchablePatterns:
    """The assertion the original bug could not fail."""

    @pytest.mark.parametrize(
        "pattern,sample",
        [
            (r"\bLa\s+Liga\b", "La Liga Champion"),
            (r"\bLa\s+Liga\b", "La Liga Winner"),
            (r"\bChampions\s+League\b", "Champions League Winner"),
            (r"\bPremier\s+League\b", "English Premier League Champion"),
            (r"\bUEFA\s+Champions\b", "UEFA Champions League Winner"),
            (r"\bNBA\b", "NBA Champion"),
            (r"\bSuper\s+Bowl\b", "Super Bowl Champion"),
            (r"\bMajor\s+League\s+Baseball\b", "Major League Baseball Champion"),
            (r"\bU\.?S\.?\s+Open\b", "U.S. Open Winner"),
            (r"\bWomen.?s\s+(?:NBA|Basketball)\b", "Women's Basketball Champion"),
            (r"\bAL\s+(?:East|West|Central)\b", "AL East Winner"),
        ],
    )
    def test_emitted_pattern_matches_a_name_the_regex_matches(self, pattern, sample):
        # Precondition: the sample really is something the regex accepts, so a
        # failure below is the converter's fault and not the sample's.
        assert re.search(pattern, sample, re.IGNORECASE), "bad test sample"
        body = regex_to_ilike(pattern)
        assert body, f"{pattern!r} produced an empty ILIKE body"
        assert ilike_can_match_literal(body, sample), (
            f"ILIKE '%{body}%' cannot match {sample!r} — the prefilter would "
            f"hide every row the regex accepts"
        )

    def test_the_original_defect_is_reproduced_and_fixed(self):
        """`\\s+` must become `%`, not a literal `+`."""
        body = regex_to_ilike(r"\bLa\s+Liga\b")
        assert body == "La%Liga"
        assert "+" not in body
        # And the shape that shipped for years is provably unmatchable.
        assert not ilike_can_match_literal("La+Liga", "La Liga Champion")


class TestConverterIsASuperset:
    """Narrower is a silent data-loss bug; wider only costs a few rows."""

    @pytest.mark.parametrize(
        "pattern,sample",
        [
            # An alternation cannot be expressed in one ILIKE, so it must widen
            # to `%` rather than emit one arm and drop the other.
            (r"\bSpanish\s+(?:League|Football)\b", "Spanish Football Champion"),
            (r"\bSpanish\s+(?:League|Football)\b", "Spanish League Champion"),
            (r"\bGerman\s+(?:League|Football)\b", "German League Winner"),
            (r"\bNL\s+(?:East|West|Central)\b", "NL Central Winner"),
            # `.` is any-char and must widen to `%`, never be deleted.
            (r"\bWomen.s\s+NCAA\b", "Women's NCAA Champion"),
        ],
    )
    def test_unrepresentable_constructs_widen_rather_than_narrow(self, pattern, sample):
        assert re.search(pattern, sample, re.IGNORECASE), "bad test sample"
        body = regex_to_ilike(pattern)
        assert ilike_can_match_literal(body, sample)

    def test_a_pattern_with_no_literal_text_returns_empty_not_a_wrong_pattern(self):
        # The caller must widen to the whole category rather than push down a
        # pattern that constrains nothing meaningful.
        assert regex_to_ilike(r"\b\w+\b") == ""
        assert regex_to_ilike(r"^.*$") == ""

    def test_no_regex_metacharacter_survives_into_the_ilike(self):
        for slug, cfg in LEAGUE_CONFIGS.items():
            for pattern in cfg.league_name_patterns or []:
                body = regex_to_ilike(pattern)
                residue = set(body) & set("+|()[]^$?")
                assert not residue, (
                    f"{slug}: {pattern!r} -> {body!r} kept regex metacharacters "
                    f"{sorted(residue)}, which ILIKE reads as literal text"
                )


class TestEveryConfiguredLeaguePatternIsPushable:
    """Repo-wide sweep: no league may carry a pattern that cannot match.

    This is the guard that would have caught the bug on the day it shipped.
    """

    def test_every_league_name_pattern_emits_a_usable_or_explicitly_empty_body(self):
        for slug, cfg in LEAGUE_CONFIGS.items():
            for pattern in cfg.league_name_patterns or []:
                body = regex_to_ilike(pattern)
                if body == "":
                    continue  # caller widens to the whole category — safe
                # A body that still contains a quantifier or alternation is a
                # literal in SQL and is almost certainly unmatchable.
                assert not re.search(r"[+|?]", body), (
                    f"{slug}: {pattern!r} -> ILIKE '%{body}%' is unmatchable"
                )
