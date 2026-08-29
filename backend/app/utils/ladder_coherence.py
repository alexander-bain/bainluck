"""The Over/Under ladder as ONE priced object, and the proof that it was not priced.

WHAT THIS DECIDES, and why it is a theorem rather than a heuristic.

A Polymarket total-line market comes as a ladder over one game: ``O/U 0.5``,
``O/U 1.5``, ``O/U 2.5`` ... Each rung is stored as its own two-leg market, and
the published curve grades each rung as an independent forecast. But the rungs
are not independent, and one relation between them holds with no modelling
assumption at all::

    P(total > L)  >  P(total > L + 1)

strictly, because the difference between the two events is "the total lands in
between", and for half-integer lines over a discrete total that difference is a
real outcome with non-zero probability. A ladder whose Over price fails to fall
between two rungs one goal apart has not been priced by anyone who was looking
at both rungs. That is not a taste judgment about the price; it is an
arithmetic contradiction inside a single object.

WHY THE LADDER IS THE UNIT AND NOT THE RUNG. Ruling 111 settled this shape on a
different surface, in the same words: *"The defect's unit was the ladder; every
rule on the rail had the row as its subject. No amount of tuning a per-row
predicate reaches that."* It is measured again here. On ``soccer/quantity``
(CAL-P106, 2,854 truth-eligible pairs, whole population, 0 unswept ranges) the
same violations, condemned two ways:

===============================  ==========  =========
treatment                        legs KEPT   ECE (pp)
===============================  ==========  =========
baseline, nothing removed             5,708       8.53
rung as the unit (rule B)             3,538       5.95
**ladder as the unit (rule A)**       2,322     **3.76**
===============================  ==========  =========

Condemning only the rungs caught in a violating pair leaves 5.95; condemning the
ladder they belong to leaves 3.76. A violation is evidence about the pricing
process that produced the whole family, not about the two rungs where the
arithmetic happened to become visible.

⚠️ EVERY NUMBER IN THIS DOCSTRING IS ON THE KEY THIS MODULE SHIPS —
``ladder_family_key`` over ``futures_markets.name`` — and is re-runnable:
``artifacts/cal-p106/rule_a_vs_b_soccer_q.json`` (A and B on one population) and
``artifacts/cal-p106/violation_detail_soccer_q.json`` (the pair counts). CAL-P107
found the first draft of this table had been computed on an *exploratory* SQL
``game_key`` from a scratch probe, which groups 714 families where this key
groups 596: it read 3.42/2,372 for rule A and 5.71/3,652 for rule B. The
conclusion survived the correction and the figures did not. A docstring number
whose producing code is not named is the CAL-P105 defect in miniature.

THE POPULATION IT SEPARATES, so nobody has to take the ECE on faith. Over-leg
gap (price − win rate) by rung, on the two classes this predicate splits::

    line   0.5    1.5    2.5    3.5    4.5    5.5
    KEEP  -1.5   -2.5   -7.6   -3.2   +2.6   +3.3
    DROP -31.9  -13.5   -1.0  +12.9  +21.7  +33.0

The DROP class is a price that barely moves while the outcome rate collapses —
the flat, templated ladder. Three different Bolivian league games in the sample
carry the byte-identical ladder ``0.68 / 0.605 / 0.52 / 0.405 / 0.28 / 0.28``,
with ``calibration_probability`` equal to ``opening_probability`` on every rung.

WHAT THE RULE DOES NOT REPAIR, stated here because the table above is the part
people quote. The KEEP class is clean only where the rungs are: at lines 6.5 and
above its own gap runs +9.2 to +31.5 pp on 10–19 markets a rung. The rule
separates a templated ladder from a priced one; it does not make the thin tail of
a priced one accurate, and 3.76 pp is a cell still over Alex's bar.

WHY THE EXISTING PLACEHOLDER RULE CANNOT SEE THIS, measured and not assumed.
``precompute_calibration.POLY_PLACEHOLDER_EXCLUDE`` removes a Polymarket outcome
that is both inside ``[0.45, 0.55]`` and has no snapshot with ``yes_bid > 0 OR
last_price > 0``. These rungs sit at ``0.485``/``0.495`` — inside the band — and
they carry a resting quote, so the evidence half passes. Measured on this cell:
**5,748 of 5,749 legs have bid-or-trade evidence on their pair**, so an
evidence-only rule removes one leg. A resting market-maker quote is a book; it
is not a forecast, and #151's census — which found the discriminator on the
never-quoted exact-0.50 class — could not have distinguished them.

NO TOLERANCE KNOB, and that is a measurement rather than an omission. The worry
is that two deep rungs both pinned at a storage floor would read as a violation.
Counted over all **631** violating adjacent pairs in the cell: **0 have both
prices below 0.02**, and **0** ladders have only floor-level violations. Ruling
083 — a guard that cannot tell two cases apart is given evidence, not a wider
band.

WHAT THIS MODULE DOES NOT DO. It never reads an outcome. Every function here is a
function of names and prices, so the predicate cannot be fitted to ``is_winner``
and a holdout tests stability, not leakage. It writes nothing (gotcha #21).
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

#: The rung token. Anchored on the literal ``O/U`` Polymarket uses in the market
#: name; a line is a bare number or a half-integer.
OU_LINE_RE = re.compile(r"O/U\s+(\d+(?:\.\d+)?)")

#: Two rungs are ADJACENT when their lines differ by exactly one unit. The step
#: is one because that is the granularity a total moves in; a wider window would
#: compare rungs with a real outcome between them and a narrower one has no
#: rungs to compare.
LADDER_ADJACENT_STEP = 1.0

#: Float slack for the adjacency comparison only. Lines are parsed from text and
#: are exact half-integers, so this guards the arithmetic and never the verdict.
_LINE_EPS = 1e-6

LADDER_COHERENCE_RULE_TEXT = (
    "A Polymarket Over/Under ladder over one game is a single priced object: its "
    "Over price must fall strictly between rungs one unit apart, because the "
    "difference between 'total > L' and 'total > L+1' is a real outcome. A ladder "
    "carrying an adjacent-rung violation was not priced against itself, so EVERY "
    "rung of that ladder is excluded from the published curve — the ladder is the "
    "unit, not the rung (ruling 111). A family of one rung is never condemned: "
    "the relation is untestable there, and an untestable row is left in (ruling "
    "105). Read-side only; never mutates is_winner or calibration_probability."
)


def parse_ou_line(name: str | None) -> float | None:
    """The rung's line, or ``None`` when the name carries no ``O/U`` token."""
    if not name:
        return None
    match = OU_LINE_RE.search(name)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:  # pragma: no cover - the regex cannot produce this
        return None


def ladder_family_key(name: str | None) -> str | None:
    """The ladder a rung belongs to: its market name with the rung removed.

    Deleting the ``O/U <line>`` token rather than truncating at it is the whole
    point. ``"IR Iran vs. New Zealand: 1st Half O/U 1.5"`` and
    ``"IR Iran vs. New Zealand: O/U 1.5"`` are DIFFERENT ladders about the same
    fixture — one prices a half, one prices the match — and a key that cut the
    string at ``O/U`` would keep them apart only by accident while a key that
    cut at ``:`` would merge them. Whatever qualifier a name carries stays in
    the key, so two rungs are compared only when everything except the line is
    identical.

    Returns ``None`` for a name with no rung, which is how a caller tells "not a
    ladder member" from "a ladder of one".
    """
    if not name:
        return None
    match = OU_LINE_RE.search(name)
    if not match:
        return None
    stripped = name[: match.start()] + name[match.end():]
    return " ".join(stripped.split()).strip(" :-").casefold()


def adjacent_violations(
    rungs: Mapping[float, float],
) -> list[tuple[float, float, float, float]]:
    """Every adjacent pair whose Over price fails to fall. Evidence, not a bool.

    ``rungs`` maps line -> Over price. Returns ``(low_line, low_price,
    high_line, high_price)`` for each pair one unit apart where
    ``high_price >= low_price``. Equality counts: two rungs one goal apart
    cannot carry the same probability, so an exactly-equal pair is the flat
    templated ladder, which is the largest single shape (**250 of 631** in the
    cell that motivated this).

    A list rather than a count, because a cert has to be able to name the pair
    it is arguing about.
    """
    lines = sorted(line for line, price in rungs.items() if price is not None)
    out: list[tuple[float, float, float, float]] = []
    for low in lines:
        for high in lines:
            if abs((high - low) - LADDER_ADJACENT_STEP) > _LINE_EPS:
                continue
            low_p, high_p = rungs[low], rungs[high]
            if high_p >= low_p:
                out.append((low, float(low_p), high, float(high_p)))
    return out


def ladder_is_incoherent(rungs: Mapping[float, float]) -> bool:
    """True when this ladder carries at least one adjacent-rung violation.

    A ladder of one rung is never incoherent — there is nothing to compare it
    with, and ruling 105's clause is explicit that a family of one is never
    condemned on a structural argument. Stated as its own early return rather
    than left to fall out of the loop, because "no pairs, so no violations" and
    "deliberately exempt" are the same answer for opposite reasons and a reader
    is entitled to see which one is meant (gotcha #53).
    """
    if len(rungs) < 2:
        return False
    return bool(adjacent_violations(rungs))


def read_ladders(
    rows: Iterable[Mapping[str, object]],
    *,
    name_key: str = "name",
    price_key: str = "over_price",
) -> dict[str, dict]:
    """Group rung rows into ladders, and record where the grouping is UNSAFE.

    Returns ``key -> {"rungs": {line: price}, "duplicate_lines": {line: count},
    "rows": n}``. Each row needs a market name and the rung's OVER price; a row
    with no rung token or no price takes no part, because a row that cannot be
    placed in a ladder cannot say anything about one.

    ``duplicate_lines`` is the load-bearing output and it exists because of a
    measured failure. Run over ``esports/quantity`` (CAL-P106), this key
    collapsed **231 markets into ONE family**: those names do not carry the
    fixture, so every rung of every match landed on the same key and ten
    arbitrary rows would have decided the verdict for all 231. Two rows on the
    same (family, line) is proof that the key is not identifying a single
    ladder — never that the ladder is bad — so it is recorded rather than
    resolved by picking a winner.
    """
    ladders: dict[str, dict] = {}
    for row in rows:
        name = row.get(name_key)
        key = ladder_family_key(name if isinstance(name, str) else None)
        line = parse_ou_line(name if isinstance(name, str) else None)
        price = row.get(price_key)
        if key is None or line is None or price is None:
            continue
        slot = ladders.setdefault(
            key, {"rungs": {}, "duplicate_lines": {}, "rows": 0}
        )
        slot["rows"] += 1
        rung = round(float(line), 4)
        if rung in slot["rungs"]:
            slot["duplicate_lines"][rung] = slot["duplicate_lines"].get(rung, 1) + 1
            continue
        slot["rungs"][rung] = float(price)
    return ladders


def ambiguous_families(ladders: Mapping[str, Mapping]) -> set[str]:
    """Families whose key demonstrably groups more than one ladder."""
    return {key for key, v in ladders.items() if v["duplicate_lines"]}


def incoherent_families(
    rows: Iterable[Mapping[str, object]],
    *,
    name_key: str = "name",
    price_key: str = "over_price",
) -> set[str]:
    """The set of ladder keys to exclude, given one row per rung.

    A family is condemned only when the grouping is UNAMBIGUOUS. This rule
    deletes rows from the published curve, so where its own premise — "these
    rungs are one ladder" — is disproven by a duplicate line, it fails toward
    KEEPING them. Failing the other way turned the esports key collapse into a
    100% condemnation of a cell the rule has no business touching, which is how
    the guard was found.
    """
    ladders = read_ladders(rows, name_key=name_key, price_key=price_key)
    ambiguous = ambiguous_families(ladders)
    return {
        key for key, v in ladders.items()
        if key not in ambiguous and ladder_is_incoherent(v["rungs"])
    }


# ---------------------------------------------------------------------------
# The SQL rendering of the two text functions above.
#
# NOT a second definition — a second SITE for the same one, and the pair is the
# hazard CAL-P097 named: "the fold and the shipping builder must be UNABLE to
# disagree". Python cannot prove agreement with Postgres regex in a unit test
# (there is no local Postgres in this sandbox), so agreement is a CERT
# obligation and is written down as one: a whole-population differential between
# the Python predicate and this SQL, reported as a count of disagreeing markets,
# with zero as the only passing value. Until that runs, treat this as UNPROVEN
# and drive every measurement from the Python side, which is what CAL-P106 did.
#
# ``{alias}`` is the ``futures_markets`` alias at the call site.
OU_LINE_SQL = "substring({alias}.name from 'O/U ([0-9]+(\\.[0-9]+)?)')"

LADDER_FAMILY_SQL = (
    "lower(btrim(regexp_replace("
    "regexp_replace({alias}.name, 'O/U[[:space:]]+[0-9]+(\\.[0-9]+)?', '', 'g'),"
    " '[[:space:]]+', ' ', 'g'), ' :-'))"
)


def cell_ece_pp(
    prices: Sequence[float], winners: Sequence[int]
) -> float | None:
    """The census's n-weighted ECE in pp, for a caller holding raw legs.

    Binning and arithmetic are both DELEGATED to
    :mod:`app.utils.calibration_ece` — ``bin_index`` and ``calibration_error``,
    at the census's floor of ``min_bin_n = 0``. This module must not become a
    fifth implementation of an ECE: CAL-P105 found four already in this tree and
    had to prove them equal after the fact, and the only reason that ended well
    is that they happened to agree.
    """
    from app.utils.calibration_ece import bin_index, calibration_error

    if len(prices) != len(winners):
        raise ValueError("prices and winners must be the same length")
    buckets: dict[int, dict[str, float]] = {}
    for price, winner in zip(prices, winners):
        slot = buckets.setdefault(
            bin_index(float(price)), {"n": 0, "winners": 0, "sum_prob": 0.0}
        )
        slot["n"] += 1
        slot["winners"] += int(winner)
        slot["sum_prob"] += float(price)
    return calibration_error(buckets.values(), min_bin_n=0)
