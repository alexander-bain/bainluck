"""The shapes one team name can take without becoming a different team. #2792.

``_teams_agree`` decides whether an anchored row IS the fixture its authority id
names, and it decides by comparing our stored team names against every name
ESPN publishes.  That comparison is deliberately EXACT — an inexact one is how
a matcher fuses two fixtures — and exactness is affordable only if both
vocabularies are wide enough.  Measured 2026-09-03 against production, they
were not: 52 of 685 anchored rows came back ``teams_disagree`` and **51 of them
were the same fixture spelled differently**.  Exactly one was a real
mis-anchor (E416569, Ohio State @ Texas wearing *Texas v Texas State*'s id),
which is the row #2792 is named for and the row every rule here must keep out.

The cost of that shortfall is reach, not corruption — ``teams_disagree`` writes
nothing — but it is what stopped the anchor-schedule rail correcting a misdated
row for any team whose name differs in vocabulary from ESPN's, which is most of
MLS, a third of NCAAF's FCS visitors and all of the AFL.

═══ TWO WIDENINGS, AND THE ONE THIS MODULE REFUSES ═══

**1. Read the names the authority already publishes** (:func:`composed_forms`).
ESPN gives ``location`` and ``name`` separately and, for most leagues, their
concatenation as ``displayName``.  For the AFL it does not: Hawthorn is
``location='Hawthorn'``, ``name='Hawks'``, ``displayName='Hawthorn'`` — so our
perfectly ordinary "Hawthorn Hawks" matched none of the five strings we read.
Composing the pairs ESPN itself implies is not a fuzzy rule at all; it is
reading a field we already fetched.  It is what rescues ``UMass Minutemen``
(``nickname`` + ``name``) and ``LIU Sharks`` (``abbreviation`` + ``name``).

**2. Reduce both sides identically** (:func:`canonical_forms`).  Punctuation, a
leading article, a club initialism — and NOT a founding year, which looked just
as obvious as the other three and turned out to fuse two clubs; see
:data:`CLUB_INITIALISMS`' neighbouring comment.  Every rule here is a
*reduction of the whole name*, never a sub-token — which is the property that
keeps it safe.  A rule that let part of a name stand for the name would make
short tokens into wildcards, the defect that once made ``Christopher
O'Connell`` compare equal to ``Oleksandra Oliynykova``.  ``Ohio State
Buckeyes`` reduces only to itself, so no reduction can walk it toward ``Texas
State Bobcats``.

**3. What this module will NOT do: synonyms.**  Ten of the 52 disagreements are
genuine vocabulary differences — ``App State``/``Appalachian State``,
``Southern Miss``/``Southern Mississippi``, ``Athletic Bilbao``/``Athletic
Club``, ``Nicholls``/``Nicholls State``, and ``Houston Baptist``/``Houston
Christian``, which is not even an alias but a university that renamed itself.
No structural rule reaches those, and the rule that would — token overlap, or
accepting a prefix — is precisely the rule that also concludes ``Ohio State``
and ``Texas State`` are the same school.  They stay ``teams_disagree``, they
stay safe (nothing is written), and they are filed rather than guessed.

═══ HOW THE WIDENING IS PROVED NOT TO FUSE ═══

A widened matcher is not tested by the cases that motivated it; every one of
those is a case you already know the answer to.  It is tested by sweeping the
whole real entity field and asserting no two DIFFERENT teams collide.
``scripts/audit_authority_name_forms.py`` does that over every distinct team
name on production, per sport, and ``tests/test_authority_name_forms.py`` pins
the corpus so a future loosening has to survive all of it.

And note the direction this fails in, because it decides how tolerant to be: a
false DISAGREEMENT costs reach (a misdated row stays misdated, visibly).  A
false AGREEMENT lets one game's clock be written from another game's schedule.
So every judgment call here is biased toward refusing.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.name_normalization import normalize_team_name_for_matching

__all__ = [
    "CLUB_INITIALISMS",
    "COMPOSABLE_KEYS",
    "CONTESTED_RESIDUALS",
    "canonical_forms",
    "composed_forms",
]

#: Standalone initialisms that prefix or suffix a club's name without being part
#: of it. Stripped only at the very start or the very end, and only as a whole
#: token, so ``ca`` cannot bite ``CA Osasuna``'s neighbours or eat the ``AC`` in
#: a name that merely contains those letters.
#:
#: **Every entry is here because a production row needed it**, and the module
#: docstring's second warning is why the list is not longer: an affix no real
#: pair exercises is an untested affix, and a list nobody can point at a row for
#: is a list that grows until it collides with something. Re-derive with
#: ``scripts/audit_authority_name_forms.py`` before adding one.
#:
#:   fc  Chicago Fire FC · Houston Dynamo FC · Vancouver Whitecaps FC · Le Mans FC
#:   sc  Columbus Crew SC · SC Paderborn 07 · SC Freiburg
#:   ac  Le Havre AC
#:   bc  Atalanta BC
#:   cf  Elche CF
#:   ca  CA Osasuna
#:   rc  RC Lens
CLUB_INITIALISMS = frozenset({"fc", "sc", "ac", "bc", "cf", "ca", "rc"})

#: Reductions the sweep proved are reached by two DIFFERENT clubs. Producing one
#: of these is refused: the name keeps its affix and the comparison stays exact,
#: which costs reach and cannot fuse.
#:
#: Every entry was found by ``scripts/audit_authority_name_forms.py`` over the
#: real corpus, not reasoned about in advance — that is the only way this list
#: could have been right, because each one is a coincidence of two clubs we
#: happen to hold:
#:
#:   barcelona   FC Barcelona (Spain) and Barcelona SC (Guayaquil) are not one
#:               club, and "Barcelona SC" is exactly how the second is written.
#:   paris       Paris FC and Paris Saint-Germain are two Ligue 1 clubs, and a
#:               bare "Paris" cannot be assigned to either.
#:   rangers     "FC Rangers" and "Rangers" are held separately and we have no
#:               evidence they are the same side.
#:   lusitania   "Lusitania FC" and "SC Lusitania" likewise.
#:   al ahli     Several distinct Al Ahli clubs are in the corpus; "Al Ahli SC"
#:               must not become whichever one a bare "Al Ahli" happens to be.
#:
#: Refusal is the safe direction (module docstring, last paragraph), so an entry
#: added on suspicion costs only a row the rail declines to correct. Re-run the
#: sweep when the corpus grows — a snapshot cannot see a club we signed today.
CONTESTED_RESIDUALS = frozenset(
    {"barcelona", "paris", "rangers", "lusitania", "al ahli"}
)

#: The ESPN competitor fields that hold a *part* of a club's name — a place, a
#: mascot, or a short form of either. ``displayName`` is excluded on purpose: it
#: usually IS the composition already, and composing it again would produce
#: "Rutgers Scarlet Knights Scarlet Knights".
#:
#: **Which field holds which part is not fixed, and assuming it was is how the
#: first draft of this module failed.** For NCAAF, ``name`` is the mascot
#: (``Minutemen``) and ``location`` the place (``Massachusetts``). For the AFL,
#: ESPN reverses them:
#:
#:     Hawthorn:  displayName 'Hawthorn'  name 'Hawthorn'  nickname 'Hawks'
#:
#: so pairing ``location``-ish fields with ``name`` produced ``hawks hawthorn``
#: and the two AFL rows stayed unmatched through a census that was supposed to
#: have fixed them. The composition is therefore ORDER-INSENSITIVE: every
#: ordered pair of two distinct published fields. It is mechanical, it is only
#: ever a concatenation of two strings the authority itself published for this
#: one team, and the junk half of each pair ("hawks hawthorn") matches nothing.
COMPOSABLE_KEYS = ("location", "shortDisplayName", "nickname", "abbreviation", "name")

#: THERE IS NO FOUNDING-YEAR RULE, AND THAT IS A FINDING RATHER THAN AN
#: OVERSIGHT. Stripping a trailing ``04``/``07``/``1846`` looked obviously safe
#: — ``Schalke 04`` is Schalke — and the sweep refuted it on the first run:
#:
#:     'iberia'  <-  ['iberia 1999', 'iberia 2010']
#:
#: Two different Georgian clubs, told apart by nothing but the year. A founding
#: year is not decoration on a club's name; it is precisely the token that
#: disambiguates clubs which share one. Measured against the whole corpus the
#: rule's only unique win was ``SC Paderborn`` ↔ ``SC Paderborn 07`` (Schalke
#: and Heidenheim already agree once the initialism comes off), so it bought one
#: row of reach and cost a fusion. Do not add it back.

#: Apostrophes carry no identity once both sides are compared: ``Hawai'i`` and
#: ``Hawaii`` are one school, ``Ragin' Cajuns`` and ``Ragin Cajuns`` one team.
#: ``normalize_name`` unifies the several apostrophe characters into one but
#: keeps it, which is right for display and wrong for comparison.
_APOSTROPHE_RE = re.compile(r"'")

#: Hyphens and slashes separate words that our feeds write with a space:
#: ``Arkansas-Pine Bluff`` / ``Arkansas Pine Bluff``.
_SEPARATOR_RE = re.compile(r"[-–—/]+")


def _flatten(name: str) -> str:
    """Punctuation and spacing differences that are not identity differences."""
    flattened = _SEPARATOR_RE.sub(" ", name)
    flattened = _APOSTROPHE_RE.sub("", flattened)
    # ``Brighton & Hove Albion`` / ``Brighton and Hove Albion``. Whole-token
    # only: an ampersand glued to a word is not a conjunction.
    flattened = re.sub(r"\s+&\s+", " and ", flattened)
    return " ".join(flattened.split())


def _strip_affixes(name: str) -> str:
    """Leading article and leading/trailing club initialisms.

    Applied repeatedly until nothing more comes off, because they stack.  Never
    allowed to consume the last token — a name reduced to nothing would match
    every other name reduced to nothing.

    Returns ``""`` when the result lands on a :data:`CONTESTED_RESIDUALS` entry,
    which the caller reads as "no reduction available" rather than as a form.
    """
    current = name
    while True:
        tokens = current.split()
        if len(tokens) < 2:
            break
        if tokens[0] == "the" or tokens[0] in CLUB_INITIALISMS:
            current = " ".join(tokens[1:])
            continue
        if tokens[-1] in CLUB_INITIALISMS:
            current = " ".join(tokens[:-1])
            continue
        break
    return "" if current in CONTESTED_RESIDUALS else current


def canonical_forms(name: Any) -> frozenset[str]:
    """Every form ``name`` may be written in, as a set of WHOLE names.

    Applied to our stored name and to each of the authority's alike, so the
    comparison stays symmetric. The full normalized name is always included, so
    a widening can only ever add agreements, never remove one that the exact
    rule already found.

    Empty in, empty out — and an empty set intersects nothing, which is the
    reading a blank name must get.
    """
    if not isinstance(name, str):
        return frozenset()
    base = normalize_team_name_for_matching(name)
    if not base:
        return frozenset()
    forms = {base}
    flattened = _flatten(base)
    if flattened:
        forms.add(flattened)
        stripped = _strip_affixes(flattened)
        if stripped:
            forms.add(stripped)
    return frozenset(forms)


def composed_forms(block: dict[str, Any]) -> frozenset[str]:
    """Every ordered pair of two distinct :data:`COMPOSABLE_KEYS` values.

    The names ESPN's own fields imply but never print — the whole of the AFL's
    vocabulary gap, and the reason ``UMass Minutemen`` (``nickname`` + ``name``)
    and ``LIU Sharks`` (``abbreviation`` + ``name``) were unreachable.

    A pair is skipped when one part already contains the other, because that
    composition is not a name anybody writes: ``Rutgers Scarlet Knights`` +
    ``Scarlet Knights`` is a stutter, not an alias.
    """
    if not isinstance(block, dict):
        return frozenset()
    parts = []
    for key in COMPOSABLE_KEYS:
        value = normalize_team_name_for_matching(block.get(key) or "")
        if value and value not in parts:
            parts.append(value)
    forms = set()
    for first in parts:
        for second in parts:
            if first == second or first in second or second in first:
                continue
            forms.add(f"{first} {second}")
    return frozenset(forms)
