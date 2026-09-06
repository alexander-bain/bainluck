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
see them. They are :data:`_ORDER_ALIASES_REVIEWED`, and the REVIEW layer is the
union of the two — **9 classes: 7 measured, 2 reviewed.**

That layer is no longer the whole of :data:`ORDER_ALIASES`. Under Alex's standing
ruling on names, the authority record proves classes of its own, and both
reviewed entries turn out to be among them; see the section at the foot of this
module, and read the counts there rather than here, because they move with every
capture of the venue.

A reviewed class carries no measurement, so it carries its evidence instead.
Each is a :class:`ReviewedAlias` — the spelling the register holds, the second
spelling being asserted to be the same human, who asserted it, when, and on what
basis — and :data:`_ORDER_ALIASES_REVIEWED` is DERIVED from those records rather
than written out beside them. None of that makes an attestation true; nothing we
hold can, and the sweep for a second ordering of either name came back empty.
What it does is make the claim attributable and falsifiable, and put it on the
agreement row under ``allowances`` where an operator reads it. Both currently
say ``ratified_by_alex: false``: they are this lane's reading, not a ruling, and
the row discloses that rather than implying a review that has not happened.

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
from itertools import permutations
from typing import Iterable, Optional

from app.utils import authority_tennis_capture as _capture

#: A join key: the folded surname, and the given-name initial when one is known.
#: ``None`` in the second slot means "our side has no given name for this player"
#: — 32.5% of the field — and is a real key, not a missing one.
TennisKey = tuple[str, Optional[str]]

#: A doubles team: the two folded surnames, order-insensitive but
#: multiplicity-preserving — a sorted pair, NOT a set. See
#: :func:`register_identity` for why the distinction is load-bearing.
DoublesKey = tuple[str, ...]

_NON_NAME = re.compile(r"[^a-z0-9 ]+")

#: `ReviewedAlias.reviewed_on`. A date is stored as a string so the records stay
#: plain data, so the shape is checked rather than assumed.
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def fold_tennis_name(name: object) -> str:
    """Lowercase, strip diacritics and punctuation, collapse whitespace.

    Applied identically to both sides. ``Anna Bondár`` and ``Anna Bondar`` are
    one player and the field holds both spellings; ``Daria KHOMUTSIANSKAYA`` and
    ``Daria Khomutsianskaya`` likewise.

    Defined here, above the re-ordering section, because :class:`ReviewedAlias`
    folds its two orderings at construction time and the records are built at
    import.
    """
    if not isinstance(name, str):
        return ""
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = _NON_NAME.sub(" ", folded.lower())
    return " ".join(folded.split())

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

@dataclass(frozen=True)
class ReviewedAlias:
    """One order allowance that rests on review rather than on measurement.

    A measured alias carries its own evidence: the corpus holds both orders, and
    :func:`_orders_by_multiset` can be re-run to show it. A REVIEWED alias cannot
    — the corpus holds one order, so there is nothing to re-measure and the entry
    is only as good as the claim behind it. Before #3287 that claim was a bare
    tuple in a set with a trailing comment, and **a fabricated entry was
    indistinguishable from a real one**: appending ``("carlos", "alcaraz")`` and
    a line of prose to the header passed every test in this module's suite.

    So the claim is made a record instead of a comment, and the record has to
    state the things a fabrication cannot supply without lying on the face of it:
    which spelling the register actually holds, which second spelling is being
    asserted to be the same human, who asserted it, when, and on what basis.
    None of that makes the assertion TRUE — no data we hold can, which is the
    finding of #3287's option-1 sweep — but it makes the assertion *legible,
    attributable and falsifiable*, and it puts it on the agreement row where an
    operator reads it instead of in a source comment where nobody does.

    The fields are deliberately NOT independent. ``tokens`` is derived from the
    two orderings rather than declared beside them, so a record cannot claim one
    permutation class and quietly admit another; ``__post_init__`` refuses a
    record whose two orderings are not permutations of each other, or are the
    same string, or whose provenance fields are blank.
    """

    #: The spelling the register actually holds today — the one a sweep can see.
    corpus_order: str
    #: The second spelling this record asserts is the SAME human. The register
    #: has not received it; that is precisely why measurement cannot settle it.
    claimed_order: str
    #: Who made the assertion. Not decoration: an allowance nobody will own is
    #: an allowance that should not be granted.
    reviewer: str
    #: ISO date the assertion was made, so a stale review is visible as stale.
    reviewed_on: str
    #: The basis. What makes these one player rather than two, in one sentence
    #: an operator can disagree with.
    attestation: str
    #: Whether a human with authority over the product has ratified this. An
    #: agent's reading is a proposal; only Alex can make it a ratified one
    #: (D50). Published on the row so the residue is disclosed, not implied.
    ratified_by_alex: bool = False

    @property
    def tokens(self) -> tuple[str, ...]:
        """The permutation class, DERIVED from the two orderings, never declared."""
        return tuple(sorted(fold_tennis_name(self.corpus_order).split()))

    def __post_init__(self) -> None:
        corpus = fold_tennis_name(self.corpus_order)
        claimed = fold_tennis_name(self.claimed_order)
        if not corpus or not claimed:
            raise ValueError(
                f"reviewed alias needs both orderings spelled out, got "
                f"corpus_order={self.corpus_order!r} claimed_order={self.claimed_order!r}"
            )
        if corpus == claimed:
            raise ValueError(
                f"reviewed alias {corpus!r} claims no SECOND ordering — "
                "corpus_order and claimed_order fold to the same string, so the "
                "record asserts nothing and would admit a class it never named"
            )
        if sorted(corpus.split()) != sorted(claimed.split()):
            raise ValueError(
                f"reviewed alias {self.corpus_order!r} / {self.claimed_order!r} "
                "is not a re-ordering — the two spellings are different token "
                "multisets, so allowing it would admit a substitution, not a "
                "permutation"
            )
        if not self.reviewer.strip():
            raise ValueError(f"reviewed alias {corpus!r} names no reviewer")
        if not _ISO_DATE.fullmatch(self.reviewed_on):
            raise ValueError(
                f"reviewed alias {corpus!r} has reviewed_on={self.reviewed_on!r}, "
                "which is not an ISO date"
            )
        if not self.attestation.strip():
            raise ValueError(f"reviewed alias {corpus!r} states no basis")

    def receipt(self) -> dict[str, object]:
        """What the agreement row publishes for this allowance."""
        return {
            "tokens": list(self.tokens),
            "corpus_order": self.corpus_order,
            "claimed_order": self.claimed_order,
            "reviewer": self.reviewer,
            "reviewed_on": self.reviewed_on,
            "attestation": self.attestation,
            "ratified_by_alex": self.ratified_by_alex,
        }


#: Reviewed aliases the field currently spells only ONE way.
#:
#: These are here because **a corpus sweep measures what our column happens to
#: hold today, which is a reduced fixture of the aliasing relation itself.** Both
#: are named as one-player-two-orders by this module's header and by its tests;
#: the register simply has not received the second spelling yet. Deriving the
#: list from today's corpus alone would silently drop them and then refuse a pair
#: we have already reviewed, the first day the other spelling arrives.
#:
#: **Neither is ratified.** Both readings were made by the authority lane while
#: writing this module, not by a person with authority over the product, and
#: saying so is the point of #3287: the row discloses two unratified allowances
#: rather than presenting them as review that happened. Ratifying them is a
#: minutes-long read for Alex (`alex-inbox`), and until he does, an operator can
#: see exactly what rests on an agent's judgement.
REVIEWED_ALIASES: tuple[ReviewedAlias, ...] = (
    ReviewedAlias(
        corpus_order="Juncheng Shang",
        claimed_order="Shang Juncheng",
        reviewer="authority lane (agent)",
        reviewed_on="2026-09-05",
        attestation=(
            "Chinese convention: `Shang` is the family name and `Juncheng` the "
            "given name, so both orders name the one player. No second player "
            "in our register bears these tokens in the opposite order."
        ),
    ),
    ReviewedAlias(
        corpus_order="Qinwen Zheng",
        claimed_order="Zheng Qinwen",
        reviewer="authority lane (agent)",
        reviewed_on="2026-09-05",
        attestation=(
            "Chinese convention: `Zheng` is the family name and `Qinwen` the "
            "given name, so both orders name the one player. No second player "
            "in our register bears these tokens in the opposite order."
        ),
    ),
)

#: Derived from :data:`REVIEWED_ALIASES`, never written out beside it — a second
#: literal is a second thing to keep in step, and the day they drift the set is
#: what the matcher obeys while the records are what a reader audits.
_ORDER_ALIASES_REVIEWED: frozenset[tuple[str, ...]] = frozenset(
    alias.tokens for alias in REVIEWED_ALIASES
)

#: The token multisets that name ONE player under more than one written order.
#: Keyed on the sorted tokens; membership is what lets :func:`register_identity`
#: ignore order for that class and only that class.
#:
#: **Rebound at the bottom of this module** to add the classes the AUTHORITY
#: RECORD proves (D69 = A) — see "WHY NOBODY IS ASKED ABOUT A NAME AGAIN". The
#: binding here is the pre-D69 set and exists so the functions below can be
#: defined before the prover that needs them runs.
ORDER_ALIASES: frozenset[tuple[str, ...]] = (
    _ORDER_ALIASES_MEASURED | _ORDER_ALIASES_REVIEWED
)


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


# ═════════════════════════════════════════════════════════════════════════════
# WHY NOBODY IS ASKED ABOUT A NAME AGAIN  —  D69 = A (Alex, 2026-09-05 7:16pm PT)
# ═════════════════════════════════════════════════════════════════════════════
#
# Everything above this line decides order by REVIEW: seven classes swept out of
# the corpus and read by a person, two more attested by this lane and published
# as unratified. Alex ended that:
#
#     "I don't have enough context to know if those are the same people, and you
#     don't want human in the loop on this, because it's not the last time
#     this'll happen with names. Sort it out in a scalable way."
#
# and, when asked how a machine could know:
#
#     "not from Fable's knowledge of Chinese naming — from the authority record:
#     the same draw slot, opponent and date carry one spelling in one source and
#     the other in the other. The lane proves it that way, or does not alias."
#
# ─── WHAT THE VENUE ACTUALLY SERVES, AND HOW THE PROOF DIFFERS FROM THE ASK ───
#
# Measured against StatPal's own tennis endpoints on 2026-09-06 (notice 26a),
# d-7…d7 plus livescores, 372 fixtures: **StatPal never spells `Zheng Qinwen`.**
# It serves `Q. Zheng`. The reversed spelling the ruling expected to find on the
# other side of the slot is not there — and it is not in our register either,
# over a year of it (7,539 distinct spellings).
#
# The slot proves something better. StatPal's singles form is
# `{initial}. {Surname}`, so a slot does not merely *exhibit* the other ordering,
# it **names the surname outright** — the one fact our own column never records
# and the only fact the order question turns on. `Q. Zheng` opposite `M. Keys`
# on 2026-09-05 in `tennis_wta_us_open`, against our `Qinwen Zheng` opposite
# `Madison Keys`, says: the surname is `zheng`, the given name starts with `q`.
# Six such slots over four days and two tour keys, all carrying StatPal player id
# `43122` — and `M. Zheng`, a different player, carries `126416` throughout, which
# is the ruling's first clause working: **identity is the id, not the string.**
#
# Once the surname is proven, the fold follows without anybody's opinion about
# how Chinese names are written: `Zheng Qinwen` read surname-first produces the
# same key `('zheng', 'q')`, so the day that spelling arrives it is the same
# player, automatically, with this receipt behind it.
#
# ─── THE THREE GUARDS, EACH REFUTABLE FROM THE CAPTURE ───
#
# A rule that folded every re-ordering it could reach would fuse `Garcia Perez`
# with `Perez-Garcia`, which in Spanish are two families and, in our register, two
# people (both spellings in the field on 2026-07-13). So a class folds only when:
#
# 1. **A slot joined one of our spellings in the class to an authority id.** Not
#    "the surname appears somewhere" — a slot, with a date, an opponent and a
#    stable player id. No slot, no fold; this is the clause that makes
#    `Garcia Perez` a non-candidate outright today, and the one CERT-2017 found
#    a second tier quietly evading.
# 2. **The class's OTHER tokens are not surnames.** `zheng` is in the authority's
#    surname vocabulary and `qinwen` is not; `shang` is and `juncheng` is not.
#    Where both tokens are surnames the re-ordering may well be two families, and
#    the rule declines to guess.
# 3. **Our register does not already hold the reversed order.** If it does, the
#    two spellings are in the field together and folding them is the review
#    question this section exists to retire, not a prediction — those classes
#    stay with :data:`_ORDER_ALIASES_MEASURED`, which was swept and read. If it
#    does not, the fold changes nothing today and everything the day the second
#    spelling arrives, which is exactly the "not the last time this'll happen"
#    Alex was pointing at.
#
# Guard 3 is why the capture reads a YEAR of our spellings while the slots can
# only ever cover the venue's fifteen-day window: `Perez-Garcia` last appeared
# eight weeks outside that window, and a guard that could not see it would have
# folded two people the first time a Garcia slot landed.

#: A slot join: the authority named this player, with an id, opposite an opponent
#: we also recognised. The strong kind.
PROOF_SLOT = "slot"

#: There is deliberately no second, weaker kind — see the end of
#: :func:`slot_proven_order_aliases` for the one that was removed and what it
#: authorised. Every alias here is `PROOF_SLOT` or does not exist.


@dataclass(frozen=True)
class ProvenSlot:
    """One side of one fixture where BOTH sides agreed, on one day.

    The opponent fields are not context. They are the proof: a single name
    agreeing with a single name is a coincidence the field produces 572 ways,
    and `__post_init__` refuses a record whose opponents do not agree under the
    same relation the matcher uses. That refusal is what makes this a SLOT.
    """

    authority: str
    authority_id: str
    authority_name: str
    our_name: str
    slot_date: str
    tour: str
    authority_opponent: str
    our_opponent: str
    doubles: bool = False

    def __post_init__(self) -> None:
        for field in ("authority", "authority_id", "authority_name", "our_name",
                      "tour", "authority_opponent", "our_opponent"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"proven slot has a blank {field}")
        if not _ISO_DATE.fullmatch(self.slot_date):
            raise ValueError(
                f"proven slot has slot_date={self.slot_date!r}, which is not an ISO date"
            )
        if not tennis_names_agree(self.our_name, self.authority_name):
            raise ValueError(
                f"proven slot {self.our_name!r} / {self.authority_name!r}: the two "
                "sides do not agree, so this record proves nothing about our name"
            )
        if not tennis_names_agree(self.our_opponent, self.authority_opponent):
            raise ValueError(
                f"proven slot {self.our_name!r} / {self.authority_name!r}: the "
                f"OPPONENTS ({self.our_opponent!r} / {self.authority_opponent!r}) do "
                "not agree, so this is a name coincidence and not a slot"
            )

    @property
    def proven_key(self) -> Optional[TennisKey]:
        """The (surname, initial) the authority named. ``None`` for doubles."""
        return None if self.doubles else statpal_tennis_key(self.authority_name)

    @property
    def proven_surnames(self) -> frozenset[str]:
        """Every token the authority used AS a surname on this side."""
        if self.doubles:
            return frozenset(doubles_key(self.authority_name) or ())
        key = self.proven_key
        return frozenset({key[0]}) if key else frozenset()

    @property
    def tokens(self) -> tuple[str, ...]:
        """The permutation class of OUR spelling, derived and never declared."""
        return tuple(sorted(fold_tennis_name(self.our_name).split()))


@dataclass(frozen=True)
class SlotProvenAlias:
    """One order-alias the authority record proves, with the evidence attached."""

    tokens: tuple[str, ...]
    kind: str
    confidence: float
    surname: str
    authority_ids: tuple[str, ...]
    slots: tuple[ProvenSlot, ...]

    def receipt(self) -> dict[str, object]:
        """What the agreement row publishes. No reviewer field, on purpose."""
        return {
            "tokens": list(self.tokens),
            "kind": self.kind,
            "confidence": self.confidence,
            "surname": self.surname,
            "authority_ids": list(self.authority_ids),
            "slots": [
                {
                    "authority": s.authority,
                    "authority_id": s.authority_id,
                    "authority_name": s.authority_name,
                    "our_name": s.our_name,
                    "date": s.slot_date,
                    "tour": s.tour,
                    "opponent": s.our_opponent,
                }
                for s in self.slots
            ],
        }


def _reversed_orders_in_field(tokens: tuple[str, ...],
                              written: str,
                              our_spellings: frozenset[str]) -> tuple[str, ...]:
    """Orderings of this class our register holds OTHER than the written one.

    Guard 3's evidence. Enumerating permutations is bounded in practice — the
    classes that reach here are two and three tokens — and a class of five or
    more is refused by the caller rather than permuted, because 120 lookups to
    answer a question about a name is a sign the name is not what we think.
    """
    return tuple(sorted(
        candidate
        for candidate in {" ".join(p) for p in permutations(tokens)}
        if candidate != written and candidate in our_spellings
    ))


def slot_proven_order_aliases(
    slots: Iterable[ProvenSlot],
    authority_surnames: Iterable[str],
    our_spellings: Iterable[str],
) -> tuple[SlotProvenAlias, ...]:
    """Which re-orderings the authority record proves are one player.

    Pure: everything it knows arrives in its arguments, so the same capture
    always produces the same answer and a test can refute it with a different
    one. The three guards are in the module comment above; each refusal below
    names which one refused it.
    """
    surnames = frozenset(authority_surnames)
    spellings = frozenset(our_spellings)

    by_class: dict[tuple[str, ...], list[ProvenSlot]] = {}
    for slot in slots:
        if slot.doubles:
            continue  # a doubles ROW has no singles permutation class of its own
        if len(slot.tokens) < 2 or len(slot.tokens) > 3:
            # One token has no order; four or more is a name we do not understand
            # well enough to permute (`Andre Souza Pinto De Camargo E Silva`).
            continue
        by_class.setdefault(slot.tokens, []).append(slot)

    aliases: list[SlotProvenAlias] = []
    for tokens, class_slots in sorted(by_class.items()):
        keys = {s.proven_key for s in class_slots if s.proven_key}
        ids = {s.authority_id for s in class_slots}
        if len(keys) != 1 or len(ids) != 1:
            # Two keys or two ids under one token multiset is two people wearing
            # one spelling. Refusing is the whole reason identity is the id.
            continue
        surname = next(iter(keys))[0]
        if surname not in surnames:
            continue  # guard 1: the proof has to be in the captured vocabulary
        others = [t for t in tokens if t != surname]
        if any(t in surnames for t in others):
            continue  # guard 2: the other token is a family name somewhere
        written = fold_tennis_name(class_slots[0].our_name)
        if _reversed_orders_in_field(tokens, written, spellings):
            continue  # guard 3: both orders are in the field — a review question
        aliases.append(SlotProvenAlias(
            tokens=tokens, kind=PROOF_SLOT, confidence=1.0, surname=surname,
            authority_ids=tuple(sorted(ids)), slots=tuple(class_slots),
        ))

    # THERE IS NO WEAKER PATH, and CERT-2017 is why. The first cut also emitted a
    # class when a surname TOKEN had been proved somewhere — typically by a
    # doubles pair, which StatPal spells as surnames only — even though no slot
    # had ever joined that spelling and no player id stood behind it. It read as
    # a reasonable second tier. It was not:
    #
    #   * `Bublik/ Shang` is a doubles TEAM (id 352267). A team id is not a
    #     person, so the class it authorised was tied to nobody.
    #   * The same path independently authorised `Alice Shang` — a different
    #     human who merely shares the surname — which is the substitution this
    #     whole module is biased against.
    #   * 175 of 331 classes came out of it, so the majority of the tolerance
    #     rested on evidence that named no person at all.
    #
    # D69's clause is "identity is the id… the lane proves it that way, or does
    # not alias", and a surname token proves a WORD, never a PERSON. So a class
    # folds only with a slot behind it and an authority id inside that slot.
    # `Juncheng Shang` consequently does NOT fold: StatPal served him only in
    # doubles in the captured window, and declining is the correct answer until
    # it serves him in singles.
    return tuple(aliases)


def _captured_slots() -> tuple[ProvenSlot, ...]:
    """The capture's records, refused one by one if they do not prove a slot."""
    built = []
    for record in _capture.PROVEN_SIDES:
        try:
            built.append(ProvenSlot(authority="statpal", **record))
        except ValueError:
            # A capture is a measurement, and a measurement can hold a row that
            # does not survive the definition. Dropping it is right; dropping it
            # SILENTLY is not, so the count is published on the agreement row.
            continue
    return tuple(built)


CAPTURED_SLOTS: tuple[ProvenSlot, ...] = _captured_slots()

#: Derived by running the real prover over the real capture. Not a literal, and
#: deliberately not one: a hand-written list here would be the reviewed set again
#: under a new name, and the whole point of D69 is that no hand writes it.
SLOT_PROVEN_ALIASES: tuple[SlotProvenAlias, ...] = slot_proven_order_aliases(
    CAPTURED_SLOTS, _capture.AUTHORITY_SURNAMES, _capture.OUR_SPELLINGS
)

_ORDER_ALIASES_SLOT_PROVEN: frozenset[tuple[str, ...]] = frozenset(
    alias.tokens for alias in SLOT_PROVEN_ALIASES
)

#: The final binding — measured by corpus sweep, reviewed by a human (both now
#: superseded by evidence, see the test that proves the containment), and proven
#: by the authority record.
ORDER_ALIASES = (
    _ORDER_ALIASES_MEASURED | _ORDER_ALIASES_REVIEWED | _ORDER_ALIASES_SLOT_PROVEN
)
