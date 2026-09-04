"""LAT-P224 equivalence guards for the Discover token derivations.

A cold Discover build derived `_discover_feature_tokens` twice per card on
identical arguments — once in the scoring loop, once again inside
`_discover_semantic_tokens`, which only filters it. The loop now derives it once
and hands it down, and the regional alias patterns are compiled at import
instead of per alias per call.

Both are no-ops, so what needs guarding is that they STAY no-ops: a served feed
whose tokens changed is a re-ordered feed, not a faster one. These tests are the
equivalence gate for that class.
"""

import re

import pytest

from app.routes.feed import (
    _REGIONAL_FEATURE_ALIAS_PATTERNS,
    _REGIONAL_FEATURE_ALIASES,
    _discover_feature_tokens,
    _discover_semantic_tokens,
)

# Deliberately wide: sports matchups, the regional aliases, championship
# language, entity bigrams, macro/AI/election topic hits, and the degenerate
# inputs (empty, None, punctuation-only) that a real pool contains.
TOKEN_BATTERY = [
    ("Tampa Bay Rays vs Boston Red Sox", "baseball", "event"),
    ("Buffalo Bills vs New England Patriots", "football", "event"),
    ("Boston Celtics vs Miami Heat", "basketball", "event"),
    ("Who will win the Massachusetts Governor election?", "politics", "futures"),
    ("Will the Fed cut rates in December?", "economics", "futures"),
    ("Will OpenAI release GPT-6 this year?", "tech", "futures"),
    ("Will Noah Kahan be #1 on Spotify this week?", "entertainment", "futures"),
    ("Chilean Primera Division champion", "soccer", "futures"),
    ("Who wins the Chilean league?", "soccer", "futures"),
    ("Vermont v. New Hampshire", "politics", "futures"),
    ("Maine Senate primary winner", "politics", "futures"),
    ("Rhode Island turnout over 40%?", "politics", "futures"),
    ("Connecticut Governor 2026", "politics", "futures"),
    ("Bruins win the Stanley Cup", "hockey", "futures"),
    ("2026 NBA Champion", None, "futures"),
    ("Bostonian bostonia bostons", "other", "futures"),  # boundary, must NOT match
    ("", "other", "futures"),
    ("   ", None, None),
    ("!!!", "", "event"),
    (None, None, None),
]


@pytest.mark.parametrize("item_name,category,item_type", TOKEN_BATTERY)
def test_semantic_tokens_identical_whether_features_are_handed_in(
    item_name, category, item_type
):
    """Handing the feature set in must produce exactly what deriving it does."""
    derived_inline = _discover_semantic_tokens(
        item_name=item_name,
        category=category,
        item_type=item_type,
    )
    features = _discover_feature_tokens(
        item_name=item_name,
        category=category,
        item_type=item_type,
    )
    handed_in = _discover_semantic_tokens(
        item_name=item_name,
        category=category,
        item_type=item_type,
        feature_tokens=features,
    )

    assert handed_in == derived_inline


@pytest.mark.parametrize("item_name,category,item_type", TOKEN_BATTERY)
def test_handed_in_feature_set_is_not_mutated(item_name, category, item_type):
    """The caller reuses the set it passes — the callee may read it, never write it."""
    features = _discover_feature_tokens(
        item_name=item_name,
        category=category,
        item_type=item_type,
    )
    before = set(features)

    _discover_semantic_tokens(
        item_name=item_name,
        category=category,
        item_type=item_type,
        feature_tokens=features,
    )

    assert features == before


def test_handing_features_in_skips_the_second_derivation(monkeypatch):
    """The whole point: the duplicate derivation must actually stop happening."""
    import app.routes.feed as feed_module

    calls = []
    real = feed_module._discover_feature_tokens

    def counting(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(feed_module, "_discover_feature_tokens", counting)

    features = feed_module._discover_feature_tokens(
        item_name="Boston Celtics vs Miami Heat",
        category="basketball",
        item_type="event",
    )
    assert len(calls) == 1

    feed_module._discover_semantic_tokens(
        item_name="Boston Celtics vs Miami Heat",
        category="basketball",
        item_type="event",
        feature_tokens=features,
    )
    assert len(calls) == 1, "supplying feature_tokens must not re-derive them"

    feed_module._discover_semantic_tokens(
        item_name="Boston Celtics vs Miami Heat",
        category="basketball",
        item_type="event",
    )
    assert len(calls) == 2, "omitting feature_tokens must still derive them"


def test_precompiled_alias_patterns_cover_the_alias_list_in_order():
    """Derived from the alias list, so a new alias can never lose its patterns.

    Asserted as a relationship, not a count: the list is expected to grow.
    """
    assert len(_REGIONAL_FEATURE_ALIAS_PATTERNS) == len(_REGIONAL_FEATURE_ALIASES)

    for (alias, region_tokens), (pattern, compiled_tokens) in zip(
        _REGIONAL_FEATURE_ALIASES, _REGIONAL_FEATURE_ALIAS_PATTERNS
    ):
        assert compiled_tokens == region_tokens
        assert pattern.pattern == rf"\b{re.escape(alias)}\b"
        assert pattern.flags == re.compile(rf"\b{re.escape(alias)}\b").flags


@pytest.mark.parametrize("item_name,category,item_type", TOKEN_BATTERY)
def test_precompiled_alias_patterns_match_the_runtime_built_ones(
    item_name, category, item_type
):
    """Same aliases fire, same regions, on the same lowered text."""
    lower = (item_name or "").lower()

    runtime_hits = {
        alias
        for alias, _tokens in _REGIONAL_FEATURE_ALIASES
        if re.search(rf"\b{re.escape(alias)}\b", lower)
    }
    compiled_hits = {
        alias
        for (alias, _tokens), (pattern, _t2) in zip(
            _REGIONAL_FEATURE_ALIASES, _REGIONAL_FEATURE_ALIAS_PATTERNS
        )
        if pattern.search(lower)
    }

    assert compiled_hits == runtime_hits

    expected_regions: set[str] = set()
    for alias, tokens in _REGIONAL_FEATURE_ALIASES:
        if alias in runtime_hits:
            expected_regions.update(tokens)

    produced = _discover_feature_tokens(
        item_name=item_name,
        category=category,
        item_type=item_type,
    )
    assert expected_regions <= produced


def test_region_aliases_still_respect_word_boundaries():
    """The precompile must not silently widen matching to substrings."""
    tokens = _discover_feature_tokens(
        item_name="Bostonian bostonia bostons",
        category="other",
        item_type="futures",
    )

    assert not {t for t in tokens if t.startswith("region:")}
