"""Template-family detection over a set of candidate prop markets.

═══ THE QUESTION THIS MODULE EXISTS TO ANSWER ═══

Alex, reviewing UX-P151's combined second-major card (2026-08-28, relayed
through the UX-P154 runner directive), quoted rather than paraphrased because
ruling 144 requires it:

    *"Was this a bespoke solution? I thought we'd built tools to identify groups
    and surface them as groups. Why didn't any of them trigger?"*

**It was bespoke, and the answer is in three parts.**

1. **The tournament props pipeline has one family concept and it is a CAP, not
   a GROUPER.** `frontend/lib/tournamentProps.ts::curatedProps` asks
   `propTemplateFamily` for a key, and when it has seen that key before it does
   ``dropped.template += 1; continue``. There is no branch anywhere in that file
   where a detected family produces a combined card — the only two things the
   machinery can emit are TWO CARDS or ONE CARD AND A DELETION. UX-P138 got the
   deletion, UX-P147 rekeyed to stop the deletion and got the repetition, and
   neither had a third option to reach for.

   (Worse, and measured: since UX-P147 keyed the family on the WHOLE register
   key, and register keys are unique by construction — the pass refuses
   duplicates — that cap has been structurally unreachable. `dropped.template`
   could not be non-zero. The rule Alex was told about was already dead.)

2. **The real grouping tool we DO have was never wired to this surface, and
   would not have fired anyway.** `app/utils/prop_families.py::group_prop_families`
   is exactly the tool he remembers: it detects a family by pattern and emits
   ONE family with one row per entity — a combined card in payload form. Its
   only consumer is ``GET /api/teams/{...}/prop-families``. The tournament
   register pass never calls it. And had it been called,
   ``family_key("Carlos Alcaraz: Grand Slam wins in 2026")`` returns **None**:
   that title matches none of its five patterns (Next Team, "... of the year",
   a standalone award, "<entity> to <verb> N <unit>", or an over/under), because
   its vocabulary was built for league props and this is a season-total ladder
   with the subject in front of a colon.

3. **`market_grouping.py` groups on a different axis entirely** — a provider's
   own event (`group_id`), which is what makes a Polymarket multi-market event
   one thing. `KXGRANDSLAM-CALC26` and `KXGRANDSLAM-JSIN26` are two separate
   Kalshi series with no shared provider event, so nothing there could have
   related them either.

So: the DETECTOR was blind to the shape and the RENDERER had no combined output.
Both halves were missing, which is why a human wrote the legs by hand.

═══ WHAT THIS MODULE DOES INSTEAD ═══

It detects a template family **structurally, from the markets themselves**, with
no vocabulary to keep current:

    two markets are the same question about different subjects when their
    titles differ ONLY in one contiguous run of tokens, and they share at
    least one OUTCOME NAME.

Both halves are load-bearing:

* The **title diff** finds the subject without knowing what a subject looks
  like. "Carlos Alcaraz: Grand Slam wins in 2026" against "Jannik Sinner: Grand
  Slam wins in 2026" shares five trailing tokens and differs in two leading
  ones; the shared part is the question and the differing part is who it is
  about. Nothing here knows about tennis, players, or Grand Slams — add a
  third man tomorrow and he joins the family without a code change, which is
  the actual test of "by the system".
* The **shared outcome** is what makes the rows COMPARABLE. Two markets can
  share a question shape and price different things (a 1+/2+/3+ ladder versus
  a Yes/No); putting those side by side under one heading would be the same
  defect as a ladder maximum answering a slam question (UX-P134). A shared
  outcome name means there is something the card can take from EVERY member
  and print in one column, which is what a comparison is.

⚠️ **The second condition started out as "the same SET of outcomes" and the
real data refused it, which is worth recording because the strict version reads
better.** Measured 2026-08-28 on the two markets Alex's own card is built from:

    KXGRANDSLAM-CALC26  (Alcaraz)   2+ · 3+ · All 4
    KXGRANDSLAM-JSIN26  (Sinner)    1+ · 2+ · 3+

Two rungs each side that the other does not have. Alcaraz has no `1+` rung
listed and Sinner no `All 4`, and neither absence means the question is a
different question — it means a threshold ladder's rungs are per-market and
move. An identical-set rule would have failed to detect the one family we
already know exists, which is the strongest possible evidence against it. So
the family carries the INTERSECTION as its `shared_outcomes`, and the
comparison is required to come out of that intersection.

**The words stay curated; the composition stops being.** This module never
invents a question — it reports that a family exists and what its skeleton is.
The register's curation supplies the sentence a reader sees, and the pass
REFUSES a detected family nobody has written a question for, rather than
guessing one or silently shipping the repetition. See
``scripts/populate_tournament_props.py``.

**Row names come from the market's own words.** The subject tokens are printed
as the row label, title-cased and otherwise untouched — "Carlos Alcaraz", not a
curated "Alcaraz". Alex's item 4 in the same directive: *"the market's own words
are USED when they are the market's words."* A curated rename is a claim about a
number that nobody downstream can check; the source's own subject is a fact.

Pure logic, no DB, no network, no Celery — same posture as
``app.utils.cross_source_matching`` and ``app.utils.prop_families``.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field

__all__ = [
    "MAX_SUBJECT_RATIO",
    "MIN_SHARED_TOKENS",
    "TemplateFamily",
    "TemplateMember",
    "detect_template_families",
    "outcome_signature",
    "skeleton_of",
    "subject_display",
]

#: How many tokens two titles must SHARE before their difference counts as a
#: subject rather than as two different questions.
#:
#: Two, and the number is small because a real family can have a short skeleton:
#: "LeBron James Next Team" and "Kevin Durant Next Team" share exactly two
#: tokens and are the archetypal prop family. One shared token is not evidence
#: of a template — it is evidence of English ("Alcaraz wins" / "Sinner wins").
MIN_SHARED_TOKENS = 2

#: The differing run may be no LONGER than the shared part.
#:
#: This is the guard that a token floor alone cannot give, and the specimen it
#: exists for is real enough to be embarrassing:
#:
#:     "Alcaraz to win the US Open in 2026"
#:     "Sinner to win the Australian Open in 2026"
#:
#: One contiguous difference, three shared trailing tokens ("open in 2026"), and
#: they are TWO DIFFERENT TOURNAMENTS. The difference swallowed the question.
#: Requiring the subject to be no bigger than the skeleton is the cheap way to
#: say "most of the title has to be the part they agree on" without a ratio
#: nobody can defend the constant of.
MAX_SUBJECT_RATIO = 1.0

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str | None) -> list[str]:
    """Lowercase word tokens. Punctuation is a separator, never a token.

    The colon in "Carlos Alcaraz: Grand Slam wins in 2026" is exactly the kind
    of thing one source uses and another does not, so it may not be allowed to
    decide whether two markets are a family.
    """
    return _WORD_RE.findall((text or "").lower())


def outcome_signature(names: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """The normalised, ORDER-INDEPENDENT set of a market's outcome names.

    Order-independent because two sources — and one source on two days — will
    hand back the same ladder sorted differently, and a family that dissolves
    because a list came back reversed is a family nobody can rely on.

    Duplicates collapse: a market listing an outcome twice is a data bug and
    should not read as a different SHAPE from one listing it once.
    """
    return tuple(sorted({" ".join(_tokens(name)) for name in (names or []) if name}))


@dataclass(frozen=True)
class TemplateMember:
    """One market's place in a family."""

    market_ext: str
    market_name: str
    source: str
    #: The tokens that are this member's and nobody else's — the subject.
    subject_tokens: tuple[str, ...]

    @property
    def subject(self) -> str:
        return " ".join(self.subject_tokens)

    @property
    def display_name(self) -> str:
        return subject_display(self.market_name, self.subject_tokens)


@dataclass(frozen=True)
class TemplateFamily:
    """A set of markets that ask one question about different subjects."""

    #: "{} grand slam wins in 2026" — the question with the subject slot empty.
    skeleton: str
    #: The outcome names EVERY member offers, normalised and sorted. The
    #: combined card's comparison must be one of these — that is the whole
    #: reason the intersection is carried rather than recomputed.
    signature: tuple[str, ...]
    members: tuple[TemplateMember, ...] = field(default_factory=tuple)

    @property
    def market_exts(self) -> tuple[str, ...]:
        return tuple(m.market_ext for m in self.members)


def subject_display(market_name: str, subject_tokens: tuple[str, ...]) -> str:
    """The subject as the SOURCE spelled it, not as we lowercased it.

    `_tokens` destroys case so titles can be compared; a row label built from
    those tokens would read "carlos alcaraz". So the original title is re-scanned
    for the same run of words and the source's own casing is returned. Falls back
    to title-casing the tokens when the re-scan cannot find them, which happens
    only if the title contains the subject in a form the tokenizer split
    differently — a card printing "Carlos Alcaraz" is right either way.
    """
    if not subject_tokens:
        return ""
    pattern = r"\s*".join(
        re.escape(token) + r"[^\sA-Za-z0-9]*" for token in subject_tokens
    )
    found = re.search(pattern, market_name or "", flags=re.IGNORECASE)
    if found:
        # Trailing punctuation ("Alcaraz:") is a separator in the title and not
        # part of the name.
        return found.group(0).strip().strip(":;,-–—").strip()
    return " ".join(token.capitalize() for token in subject_tokens)


def skeleton_of(prefix: tuple[str, ...], suffix: tuple[str, ...]) -> str:
    """The family's question with the subject slot written as `{}`."""
    return " ".join([*prefix, "{}", *suffix]).strip()


def _subject_fits(subject: tuple[str, ...], shared: int) -> bool:
    """Is this differing run small enough to be a SUBJECT? See MAX_SUBJECT_RATIO."""
    return len(subject) <= shared * MAX_SUBJECT_RATIO


def _pair_skeleton(
    left: list[str], right: list[str]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    """`(prefix, suffix, left_subject, right_subject)` or None if not a template pair.

    The rule is deliberately strict: ONE contiguous run of difference. Two
    titles that differ in two places are two edits apart and are not one
    question with a name swapped — they are two questions that happen to share
    some words, and pairing them is how a grouper starts inventing families.
    """
    head = 0
    while head < len(left) and head < len(right) and left[head] == right[head]:
        head += 1

    tail = 0
    while (
        tail < len(left) - head
        and tail < len(right) - head
        and left[len(left) - 1 - tail] == right[len(right) - 1 - tail]
    ):
        tail += 1

    left_mid = tuple(left[head : len(left) - tail])
    right_mid = tuple(right[head : len(right) - tail])

    # Identical titles are not a family — they are a duplicate, which is a
    # different problem with a different fix.
    if not left_mid or not right_mid:
        return None
    if left_mid == right_mid:
        return None
    shared = head + tail
    if shared < MIN_SHARED_TOKENS:
        return None
    if not _subject_fits(left_mid, shared) or not _subject_fits(right_mid, shared):
        return None

    prefix = tuple(left[:head])
    suffix = tuple(left[len(left) - tail :]) if tail else ()
    return prefix, suffix, left_mid, right_mid


def detect_template_families(markets: list[dict]) -> list[TemplateFamily]:
    """Every template family in ``markets``, largest first.

    Each market dict needs ``market_ext``, ``market_name``, ``source`` and
    ``outcomes`` (a list of outcome-name strings).

    A market belongs to at most one family — the transitive closure over
    template pairs. Families of one are not emitted: a lone market is a card,
    which is what it already was.

    A family whose members' outcome names have an EMPTY intersection is
    dropped, even when the titles pair. The closure can reach that state (A and
    B share `2+`, B and C share `1+`, A and C share nothing) and a card with a
    blank cell in it is not a comparison.
    """
    usable: list[tuple[dict, list[str], set[str]]] = []
    for market in markets or []:
        if not isinstance(market, dict):
            continue
        signature = set(outcome_signature(market.get("outcomes")))
        if not signature:
            # No outcomes means nothing to compare. Silence here rather than a
            # refusal: an unpriced market is the pass's problem, not this one's.
            continue
        usable.append((market, _tokens(market.get("market_name")), signature))

    if len(usable) < 2:
        return []

    # Union-find over template pairs. The population is a curated dump — single
    # digits — so the pairwise pass costs nothing and is easier to be sure of
    # than an incremental clustering.
    parent = list(range(len(usable)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    skeletons: dict[int, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            if not (usable[i][2] & usable[j][2]):
                # Same shape of question, different KIND of answer. A ladder
                # beside a Yes/No is two questions, however alike the titles.
                continue
            pair = _pair_skeleton(usable[i][1], usable[j][1])
            if pair is None:
                continue
            prefix, suffix, _, _ = pair
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri
            skeletons[find(i)] = (prefix, suffix)

    clusters: "OrderedDict[int, list[int]]" = OrderedDict()
    for i in range(len(usable)):
        clusters.setdefault(find(i), []).append(i)

    families: list[TemplateFamily] = []
    for root, indexes in clusters.items():
        if len(indexes) < 2 or root not in skeletons:
            continue
        prefix, suffix = skeletons[root]

        shared_tokens = len(prefix) + len(suffix)
        built: list[TemplateMember] = []
        shared: set[str] | None = None
        for index in indexes:
            market, tokens, signature = usable[index]
            subject = tuple(tokens[len(prefix) : len(tokens) - len(suffix)])
            # Re-checked per member, not only per pair: the skeleton comes from
            # ONE pair, and a third market joined through the closure can have a
            # subject that pair never measured.
            if not subject or not _subject_fits(subject, shared_tokens):
                built = []
                break
            built.append(
                TemplateMember(
                    market_ext=str(market.get("market_ext")),
                    market_name=str(market.get("market_name") or ""),
                    source=str(market.get("source") or ""),
                    subject_tokens=subject,
                )
            )
            shared = signature if shared is None else (shared & signature)

        if len(built) < 2 or not shared:
            continue
        # Two members with the SAME subject are not a comparison. This is the
        # transitive-closure escape hatch: A~B and B~C can hold while A and C
        # are the same subject worded two ways, and a card with one man on it
        # twice is worse than no card.
        if len({m.subject for m in built}) != len(built):
            continue

        families.append(
            TemplateFamily(
                skeleton=skeleton_of(prefix, suffix),
                signature=tuple(sorted(shared)),
                members=tuple(sorted(built, key=lambda m: m.market_ext)),
            )
        )

    families.sort(key=lambda f: (-len(f.members), f.skeleton))
    return families
