"""#2627 — /api/feed/tag-counts must answer in ONE category vocabulary.

The endpoint builds its response from two statements:

  * the events arm classifies `sports.key` with a hand-written CASE and emits a
    category name it chooses itself;
  * the futures arm emits `COALESCE(llm_sport_category, 'other')` — whatever the
    classifier stored.

The reader (`/categories`) then looks up ONE key per tile and reads both halves
off it. So the two arms are not merely adjacent — they must agree on how a
category is spelled, or a tile can only ever print one of its two numbers.

They did not agree. The CASE emitted the singular ``'motorsport'`` while every
motorsports row in the database is stored under the plural. The response
therefore described one category twice::

    "motorsport":  {"events": 1, "futures": 0}     <- the tile read this one
    "motorsports": {"events": 0, "futures": 142}   <- nobody read this one

and the Motorsport tile said "1 event" over 147 open markets, then (once that
one event finished) "No items".

The guard below does not pin the string ``motorsports``. It pins the property
that was violated: every category the events arm can emit must be a category the
futures arm can also emit — i.e. a real ``llm_sport_category`` — with ``other``
allowed as the shared catch-all. That is what makes it survive the next league
being added to the CASE, and it is red on the parent commit because
``motorsport`` is not an ``llm_sport_category`` at all.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.routes.feed import get_tag_counts
from app.utils.sport_keys import LLM_CATEGORY_TO_SPORT_PREFIX

# The futures arm's own catch-all, which by construction is not a classifier
# output and so is not in the canonical map.
SHARED_CATCH_ALL = "other"


@pytest.fixture(scope="module")
def handler_source() -> str:
    return inspect.getsource(get_tag_counts)


def _case_targets(source: str) -> list[str]:
    """Every category the events arm's CASE can emit.

    Anchored on ``THEN '<x>'`` rather than on any quoted string, so the prose in
    the surrounding comments — which necessarily names the old singular in order
    to explain the bug — cannot be mistaken for a target and cannot make this
    guard vacuous.
    """
    targets = re.findall(r"THEN\s+'([a-z_]+)'", source)
    if not targets:
        raise AssertionError(
            "found no THEN '<category>' targets in get_tag_counts — the events "
            "arm was rewritten into a shape this guard cannot read, so it is "
            "asserting nothing. Re-point the parser before trusting a pass."
        )
    return targets


def test_the_parser_sees_the_whole_case(handler_source: str) -> None:
    """A control: the scan must find the real, full arm, not a fragment of it."""
    targets = _case_targets(handler_source)
    # The CASE classifies 15 sport-key families plus an ELSE catch-all.
    assert len(targets) >= 15, targets
    for expected in ("football", "basketball", "baseball", "soccer", "tennis"):
        assert expected in targets, f"{expected} missing — parser read a fragment"


def test_every_events_arm_category_is_a_real_llm_category(handler_source: str) -> None:
    """The two arms of one response must be able to describe the same category.

    Red on the parent: ``motorsport`` is not a key of
    ``LLM_CATEGORY_TO_SPORT_PREFIX``, so the futures arm can never produce it and
    no tile can ever carry both numbers.
    """
    strays = [
        t
        for t in _case_targets(handler_source)
        if t != SHARED_CATCH_ALL and t not in LLM_CATEGORY_TO_SPORT_PREFIX
    ]
    assert strays == [], (
        "the events arm emits categories the futures arm cannot: "
        f"{strays}. A tile looks up one key and reads both halves off it, so a "
        "category spelled differently by the two arms loses one of its numbers."
    )


def test_motorsports_specifically_is_the_plural(handler_source: str) -> None:
    """The instance behind #2627, pinned by value.

    `test_every_events_arm_category_is_a_real_llm_category` already covers this,
    but only as long as the singular stays absent from the canonical map. This
    states the shipped answer outright so a future widening of that map cannot
    silently re-open the defect.
    """
    targets = _case_targets(handler_source)
    assert "motorsports" in targets
    assert "motorsport" not in targets


def test_the_singular_is_not_a_valid_category(handler_source: str) -> None:
    """The premise the guard above rests on — asserted, not assumed.

    Green on both arms. If ``motorsport`` were ever added to the canonical map,
    the class guard would quietly stop catching this bug; this fails loudly
    instead.
    """
    assert "motorsport" not in LLM_CATEGORY_TO_SPORT_PREFIX
    assert "motorsports" in LLM_CATEGORY_TO_SPORT_PREFIX


def test_the_futures_arm_still_emits_the_raw_classifier_value(
    handler_source: str,
) -> None:
    """Green on both arms.

    The whole argument above depends on the futures arm being the side that
    speaks the classifier's vocabulary. If it ever starts translating, the
    events arm is no longer obliged to match ``llm_sport_category`` and this
    guard's premise is gone.
    """
    assert "COALESCE(llm_sport_category, 'other') AS category" in handler_source
