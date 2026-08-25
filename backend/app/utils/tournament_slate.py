"""Build the daily slate — "the script vs the divergence" (UX-P132, charter layer 2).

The boards answer *who wins the tournament*.  The slate answers *what is on
today*, and it is the half of the page that actually has live prices: the
outright fields have been dark for 8-32 days (#2199) while the match markets
were captured minutes ago.

**The script vs the divergence.**  The SCRIPT is the opening price — what the
market expected when the match was first quoted.  The DIVERGENCE is where it
has moved since.  A row is only interesting because those two differ, so both
travel together and the move is computed from the same normalized basis as the
number displayed beside it.  Computing the delta on raw prices and displaying
normalized ones would produce a row whose "+4.2" does not equal the difference
between its own two numbers.

Three things this module refuses to do:

1. **Print ``Yes``/``No``.**  Every side is looked up through the register's
   ``sides`` map, ``entity_key -> outcome_id``, pinned offline from the source's
   own ordered labels.  There is no name parsing here and no positional
   assumption; an unmapped side yields no row rather than a guess.

2. **Present an incoherent pair as a clean split.**  Two-outcome match quotes
   are independent binaries (gotcha #23): they are *quotes*, not a probability
   distribution, and nothing makes them sum to 1.  Measured 2026-08-25, all 162
   US Open qualification pairs summed to exactly 1.000 — but that is an
   observation about one moment, not a property, and the Cincinnati sample in
   the Day-1 census summed to 1.01.  So the sum is checked every time,
   normalized when it is close enough to be an overround, and REFUSED when it
   is not.  A 30-point disagreement normalized into a tidy 60/40 is a fabricated
   number wearing two players' names.

3. **Show a finished match as today's.**  Registration already excludes closed
   matches, but the register is a committed file and the clock keeps moving, so
   the same start-time bound is re-applied at serve time.  A register written
   this morning must not still be presenting this morning's matches at
   midnight.

Pure logic — every input is a plain dict, so the whole slate is testable
without a database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from app.utils.tournament_board import DARK_PRICE_HOURS, draw_label, price_state
from app.utils.tournament_register import TournamentRegister

logger = logging.getLogger(__name__)

#: How far a two-sided quote may sum from 1.0 and still be treated as one
#: question with an overround.  Beyond this the two sides are not describing the
#: same match closely enough for a split to mean anything.
#:
#: 12 points is wide enough to absorb every overround this class produces (the
#: measured worst case across the Day-1 census was 1 point) and narrow enough
#: that a genuinely broken pair — one side stale at 0.9 while the other moved to
#: 0.6 — is refused rather than laundered.
MAX_PAIR_DEVIATION = 0.12

#: A slate row disappears this long after its scheduled start.  Matches the
#: generator's exclusion window so the file and the serving path agree; if they
#: drifted, a match would be registered and then not shown, or shown after it
#: was meant to be dropped, with no single place to look.
MATCH_STALE_AFTER_HOURS = 6.0

#: A move smaller than this is noise, not a story. Same dead band as the board's
#: trend direction, so "moved" means one thing across the whole page.
MOVE_DEAD_BAND = 0.003


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def normalize_pair(
    a: Optional[float], b: Optional[float]
) -> tuple[Optional[float], Optional[float], Optional[float], bool]:
    """Two independent binary quotes -> one coherent pair.

    Returns ``(a_norm, b_norm, raw_sum, coherent)``.  When the pair cannot be
    made coherent both probabilities come back ``None`` — the caller must not
    fall back to the raw values, and there is nothing to fall back to.

    Not collapsed into "just renormalize": the *decision* is whether these two
    numbers are one question at all.  ``0.54 + 0.47`` is one question with a
    1-point overround.  ``0.90 + 0.60`` is two stale readings, and dividing them
    by 1.5 yields 60/40 — a number with no referent that looks exactly like a
    real one.
    """
    if a is None or b is None:
        return None, None, None, False
    if a < 0 or b < 0:
        return None, None, round(a + b, 6), False

    total = a + b
    if total <= 0:
        return None, None, round(total, 6), False
    if abs(total - 1.0) > MAX_PAIR_DEVIATION:
        return None, None, round(total, 6), False
    return round(a / total, 6), round(b / total, 6), round(total, 6), True


def _side_view(
    entity_key: str,
    player: dict[str, Any],
    loaded: dict[str, Any],
) -> dict[str, Any]:
    return {
        "entity_key": entity_key,
        "display_name": player.get("display_name") or entity_key,
        "seed": player.get("seed"),
        "country": player.get("country"),
        "role": player.get("role", "contender"),
        "probability": None,
        "opening_probability": None,
        "move": None,
        "raw_probability": _as_float(loaded.get("probability")),
        "raw_opening_probability": _as_float(loaded.get("opening_probability")),
        "observed_at": loaded.get("observed_at"),
    }


def build_slate(
    register: dict[str, Any],
    *,
    prices: dict[int, dict[str, Any]],
    now: datetime,
    max_stale_hours: float = MATCH_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Assemble the daily slate payload.

    ``prices`` is keyed by ``outcome_id`` and carries ``{"probability",
    "opening_probability", "observed_at"}``.  Keying on the outcome id the
    register pins — rather than on anything derived from a name at request time
    — is what makes the sides mapping load-bearing instead of decorative.
    """
    reg = TournamentRegister(register)
    cutoff = now - timedelta(hours=max_stale_hours)

    rows: list[dict[str, Any]] = []
    dropped: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for matchup in reg.matchups:
        players = matchup.get("players")
        if not isinstance(players, list) or len(players) != 2:
            drop("NOT_A_PAIR")
            continue

        scheduled = matchup.get("scheduled_date")
        started: Optional[datetime] = None
        if isinstance(scheduled, str) and scheduled:
            try:
                started = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
            except ValueError:
                started = None
        if started is None:
            drop("NO_SCHEDULED_START")
            continue
        if started < cutoff:
            # Registered when it was upcoming; it is not upcoming now. The
            # register is a file and the clock is not.
            drop("ALREADY_PLAYED")
            continue

        block = next(
            (
                b for b in (matchup.get("sources") or [])
                if isinstance(b, dict) and b.get("status") == "live"
            ),
            None,
        )
        if block is None:
            drop("NO_LIVE_SOURCE")
            continue

        sides_map = block.get("sides")
        if not isinstance(sides_map, dict) or set(sides_map) != set(players):
            drop("SIDES_UNMAPPED")
            continue

        views: list[dict[str, Any]] = []
        newest: Optional[datetime] = None
        for entity_key in players:
            player = reg.by_entity.get(entity_key)
            if player is None:
                break
            side = sides_map.get(entity_key) or {}
            outcome_id = side.get("outcome_id")
            loaded = prices.get(outcome_id) if isinstance(outcome_id, int) else None
            view = _side_view(entity_key, player, loaded or {})
            observed = (loaded or {}).get("observed_at")
            if isinstance(observed, datetime) and (newest is None or observed > newest):
                newest = observed
            views.append(view)
        if len(views) != 2:
            drop("PLAYER_NOT_REGISTERED")
            continue

        a_norm, b_norm, raw_sum, coherent = normalize_pair(
            views[0]["raw_probability"], views[1]["raw_probability"]
        )
        # The script is normalized on its OWN sum, not the current one — an
        # opening pair has its own overround, and mixing bases would make the
        # move an artifact of the two sums differing rather than of the market
        # moving.
        a_open, b_open, open_sum, open_coherent = normalize_pair(
            views[0]["raw_opening_probability"], views[1]["raw_opening_probability"]
        )

        if coherent:
            views[0]["probability"] = a_norm
            views[1]["probability"] = b_norm
        if open_coherent:
            views[0]["opening_probability"] = a_open
            views[1]["opening_probability"] = b_open
        if coherent and open_coherent:
            for view in views:
                view["move"] = round(
                    view["probability"] - view["opening_probability"], 6
                )

        age = (now - newest).total_seconds() / 3600.0 if newest else None
        state = price_state(age)

        favourite = None
        if coherent:
            favourite = (
                views[0]["entity_key"]
                if (views[0]["probability"] or 0) >= (views[1]["probability"] or 0)
                else views[1]["entity_key"]
            )

        moves = [v["move"] for v in views if v["move"] is not None]
        rows.append({
            "matchup_key": matchup.get("matchup_key"),
            "draw": matchup.get("draw"),
            "draw_label": draw_label(str(matchup.get("draw") or "")),
            "round": matchup.get("round"),
            "scheduled_date": started.isoformat(),
            "sides": views,
            # The honesty fields. A client that ignores every one of them still
            # cannot render a confident number, because `probability` is None
            # whenever the pair is incoherent.
            "coherent": coherent,
            "raw_sum": raw_sum,
            "opening_raw_sum": open_sum,
            "probability_is_live": state == "live" and coherent,
            "price_state": state,
            "observed_at": newest.isoformat() if newest else None,
            "age_hours": round(age, 2) if age is not None else None,
            "favourite": favourite,
            "has_moved": any(abs(m) > MOVE_DEAD_BAND for m in moves),
            "source_count": 1,
        })

    rows.sort(key=lambda r: (r["scheduled_date"], r["matchup_key"] or ""))

    observed_times = [
        datetime.fromisoformat(r["observed_at"]) for r in rows if r.get("observed_at")
    ]
    newest_overall = max(observed_times) if observed_times else None
    slate_age = (
        (now - newest_overall).total_seconds() / 3600.0 if newest_overall else None
    )

    if dropped:
        # Never a silent truncation. A short slate must be explainable.
        logger.info(
            "tournament slate for %s-%s dropped %s matchups: %s",
            reg.tournament, reg.season, sum(dropped.values()), dropped,
        )

    return {
        "matches": rows,
        "count": len(rows),
        "incoherent": sum(1 for r in rows if not r["coherent"]),
        "dropped": dict(sorted(dropped.items())),
        "price_state": price_state(slate_age),
        "newest_observed_at": newest_overall.isoformat() if newest_overall else None,
        "age_hours": round(slate_age, 2) if slate_age is not None else None,
        "dark_after_hours": DARK_PRICE_HOURS,
    }


def build_props(
    register: dict[str, Any],
    *,
    prices: dict[int, dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """The curated props & futures section (UX-P132, Alex's item 5).

    Reads only what the register curated.  There is no discovery step and no
    "everything else about this tournament" query, which is what keeps
    "curated, not a dump" true as the tournament grows — the interestingness
    bar is applied once, by the agent, when the register is written.

    A prop whose outcomes are all unpriced still renders: knowing the question
    is being asked is worth something, and an empty probability is honest where
    an invented one is not.
    """
    out: list[dict[str, Any]] = []
    for prop in TournamentRegister(register).props:
        views: list[dict[str, Any]] = []
        newest: Optional[datetime] = None

        for outcome in prop.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            loaded = prices.get(outcome.get("outcome_id")) or {}
            probability = _as_float(loaded.get("probability"))
            observed = loaded.get("observed_at")
            if isinstance(observed, datetime) and (newest is None or observed > newest):
                newest = observed
            views.append({
                "entity_key": outcome.get("entity_key"),
                "display_name": outcome.get("display_name"),
                "probability": round(probability, 6) if probability is not None else None,
                # Filled below, once the section's freshness is known. A
                # per-outcome flag that disagreed with the section's banner
                # would be the page contradicting itself.
                "probability_is_live": False,
            })

        age = (now - newest).total_seconds() / 3600.0 if newest else None
        state = price_state(age)
        for view in views:
            view["probability_is_live"] = state == "live" and view["probability"] is not None

        out.append({
            "key": prop.get("key"),
            "title": prop.get("title"),
            "hook": prop.get("hook"),
            "draw": prop.get("draw"),
            "source": prop.get("source"),
            "outcomes": views,
            "price_state": state,
            "observed_at": newest.isoformat() if newest else None,
            "age_hours": round(age, 2) if age is not None else None,
        })
    return out
