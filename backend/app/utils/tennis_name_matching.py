"""Does a StatPal tennis player name and one of ours name the same person?

#2867 / D59 step 4. StatPal serves `"B. Van De Zandschulp"`; our row says
`"Botic van de Zandschulp"`. Neither is wrong and no id joins them, so a link
between a StatPal match and one of our events is decided on the two names, the
date and the tournament — and the names are the hard part.

## Why a surname-token rule and not a similarity score

The measurement bus's one-time sweep (`ARTIFACT-M-20260903-I`, 2026-09-03)
matched 221 of 561 StatPal matches this way and banked the ten shapes that broke
naive attempts. Every one of them is a STRUCTURAL difference between the two
renderings, not a spelling difference:

    "Y. Bu"                = "Bu Yunchaokete"          family name written FIRST
    "B. Van De Zandschulp" = "Botic van de Zandschulp" particles, title-cased
    "L. van Assche"        = "Luca Van Assche"         particles, the other way
    "C. Wong"              = "Chak Lam Coleman Wong"   three given names
    "D. Merida Aguilar"    = "Daniel Merida Aguilar"   two-token surname
    "T. Barrios Vera"      = "Tomas Barrios Vera"      two-token surname
    "T. M. Etcheverry"     = "Tomas Martin Etcheverry" two initials
    "Z. Svajda"            = "Zachary Svajda"          given name abbreviated
    "Auger-Aliassime"      = "Auger Aliassime"         hyphen vs space
    "Ka. Pliskova"         = "Karolina Pliskova"       MULTI-LETTER initial

A fuzzy ratio gets some of these and cannot get the first one at any threshold,
because "Y. Bu" and "Bu Yunchaokete" share three characters. Worse, the
threshold that admits `Bu` also admits every other two-letter surname in the
draw. Ruling 048 exists because five rounds of threshold tuning each produced a
new specimen class; this is the same shape of problem and gets a rule.

## The rule

Split the StatPal name into leading INITIAL tokens and a trailing SURNAME. Then
our name must contain that surname as a contiguous run at one END or the other —
suffix for western order, prefix for family-name-first — and every initial must
PREFIX one of the remaining tokens, in order.

Two properties fall out, and both matter more than the parsing:

**The initial is a discriminator, not decoration.** StatPal writes `Ka. Pliskova`
and `Xin. Wang` precisely because `K. Pliskova` and `X. Wang` are ambiguous in
the same draw. Treating an initial as one letter throws that away and matches
Karolina to Kristyna. Treating it as a prefix keeps it: `Ka.` accepts *Karolina*
and refuses *Kristyna*.

**The prefix arm is what makes it safe.** Allowing the surname at either end is
what reads `Y. Bu` correctly, and on its own it would be far too generous — the
surname `Wu` prefixes plenty of names. The initial check is what bounds it:
`Y. Bu` against `Bu Yunchaokete` leaves `yunchaokete`, which starts with `y`.
Against a hypothetical `Bu Ming` it leaves `ming`, which does not, and the match
is refused. Neither arm is safe alone.

## What it refuses to do

**Doubles never match.** StatPal writes them as `"Galloway/ Goransson"` and we
hold no doubles rows at all; the sweep's token fallback caught 30+ false
doubles-to-singles hits before they were excluded. A name containing `/` is
rejected before anything else happens, so the question is never asked.

**No answer is not a wrong answer.** Every function here returns `None` or
`False` rather than a best guess. The caller writes an `event_provider_anchors`
row on the result, and a wrong anchor is a cross-match between two real matches
that ruling 048 exists to make impossible.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

#: StatPal renders a doubles pair as `"Galloway/ Goransson"`. We hold no doubles
#: rows, so the only thing a doubles name can do is match a singles row by
#: accident.
DOUBLES_MARKER = "/"

#: An initial: one or more letters followed by a dot (`B.`, `Ka.`, `Xin.`), or a
#: bare single letter for the renderings that drop the dot.
_INITIAL_RE = re.compile(r"^(?:([a-z]+)\.|([a-z]))$")


def _ascii_fold(value: str) -> str:
    """`Bublik` from `Bublík`, `Munar` from `Muñar`.

    NFKD then drop the combining marks. Both sides are folded the same way, so a
    provider that keeps diacritics and one that strips them agree.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_tokens(name: Optional[str]) -> list[str]:
    """A player name as lowercase ASCII word tokens.

    Hyphens and apostrophes become separators rather than being deleted:
    `Auger-Aliassime` and `Auger Aliassime` must produce the same tokens, and
    `O'Connell` must not become the single token `oconnell` on one side and two
    on the other. A dot is KEPT — :func:`split_initials` needs it to tell `Ka.`
    (an initial) from `Ka` (a very short surname).
    """
    if not name:
        return []
    folded = _ascii_fold(str(name)).lower()
    folded = re.sub(r"[^a-z0-9.]+", " ", folded)
    return [t for t in folded.split() if t]


@dataclass(frozen=True)
class ParsedName:
    """A StatPal name split into what it abbreviates and what it spells out."""

    initials: tuple[str, ...]
    surname: tuple[str, ...]

    @property
    def is_usable(self) -> bool:
        """A name with no surname tokens can match anything and must match nothing."""
        return bool(self.surname)


def split_initials(name: Optional[str]) -> Optional[ParsedName]:
    """Split `"T. M. Etcheverry"` into initials `("t", "m")`, surname `("etcheverry",)`.

    `None` for a doubles pair or an unparseable name — never a `ParsedName` with
    an empty surname, because a caller that forgets to check `is_usable` would
    then match every row in the draw.

    Only LEADING tokens are read as initials. `"D. Merida Aguilar"` keeps both
    surname tokens; a rule that stripped every short token would eat the `de` in
    `"J. De Jong"`.
    """
    if not name or DOUBLES_MARKER in str(name):
        return None

    tokens = normalize_tokens(name)
    if not tokens:
        return None

    initials: list[str] = []
    idx = 0
    for token in tokens:
        m = _INITIAL_RE.match(token)
        if not m:
            break
        initials.append(m.group(1) or m.group(2))
        idx += 1

    surname = tuple(t.rstrip(".") for t in tokens[idx:])
    surname = tuple(t for t in surname if t)
    if not surname:
        return None
    return ParsedName(initials=tuple(initials), surname=surname)


def _initials_agree(initials: tuple[str, ...], given: list[str]) -> bool:
    """Every initial prefixes a given-name token, in order.

    In order, and consumed left to right: `T. M.` against `Tomas Martin` matches
    both, and against `Martin Tomas` it does not. Order is information StatPal
    is giving us and discarding it costs a real discrimination.

    No initials at all is not agreement and not disagreement — the caller decides
    what a surname-only match is worth. Here it is vacuously true, and
    :func:`names_match` is what refuses to lean on it.
    """
    pos = 0
    for initial in initials:
        while pos < len(given) and not given[pos].startswith(initial):
            pos += 1
        if pos >= len(given):
            return False
        pos += 1
    return True


def names_match(statpal_name: Optional[str], our_name: Optional[str]) -> bool:
    """Do these two renderings name the same player?

    The surname run must sit at one END of our name — suffix for western order,
    prefix for family-name-first — and the initials must prefix what is left.

    A StatPal name with NO initials is matched on the surname alone and ONLY in
    the suffix orientation. The prefix arm exists to read family-name-first
    renderings, and it is the initial check that keeps it from matching every
    name beginning with a common syllable; without initials there is nothing
    holding it, so that combination is refused rather than guessed.
    """
    parsed = split_initials(statpal_name)
    if parsed is None or not parsed.is_usable:
        return False
    ours = normalize_tokens(our_name)
    ours = [t.rstrip(".") for t in ours]
    ours = [t for t in ours if t]
    if not ours:
        return False

    surname = list(parsed.surname)
    n = len(surname)
    if len(ours) < n:
        return False

    # Western order: "van de zandschulp" ends "botic van de zandschulp".
    if ours[-n:] == surname and _initials_agree(parsed.initials, ours[:-n]):
        return True

    # Family name first: "bu" begins "bu yunchaokete". Requires initials.
    if parsed.initials and ours[:n] == surname:
        return _initials_agree(parsed.initials, ours[n:])

    return False


def pair_matches(
    statpal_pair: tuple[Optional[str], Optional[str]],
    our_pair: tuple[Optional[str], Optional[str]],
) -> bool:
    """Do these two two-player matches have the same two players?

    Both orientations are tried because StatPal's first-listed player is not our
    home side in any reliable way — `_parse_tennis_match` calls players[0] "home"
    for want of anything better, and tennis has no home side to be right about.

    Each player must match EXACTLY ONE of ours, and the two must not both land on
    the same one. Without that, a StatPal `A. Zverev` v `M. Zverev` would match
    our `Alexander Zverev` v anybody, because the first name satisfies both
    slots.
    """
    sp_a, sp_b = statpal_pair
    our_a, our_b = our_pair

    straight = names_match(sp_a, our_a) and names_match(sp_b, our_b)
    crossed = names_match(sp_a, our_b) and names_match(sp_b, our_a)
    if not (straight or crossed):
        return False

    # Refuse a pairing where one of our players answers to both StatPal names —
    # the orientation would then be decided by which arm was evaluated first.
    if straight and crossed:
        return sp_a != sp_b and our_a != our_b
    return True
