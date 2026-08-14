"""The tier-lexicographic search scorer — ruling 041, Q325.

Full prose, including the reconstruction provenance: ``docs/search-scoring-spec.md``.

Search ranks by **match class** first and by knobs only *within* a class, and an
entity ranks **only on evidence it owns**. Those two sentences are the whole
design, and each of them kills one of the two measured failure families:

* **Owned-evidence-only kills concept over-match.** Before this, an event
  concept could be derived from a MEMBER market and then ranked as though the
  concept itself had matched — so ``super bowl``, ``world series``, ``wwe`` and
  ``stranger things`` all answered with ``concept:event:awards:emmys``. The
  Emmys concept never matched any of those queries; a market underneath it did.
  A concept whose own name/aliases do not match is now UNRANKABLE, not
  low-ranked, because a bad answer that merely sorts late still wins whenever
  the good answers are absent.

* **Tier order kills fragment wins.** Before this, ``/typeahead`` assembled its
  answer from FIXED SLOTS — one hub, one team, two events, one concept, two
  markets — with no relevance signal anywhere in the merge. A team therefore
  took the top slot whatever it matched on, so ``ai`` answered
  ``1. FC Kaiserslautern`` (fragment: k-a-i-s...**ai**...), ``ipo`` answered
  ``Asteras Tripolis`` (tr-**ipo**-lis), and ``british open`` answered a team
  called ``Brito``. A fragment now lands in MC5 and can never outrank a real
  token match, whatever kind it is.

Both families were measured, not theorised: 2026-08-12 21:48Z against production
v3792, ``entity_top_1`` 30/44 with 14 failures, 11 of them in exactly these two
classes.

The tiers
---------
Lower is better. The order is **inviolable**: no knob setting may lift a
lower-priority class above a higher one. That is property 1 of the suite, and it
is the invariant the whole design rests on — the knobs exist so that ordering
*within* a class can be tuned without anyone having to re-argue the ordering
*between* classes.

===== ===================================================================
class  meaning
===== ===================================================================
MC0    exact full-alias equality, UNFOLDED (no stemming, no accent strip,
       no punctuation strip — see ``_exact_key``)
MC1    every query token present in the entity's OWN name (fold allowed)
MC2    prefix match on the last query token (the typeahead case: the user
       is still typing the final word)
MC3    partial token match — some, not all, query tokens present
MC4    outcome-only evidence: a market matching on its OWN outcomes
MC5    fragment / fuzzy (trigram)
None   UNRANKABLE — derived-only evidence, or no evidence at all
===== ===================================================================

Ties inside a class break by **kind**: market > event > team. The gold set
agrees with the ruling here — of the 14 measured failures, 10 want a market at
rank 1 and 3 want a team, which is the same ordering read off the data.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --- the tiers -------------------------------------------------------------

MC0_EXACT = 0
MC1_ALL_TOKENS = 1
MC2_LAST_TOKEN_PREFIX = 2
MC3_PARTIAL_TOKENS = 3
MC4_OUTCOME_ONLY = 4
MC5_FRAGMENT = 5
UNRANKABLE = None

#: RATIFIED: market > event > team. Preserved exactly, at 2 > 3 > 4.
#:
#: `concept` and `hub` are NOT covered by the ratified text, so placing them is
#: a reconstruction judgment — recorded as such in docs/search-scoring-spec.md,
#: and it is one dict to flip if Alex rules otherwise.
#:
#: They sit ABOVE market, and that placement was MEASURED rather than chosen.
#: The first draft put a concept below the market it aggregates, which reads
#: plausibly and cost seven gold probes: `grammys` answered "Grammy Winner: Best
#: New Artist" instead of The Grammys, `world cup` answered "2030 FIFA World Cup
#: Champion" instead of the 2026 tournament, `us open` answered a market whose
#: name is BYTE-IDENTICAL to the concept it displaced. In every case both sit in
#: the same class and the concept is the tighter answer, so kind order is the
#: only thing deciding — and a hub or concept is the page the user is looking
#: for when they type its name, with the markets reachable from it. An aggregate
#: that matches as well as its members outranks them.
#:
#: The ratified market > event > team relation is untouched by this: it governs
#: the three kinds it names, and nothing here reorders them.
KIND_ORDER: dict[str, int] = {
    "event_concept": 0,
    "concept": 0,
    "hub": 1,
    "futures": 2,
    "market": 2,
    "event": 3,
    "team": 4,
}
_KIND_ORDER_FALLBACK = 9

# --- the knobs -------------------------------------------------------------
# FIVE knobs, against a ratified ceiling of eight. Every default here is
# PROVISIONAL until the measured run, and a move is accepted only if net flips
# >= 2*sqrt(f) on the test split, at most two moves per cycle, one ranking change
# in flight at a time. Knobs tune ordering WITHIN a class; none of them can move
# a candidate across one.

#: Fragment similarity at or above this is "a real fragment" and orders ahead of
#: weaker ones INSIDE MC5. It is not an admission gate — see `match_class`.
TRIGRAM_FLOOR = 0.30
#: Below this query length, fragment similarity earns no ordering credit at all;
#: two-character overlaps are noise and should not reorder anything.
MIN_FRAGMENT_LEN = 3
#: A last token shorter than this is too weak to carry MC2 on its own.
PREFIX_MIN_LEN = 2
#: MC3 needs at least this fraction of the query's tokens present.
PARTIAL_MIN_COVERAGE = 0.5
#: Within a class and kind, a major professional league outranks the rest. This
#: is what separates `team:boston-bruins` from `team:belmont-bruins-ncaa` and
#: `team:new-england-patriots` from `team:california-baptist` — both are honest
#: MC1 token matches, so nothing above the knob layer can tell them apart.
PROMINENT_SPORT_KEYS: frozenset[str] = frozenset({
    "basketball_nba",
    "icehockey_nhl",
    "baseball_mlb",
    "americanfootball_nfl",
    "soccer_epl",
    "soccer_uefa_champs_league",
    "basketball_wnba",
    "mma_mixed_martial_arts",
})


# --- folding ---------------------------------------------------------------

_TOKEN_RE = re.compile(r"[0-9a-z]+")
_WS_RE = re.compile(r"\s+")


def _exact_key(text: str) -> str:
    """The MC0 key. Casefold and whitespace only — deliberately NOT a fold.

    "UNFOLDED" in the ruling means no stemming, no accent stripping and no
    punctuation stripping: at MC0 the claim is that the user typed the entity's
    name, so `Sao Paulo` must not become equal to `São Paulo` here (it can still
    meet at MC1). Casefold is retained because a typeahead query is typed
    lowercase by convention and case carries no meaning — that single point is
    the one reconstruction judgment inside MC0, and it is flagged in the spec.
    """
    return _WS_RE.sub(" ", unicodedata.normalize("NFC", text or "")).strip().casefold()


def _fold_token(token: str) -> str:
    """MC1+ folding: casefold, strip accents, strip one trailing plural `s`."""
    t = unicodedata.normalize("NFKD", token.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t


def tokens(text: str) -> tuple[str, ...]:
    """Folded token tuple. Order preserved; duplicates kept (the last token of a
    query is load-bearing for MC2, so this cannot return a set)."""
    lowered = unicodedata.normalize("NFKD", (text or "").casefold())
    lowered = "".join(c for c in lowered if not unicodedata.combining(c))
    return tuple(_fold_token(m) for m in _TOKEN_RE.findall(lowered))


def trigram_similarity(a: str, b: str) -> float:
    """Jaccard over padded 3-grams. Not Postgres' `similarity()` and not trying
    to be: MC5 is the bottom class, everything above it wins regardless, so this
    only has to decide whether a fragment is admitted at all."""
    def grams(s: str) -> set[str]:
        s = f"  {_WS_RE.sub(' ', (s or '').casefold().strip())} "
        return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else set()

    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


# --- evidence --------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """Everything a candidate is allowed to rank on, and nothing else.

    The `derived` flag is the load-bearing field. It marks a candidate whose
    only basis for being here at all is content belonging to something else —
    an event concept assembled from a member market, most importantly. Such a
    candidate is UNRANKABLE: not demoted, EXCLUDED. Demotion is not enough,
    because the Emmys concept won `super bowl` in a result set where nothing
    else had claimed the top slot.
    """

    name: str
    aliases: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    kind: str = "market"
    derived: bool = False
    sport_key: str | None = None
    #: Free tuple appended after every ruled term, for existing within-tier
    #: signals (volume, market_tier, commence_time...). Ascending = better.
    within_tier: tuple = field(default_factory=tuple)

    def owned_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


def match_class(query: str, ev: Evidence) -> int | None:
    """The match class of `ev` against `query`, or None if it must not rank."""
    if ev.derived:
        # Owned-evidence-only. The entire Emmys family dies on this line.
        return UNRANKABLE

    q_exact = _exact_key(query)
    if not q_exact:
        return UNRANKABLE

    # MC0 — exact, unfolded, against the name or any alias it owns.
    for own in ev.owned_names():
        if own and _exact_key(own) == q_exact:
            return MC0_EXACT

    q_tokens = tokens(query)
    if not q_tokens:
        return UNRANKABLE

    name_tokens: set[str] = set()
    for own in ev.owned_names():
        name_tokens.update(tokens(own))

    if name_tokens:
        # MC1 — every query token present in a name it owns.
        present = [t for t in q_tokens if t in name_tokens]
        if len(present) == len(q_tokens):
            return MC1_ALL_TOKENS

        # MC2 — all but the last matched, and the last is a live prefix.
        last = q_tokens[-1]
        if (
            len(last) >= PREFIX_MIN_LEN
            and all(t in name_tokens for t in q_tokens[:-1])
            and any(nt.startswith(last) for nt in name_tokens)
        ):
            return MC2_LAST_TOKEN_PREFIX

        # MC3 — some of the query landed, but not all of it.
        if present and len(present) / len(q_tokens) >= PARTIAL_MIN_COVERAGE:
            return MC3_PARTIAL_TOKENS

    # MC4 — a market may rank on its OWN outcomes when its name says nothing.
    if ev.outcomes:
        outcome_tokens: set[str] = set()
        for o in ev.outcomes:
            outcome_tokens.update(tokens(o))
        if outcome_tokens and all(t in outcome_tokens for t in q_tokens):
            return MC4_OUTCOME_ONLY

    # MC5 — the floor. Where `brito`, `tripolis` and `kaiserslautern` live.
    #
    # Anything non-derived that got this far lands here rather than being
    # dropped, and the distinction is the ruling's, not a convenience: the ONLY
    # thing declared UNRANKABLE is derived-only evidence. Recall belongs to the
    # SQL that built the candidate set — it already decided this row is a
    # candidate — and a scorer that also filters is a scorer that can empty a
    # result set while claiming to have ordered it. This reorders; it never
    # removes. (An earlier draft of this function returned UNRANKABLE here. The
    # property suite's own specimen check caught it, which is what that check
    # is for.)
    return MC5_FRAGMENT


def fragment_credit(query: str, ev: Evidence) -> float:
    """How good a fragment match is, for ordering WITHIN MC5. 0.0 = none."""
    q_exact = _exact_key(query)
    if len(q_exact) < MIN_FRAGMENT_LEN:
        return 0.0
    best = 0.0
    for own in ev.owned_names():
        if not own:
            continue
        own_exact = _exact_key(own)
        if q_exact in own_exact or own_exact in q_exact:
            best = max(best, 1.0)
            continue
        sim = trigram_similarity(q_exact, own_exact)
        if sim >= TRIGRAM_FLOOR:
            best = max(best, sim)
    return best


def kind_rank(kind: str) -> int:
    return KIND_ORDER.get((kind or "").lower(), _KIND_ORDER_FALLBACK)


def rank_key(query: str, ev: Evidence) -> tuple | None:
    """Sort key for one candidate, ascending. None means: do not rank it.

    The tuple is lexicographic and the class comes FIRST, which is the whole
    guarantee: no later term — kind, prominence, volume, recency — can lift a
    candidate over one in a better class.
    """
    mc = match_class(query, ev)
    if mc is UNRANKABLE:
        return None
    prominence = 0 if (ev.sport_key or "") in PROMINENT_SPORT_KEYS else 1
    # Negated so that a BETTER fragment sorts earlier under an ascending key.
    # Constant across MC0-MC4 candidates of equal class, so it cannot perturb
    # any ordering that the classes above already settled.
    fragment = -fragment_credit(query, ev) if mc == MC5_FRAGMENT else 0.0
    return (mc, kind_rank(ev.kind), prominence, fragment, *ev.within_tier)


# --- the evidence wire form ------------------------------------------------
#
# ONE definition of how an `Evidence` crosses a process boundary, owned by the
# module that owns `Evidence`. Both consumers import it: the endpoint echoes
# with `evidence_to_wire`, the offline harness rebuilds with
# `evidence_from_wire`. That is what "the harness and the endpoint agree by
# construction" means operationally — not two mappings kept in sync by care.
#
# WHY THIS EXISTS, MEASURED (LAT-P050, 2026-08-13, production v3804):
# the harness used to hand-roll `Evidence(name=display_name, kind=kind)` — two
# of six fields — off the typeahead RESPONSE. But the response is not the
# evidence: `typeahead_search` pops `_derived`, `_aliases` and `_outcome_names`
# before returning, precisely because they are ranking inputs and not payload.
# So the harness re-ranked production's own output with the evidence removed and
# scored 30/44 against production's measured 35/44 — it DEMOTED five correct
# answers (bruins, celtics, patriots, red-sox, yankees), every one a team that
# production had ranked MC0 on an alternate name the response strips. A team
# with its aliases withheld drops MC0 -> MC1, ties with a market, and loses on
# `KIND_ORDER` (team 4, market 2).
#
# That is the same withheld-evidence defect the ROUTE has now been fixed for
# three times (#1836, #1839, #1843) — committed by the instrument that grades
# the fixes, which is why a projected 39-41 band was published against an actual
# 32. An instrument cannot be trusted to measure a class of bug it contains.
#
#: Keys of the wire form. Frozen as data so a field added to `Evidence` without
#: a decision here fails the round-trip test instead of silently not crossing.
EVIDENCE_WIRE_KEYS: tuple[str, ...] = (
    "name",
    "aliases",
    "outcomes",
    "kind",
    "derived",
    "sport_key",
    "within_tier",
)


def evidence_to_wire(ev: Evidence) -> dict:
    """Serialize the evidence a candidate was actually ranked on, JSON-safely."""
    return {
        "name": ev.name,
        "aliases": list(ev.aliases),
        "outcomes": list(ev.outcomes),
        "kind": ev.kind,
        "derived": bool(ev.derived),
        "sport_key": ev.sport_key,
        "within_tier": list(ev.within_tier),
    }


def evidence_from_wire(payload: dict) -> Evidence:
    """Rebuild an `Evidence` from `evidence_to_wire`. Round-trip exact."""
    return Evidence(
        name=payload.get("name") or "",
        aliases=tuple(payload.get("aliases") or ()),
        outcomes=tuple(payload.get("outcomes") or ()),
        kind=payload.get("kind") or "market",
        derived=bool(payload.get("derived")),
        sport_key=payload.get("sport_key"),
        within_tier=tuple(payload.get("within_tier") or ()),
    )


def rank(query: str, candidates: list[tuple[Evidence, object]]) -> list[object]:
    """Rank `(evidence, payload)` pairs, dropping every UNRANKABLE one.

    Stable: candidates that tie on the full key keep their input order, so an
    upstream ordering that already means something is preserved rather than
    scrambled.
    """
    keyed = []
    for i, (ev, payload) in enumerate(candidates):
        k = rank_key(query, ev)
        if k is None:
            continue
        keyed.append((k, i, payload))
    keyed.sort(key=lambda row: (row[0], row[1]))
    return [payload for _, _, payload in keyed]
