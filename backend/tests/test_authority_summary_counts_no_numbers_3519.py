"""The SERVED prose must not hard-code how many identity numbers there are.

PILLAR: MATCHING. SHIP: nothing goes blank when ESPN does — the agreement payload
is how anyone decides whether a sport may be failed over, and `FLIP_GATE_SUMMARY`
is its opening sentence, "the first thing anybody reading the payload reads".

#3519 published a third identity number and the summary still said "identity's
TWO numbers", so the payload's own guidance contradicted the payload. Nothing
caught it: every existing assertion checked what the summary *contains*, and this
is a defect of what it *claims*. The class is general — served prose that counts a
collection goes stale the moment the collection grows, and the count is exactly
the part no test looks at.

So these guards are about the SHAPE of the sentence, not this one wording.
"""

from __future__ import annotations

import re

import pytest

from app.utils.authority_agreement import (
    FLIP_GATE_SUMMARY,
    GATE_PENDING,
    IDENTITY_DENOMINATORS,
    governing_identity,
)

#: Words that assert "there are exactly N of them". `both` is included and is the
#: subtle one: it is not a numeral, it reads as natural English, and it claims a
#: count of two just as firmly as "two" does — it is the word the pre-#3519
#: PENDING verdict actually used.
COUNTING_WORDS = ("one", "two", "three", "four", "five", "both", "either")

#: A counting word QUALIFYING the word "number(s)" — not a counting word anywhere.
#:
#: The broad version of this guard is wrong and was written first. It red-flagged
#: "Five gate states", which is a true count of a different collection and is
#: pinned to its own constant, and "the ruling on which one decides", where `one`
#: is a pronoun. A guard that fires on correct prose gets the guard deleted, not
#: the prose fixed. So the pattern is scoped to the collection this is about, and
#: stops at a sentence boundary so a count in one clause cannot be blamed on a
#: noun in the next.
_COUNTED_NUMBER = re.compile(
    rf"\b({'|'.join(COUNTING_WORDS)})\b[^.;:]{{0,40}}?\bnumbers?\b", re.I
)


def _counting_words_in(text: str) -> list[str]:
    """Counting words that claim how many identity NUMBERS there are.

    Backticked identifiers are stripped first: `ours_covered_in_span_pct` and
    `identity.governing` are field names the summary exists to point at, not
    claims about quantity, and forbidding them would make this guard unobeyable.
    """
    prose = re.sub(r"`[^`]*`", "", text)
    return [m.group(1).lower() for m in _COUNTED_NUMBER.finditer(prose)]


def _pending_why(sport_key: str = "baseball_mlb") -> str:
    verdict = governing_identity(sport_key, {"both": 1, "pct": 100.0})
    assert verdict["gate"] == GATE_PENDING, "fixture must exercise the PENDING path"
    return verdict["why"]


@pytest.mark.parametrize(
    "name,text",
    [
        ("FLIP_GATE_SUMMARY", FLIP_GATE_SUMMARY),
        ("governing_identity(...)['why'] for a PENDING sport", _pending_why()),
    ],
)
def test_served_prose_does_not_count_identitys_numbers(name, text):
    """Both of these strings ship to whoever reads the endpoint.

    A count here is not a cosmetic slip: a reader told there are two numbers,
    looking at a row carrying three, has been told the payload is something other
    than what it is — and the whole purpose of the summary is to stop a reader
    scoring a sport on the wrong number.
    """
    found = _counting_words_in(text)
    assert not found, (
        f"{name} contains the counting word(s) {found}. Served prose must not "
        f"say how many identity numbers exist — there are "
        f"{len(IDENTITY_DENOMINATORS)} today and the sentence goes stale the "
        f"next time one is added. Say 'identity's published numbers' instead.\n"
        f"--- text ---\n{text}"
    )


def test_the_guard_fires_on_the_exact_wording_that_shipped():
    """The control. Without it this is a test that passes because it is toothless.

    These are the two strings verbatim as production served them before #3519's
    follow-up, and both MUST be caught — a detector that misses the real
    historical defect proves nothing about the next one.
    """
    shipped_summary = (
        "Identity governs; schedule and anchors are reported and gate nothing. "
        "WHICH of identity's two numbers scores a sport is per sport (D63)"
    )
    shipped_why = (
        "baseball_mlb has no governing identity number, so no daily row can "
        "advance its streak. Both numbers are still published below; what is "
        "missing is the ruling on which one decides."
    )

    assert "two" in _counting_words_in(shipped_summary)
    assert "both" in _counting_words_in(shipped_why)


@pytest.mark.parametrize(
    "innocent",
    [
        # A true count of a DIFFERENT collection, pinned to its own constant.
        "Five gate states: MEETS advances the streak, BELOW resets it",
        # `one` as a pronoun, not a quantity.
        "what is missing is the ruling on which one decides",
        # Field names the summary exists to point at.
        "read the verdict off `identity.governing`, which names the number(s)",
        # A count separated from `number` by a sentence boundary.
        "There are five gate states. The governing number is per sport.",
    ],
)
def test_the_guard_does_not_fire_on_correct_prose(innocent):
    """A guard that reds correct prose gets deleted, not obeyed.

    Each of these was a false positive of the first, broader version of this
    detector, and each is a sentence the payload should be free to say.
    """
    assert _counting_words_in(innocent) == []


def test_the_summary_still_tells_a_reader_where_the_verdict_is():
    """Removing the count must not remove the sentence's job.

    The paired risk of a de-counting edit: satisfy the guard above by deleting the
    clause instead of rewording it, leaving a summary that no longer routes the
    reader to the per-sport verdict — which is the mistake D63 exists to prevent.
    """
    assert "identity.governing" in FLIP_GATE_SUMMARY
    assert "per sport" in FLIP_GATE_SUMMARY
    assert "D63" in FLIP_GATE_SUMMARY
