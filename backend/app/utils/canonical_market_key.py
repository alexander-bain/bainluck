"""What a ``FuturesMarket.canonical_market_key`` is allowed to be used for.

This module imports nothing, like ``sport_keys.py``, so both the feed route and
the interestingness precompute task can read one predicate without either
importing the other.

THE RULE (#6517). A canonical key of the shape ``<topic>::<generic>:<year>`` —
empty league segment, generic category — is a topic-and-year catch-all, not a
question. On 2026-09-16 ``politics::championship:2027`` held 1,422 rows: 1,419
Kalshi and 3 Polymarket, the Polymarket three being settled markets about EU
debt, Greenland and a Ukraine ceasefire. Two rows sharing that key are not two
views of one question, so the key cannot answer either of the questions its
readers ask of it:

* "are these the same card?" — feed dedupe, which has refused these keys since
  the guard was written; and
* "is this question carried by more than one venue?" — the source count behind
  ``multi_source``, which read the same key with NO guard until #6517 and so
  told "Which party will win the U.S. House?" that Polymarket corroborated it.

The second is the strictly stronger claim, so it may never be answered by a key
that is too weak for the first.
"""

#: Topic segments that are themselves a sport. These keys carry real league
#: structure elsewhere in the string, so the generic-category test below would
#: over-refuse them.
SPORTS_LIKE_TOPICS = frozenset(
    {
        "baseball",
        "basketball",
        "football",
        "golf",
        "hockey",
        "mma",
        "olympics",
        "soccer",
        "tennis",
    }
)

#: Category segments that name no question — every market in a topic-year lands
#: in one of these when nothing more specific was derived.
GENERIC_MARKET_CATEGORIES = frozenset(
    {"championship", "prediction", "other", "general"}
)


def canonical_key_identifies_one_question(key: str | None) -> bool:
    """True when ``key`` denotes a single question, not a topic-year bucket.

    Named for the property rather than for either caller: the same answer
    governs feed dedupe and venue-count attribution. A key with fewer than four
    segments is not one of the generated topic-year keys this guards against
    and is left alone.
    """
    if not key:
        return False
    parts = key.split(":")
    if len(parts) < 4:
        return True
    topic, league, category, _season = parts[:4]
    return bool(
        league
        or topic in SPORTS_LIKE_TOPICS
        or category not in GENERIC_MARKET_CATEGORIES
    )
