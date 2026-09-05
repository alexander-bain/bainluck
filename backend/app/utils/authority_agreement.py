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

from dataclasses import dataclass, field
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

#: Why a sport's `schedule` bucket is refused rather than counted.
#:
#: Tennis is an EXISTENCE authority and not a TIME authority, and the two are not
#: degrees of the same thing. StatPal stamps `15:00` UTC on unplayed tennis as a
#: session placeholder — 66 of 70 fixtures on the measured day — and backfills the
#: real minute only after the match is played; we carry our own midnight-UTC
#: placeholder on unlinked rows. Every paired fixture would therefore land in
#: `wrong_day`, and the row would publish a four-figure disagreement count about a
#: field neither side has committed to.
#:
#: `governs: False` is not enough on its own. It is already true of every
#: schedule bucket, and it says the number does not gate a flip — not that the
#: number is manufactured. A published count is read.
SCHEDULE_NOT_SCORED = (
    "not scored: this source is an EXISTENCE authority for this sport, not a "
    "TIME authority. StatPal stamps a 15:00 UTC session placeholder on unplayed "
    "tennis and backfills the real minute after the match, and our unlinked rows "
    "carry a midnight-UTC placeholder, so a clock comparison here measures two "
    "placeholders rather than a disagreement. The identity join uses the clock "
    "only to choose WHICH of two admissible pairings to make, never whether to "
    "make one."
)

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
    "tennis_singles": "link_tennis_statpal_fixtures",
    "tennis_doubles": "link_tennis_statpal_fixtures",
}

#: The keys above that are MEASUREMENT POPULATIONS rather than `sports.key`s.
#:
#: Every other key in `SHADOW_STAMPERS` is a real `sports.key` you could join
#: `events` on. These two are not, and the difference has to be loud, because a
#: reader who assumes otherwise writes `AUTHORITY_BY_SPORT["tennis_singles"]` and
#: flips nothing at all — our tennis rows live under `tennis_atp`,
#: `tennis_wta`, `tennis_other` and one key per tournament, 42 of them measured
#: on production 2026-09-05.
#:
#: Two facts force the split, and they pull in opposite directions:
#:
#:   * **Our 42 keys are ONE StatPal id space.** StatPal numbers every tennis
#:     match in a single sequence and serves them from one endpoint family, which
#:     is why `provider_anchor_keys.statpal_id_space` folds every `tennis*` key to
#:     `tennis`. A row per `sports.key` would be 42 rows measuring one population.
#:   * **Singles and doubles are TWO populations and must never share a
#:     denominator.** Doubles outnumber singles better than 2:1 on a US Open day
#:     and `tennis_names_agree` refuses to match a doubles name to a singles one
#:     — correctly. Under one denominator every doubles fixture StatPal publishes
#:     lands in `statpal_only` and the row reports a large phantom gap that no
#:     amount of matching could ever close: spec rule 5's unreachable-by-design,
#:     manufactured by the shape of the denominator rather than by the data.
#:
#: So the honest unit is neither our key nor their space — it is the DRAW. Named
#: apart here so `test_a_measurement_population_is_never_a_sport_key` can assert
#: no flip switch, and no consumer of one, ever reads one of these as a sport.
MEASUREMENT_POPULATIONS: frozenset[str] = frozenset(
    {"tennis_singles", "tennis_doubles"}
)

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
#:   * ``baseball_mlb`` — MEASURED now, and the answer is that neither published
#:     number may govern it yet. Its `season-schedule` is a rolling ~17-day
#:     window (227 games) rather than a season, so it is neither NFL's case nor
#:     NBA's, and the split this ship added is what makes the reason sayable
#:     rather than a suspicion. Over the honest denominator (`measurement_bounds`,
#:     729 rows, production 2026-09-05) our inventory falls **507 before StatPal's
#:     first fixture, 222 inside its span, 0 beyond its last**:
#:
#:       - ``ours_covered_pct`` cannot govern MLB. At most 227 of 729 rows can
#:         match, so it is capped near 31% by StatPal's retention policy and not
#:         by any disagreement about a game. It could never reach 99.5% however
#:         perfect the matching became — spec rule 5's unreachable-by-design, and
#:         the reason to say so here rather than let seven daily rows say it.
#:       - the only candidate that could govern MLB is the same number measured
#:         INSIDE StatPal's span, which is what the pre-filtered row was already
#:         reporting under the wrong name: **157 of 222, 70.72%**. That is 29
#:         points below the bar, and #3093 (two of our rows for one game) is a
#:         known contributor of unmeasured size to the 65-game complement.
#:
#:     So MLB stays absent, and the blocker is now a number rather than a wait:
#:     re-measure the inside-span figure once #3093 is fixed. Proposing it as a
#:     governing number is a D63 amendment and Alex's, not this file's.
#:   * ``tennis_singles`` / ``tennis_doubles`` — MEASURED from today, and absent
#:     for a reason that no number can retire: **tennis has no D63 ruling at
#:     all.** D63 answered the question for NBA, NHL and NFL and was not asked
#:     about tennis, so there is nothing here to look up and a default would be
#:     this file inventing one. The row publishes both numbers and gates
#:     `PENDING-NO-GOVERNING-NUMBER`, exactly as MLB does, and the clock does not
#:     start — a streak counted against a question nobody has chosen is seven
#:     days of evidence for nothing.
#:
#:     Two further things must be true before tennis could be proposed, and
#:     neither is today:
#:
#:       - **Discovery.** The ingest parser reads 0 of 7 tennis fixtures on
#:         `statpal_tennis_daily_20260903.json` and 0 of 11 on the livescores
#:         fixture, because tennis's `scores.tournament` is a LIST of draws while
#:         `_extract_match_items` guards `isinstance(tournament, dict)` (#3193).
#:         A sport that discovers nothing can post seven perfect days and prove
#:         only that we agree about the matches we already had.
#:       - **Duplicates.** Over the last 120 days of singles, 1,811 player pairs
#:         appear twice within five days of each other — 1,170 of them under two
#:         different `sports.key`s (production 2026-09-05). Those are two of our
#:         rows for one match, not two matches; each one inflates `ours_only` by
#:         a row that agrees with nothing by construction. Same shape as #3093's
#:         contribution to MLB's in-span misses, and lane1's under D39/#2693.
#:
#:     Proposing a governing number for either population is a D63 amendment and
#:     Alex's, not this file's — and it needs those two fixed first, or the number
#:     it proposes is measuring them.
GOVERNING_IDENTITY_NUMBERS: dict[str, tuple[str, ...]] = {
    "americanfootball_nfl": ("pct", "ours_covered_pct"),
    "basketball_nba": ("ours_covered_pct",),
    "icehockey_nhl": ("ours_covered_pct",),
}

#: The FIVE states of the flip gate. Only one of them advances a streak, and the
#: other four are distinct facts that a two-state gate would have blurred:
#:
#:   * ``MEETS``    — measured, over a real denominator, at or above the bar.
#:     Advances the streak.
#:   * ``BELOW``    — measured, under the bar. Resets it.
#:   * ``NO-SCORE`` — the read succeeded but there was nothing to divide by, so
#:     `_pct` returned `None`. Carries the streak unchanged, exactly as
#:     `READ-FAILED` does (spec rule 6). Collapsing this into `BELOW` would
#:     reset a streak on a day nobody disagreed about anything — gotcha #53's
#:     class, and the reason `_pct` refuses to return `0.0` in the first place.
#:   * ``TOO-FEW-TO-SCORE`` — there WAS something to divide by and it was not a
#:     measurement. See `MINIMUM_SCORED_DENOMINATOR`. Carries the streak: a day
#:     with one game on it is not a day anybody disagreed.
#:   * ``PENDING-NO-GOVERNING-NUMBER`` — the sport has not been told which of
#:     its two numbers decides. Nothing to advance, nothing to reset.
#:
#: The last three are all "not advancing" and are still not the same thing: a
#: quiet day, a day too small to read, and an unanswered question. Only one of
#: them is fixed by a ruling.
GATE_MEETS = "MEETS"
GATE_BELOW = "BELOW"
GATE_NO_SCORE = "NO-SCORE"
GATE_TOO_FEW = "TOO-FEW-TO-SCORE"
GATE_PENDING = "PENDING-NO-GOVERNING-NUMBER"

#: The gate states that leave a seven-day streak exactly as it was. Published as
#: a set rather than re-derived by each reader: whether a state pauses or resets
#: a streak is a spec decision, not a rendering detail.
GATES_CARRY_STREAK = frozenset({GATE_NO_SCORE, GATE_TOO_FEW, GATE_PENDING})

#: The smallest denominator a percentage may be scored on and still reach
#: `MEETS`.
#:
#: **This is not the answer to #3071.** Question A — what the minimum denominator
#: for a flip should actually be — is Alex's and is unruled. This is the floor
#: that EVERY candidate answer to it contains: a ratio over a single game is
#: 100% or 0% and nothing else, so it cannot distinguish "we agree about every
#: game" from "there was one game and we happened to have it". Refusing that one
#: case commits to nothing Alex has not already implied by asking the question.
#:
#: What it deliberately does NOT do is guess the real floor. NBA reads 41/41 and
#: NHL 32/32 today; both clear this and both may well be under whatever Alex
#: rules. So the governing block publishes `minimum_denominator` beside the
#: numbers AND `minimum_denominator_ruling`, which says the real one is open —
#: D55's rule that a gap tags loudly rather than passing silently. A reader who
#: sees `MEETS` on 41 games is told, on the row, that 41 has not been blessed.
MINIMUM_SCORED_DENOMINATOR = 2

#: Open question the floor above is standing in for, named on every row.
MINIMUM_DENOMINATOR_RULING = (
    "#3071 (Question A) is open: the minimum denominator for a flip is unruled. "
    f"{MINIMUM_SCORED_DENOMINATOR} is not that answer — it is the floor every "
    "candidate answer contains, because a ratio over one game can only be 100% "
    "or 0%. Read `denominators` before reading a percentage."
)

#: How each governing identity number's denominator is rebuilt from the counts
#: the row already publishes.
#:
#: Derived from `both`/`statpal_only`/`ours_only` rather than passed in, for the
#: same reason `governing` is assembled from the row's own numbers: a denominator
#: computed by a second path can disagree with the percentage printed beside it.
#: A name with no entry here scores nothing rather than defaulting — see
#: `governing_identity`, and `test_every_governing_number_can_say_its_denominator`
#: which fails if a number is added to `GOVERNING_IDENTITY_NUMBERS` without one.
IDENTITY_DENOMINATORS: dict[str, Callable[[dict[str, Any]], int]] = {
    # The union of both sides.
    "pct": lambda i: int(i["both"]) + int(i["statpal_only"]) + int(i["ours_only"]),
    # The games WE list.
    "ours_covered_pct": lambda i: int(i["both"]) + int(i["ours_only"]),
}

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
#: So this says the four things a reader needs before they look at a number:
#: which question decides is PER SPORT, the verdict is already computed on the
#: row, every percentage carries the denominator it was scored on, and there are
#: five gate states rather than pass/fail.
FLIP_GATE_SUMMARY = (
    # The 7 is a literal here and `authority_streak.REQUIRED_STREAK_DAYS`
    # elsewhere, because that module imports THIS one and the constant cannot
    # live upstream of its own owner without a cycle. They are pinned together
    # by `test_the_summary_and_the_streak_counter_agree_on_seven`.
    f"D50: a flip needs 7 consecutive daily rows clearing "
    f"{FLIP_BAR_PCT}%, plus a YOUR-TURN entry Alex has seen. Identity governs; "
    "schedule and anchors are reported and gate nothing. WHICH of identity's "
    "two numbers scores a sport is per sport (D63), so do not compare a "
    "percentage to the bar yourself — read the verdict off that sport's "
    "`identity.governing`, which names the number(s), their values, the "
    "denominator each was scored on and the bar it used. Five gate states: "
    f"`{GATE_MEETS}` advances the streak, `{GATE_BELOW}` resets it, and "
    f"`{GATE_NO_SCORE}` (nothing to divide by), `{GATE_TOO_FEW}` (a denominator "
    f"under {MINIMUM_SCORED_DENOMINATOR}, which is a floor and not #3071's "
    f"unruled answer) and `{GATE_PENDING}` (the sport has not been told which "
    "number decides) all carry it unchanged."
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

    Every number is published WITH the denominator it was scored on, and a
    denominator too small to be a measurement cannot reach `MEETS`. A percentage
    with no denominator beside it is the failure this lane has now found three
    times in three different shapes: 100% over 41 games and 100% over 1 game read
    identically on the ledger line, and only one of them is seven days from
    flipping a sport's source of record.
    """
    base = {
        "bar_pct": FLIP_BAR_PCT,
        "minimum_denominator": MINIMUM_SCORED_DENOMINATOR,
        "minimum_denominator_ruling": MINIMUM_DENOMINATOR_RULING,
    }
    names = GOVERNING_IDENTITY_NUMBERS.get(sport_key)
    if not names:
        return {
            **base,
            "numbers": [],
            "values": {},
            "denominators": {},
            "gate": GATE_PENDING,
            "why": (
                f"{sport_key} has no governing identity number, so no daily row "
                "can advance its streak. Both numbers are still published below; "
                "what is missing is the ruling on which one decides."
            ),
        }
    values = {name: identity[name] for name in names}
    denominators = {name: _denominator_of(name, identity) for name in names}
    block = {
        **base,
        "numbers": list(names),
        "values": values,
        "denominators": denominators,
    }
    # `None` is not a low score, it is the absence of one, and it must reach the
    # gate as its own state rather than being compared against the bar. A single
    # unscored number makes the whole verdict NO-SCORE: a sport does not half
    # clear a bar. A number whose denominator cannot be named lands here too —
    # "we cannot say what this was divided by" is not a score either, and
    # defaulting it to a denominator would be the silent pass D55 forbids.
    unscored = sorted(
        name for name in names if values[name] is None or denominators[name] is None
    )
    if unscored:
        return {
            **block,
            "gate": GATE_NO_SCORE,
            "why": (
                f"{', '.join(unscored)} has no denominator to divide by, so this "
                "day scores nothing and carries the streak unchanged (spec rule 6)"
            ),
        }
    # Checked BEFORE the bar, not after: a 1-game day is at 100% and would
    # otherwise be the strongest-looking row of the seven.
    too_few = sorted(
        name for name in names if denominators[name] < MINIMUM_SCORED_DENOMINATOR
    )
    if too_few:
        return {
            **block,
            "gate": GATE_TOO_FEW,
            "why": (
                f"{', '.join(too_few)} scored over fewer than "
                f"{MINIMUM_SCORED_DENOMINATOR} games, which is not a measurement "
                f"of agreement; the streak carries unchanged. "
                f"{MINIMUM_DENOMINATOR_RULING}"
            ),
        }
    below = sorted(name for name, value in values.items() if value < FLIP_BAR_PCT)
    return {
        **block,
        "gate": GATE_BELOW if below else GATE_MEETS,
        "why": (
            f"{', '.join(below)} below {FLIP_BAR_PCT}%"
            if below
            else f"all governing numbers at or above {FLIP_BAR_PCT}% over "
            + ", ".join(f"{denominators[n]} games ({n})" for n in names)
        ),
    }


def _denominator_of(name: str, identity: dict[str, Any]) -> Optional[int]:
    """What `name` was divided by, rebuilt from the row's own counts.

    `None` when the number has no entry in `IDENTITY_DENOMINATORS` — a governing
    number added without saying what it divides by scores nothing rather than
    being waved through on a guessed denominator.
    """
    build = IDENTITY_DENOMINATORS.get(name)
    if build is None:
        return None
    try:
        return build(identity)
    except (KeyError, TypeError, ValueError):
        return None


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


@dataclass(frozen=True)
class Join:
    """Which fixtures are which rows, and everything the join could not place.

    The return of a *join strategy* — the one part of a row that is sport-shaped.
    Everything else `build_agreement_row` does (the identity block, the horizon
    splits, the governing verdict, the receipts) is arithmetic over this and is
    shared by every sport, which is the point: two sports may disagree about what
    "the same game" means and must not disagree about what a row says.

    `fixtures` and `rows` are the USABLE sides, already stripped of
    `unusable_*` — published back because the horizon splits are measured
    against the span of the other side's usable list, and a strategy that drops
    a row without saying so would move a denominator silently.
    """

    fixtures: list[Side]
    rows: list[Side]
    paired: list[tuple[Side, Side]]
    statpal_only: list[Side]
    ours_only: list[Side]
    unusable_fixtures: list[Side]
    unusable_rows: list[Side]
    #: Exclusions a strategy makes that the default does not, each under its own
    #: name. Counted into `excluded` and receipted under the same key.
    #:
    #: This exists so a strategy can refuse without lying. Tennis's resolver can
    #: answer AMBIGUOUS — "two of our rows could be this match and I will not
    #: choose" — which is neither agreement nor disagreement. Dropping it into
    #: `statpal_only` would publish it as *"StatPal has a match we do not"*,
    #: which is the opposite of what happened, and is spec rule 5's failure:
    #: an exclusion that quietly moves the governing number.
    refusals: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


#: The signature every join strategy has. `normalize` is the default strategy's
#: and is accepted (and ignored) by the others so that `build_agreement_row` has
#: one call shape rather than a branch.
JoinStrategy = Callable[
    [Sequence[Side], Sequence[Side], Callable[[Optional[str]], str]], Join
]


def pair_by_normalized_key(
    fixtures: Sequence[Side],
    rows: Sequence[Side],
    normalize: Callable[[Optional[str]], str],
) -> Join:
    """The default join: equal normalised `(away, home)` pair, nearest kickoff.

    Lifted out of `build_agreement_row` unchanged when tennis needed a different
    one, and unchanged is the operative word: NFL, NBA and NHL have seven-day
    clocks running on numbers this function produces, and a refactor that moved
    one of them by a game would restart three clocks to tidy a signature.
    `test_the_default_join_is_the_same_join_it_always_was` pins that.

    It is a KEY join, and that is exactly why tennis cannot use it. A key groups
    by equality, and equality is transitive; tennis's identity relation is not,
    because `keys_agree` reads a missing given name as UNKNOWN rather than as a
    difference (a third of our field has no given name at all). `Garcia` and
    `Garcia Garcia` are both reachable from `G. Garcia` and are not each other,
    so no key can hold them — group by one and the census goes blind exactly
    where the matcher is tolerant.
    """
    usable_f = [f for f in fixtures if _pair_key(f, normalize) is not None]
    usable_r = [r for r in rows if _pair_key(r, normalize) is not None]

    by_key_f: dict[str, list[Side]] = {}
    for f in usable_f:
        by_key_f.setdefault(_pair_key(f, normalize), []).append(f)  # type: ignore[arg-type]
    by_key_r: dict[str, list[Side]] = {}
    for r in usable_r:
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

    return Join(
        fixtures=usable_f,
        rows=usable_r,
        paired=paired,
        statpal_only=statpal_only,
        ours_only=ours_only,
        unusable_fixtures=[f for f in fixtures if _pair_key(f, normalize) is None],
        unusable_rows=[r for r in rows if _pair_key(r, normalize) is None],
    )


def pair_greedily(
    fixtures: Sequence[Side],
    rows: Sequence[Side],
    agree: Callable[[Side, Side], bool],
) -> tuple[list[tuple[Side, Side]], list[Side], list[Side]]:
    """Pair on an arbitrary agreement relation, nearest kickoff first.

    `_pair_within_key`'s algorithm over a relation instead of a bucket, for the
    strategies whose relation is not an equality and therefore has no bucket.
    The tie-break rule is the same and for the same reason: the kickoff decides
    WHICH of two admissible pairings is made and never whether one is made at
    all, so a disagreement about the clock is reported rather than lost.

    Untimed pairs are settled last, in arrival order, after every timed pairing —
    absence is not proximity.
    """
    timed: list[tuple[timedelta, int, int]] = []
    untimed: list[tuple[int, int]] = []
    for fi, f in enumerate(fixtures):
        for ri, r in enumerate(rows):
            if not agree(f, r):
                continue
            d = _delta(f, r)
            if d is None:
                untimed.append((fi, ri))
            else:
                timed.append((d, fi, ri))
    timed.sort(key=lambda c: (c[0], c[1], c[2]))

    used_f: set[int] = set()
    used_r: set[int] = set()
    paired: list[tuple[Side, Side]] = []
    for _d, fi, ri in timed:
        if fi in used_f or ri in used_r:
            continue
        used_f.add(fi)
        used_r.add(ri)
        paired.append((fixtures[fi], rows[ri]))
    for fi, ri in untimed:
        if fi in used_f or ri in used_r:
            continue
        used_f.add(fi)
        used_r.add(ri)
        paired.append((fixtures[fi], rows[ri]))

    spare_f = [f for i, f in enumerate(fixtures) if i not in used_f]
    spare_r = [r for i, r in enumerate(rows) if i not in used_r]
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
    pair_sides: Optional[JoinStrategy] = None,
    time_authority: bool = True,
) -> dict[str, Any]:
    """One sport's ledger row, from both sides of the same moment.

    `read_failures` is not decoration. If either endpoint refused, the row is
    `READ-FAILED` and carries no percentage: the spec pauses a streak on a
    failed read and resets it on a real disagreement, and a row that cannot tell
    those apart makes the seven-day count meaningless.

    `pair_sides` is the sport-shaped part — see :class:`Join`. Omitted, the
    default key join runs and every sport that had a row before this parameter
    existed still gets the identical one.

    `time_authority=False` says this provider's clock is not evidence, and the
    `schedule` bucket is then REFUSED rather than computed. It is not the same as
    `governs=False`, which every schedule bucket already carries: a reported
    bucket that gates nothing is still a published count of disagreements, and
    for a source that stamps a placeholder hour on unplayed fixtures that count
    is manufactured. Publishing "1,900 wrong_day" beside a note saying to ignore
    it is how a number nobody should read gets read anyway.
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

    join = (pair_sides or pair_by_normalized_key)(real_fixtures, rows, normalize)
    unusable_fixtures = join.unusable_fixtures
    unusable_rows = join.unusable_rows
    real_fixtures = join.fixtures
    real_rows = join.rows
    paired = join.paired
    statpal_only = join.statpal_only
    ours_only = join.ours_only

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
        if time_authority:
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
                # A strategy's own refusals, each under its own name. Merged into
                # `excluded` rather than published beside it so that spec rule 5's
                # promise — every row left out is named and counted in one place —
                # survives a strategy adding a reason the default never had.
                **{name: len(items) for name, items in join.refusals.items()},
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
            "schedule": (
                {
                    **schedule,
                    "scored": True,
                    "governs": False,
                    "within_is": f"kickoffs within {WITHIN}",
                    "wrong_day_is": f"kickoffs more than {WRONG_DAY} apart",
                }
                if time_authority
                else {
                    "scored": False,
                    "governs": False,
                    "why": SCHEDULE_NOT_SCORED,
                }
            ),
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
                **{
                    name: items[:RECEIPT_CAP]
                    for name, items in join.refusals.items()
                },
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
        # A refused schedule bucket renders as one token rather than as four
        # zeros. `0/0/0/0` is what a sport with no disagreements looks like, and
        # printing it for a sport whose clock was never compared would be the
        # strongest-looking field on the line.
        f"| schedule={_schedule_text(sched)} "
        f"| anchors={row['anchors']['anchored']} "
        f"| streak={streak} | {READ_OK}"
    )


def _schedule_text(schedule: dict[str, Any]) -> str:
    """`schedule=` as either the four counts or an explicit refusal.

    `scored` is read with a `False` default rather than a `True` one: a row
    banked before that key existed carries the four counts and nothing else, and
    defaulting it to unscored would render every historical row as NOT-SCORED.
    So the four counts are the fallback and the refusal is opt-in — but a row
    that has neither, which is a shape this module has never produced, renders as
    NOT-SCORED rather than raising in a ledger line.
    """
    if schedule.get("scored") is False:
        return "NOT-SCORED"
    try:
        return (
            f"{schedule['within']}/{schedule['off_by_hours']}"
            f"/{schedule['wrong_day']}/{schedule['time_missing']}"
        )
    except KeyError:
        return "NOT-SCORED"


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
    # `/n` is not decoration either. NBA's line has read `covers=100.0%` since
    # step 3, and 100% over 41 games and 100% over 1 game are the same six
    # characters on the ledger. The denominator is the difference between a
    # streak worth banking and one that says nothing, so it travels with the
    # number rather than three fields away in the JSON.
    denominators = governing.get("denominators") or {}
    scored = ",".join(
        f"{name}={governing['values'][name]}%/{denominators.get(name, '?')}"
        for name in governing["numbers"]
    )
    return f"{gate}({scored} vs {governing['bar_pct']}%)"
