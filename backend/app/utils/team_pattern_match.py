"""Token-boundary matching of ILIKE-escaped team patterns against a label.

THE SEAM (#6806). `_build_related_futures` (``routes/events.py``) asks two
questions about every candidate outcome: (1) does its name reach the SQL
candidate net, ``FuturesOutcome.name ILIKE '%<pattern>%'``, and (2) which side
of the fixture does it belong to, ``_matches_any(name, patterns)``. The second
answered by bare substring — ``clean.lower() in name_lower`` — so a short token
that merely OCCURS inside another club's name assigned that club's outcome:

    _team_name_patterns("Lech Poznań") -> ["Lech Poznań", "Poznań", "Lech"]
    'lech' in 'anderlecht'    -> True    (Belgian Pro League Champion, 6%)
    'lech' in 'lechia gdansk' -> True    (Ekstraklasa Champion, 1%)

Production 2026-09-17 served Anderlecht's price as Lech Poznań's championship
path (issue #6806); the 2026-09-18 public payload served Lechia Gdańsk beside
Lech (`artifacts/other-model-related-futures-identity-execution/inputs/`).

THE RULE. A pattern matches a label only where it occupies WHOLE TOKENS: the
character before the match must not be alphanumeric (or the match starts the
label), and the character after must not be alphanumeric (or the match ends
it). Each edge is only required when the pattern's own edge character is
alphanumeric — a pattern that ends in ``)`` or ``.`` already ends a token, and a
label like ``Miami (OH) RedHawks`` must keep matching ``Miami (OH)``.

    Lech        | Lech Poznan       -> match   (ends at a space)
    Lech        | Anderlecht        -> refused (interior)
    Lech        | Lechia Gdansk     -> refused (prefix of a longer token)
    Celtics     | Boston Celtics    -> match   (suffix, boundary before)
    Boston      | Boston Celtics    -> match   (prefix token)
    LA          | LA Clippers       -> match
    LA          | Atlanta Hawks     -> refused (the `LA` alias used to claim Atlanta)
    Saint-Étienne | AS Saint-Étienne -> match  (hyphen and accent sit INSIDE)
    100% Club   | 1000% Club        -> refused (the `%` is literal — see below)

ALPHANUMERIC IS UNICODE-AWARE (``str.isalnum``): ``ń``, ``é``, ``ş`` are letters,
so ``Pozna`` does NOT match ``Poznań`` — a diacritic-bearing letter is part of
its token, exactly as a plain one is. This module adds NO transliteration: an
accented event name against an unaccented label is unchanged behaviour, reached
(when it is reached) through whichever token both spellings share.

PATTERNS ARRIVE ILIKE-ESCAPED. ``_team_name_patterns`` and the alias/roster
loop write patterns through ``_escape_like`` (``\\`` -> ``\\\\``, ``%`` -> ``\\%``,
``_`` -> ``\\_``) because they are also SQL wildcards. :func:`unescape_like_pattern`
reads them back in one left-to-right pass, so ``\\\\%`` is a literal backslash
followed by a wildcard-escape, never the other grouping.

WHAT THIS IS NOT. Not ``names_match`` (``utils/name_normalization``): that
answers "are these two strings the same team" with diacritic folding,
abbreviation expansion and a token-overlap score, and is the right tool where
two whole names are compared. This is a boundary rule for a pattern list that
already contains the short tokens, aliases and roster names the route chose
to search with; it decides only whether a chosen token is present as a token.
"""

from __future__ import annotations

__all__ = [
    "unescape_like_pattern",
    "pattern_matches_token",
    "any_pattern_matches_token",
]


def unescape_like_pattern(pattern: str) -> str:
    """Invert ``_escape_like``: ``\\\\`` -> ``\\``, ``\\%`` -> ``%``, ``\\_`` -> ``_``.

    Single left-to-right pass. A backslash before any other character, or a
    trailing backslash, is kept literally so an unescaped input is not damaged.
    """
    if "\\" not in pattern:
        return pattern
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\" and i + 1 < n and pattern[i + 1] in "\\%_":
            out.append(pattern[i + 1])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _is_token_char(ch: str) -> bool:
    return ch.isalnum()


def pattern_matches_token(label: str, pattern: str) -> bool:
    """True when ``pattern`` (ILIKE-escaped, case-insensitive) occupies whole
    tokens somewhere in ``label``. See the module docstring for the rule."""
    if not label or not pattern:
        return False
    needle = unescape_like_pattern(pattern).lower()
    if not needle:
        return False
    hay = label.lower()

    need_left = _is_token_char(needle[0])
    need_right = _is_token_char(needle[-1])

    start = hay.find(needle)
    while start != -1:
        end = start + len(needle)
        left_ok = (not need_left) or start == 0 or not _is_token_char(hay[start - 1])
        right_ok = (not need_right) or end == len(hay) or not _is_token_char(hay[end])
        if left_ok and right_ok:
            return True
        start = hay.find(needle, start + 1)
    return False


def any_pattern_matches_token(label: str, patterns: list[str]) -> bool:
    """``any(pattern_matches_token(label, p) for p in patterns)``, short-circuit."""
    if not label:
        return False
    for p in patterns:
        if pattern_matches_token(label, p):
            return True
    return False
