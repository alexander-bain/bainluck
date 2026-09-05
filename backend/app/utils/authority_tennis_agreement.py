"""How a tennis agreement row joins its two sides, and over what span. #2867 / D50.

**SHIP: tennis joins the four sports whose StatPal agreement is measured every
day, so the question "would StatPal have shown this match when ESPN did not?"
has a number instead of an opinion — and the number is split by draw, so it is
not a phantom.** (Pillar: MATCHING.)

`authority_agreement` owns what a row SAYS. This module owns the one part of it
that is sport-shaped for tennis: which fixture is which row, and how far either
side of now our own inventory is read. Everything else — the identity block, the
horizon splits, the governing verdict, the receipts — is shared, because two
sports may disagree about what "the same match" means and must not disagree
about what a row means.

WHY TENNIS CANNOT USE THE DEFAULT JOIN
══════════════════════════════════════
The default is a KEY join: normalise both sides' names, group by the pair, and
equal keys are the same game. That works wherever the identity relation is an
equality, and tennis's is not.

`authority_tennis_names.keys_agree` reads a missing given name as **UNKNOWN**,
never as a difference, because 32.5% of our field has no given name at all. So
`Garcia` and `Garcia Garcia` are each reachable from `G. Garcia` and are not
reachable from each other. That relation is reflexive and symmetric and **not
transitive**, and a non-transitive relation has no keys: any grouping either
fuses two players or hides a match, and whichever it does it does silently.

This is the same failure this lane has now paid for twice — a census grouped by
the join key is blind exactly where the matcher is tolerant (CERT-1890) — and
the fix is the same: join on the relation the matcher actually uses. So
`pair_tennis_sides` calls `resolve_tennis_name`, the one place that judgment
lives, rather than re-implementing it as a string. A test that re-implements the
identity cannot fail (CERT-1900); neither can a join that does.

AMBIGUOUS IS A REFUSAL WE PUBLISH, NOT A ROW WE DROP
═════════════════════════════════════════════════════
`resolve_tennis_name` answers AMBIGUOUS when two of our rows could both be one
StatPal match and it will not choose. That is neither agreement nor
disagreement, and it has exactly one honest home: `excluded`, under its own
name, with both candidates in the receipt.

The tempting alternatives are both wrong in the flattering direction. Counting
it as `statpal_only` publishes *"StatPal has a match we do not"* when we have
two. Picking the nearest kickoff pairs one and reports the other as `ours_only`,
which prints the same duplicate as a disagreement about a match. It is reported
and left alone: two of our rows for one match is a duplicate, it is D39/#2693's,
and this module may not fix it.

ORIENTATION IS NOT A DIFFERENCE HERE
════════════════════════════════════
The default join keys on `(away, home)` in that order, because a home-and-home
pair of division games are two different fixtures. Tennis has no home side —
which player our column stored first is an artifact of ingestion — so a fixture
matches a row under either orientation. Keeping orientation would report every
match whose two providers listed the players in opposite order as two misses.

THE SPAN, AND WHY THE TEAM-SPORT CEILING DOES NOT APPLY
════════════════════════════════════════════════════════
`MEASUREMENT_HORIZON` is 40 days and is bounded from both ends: wider than any
provider's rolling window, and narrower than half `TIGHTEST_OFFSEASON_GAP` so
that a span anchored in an offseason cannot reach two different seasons.

**Tennis has no offseason, and this was measured rather than assumed.** Over our
whole tennis inventory — 30,450 rows, 216 distinct play-days from 2026-01-28 to
2026-09-07, read on production 2026-09-05 — the longest gap between two
consecutive play-days is **5.0 days**. The tour is continuous.

Applying the team-sport ceiling literally would therefore cap tennis's horizon at
2.5 days, which is NARROWER than StatPal's own `d-7…d+7` reach — and a horizon
inside the provider's window re-creates precisely the defect the horizon exists
to prevent, where a row of ours past the edge of a rolling schedule is subtracted
by SQL before it can be counted as missing (CERT-962). The bound would not merely
fail to apply; obeying it would be the bug.

So the ceiling is replaced, not inherited, and the replacement is stated:

  * **Wider than the provider's reach**, which is the surviving half of the
    original bound. StatPal serves tennis over `d-7…d+7`, so 14 > 7 with a
    7-day margin.
  * **The thing the offseason bound was protecting against does not exist here.**
    It kept one window from spanning two seasons; a continuous tour has none to
    span. What a 14-day window does span is several tournaments, and that is
    already the accepted design — the linker records the tournament in its
    receipt and deliberately never filters on it, because our own `sports.key` is
    not reliable enough to exclude a candidate on (a live US Open singles match
    sat under `tennis_other` the day it was written).
  * **The residual hazard is a pair meeting twice inside the window, and
    narrowing does not address it.** Of 3,707 repeat meetings in 120 days, 1,860
    fall within 7 days and 2,099 within 14 — the bulk are inside ANY usable
    window, because they are mostly duplicate rows rather than real rematches
    (1,170 of the close pairs sit under two different `sports.key`s). Duplicates
    are a matching symptom, filed under #2693, and a horizon is the wrong tool
    for them. `_pair_with_tie_detection` settles the distinguishable ones —
    largest pairing first, nearest start to choose among pairings of equal
    size — and refuses only the ties.

14 days holds 2,004 of our tennis rows, 252 of them doubles, across 8 sport keys
(production 2026-09-05) — a denominator a ten-minute task can read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any, Callable, Optional, Sequence

from app.utils.authority_agreement import (
    Join,
    Side,
    build_agreement_row,
    measurement_bounds,
)
from app.utils.authority_tennis_names import (
    AMBIGUOUS,
    REVIEWED_ALIASES,
    is_doubles_name,
    looks_like_a_player,
    resolve_tennis_name,
    tennis_names_agree,
)

#: StatPal's own reach for tennis: `daily/d-7 … d7`, with no `d0` (that token
#: answers HTTP 500, not 404). The floor under `TENNIS_MEASUREMENT_HORIZON`.
STATPAL_TENNIS_REACH = timedelta(days=7)

#: How far either side of now our tennis inventory is measured. See the module
#: docstring for why this is not `MEASUREMENT_HORIZON` and why the offseason
#: ceiling that bounds that constant does not apply to a continuous tour.
TENNIS_MEASUREMENT_HORIZON = timedelta(days=14)

#: The longest gap between two consecutive tennis play-days in our own table:
#: 5.0 days over 216 play-days, 2026-01-28 to 2026-09-07, measured on production
#: 2026-09-05. Pinned as a constant rather than left in prose because it is the
#: evidence for the paragraph above, and
#: `test_the_team_sport_offseason_ceiling_cannot_be_applied_to_tennis` asserts
#: the conclusion follows from it rather than from a remembered sentence.
TENNIS_TIGHTEST_GAP = timedelta(days=5)

#: The two draws, and the `SHADOW_STAMPERS` key each one banks its row under.
SINGLES = "tennis_singles"
DOUBLES = "tennis_doubles"

#: `Join.refusals` key for a StatPal fixture whose player our register holds
#: under two identities. Named in the row, never folded into a bucket that means
#: something else — see the module docstring.
AMBIGUOUS_REFUSAL = "ambiguous_identity"

#: `Join.refusals` key for OUR rows an ambiguous fixture could not be told apart
#: between, left unpaired at the end of the pass. Separate from the key above
#: because one ambiguous fixture and the two rows it implicates are different
#: quantities and `excluded` is read as a census (CERT-1904).
AMBIGUOUS_CANDIDATE_ROWS = "ambiguous_identity_candidate_rows"

#: `Join.refusals` keys for a candidate component this module declined to solve
#: because it was larger than `MAX_ASSIGNMENTS_PER_COMPONENT`.
#:
#: Kept apart from the two keys above, on both sides, because *the data does not
#: choose* and *we did not finish asking* are different findings that happen to
#: leave the denominator the same way. Folding the second into the first would
#: publish our own bound as a property of the field, and would hide the one
#: signal that says the bound needs raising. Zero is the expected reading.
UNSOLVED_COMPONENT_FIXTURES = "unsolved_component"
UNSOLVED_COMPONENT_ROWS = "unsolved_component_candidate_rows"

#: Every refusal name this strategy can emit, declared to `Join` so the row seeds
#: all four at `0` whatever today's data did (#3275).
#:
#: The `if` guards in `pair_tennis_sides` stay: `Join.refusals` remains a record
#: of what THIS pass refused, and this tuple is what the census is keyed by.
#: Collapsing the two — always writing empty lists into `refusals` — would make
#: the seeding vacuous, so the mechanism every future strategy relies on would
#: never run in the one place that uses it.
#: `Join.allowances` key for the re-ordering classes this strategy folds on
#: REVIEW rather than on measurement (`authority_tennis_names.REVIEWED_ALIASES`).
#:
#: Deliberately not a refusal name. Every other name this module publishes is a
#: reason a row left the denominator; this one is a reason two names were allowed
#: to MEET, and its effect on the governing number therefore points the other way
#: — upward, generously, and with nothing in `excluded` to show for it. Zero is
#: NOT the expected reading here: two entries are expected, and both are expected
#: to say `ratified_by_alex: false` until he reads them (#3287).
ORDER_ALIAS_ALLOWANCE = "order_aliases_reviewed"

TENNIS_REFUSAL_NAMES = (
    AMBIGUOUS_REFUSAL,
    AMBIGUOUS_CANDIDATE_ROWS,
    UNSOLVED_COMPONENT_FIXTURES,
    UNSOLVED_COMPONENT_ROWS,
)

#: What this strategy's denominator actually is, published on the row.
#:
#: The shared default describes an ordered normalised-pair key with kickoff as an
#: in-key tiebreak. **Every clause of that is false for tennis** — the join is a
#: resolver over a non-transitive relation, orientation is not a difference, and
#: there are no keys to be inside of. A row that describes the wrong join is a
#: measurement with the wrong source attached to it (CERT-1895's lesson, and
#: CERT-1904 caught this file failing it).
#:
#: The tiebreak clause is worded as it is because of CERT-1917: "start time
#: chooses which pairing is made" was true of one edge and false of the graph,
#: and a walk that took the nearest edge first destroyed the only full pairing
#: two Garcias and an untitled row admitted. Size is settled before the clock.
TENNIS_DENOMINATOR_IS = (
    "distinct matches under the union of both sides, joined by "
    "`authority_tennis_names.resolve_tennis_name` on BOTH players in either "
    "orientation — not by a normalised pair key, because the identity relation "
    "reads a missing given name as UNKNOWN and so is not transitive. Candidates "
    "are resolved as ONE assignment over the whole candidate graph, largest "
    "pairing first; start time then chooses WHICH of two equally large pairings "
    "is made, and never whether one is made. Only joins that hold across every "
    "such pairing are published. Singles and doubles are separate denominators; "
    "a fixture whose player our register holds under two identities, any of our "
    "rows it could not be told apart between, and any component too large to "
    "resolve exactly, leave the denominator under `excluded` rather than "
    "counting as a disagreement."
)


def is_doubles_side(side: Side) -> bool:
    """Is this fixture or row a doubles draw?

    Either name carrying the pair marker is enough. A side with one doubles name
    and one singles name is malformed rather than mixed, and it lands in the
    doubles population where `doubles_key` refuses it as unusable and it is
    counted — which is the loud failure, against a silent singles match.
    """
    return is_doubles_name(side.home) or is_doubles_name(side.away)


def split_by_draw(sides: Sequence[Side]) -> tuple[list[Side], list[Side]]:
    """`(singles, doubles)`. The split that keeps two denominators apart."""
    doubles = [s for s in sides if is_doubles_side(s)]
    singles = [s for s in sides if not is_doubles_side(s)]
    return singles, doubles


def _readable(side: Side) -> bool:
    """Can both of this side's names be read as players at all?

    Not "do they match anything" — that is the join's question. This is the
    prior one, and it is why `_NOT_A_PLAYER` exists: futures-market titles have
    leaked into the tennis team-name column, and `Black Desert Resort (Men's
    Doubles) Winner` is not a player who is missing from StatPal.
    """
    return looks_like_a_player(side.home) and looks_like_a_player(side.away)


def _sides_agree(fixture: Side, row: Side) -> bool:
    """Is this StatPal fixture this row of ours — under either orientation?

    Both players must agree. One agreeing player is not half a match: on a
    tournament day the same player appears in the singles draw and, under a
    different key, the doubles draw, and a one-name rule would pair them.
    """
    straight = tennis_names_agree(row.home, fixture.home) and tennis_names_agree(
        row.away, fixture.away
    )
    crossed = tennis_names_agree(row.home, fixture.away) and tennis_names_agree(
        row.away, fixture.home
    )
    return straight or crossed


def _ambiguity(
    fixture: Side, rows: Sequence[Side]
) -> Optional[tuple[dict[str, Any], list[Side]]]:
    """A receipt and the OUR-SIDE rows it implicates, if this fixture is ambiguous.

    Asked with `resolve_tennis_name` against the names actually in the window,
    not against the global register: the field has 572 contested keys and almost
    none of them are reachable on one tournament-day. Resolving globally would
    refuse matches nobody could confuse.

    **Ambiguity is a property of the candidate COMPONENT**, and each earlier
    version located it one level too low. All three are on the record because the
    progression is the finding:

      * CERT-1904 — excluding the FIXTURE and leaving its candidate rows in the
        population. `G. Garcia` published `ambiguous_identity=1` AND
        `ours_only=2`: a duplicate of ours printed as two matches StatPal is
        missing, which is what this module exists to refuse.
      * CERT-1909 — over-correcting, by asking `resolve_tennis_name` about ONE
        player against every name in the window and holding out every row that
        answered. With rows `Garcia–Jannik Sinner` and `Garcia Garcia–Daniil
        Medvedev`, the Medvedev match was held out of a Sinner fixture's
        arithmetic. **It cannot be that fixture** — the opponent settles it — so a
        real match left the denominator and the row read 0/0/0.
      * CERT-1910 — then refusing any fixture with two complete-match candidates.
        Two Alcaraz–Sinner meetings a week apart give each fixture two candidates
        and the row published `0/0/0/0` with two exclusions, **bypassing the
        nearest-kickoff pairing this module says handles repeat meetings.** Two
        fixtures and two rows are not an ambiguity; they are a one-to-one
        assignment with a tiebreak already specified for it.

    So the question is asked of the **component**, not of a name, a match or a
    fixture: take the connected component of the agreement graph and ask whether
    it resolves ONE-TO-ONE. One fixture and one row resolves. Two fixtures and two
    rows resolves, and the kickoff says which is which. One fixture and two rows
    does not — there is a spare row and nothing to choose on — and that is the
    only shape that is genuinely a refusal.

    See :func:`_pair_with_tie_detection`, which owns that judgment. This function
    is now only the RECEIPT: it names which player the register holds twice, via
    `resolve_tennis_name`, so a refusal says why rather than merely that.
    **Naming the reason and choosing the outcome are different jobs, and letting
    the first do the second is the shape of all three blocks on this branch.**
    """
    candidates = [r for r in rows if _sides_agree(fixture, r)]
    if not candidates:
        return None

    # Which player is the contested one, for the receipt only. Resolved against
    # the CANDIDATES' names rather than the whole window: the question is what
    # makes these two matches indistinguishable, not what is contested elsewhere.
    pool = [
        name
        for r in candidates
        for name in (r.home, r.away)
        if isinstance(name, str)
    ]
    contested_name = None
    contested_with: tuple[str, ...] = ()
    for theirs in (fixture.home, fixture.away):
        resolution = resolve_tennis_name(theirs, pool)
        if resolution.outcome == AMBIGUOUS:
            contested_name = theirs
            contested_with = resolution.candidates
            break

    receipt = {
        "statpal_id": fixture.ref,
        "players": [fixture.home, fixture.away],
        "statpal_start": fixture.start.isoformat() if fixture.start else None,
        "label": fixture.label,
        "unresolved_name": contested_name,
        "our_candidates": list(contested_with),
        "our_event_ids": [r.ref for r in candidates],
        "why": (
            f"{len(candidates)} of our rows agree with this fixture on BOTH "
            "players, so we cannot say which one it is. Neither agreement nor "
            "disagreement, and not this module's to resolve (D39, #2693)"
        ),
    }
    return receipt, candidates


#: Cost of one candidate edge whose two sides cannot both be timed. A timed edge
#: always beats an untimed one, so a fixture with any timed candidate is never
#: decided by an untimed one — and a missing start is not weaker evidence than a
#: tied one, it is no evidence.
_UNTIMED = (1, timedelta(0))


def _edge_key(fixture: Side, row: Side) -> tuple[int, timedelta]:
    """`(untimed?, how far apart)` — the cost of joining this fixture to this row."""
    if fixture.start is None or row.start is None:
        return _UNTIMED
    return (0, abs(fixture.start - row.start))


#: How many candidate assignments one component may contain before this module
#: stops solving it and refuses it whole.
#:
#: The published edges are the ones EVERY optimal pairing agrees on, which is a
#: question about all of them, and the search is exponential in the number of
#: fixtures a component holds. Past this bound the component leaves the
#: denominator as a tie. It is a bound on the SET of candidates rather than on
#: elapsed work, so it is the same bound whatever order the rows arrived in — a
#: budget spent by a walk would reintroduce exactly the CERT-1915 defect.
#:
#: 20,000 admits far more than a tennis day produces: the shape it has to hold is
#: a handful of repeat meetings of one pair against a handful of our rows, and
#: `test_the_bound_does_not_refuse_an_ordinary_days_component` pins the constant
#: to that shape by relation rather than to this number.
MAX_ASSIGNMENTS_PER_COMPONENT = 20_000


def _components(
    n_f: int,
    n_r: int,
    by_f: dict[int, list[int]],
    by_r: dict[int, list[int]],
) -> list[tuple[list[int], list[int]]]:
    """The candidate graph split into the parts that cannot affect each other.

    Solved separately because an assignment is only ever contested inside its own
    component, and because the search below is exponential in a component's size:
    a tournament day is many tiny components, not one large one.
    """
    seen_f: set[int] = set()
    seen_r: set[int] = set()
    found: list[tuple[list[int], list[int]]] = []
    for start in range(n_f):
        if start in seen_f:
            continue
        seen_f.add(start)
        comp_f, comp_r, stack = [], [], [(True, start)]
        while stack:
            is_fixture, idx = stack.pop()
            if is_fixture:
                comp_f.append(idx)
                for ri in by_f[idx]:
                    if ri not in seen_r:
                        seen_r.add(ri)
                        stack.append((False, ri))
            else:
                comp_r.append(idx)
                for fi in by_r[idx]:
                    if fi not in seen_f:
                        seen_f.add(fi)
                        stack.append((True, fi))
        found.append((sorted(comp_f), sorted(comp_r)))
    # Rows no fixture reaches are their own components, and they are the ordinary
    # `ours_only` miss. Reached from the row side because the walk above starts
    # at fixtures and would never visit them.
    found.extend(([], [ri]) for ri in range(n_r) if ri not in seen_r)
    return found


def _outcomes_of_every_optimum(
    comp_f: Sequence[int],
    comp_r: Sequence[int],
    by_f: dict[int, list[int]],
    edges: dict[tuple[int, int], tuple[int, timedelta]],
) -> Optional[tuple[dict[int, set[Optional[int]]], dict[int, set[Optional[int]]]]]:
    """What each side of this component does across ALL optimal pairings.

    Returns `(per fixture, per row)` sets of partners, where `None` means "left
    unmatched in that pairing" — or `None` if the component is past
    `MAX_ASSIGNMENTS_PER_COMPONENT` and was not searched.

    A pairing is scored `(-size, untimed edges, total gap)` and the best one
    wins, so **cardinality is settled before the clock is consulted**. That
    ordering is CERT-1917 and it is the whole point: a locally exact edge may not
    be bought at the price of a match. On the graph

        fA → {Caroline Garcia, Garcia}      fD → {Garcia}

    the exact-time edge `fA→Garcia` leaves `fD` and `Caroline Garcia` with
    nothing, and the row publishes `1/1/1` over a denominator of 3 — two
    manufactured misses in opposite directions, out of two matches that both
    exist. There is exactly one pairing of maximum size and it is the answer.

    The clock keeps its declared job: it chooses among pairings of EQUAL size,
    which is "which of two admissible pairings is made" and never "whether one is
    made". A timed edge outranks an untimed one for the same reason.

    Every optimum is enumerated rather than one being returned, because what may
    be published is what all of them agree on. A node whose partner varies across
    optima — or which is matched in one and unmatched in another — has no answer
    in the data, and picking one would be the arrival-order defect of CERT-1915
    reached by a different route.
    """
    # Read off the adjacency rather than re-scanning the component: a component
    # holding most of the day would cost |fixtures| x |rows| a second time.
    reach = {fi: sorted(by_f[fi]) for fi in comp_f}
    assignments = 1
    for fi in comp_f:
        assignments *= len(reach[fi]) + 1
        if assignments > MAX_ASSIGNMENTS_PER_COMPONENT:
            return None

    order = list(comp_f)
    chosen: list[Optional[int]] = [None] * len(order)
    taken: set[int] = set()
    f_out: dict[int, set[Optional[int]]] = {fi: set() for fi in comp_f}
    r_out: dict[int, set[Optional[int]]] = {ri: set() for ri in comp_r}
    best: Optional[tuple[int, int, timedelta]] = None

    def _walk(i: int, size: int, untimed: int, gap: timedelta) -> None:
        nonlocal best
        if i == len(order):
            score = (-size, untimed, gap)
            if best is not None and score > best:
                return
            if best is None or score < best:
                best = score
                for partners in f_out.values():
                    partners.clear()
                for partners in r_out.values():
                    partners.clear()
            matched_by = {ri: order[j] for j, ri in enumerate(chosen) if ri is not None}
            for j, ri in enumerate(chosen):
                f_out[order[j]].add(ri)
            for ri in comp_r:
                r_out[ri].add(matched_by.get(ri))
            return
        _walk(i + 1, size, untimed, gap)  # this fixture goes unmatched
        for ri in reach[order[i]]:
            if ri in taken:
                continue
            edge_untimed, edge_gap = edges[(order[i], ri)]
            taken.add(ri)
            chosen[i] = ri
            _walk(i + 1, size + 1, untimed + edge_untimed, gap + edge_gap)
            chosen[i] = None
            taken.discard(ri)

    _walk(0, 0, 0, timedelta(0))
    return f_out, r_out


@dataclass(frozen=True)
class _Resolution:
    """What the join decided about one draw, before any of it is worded.

    A record rather than a tuple because the two refusal reasons are different
    quantities and must not arrive at the caller interchangeable: `tied_*` is
    *the data does not choose*, `unsolved_*` is *we did not finish asking*. They
    leave the denominator the same way and they are not the same finding, and
    folding one into the other is the mistake five blocks on this branch were
    about.
    """

    paired: list[tuple[Side, Side]]
    tied_fixtures: list[Side]
    tied_rows: list[Side]
    unsolved_fixtures: list[Side]
    unsolved_rows: list[Side]
    spare_fixtures: list[Side]
    spare_rows: list[Side]


def _pair_with_tie_detection(fixtures: Sequence[Side], rows: Sequence[Side]) -> _Resolution:
    """Publish the joins every optimal pairing agrees on; refuse the rest.

    Two things this must be, and each of them cost a block:

      * **CERT-1915 — the answer may not depend on arrival order.** The version
        before last discovered equal-distance rivals while it was already
        consuming availability, so a chain published one pair under one ordering
        and none under a permutation. SQL arrival order is not identity evidence.
      * **CERT-1917 — nor may it depend on the order the graph is walked in at
        all.** Its replacement took every edge the graph locally FORCED, and a
        locally forced edge can destroy the graph's only full pairing. Reading
        the snapshot immutably made the wrong answer stable rather than making it
        right; all four permutations of the specimen agreed on it.

    So the answer is a property of the graph and is computed as one: solve each
    component for its optimal pairings (`_outcomes_of_every_optimum` — largest
    first, nearest kickoff second), and publish an edge only where EVERY optimum
    contains it. A side left unmatched by every optimum was never contested and
    is an ordinary `statpal_only` / `ours_only` miss. Anything else — a partner
    that varies, or a side matched in one optimum and spare in another — is a
    tie, and a tie is refused and reported rather than guessed.
    """
    edges: dict[tuple[int, int], tuple[int, timedelta]] = {}
    by_f: dict[int, list[int]] = {fi: [] for fi in range(len(fixtures))}
    by_r: dict[int, list[int]] = {ri: [] for ri in range(len(rows))}
    for fi, fixture in enumerate(fixtures):
        for ri, row in enumerate(rows):
            if _sides_agree(fixture, row):
                edges[(fi, ri)] = _edge_key(fixture, row)
                by_f[fi].append(ri)
                by_r[ri].append(fi)

    paired_idx: list[tuple[int, int]] = []
    tied_f: list[int] = []
    tied_r: list[int] = []
    unsolved_f: list[int] = []
    unsolved_r: list[int] = []
    spare_f: list[int] = []
    spare_r: list[int] = []

    for comp_f, comp_r in _components(len(fixtures), len(rows), by_f, by_r):
        solved = _outcomes_of_every_optimum(comp_f, comp_r, by_f, edges)
        if solved is None:
            # Past the bound, so refused whole and under its own name. There is
            # deliberately no fallback: a walk that "does its best" here is the
            # arrival-order defect above wearing a budget.
            unsolved_f.extend(comp_f)
            unsolved_r.extend(comp_r)
            continue
        f_out, r_out = solved
        for fi in comp_f:
            partners = f_out[fi]
            if len(partners) != 1:
                tied_f.append(fi)
            elif (only := next(iter(partners))) is None:
                spare_f.append(fi)
            else:
                paired_idx.append((fi, only))
        for ri in comp_r:
            # The matched case is already published from the fixture side: a row
            # every optimum gives to one fixture is that fixture's unique partner.
            partners = r_out[ri]
            if len(partners) != 1:
                tied_r.append(ri)
            elif next(iter(partners)) is None:
                spare_r.append(ri)

    # Ordered by id rather than by position, so that what a receipt SHOWS is as
    # order-independent as what the row counts.
    def _by_ref(indices, population):
        return sorted((population[i] for i in indices), key=lambda side: side.ref)

    return _Resolution(
        paired=sorted(
            ((fixtures[fi], rows[ri]) for fi, ri in paired_idx),
            key=lambda pair: (pair[0].ref, pair[1].ref),
        ),
        tied_fixtures=_by_ref(tied_f, fixtures),
        tied_rows=_by_ref(tied_r, rows),
        unsolved_fixtures=_by_ref(unsolved_f, fixtures),
        unsolved_rows=_by_ref(unsolved_r, rows),
        spare_fixtures=_by_ref(spare_f, fixtures),
        spare_rows=_by_ref(spare_r, rows),
    )


def pair_tennis_sides(
    fixtures: Sequence[Side],
    rows: Sequence[Side],
    normalize: Callable[[Optional[str]], str] | None = None,
    *,
    draw: Optional[str] = None,
) -> Join:
    """The tennis join: `resolve_tennis_name`'s relation, nearest start as tiebreak.

    `normalize` is accepted and ignored — a tennis name is not reducible to a
    join string, which is the whole argument in the module docstring. It is in
    the signature so `build_agreement_row` has one call shape for every strategy
    rather than a branch that has to know which sport it is building.

    Call it with ONE draw at a time. It does not split singles from doubles
    itself: the split has to be two rows with two denominators
    (`split_by_draw`), and a function that silently handled both would let a
    caller ask for one number over both populations, which is the phantom gap
    this ship exists to prevent.

    `draw` says WHICH draw, and it exists only so the row can be honest about
    the reviewed order allowances (CERT-1948). Those two classes are singles
    player names, and the doubles join keys on an unordered pair of surnames:
    measured over the pinned corpus, **0 of 1,674 doubles names have a token
    multiset in `ORDER_ALIASES`**, so the tolerance cannot move a doubles
    number. Publishing it on the doubles row claimed a tolerance that row never
    relied on — the row saying something untrue about its own pass, which is the
    exact failure this ship exists to stop, committed by the ship itself.

    Unstated `draw` publishes NO allowance. A caller that has not said which
    draw it is building does not get a claim published on its behalf.
    """
    usable_f = [f for f in fixtures if _readable(f)]
    usable_r = [r for r in rows if _readable(r)]

    # Every decision is made per ASSIGNMENT over the whole candidate graph, and a
    # refusal is a TIE — never a shape, never a large candidate set, and never
    # the edge some walk happened to reach first. See `_pair_with_tie_detection`
    # and the progression of blocks recorded on `_ambiguity`.
    resolved = _pair_with_tie_detection(usable_f, usable_r)

    def _fixture_receipt(fx: Side, candidates: Sequence[Side], why: str) -> dict[str, Any]:
        return {
            "statpal_id": fx.ref,
            "players": [fx.home, fx.away],
            "statpal_start": fx.start.isoformat() if fx.start else None,
            "label": fx.label,
            "unresolved_name": None,
            "our_candidates": [],
            "our_event_ids": [r.ref for r in candidates],
            "why": why,
        }

    def _row_receipt(row: Side, why: str) -> dict[str, Any]:
        return {
            "event_id": row.ref,
            "players": [row.home, row.away],
            "our_start": row.start.isoformat() if row.start else None,
            "label": row.label,
            "column_holds": row.held_id,
            "why": why,
        }

    refused: list[dict[str, Any]] = []
    for fx in resolved.tied_fixtures:
        found = _ambiguity(fx, resolved.tied_rows)
        refused.append(
            found[0]
            if found is not None
            else _fixture_receipt(
                fx,
                resolved.tied_rows,
                "tied with another candidate at the same distance, so which "
                "match this is would be an arbitrary choice",
            )
        )

    refusals: dict[str, list[dict[str, Any]]] = {}
    if refused:
        refusals[AMBIGUOUS_REFUSAL] = refused
    if resolved.tied_rows:
        # Counted under their OWN name rather than added to the fixture receipt's
        # count. One tied fixture and two rows held out of the denominator are
        # different quantities, and `excluded` is read as a census.
        refusals[AMBIGUOUS_CANDIDATE_ROWS] = [
            _row_receipt(
                row,
                "tied with another of our rows for the same fixture at the same "
                "distance. Left in `ours_only` it would publish a duplicate of "
                "ours as a match StatPal is missing",
            )
            for row in resolved.tied_rows
        ]
    if resolved.unsolved_fixtures:
        refusals[UNSOLVED_COMPONENT_FIXTURES] = [
            _fixture_receipt(
                fx,
                resolved.unsolved_rows,
                f"this fixture sits in a candidate component larger than "
                f"{MAX_ASSIGNMENTS_PER_COMPONENT} possible assignments, so which "
                "pairings hold across all of them was not established. Not a "
                "finding about the field — a bound of ours, and the signal that "
                "it needs raising",
            )
            for fx in resolved.unsolved_fixtures
        ]
    if resolved.unsolved_rows:
        refusals[UNSOLVED_COMPONENT_ROWS] = [
            _row_receipt(
                row,
                "sits in the same unsolved candidate component. Left in "
                "`ours_only` it would publish our own bound as a match StatPal "
                "is missing",
            )
            for row in resolved.unsolved_rows
        ]

    left_out_f = {fx.ref for fx in resolved.tied_fixtures} | {
        fx.ref for fx in resolved.unsolved_fixtures
    }
    left_out_r = {row.ref for row in resolved.tied_rows} | {
        row.ref for row in resolved.unsolved_rows
    }

    return Join(
        fixtures=[f for f in usable_f if f.ref not in left_out_f],
        rows=[r for r in usable_r if r.ref not in left_out_r],
        paired=resolved.paired,
        statpal_only=resolved.spare_fixtures,
        ours_only=resolved.spare_rows,
        unusable_fixtures=[f for f in fixtures if not _readable(f)],
        unusable_rows=[r for r in rows if not _readable(r)],
        refusals=refusals,
        refusal_names=TENNIS_REFUSAL_NAMES,
        allowances=(
            {ORDER_ALIAS_ALLOWANCE: [a.receipt() for a in REVIEWED_ALIASES]}
            if draw == SINGLES
            else {}
        ),
        denominator_is=TENNIS_DENOMINATOR_IS,
    )


def tennis_measurement_bounds(write_window, *, now):
    """The span of OUR tennis inventory a row is measured over.

    `measurement_bounds` with tennis's own horizon rather than the team-sport
    one. Routed through the shared function rather than computed here so the two
    load-bearing properties come along unchanged: it is never narrower than the
    write window, and it reaches past the edge of a rolling schedule.
    """
    return measurement_bounds(
        write_window, now=now, horizon=TENNIS_MEASUREMENT_HORIZON
    )


def build_tennis_agreements(
    *,
    fixtures: Sequence[Side],
    rows: Sequence[Side],
    read_failures: Sequence[str] = (),
    sources_read: Sequence[str] = (),
    window: Optional[tuple] = None,
    measurement_window: Optional[tuple] = None,
) -> dict[str, dict[str, Any]]:
    """One agreement row per draw, keyed by its `SHADOW_STAMPERS` key.

    **Both sides are split before either is counted.** Splitting only StatPal's
    side would leave our doubles rows in the singles denominator, where nothing
    can ever match them, and the singles row would report our own doubles
    inventory as a disagreement.

    Neither row is scored on the clock (`time_authority=False`) and neither has a
    governing number, so both gate `PENDING-NO-GOVERNING-NUMBER` and neither can
    advance a streak. That is the state, not a placeholder for one.
    """
    singles_f, doubles_f = split_by_draw(fixtures)
    singles_r, doubles_r = split_by_draw(rows)

    def _row(sport_key: str, fs: Sequence[Side], rs: Sequence[Side]):
        return build_agreement_row(
            sport_key=sport_key,
            fixtures=fs,
            rows=rs,
            # Unused by this strategy and required by the signature. `str` rather
            # than a lambda that folds a name: a normaliser that looked plausible
            # here would be a second, dead implementation of tennis identity, and
            # the next reader would believe it.
            normalize=str,
            read_failures=read_failures,
            sources_read=sources_read,
            window=window,
            measurement_window=measurement_window,
            # Bound to the draw being built, so the row's `allowances` describe
            # THIS draw's pass and not the other one's (CERT-1948).
            pair_sides=partial(pair_tennis_sides, draw=sport_key),
            time_authority=False,
        )

    return {
        SINGLES: _row(SINGLES, singles_f, singles_r),
        DOUBLES: _row(DOUBLES, doubles_f, doubles_r),
    }
