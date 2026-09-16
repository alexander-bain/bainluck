"""The display form of a prediction-market question.

#3513: Polymarket publishes a GROUP TEMPLATE as the event title and a fully
written question for every member in the same payload. We ingest the template
into ``futures_markets.name``, so a Discover card asks the reader a question
with a hole in it — "Netanyahu out by...?", "Kraken IPO by ___ ?".

Measured on production 2026-09-16 02:2xZ (counted with a Postgres REGEX,
because a bare ``_`` is a LIKE wildcard and ``LIKE '%___%'`` matches any three
characters): **2,626 markets carry a blank — 372 open, 2,254 resolved.** Every
one of the 372 open rows is polymarket; no other source has one.

This module is the render-time half of that issue. It never reconstructs the
missing words — that is the ingest-side join against Polymarket's
``markets[].question`` / ``groupItemTitle``, which stays open on #3513. It has
two rules, and each one only fires on a shape that has been read end to end:

  TRAILING (``_strip_trailing_blank``) — removes a placeholder sitting at the
      END of the question together with the preposition that governed it.
      "Netanyahu out by...?" -> "Netanyahu out?".

  OBJECT SLOT (``_rewrite_object_slot``) — the blank is the direct object of a
      verb, so there is nothing to strip and deleting it in place leaves "Will
      EUR/USD hit in 2026?". The yes/no question becomes the wh-question it was
      always asking: "What will EUR/USD hit in 2026?". See that function.

🔴 POPULATIONS DELIBERATELY LEFT EXACTLY AS THEY ARE, because for them any
rewrite yields a card WORSE than the one it replaces:

  DIRECTIONAL (37 of the 52 open rows left) — "Amazon 2026 capex above ___?"
      "above" is not a locator, it is the comparison the ladder is made of.
      The rungs $305 · 92%, $310 · 84% are only coherent as "above $305"; drop
      the word and they read as "at $305" — 92% and 84% for two different exact
      prices, which is nonsense. A truthful-but-ugly headline would become a
      clean-looking lie, so this one waits for the join.

  ADJECTIVE SLOT (19 distinct names measured, 2 of them open) — "Will MrBeast
      hit ___ Billion views by June 30?", "Will USD hit ___ Iranian rials by
      March 31?", "Will Crude Oil (CL) hit__ Week of March 16?"
      These reach the object-slot pattern and are refused by its TAIL test: the
      blank qualifies the words after it rather than standing in for them, so
      the rewrite would print "What will MrBeast hit Billion views by June
      30?". Refused by a measured rule, not by a name list.

  EMBEDDED, everything else (13 of the 52 open rows left) — "Will any AI model
      reach ___ Overall Arena Score by December 31?", "Will Claude go down on
      __ days in September?": a blank mid-sentence under no rule here.

Applied to the live open population: 87 rows printed a hole after the trailing
rule alone, **52 after both** (37 + 2 + 13 above). That is the honest remainder
and it is what the ingest join is for; it is not a silent gap.

All three are pinned by CONTROL tests that assert byte-identity.

THE RULE THIS MODULE FOLLOWS: clean a name where it is **printed**, never where
it is **interpreted**. ``feed.py`` also passes ``market.name`` into
``humanize_binary_outcome_name``, ``_is_model_question`` and a ``\\bvs\\b``
probe — those read the name to make a decision, and normalising their input
would change behaviour rather than presentation. Call sites are listed in the
issue; this module is applied only at display boundaries.

Pure: imports ``re`` and nothing else, so any route may call it.
"""

import re

#: A template blank, wherever it sits. 2+ underscores rather than 3+ because
#: Polymarket writes both widths for the same template — "Anthropic IPO by __?"
#: and "Kraken IPO by ___ ?" are the same defect — and 3+ dots rather than
#: exactly 3 because two production names carry four.
_BLANK = r"(?:_{2,}|\.{3,})"

# The blank plus the question mark it swallowed. ``\Z`` anchors it to the end:
# an embedded blank (real text after it) never matches here, which is the
# EMBEDDED carve-out above and the reason the object-slot rule below exists.
_TRAILING_BLANK = re.compile(_BLANK + r"\s*(\??)\s*\Z")

# Measured over the 326 trailing-blank markets on production 2026-09-15, the
# governing word is one of exactly six, and every one is a preposition — there
# is not a verb among them. That is why dropping the word is safe HERE and
# would not be in general, and it is why this is a closed list rather than a
# part-of-speech rule: a pattern would reach names nobody has reasoned about.
#
# "above" is measured (15) and is deliberately ABSENT — see the module
# docstring. A word not on this list leaves the name untouched, i.e. exactly
# what a reader sees today, so the default of this allowlist is the status quo
# and never a plausible-looking wrong answer.
_STRIPPABLE_PREPOSITIONS = ("by", "on", "at", "through", "as")


# --- the object-slot rule (the second half of #3513) -------------------------
#
# 37 open markets (and 66 distinct resolved names) put the blank straight after
# a verb, where the trailing rule cannot reach it and deleting it in place
# yields "Will EUR/USD hit in 2026?", which is not a sentence. In 35 of the 37
# the blank is a true DIRECT OBJECT:
#
#     Will OpenAI's valuation hit __ by December 31?
#     What will Gold (GC) hit__ by end of December?
#
# The rewrite is a yes/no question turned into the wh-question it was always
# asking — "What will OpenAI's valuation hit by December 31?" — with the ladder
# supplying the candidate values. Nothing is dropped, so nothing becomes a lie:
# unlike "above", ``hit`` is not a comparator, it is the verb, and it survives.
#
# 🔴 THIS IS NOT OUR PHRASING. Polymarket publishes both forms for the same
# family: 558 of our rows (52 open) already arrive as "What will Fed Rate hit
# before 2027?", "What will S&P 500 (SPX) hit by end of December?", blank-free
# and from the same venue. The rewrite makes a holed row read like its own
# siblings — measured 2026-09-16, not invented here.
_OBJECT_SLOT_VERBS = ("hit",)

# The tail must open with a preposition, i.e. the blank really was the object
# and the sentence resumes with a when/where phrase. Measured over the 37:
# "by" and "in" are the only two that occur, and the other four are the same
# grammatical class ("...hit before 2027?" reads exactly as well). A word off
# this list means the blank was an ADJECTIVE slot in front of a noun —
# "hit ___ Million subscribers", "reach ___ Arena Score" — where the rewrite
# produces "What will MrBeast hit Million subscribers?" and is worse than the
# hole. 2 open rows are refused on exactly this, and 17 distinct resolved names
# the list was never written against — which is why it is a rule about the
# tail and not a list of names.
_OBJECT_SLOT_TAIL_OPENERS = ("by", "in", "on", "at", "before", "through")

_OBJECT_SLOT = re.compile(
    r"\A(?:Will|What will)\s+(?P<subject>.+?)\s+"
    r"(?P<verb>"
    + "|".join(_OBJECT_SLOT_VERBS)
    + r")\s*"
    + _BLANK
    + r"\s*(?P<tail>.*?)\s*\?\Z"
)


def _rewrite_object_slot(name: str) -> str:
    """Turn "Will X hit __ by D?" into "What will X hit by D?".

    Returns ``name`` byte-identical unless the whole shape matches: a
    ``Will``/``What will`` question, a measured verb, a blank sitting directly
    after that verb, and a tail that either is empty or opens with a measured
    preposition.
    """
    match = _OBJECT_SLOT.match(name.strip())
    if match is None:
        return name

    tail = match.group("tail")
    if tail and tail.split()[0].lower() not in _OBJECT_SLOT_TAIL_OPENERS:
        return name

    head = f"What will {match.group('subject')} {match.group('verb')}"
    return f"{head} {tail}?" if tail else f"{head}?"


def clean_market_display_name(name: str | None) -> str | None:
    """Return ``name`` with Polymarket's template blank gone.

    "Netanyahu out by...?"                     -> "Netanyahu out?"
    "Kraken IPO by ___ ?"                      -> "Kraken IPO?"
    "GPT-5.5 released on...?"                  -> "GPT-5.5 released?"
    "Will EUR/USD hit __ in 2026?"             -> "What will EUR/USD hit in 2026?"
    "What will Gold (GC) hit__ by end of December?"
                                               -> "What will Gold (GC) hit by end of December?"

    Anything this module does not positively recognise is returned UNCHANGED
    and byte-identical — including ``None``, the empty string, a name with no
    blank at all, an adjective-slot blank, and a directional "above" blank.
    """
    if not name:
        return name

    # Two rules in order, each returning its input byte-identical when it does
    # not recognise the shape. They cannot both fire: the trailing rule only
    # returns a changed string with the blank already gone, and the object-slot
    # pattern requires one.
    return _rewrite_object_slot(_strip_trailing_blank(name))


def _trailing_blank_parts(name: str) -> tuple[str, str, str] | None:
    """``(head, preposition, question_mark)`` when the trailing rule fires, else None.

    Split out of :func:`_strip_trailing_blank` for #6470, which needs the WORD
    this rule deletes rather than the string it leaves behind. One grammar with
    two readers rather than two grammars: a name whose blank is stripped here
    and a name whose deadline is named there are by construction the same set,
    so the caption can never restore a preposition the title still carries.
    """
    stripped = name.rstrip()
    match = _TRAILING_BLANK.search(stripped)
    if match is None:
        return None

    head = stripped[: match.start()].rstrip()
    lowered = head.lower()
    for preposition in _STRIPPABLE_PREPOSITIONS:
        if lowered.endswith(" " + preposition):
            head = head[: -(len(preposition) + 1)].rstrip()
            break
    else:
        # A blank we recognise governed by a word we have not measured. Leave
        # the name alone rather than guess: "X above?" reads worse than the
        # blank it replaced.
        return None

    head = head.rstrip(" ,;:-")
    if not head:
        # The question was nothing but a preposition and a blank. Nothing here
        # is better than an empty headline.
        return None

    return head, preposition, match.group(1) or ""


def _strip_trailing_blank(name: str) -> str:
    """The trailing-blank rule: drop the blank AND the preposition governing it."""
    parts = _trailing_blank_parts(name)
    if parts is None:
        return name
    head, _preposition, question_mark = parts
    return head + question_mark


def elided_trailing_preposition(name: str | None) -> str | None:
    """The preposition :func:`clean_market_display_name` DELETES, or ``None``.

    "Anthropic IPO by __?"              -> "by"
    "GPT-5.5 released on...?"           -> "on"
    "Amazon 2026 capex above ___?"      -> None   (not a strippable word)
    "Will Trump issue rebates by Election Day?"
                                        -> None   (no blank: nothing is elided)

    #6470 — this is the VENUE telling us what its outcome list means. Polymarket
    writes the group template as the market name and the members fill the slot,
    so "… by <blank>?" with a dated leg is that venue's own statement that the
    leg is a DEADLINE and not a window. That is the notice-26/27 standard —
    membership read off the venue's structure — rather than a guess from the
    shape of the label, which cannot tell "by December 31" from "during
    December" and must therefore stay silent.

    Returns the preposition exactly as it appears in
    :data:`_STRIPPABLE_PREPOSITIONS` (lower case), and ``None`` for every name
    this module leaves byte-identical. A caller may only act on a word it has
    reasoned about: the list is closed, but this function does NOT rank its
    members, so a caller wanting deadline semantics tests for ``"by"`` itself.
    """
    if not name:
        return None
    parts = _trailing_blank_parts(name)
    return None if parts is None else parts[1]
