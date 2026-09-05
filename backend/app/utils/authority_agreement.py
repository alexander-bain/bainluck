"""The agreement row the flip gate is counted on. #2867 / D50, program step 2.

**SHIP: the 7-day agreement count that decides whether StatPal may ever become a
source of record can actually start, because the number it counts is published
instead of re-derived by hand every morning.** (Pillar: MATCHING.)

D50 sets one gate: *nothing user-visible flips without a measured 7-day ≥99.5%
agreement row from the bus AND a YOUR-TURN entry Alex has seen.* Bus bucket
`M-R-AUTHORITY` appends one row per sport per day to
`ARTIFACT-M-R-AUTHORITY-LEDGER.md`, and `ARTIFACT-AUTHORITY-LEDGER-SPEC.md` says
what a row must contain. This module computes that row.

WHY THE STAMPER'S OWN COUNTS ARE NOT THE ROW
════════════════════════════════════════════
`tasks/stamp_nfl_statpal_fixtures` matches on **both team names AND kickoff
within ±1h**, which is the right rule for *writing an identity claim* and the
wrong one for *measuring identity*. The spec says so in rule 4:

    Join on identity; never key the join on the field under test. A join keyed
    on kickoff cannot report a kickoff disagreement — it drops the row instead.

Production, first pass 2026-09-04 10:23Z, is that sentence with numbers on it:
38 fixtures "unmatched" and 31 of our rows "unmatched", and the two lists are
mostly THE SAME GAMES seen from both ends. `Tampa Bay Buccaneers v Atlanta
Falcons` is StatPal 2026-12-27T00:00Z and ours 2026-12-27T05:00Z — one game, one
kickoff disagreement, counted by the stamper as two separate misses. Published
as identity, that reads 244/321 = 76% and would put a flip permanently out of
reach for a reason that is not an identity problem at all.

So this module joins on the **normalised team pair** and nothing else, uses the
nearest kickoff only to decide *which* meeting of a repeat fixture pairs with
which, and reports the clock as its own bucket that gates nothing.

WHAT A ROW SAYS
═══════════════
  * ``identity`` — in both / StatPal-only / ours-only. The governing bucket, and
    it carries TWO numbers: ``pct`` over the union of both sides, and
    ``ours_covered_pct`` over the games we list. Both are published for every
    sport. ``identity.governing`` says which of them scores THIS sport's streak
    and whether it clears the bar (D63; `GOVERNING_IDENTITY_NUMBERS`) — because
    the answer differs by sport, and a reader picking one is a reader who can
    pick the wrong one. Each number's complement is split by horizon —
    ``statpal_only_by_horizon`` and ``ours_only_by_horizon`` — so an absence
    outside the span the other side publishes is never read as a disagreement
    about a game.
  * ``schedule`` — within the window / off by hours / a different day. Reported,
    never merged into identity (spec rule 2: a blend buried five real findings
    inside twenty-four non-findings).
  * ``anchors`` — of the games both sides have, how many carry the id join the
    shadow stamper wrote. This is the number that says the join is usable; it is
    NOT the agreement number, and putting them in one ratio would mean a sport
    with no stamper yet reads as a disagreement.
  * ``excluded`` — every row left out, by name and count. An unstated exclusion
    is how a bar becomes unreachable by design (spec rule 5).
  * ``measurement_window`` — the span of OUR inventory the row was measured over,
    stated beside ``window`` (the narrower span the stamper writes ids in)
    because they are no longer the same span and a reader cannot tell which
    produced a denominator by looking at the number.

WHAT IT REFUSES TO DO
═════════════════════
It computes nothing from an empty read. A pass that could not reach StatPal
produces ``read="READ-FAILED"`` and no percentages at all — not 0%, which would
reset a streak that should only pause (spec rule 6, gotcha #53).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Sequence

#: How far apart two kickoffs may be and still be called agreement. Same value
#: the NFL stamper writes on, restated here rather than imported: the stamper's
#: window is a *write* threshold and this one is a *report* threshold, and the
#: day one of them moves the other must not follow silently.
WITHIN = timedelta(hours=1)

#: Past this, the two sides are not describing the same slot in the week. The
#: spec's "wrong week" bucket. 1.2 days, not 1.0: an NFL Sunday afternoon game
#: and a Sunday night game are ~7 hours apart, and calling that a wrong week
#: would file the league's own schedule as a defect.
WRONG_DAY = timedelta(days=1.2)

#: The shortest gap between two consecutive games of ONE league in our own
#: table — a league's offseason, measured rather than recalled. NHL's, from
#: 2026-06-15 (last playoff game) to 2026-09-19 (first preseason game), over a
#: 700-day sample of `events` read 2026-09-05. NBA's is 128.8 days, the NFL's
#: 179.0; MLB's does not appear because our MLB inventory begins mid-season.
#:
#: It is here as the ceiling on `MEASUREMENT_HORIZON` and for nothing else.
TIGHTEST_OFFSEASON_GAP = timedelta(days=97)

#: How far either side of NOW our own inventory is measured for the agreement
#: row, over and above the span the stamper writes ids in.
#:
#: The two spans are different questions and used to be one query. The stamper
#: matches ids, so it reads only where StatPal has fixtures to match against —
#: correctly. The row ANSWERS "of the games we list, does StatPal have them?",
#: and reading that over StatPal's own span answers it only where StatPal has
#: already said yes: a game of ours past the edge of a rolling schedule was
#: dropped by SQL before it could be counted as missing (CERT-962). The
#: denominator was horizon-subtracted at selection while the row said it was not.
#:
#: 40 days, and the number is bounded from both ends:
#:
#:   * it must be WIDER than any provider's rolling window, or the subtraction
#:     survives. MLB's `season-schedule` is ~17 days, measured.
#:   * it must be narrower than half `TIGHTEST_OFFSEASON_GAP`, or a span anchored
#:     in an offseason reaches two different seasons and the row compares one
#:     season's inventory to another's schedule. 2 × 40 = 80 days against a
#:     measured 97, a 17-day margin. `test_measurement_horizon_cannot_span_two_seasons`
#:     fails if a later edit spends that margin.
#:
#: This is a horizon, not a season: `events` carries no season column, and a
#: bound derived from one we do hold beats a bound named after one we do not.
MEASUREMENT_HORIZON = timedelta(days=40)

#: Team-name tokens that name no franchise. A StatPal playoff bracket carries
#: these until the seeding is known; there is nothing for us to disagree with,
#: so they leave the denominator by name and are counted where they went.
PLACEHOLDER_TOKENS = frozenset({"tbd", "tba", "to be decided", "to be announced"})

#: Ceiling on any one receipt list. The row is read by a bus window and by a
#: human; a 300-entry list is neither. The count beside it is never capped, so
#: truncation can never change a number, only the examples under it.
RECEIPT_CAP = 40

READ_OK = "READ-OK"
READ_FAILED = "READ-FAILED"

#: Which sports have a shadow stamper, and which task banks their row.
#:
#: One entry per sport that program step 2/3 has landed — a sport is here
#: BECAUSE something writes its correspondence, not because we intend to. The
#: per-sport flip config (`AUTHORITY_BY_SPORT`, program step 6) will supersede
#: this map when it exists; until then a sport's presence here means exactly
#: "there is a dark id join for it and an agreement row to read".
SHADOW_STAMPERS: dict[str, str] = {
    "americanfootball_nfl": "stamp_nfl_statpal_fixtures",
    "basketball_nba": "stamp_nba_statpal_fixtures",
    "icehockey_nhl": "stamp_nhl_statpal_fixtures",
    "baseball_mlb": "stamp_mlb_statpal_fixtures",
}

#: The bar a governing number must clear, on seven consecutive daily rows, before
#: a sport's authority may be flipped (ledger spec rule 1, D50). Stated once,
#: here, so the row can carry its own verdict instead of a reader comparing.
FLIP_BAR_PCT = 99.5

#: WHICH of identity's two numbers a sport's seven-day streak is scored on.
#: D63 = A (Alex, 2026-09-04): "NBA/NHL seven-day agreement = 'of the games WE
#: list, StatPal has them'; NFL symmetric."
#:
#: `identity` is the governing BUCKET — that is the axis `governs` marks, against
#: `schedule` and `anchors`, which report and gate nothing. D63 settles a second
#: question the bucket flag cannot answer, because identity carries TWO numbers:
#:
#:   * ``pct`` — the UNION denominator. "Of every game either side lists, how
#:     many does the other also list?" Meaningful only where both sides publish
#:     the same population.
#:   * ``ours_covered_pct`` — "of the games WE list, does StatPal have them?"
#:     This is the question Alex's bar actually asks, and the only one reachable
#:     where StatPal publishes a whole season on day one and we ingest a rolling
#:     odds-driven slice.
#:
#: NFL is SYMMETRIC: both sides carry the same population, measured 99.69 against
#: 99.38 on 9/4. So both numbers govern, and requiring both costs nothing —
#: where the two questions have the same answer, asking both is free and asking
#: only one throws away a real signal.
#:
#: NBA and NHL are NOT symmetric: 100.00 against 3.40. Scoring them on `pct`
#: would hold a flip permanently out of reach for a reason that is not a
#: disagreement about a single game — exactly the unreachable-by-design failure
#: spec rule 5 exists to prevent.
#:
#: **A sport absent from this map has NO governing number and CANNOT clear the
#: bar.** That is the point, not an oversight: this map is where a sport answers
#: "which question decides my flip?", and a sport that has not answered it must
#: not be scored by a default. Under D55 the answer is explicit or it is absent;
#: a gap tags loudly and never silently passes. Absent today, each for a stated
#: reason and neither by omission:
#:
#:   * ``baseball_mlb`` — joins the shadow today (program step 5) and has never
#:     produced a row, so the shape of its two numbers is UNMEASURED. Its
#:     `season-schedule` is a rolling ~17-day window (227 games) rather than a
#:     season, so it is a priori neither NFL's case nor NBA's, and guessing which
#:     would be the half-configured sport `LeagueSpec` exists to forbid. Decide
#:     it from its first seven rows, not from this comment.
#:   * ``tennis_atp`` / ``tennis_wta`` — the forward matcher has not landed, and
#:     tennis is an existence authority rather than a time authority
#:     (`ARTIFACT-AUTHORITY-20260903-TENNIS.md`).
GOVERNING_IDENTITY_NUMBERS: dict[str, tuple[str, ...]] = {
    "americanfootball_nfl": ("pct", "ours_covered_pct"),
    "basketball_nba": ("ours_covered_pct",),
    "icehockey_nhl": ("ours_covered_pct",),
}

#: The FOUR states of the flip gate. Only one of them advances a streak, and the
#: other three are distinct facts that a three-state gate would have blurred:
#:
#:   * ``MEETS``    — measured, at or above the bar. Advances the streak.
#:   * ``BELOW``    — measured, under the bar. Resets it.
#:   * ``NO-SCORE`` — the read succeeded but there was nothing to divide by, so
#:     `_pct` returned `None`. Carries the streak unchanged, exactly as
#:     `READ-FAILED` does (spec rule 6). Collapsing this into `BELOW` would
#:     reset a streak on a day nobody disagreed about anything — gotcha #53's
#:     class, and the reason `_pct` refuses to return `0.0` in the first place.
#:   * ``PENDING-NO-GOVERNING-NUMBER`` — the sport has not been told which of
#:     its two numbers decides. Nothing to advance, nothing to reset.
#:
#: The last two are both "not advancing" and are still not the same thing: one
#: is a quiet day, the other is an unanswered question, and only one of them is
#: fixed by a ruling.
GATE_MEETS = "MEETS"
GATE_BELOW = "BELOW"
GATE_NO_SCORE = "NO-SCORE"
GATE_PENDING = "PENDING-NO-GOVERNING-NUMBER"

#: The gate states that leave a seven-day streak exactly as it was. Published as
#: a set rather than re-derived by each reader: whether a state pauses or resets
#: a streak is a spec decision, not a rendering detail.
GATES_CARRY_STREAK = frozenset({GATE_NO_SCORE, GATE_PENDING})

#: The one-paragraph summary the agreement endpoint prints above the sports, and
#: the first thing anybody reading the payload reads.
#:
#: It is BUILT from the constants above rather than typed beside them, because
#: the summary that ships is the summary that goes stale. The wording it
#: replaces ("identity >= 99.5% on the governing bucket") predated D63 and was
#: true of the buckets and wrong about the numbers: identity is indeed the
#: governing bucket against `schedule` and `anchors`, but a reader who has just
#: been told "identity >= 99.5%" reaches for `identity.pct`, which for NBA and
#: NHL reads 3.40 and governs nothing. Scoring a sport on the wrong one of
#: identity's two numbers is the exact mistake D63 exists to prevent, so it may
#: not survive in the payload's opening sentence.
#:
#: So this says the three things a reader needs before they look at a number:
#: which question decides is PER SPORT, the verdict is already computed on the
#: row, and there are four gate states rather than pass/fail.
FLIP_GATE_SUMMARY = (
    f"D50: a flip needs 7 consecutive daily rows clearing {FLIP_BAR_PCT}%, plus "
    "a YOUR-TURN entry Alex has seen. Identity governs; schedule and anchors "
    "are reported and gate nothing. WHICH of identity's two numbers scores a "
    "sport is per sport (D63), so do not compare a percentage to the bar "
    "yourself — read the verdict off that sport's `identity.governing`, which "
    "names the number(s), their values and the bar it used. Four gate states: "
    f"`{GATE_MEETS}` advances the streak, `{GATE_BELOW}` resets it, and "
    f"`{GATE_NO_SCORE}` (nothing to divide by) and `{GATE_PENDING}` (the sport "
    "has not been told which number decides) both carry it unchanged."
)


def _identity_block(
    sport_key: str,
    *,
    both: int,
    statpal_only: int,
    ours_only: int,
    denominator: int,
    horizon: dict[str, int],
    ours_horizon: dict[str, int],
) -> dict[str, Any]:
    """The identity bucket, with its two numbers and the ruling on which decides.

    Built here rather than inline so that `governing` is assembled from the very
    same numbers the row publishes. A verdict computed from a second, parallel
    derivation of `pct` is a verdict that can disagree with the figure printed
    beside it.
    """
    identity: dict[str, Any] = {
        "both": both,
        "statpal_only": statpal_only,
        "ours_only": ours_only,
        "pct": _pct(both, denominator),
        # `identity` is the governing BUCKET, against `schedule` and `anchors`.
        # WHICH of its two numbers scores the streak is a separate question,
        # answered per sport in `governing` below (D63).
        "governs": True,
        # Where the StatPal-only games fall against our own inventory.
        # Reported, never subtracted — see `_statpal_only_by_horizon`.
        "statpal_only_by_horizon": horizon,
        # "Of the games WE hold, how many does StatPal also have?"
        #
        # A DIFFERENT question from `pct`. For a sport where both sides carry
        # the same population it is nearly the same number (NFL: 99.69 against
        # 99.38). For NBA and NHL, where StatPal publishes a season and we
        # ingest a rolling odds-driven slice, it is 100.00 against 3.40 — and
        # the gap between the two IS the finding, which is why both are printed
        # and neither is blended into the other (spec rule 2).
        #
        # Under D63 this is the number that GOVERNS for NBA and NHL. It is still
        # published for every sport, governing or not: the pair is the finding.
        "ours_covered_pct": _pct(both, both + ours_only),
        # Where our own misses fall against StatPal's published span — the
        # mirror of `statpal_only_by_horizon`, and the split that says whether
        # `ours_covered_pct`'s complement is a disagreement or their horizon.
        # Reported, never subtracted — see `_ours_only_by_horizon`.
        "ours_only_by_horizon": ours_horizon,
    }
    identity["governing"] = governing_identity(sport_key, identity)
    return identity


def governing_identity(sport_key: str, identity: dict[str, Any]) -> dict[str, Any]:
    """Which identity number(s) gate this sport's flip, and whether they clear.

    The verdict is computed HERE and published on the row, rather than left to
    whoever reads the ledger (D46's pattern: move the scoring into the app and
    let the bus read the number). Two readers comparing two percentages against
    a remembered bar is how a sport gets scored on the wrong question — which is
    the whole of what D63 fixes.
    """
    names = GOVERNING_IDENTITY_NUMBERS.get(sport_key)
    if not names:
        return {
            "numbers": [],
            "values": {},
            "bar_pct": FLIP_BAR_PCT,
            "gate": GATE_PENDING,
            "why": (
                f"{sport_key} has no governing identity number, so no daily row "
                "can advance its streak. Both numbers are still published below; "
                "what is missing is the ruling on which one decides."
            ),
        }
    values = {name: identity[name] for name in names}
    # `None` is not a low score, it is the absence of one, and it must reach the
    # gate as its own state rather than being compared against the bar. A single
    # unscored number makes the whole verdict NO-SCORE: a sport does not half
    # clear a bar.
    unscored = sorted(name for name, value in values.items() if value is None)
    if unscored:
        return {
            "numbers": list(names),
            "values": values,
            "bar_pct": FLIP_BAR_PCT,
            "gate": GATE_NO_SCORE,
            "why": (
                f"{', '.join(unscored)} has no denominator to divide by, so this "
                "day scores nothing and carries the streak unchanged (spec rule 6)"
            ),
        }
    below = sorted(name for name, value in values.items() if value < FLIP_BAR_PCT)
    return {
        "numbers": list(names),
        "values": values,
        "bar_pct": FLIP_BAR_PCT,
        "gate": GATE_BELOW if below else GATE_MEETS,
        "why": (
            f"{', '.join(below)} below {FLIP_BAR_PCT}%"
            if below
            else f"all governing numbers at or above {FLIP_BAR_PCT}%"
        ),
    }


@dataclass(frozen=True)
class Side:
    """One fixture, from either side, in the only terms the join needs.

    Deliberately not a ``StatPalFixture`` and not an ORM row: this module is
    pure so it can be driven by real payloads from both sides at once, and a
    shared shape is what lets the two sides be compared without either one's
    vocabulary winning.
    """

    #: StatPal's contest id, or our event id as a string. Only ever displayed.
    ref: str
    home: Optional[str]
    away: Optional[str]
    start: Optional[datetime]
    #: Round, status — whatever this side calls the context. Receipts only.
    label: Optional[str] = None
    #: For our rows: what ``events.statpal_fixture_id`` currently holds.
    held_id: Optional[str] = None


def is_placeholder(name: Optional[str]) -> bool:
    """`"TBD"` names no team; `"Tampa Bay Buccaneers"` does."""
    if not name:
        return False
    return str(name).strip().lower() in PLACEHOLDER_TOKENS


def _pair_key(side: Side, normalize: Callable[[Optional[str]], str]) -> Optional[str]:
    """`(away, home)` normalised, in that orientation, or `None` if unusable.

    Orientation is kept because a home-and-home pair of division games are two
    different fixtures, and folding them into one key would pair Week 6 with
    Week 14 and then report the kickoff gap as a defect.
    """
    away = normalize(side.away)
    home = normalize(side.home)
    if not away or not home:
        return None
    return f"{away}@{home}"


def _delta(a: Side, b: Side) -> Optional[timedelta]:
    if a.start is None or b.start is None:
        return None
    return abs(a.start - b.start)


def _pair_within_key(
    fixtures: list[Side], rows: list[Side]
) -> tuple[list[tuple[Side, Side]], list[Side], list[Side]]:
    """Pair one key's fixtures to its rows by nearest kickoff, dropping neither.

    Greedy on the smallest gap first. Two teams meet twice a season and both
    meetings live under one key, so *something* has to decide which pairs with
    which — but the gap is a tiebreak and never a filter: a pairing is made
    however far apart the two kickoffs are, because the whole point is to be
    able to report that distance instead of losing the row to it.

    Pairs with a missing kickoff on either side are made last, in arrival order,
    once every timed pairing has been settled. Absence is not proximity.
    """
    candidates = []
    for fi, f in enumerate(fixtures):
        for ri, r in enumerate(rows):
            d = _delta(f, r)
            if d is not None:
                candidates.append((d, fi, ri))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))

    used_f: set[int] = set()
    used_r: set[int] = set()
    paired: list[tuple[Side, Side]] = []
    for _d, fi, ri in candidates:
        if fi in used_f or ri in used_r:
            continue
        used_f.add(fi)
        used_r.add(ri)
        paired.append((fixtures[fi], rows[ri]))

    spare_f = [f for i, f in enumerate(fixtures) if i not in used_f]
    spare_r = [r for i, r in enumerate(rows) if i not in used_r]
    while spare_f and spare_r:
        paired.append((spare_f.pop(0), spare_r.pop(0)))
    return paired, spare_f, spare_r


def _schedule_bucket(fixture: Side, row: Side) -> str:
    d = _delta(fixture, row)
    if d is None:
        return "time_missing"
    if d <= WITHIN:
        return "within"
    if d > WRONG_DAY:
        return "wrong_day"
    return "off_by_hours"


def _fixture_receipt(f: Side, r: Optional[Side] = None, **extra: Any) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "statpal_id": f.ref,
        "teams": [f.away, f.home],
        "statpal_start": f.start.isoformat() if f.start else None,
        "label": f.label,
    }
    if r is not None:
        receipt["event_id"] = r.ref
        receipt["our_start"] = r.start.isoformat() if r.start else None
        d = _delta(f, r)
        receipt["delta_hours"] = None if d is None else round(
            d.total_seconds() / 3600.0, 2
        )
    receipt.update(extra)
    return receipt


def _row_receipt(r: Side, **extra: Any) -> dict[str, Any]:
    return {
        "event_id": r.ref,
        "teams": [r.away, r.home],
        "our_start": r.start.isoformat() if r.start else None,
        "label": r.label,
        "column_holds": r.held_id,
        **extra,
    }


def _pct(numerator: int, denominator: int) -> Optional[float]:
    """`None`, never `0.0`, when there is nothing to divide by.

    A percentage over an empty denominator is not a low score, it is not a
    score. Returning zero here is how a sport nobody measured yet ends up
    looking like a sport that failed (gotcha #53).
    """
    if denominator <= 0:
        return None
    return round(100.0 * numerator / denominator, 2)


def measurement_bounds(
    write_window: tuple[datetime, datetime],
    *,
    now: datetime,
    horizon: timedelta = MEASUREMENT_HORIZON,
) -> tuple[datetime, datetime]:
    """The span of OUR inventory an agreement row is measured over.

    The union of the stamper's own write window with ``now ± horizon``, and the
    union rather than the wider of the two on purpose. Two properties fall out of
    it, and both are load-bearing:

      * **It is never narrower than the write window.** So no sport whose local
        inventory already sits inside StatPal's span can have its denominator
        moved by this function, and the three sports whose seven-day clocks are
        already running do not have their numbers redefined underneath them.
        Measured 2026-09-05: NFL 322 rows, NBA 41, NHL 32 — unchanged either way.
        Only MLB moves, 222 → 729, which is the sport this exists for and the one
        sport with no governing number yet.
      * **It reaches past the edge of a rolling schedule.** A game of ours in
        October, while StatPal's window ends after 17 days, is now inside the
        population and lands in ``ours_only_by_horizon.beyond_statpal_last``
        instead of never being read at all.

    `now` is passed, never called for: a bound that reads the clock itself cannot
    be pinned by a test at a fixed date (gotcha #44).
    """
    start, end = write_window
    return (min(start, now - horizon), max(end, now + horizon))


def _split_against_span(
    misses: Sequence[Side],
    span_source: Sequence[Side],
    *,
    before: str,
    inside: str,
    beyond: str,
) -> dict[str, int]:
    """Place each miss against the timed span of the OTHER side's list.

    The shared core of the two horizon splits. Both ask the same question in
    opposite directions — "does this absence fall inside the window the other
    side actually publishes?" — and a second hand-written copy of that arithmetic
    is a second place for the two directions to drift apart.

    An empty span is NOT an empty split: with no timed fixture on the other side
    there is no window to be inside or outside of, and reporting zeros would
    claim every miss falls within it. Those rows go to ``unplaceable``, as does
    any miss with no kickoff of its own.
    """
    starts = [s.start for s in span_source if s.start is not None]
    split = {before: 0, inside: 0, beyond: 0, "unplaceable": 0}
    if not starts:
        split["unplaceable"] = len(misses)
        return split

    first, last = min(starts), max(starts)
    for m in misses:
        if m.start is None:
            split["unplaceable"] += 1
        elif m.start < first:
            split[before] += 1
        elif m.start > last:
            split[beyond] += 1
        else:
            split[inside] += 1
    return split


def _statpal_only_by_horizon(
    statpal_only: Sequence[Side], rows: Sequence[Side]
) -> dict[str, int]:
    """Split "StatPal has it, we don't" by where it falls against OUR inventory.

    Added by program step 3 because NBA and NHL make the distinction load-bearing
    and the NFL never could. StatPal publishes a whole season on day one — 1206
    NBA games, 1404 NHL — while our table only ever holds the games that have
    odds posted: 41 and 32, measured 2026-09-04. Under one undivided
    ``statpal_only`` count those two sports read as a 3% identity disagreement,
    when what is actually being measured is how far ahead our ingestion reaches.

    So the count is split, and none of the three parts govern anything:

      * ``before_our_first`` / ``beyond_our_last`` — outside the span our table
        covers at all. Not a disagreement about a game; a statement about our
        horizon.
      * ``inside_our_span`` — StatPal has a game on a date we DO cover and we
        hold no row for it. **This is the one that is a finding**, and it is the
        one an ingestion gap would show up in.

    `identity.pct` is untouched by any of this: the split is reported beside it,
    never subtracted from it, because an exclusion that quietly moves the number
    is the failure mode spec rule 5 exists to prevent.
    """
    return _split_against_span(
        statpal_only,
        rows,
        before="before_our_first",
        inside="inside_our_span",
        beyond="beyond_our_last",
    )


def _ours_only_by_horizon(
    ours_only: Sequence[Side], fixtures: Sequence[Side]
) -> dict[str, int]:
    """Split "we have it, StatPal doesn't" by where it falls against THEIR span.

    The mirror of `_statpal_only_by_horizon`, and it exists because the number it
    discriminates is the one that governs. `ours_covered_pct` — "of the games WE
    list, does StatPal have them?" — is the D63 governing number for NBA and NHL
    and one of NFL's two, and its complement is `ours_only`. Until now nothing on
    the row said whether one of those absences sits inside the span StatPal
    actually publishes or past the edge of it, and those are different facts:

      * ``inside_statpal_span`` — StatPal publishes that date and has no such
        game. **This is the one that is a finding**, and the only part of
        `ours_only` that is evidence StatPal would have left a hole in the site.
      * ``before_statpal_first`` / ``beyond_statpal_last`` — outside the span
        StatPal serves at all. Not a disagreement about a game; a statement about
        THEIR horizon, exactly as the mirrored buckets are about ours.

    MLB is why this is built now. Its `season-schedule` is a rolling ~17-day
    window rather than a season, so a game of ours two months out is guaranteed
    to be `ours_only` and guarantees nothing about agreement — while the same
    absence inside the window would be the strongest disagreement we can measure.
    D63's discriminator table was built entirely from the StatPal-side split, so
    MLB's governing number cannot be ruled on until the same split exists on this
    side (`ARTIFACT-AUTHORITY-20260905-*`, #2867).

    Reported, never subtracted: every row this splits is still in
    `ours_covered_pct`'s denominator. An exclusion that quietly moves the
    governing number is spec rule 5's failure mode, and it would be worse here
    than on the StatPal side precisely because this side governs.

    That sentence was once false where it mattered most, and the correction is
    the reason `measurement_bounds` exists. The split is honest about the rows it
    receives, but the caller used to hand it only the rows inside StatPal's own
    span ±1h — so an October game of ours, against a 17-day rolling schedule, was
    subtracted by SQL before this function could report it (CERT-962). The
    denominator is bounded by `MEASUREMENT_HORIZON` and by nothing else, and that
    bound is published on the row as ``measurement_window``.
    """
    return _split_against_span(
        ours_only,
        fixtures,
        before="before_statpal_first",
        inside="inside_statpal_span",
        beyond="beyond_statpal_last",
    )


def build_agreement_row(
    *,
    sport_key: str,
    fixtures: Sequence[Side],
    rows: Sequence[Side],
    normalize: Callable[[Optional[str]], str],
    read_failures: Sequence[str] = (),
    sources_read: Sequence[str] = (),
    window: Optional[tuple[datetime, datetime]] = None,
    measurement_window: Optional[tuple[datetime, datetime]] = None,
    is_anchor_id: Callable[[Optional[str]], bool] = lambda v: bool(
        v and str(v).strip().isdigit()
    ),
) -> dict[str, Any]:
    """One sport's ledger row, from both sides of the same moment.

    `read_failures` is not decoration. If either endpoint refused, the row is
    `READ-FAILED` and carries no percentage: the spec pauses a streak on a
    failed read and resets it on a real disagreement, and a row that cannot tell
    those apart makes the seven-day count meaningless.
    """
    row: dict[str, Any] = {
        "sport_key": sport_key,
        "sources_read": list(sources_read),
        "read_failures": list(read_failures),
    }
    if window:
        row["window"] = [window[0].isoformat(), window[1].isoformat()]
    if measurement_window:
        # Stated even when it equals `window`, which for three of the four sports
        # it does: a field that appears only when the two spans differ is a field
        # whose absence a reader has to interpret.
        row["measurement_window"] = [
            measurement_window[0].isoformat(),
            measurement_window[1].isoformat(),
        ]

    if read_failures:
        row["read"] = READ_FAILED
        row["note"] = (
            "one or more StatPal endpoints refused; no agreement computed. "
            "A READ-FAILED row pauses the streak, it does not reset it."
        )
        return row

    row["read"] = READ_OK

    # Exclusions FIRST, and counted where they went — spec rule 5.
    placeholder_fixtures = [
        f for f in fixtures if is_placeholder(f.home) or is_placeholder(f.away)
    ]
    real_fixtures = [
        f for f in fixtures if not (is_placeholder(f.home) or is_placeholder(f.away))
    ]
    unusable_fixtures = [f for f in real_fixtures if _pair_key(f, normalize) is None]
    unusable_rows = [r for r in rows if _pair_key(r, normalize) is None]
    real_fixtures = [f for f in real_fixtures if _pair_key(f, normalize) is not None]
    real_rows = [r for r in rows if _pair_key(r, normalize) is not None]

    by_key_f: dict[str, list[Side]] = {}
    for f in real_fixtures:
        by_key_f.setdefault(_pair_key(f, normalize), []).append(f)  # type: ignore[arg-type]
    by_key_r: dict[str, list[Side]] = {}
    for r in real_rows:
        by_key_r.setdefault(_pair_key(r, normalize), []).append(r)  # type: ignore[arg-type]

    paired: list[tuple[Side, Side]] = []
    statpal_only: list[Side] = []
    ours_only: list[Side] = []
    for key in set(by_key_f) | set(by_key_r):
        p, spare_f, spare_r = _pair_within_key(
            by_key_f.get(key, []), by_key_r.get(key, [])
        )
        paired.extend(p)
        statpal_only.extend(spare_f)
        ours_only.extend(spare_r)

    both = len(paired)
    denominator = both + len(statpal_only) + len(ours_only)
    horizon = _statpal_only_by_horizon(statpal_only, real_rows)
    ours_horizon = _ours_only_by_horizon(ours_only, real_fixtures)

    schedule: dict[str, int] = {
        "within": 0,
        "off_by_hours": 0,
        "wrong_day": 0,
        "time_missing": 0,
    }
    schedule_receipts: list[dict[str, Any]] = []
    anchored = 0
    anchor_mismatch: list[dict[str, Any]] = []
    polluted: list[dict[str, Any]] = []
    unanchored = 0

    for f, r in paired:
        bucket = _schedule_bucket(f, r)
        schedule[bucket] += 1
        if bucket != "within" and len(schedule_receipts) < RECEIPT_CAP:
            schedule_receipts.append(_fixture_receipt(f, r, bucket=bucket))

        held = r.held_id
        if held is not None and str(held).strip() and not is_anchor_id(held):
            # #2963: the column holds a sentence, not an id. It says "linked"
            # and can never be anchored, so it is neither anchored nor simply
            # missing — its own bucket, or the repair loses its population.
            polluted.append(_row_receipt(r, statpal_id=f.ref))
        elif held and str(held).strip() == str(f.ref):
            anchored += 1
        elif held and str(held).strip():
            anchor_mismatch.append(_row_receipt(r, statpal_id=f.ref))
        else:
            unanchored += 1

    row.update(
        {
            "denominator": denominator,
            "denominator_is": (
                "distinct fixtures under the union of both sides, keyed on the "
                "normalised (away, home) pair; kickoff is a tiebreak within a "
                "key and never a filter"
            ),
            "excluded": {
                "statpal_placeholders": len(placeholder_fixtures),
                "statpal_unusable_names": len(unusable_fixtures),
                "our_unusable_names": len(unusable_rows),
            },
            "identity": _identity_block(
                sport_key,
                both=both,
                statpal_only=len(statpal_only),
                ours_only=len(ours_only),
                denominator=denominator,
                horizon=horizon,
                ours_horizon=ours_horizon,
            ),
            "schedule": {
                **schedule,
                "governs": False,
                "within_is": f"kickoffs within {WITHIN}",
                "wrong_day_is": f"kickoffs more than {WRONG_DAY} apart",
            },
            "anchors": {
                "anchored": anchored,
                "unanchored": unanchored,
                "mismatch": len(anchor_mismatch),
                "polluted_column": len(polluted),
                "pct_of_both": _pct(anchored, both),
                "governs": False,
                "note": (
                    "the id join the shadow stamper wrote, over the games both "
                    "sides have. Not the agreement number."
                ),
            },
            "receipts": {
                "statpal_only": [
                    _fixture_receipt(f) for f in statpal_only[:RECEIPT_CAP]
                ],
                "ours_only": [_row_receipt(r) for r in ours_only[:RECEIPT_CAP]],
                "schedule_disagreements": schedule_receipts,
                "anchor_mismatch": anchor_mismatch[:RECEIPT_CAP],
                "polluted_column": polluted[:RECEIPT_CAP],
                "statpal_placeholders": [
                    _fixture_receipt(f) for f in placeholder_fixtures[:RECEIPT_CAP]
                ],
            },
        }
    )
    return row


def ledger_line(row: dict[str, Any], *, day: str, streak: str = "?/7") -> str:
    """The row as the one line `ARTIFACT-M-R-AUTHORITY-LEDGER.md` appends.

    The spec fixes this format, so it is rendered here rather than in the bus
    window: a format assembled by whoever is reading is a format that drifts,
    and the seven-day count is a comparison across days.
    """
    if row.get("read") == READ_FAILED:
        return (
            f"{day} | {row['sport_key']} | READ-FAILED:{'; '.join(row['read_failures'])} "
            f"| streak carried unchanged"
        )
    excl = row.get("excluded", {})
    excl_text = " ".join(f"{k}:{v}" for k, v in excl.items() if v) or "none"
    ident = row["identity"]
    sched = row["schedule"]
    return (
        f"{day} | {row['sport_key']} | denom={row['denominator']} excl={excl_text} "
        f"| identity={ident['pct']}% ({ident['both']}/{ident['statpal_only']}/"
        f"{ident['ours_only']}) "
        # Added by program step 3, and not decoration. NBA's line reads
        # `identity=3.4%` and NHL's `2.28%` — not because either side disagrees
        # about a game, but because StatPal publishes a whole season on day one
        # and we ingest a rolling odds-driven slice. Without `covers=` beside it
        # a bus operator appends a catastrophic-looking row every morning for a
        # sport where the two sides agree about every game we hold.
        f"| covers={ident['ours_covered_pct']}% "
        # D63: the two numbers above are BOTH published for every sport, and
        # this field says which of them this sport is scored on and whether it
        # clears. Rendered from the row's own verdict rather than recomputed,
        # so the line can never disagree with the JSON it came from — and so a
        # bus operator advances a streak by reading a word, not by remembering
        # which question NBA is asked.
        f"| gate={_gate_text(ident)} "
        f"| schedule={sched['within']}/{sched['off_by_hours']}/{sched['wrong_day']}"
        f"/{sched['time_missing']} "
        f"| anchors={row['anchors']['anchored']} "
        f"| streak={streak} | {READ_OK}"
    )


def _gate_text(identity: dict[str, Any]) -> str:
    """`gate=` as one unambiguous token, with the number it was decided on.

    PENDING renders differently from BELOW on purpose. A sport with no governing
    number and a sport measured under the bar are both "not advancing", and a
    format that showed them alike would be a check whose pass and fail look the
    same.
    """
    governing = identity.get("governing") or {}
    gate = governing.get("gate", GATE_PENDING)
    if gate == GATE_PENDING:
        return GATE_PENDING
    scored = ",".join(
        f"{name}={governing['values'][name]}%" for name in governing["numbers"]
    )
    return f"{gate}({scored} vs {governing['bar_pct']}%)"
