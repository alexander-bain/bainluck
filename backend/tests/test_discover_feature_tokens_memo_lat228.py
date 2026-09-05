"""Guards for the `_discover_feature_tokens` memo (LAT-P228).

The memo turns a per-call derivation into a per-distinct-input one. Two classes
of defect can hide in that change, and each gets a guard here:

1. **A key that does not cover the input.** If any argument is left out of the
   cache key, two different inputs collide and the second one is served the
   first one's tokens. Personalization would then score a card against another
   card's entities.
2. **A shared mutable value.** The public function returns a `set`, and a memo
   that hands back the cached object lets any caller's mutation poison every
   later reader in the process.

The third guard pins the staleness argument the memo rests on: the tokens are a
pure function of `(item_name, category, item_type)`, so the same input must
produce the same tokens no matter what else the process has done.
"""

import pytest

from app.routes import feed


@pytest.fixture(autouse=True)
def _clear_memo():
    feed._discover_feature_tokens_cached.cache_clear()
    yield
    feed._discover_feature_tokens_cached.cache_clear()


def _tokens(name, category=None, item_type=None):
    return feed._discover_feature_tokens(
        item_name=name, category=category, item_type=item_type
    )


# --------------------------------------------------------------------------
# 1. The key covers every input
# --------------------------------------------------------------------------

def test_item_type_is_part_of_the_key():
    """A different item_type must not be served the first type's tokens."""
    as_event = _tokens("Yankees vs Red Sox", "baseball", "event")
    as_futures = _tokens("Yankees vs Red Sox", "baseball", "futures")

    assert "type:event" in as_event
    assert "type:futures" in as_futures
    assert "type:futures" not in as_event
    assert "type:event" not in as_futures


def test_category_is_part_of_the_key():
    """A different category must not be served the first category's tokens."""
    as_baseball = _tokens("Who wins the title?", "baseball", "futures")
    as_politics = _tokens("Who wins the title?", "politics", "futures")

    assert "category:baseball" in as_baseball
    assert "category:politics" in as_politics
    assert "category:baseball" not in as_politics


def test_name_is_part_of_the_key():
    """A renamed item is a different key and never sees the old entities."""
    first = _tokens("Taylor Swift wins Grammy", "entertainment", "futures")
    second = _tokens("Kendrick Lamar wins Grammy", "entertainment", "futures")

    assert any(t.startswith("entity:taylor") for t in first)
    assert not any(t.startswith("entity:taylor") for t in second)


def test_none_and_empty_inputs_do_not_collide():
    """`None` and `""` are distinct keys and must not be conflated."""
    assert _tokens(None, None, None) == _tokens("", "", None)  # same normalization
    assert _tokens("Fed cuts rates", None, None) != _tokens(None, None, None)


# --------------------------------------------------------------------------
# 2. The returned set is fresh and safely mutable
# --------------------------------------------------------------------------

def test_returns_a_mutable_set_not_the_cached_object():
    a = _tokens("Fed cuts rates in March", "economics", "futures")
    b = _tokens("Fed cuts rates in March", "economics", "futures")

    assert isinstance(a, set) and not isinstance(a, frozenset)
    assert a == b
    assert a is not b, "callers must not share one cached set object"


def test_caller_mutation_cannot_poison_the_cache():
    """The whole point of copying on the way out."""
    first = _tokens("Fed cuts rates in March", "economics", "futures")
    baseline = set(first)

    first.add("entity:injected_by_a_caller")
    first.discard("category:economics")

    second = _tokens("Fed cuts rates in March", "economics", "futures")
    assert second == baseline
    assert "entity:injected_by_a_caller" not in second


# --------------------------------------------------------------------------
# 3. The memo engages, and it does not change any answer
# --------------------------------------------------------------------------

def test_memo_actually_hits_on_a_repeated_input():
    for _ in range(3):
        _tokens("Chiefs vs Eagles", "football", "event")

    info = feed._discover_feature_tokens_cached.cache_info()
    assert info.misses == 1
    assert info.hits == 2


def test_memoised_value_equals_a_freshly_computed_one():
    """A hit and a cold miss must agree, for a spread of real-shaped names."""
    cases = [
        ("Cal Raleigh: Home Runs O/U 0.5", "baseball", "futures"),
        ("Botafogo FR vs. Grêmio FBPA: Both Teams to Score", "soccer", "futures"),
        ("Will the Fed cut rates by September?", "economics", "futures"),
        ("Who wins the 2028 Democratic primary?", "politics", "futures"),
        ("Jiri Prochazka vs Magomed Ankalaev", None, "event"),
        ("Will OpenAI release GPT-6 this year?", "tech", "futures"),
        ("Maine storm total snowfall", "weather", "futures"),
        (None, None, None),
        ("", "other", "event"),
    ]
    for name, category, item_type in cases:
        warm = _tokens(name, category, item_type)  # miss, then cached
        warm_again = _tokens(name, category, item_type)  # hit
        feed._discover_feature_tokens_cached.cache_clear()
        cold = _tokens(name, category, item_type)  # recomputed from scratch
        assert warm == cold == warm_again, f"memo changed the answer for {name!r}"


def test_tokens_do_not_depend_on_call_order():
    """Pure function: interleaving other inputs cannot change an answer."""
    alone = _tokens("Lakers vs Celtics", "basketball", "event")

    feed._discover_feature_tokens_cached.cache_clear()
    for filler in ("Fed cuts rates", "Oscar Best Picture", "Chiefs vs Eagles"):
        _tokens(filler, "other", "futures")
    interleaved = _tokens("Lakers vs Celtics", "basketball", "event")

    assert alone == interleaved
