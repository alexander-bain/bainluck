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

WHAT THIS MODULE DOES NOT DO. It writes nothing (gotcha #21). It is not a fifth
ECE either — callers needing one use :func:`app.utils.ladder_coherence.cell_ece_pp`,
which delegates to :mod:`app.utils.calibration_ece`.

**THE LEAKAGE LINE, AND IT RUNS THROUGH THE MIDDLE OF THIS FILE.** Everything up
to the CAL-P134 section is a function of names and prices only: the predicate
cannot be fitted to ``is_winner``, so a holdout there tests stability rather
than leakage. :func:`truth_reversals` and :func:`outcome_ladder_report` DO read
the outcome, deliberately, and a rule built on them is a truth-ELIGIBILITY
finding rather than a leakage-free exclusion — the distinction is argued at
:func:`truth_reversals` and must travel with any number quoted from it.
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

#: The two-sided ``O/U`` line, written as ONE token. Polymarket's sports book
#: names a total this way — ``Trujillanos FC vs. Monagas SC: O/U 3.5``,
#: ``Map 1 Total Rounds: Over/Under 24.5`` — and prices it with ``Over`` and
#: ``Under`` legs rather than a ``Yes`` leg.
#:
#: 🔴 THIS PATTERN EXISTS TO FIX A SIGN INVERSION, NOT TO ADD COVERAGE. Measured
#: by ``artifacts/cal-p135/polymarket-name-ladder-census.py``: on 19,766
#: ``polymarket/esports`` names, :data:`THRESHOLD_RE` already matched — but it
#: matched the ``Under`` half of the compound, because ``_NUM`` permits only
#: whitespace between the direction word and the number, so the ``Over`` (with
#: a ``/`` after it) cannot bind and the ``Under`` (adjacent to the number) can.
#: The very tightness that stops "g-over-nment" binding to "April 30" is what
#: picks the WRONG HALF of "Over/Under". The resulting rung was filed as
#: ``inc`` — the exact inverse of the truth, since the Over price FALLS as the
#: line rises — under a key that had silently swallowed the word ``Over``
#: (``map 1 total rounds: over/ <RUNG>``).
#:
#: That inversion is latent rather than live: the ``duplicate_values`` guard
#: currently marks nearly every such family ambiguous, so only 2 families were
#: condemned. It detonates the moment a caller scopes the family key to a real
#: event identity, which is the obvious next fix — measured, that turns 2
#: condemned families into 1,296, and they are the ladders behaving CORRECTLY.
#: Anyone adding an identity-scoped key must land this pattern with it.
OVER_UNDER_RE = re.compile(
    rf"(?<![a-z])(?:o\s*/\s*u|over\s*/\s*under){_NUM}", re.I)

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


def parse_over_under(text: str | None) -> tuple[tuple[int, int], float, str] | None:
    """An ``O/U 3.5`` line as a DESCENDING rung, or ``None``.

    Descending is not a convention, it is the containment argument: the priced
    side of an over/under line is the OVER side, and "total over 4.5" is
    contained in "total over 3.5", so the Over price can only fall as the line
    rises. The sign therefore belongs to the compound token and is fixed here
    rather than read off a direction word — which is the whole point, because
    the direction word this compound presents LAST is ``Under``.

    The span covers the entire ``O/U <line>`` token, not just the number, so
    :func:`blanked_key` blanks the whole line and two rungs of one total agree
    on a family key. Blanking only the number would leave ``over/`` in the key,
    which is how the defect this function replaces stayed readable-looking.
    """
    if not text:
        return None
    m = OVER_UNDER_RE.search(text)
    if not m:
        return None
    return m.span(), _magnitude(m.group("val"), m.group("unit")), DEC


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
NAME_GRAMMARS = (parse_over_under, parse_threshold, parse_by_date)


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
    parses = []
    for grammar in NAME_GRAMMARS:
        parsed = grammar(name)
        if parsed is not None:
            parses.append(parsed)

    # A COMPOUND TOKEN OWNS ITS NUMBER. Where one grammar's span strictly
    # contains another's, the inner parse is a fragment of the outer one and is
    # dropped. This is what stops "Over/Under 24.5" yielding BOTH a descending
    # O/U rung and the ascending "Under 24.5" rung that THRESHOLD_RE finds
    # inside it — two families, opposite signs, from one line, one of them
    # wrong. Containment rather than overlap is deliberate: the two-dimensional
    # valuation grid ("hit (HIGH) $210B by June 30") produces DISJOINT spans and
    # must keep contributing to both its threshold and its date family.
    out: list[tuple[tuple[str, str], float]] = []
    for span, value, direction in parses:
        if any(other[0] <= span[0] and span[1] <= other[1] and other != span
               for other, _, _ in parses):
            continue
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

#: CAL-P136. The PRICE site, and it is a separate blindness from the grammar.
#:
#: Every caller of this module so far has priced a rung with a leg literally
#: named ``yes`` — that is what ``MONO_ROWS_SQL`` selects, and a market with no
#: such leg gets a NULL price and is dropped before any grammar runs. Polymarket's
#: two-sided totals book has no ``yes`` leg at all: it prices ``Over`` and
#: ``Under``. Measured by CAL-P135, ``polymarket/baseball`` has ZERO O/U-named
#: markets with a yes leg and ``polymarket/soccer`` has two, so on those cells
#: the grammar fix landed by CAL-P135 buys nothing on its own.
#:
#: 🔴 THE LEG IS NOT INTERCHANGEABLE WITH THE PROPOSITION. ``Over`` and ``Under``
#: price OPPOSITE claims, so substituting the wrong one inverts the law's sign
#: exactly as reading the ``Under`` half of the compound did (see
#: :data:`OVER_UNDER_RE`). The substitution below is therefore deliberately
#: narrow and REFUSES rather than guesses:
#:
#:   * a ``yes`` leg always wins — it is what every existing measurement used,
#:     and changing that would silently re-base the shipped cells;
#:   * ``over`` substitutes ONLY on a market that carries BOTH an ``over`` and an
#:     ``under`` leg (proof of the two-sided pair shape, rather than a market
#:     that merely happens to own an outcome called "over") AND whose name parses
#:     as the :func:`parse_over_under` compound, whose direction is fixed at
#:     :data:`DEC` by containment rather than read off a word;
#:   * every other shape yields no price and a REASON, which callers count.
#:
#: The reason codes exist because of lesson 22: a refusal that is not counted is
#: indistinguishable from a clean cell.
YES_LEG, OVER_LEG, UNDER_LEG = "yes_price", "over_price", "under_price"

#: Where :func:`ladder_report` parks the price it resolved, when it was asked to
#: resolve one. Private, and named so it cannot collide with a caller's column.
_RESOLVED_PRICE = "_resolved_price"


def proposition_price(
    row: Mapping[str, object],
    *,
    name_key: str = "name",
    yes_key: str = YES_LEG,
    over_key: str = OVER_LEG,
    under_key: str = UNDER_LEG,
) -> tuple[float | None, str]:
    """``(price, reason)`` for the proposition this market's NAME asserts.

    ``reason`` is ``"yes"`` or ``"over"`` when a price was found, and otherwise
    names the refusal: ``"no_name"``, ``"no_leg"`` (neither a yes nor a complete
    over/under pair), ``"half_pair"`` (an over or under leg without its twin,
    which is not the two-sided shape and may be a one-sided ask placeholder), or
    ``"not_ou_named"`` (a genuine two-sided pair whose name this module's
    grammars do not read as an O/U compound, so which side is being asserted is
    unknown).

    Never raises on a missing key: a caller pulling only a yes leg gets exactly
    the behaviour it had before this function existed.
    """
    name = row.get(name_key)
    if not isinstance(name, str) or not name:
        return None, "no_name"
    yes = row.get(yes_key)
    if yes is not None:
        return float(yes), "yes"
    over, under = row.get(over_key), row.get(under_key)
    if over is None and under is None:
        return None, "no_leg"
    if over is None or under is None:
        return None, "half_pair"
    if parse_over_under(name) is None:
        return None, "not_ou_named"
    return float(over), "over"


#: Separates the identity context from the blanked name inside a family key.
#: A unit separator rather than a printable character so it can never occur in
#: a market name and accidentally merge or split a family.
CONTEXT_SEP = "\x1f"


def scoped_key(context: object, blanked: str) -> str:
    """The family-key string, optionally scoped to an identity.

    ``None`` context returns the bare blanked name, so a caller that does not
    supply an identity gets byte-identical keys to every measurement taken
    before CAL-P136.
    """
    if context is None:
        return blanked
    return f"{context}{CONTEXT_SEP}{blanked}"


def read_name_ladders(
    rows: Iterable[Mapping[str, object]],
    *,
    name_key: str = "name",
    price_key: str = "yes_price",
    id_key: str = "market_id",
    context_key: str | None = None,
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

    ``context_key`` names a row column holding an IDENTITY, and when given, the
    family key is scoped to it (:func:`scoped_key`). This is the fix for the
    hazard the module docstring has always named and CAL-P135 finally measured:
    a Polymarket sub-market's name is frequently context-free ("Games Total: O/U
    2.5"), so ``blanked_key`` alone collapses unrelated matches into one family
    — largest measured, 5,811 markets across 409 events. Scoping the key is NOT
    merely a refinement of the census; it changes which families are
    condemnable, because ``duplicate_values`` was the only thing standing
    between that collapse and a rule that deletes rows.

    🔴 SCOPING THE KEY REQUIRES THE :data:`OVER_UNDER_RE` SIGN FIX. Under the
    pre-CAL-P135 grammar the compound's ``Under`` half bound and the family was
    filed ``inc``, the exact inverse of the truth; the collapse was the only
    reason that inversion stayed latent. CAL-P135 measured what scoping the key
    without the sign fix would do: 2 condemned families become 1,296, and they
    are the ladders behaving CORRECTLY. The two land together or not at all.

    Left ``None``, every key is byte-identical to the pre-CAL-P136 behaviour.
    """
    ladders: dict[tuple[str, str], dict] = {}
    for row in rows:
        name = row.get(name_key)
        price = row.get(price_key)
        if not isinstance(name, str) or price is None:
            continue
        context = row.get(context_key) if context_key is not None else None
        for (blanked, direction), value in name_rungs(name):
            key = (scoped_key(context, blanked), direction)
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
    price_key: str | None = "yes_price",
    id_key: str = "market_id",
    context_key: str | None = None,
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

    ``context_key`` is forwarded to :func:`read_name_ladders` and is applied
    again when this function re-derives each row's keys, so the partition and
    the family census are always built from the SAME key. Deriving them from
    two different keys is the shape of bug that makes a census reconcile
    against nothing.

    ``price_key=None`` selects the price with :func:`proposition_price` instead
    of reading one fixed column, which is how a caller reaches a book that is
    not priced with a ``yes`` leg. The refusal tally lands in the census as
    ``price_legs`` — where a reader sees it next to the verdict, because a cell
    whose whole population was refused at the price site reads exactly like a
    clean cell otherwise (lesson 22).
    """
    rows = [dict(r) for r in rows]
    price_legs: dict[str, int] = {}
    if price_key is None:
        price_key = _RESOLVED_PRICE
        for row in rows:
            price, reason = proposition_price(row, name_key=name_key)
            price_legs[reason] = price_legs.get(reason, 0) + 1
            row[_RESOLVED_PRICE] = price
    ladders = read_name_ladders(
        rows, name_key=name_key, price_key=price_key, id_key=id_key,
        context_key=context_key)
    ambiguous = ambiguous_families(ladders)
    condemned = condemned_families(ladders)

    drop: set = set()
    amb_ids: set = set()
    coherent: set = set()
    for row in rows:
        name = row.get(name_key)
        if not isinstance(name, str) or row.get(price_key) is None:
            continue
        context = row.get(context_key) if context_key is not None else None
        keys = [(scoped_key(context, blanked), direction)
                for (blanked, direction), _ in name_rungs(name)]
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
            "price_legs": price_legs,
            "context_scoped": context_key is not None,
        },
    }


# ---------------------------------------------------------------------------
# CAL-P134 — the OUTCOME site as Kalshi actually writes it, and the TRUTH law.
# ---------------------------------------------------------------------------
#
# WHY THIS SECTION EXISTS. Everything above was measured on Polymarket, where a
# ladder rung is a market and the price is its YES leg. Folding ``--by mono``
# over ``kalshi/economics`` — the cell where threshold ladders were most certain
# to live — returned 46 families and one condemned pair, which reads as an
# all-clear and is nothing of the kind. Kalshi does not write ``2400+`` and
# mostly does not put the rung in the market name at all. It writes the whole
# ladder inside one market's outcome list, in three shapes::
#
#     Above 410M          above $68.25          7,175 or above
#
# 4,621 of the 7,590 markets in that cell are all-cumulative in exactly this
# sense. :func:`parse_plus_bracket` refuses every one of them, and the
# ``MONO_ROWS_SQL`` pre-pass cannot even see them, because they have no leg
# named ``yes``. The instrument reported its own blindness as a clean cell
# (gotcha #53).
#
# The safety argument of :func:`outcome_ladder` is unchanged and is what makes
# this extension legal: a market qualifies only when EVERY leg parses as a
# cumulative threshold pointing the SAME WAY. A ``quantity`` market's legs are
# usually mutually exclusive brackets (``<5``, ``5-6``, ``>16``) which partition
# rather than nest, and a mixed or opposite-signed leg disqualifies the market
# outright rather than widening the law.

#: ``Above 410M``, ``above $68.25``, ``over 3.5%`` — the direction word LEADS.
_CUMULATIVE_PRE_RE = re.compile(
    rf"^\s*(?P<word>{_UP_WORDS}|{_DOWN_WORDS}){_NUM}\s*$", re.I)

#: ``7,175 or above``, ``$25,600 or higher``, ``3.0% or less`` — the direction
#: word TRAILS. This is the single most common leg shape in Kalshi economics and
#: no grammar in this module saw it before CAL-P134.
_CUMULATIVE_POST_RE = re.compile(
    r"^\s*\$?\s*(?P<val>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>bn|[kmbt])?\b%?\s*"
    r"or\s+(?P<word>above|higher|more|greater|over|below|lower|less|under)\s*$", re.I)

_POST_DOWN = {"below", "lower", "less", "under"}


def parse_cumulative_leg(text: str | None) -> tuple[float, str] | None:
    """An outcome leg that is a cumulative threshold: ``(value, direction)``.

    Accepts the three shapes above plus the bare ``X+`` bracket the module
    already knew, so a caller has one entry point and the older grammar keeps
    its guards. Returns ``None`` for a range leg, a tail leg, a ``Yes``/``No``
    or any prose — every one of which must disqualify its market rather than be
    skipped, which is why this returns ``None`` instead of raising.
    """
    if not text:
        return None
    m = _CUMULATIVE_PRE_RE.match(text)
    if m:
        direction = INC if _DOWN_ONLY_RE.match(m.group("word")) else DEC
        return _magnitude(m.group("val"), m.group("unit")), direction
    m = _CUMULATIVE_POST_RE.match(text)
    if m:
        direction = INC if m.group("word").lower() in _POST_DOWN else DEC
        return _magnitude(m.group("val"), m.group("unit")), direction
    plus = parse_plus_bracket(text)
    if plus is not None:
        _, value, direction = plus
        return value, direction
    return None


def cumulative_outcome_ladder(
    outcomes: Sequence[Mapping[str, object]],
    *,
    name_key: str = "name",
) -> tuple[list[tuple[float, Mapping[str, object]]], str] | None:
    """``([(value, row), ...], direction)`` when the outcome list is ONE ladder.

    The generalisation of :func:`outcome_ladder` past the bare ``X+`` leg, and
    it keeps that function's whole discriminator: at least two legs, EVERY leg a
    cumulative threshold, all legs pointing the same way, no duplicate rung
    value. Rows are returned rather than a value->price map because the truth
    law below needs ``is_winner`` and ``resolution_source`` off the same row and
    must not re-derive which leg it came from.

    A leg with no price is NOT excluded here — pricing is the caller's problem,
    and dropping it at this layer would let a ladder qualify on a subset of its
    own legs, which is how a partition silently changes population (lesson 14).
    """
    if len(outcomes) < 2:
        return None
    out: list[tuple[float, Mapping[str, object]]] = []
    directions = set()
    seen: set[float] = set()
    for row in outcomes:
        name = row.get(name_key)
        parsed = parse_cumulative_leg(name if isinstance(name, str) else None)
        if parsed is None:
            return None
        value, direction = parsed
        rung = round(float(value), 6)
        if rung in seen:
            return None
        seen.add(rung)
        directions.add(direction)
        out.append((rung, row))
    if len(directions) != 1:
        return None
    return sorted(out), directions.pop()


def truth_reversals(
    ordered: Sequence[tuple[float, bool]], direction: str,
) -> list[tuple[float, float]]:
    """Consecutive rungs whose GRADED RESULTS contradict containment. Evidence.

    This is the law the rest of the module does not have, and it is stronger
    than the price law in a way worth stating plainly. A price reversal has a
    defence — the book really was quoted like that, and calibration is exactly
    the business of scoring quotes that were wrong. A *truth* reversal has none.
    If the legs are cumulative thresholds over one quantity, the realized value
    V settles all of them at once::

        is_winner(above X)  ==  (V > X)

    so on a descending family the graded results, read in ascending rung order,
    can only be ``True … True False … False``. A ``False`` below a ``True`` means
    **at least one of those two labels is wrong**, and no fact about the world
    makes both correct. The curve is scoring that row against a label that
    cannot be right.

    ⚠️ THE PRICE LAW ABOVE IS LEAKAGE-FREE AND THIS ONE IS NOT. Everything
    before this section is a function of names and prices only, which is what
    lets a holdout there test stability rather than leakage. This function reads
    ``is_winner``. A rule built on it is therefore NOT in that class and must
    never be described as if it were: it is a truth-ELIGIBILITY finding of the
    same kind as the pass2_loser poison — rows removed because their ground
    truth is provably self-contradictory, not because of how they scored.
    """
    if direction not in (DEC, INC):
        raise ValueError(f"direction must be {DEC!r} or {INC!r}, got {direction!r}")
    out: list[tuple[float, float]] = []
    for (low, low_w), (high, high_w) in zip(ordered, ordered[1:]):
        broken = (not low_w and high_w) if direction == DEC else (low_w and not high_w)
        if broken:
            out.append((low, high))
    return out


def outcome_ladder_report(
    markets: Mapping[object, Sequence[Mapping[str, object]]],
    *,
    name_key: str = "name",
    price_key: str = "price",
    winner_key: str = "is_winner",
    source_key: str = "resolution_source",
    authoritative: frozenset = frozenset(
        {"api_settlement", "clean_resolution", "kalshi_api", "settlement"}),
) -> dict:
    """The OUTCOME site end to end: id partition plus the census behind it.

    ``markets`` maps market id -> its outcome rows. The market id IS the family
    here, so there is no key to collapse and none of the name site's ambiguity
    machinery applies — the only way two ladders can merge is a duplicate rung
    value, which :func:`cumulative_outcome_ladder` already refuses.

    Returns ``truth_broken`` / ``price_broken`` / ``clean`` id sets and a census
    split by resolution authority, because the split is the finding. Measured on
    ``kalshi/economics``: 0.3% of all-authoritative ladders carry a truth
    reversal against 22.2% of ladders containing a pass-2 guess — a 74x rate
    difference established by logic alone, with no model and no price.

    The three id sets are disjoint and ordered by severity: a ladder whose truth
    is broken is never also reported as merely price-broken, because the wrong
    label is the bigger claim and a caller sizing arms by addition must not
    count it twice.
    """
    truth_broken: set = set()
    price_broken: set = set()
    clean: set = set()
    census: dict[str, int] = {k: 0 for k in (
        "markets_scanned", "markets_not_a_ladder", "ladders",
        "ladders_under_two_graded_legs", "ladders_auth", "ladders_guess",
        "truth_pairs_auth", "truth_reversal_pairs_auth", "ladders_truth_broken_auth",
        "truth_pairs_guess", "truth_reversal_pairs_guess", "ladders_truth_broken_guess",
        "price_pairs", "price_reversal_pairs", "ladders_price_broken",
        "legs_truth_broken", "legs_price_broken", "legs_clean")}

    for mid, outcomes in markets.items():
        census["markets_scanned"] += 1
        read = cumulative_outcome_ladder(list(outcomes), name_key=name_key)
        if read is None:
            census["markets_not_a_ladder"] += 1
            continue
        census["ladders"] += 1
        ordered, direction = read
        graded = [(v, r) for v, r in ordered if r.get(source_key)]
        if len(graded) < 2:
            census["ladders_under_two_graded_legs"] += 1
            continue
        band = ("auth" if all(r.get(source_key) in authoritative for _, r in graded)
                else "guess")
        census[f"ladders_{band}"] += 1
        rev = truth_reversals([(v, bool(r.get(winner_key))) for v, r in graded],
                              direction)
        census[f"truth_pairs_{band}"] += len(graded) - 1
        census[f"truth_reversal_pairs_{band}"] += len(rev)
        if rev:
            census[f"ladders_truth_broken_{band}"] += 1
            census["legs_truth_broken"] += len(outcomes)
            truth_broken.add(mid)
            continue
        priced = [(v, float(r[price_key])) for v, r in ordered
                  if r.get(price_key) is not None]
        if len(priced) < 2:
            census["legs_clean"] += len(outcomes)
            clean.add(mid)
            continue
        vio = monotonicity_violations({v: p for v, p in priced}, direction)
        census["price_pairs"] += len(priced) - 1
        census["price_reversal_pairs"] += len(vio)
        if vio:
            census["ladders_price_broken"] += 1
            census["legs_price_broken"] += len(outcomes)
            price_broken.add(mid)
        else:
            census["legs_clean"] += len(outcomes)
            clean.add(mid)

    return {"truth_broken": truth_broken, "price_broken": price_broken,
            "clean": clean, "census": census}
