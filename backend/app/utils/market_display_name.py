"""The display form of a prediction-market question.

#3513: Polymarket publishes a GROUP TEMPLATE as the event title and a fully
written question for every member in the same payload. We ingest the template
into ``futures_markets.name``, so a Discover card asks the reader a question
with a hole in it — "Netanyahu out by...?", "Kraken IPO by ___ ?".

Measured on production 2026-09-15 (``status='open'``, counted with ``strpos``
because a bare ``_`` is a LIKE wildcard): **362 markets carry a blank, 100% of
them polymarket** — 294 with ``...`` and 68 with ``___``. Eight of them render
on page one of the default landing page.

This module is the narrow, render-time half of that issue: it removes a
placeholder sitting at the END of the question together with the preposition
that governed it, so the card prints a question a person can read. It does NOT
reconstruct the missing words — that is the ingest-side join against
Polymarket's ``markets[].question`` / ``groupItemTitle``, which stays open on
#3513.

🔴 TWO POPULATIONS ARE DELIBERATELY LEFT EXACTLY AS THEY ARE, because for them
removing the blank yields a card WORSE than the one it replaces:

  EMBEDDED (36 measured) — "Will Apple (AAPL) close above ___ end of September?"
      The blank sits mid-sentence with real text after it. Dropping it gives
      "close above end of September", which is not a sentence.

  DIRECTIONAL (15 measured) — "Amazon 2026 capex above ___?"
      "above" is not a locator, it is the comparison the ladder is made of.
      The rungs $305 · 92%, $310 · 84% are only coherent as "above $305"; drop
      the word and they read as "at $305" — 92% and 84% for two different exact
      prices, which is nonsense. A truthful-but-ugly headline would become a
      clean-looking lie, so this one waits for the join.

Both are pinned by CONTROL tests that assert byte-identity.

THE RULE THIS MODULE FOLLOWS: clean a name where it is **printed**, never where
it is **interpreted**. ``feed.py`` also passes ``market.name`` into
``humanize_binary_outcome_name``, ``_is_model_question`` and a ``\\bvs\\b``
probe — those read the name to make a decision, and normalising their input
would change behaviour rather than presentation. Call sites are listed in the
issue; this module is applied only at display boundaries.

Pure: imports ``re`` and nothing else, so any route may call it.
"""

import re

# A blank is 3+ underscores or 3+ dots, optionally followed by the question
# mark it swallowed. ``\Z`` anchors it to the end: an embedded blank (real text
# after it) never matches, which is the EMBEDDED carve-out above.
# 3+ dots rather than exactly 3 because two production names carry four.
_TRAILING_BLANK = re.compile(r"(?:_{3,}|\.{3,})\s*(\??)\s*\Z")

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


def clean_market_display_name(name: str | None) -> str | None:
    """Return ``name`` with a trailing template blank and its preposition gone.

    "Netanyahu out by...?"        -> "Netanyahu out?"
    "Kraken IPO by ___ ?"         -> "Kraken IPO?"
    "GPT-5.5 released on...?"     -> "GPT-5.5 released?"

    Anything this module does not positively recognise is returned UNCHANGED
    and byte-identical — including ``None``, the empty string, a name with no
    blank at all, an embedded blank, and a directional "above" blank.
    """
    if not name:
        return name

    stripped = name.rstrip()
    match = _TRAILING_BLANK.search(stripped)
    if match is None:
        return name

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
        return name

    head = head.rstrip(" ,;:-")
    if not head:
        # The question was nothing but a preposition and a blank. Nothing here
        # is better than an empty headline.
        return name

    return head + (match.group(1) or "")
