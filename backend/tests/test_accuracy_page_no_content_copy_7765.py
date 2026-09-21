"""#7765: the 503 sentences say "accuracy", the word the nav gave the reader.

THE DEFECT. #7738 renamed the footer's only link to this page from
"Calibration" to "Accuracy" and moved the tab title with it. The refusal
sentences composed here still said *"Calibration data is temporarily
unavailable"* and *"Calibration data is being rebuilt and is not ready yet."* —
and they render when the page has NO content, so there is no Calibration Table,
no "what's a calibration curve?", nothing on screen that gives the word a
meaning. That is ``JARGON_BANS``' own clause: our pipeline's nouns are not the
reader's.

WHY THIS SUITE EXISTS ON THIS SIDE, WHEN A FRONTEND ONE ALREADY READS THIS FILE.
``accuracyPageNoContentStatesSpeakTheNavsWord7765.test.ts`` reads this module as
TEXT and pins the two literals. That catches an edit to these lines and nothing
else. The sentence a reader meets is the one ``unavailable_advice()`` RETURNS,
and the module's own header is explicit that this is the half no bundle scan can
see, because it is composed at runtime. A message built by a future branch — an
f-string, a reason-specific override, a value threaded in from config — would
satisfy the text scan and still print the banned noun.

So this asserts over the objects, through the lookup, including the unknown
reason branch that no end-to-end request can reach while only two call sites
exist. Same split ``test_calibration_refusal_advice_p1191.py`` already uses, and
its properties (the two refusals differ, no timing promise in the cautious half)
are unchanged by the noun and are still pinned there — this suite deliberately
does not restate them.

NOT ASSERTED HERE, ON PURPOSE: that the word is gone everywhere. It is not, and
should not be. The rendering page keeps it in all eight of its in-context uses,
each arriving with its meaning attached — the fence is the empty state, not the
vocabulary. The frontend suite carries that control.
"""

from __future__ import annotations

import pytest

from app.routes.calibration import (
    UNAVAILABLE_ADVICE,
    UNAVAILABLE_ADVICE_DEFAULT,
    unavailable_advice,
)

#: The pipeline noun, as a reader would meet it in any casing.
PIPELINE_NOUN = "calibration"

#: The word the footer now uses for this page (#7738), and therefore the only
#: one a reader has been shown by the time these sentences render.
READER_NOUN = "accuracy"


def _every_advice_sentence() -> list[tuple[str, str]]:
    """``(reason, sentence)`` for every refusal this module can produce.

    Includes the default under a synthetic reason, because the default is not
    merely one more entry: it is what EVERY unmapped reason resolves to, so a
    suite that walked only ``UNAVAILABLE_ADVICE.items()`` would leave the most
    reachable sentence on the page untested. The frontend's extractor made
    exactly that mistake against this file and its arity assertion caught it.
    """
    pairs = [(reason, message) for reason, (_, message) in UNAVAILABLE_ADVICE.items()]
    pairs.append(("<default>", UNAVAILABLE_ADVICE_DEFAULT[1]))
    # Non-vacuity: a refactor that empties or renames the map must redden here
    # rather than pass a loop over nothing.
    assert len(pairs) >= 2, f"expected the mapped reasons plus the default, got {pairs!r}"
    return pairs


@pytest.mark.parametrize("reason,sentence", _every_advice_sentence())
def test_no_refusal_sentence_hands_the_reader_the_pipeline_noun(reason, sentence):
    assert PIPELINE_NOUN not in sentence.lower(), (
        f"{reason!r} prints {PIPELINE_NOUN!r} to a reader looking at an empty page: "
        f"{sentence!r}"
    )


@pytest.mark.parametrize("reason,sentence", _every_advice_sentence())
def test_every_refusal_sentence_names_the_page_in_the_readers_word(reason, sentence):
    # The complement of the ban, and the reason it is worth its own assertion:
    # deleting the subject entirely ("Data is being rebuilt") would satisfy the
    # test above while telling a reader even less than the defect did.
    assert READER_NOUN in sentence.lower(), (
        f"{reason!r} never names what is unavailable in the reader's word: {sentence!r}"
    )


def test_the_sentence_an_unmapped_reason_resolves_to_is_clean_through_the_lookup():
    """The branch a reason added in 2027 falls into, read through the function.

    ``unavailable_advice`` is the only thing the route calls, so this is the
    value that actually reaches a reader. Asserting the constant alone would
    pass if the lookup grew a wrapper that decorated the message.
    """
    _, message = unavailable_advice("a_reason_added_in_2027")

    assert PIPELINE_NOUN not in message.lower()
    assert READER_NOUN in message.lower()
    assert message == UNAVAILABLE_ADVICE_DEFAULT[1]


def test_the_mapped_reason_is_clean_through_the_lookup_too():
    _, message = unavailable_advice("route_budget_exhausted")

    assert PIPELINE_NOUN not in message.lower()
    assert READER_NOUN in message.lower()
    # And it is still the TRANSIENT sentence, not the cautious default — the
    # distinction CAL-P1191 exists to protect. Pinned by identity rather than by
    # its words so this suite cannot drift into re-testing that suite's claim.
    assert message != UNAVAILABLE_ADVICE_DEFAULT[1]
