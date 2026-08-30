"""Convert a Python regex into SQL ILIKE patterns that are a safe SUPERSET.

Why this exists
---------------
The playoff-grid reader pushes each league's ``league_name_patterns`` down to
SQL as an ILIKE prefilter, so it does not have to load every market in a sport
category before deciding league membership.  The authoritative decision is
still made in Python afterwards (``_market_passes_league_filter`` re-applies
the real ``re`` patterns), so the ILIKE has exactly one correctness
obligation:

    **It must never be NARROWER than the regex it came from.**

A narrower pattern silently removes rows before the real matcher ever sees
them.  A wider one costs a few extra rows that Python then rejects.  So every
construct this module cannot represent is widened to ``%`` rather than dropped
or transliterated.

The bug that motivated it
-------------------------
The previous inline converter stripped ``\\b`` and ``\\s`` in one pass::

    re.sub(r"\\\\[bs]", "", r"\\bLa\\s+Liga\\b")   # -> "La+Liga"

and only then tried to turn ``\\s+`` into ``%`` — but ``\\s`` was already gone,
leaving a bare ``+``.  ``La+Liga`` is a literal, and no market is named that,
so the condition was false for every row.  It failed silently and totally:
``ILIKE`` is total on text, so there is no error, no warning and no log line —
just a league whose grid renders a tidy "no championship odds available yet"
over markets that exist and are priced.  Every multi-word pattern in every
league config was affected; only the single-word ones (``\\bNBA\\b``) worked.

The lesson generalised: **a prefilter that cannot match is indistinguishable
from an empty database.**  Hence ``ilike_can_match_literal`` below, which the
guard test uses to assert every emitted pattern can still match the plain text
its own regex was written for.
"""

from __future__ import annotations

import re

__all__ = ["regex_to_ilike", "ilike_can_match_literal"]


# Regex constructs that carry no literal text and can simply be deleted:
# anchors and word/string boundaries.
_ZERO_WIDTH = re.compile(r"\\[bBAZzG]")

# Constructs that stand for "some characters here" and must widen to `%`:
#   \s+ \s* \s   \d+ \w* …  and any character class or group.
_WIDEN_ESCAPE = re.compile(r"\\[sdwSDWN][+*?]?")
_WIDEN_GROUP = re.compile(r"\((?:\?[:=!][^()]*|[^()]*)\)[+*?]?")
_WIDEN_CLASS = re.compile(r"\[[^\]]*\][+*?]?")

# A literal escaped by a backslash: \. \- \/ → the character itself.
_ESCAPED_LITERAL = re.compile(r"\\(.)")

# A bare `.` (any char), optionally quantified, and any leftover quantifier
# applied to a literal — all widen.
_WIDEN_DOT = re.compile(r"\.[+*?]?")
_TRAILING_QUANT = re.compile(r"(?<=[^%])[+*?]")

_COLLAPSE = re.compile(r"%{2,}")


def regex_to_ilike(pattern: str) -> str:
    """Return an ILIKE body (no surrounding ``%``) that is a superset of ``pattern``.

    Returns ``""`` when nothing literal survives — the caller must treat that
    as "this pattern cannot be pushed to SQL" and fall back to a wider filter,
    never as "this pattern matches nothing".
    """
    s = pattern

    # Order matters and is the whole point of this module: widen the
    # whitespace/class escapes BEFORE deleting the zero-width ones, so `\s+`
    # is still recognisable as `\s+` when we reach it.
    s = _WIDEN_GROUP.sub("%", s)
    s = _WIDEN_CLASS.sub("%", s)
    s = _WIDEN_ESCAPE.sub("%", s)
    s = _ZERO_WIDTH.sub("", s)

    # Remaining backslash escapes are literals (`\.` → `.`).
    s = _ESCAPED_LITERAL.sub(r"\1", s)

    # `.` is regex any-char; `_` would demand exactly one character, so widen
    # to `%` (zero-or-more) to stay a superset.
    s = _WIDEN_DOT.sub("%", s)

    # Any quantifier still attached to a literal (`Liga+`) means "one or more
    # of that literal" — the literal itself is still required, so keep it and
    # drop only the quantifier.
    s = _TRAILING_QUANT.sub("", s)

    # Leftover grouping/anchor punctuation carries no literal text.
    s = s.translate({ord(c): None for c in "()[]^$|"})

    # SQL wildcards inside the source pattern would be taken literally by the
    # caller's f-string; escape them so they match themselves.
    s = s.replace("_", r"\_")

    s = _COLLAPSE.sub("%", s).strip()

    # A pattern that reduced to nothing but wildcards constrains nothing.
    if not s.strip("%").strip():
        return ""
    return s


def ilike_can_match_literal(ilike_body: str, text: str) -> bool:
    """True when ``ILIKE '%<ilike_body>%'`` would match ``text``.

    Used by the guard test to prove an emitted pattern is still capable of
    matching the plain-language name its regex was written for. This is the
    assertion the original bug could not fail.
    """
    if not ilike_body:
        return False
    parts = [re.escape(p.replace(r"\_", "_")) for p in ilike_body.split("%")]
    return re.search(".*".join(parts), text, re.IGNORECASE) is not None
