"""`/api/feed/tag-counts` must return ONE category vocabulary, not two.

## the defect

The route merges two statements into a single ``{"counts": {...}}`` map. The
futures half emits ``COALESCE(llm_sport_category, 'other')`` — the category
column, verbatim. The events half has no such column, so it derives a label
from ``sports.key`` with a hardcoded ``CASE``. Those two halves are free to
disagree, and for motor racing they did::

    WHEN s.key LIKE 'motorsport_%' ... THEN 'motorsport'   -- events half
    COALESCE(llm_sport_category, 'other')                  -- futures half, 'motorsports'

so one payload carried two sibling keys for one sport::

    {"motorsport":  {"events": N, "futures": 0},
     "motorsports": {"events": 0, "futures": M}}

The `/categories` tile keys on one of them and therefore could never show the
other's count. Measured on production 2026-08-30: 145 open ``motorsports``
futures, and a Motorsport tile reading zero.

The singular/plural split is not a typo — it is the codebase's real convention.
``motorsport_f1`` is a SPORT KEY; ``motorsports`` is a CATEGORY.
``sport_keys.py`` carries both translation dicts. The events half was emitting
the sport-key spelling into the category namespace.

## what this guards

Not the one token. The general property: **every label the events half invents
must be a label the futures half could also produce**, because they are merged
into one keyspace. A new ``WHEN`` arm spelling a category the classifier never
writes reintroduces the same class of split, silently — the payload stays
well-formed and the tile just reads zero.

Alex ruling D9, 2026-08-30: "every category with open markets gets a tile,
ordered by size; motorsport naming fixed."
"""

import re

from app.services.llm import SPORT_CATEGORIES
from app.utils.event_taxonomy import ALLOWED_TAGS

# The handler's source is the subject. Reading the module file (rather than
# `inspect.getsource`) keeps the guard honest if the statement is ever moved
# behind a helper.
import app.routes.feed as feed_module


def _events_half_case_labels() -> set[str]:
    """Every literal this route's events statement can emit as a category."""
    source = open(feed_module.__file__, encoding="utf-8").read()

    # Bound the search to the tag-counts handler so an unrelated CASE elsewhere
    # in this 9k-line module cannot satisfy — or pollute — the assertion.
    start = source.index("async def get_tag_counts")
    end = source.index("return {\"counts\": counts}", start)
    handler = source[start:end]

    # `WHEN ... THEN 'label'` plus the trailing `ELSE 'other'`.
    labels = set(re.findall(r"THEN\s+'([a-z_]+)'", handler))
    labels |= set(re.findall(r"ELSE\s+'([a-z_]+)'", handler))
    return labels


def test_the_extraction_is_not_vacuous():
    """A guard that finds nothing must fail, not pass.

    If the statement is rewritten in a shape this regex cannot read, the
    vocabulary assertion below would go quietly green over an empty set.
    """
    labels = _events_half_case_labels()
    assert len(labels) >= 10, f"expected the CASE arms, extracted only {labels!r}"
    # Anchors that must survive any rewrite of the statement.
    assert {"football", "basketball", "baseball", "other"} <= labels


def test_events_half_emits_only_real_category_values():
    """Both halves of one payload speak one vocabulary."""
    labels = _events_half_case_labels()

    # The classifier's own vocabulary is the definition of a category value:
    # it is exactly the set `llm_sport_category` is ever written from.
    known = set(SPORT_CATEGORIES) | ALLOWED_TAGS["sport"] | {"other"}

    offenders = sorted(labels - known)
    assert not offenders, (
        "the events half of /api/feed/tag-counts emits category labels the "
        "futures half can never produce, so each one becomes an orphan key in "
        f"the merged payload: {offenders}. Emit the llm_sport_category "
        "spelling (plural 'motorsports'), not the sport-key prefix "
        "(singular 'motorsport_f1')."
    )


def test_motor_racing_uses_the_category_spelling_not_the_sport_key_spelling():
    """The specific regression, pinned by name."""
    labels = _events_half_case_labels()
    assert "motorsports" in labels, (
        "the events half must emit the CATEGORY spelling so its count merges "
        "with the futures half"
    )
    assert "motorsport" not in labels, (
        "'motorsport' is the SPORT-KEY prefix (motorsport_f1), not a category. "
        "Emitting it into the category keyspace splits motor racing across two "
        "keys and zeroes the tile."
    )


def test_the_two_spellings_are_still_distinct_concepts():
    """Guard the fix from being 'simplified' by collapsing both spellings.

    The prefix must stay singular; only the category is plural. If someone
    renames the sport-key prefix to match, prefix matching breaks everywhere.
    """
    from app.utils.sport_keys import (
        LLM_CATEGORY_TO_SPORT_PREFIX,
        SPORT_PREFIX_TO_LLM_CATEGORY,
    )

    assert SPORT_PREFIX_TO_LLM_CATEGORY["motorsport"] == "motorsports"
    assert LLM_CATEGORY_TO_SPORT_PREFIX["motorsports"] == "motorsport"
