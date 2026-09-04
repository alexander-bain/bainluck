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
  * ``identity`` — in both / StatPal-only / ours-only. The governing bucket.
  * ``schedule`` — within the window / off by hours / a different day. Reported,
    never merged into identity (spec rule 2: a blend buried five real findings
    inside twenty-four non-findings).
  * ``anchors`` — of the games both sides have, how many carry the id join the
    shadow stamper wrote. This is the number that says the join is usable; it is
    NOT the agreement number, and putting them in one ratio would mean a sport
    with no stamper yet reads as a disagreement.
  * ``excluded`` — every row left out, by name and count. An unstated exclusion
    is how a bar becomes unreachable by design (spec rule 5).

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
    starts = [r.start for r in rows if r.start is not None]
    if not starts:
        # No timed row on our side, so there is no span to be inside or outside
        # of. Reporting zeros here would claim the whole StatPal list falls in
        # our window, which is the opposite of what an empty table means.
        return {
            "before_our_first": 0,
            "inside_our_span": 0,
            "beyond_our_last": 0,
            "unplaceable": len(statpal_only),
        }

    first, last = min(starts), max(starts)
    split = {
        "before_our_first": 0,
        "inside_our_span": 0,
        "beyond_our_last": 0,
        "unplaceable": 0,
    }
    for f in statpal_only:
        if f.start is None:
            split["unplaceable"] += 1
        elif f.start < first:
            split["before_our_first"] += 1
        elif f.start > last:
            split["beyond_our_last"] += 1
        else:
            split["inside_our_span"] += 1
    return split


def build_agreement_row(
    *,
    sport_key: str,
    fixtures: Sequence[Side],
    rows: Sequence[Side],
    normalize: Callable[[Optional[str]], str],
    read_failures: Sequence[str] = (),
    sources_read: Sequence[str] = (),
    window: Optional[tuple[datetime, datetime]] = None,
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
            "identity": {
                "both": both,
                "statpal_only": len(statpal_only),
                "ours_only": len(ours_only),
                "pct": _pct(both, denominator),
                "governs": True,
                # Where the StatPal-only games fall against our own inventory.
                # Reported, never subtracted — see `_statpal_only_by_horizon`.
                "statpal_only_by_horizon": horizon,
                # "Of the games WE hold, how many does StatPal also have?"
                #
                # A DIFFERENT question from `pct`, and it does not govern. For a
                # sport where both sides carry the same population it is nearly
                # the same number (NFL: 99.69 against 99.38). For NBA and NHL,
                # where StatPal publishes a season and we ingest a rolling
                # odds-driven slice, it is 100.00 against 3.40 — and the gap
                # between the two IS the finding, which is why both are printed
                # and neither is blended into the other (spec rule 2).
                "ours_covered_pct": _pct(both, both + len(ours_only)),
            },
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
        f"| schedule={sched['within']}/{sched['off_by_hours']}/{sched['wrong_day']}"
        f"/{sched['time_missing']} "
        f"| anchors={row['anchors']['anchored']} "
        f"| streak={streak} | {READ_OK}"
    )
