"""One competition may not take the whole rail (#3872).

A league page's LIVE & UPCOMING rail is eight slots ordered live-first, then
soonest-first (`event_rails.live_first_order`). That order is correct and this
module does not replace it. What it fixes is the case where one competition
inside a league answers that order so completely that nothing else in the
league can be seen at all.

MEASURED, production, 2026-09-08 08:1x-08:3xZ, `/sport/tennis/atp` during the
US Open men's semi-finals. The rail's own candidate window held:

    feeder-circuit rows (Challenger/ITF)   12 live, 82 scheduled
    everything else                         0 live, 15 scheduled

Twelve Challenger matches at Phan Thiet and Shanghai were on court, so
live-first handed them all eight slots, and the fifteen rows a reader had come
for -- Tiafoe-Michelsen, six US Open doubles, Shelton-Alcaraz, Zverev,
Khachanov -- got none. Nothing was broken: the Challengers genuinely started at
06:00Z and the Slam at 17:00Z+. It is the RULE that is wrong, and it is the
same sentence `is_tennis_feeder_circuit` already carries for the hub rail
(#3640): a clock is not a reason to bury the tournament during the tournament.

── why an EQUAL SHARE and not a cap ──

The obvious fix is a constant -- "at most N Challenger rows". Three separate
values were checked against the measured population and every one of them
still missed Shelton-Alcaraz, because behind the twelve Challengers sat six US
Open DOUBLES matches all stamped 18:00Z, which then took every slot the cap
freed. A cap tuned until one specimen appears is tuned to one day.

So the rule carries no tuned number. Each competition in play may take up to an
EQUAL SHARE of the rail, `limit // competitions`, and the remainder is
backfilled in the rail's own order so no slot is ever lost.

🔴 **WHAT COUNTS AS ONE COMPETITION IS THE CALLER'S ANSWER, NOT THIS MODULE'S,
AND IT IS THE HALF THAT DECIDES THE OUTCOME.** Keyed on the venue's raw string,
the Challenger circuit is not thinned by the share -- it is SUBDIVIDED. That
window held SEVEN separate Challenger draws, so the share is 8 // 9 = 0 -> 1 and
the circuit takes seven of the eight slots one draw at a time; replayed on the
real rows it seats Bax-Jones, Ymer-Kotov, Tobon-Kirci, Added-Masur, Kolar-Wallin,
Seyboth Wild-Ferrari, Sanchez Jover-Bueno and Tiafoe, and still no
Shelton-Alcaraz. One match from each of seven feeder tournaments is not an
improvement on seven from one; it is the same rail with more logos.

`league_futures` therefore folds every match its venue names as feeder-circuit
play into one group before calling this, using `is_tennis_feeder_circuit` --
#3640's own predicate, already measured on this population. Folded, the
measured rail is 3 groups and a share of 2: two live Challengers,
Tiafoe-Michelsen, two US Open doubles, Shelton-Alcaraz, Zverev and Khachanov.

🔴 **PROVABLY INERT WHERE THE VOCABULARY IS THIN, AND THAT IS WHY `C <= 1`
RETURNS EARLY RATHER THAN COMPUTING A SHARE OF EIGHT.** The venue-stated
`competition` field is rich for tennis and degenerate elsewhere -- measured
across every league's rail window on the same pass:

    tennis_atp          105 events, 105 with a competition, 9 distinct
    tennis_wta           17            17                   4
    americanfootball_ncaaf  93         61                   1
    baseball_mlb        104            49                   1
    americanfootball_nfl 32            32                   1
    every soccer league  ~500           0                   0

MLB and NCAAF name ONE competition and leave half their rows unnamed. A rule
that thinned the named group there would promote unnamed rows over named ones
for no product reason, on pages nobody has complained about. With one
competition there is no share to take, so those rails are returned untouched by
identity -- not by a caller remembering to opt out.

The caller opts in per domain anyway (`league_futures`, following #3640's
`_UNDERCARD_CLASSIFIERS`), because inert-by-identity is a property of today's
data and the opt-in is a property of the decision.
"""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


def equal_share_by_competition(
    rows: Sequence[T],
    *,
    limit: int,
    competition_of: Callable[[T], str | None],
) -> list[T]:
    """Take ``limit`` rows from ``rows``, letting no competition monopolise them.

    ``rows`` arrives in the rail's own order and the result stays in it -- this
    only decides WHICH rows, never where they sit, so a genuinely live match
    still leads the rail exactly as `live_first_order` put it.

    ``competition_of`` returns the venue's own name for the competition a row
    belongs to, or ``None`` when no venue stated one.

    🔴 **An unnamed row is never held back.** `None` is not a group -- it is the
    absence of evidence, and every one of those rows keeps its natural slot.
    Sharing them out would mean inventing the very grouping the venue declined
    to state, which is the failure `is_tennis_feeder_circuit` refuses in its own
    docstring ("a tour we cannot read as a feeder circuit is simply not one").

    🔴 **No slot is ever lost to the share.** Rows held back by it are
    backfilled, in the rail's order, until the rail is full. A window that holds
    nothing but one competition therefore returns that competition's first
    ``limit`` rows -- the pre-#3872 answer, unchanged -- which is what keeps a
    diversity cap from emptying the surface it was meant to diversify
    (gotcha #43, and #1091's lesson before it).
    """
    if limit <= 0:
        return []

    named = {c for r in rows if (c := competition_of(r)) is not None}
    # Nothing to share out. Returned by identity of the rule and not by a
    # caller's opt-out, so a league whose venue names one competition -- MLB,
    # NFL, NCAAF -- can never be reshaped by this module. See the header.
    #
    # 🔴 The ZERO half is load-bearing and the ONE half is belt-and-braces, and
    # they are written as one branch because a reader should not have to work
    # that out. At zero the share below would divide by it: every soccer league
    # names no competition at all, so that is the common path and not a corner.
    # At one, `limit // 1` is `limit` and the walk already returns `rows[:limit]`
    # unchanged -- the branch states the guarantee the arithmetic happens to
    # keep, so that a future change to how the share is computed cannot quietly
    # take it away from MLB. A mutant that widens `<= 1` to `<= 0` therefore
    # survives ON PURPOSE; one that removes the branch outright does not.
    if len(named) <= 1:
        return list(rows[:limit])

    share = max(1, limit // len(named))

    taken: list[T] = []
    held: list[T] = []
    counts: dict[str, int] = {}
    for row in rows:
        if len(taken) >= limit:
            break
        competition = competition_of(row)
        if competition is None:
            taken.append(row)
            continue
        if counts.get(competition, 0) >= share:
            held.append(row)
            continue
        counts[competition] = counts.get(competition, 0) + 1
        taken.append(row)

    # The rail is a promise of `limit` rows, not of the share. Anything the
    # share held back comes back in the rail's own order until it is full.
    if len(taken) < limit:
        chosen = {id(r) for r in taken}
        for row in [*held, *rows]:
            if len(taken) >= limit:
                break
            if id(row) not in chosen:
                chosen.add(id(row))
                taken.append(row)

    # Back into the rail's order. The walk above preserves it for everything it
    # took in one pass, but a backfilled row was passed over earlier and would
    # otherwise be pinned to the end.
    position = {id(r): i for i, r in enumerate(rows)}
    taken.sort(key=lambda r: position[id(r)])
    return taken
