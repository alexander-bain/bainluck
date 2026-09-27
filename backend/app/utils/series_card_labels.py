"""Reader labels for the event page's SERIES card (#9139).

── THE DEFECT, AS A READER HIT IT ───────────────────────────────────────────────

``/events/15319563`` (Red Sox @ Yankees, AL Wild Card Game 1) printed, at 390px::

    Series Winner: Boston vs New York Y
      New York Y   57%
      Boston       40%
    Series Total Games: Boston vs New York Y
      Yes          49%

Two defects on one card. "Yes" answers a question the page never asks, and
"New York Y" is not a club.

── "YES" IS THE TOP RUNG OF A LADDER, AND THE RUNG IS IN THE TICKER ────────────

Kalshi's ``…SERIESGAMES`` markets are a ladder of "at least N games" rungs, one
outcome per rung, with ticker suffix ``-N``. The lower rungs arrive with a
subtitle a reader can use (``…-5`` → ``Over 4.5 total games``), but the TOP rung
— the series going the distance — arrives as a bare ``Yes``
(``KXNBASERIESGAMES-26MINSASR2-7``). A best-of-3 has only that rung, so its whole
card was one bare ``Yes``. The number of games exists nowhere but the ticker.

So a bare ``Yes`` whose own outcome ticker is ``…SERIESGAMES-…-N`` is served as
``Over {N-0.5} total games`` — its siblings' own wording, so a seven-game ladder
reads as one vocabulary. Anything else that says ``Yes`` is left alone: without
the ticker there is no question to name, and a guessed one is worse than a bare
one.

── CLUB NAMES COME FROM EACH OUTCOME'S OWN TICKER ──────────────────────────────

``KXMLBSERIES-26BOSNYYWC-NYY`` names the club behind ``New York Y``;
:func:`game_market_club_names.repair_field_outcome_name` is the reader-side engine
for exactly this (id-anchored, and it refuses unless the shipped text agrees).
The titles carry the same truncation but no outcome of their own, so the repairs
the outcomes proved are applied to every title on the card — the card is one
matchup, so it gets one vocabulary. A shipped name two outcomes expand
differently is dropped, not resolved.

Names are rewritten IN PLACE: the web card and the iPhone ``RelatedFuturesView``
both print ``market_name`` and ``outcomes[].name``, and neither needs a change.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping, MutableMapping, Optional

from app.utils.game_market_club_names import repair_field_outcome_name
from app.utils.kalshi_display_names import apply_name_repairs

#: ``KXMLBSERIESGAMES-26BOSNYYWC-3`` → rung 3. Anchored on the series family so a
#: ``Yes`` from any other market (a Series Winner phrased as a question, a prop)
#: can never be relabelled as a games count.
_SERIES_GAMES_RUNG_RE = re.compile(r"SERIESGAMES-[A-Z0-9]+-(\d{1,2})$")


def series_games_rung_label(
    outcome_external_id: Optional[str], shipped_name: Optional[str]
) -> Optional[str]:
    """``("KXMLBSERIESGAMES-26BOSNYYWC-3", "Yes")`` → ``"Over 2.5 total games"``.

    ``None`` when the name should ship unchanged: it is not a bare ``Yes``, or
    its ticker is not a series-games rung.
    """
    if not outcome_external_id or (shipped_name or "").strip() != "Yes":
        return None
    match = _SERIES_GAMES_RUNG_RE.search(str(outcome_external_id).strip().upper())
    if not match:
        return None
    games = int(match.group(1))
    if games < 2:
        return None
    return f"Over {games - 0.5:g} total games"


def relabel_series_card(
    markets: Iterable[MutableMapping],
    ticker_by_outcome_id: Mapping[int, Optional[str]],
) -> int:
    """Rewrite one event's ``series_markets`` labels in place; return fields changed."""
    markets = [m for m in markets if isinstance(m, MutableMapping)]
    changed = 0
    repairs: dict[str, str] = {}
    contradicted: set[str] = set()

    for market in markets:
        for outcome in market.get("outcomes") or []:
            if not isinstance(outcome, MutableMapping):
                continue
            shipped = outcome.get("name")
            if not isinstance(shipped, str) or not shipped:
                continue
            ticker = ticker_by_outcome_id.get(outcome.get("outcome_id"))
            rung = series_games_rung_label(ticker, shipped)
            if rung:
                outcome["name"] = rung
                changed += 1
                continue
            full = repair_field_outcome_name(ticker, shipped)
            if not full:
                continue
            if shipped in repairs and repairs[shipped] != full:
                contradicted.add(shipped)
            repairs[shipped] = full

    for shipped in contradicted:
        repairs.pop(shipped, None)
    if not repairs:
        return changed

    for market in markets:
        title = market.get("market_name")
        if isinstance(title, str) and title:
            after = apply_name_repairs(title, repairs)
            if after != title:
                market["market_name"] = after
                changed += 1
        for outcome in market.get("outcomes") or []:
            if not isinstance(outcome, MutableMapping):
                continue
            before = outcome.get("name")
            if isinstance(before, str) and before:
                after = apply_name_repairs(before, repairs)
                if after != before:
                    outcome["name"] = after
                    changed += 1
    return changed


__all__ = ["relabel_series_card", "series_games_rung_label"]
