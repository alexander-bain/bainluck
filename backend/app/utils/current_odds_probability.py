"""What the `current_odds` object is allowed to serve as its probability (#7221).

═══ THE OBJECT CONTRADICTED ITSELF, IN ONE RESPONSE, AT ONE TIMESTAMP ═══

`current_odds` is the sportsbook object. Every other field in it — `spread`,
`over_under`, the projected scores, `bookmaker_count` and the `captured_at`
stamp — is computed from the snapshot rows the route just filtered. Its
probability was not: it was `compute_aggregate_probability`, whose **Tier 3
returns `opening_home_probability`** (#6694), so on an event with no weighted
source in its bag and no ESPN reading, the object served THE OPENING LINE under
a stamp saying the reading was seconds old.

Measured on production 2026-09-19 14:19:20Z, `GET /api/events/15314578`
(Uganda–Kenya, cricket, live since 11:30Z), one response:

    current_odds.home_probability   0.6414
    current_odds.captured_at        14:19:20.574177Z   <- seconds old
    current_odds.bookmaker_count    1
    bookmaker_odds[0]               fanduel 0.044 @ 14:19:20.574177Z

The one book the object counts, stamped at the very same microsecond, priced
the home side at 4.4% while the object beside it said 64.1%. The `/search`
card printed `Uganda 64% · Kenya 36%` under a green LIVE badge with
`Opened 64/36` directly beneath it — the live figure and the pre-match figure
were the same number, because they were the same number.

16 live events carried the signature at that minute (481 in a two-day window:
377 scheduled, 49 completed, 39 suspended, 16 live); nine of the sixteen were
more than five points from their own books' consensus, the worst 58.19.

═══ WHY THIS IS NOT "SERVE THE BOOKS" WITH THE FLOOR REMOVED ═══

🔴 RULING 051 IS NOT WEAKENED HERE AND MUST NOT BE. A one-book consensus is
kept OUT OF THE BLEND on purpose — `BETTING_BOOK_FLOOR` (3) exists because
#1841 printed 87-13 for a team trailing 0-5 — and this module does not put it
back in. `win_probability_sources`, `compute_aggregate_probability` and every
blend consumer are untouched: the blend still declines to speak, which is
correct. What changes is only what the SPORTSBOOK object reports when the blend
has declined — and an object that counts one book, stamps that book's capture
instant and then prints a number from three hours earlier is not protecting a
reader from a thin market, it is hiding a thin market behind a stale number.
The count travels with the number (`bookmaker_count: 1`), and both clients
already spend it: the web card captions the figure "Live · 1 sportsbook".

═══ IN-PLAY ONLY, AND THAT IS A SAFETY BOUNDARY, NOT A SCOPE DODGE ═══

The substitution fires on `status == "live"` and nowhere else, because that is
exactly where the route's own filter guarantees the substitute is worth
serving. `filter_stale_bookmaker_snapshots` runs its LAYER 2 recency pass —
drop any book whose last confirmation is more than ten minutes behind the
freshest one — only when `event_status == "live"`. So on a live event the
consensus reaching this function is confirmed since kickoff AND within ten
minutes of the newest quote; off it, it could be a pre-game row wearing a
current name, which is the #1841 hazard rather than the cure for it.

The other three states also need nothing:

* `scheduled` — `Event.opening_*` is still rewritten on every poll until the
  consensus freezes (#3922), so Tier 3 IS the current price there and the
  substitution would be a no-op with a blast radius of 377 rows.
* `completed` / `suspended` — the card reads `opening_odds` for these
  (`isFinishedStatus(status) && opening`, `EventCard`), captions it
  "Pre-match · sportsbooks", and is right to: settled means settled.

So this is a live-event truth fix, and the finished and pregame payloads are
byte-identical to what they are today.
"""

from typing import Optional

from app.utils.aggregation import TIER_OPENING

#: The one status whose snapshot consensus has passed the in-play recency
#: filter. See the module docstring — this is `filter_stale_bookmaker_snapshots`
#: layer 2's own condition, restated here so the two cannot drift silently.
_IN_PLAY = "live"


def current_odds_probability(
    blend: Optional[float],
    blend_tier: Optional[str],
    snapshot_consensus: Optional[float],
    event_status: Optional[str],
) -> Optional[float]:
    """The home probability the `current_odds` object may serve.

    ``blend`` / ``blend_tier`` are ``compute_aggregate_probability_tiered``'s
    pair. ``snapshot_consensus`` is ``aggregate_bookmaker_odds(...)``'s
    ``home_probability`` for the same event — the consensus of the very books
    this object counts and stamps.

    A Tier-1 or Tier-2 answer is a live, multi-source reading and is served
    unchanged; only a Tier-3 answer — which is the opening line and nothing
    else — steps aside, and only on an in-play event that has a consensus to
    step aside FOR. Every other combination returns exactly what the call site
    returned before this function existed, which is why the two call sites can
    share it without either surface moving on the shapes it already served.
    """
    if (
        event_status == _IN_PLAY
        and blend_tier == TIER_OPENING
        and snapshot_consensus is not None
    ):
        return snapshot_consensus
    return blend if blend is not None else snapshot_consensus
