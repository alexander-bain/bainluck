"""An open winner contract beside an immutable final game result (#9484).

Read only, from the game-market builder's loaded rows. The route supplies its
existing whole-match recognition and whole-market selection policy; this helper
does not introduce a second matcher, infer settlement from prices, or mutate the
event. Closed contracts travel separately so held clients can fence resurrection.

A quote that only repeats the recorded result (the scored winner's leg at or
above ``CERTAIN_LEG_PROBABILITY``) is withheld: the score already says it (Alex,
#9544). Lower-priced and disagreeing quotes still travel; nothing is rewritten.
"""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite
from typing import Callable, Iterable, Mapping

from app.utils.feed_market_quality import is_empty_book_midpoint
from app.utils.field_opening_coherence import CERTAIN_LEG_PROBABILITY
from app.utils.futures_unsupported_price import (
    price_refuted_by_live_book,
    row_carries_a_verdict,
)
from app.utils.latest_observation import blended_observed_at
from app.utils.market_shape import venue_leg_count
from app.utils.settledness import market_assigned_settled


def _positive_id(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _stamp(value: object) -> str | None:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _recorded_winner_side(home_score: object, away_score: object) -> str | None:
    """The scored winner, or None when the score cannot name one (missing, draw)."""
    scores = (home_score, away_score)
    if not all(type(score) is int and score >= 0 for score in scores) or home_score == away_score:
        return None
    return "home" if home_score > away_score else "away"


def final_game_winner_quotes(
    *,
    event_id: int,
    event_is_finished: bool,
    mapped_event_ids: Iterable[int],
    home_name: str | None,
    away_name: str | None,
    home_score: object,
    away_score: object,
    markets: Iterable[object],
    outcomes: Iterable[object],
    observed_at: Mapping[int, datetime],
    is_match_winner: Callable,
    winner_side: Callable,
    fold_winner_markets: Callable,
    resolve_outcome_name: Callable,
    normalize_probs: Callable,
) -> dict:
    """Return one complete quoted book and exact terminal winner-market IDs.

    ``mapped_event_ids`` must be the builder's proven folded event IDs, never its
    unlinked team-name/time fallback. All outcomes participate in recognition and
    settlement checks BEFORE any price filtering. One missing or refused leg
    withholds the whole quote; it does not remove that market from subscriptions.
    """
    empty = {"open_winner_quote": None, "closed_winner_market_ids": []}
    if not event_is_finished or _positive_id(event_id) is None:
        return empty
    mapped = {value for raw in mapped_event_ids if (value := _positive_id(raw))}
    if event_id not in mapped:
        return empty

    by_market: dict[int, list] = defaultdict(list)
    for outcome in outcomes:
        fields = vars(outcome)  # Already-loaded scalars only; no lazy queries.
        if _positive_id(fields.get("id")) and _positive_id(fields.get("market_id")):
            by_market[fields["market_id"]].append(outcome)

    candidates: list[dict] = []
    closed: set[int] = set()
    exclusive_by_market: dict[int, bool] = {}
    for market in markets:
        fields = vars(market)
        market_id = _positive_id(fields.get("id"))
        source = fields.get("source")
        if (market_id is None or fields.get("event_id") not in mapped
                or source not in {"kalshi", "polymarket"}):
            continue
        exclusive_by_market[market_id] = fields.get("mutually_exclusive") is True
        # An explicit contract closure survives missing/partial outcome rows.
        # These IDs only fence that same contract; absence alone never closes it.
        if fields.get("settled_at") is not None or market_assigned_settled(market, []):
            closed.add(market_id)
            continue
        legs = by_market.get(market_id, [])
        if not legs or len({leg.id for leg in legs}) != len(legs):
            continue
        # Name only an exact Yes/No pair, using the existing route resolver.
        # Never reinterpret a mixed parent containing props as a winner book.
        binary = sorted(vars(leg).get("name") or "" for leg in legs) == ["No", "Yes"]
        rows = [{
            "_market_id": market_id,
            "market_name": fields.get("name"),
            "outcome_id": leg.id,
            "outcome_name": resolve_outcome_name(leg.name, fields.get("name"))
            if binary else leg.name,
            "source": source,
        } for leg in legs]
        if not is_match_winner(rows, home_name, away_name):
            continue
        sides = [winner_side(row["outcome_name"], home_name, away_name) for row in rows]
        if (not {"home", "away"}.issubset(sides)
                or len(set(sides)) != len(sides)
                or not set(sides) <= {"home", "away", "draw"}):
            continue

        # Kalshi often leaves settled rows status=open. A loss/void with a
        # resolution_source is terminal too, even when no leg won. A retracted
        # grade (ungradeable_result) is not a verdict; the shared policy owns it.
        terminal = (
            fields.get("settled_at") is not None
            or market_assigned_settled(market, legs)
            or any(row_carries_a_verdict(vars(leg).get("resolution_source")) for leg in legs)
        )
        if terminal:
            closed.add(market_id)
            continue
        if fields.get("status") != "open":
            continue
        metadata = fields.get("market_metadata")
        declared = venue_leg_count(
            metadata if isinstance(metadata, dict) else {},
            fields.get("name"), fields.get("mutually_exclusive"),
        )
        if declared is not None and len(rows) < declared:
            continue

        valid_rows = []
        for row, side, leg in zip(rows, sides, legs):
            data = vars(leg)
            probability = _number(data.get("current_probability"))
            bid = _number(data.get("current_yes_bid"))
            ask = _number(data.get("current_yes_ask"))
            if (probability is None or not 0 <= probability <= 1
                    or is_empty_book_midpoint(probability, bid, ask)
                    or price_refuted_by_live_book(
                        source, data.get("resolution_source"), data.get("is_winner"),
                        probability, bid, ask,
                    )):
                break
            valid_rows.append({**row, "side": side, "probability": probability,
                               "observed_at": _stamp(observed_at.get(leg.id))})
        if len(valid_rows) == len(rows) and any(row["probability"] > 0 for row in valid_rows):
            candidates.extend(valid_rows)

    selected = fold_winner_markets(candidates, home_name, away_name)
    quote = None
    if selected:
        # The existing fold selects ONE whole book. Fail closed if that contract
        # ever changes; never combine unrelated venues into an invented blend.
        ids = {row["_market_id"] for row in selected}
        if len(ids) == 1:
            first = selected[0]
            oldest = blended_observed_at([row["observed_at"] for row in selected])
            # Use the existing #23 display policy, including its refusal bands.
            # A normalized sibling depends on the whole book, so its age is the
            # oldest real contributor (unknown stays unknown), not its own row.
            if normalize_probs(selected, mutually_exclusive=exclusive_by_market[first["_market_id"]],
                               field_complete=True):
                for row in selected:
                    row["observed_at"] = oldest
            names = {"home": home_name, "away": away_name, "draw": "Draw"}
            order = {"home": 0, "away": 1, "draw": 2}
            quote = {
                "event_id": event_id,
                "market_id": first["_market_id"],
                "market_name": first["market_name"],
                "source": first["source"],
                "status": "open",
                "observed_at": oldest,
                "outcomes": [{
                    "outcome_id": row["outcome_id"], "side": row["side"],
                    "name": names[row["side"]], "probability": row["probability"],
                    "observed_at": row["observed_at"],
                } for row in sorted(selected, key=lambda row: order[row["side"]])],
            }
            # Judged on the served (post-#23) number, the one a reader would see.
            recorded = _recorded_winner_side(home_score, away_score)
            if recorded and any(row["side"] == recorded
                                and row["probability"] >= CERTAIN_LEG_PROBABILITY
                                for row in quote["outcomes"]):
                quote = None
    return {"open_winner_quote": quote, "closed_winner_market_ids": sorted(closed)}
