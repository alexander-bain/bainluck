"""Whether a StatPal tennis name and one of ours are the same player. #2867, step 4.

**SHIP: tennis can join to StatPal at all — which is the precondition for the
tennis agreement row, and the thing `ARTIFACT-AUTHORITY-20260903-TENNIS.md` makes
binding before any tennis number is published.** (Pillar: MATCHING. Program step
4, riding the lane's ship: *every game exists on the site before any market lists
it*.)

This module decides identity ONLY. It never decides time: StatPal stamps
``15:00`` UTC as a session placeholder on unplayed tennis and backfills the true
minute after the match (66 of 70 unplayed fixtures on 2026-09-04), so
**StatPal tennis is an EXISTENCE authority, not a TIME authority** and nothing
here may be reused to move a kickoff.

═══ THE TWO VOCABULARIES, MEASURED ═══

Measured against the real field on 2026-09-05: **7,731 distinct tennis names**
across every ``tennis%`` sport key in production.

*Theirs* is regular. StatPal serves ``I. Surname`` — one or more initials, then a
surname that may be several tokens: ``C. Alcaraz``, ``T. M. Etcheverry``,
``B. Van De Zandschulp``, ``D. Merida Aguilar``. Doubles come as
``Galloway/ Goransson``.

*Ours* is four vocabularies wearing one column:

===========================  =====  =====  ==========================
shape                            n      %  example
===========================  =====  =====  ==========================
two-token                     2851   36.9  ``Marie Bouzkova``
**bare surname**              2516   32.5  ``Hrazdil``, ``Gaston``
doubles pair                  1674   21.7  ``Bagaric/Moratelli``
three-token                    563    7.3  ``Murkel Dellien Velasco``
four or more                   127    1.6  ``Andre Souza Pinto De Camargo E Silva``
===========================  =====  =====  ==========================

**A third of our tennis names carry no given name at all.** That single fact
kills the obvious rule — "compare the initial" — as a *requirement*: for 2,516
names there is no initial on our side to compare. It can only ever be a
disambiguator, applied when both sides happen to have one.

═══ WHY THE JOIN KEY IS A PAIR AND NOT A SURNAME ═══

The tempting rule is "join on the surname". Measured on the real field, a
surname-only join is **contested 38.3% of the time** — 2,649 of 6,925 candidate
surnames are claimed by more than one distinct name. It is not a join; it is a
coin flip with 6,925 sides.

So the key is the pair ``(surname, given-initial)``. Theirs produces exactly one.
Ours produces every reading its tokens allow, and a bare surname produces
``(surname, None)``.

═══ THE ORDER PROBLEM, AND WHAT ADMITTING IT COSTS ═══

``Wu Yibing`` is our spelling; StatPal serves ``Y. Wu``. The surname is FIRST.
A surname-last rule reads ``Yibing`` as the surname and reports a permanent false
miss on every Chinese player — the artifact's finding, and the reason this is not
a detail to defer.

Admitting the surname-first reading is not free, and the price is worth stating
because it is the same hazard :data:`CONTESTED` exists for. Measured:

==============================  ==========  ==============  ===================
reading                         keys        contested keys  names with NO
                                                            uncontested key
==============================  ==========  ==============  ===================
surname-last only                    6,674     208 (3.12%)                  257
plus surname-first                  10,617     572 (5.39%)                  149
==============================  ==========  ==============  ===================

Admitting the Asian reading nearly triples the contested keys (208 → 572) and
**almost halves the names that no key can reach** (257 → 149). That is the trade,
measured rather than argued, and it is taken: a contested key is refused loudly
(see :func:`resolve_tennis_name`), while an unreachable name is a player who can
never be joined at all.

What is NOT done is the rule that looks equivalent and is not: letting a token
*prefix* count as cover. That makes any one-letter token a wildcard —
``Christopher O'Connell`` compared equal to ``Oleksandra Oliynykova`` when the
``o`` split out of ``O'Connell`` covered both — so every surname here is matched
**whole and exact**, never as a prefix. The pair key refuses that collision in
both readings, and the sweep test pins it.

The corollary is that a two-character surname is safe here where the older
``>=3``-character anchor rule would have refused it. ``Wu``, ``Bu``, ``Ha``,
``Hu`` are real surnames and there are 50 of two characters or fewer in the
field; they are only wildcards under prefix matching, which this module does not
do.

═══ AND WHICH RE-ORDERINGS ARE ONE PLAYER — REVIEWED, NOT ASSUMED ═══

Admitting the surname-first reading above says a *StatPal* name may be joined
under either reading. It does not say that two of OUR names which are token
permutations of each other are one player, and the second claim is the one that
can silently substitute. Swept over the whole field, **8 token multisets are
spelled in more than one order**, and they do not all mean the same thing:

=========================================  ===  ==============================
class                                        n  reading
=========================================  ===  ==============================
Chinese / Korean / Taiwanese / Indian        7  one player, both name orders
Spanish compound surname                     1  order is part of the surname
=========================================  ===  ==============================

The seven fold (:data:`_ORDER_ALIASES_MEASURED`). The eighth does not:
``Garcia Perez``, ``Garcia-Perez`` and ``Perez-Garcia`` are all in the register,
and in Spanish a compound surname is ordered paternal-then-maternal, so swapping
it names a different family. Nothing in our column can tell us whether it is one
player or two, and **that is the answer, not an obstacle to it** — the module
refuses what it cannot verify (see :func:`register_identity`).

A sweep of today's corpus is not the whole list, though, and the gap is the
reduced-fixture trap wearing a new hat: it measures the orders our column
*happens to hold*, not which re-orderings *mean one player*. ``Shang Juncheng``
and ``Zheng Qinwen`` are named as one player right here and in the tests, yet
the register has only ever received one spelling of each, so the sweep cannot
see them. They are :data:`_ORDER_ALIASES_REVIEWED`, and :data:`ORDER_ALIASES` is
the union — **9 classes: 7 measured, 2 reviewed.**

The rule is therefore not "sort the tokens". It is: *an order difference is a
DIFFERENCE until a human has read the pair and said otherwise.* A permutation
class that shows up in a refreshed corpus and is not on the list fails the sweep
until someone reviews it, which is the whole point — the alternative is a
tolerance that widens itself every time the field grows.

═══ DOUBLES ═══

Order carries no information — ``Rojer/ Winegar`` and ``Winegar/Rojer`` are one
team — so a pair folds to an unordered set of surnames. Our side spells the
separator two ways (``' / '`` 1,185 times, ``'/'`` 489), and folding them
together is a repair rather than a tolerance: 1,674 stored doubles names collapse
to **1,515 real pairs**. All 159 "collisions" are one team stored twice — 157
under both separator spellings, 2 with the partners in the opposite order
(``Golubic / Waltert`` beside ``Waltert/Golubic``) — and none is two different
teams.

═══ WHICH DIRECTION THIS FAILS IN ═══

A false AGREEMENT is silent: a substitution goes undetected and the agreement row
overstates. A false DISAGREEMENT is loud: it shows up as a miss in the row and
someone looks. This module is therefore biased toward the loud failure —
ambiguity is refused, not guessed — which is the opposite of the bias a
user-facing matcher wants and the right one for a measurement that gates D50.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

#: A join key: the folded surname, and the given-name initial when one is known.
#: ``None`` in the second slot means "our side has no given name for this player"
#: — 32.5% of the field — and is a real key, not a missing one.
TennisKey = tuple[str, Optional[str]]

#: A doubles team: the two folded surnames, order-insensitive but
#: multiplicity-preserving — a sorted pair, NOT a set. See
#: :func:`register_identity` for why the distinction is load-bearing.
DoublesKey = tuple[str, ...]

_NON_NAME = re.compile(r"[^a-z0-9 ]+")

#: **Generational suffixes are NOT stripped, and the corpus sweep is why.**
#:
#: The first version of this module dropped a trailing ``Jr``/``Sr``, on the
#: reasoning that a suffix is not part of a surname. The sweep over the real
#: field failed on ``('damm', None)``, claimed by both ``Damm`` and ``Damm Jr``
#: — Martin Damm the doubles champion and Martin Damm his son, two players who
#: have both been in ATP draws. **Stripping the suffix fuses exactly the two
#: people the suffix exists to tell apart**, which is the same shape as
#: `authority_name_forms`' founding-year rule fusing ``Iberia 1999`` with
#: ``Iberia 2010``, and it was found the same way: by running the widening over
#: the whole field instead of over the cases that motivated it.
#:
#: Keeping the suffix costs a missed join on a row spelled inconsistently — the
#: LOUD failure this module is biased toward — where dropping it bought a silent
#: substitution of one player for another.

#: Names in the tennis team-name column that are not players at all. Futures
#: market titles have leaked into it — ``Black Desert Resort (Men's Doubles)
#: Winner`` and its siblings — and they fold to keys like ``('winner', 'b')``
#: that collide with each other and with nothing real. Excluded by a property of
#: the string rather than by a list, because the list would rot.
_NOT_A_PLAYER = re.compile(r"\b(winner|champion|title|outright|field)\b")

#: Permutation classes the field spells in BOTH orders today — found by sweeping
#: the 2026-09-05 corpus for token multisets with more than one written order,
#: then reading each one. Each is a convention where the family name leads and
#: our column stored both readings of the same human:
#:
#: * ``Bu Yunchaokete``, ``Guo Hanyu``, ``Ma Yexin``, ``Wu Yibing`` — Chinese
#: * ``Liang En-Shuo`` — Taiwanese; ``Im Hee-Rae`` — Korean
#: * ``Sasikumar Mukund`` — Indian
#:
#: The sweep found eight. The eighth, ``('garcia', 'perez')``, is deliberately
#: ABSENT — see the module header. A list of reviewed aliases is exactly the
#: place where "we do not know" has to look like an omission rather than
#: dissolve into a sort.
_ORDER_ALIASES_MEASURED: frozenset[tuple[str, ...]] = frozenset(
    {
        ("bu", "yunchaokete"),
        ("en", "liang", "shuo"),
        ("guo", "hanyu"),
        ("hee", "im", "rae"),
        ("ma", "yexin"),
        ("mukund", "sasikumar"),
        ("wu", "yibing"),
    }
)

#: Reviewed aliases the field currently spells only ONE way.
#:
#: These are here because **a corpus sweep measures what our column happens to
#: hold today, which is a reduced fixture of the aliasing relation itself.** Both
#: are named as one-player-two-orders by this module's header and by its tests;
#: the register simply has not received the second spelling yet. Deriving the
#: list from today's corpus alone would silently drop them and then refuse a pair
#: we have already reviewed, the first day the other spelling arrives.
_ORDER_ALIASES_REVIEWED: frozenset[tuple[str, ...]] = frozenset(
    {
        ("juncheng", "shang"),  # Shang Juncheng — corpus holds only `Juncheng Shang`
        ("qinwen", "zheng"),  # Zheng Qinwen — corpus holds only `Qinwen Zheng`
    }
)

#: The token multisets our register spells in more than one order for ONE
#: player. Keyed on the sorted tokens; membership is what lets
#: :func:`register_identity` ignore order for that class and only that class.
#: **Reviewed, never derived** — the sweep proposes, a person disposes.
ORDER_ALIASES: frozenset[tuple[str, ...]] = (
    _ORDER_ALIASES_MEASURED | _ORDER_ALIASES_REVIEWED
)


def fold_tennis_name(name: object) -> str:
    """Lowercase, strip diacritics and punctuation, collapse whitespace.

    Applied identically to both sides. ``Anna Bondár`` and ``Anna Bondar`` are
    one player and the field holds both spellings; ``Daria KHOMUTSIANSKAYA`` and
    ``Daria Khomutsianskaya`` likewise.
    """
    if not isinstance(name, str):
        return ""
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = _NON_NAME.sub(" ", folded.lower())
    return " ".join(folded.split())


def looks_like_a_player(name: object) -> bool:
    """False for the futures-market titles sitting in the same column."""
    folded = fold_tennis_name(name)
    return bool(folded) and not _NOT_A_PLAYER.search(folded)


def _tokens(name: object) -> list[str]:
    return fold_tennis_name(name).split()


def is_doubles_name(name: object) -> bool:
    """A doubles pair, on either side, under either of our two spellings."""
    return isinstance(name, str) and "/" in name


def doubles_key(name: object) -> Optional[DoublesKey]:
    """The unordered pair of surnames, or ``None`` if this is not a clean pair.

    ``None`` rather than a one-element set for a malformed pair: a doubles row we
    cannot read into two players is a row to report, not to half-match.
    """
    if not is_doubles_name(name):
        return None
    assert isinstance(name, str)
    parts = [fold_tennis_name(p) for p in name.split("/")]
    parts = [p for p in parts if p]
    if len(parts) != 2:
        return None
    return tuple(sorted(parts))


def statpal_tennis_key(name: object) -> Optional[TennisKey]:
    """The single key a StatPal singles name produces, or ``None``.

    StatPal's shape is initials-then-surname, and the surname is *everything
    after the initials* — ``B. Van De Zandschulp`` is one player with a
    three-token surname, not a parse failure.
    """
    if is_doubles_name(name) or not looks_like_a_player(name):
        return None
    toks = _tokens(name)
    initials: list[str] = []
    while toks and len(toks[0]) == 1:
        initials.append(toks.pop(0))
    if not toks:
        # Initials and nothing else. Not joinable, and not silently dropped:
        # the caller reports it rather than matching it to whatever shares a
        # letter.
        return None
    return (" ".join(toks), initials[0] if initials else None)


def our_tennis_keys(name: object) -> frozenset[TennisKey]:
    """Every key one of our names could answer to.

    A bare surname yields exactly ``(surname, None)``. A multi-token name yields
    both readings — surname-last for every trailing run, surname-first for every
    leading run — because our column does not record which one it stored, and
    guessing from the tokens is the mistake this module's header measures.
    """
    if is_doubles_name(name) or not looks_like_a_player(name):
        return frozenset()
    toks = _tokens(name)
    if not toks:
        return frozenset()
    if len(toks) == 1:
        return frozenset({(toks[0], None)})
    keys: set[TennisKey] = set()
    for cut in range(1, len(toks)):
        # surname-last: "Carlos Alcaraz" -> ('alcaraz', 'c')
        keys.add((" ".join(toks[cut:]), toks[0][0]))
        # surname-first: "Wu Yibing" -> ('wu', 'y')
        keys.add((" ".join(toks[:cut]), toks[cut][0]))
    return frozenset(keys)


def register_identity(name: object) -> tuple[str, ...]:
    """The identity two of our register's names share **iff they are one player**.

    Two reductions were tried here and both deleted a discriminator:

    A `frozenset` erased MULTIPLICITY. On the real field ``Garcia`` and
    ``Garcia Garcia`` both fold to ``{'garcia'}`` — as do ``Rodriguez`` and
    ``Rodriguez Rodriguez`` — so ``G. Garcia`` resolved MATCHED against two
    people and silently picked the first (CERT-1890).

    `sorted()` erased ORDER. It keeps ``('garcia',)`` and ``('garcia',
    'garcia')`` apart, so it fixed the first bug, but it still declares every
    token permutation one player: ``Garcia-Perez`` and ``Perez-Garcia`` fold
    together and ``G. Perez`` again returns MATCHED against a candidate set
    holding both spellings.

    So order is a DIFFERENCE by default and tokens are compared in the order
    they were written; the seven reviewed classes in :data:`ORDER_ALIASES` — the
    Chinese, Korean, Taiwanese and Indian names our column stores under both
    readings, ``Wu Yibing`` beside ``Yibing Wu`` — are the only ones that fold.
    That keeps the reason the module exists while making the tolerance
    enumerable, which a sort can never be.

    Note the shape both bugs share, because it is the general lesson and not a
    tennis one: **a reduction that deletes a discriminator is not a
    normalisation**, and neither one was visible to a sweep that grouped by the
    same reduction the matcher used. Group by what the matcher REQUIRES.
    """
    if is_doubles_name(name):
        pair = doubles_key(name)
        # A malformed pair gets an identity of its own rather than collapsing
        # onto every other unreadable row. Doubles order genuinely carries no
        # information — a team is unordered, and all 159 measured pair-order
        # collisions were one team stored twice — so `doubles_key` sorts and no
        # allowlist is needed on this branch.
        return pair if pair is not None else ("?", fold_tennis_name(name))
    tokens = tuple(_tokens(name))
    multiset = tuple(sorted(tokens))
    # Returning the sorted form for a reviewed class and the written order
    # otherwise cannot cross classes: a name outside the class has a different
    # multiset, so it can never produce this one as its written order.
    return multiset if multiset in ORDER_ALIASES else tokens


def keys_agree(ours: TennisKey, theirs: TennisKey) -> bool:
    """Do two keys name the same player?

    The surname must be equal and whole. The initials must agree **when both
    sides have one** — a `None` on either side is "not known", never "matches
    anything", but it also cannot be a disagreement, because a third of our
    field has no given name to disagree with.
    """
    if ours[0] != theirs[0]:
        return False
    if ours[1] is None or theirs[1] is None:
        return True
    return ours[1] == theirs[1]


def tennis_names_agree(ours: object, theirs: object) -> bool:
    """Whether one of our names and one StatPal name are the same player or team.

    Singles against singles, doubles against doubles. A doubles name never
    matches a singles name: the two populations are different draws and
    conflating them is what produces a phantom "missing from our DB" gap, since
    doubles outnumber singles better than 2:1 on a US Open day.
    """
    if is_doubles_name(ours) or is_doubles_name(theirs):
        ours_pair, theirs_pair = doubles_key(ours), doubles_key(theirs)
        return ours_pair is not None and ours_pair == theirs_pair
    theirs_key = statpal_tennis_key(theirs)
    if theirs_key is None:
        return False
    return any(keys_agree(k, theirs_key) for k in our_tennis_keys(ours))


#: What :func:`resolve_tennis_name` decided, and why.
MATCHED = "MATCHED"
NO_CANDIDATE = "NO-CANDIDATE"
AMBIGUOUS = "AMBIGUOUS"
UNREADABLE = "UNREADABLE"


@dataclass(frozen=True)
class TennisResolution:
    """One StatPal name resolved against a candidate set.

    ``AMBIGUOUS`` carries every name it could not choose between, so the receipt
    says which two players the field cannot tell apart rather than that
    something was skipped.
    """

    outcome: str
    matched: Optional[str] = None
    candidates: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.outcome == MATCHED


def resolve_tennis_name(
    theirs: object, candidates: Iterable[object]
) -> TennisResolution:
    """Which candidate IS this StatPal name — or a named refusal.

    **Two matches is not a match.** The global field has 572 contested keys, and
    a resolver that picked the first would silently substitute one player for
    another; a false agreement here is the silent failure this module is biased
    against. Resolution is against the CANDIDATE set the caller supplies — one
    tournament-day, not the whole register — so most global collisions are never
    reachable in practice and the ones that are get reported by name.

    Contested KEYS undercount what is reachable, and the test file sweeps both:
    `keys_agree` reads a missing initial as UNKNOWN, so `Garcia` and
    `Garcia Garcia` are both reachable from `G. Garcia` while sitting under
    different keys. The reachability class is the SURNAME, not the key.
    """
    theirs_is_doubles = is_doubles_name(theirs)
    if theirs_is_doubles:
        if doubles_key(theirs) is None:
            return TennisResolution(UNREADABLE)
    elif statpal_tennis_key(theirs) is None:
        return TennisResolution(UNREADABLE)

    hits = [
        str(c)
        for c in candidates
        if isinstance(c, str) and tennis_names_agree(c, theirs)
    ]
    # Two candidates that are a REVIEWED re-ordering of the same tokens are ONE
    # player our register lists twice — `Wu Yibing` beside `Yibing Wu` — and
    # calling that ambiguous would refuse exactly the players the order tolerance
    # exists for. Everything else is two people: tokens that actually differ
    # (`Adam Martin`, `Andrej Martin`), tokens that differ in how many times one
    # repeats (`Garcia`, `Garcia Garcia`), and tokens that differ only in order
    # without a review behind them (`Garcia-Perez`, `Perez-Garcia`).
    # `register_identity` is the one place that judgment lives — the sweep calls
    # it too, so a loosening cannot hide from the corpus.
    distinct = {register_identity(h) for h in hits}
    if not hits:
        return TennisResolution(NO_CANDIDATE)
    if len(distinct) > 1:
        return TennisResolution(AMBIGUOUS, candidates=tuple(sorted(hits)))
    return TennisResolution(MATCHED, matched=hits[0], candidates=tuple(sorted(hits)))
