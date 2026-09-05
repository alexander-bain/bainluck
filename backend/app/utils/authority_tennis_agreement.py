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
    for them. `_pair_with_tie_detection` settles the distinguishable ones by
    nearest start and refuses only the ties.

14 days holds 2,004 of our tennis rows, 252 of them doubles, across 8 sport keys
(production 2026-09-05) — a denominator a ten-minute task can read.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Optional, Sequence

from app.utils.authority_agreement import (
    Join,
    Side,
    build_agreement_row,
    measurement_bounds,
)
from app.utils.authority_tennis_names import (
    AMBIGUOUS,
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

#: What this strategy's denominator actually is, published on the row.
#:
#: The shared default describes an ordered normalised-pair key with kickoff as an
#: in-key tiebreak. **Every clause of that is false for tennis** — the join is a
#: resolver over a non-transitive relation, orientation is not a difference, and
#: there are no keys to be inside of. A row that describes the wrong join is a
#: measurement with the wrong source attached to it (CERT-1895's lesson, and
#: CERT-1904 caught this file failing it).
TENNIS_DENOMINATOR_IS = (
    "distinct matches under the union of both sides, joined by "
    "`authority_tennis_names.resolve_tennis_name` on BOTH players in either "
    "orientation — not by a normalised pair key, because the identity relation "
    "reads a missing given name as UNKNOWN and so is not transitive. Start time "
    "chooses WHICH of two admissible pairings is made and never whether one is "
    "made. Singles and doubles are separate denominators; a fixture whose player "
    "our register holds under two identities, and any of our rows it could not "
    "be told apart between, leave the denominator under `excluded` rather than "
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

    See :func:`_resolve_components`, which owns that walk. This function is now
    only the RECEIPT: it names which player the register holds twice, via
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


def _pair_with_tie_detection(
    fixtures: Sequence[Side], rows: Sequence[Side]
) -> tuple[list[tuple[Side, Side]], list[Side], list[Side], list[Side], list[Side]]:
    """Pair by nearest start, refusing only the assignments that are TIED.

    Returns `(paired, tied_fixtures, tied_rows, spare_fixtures, spare_rows)`.

    **A candidate set is not ambiguous because it is large; it is ambiguous when
    the tiebreak cannot break it.** That is CERT-1913's correction and it is the
    module's own declared contract finally implemented: the start time chooses
    WHICH of two admissible pairings is made and never whether one is made. Two
    Alcaraz-Sinner fixtures a week apart against one row sitting on the earlier
    kickoff are not indistinguishable — the clock says which — so that row pairs
    and the later fixture is an honest `statpal_only`.

    A selection is TIED when, at the moment it is made, another still-available
    candidate competing for the same fixture or the same row sits at the SAME
    distance. Then the greedy choice would be arbitrary, and an arbitrary choice
    is exactly what this module refuses to publish. Both endpoints and every
    competitor are withdrawn and reported.

    Untimed candidates are settled last and any contested untimed choice is a tie
    by construction: with no clock there is nothing to break it, and arrival order
    is not evidence.

    Note the granularity — this is per ASSIGNMENT, not per component. A component
    holding one clean pair and one genuine tie keeps the clean pair, because
    discarding a match we can prove in order to refuse one we cannot is how a
    repair for over-publishing becomes a defect of under-publishing (CERT-1913).
    """
    timed: list[tuple[timedelta, int, int]] = []
    untimed: list[tuple[int, int]] = []
    for fi, f in enumerate(fixtures):
        for ri, r in enumerate(rows):
            if not _sides_agree(f, r):
                continue
            gap = None if f.start is None or r.start is None else abs(f.start - r.start)
            if gap is None:
                untimed.append((fi, ri))
            else:
                timed.append((gap, fi, ri))
    timed.sort(key=lambda c: (c[0], c[1], c[2]))

    used_f: set[int] = set()
    used_r: set[int] = set()
    tied_f: set[int] = set()
    tied_r: set[int] = set()
    paired: list[tuple[Side, Side]] = []

    def _available(fi: int, ri: int) -> bool:
        return fi not in used_f and ri not in used_r

    for gap, fi, ri in timed:
        if not _available(fi, ri):
            continue
        rivals = [
            (g2, fj, rj)
            for g2, fj, rj in timed
            if (fj, rj) != (fi, ri)
            and g2 == gap
            and (fj == fi or rj == ri)
            and _available(fj, rj)
        ]
        if rivals:
            for g2, fj, rj in [(gap, fi, ri), *rivals]:
                used_f.add(fj)
                used_r.add(rj)
                tied_f.add(fj)
                tied_r.add(rj)
            continue
        used_f.add(fi)
        used_r.add(ri)
        paired.append((fixtures[fi], rows[ri]))

    for fi, ri in untimed:
        if not _available(fi, ri):
            continue
        rivals = [
            (fj, rj)
            for fj, rj in untimed
            if (fj, rj) != (fi, ri)
            and (fj == fi or rj == ri)
            and _available(fj, rj)
        ]
        if rivals:
            for fj, rj in [(fi, ri), *rivals]:
                used_f.add(fj)
                used_r.add(rj)
                tied_f.add(fj)
                tied_r.add(rj)
            continue
        used_f.add(fi)
        used_r.add(ri)
        paired.append((fixtures[fi], rows[ri]))

    spare_f = [
        f for i, f in enumerate(fixtures) if i not in used_f and i not in tied_f
    ]
    spare_r = [r for i, r in enumerate(rows) if i not in used_r and i not in tied_r]
    return (
        paired,
        [fixtures[i] for i in sorted(tied_f)],
        [rows[i] for i in sorted(tied_r)],
        spare_f,
        spare_r,
    )


def pair_tennis_sides(
    fixtures: Sequence[Side],
    rows: Sequence[Side],
    normalize: Callable[[Optional[str]], str] | None = None,
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
    """
    usable_f = [f for f in fixtures if _readable(f)]
    usable_r = [r for r in rows if _readable(r)]

    # Every decision is made per ASSIGNMENT, and a refusal is a TIE — not a
    # large candidate set. See `_pair_with_tie_detection` and the progression of
    # four blocks recorded on `_ambiguity`.
    (
        paired,
        tied_fixtures,
        tied_rows,
        statpal_only,
        ours_only,
    ) = _pair_with_tie_detection(usable_f, usable_r)

    refused: list[dict[str, Any]] = []
    for fx in tied_fixtures:
        found = _ambiguity(fx, tied_rows)
        refused.append(
            found[0]
            if found is not None
            else {
                "statpal_id": fx.ref,
                "players": [fx.home, fx.away],
                "statpal_start": fx.start.isoformat() if fx.start else None,
                "label": fx.label,
                "unresolved_name": None,
                "our_candidates": [],
                "our_event_ids": [r.ref for r in tied_rows],
                "why": (
                    "tied with another candidate at the same distance, so which "
                    "match this is would be an arbitrary choice"
                ),
            }
        )

    refusals: dict[str, list[dict[str, Any]]] = {}
    if refused:
        refusals[AMBIGUOUS_REFUSAL] = refused
    if tied_rows:
        # Counted under their OWN name rather than added to the fixture receipt's
        # count. One tied fixture and two rows held out of the denominator are
        # different quantities, and `excluded` is read as a census.
        refusals[AMBIGUOUS_CANDIDATE_ROWS] = [
            {
                "event_id": r.ref,
                "players": [r.home, r.away],
                "our_start": r.start.isoformat() if r.start else None,
                "label": r.label,
                "column_holds": r.held_id,
                "why": (
                    "tied with another of our rows for the same fixture at the "
                    "same distance. Left in `ours_only` it would publish a "
                    "duplicate of ours as a match StatPal is missing"
                ),
            }
            for r in tied_rows
        ]

    refused_f_refs = {fx.ref for fx in tied_fixtures}
    held_refs = {r.ref for r in tied_rows}

    return Join(
        fixtures=[f for f in usable_f if f.ref not in refused_f_refs],
        rows=[r for r in usable_r if r.ref not in held_refs],
        paired=paired,
        statpal_only=statpal_only,
        ours_only=ours_only,
        unusable_fixtures=[f for f in fixtures if not _readable(f)],
        unusable_rows=[r for r in rows if not _readable(r)],
        refusals=refusals,
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
            pair_sides=pair_tennis_sides,
            time_authority=False,
        )

    return {
        SINGLES: _row(SINGLES, singles_f, singles_r),
        DOUBLES: _row(DOUBLES, doubles_f, doubles_r),
    }
