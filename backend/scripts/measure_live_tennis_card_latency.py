"""Measure how long a live tennis card takes to move after the score changes.

live/057. The queue asked for "median seconds from a point ending to our card
moving, before and after". This is the instrument that answers it.

TWO OBSERVERS, ONE CLOCK
------------------------
* **A — the upstream.** ESPN's tennis scoreboard, the source our tennis state
  actually comes from (`_sync_tennis_from_espn`, `_sync_tournament_results`).
  Polled fast. Sets complete are counted from the per-set **linescores**, at
  the first instant ESPN will tell anyone. NOT from ``status.period``, which
  trails its own linescores — see :func:`completed_sets`.
* **B — the card.** ``GET /api/events/{id}``, the payload the event page
  renders.

Latency for one score change = (first instant B shows the new score)
minus (first instant A showed it). That deliberately excludes ESPN's own lag
from the real point: this measures the segment WE control, which is the
segment a cadence change moves. It is a floor on the user-visible number, not
the whole of it.

TWO GRAINS, MEASURED SEPARATELY (live/058)
------------------------------------------
The 057 run reported one median — **sets** — and beside it the number that made
the queue: ESPN published **78 game-level changes** in 45 minutes and the card
moved **9 times**, because the card had no field a game could land in.

#2746 built that field (``events.linescore``), so this instrument now times
BOTH grains off the same two observers and the same clock:

* **sets** — A: sets complete from ESPN's per-set linescores. B:
  ``home_score + away_score``. Unchanged from 057, so the two runs are
  comparable readings of the same quantity.
* **games** — A: the per-set game tuple, oriented home-first. B:
  ``linescore.sets``, the same tuple. See :func:`games_key`.

The games join reports ``card_carries_linescore``. A run against a deployment
without #2746 gets ``false`` and zero game pairs, which is the true reading —
never a fast median over an empty set (gotcha #53: a zero-yield sweep must be
loud).

WHY NOT STATPAL AS OBSERVER A: StatPal publishes tennis at 15s with point-level
`game_score`, but it writes nothing to a tennis row today (no live tennis event
sits on a sport key in ``STATPAL_SPORT_MAPPING``, and no tennis event carries a
``statpal_fixture_id``). An observer that cannot reach the card cannot bound
the card's latency.

RATE DISCIPLINE: the public API rate-limits around 60 req/min, and a cold-load
battery has measured itself into its own 429 before. One request per event per
``--card-interval`` plus one ESPN read per ``--espn-interval``; the default of
9 events at 20s is 27 req/min. Raise the interval before raising the event
count.

Usage::

    python3 scripts/measure_live_tennis_card_latency.py \
        --minutes 40 --out /tmp/before.json

Reads ``BAINLUCK_API`` from the environment (default: production).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard"
)
TOURS = ("atp", "wta")


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _get_json(url: str, timeout: float = 15.0) -> dict | None:
    # No custom User-Agent. ESPN's edge 403s a `Mozilla/5.0` or any bespoke
    # agent string from this network and serves urllib's default fine —
    # measured three ways before believing it. A header that costs the
    # observer its upstream is not worth the politeness.
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — an observer must not die on one read
        print(f"  ! fetch failed {url[:60]}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- observer A


def set_is_complete(a, b) -> bool:
    """Whether a per-set game pair is a finished set.

    6-4 and 7-5 are two clear games; 7-6 is a tiebreak and is one. 6-5 and 6-6
    are sets still being played and must not count — miscounting either way
    shifts every latency by a whole set.
    """
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return max(a, b) >= 6 and (abs(a - b) >= 2 or max(a, b) == 7)


def completed_sets(games: list) -> int | None:
    """Sets complete, from ESPN's per-set linescores — the card's own quantity.

    THIS, NOT ``status.period``. Measured 2026-09-03 over 9 paired transitions:
    ESPN's ``period`` trails its own linescores often enough that 3 of the 9
    latencies came out NEGATIVE — our card moved before the field said the set
    had. A ground truth that arrives after the thing it is timing cannot bound
    anything. The linescores are what our writer reads, so they are what the
    clock starts on.
    """
    if not games or len(games) != 2:
        return None
    left, right = games
    return sum(
        1 for i in range(min(len(left), len(right)))
        if set_is_complete(left[i], right[i])
    )


def _fold(name) -> str:
    """A name to its comparable letters — ``"A. Tabilo"`` -> ``atabilo``."""
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def orient_home_first(home_name: str, sides: list[dict]) -> list[dict] | None:
    """ESPN's two competitors in OUR home/away order, or ``None``.

    ═══ WHY THE GAMES JOIN NEEDS THIS AND THE SETS JOIN DOES NOT ═══

    The sets join keys on ``home_score + away_score``, a SUM, which is the same
    number whichever way round the two sides are. A games tuple is not: ``6-2``
    and ``2-6`` are different keys for one scoreboard, so an unoriented observer
    A would never match observer B and the games median would come back empty
    while looking like a measurement.

    Surname containment, not the anchor's full matcher — this is a script
    joining two reads of the SAME match (the anchor has already established
    they are the same match), so all it has to do is tell two players apart.
    ``None`` when it cannot: an unoriented pair is dropped rather than guessed,
    because a reversed key silently pairs nothing.
    """
    if len(sides) != 2:
        return None
    ours = _fold(str(home_name).split()[-1]) if str(home_name).strip() else ""
    if not ours:
        return None
    hits = [i for i in (0, 1) if ours and ours in _fold(sides[i].get("name"))]
    if len(hits) != 1:
        return None
    return [sides[hits[0]], sides[1 - hits[0]]]


def games_key(sides_home_first: list[dict]) -> str | None:
    """The whole scoreboard as one comparable string — ``6-2|7-6|4-1``.

    The KEY IS THE WHOLE BOARD, not the current set, and that is deliberate:
    keyed on the current set alone, ``4-1`` in set four collides with ``4-1`` in
    set two and the join would pair a game won at 20:40 with one won an hour
    earlier. A whole-board key can repeat only if a match un-plays a game.

    ``None`` when either side publishes no line — the changeover instant, and
    the first seconds of a match.
    """
    if len(sides_home_first) != 2:
        return None
    home = sides_home_first[0].get("games") or []
    away = sides_home_first[1].get("games") or []
    if not home or not away:
        return None
    width = max(len(home), len(away))
    cells = []
    for i in range(width):
        h = home[i] if i < len(home) else None
        a = away[i] if i < len(away) else None
        cells.append(f"{'?' if h is None else int(h)}-{'?' if a is None else int(a)}")
    return "|".join(cells)


def read_espn() -> dict[str, dict]:
    """Live competitions from ESPN's tennis scoreboards, keyed by competition id.

    Returns ``{espn_id: {"period": int, "sets": int, "detail": str,
    "games": [[...], [...]]}}`` for every competition ESPN reports as
    in-progress. ``sets`` is the field to time against; ``period`` is kept only
    so a run can show how far the two disagree.
    """
    out: dict[str, dict] = {}
    for tour in TOURS:
        payload = _get_json(ESPN_SCOREBOARD.format(tour=tour))
        if not payload:
            continue
        for event in payload.get("events") or []:
            for grouping in event.get("groupings") or []:
                for comp in grouping.get("competitions") or []:
                    status = (comp.get("status") or {})
                    kind = (status.get("type") or {})
                    if kind.get("state") != "in":
                        continue
                    games = [
                        [ls.get("value") for ls in (c.get("linescores") or [])]
                        for c in (comp.get("competitors") or [])
                    ]
                    out[str(comp.get("id"))] = {
                        "period": status.get("period"),
                        "sets": completed_sets(games),
                        "detail": kind.get("detail"),
                        "games": games,
                        # Named sides, so the games tuple can be oriented to
                        # OUR home before it is used as a join key.
                        "sides": [
                            {
                                "name": (c.get("athlete") or {}).get("displayName"),
                                "games": [
                                    ls.get("value")
                                    for ls in (c.get("linescores") or [])
                                ],
                            }
                            for c in (comp.get("competitors") or [])
                        ],
                    }
    return out


# ---------------------------------------------------------------- observer B


def read_card(api: str, event_id: int) -> dict | None:
    payload = _get_json(f"{api}/api/events/{event_id}")
    if payload is None:
        return None
    home, away = payload.get("home_score"), payload.get("away_score")
    linescore = payload.get("linescore")
    sets = (linescore or {}).get("sets") if isinstance(linescore, dict) else None
    return {
        "home_score": home,
        "away_score": away,
        "sets": (home or 0) + (away or 0),
        "status": payload.get("status"),
        # live/058: the card's own games tuple, already home-first, put through
        # the SAME key builder observer A uses. One function, two callers — two
        # spellings of "6-2|7-6" would join nothing and look like a slow card.
        "games_key": (
            games_key([
                {"games": [s.get("home") for s in sets]},
                {"games": [s.get("away") for s in sets]},
            ])
            if isinstance(sets, list) and sets
            else None
        ),
    }


# ------------------------------------------------------------------ the loop


def discover_events(api: str) -> list[dict]:
    """Live tennis events that carry the ESPN id the two observers join on."""
    payload = _get_json(f"{api}/api/events/live?limit=200") or {}
    events = payload if isinstance(payload, list) else payload.get("events") or []
    found = []
    for ev in events:
        sport = str(ev.get("sport") or "")
        espn_id = ((ev.get("espn") or {}).get("espn_id"))
        if sport.startswith("tennis") and espn_id:
            found.append({
                "event_id": ev["id"],
                "espn_id": str(espn_id),
                # OUR home player, carried from discovery so observer A can
                # orient ESPN's two competitors into the same order observer B
                # publishes them in. See `orient_home_first`.
                "home_team": ev.get("home_team"),
            })
    return found


def pair_transitions(
    espn_seen: dict[str, dict],
    card_seen: dict[int, dict],
    by_espn: dict[str, int],
    started: float,
    espn_interval: float,
    card_interval: float,
    key_field: str = "sets",
) -> list[dict]:
    """Join what the upstream showed to what the card showed, one set at a time.

    Both sides are keyed on the SAME quantity, and which quantity is
    ``key_field``'s only job — ``"sets"`` for the 057 reading (complete sets,
    from linescores upstream and ``home_score + away_score`` on the card) or
    ``"games"`` for live/058's (the whole per-set games tuple, home-first on
    both sides). Keying the two on the same value is what makes the subtraction
    mean anything; one function serves both so the two medians cannot come from
    two different pairing rules.

    A value first observed within the opening poll cycle is the state we WALKED
    IN ON, not a transition we watched happen. Pairing it would measure the
    order the two observers booted in, so it is dropped from both sides.
    """
    pairs: list[dict] = []
    for espn_id, totals in espn_seen.items():
        event_id = by_espn.get(espn_id)
        if event_id is None:
            continue
        for total, t_a in totals.items():
            t_b = card_seen.get(event_id, {}).get(total)
            if t_b is None:
                continue
            if (t_a - started < espn_interval * 1.5
                    or t_b - started < card_interval * 1.5):
                continue
            pairs.append({
                "event_id": event_id, "espn_id": espn_id,
                key_field: total,
                "espn_at": _iso(t_a), "card_at": _iso(t_b),
                "latency_s": round(t_b - t_a, 1),
            })
    return pairs


def summarize(pairs: list[dict]) -> dict:
    """Median/min/max over EVERY pair, sign included.

    Dropping the negatives would be selecting on the outcome — it lifts the
    median by discarding exactly the cases where the card was fast. The same
    nine 057 readings gave 144.1 s without them and 73.3 s with.
    """
    lat = sorted(p["latency_s"] for p in pairs)
    return {
        "n": len(pairs),
        "negative_pairs": sum(1 for x in lat if x < 0),
        "median_latency_s": round(statistics.median(lat), 1) if lat else None,
        "min_latency_s": lat[0] if lat else None,
        "max_latency_s": lat[-1] if lat else None,
    }


def run(api: str, events: list[dict], minutes: float,
        espn_interval: float, card_interval: float) -> dict:
    by_espn = {e["espn_id"]: e["event_id"] for e in events}
    started = _now()
    deadline = started + minutes * 60

    # espn_id -> period -> first instant ESPN showed it
    espn_seen: dict[str, dict[int, float]] = {}
    # event_id -> set total -> first instant the card showed it
    card_seen: dict[int, dict[int, float]] = {}
    espn_last: dict[str, int] = {}
    card_last: dict[int, int] = {}
    games_changes: list[float] = []
    espn_games_last: dict[str, str] = {}

    # live/058, the games grain: the same two observers, the same clock, keyed
    # on the whole per-set games tuple instead of the set total.
    home_by_espn = {e["espn_id"]: e.get("home_team") for e in events}
    espn_games_seen: dict[str, dict[str, float]] = {}
    card_games_seen: dict[int, dict[str, float]] = {}
    espn_games_key_last: dict[str, str] = {}
    card_games_key_last: dict[int, str] = {}
    # Did the payload ever carry a linescore at all? A run against a deployment
    # without #2746 must report zero game pairs AND say why, not print a fast
    # median over an empty set.
    card_linescore_reads = 0
    # Orientation is a real failure mode, not a formality: an unoriented event
    # contributes no game pairs however many games it plays.
    unoriented: set[str] = set()

    next_espn = started
    next_card = started
    polls = {"espn": 0, "card": 0}

    while _now() < deadline:
        now = _now()

        if now >= next_espn:
            next_espn = now + espn_interval
            polls["espn"] += 1
            for espn_id, state in read_espn().items():
                if espn_id not in by_espn:
                    continue
                sets_done = state.get("sets")
                if isinstance(sets_done, int):
                    seen = espn_seen.setdefault(espn_id, {})
                    if sets_done not in seen:
                        seen[sets_done] = now
                        if espn_last.get(espn_id) is not None:
                            print(f"  A set-end  {espn_id} sets->{sets_done} "
                                  f"(period {state.get('period')}) @ {_iso(now)}",
                                  flush=True)
                        espn_last[espn_id] = sets_done
                games = json.dumps(state.get("games"))
                if espn_games_last.get(espn_id) not in (None, games):
                    games_changes.append(now)
                espn_games_last[espn_id] = games

                oriented = orient_home_first(
                    home_by_espn.get(espn_id) or "", state.get("sides") or []
                )
                if oriented is None:
                    unoriented.add(espn_id)
                    continue
                key = games_key(oriented)
                if key is None:
                    continue
                seen_g = espn_games_seen.setdefault(espn_id, {})
                if key not in seen_g:
                    seen_g[key] = now
                    if espn_games_key_last.get(espn_id) is not None:
                        print(f"  A game     {espn_id} {key} @ {_iso(now)}",
                              flush=True)
                    espn_games_key_last[espn_id] = key

        if now >= next_card:
            next_card = now + card_interval
            for espn_id, event_id in by_espn.items():
                card = read_card(api, event_id)
                polls["card"] += 1
                if card is None:
                    continue
                total = card["sets"]
                seen = card_seen.setdefault(event_id, {})
                if total not in seen:
                    seen[total] = now
                    if card_last.get(event_id) is not None:
                        print(f"  B card     {event_id} sets->{total} @ {_iso(now)}",
                              flush=True)
                    card_last[event_id] = total

                key = card.get("games_key")
                if key is None:
                    continue
                card_linescore_reads += 1
                seen_g = card_games_seen.setdefault(event_id, {})
                if key not in seen_g:
                    seen_g[key] = now
                    if card_games_key_last.get(event_id) is not None:
                        print(f"  B games    {event_id} {key} @ {_iso(now)}",
                              flush=True)
                    card_games_key_last[event_id] = key

        time.sleep(1.0)

    set_pairs = pair_transitions(
        espn_seen, card_seen, by_espn, started, espn_interval, card_interval,
        key_field="sets",
    )
    game_pairs = pair_transitions(
        espn_games_seen, card_games_seen, by_espn, started,
        espn_interval, card_interval, key_field="games",
    )
    sets_summary = summarize(set_pairs)
    games_summary = summarize(game_pairs)
    return {
        "api": api,
        "started_at": _iso(started),
        "ended_at": _iso(_now()),
        "minutes": minutes,
        "espn_interval_s": espn_interval,
        "card_interval_s": card_interval,
        "events_watched": events,
        "polls": polls,
        # THE 057 NUMBER, unchanged in definition so the two runs compare.
        "espn_game_level_changes": len(games_changes),
        "set_transitions_observed": len(set_pairs),
        "pairs": set_pairs,
        **sets_summary,
        # live/058: the grain the queue is about.
        "games": {
            **games_summary,
            "pairs": game_pairs,
            # THE HONESTY FIELDS. `false` means this deployment does not serve
            # a linescore at all, so `n: 0` is a fact about the API and not
            # about the card's speed.
            "card_carries_linescore": card_linescore_reads > 0,
            "card_linescore_reads": card_linescore_reads,
            "unoriented_events": sorted(unoriented),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=float, default=40.0)
    ap.add_argument("--espn-interval", type=float, default=15.0)
    ap.add_argument("--card-interval", type=float, default=20.0)
    ap.add_argument("--out", default="/tmp/live057_latency.json")
    ap.add_argument("--api", default=os.environ.get(
        "BAINLUCK_API", "https://api.bainluck.com"))
    args = ap.parse_args()

    events = discover_events(args.api)
    if not events:
        print("no live tennis events carrying an espn_id — nothing to measure")
        return 2
    print(f"watching {len(events)} live tennis events for {args.minutes} min")
    for e in events:
        print(f"  event {e['event_id']} <-> espn {e['espn_id']}")

    result = run(args.api, events, args.minutes,
                 args.espn_interval, args.card_interval)
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("pairs", "events_watched")}, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
