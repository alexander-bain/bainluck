"""The nested ladder as ONE priced object, generalized past Over/Under.

WHAT THIS ADDS TO :mod:`app.utils.ladder_coherence`, and why it is a second
module rather than an edit to that one.

``ladder_coherence`` proves one law on one grammar: a Polymarket ``O/U`` total
over one game, rungs one unit apart, Over price strictly falling. That law is
airtight *because* of its grammar — half-integer lines over a discrete total
guarantee a real outcome between two rungs, which is what buys strictness — and
it is unusable anywhere else, because it hard-codes the literal token ``O/U``
and a fixed adjacency step of exactly one.

The same *shape* is everywhere else in the book under different words::

    P(revenue above $10.5B)  >=  P(revenue above $11.5B)
    P(released by June 5)    <=  P(released by June 12)
    P(cases >= 2400)         >=  P(cases >= 2450)

Each is a nested family: one rung's event CONTAINS the next one's. Containment
is the whole argument, and it needs no model, no book and no outcome. This
module is that law, and it carries three deliberate weakenings relative to the
O/U one, each of which is a measurement rather than a convenience.

**ONE — ADJACENCY IS CONSECUTIVE-IN-SORTED-ORDER, NOT A FIXED STEP.** O/U could
say "one unit apart" because a total moves in goals. Threshold ladders step in
whatever the desk chose ($1.0T, $1.2T, $1.4T ... but also $172.5B) and date
ladders step irregularly (June 5, 12, 19, 26, 30, July 31). There is no step to
fix, so the general adjacency is "the next rung up that exists". Containment
holds between ANY two rungs of a nested family, so comparing consecutive ones
loses no violation: if the sequence is out of order anywhere, some consecutive
pair is out of order.

**TWO — THE LAW IS NON-STRICT, SO EQUALITY IS NOT A VIOLATION.** This is the
weakening that matters and it is the one most likely to be misquoted. O/U gets
strictness free: two rungs one goal apart cannot carry the same probability, so
an exactly-equal pair is an arithmetic contradiction, and that shape was the
LARGEST single class it condemned (250 of 631 pairs). Here the rungs can be a
day apart or $25M apart on a quantity that may have no mass in between, so
equality is consistent with the law and is not condemned. It is counted and
reported separately as ``flat_pairs``, because a long run of identical prices is
still the signature of a templated ladder — it is simply not a *proof*, and
ruling 083's clause applies: a guard that cannot tell two cases apart is given
evidence, not a wider band. **Anyone porting the O/U result here should expect
to condemn less, and the reason is this paragraph, not a weaker search.**

**THREE — DIRECTION IS PART OF THE FAMILY KEY.** The law has a sign, so two
rungs pointing opposite ways are not comparable and must never share a family.
This is not hypothetical. Measured on ``polymarket/tech`` (see below), the
valuation ladders publish a HIGH leg and a LOW leg under names that differ ONLY
in the direction marker::

    Will OpenAI's valuation hit (HIGH) $1.0T by December 31?
    Will OpenAI's valuation hit  (LOW) $500B by December 31?

Blanking the rung span collapses both to ``will openai's valuation <rung> by
december 31?``. With direction outside the key, **13 families** merged a
descending ladder into an ascending one, and applying either sign would have
manufactured violations across the whole merged family. That is the esports
key-collapse failure of ``ladder_coherence.read_ladders`` in a new costume, and
it is guarded the same way: by making the key finer, never by loosening the law.

TWO SITES, because the rung token lives in two different places.

``NAME`` site — each rung is its own market and the rung is in the market name;
the price is the YES leg. This is the cross-market ladder the directive named.

``OUTCOME`` site — the whole ladder is inside ONE market's outcome list, as bare
``2400+`` / ``2450+`` thresholds. It has no key-collapse hazard at all, because
the market id IS the family. It also carries a hard discriminator that must not
be skipped: a ``quantity`` market's outcomes are USUALLY mutually exclusive
brackets, and monotonicity is FALSE for those::

    113766  How many SpaceX Starship launches reach space in 2026?
            <5  0.215 | 5-6 0.305 | 7-8 0.100 | 9-10 0.220 | ... | >16 0.072

Those brackets partition; they do not nest, and they are supposed to sum to one
rather than fall. So the outcome site fires ONLY when EVERY outcome of the
market parses as a bare ``X+`` threshold — a range, a ``<5``, an ``or less`` or
any non-numeric leg disqualifies the whole market. Measured on
``polymarket/tech``: **21 quantity markets are all-plus, 84 carry a ``+`` leg
but are mixed** and are therefore left alone. Failing toward "not a ladder" is
the same fail-safe direction ``ladder_coherence`` takes with ambiguous keys.

⚠️ EVERY NUMBER IN THIS DOCSTRING IS MEASURED ON ``polymarket/tech`` by
``artifacts/cal-p133/ladder-monotonicity-census.py``, whose JSON output is
committed beside it. Two parser defects were found by that census and both are
guarded by name in ``backend/tests/test_ladder_monotonicity.py``:

* ``at least 2000 measles cases`` parsed the ``m`` of "measles" as a MEGA scale
  suffix and read 2,000 as 2e9, and simultaneously corrupted the family key to
  ``<rung> easles cases``. The scale suffix now has to end on a word boundary.
* ``Will Anthropic provide Mythos to the US government by April 30, 2026?``
  matched ``over`` inside "g-over-nment" and then bound it to the ``30`` of
  "April 30", inventing a threshold rung on a pure date market. Direction words
  are now boundary-anchored and the number must follow immediately.

Both were caught only because the ambiguity census PRINTS the families it
refuses instead of silently dropping them. A parser that reports what it could
not place is how a grammar gets debugged (gotcha #53).

WHAT THIS MODULE DOES NOT DO. It never reads an outcome. Every function here is
a function of names and prices, so the predicate cannot be fitted to
``is_winner`` and a holdout tests stability rather than leakage. It writes
nothing (gotcha #21). It is not a fifth ECE either — callers needing one use
:func:`app.utils.ladder_coherence.cell_ece_pp`, which delegates to
:mod:`app.utils.calibration_ece`.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

#: A ladder whose price must NOT RISE as the rung value rises. "above $X",
#: "at least X", the HIGH leg of a valuation pair, and a bare ``X+`` bracket.
DEC = "dec"

#: A ladder whose price must NOT FALL as the rung value rises. "by <date>"
#: (later dates contain earlier ones), "below $X", the LOW leg of a pair.
INC = "inc"

#: Multiplier for a magnitude suffix. ``bn`` is listed before the single
#: letters in the pattern below so the two-character form wins the alternation.
SCALE = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12, "bn": 1e9}

_MONTHS = {m[:3]: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}

#: Direction words. ``(?<![a-z])``/``(?![a-z])`` rather than ``\b`` because the
#: failure this guards is a direction word found INSIDE another word —
#: "g(over)nment" — and a bare ``\b`` on an alternation whose branches end in
#: punctuation (``(HIGH)``) does not apply uniformly. Stated as an explicit
#: lookaround so the guard is visible at the site it protects.
_UP_WORDS = (r"(?<![a-z])(?:above|over|at least|more than|greater than|"
             r"exceeds?|reaches?|hits?)(?![a-z])|hit \(HIGH\)|\(HIGH\)")
_DOWN_WORDS = (r"(?<![a-z])(?:below|under|at most|less than|fewer than|"
               r"no more than)(?![a-z])|hit \(LOW\)|\(LOW\)")

#: A magnitude. The trailing ``\b`` on the unit is load-bearing: without it the
#: ``m`` of "measles" is consumed as MEGA and 2,000 reads as 2,000,000,000.
_NUM = (r"\s*\$?\s*(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\b%?")

#: The number must follow the direction word IMMEDIATELY (only whitespace and a
#: currency mark between). Allowing slop is what let "government" bind to the
#: "30" of "April 30" three words later.
THRESHOLD_RE = re.compile(rf"(?P<word>{_UP_WORDS}|{_DOWN_WORDS}){_NUM}", re.I)

_DOWN_ONLY_RE = re.compile(rf"^(?:{_DOWN_WORDS})$", re.I)

#: ``by <Month> <day>[, <year>]`` or ``by <year>``. A bare year is pinned to its
#: last day so it sorts after every dated rung inside it.
BY_DATE_RE = re.compile(
    r"\bby\s+(?:"
    r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"(?P<day>\d{1,2})(?:,\s*(?P<yr>\d{4}))?"
    r"|(?P<bare>\d{4})"
    r")", re.I)

#: The outcome-site rung: a bare magnitude with a trailing ``+`` and NOTHING
#: else. Anchored at both ends on purpose — ``2400-2450+`` must not parse.
PLUS_BRACKET_RE = re.compile(
    r"^\s*\$?\s*(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\s*\+\s*$", re.I)

#: A date with no explicit year is read as this year. Every rung of a family
#: gets the same default, so an undated family still sorts correctly; a family
#: that MIXES dated and undated rungs across a year boundary is the known limit
#: of this default and is why :func:`ladder_report` publishes ``assumed_year``.
DEFAULT_YEAR = 2026

LADDER_MONOTONICITY_RULE_TEXT = (
    "A nested ladder is a single priced object: where one rung's event contains "
    "the next one's, the published prices must be ordered the same way — "
    "non-increasing in the threshold for an 'above X' family, non-decreasing in "
    "the date for a 'by D' family. A family carrying a strict reversal between "
    "consecutive rungs was not priced against itself, so EVERY rung of that "
    "family is excluded from the published curve — the family is the unit, not "
    "the rung (ruling 111). Equality is NOT a reversal here, unlike the O/U "
    "rule: these rungs can sit arbitrarily close together, so a flat pair is "
    "consistent with the law and is reported as evidence rather than condemned. "
    "A family of one rung is never condemned (ruling 105), and a family whose "
    "key demonstrably groups two ladders is KEPT, not condemned. Read-side "
    "only; never mutates is_winner or calibration_probability."
)


# ---------------------------------------------------------------------------
# Rung grammars. Each returns ``(span, value, direction)`` or ``None``.
# ---------------------------------------------------------------------------

def _magnitude(val: str, unit: str | None) -> float:
    out = float(val.replace(",", ""))
    if unit:
        out *= SCALE[unit.lower()]
    return out


def parse_threshold(text: str | None) -> tuple[tuple[int, int], float, str] | None:
    """A ``above/at least/below X`` rung, or ``None``.

    The direction comes from the word, never from the number, and never from
    the surrounding sentence: "hit (LOW) $15B" is an ascending rung even though
    "hit" reads like an upward verb, because the parenthesised marker is what
    Polymarket uses to name the leg.
    """
    if not text:
        return None
    m = THRESHOLD_RE.search(text)
    if not m:
        return None
    direction = INC if _DOWN_ONLY_RE.match(m.group("word")) else DEC
    return m.span(), _magnitude(m.group("val"), m.group("unit")), direction


def parse_by_date(text: str | None) -> tuple[tuple[int, int], float, str] | None:
    """A ``by <date>`` rung as a sortable ``YYYYMMDD``, or ``None``.

    Always ascending: "by June 12" contains "by June 5", so its probability can
    only be greater or equal. The value is an integer-valued float rather than a
    ``date`` so every grammar in this module hands the comparison layer the same
    type and the sort never has to branch on which parser produced a rung.
    """
    if not text:
        return None
    m = BY_DATE_RE.search(text)
    if not m:
        return None
    if m.group("bare"):
        return m.span(), float(m.group("bare")) * 10000 + 1231, INC
    value = (int(m.group("yr") or DEFAULT_YEAR) * 10000
             + _MONTHS[m.group("mon").lower()[:3]] * 100
             + int(m.group("day")))
    return m.span(), float(value), INC


def parse_plus_bracket(text: str | None) -> tuple[tuple[int, int], float, str] | None:
    """A bare ``2400+`` outcome-site rung, or ``None``. Always descending."""
    if not text:
        return None
    m = PLUS_BRACKET_RE.match(text)
    if not m:
        return None
    return m.span(), _magnitude(m.group("val"), m.group("unit")), DEC


#: The NAME-site grammars, in the order they are tried. A name may satisfy both
#: — "hit (HIGH) $210B by June 30" is a rung of a threshold ladder AND a rung of
#: a date ladder — and :func:`name_rungs` deliberately returns both.
NAME_GRAMMARS = (parse_threshold, parse_by_date)


def blanked_key(name: str, span: tuple[int, int]) -> str:
    """The family a rung belongs to: its text with THAT rung span replaced.

    Replaced rather than deleted, and only the ONE span, which is what makes a
    two-dimensional family work. "Will Stripe's valuation hit (HIGH) $210B by
    June 30?" belongs to a threshold family (June 30 stays literal in the key)
    and to a date family ($210B stays literal). Deleting both at once would
    merge every rung of the grid into one family and compare a rung against one
    that varies on the other axis.
    """
    stripped = name[:span[0]] + " <RUNG> " + name[span[1]:]
    return " ".join(stripped.split()).strip(" :-").casefold()


def name_rungs(name: str | None) -> list[tuple[tuple[str, str], float]]:
    """Every ``((family_key, direction), value)`` this market name contributes.

    Direction is inside the key rather than beside it because the law has a
    sign — see weakening THREE in the module docstring, and the 13 valuation
    families it was measured on.
    """
    if not name:
        return []
    out: list[tuple[tuple[str, str], float]] = []
    for grammar in NAME_GRAMMARS:
        parsed = grammar(name)
        if parsed is None:
            continue
        span, value, direction = parsed
        out.append(((blanked_key(name, span), direction), value))
    return out


# ---------------------------------------------------------------------------
# The law.
# ---------------------------------------------------------------------------

def monotonicity_violations(
    rungs: Mapping[float, float], direction: str,
) -> list[tuple[float, float, float, float]]:
    """Every consecutive pair whose price is ordered the WRONG way. Evidence.

    ``rungs`` maps rung value -> price. Returns ``(low_value, low_price,
    high_value, high_price)`` for each consecutive pair, in ascending value
    order, that STRICTLY contradicts ``direction``. A list rather than a count,
    because a cert has to be able to name the pair it is arguing about — the
    same reason ``ladder_coherence.adjacent_violations`` returns one.

    Equality never appears here. That is the documented weakening, not an
    oversight: see :func:`flat_pairs`, which is where a caller looks for it.
    """
    if direction not in (DEC, INC):
        raise ValueError(f"direction must be {DEC!r} or {INC!r}, got {direction!r}")
    ordered = sorted(v for v, p in rungs.items() if p is not None)
    out: list[tuple[float, float, float, float]] = []
    for low, high in zip(ordered, ordered[1:]):
        low_p, high_p = float(rungs[low]), float(rungs[high])
        broken = high_p > low_p if direction == DEC else high_p < low_p
        if broken:
            out.append((low, low_p, high, high_p))
    return out


def flat_pairs(
    rungs: Mapping[float, float],
) -> list[tuple[float, float, float, float]]:
    """Consecutive pairs carrying the SAME price, in ascending value order.

    Reported and never condemned. On the O/U grammar an equal pair is an
    arithmetic contradiction and was the single largest violating shape; here
    two rungs can be a day or a rounding step apart, so an equal pair is
    consistent with the law. It is still the signature of a templated ladder,
    so it is surfaced as its own count and left for a rule design to argue
    about with evidence in hand.
    """
    ordered = sorted(v for v, p in rungs.items() if p is not None)
    return [(low, float(rungs[low]), high, float(rungs[high]))
            for low, high in zip(ordered, ordered[1:])
            if float(rungs[low]) == float(rungs[high])]


def ladder_is_incoherent(rungs: Mapping[float, float], direction: str) -> bool:
    """True when this family carries at least one strict reversal.

    A family of one rung is never incoherent. Stated as its own early return
    rather than left to fall out of the loop, because "no pairs, so no
    violations" and "deliberately exempt" are the same answer for opposite
    reasons and a reader is entitled to see which one is meant (gotcha #53).
    """
    if len(rungs) < 2:
        return False
    return bool(monotonicity_violations(rungs, direction))


# ---------------------------------------------------------------------------
# The NAME site: one market per rung.
# ---------------------------------------------------------------------------

def read_name_ladders(
    rows: Iterable[Mapping[str, object]],
    *,
    name_key: str = "name",
    price_key: str = "yes_price",
    id_key: str = "market_id",
) -> dict[tuple[str, str], dict]:
    """Group rung markets into families, and record where the grouping is UNSAFE.

    Returns ``(key, direction) -> {"rungs": {value: price}, "duplicate_values":
    {value: count}, "member_ids": [...], "rows": n}``.

    ``duplicate_values`` is the load-bearing output, for the reason
    ``ladder_coherence.read_ladders`` gives: two rows on the same (family,
    value) is proof that the key is not identifying a single ladder, never that
    the ladder is bad. Measured on ``polymarket/tech`` it fires on 11 families,
    and every one is a genuine re-listing of the same question under a second
    market id ("AWS service disrupted by March 31?" exists three times), which
    is exactly the case where condemning would be wrong.
    """
    ladders: dict[tuple[str, str], dict] = {}
    for row in rows:
        name = row.get(name_key)
        price = row.get(price_key)
        if not isinstance(name, str) or price is None:
            continue
        for key, value in name_rungs(name):
            slot = ladders.setdefault(
                key, {"rungs": {}, "duplicate_values": {}, "member_ids": [], "rows": 0})
            slot["rows"] += 1
            slot["member_ids"].append(row.get(id_key))
            rung = round(float(value), 6)
            if rung in slot["rungs"]:
                slot["duplicate_values"][rung] = slot["duplicate_values"].get(rung, 1) + 1
                continue
            slot["rungs"][rung] = float(price)
    return ladders


# ---------------------------------------------------------------------------
# The OUTCOME site: one market holding the whole ladder.
# ---------------------------------------------------------------------------

def outcome_ladder(
    outcomes: Sequence[Mapping[str, object]],
    *,
    name_key: str = "name",
    price_key: str = "price",
) -> dict[float, float] | None:
    """The market's rungs when its outcome list is a CUMULATIVE ladder, else None.

    The discriminator, and it is the whole safety argument for this site: a
    market qualifies only when it has at least two outcomes and EVERY ONE of
    them parses as a bare ``X+`` threshold. A range leg (``5-6``), a tail leg
    (``<5``, ``>16``), an ``or less``, a ``Yes``/``No`` or any prose leg
    disqualifies the market outright.

    That strictness is not fussiness. A ``quantity`` market's outcomes are
    usually mutually exclusive BRACKETS, which partition rather than nest and
    are supposed to sum to one rather than fall; applying a monotonicity law to
    them would condemn a correctly priced market. Measured on
    ``polymarket/tech``: 21 markets are all-plus and 84 carry a ``+`` leg
    alongside something else and are left alone.

    A rung with no price does not disqualify the market — it simply takes no
    part, the same way a priceless rung does at the name site. A DUPLICATE rung
    value does disqualify it, because that is the outcome-site form of a key
    that groups two ladders.
    """
    if len(outcomes) < 2:
        return None
    rungs: dict[float, float] = {}
    for row in outcomes:
        name = row.get(name_key)
        parsed = parse_plus_bracket(name if isinstance(name, str) else None)
        if parsed is None:
            return None
        _, value, _ = parsed
        price = row.get(price_key)
        if price is None:
            continue
        rung = round(float(value), 6)
        if rung in rungs:
            return None
        rungs[rung] = float(price)
    return rungs if len(rungs) >= 2 else None


# ---------------------------------------------------------------------------
# The verdict, and the census that has to be printed alongside it.
# ---------------------------------------------------------------------------

def ambiguous_families(ladders: Mapping[tuple[str, str], Mapping]) -> set:
    """Families whose key demonstrably groups more than one ladder."""
    return {key for key, v in ladders.items() if v["duplicate_values"]}


def condemned_families(ladders: Mapping[tuple[str, str], Mapping]) -> set:
    """The family keys to exclude. Ambiguous families are KEPT, never condemned.

    This rule deletes rows from the published curve, so where its own premise —
    "these rungs are one ladder" — is disproven by a duplicate value, it fails
    toward keeping them. ``ladder_coherence`` found that guard the hard way,
    when a key collapsed 231 esports markets into one family and a
    fail-toward-condemning rule would have deleted a cell it has no business
    touching.
    """
    ambiguous = ambiguous_families(ladders)
    return {key for key, v in ladders.items()
            if key not in ambiguous
            and ladder_is_incoherent(v["rungs"], key[1])}


def ladder_report(
    rows: Iterable[Mapping[str, object]],
    *,
    name_key: str = "name",
    price_key: str = "yes_price",
    id_key: str = "market_id",
) -> dict:
    """The NAME site end to end: id partition plus the census that produced it.

    Returns ``drop`` / ``ambiguous`` / ``coherent`` id sets and a ``census``.
    The three sets are disjoint by construction and a market that contributes
    rungs to two families (the two-dimensional valuation grid) is condemned if
    EITHER family is condemned — a market priced inconsistently against its own
    date ladder is not rescued by being consistent against its threshold ladder.

    ``census`` is printed rather than summarised by callers, because a run where
    the ambiguity guard swallowed the population would otherwise look
    identical to a run where the rule found nothing (gotcha #53).
    """
    rows = list(rows)
    ladders = read_name_ladders(
        rows, name_key=name_key, price_key=price_key, id_key=id_key)
    ambiguous = ambiguous_families(ladders)
    condemned = condemned_families(ladders)

    drop: set = set()
    amb_ids: set = set()
    coherent: set = set()
    for row in rows:
        name = row.get(name_key)
        if not isinstance(name, str) or row.get(price_key) is None:
            continue
        keys = [k for k, _ in name_rungs(name)]
        keys = [k for k in keys if len(ladders.get(k, {}).get("rungs", {})) >= 2]
        if not keys:
            continue
        mid = row.get(id_key)
        if any(k in condemned for k in keys):
            drop.add(mid)
        elif any(k in ambiguous for k in keys):
            amb_ids.add(mid)
        else:
            coherent.add(mid)
    # A market condemned by one family must not also appear as merely ambiguous
    # or coherent via another; the strongest verdict wins and the sets stay
    # disjoint so a caller can size them by addition.
    amb_ids -= drop
    coherent -= drop | amb_ids

    multi = {k: v for k, v in ladders.items() if len(v["rungs"]) >= 2}
    violations = sum(len(monotonicity_violations(v["rungs"], k[1]))
                     for k, v in multi.items() if k not in ambiguous)
    flats = sum(len(flat_pairs(v["rungs"])) for k, v in multi.items()
                if k not in ambiguous)
    # Scoped to multi-rung families so it can be reconciled against
    # ``markets_ambiguous``. A family whose ONLY rung value is duplicated has no
    # pair to test, so it is untestable rather than ambiguous, and its markets
    # appear in none of the three id sets — counting it here would make the
    # family census and the market census disagree for no reason a reader could
    # discover (gotcha #53).
    return {
        "drop": drop,
        "ambiguous": amb_ids,
        "coherent": coherent,
        "census": {
            "rows_scanned": len(rows),
            "families": len(ladders),
            "families_singleton": len(ladders) - len(multi),
            "families_multi_rung": len(multi),
            "families_ambiguous": len(ambiguous & set(multi)),
            "families_untestable_duplicate_only": len(ambiguous - set(multi)),
            "families_condemned": len(condemned),
            "violating_pairs": violations,
            "flat_pairs": flats,
            "markets_drop": len(drop),
            "markets_ambiguous": len(amb_ids),
            "markets_coherent": len(coherent),
            "assumed_year": DEFAULT_YEAR,
        },
    }
