"""Every settled row's ``prematch_odds`` in ONE read — the number its own page prints.

The event route (#8315, ``events._settled_prematch_odds``) prints a finished
game's pre-game chance off Alex's ladder — Kalshi → Polymarket → sportsbooks.
Every OTHER surface that lists finished games and states their pre-game number
has to state the same one, or a reader tapping from the list to the page
watches it change. The NFL week hub (#10273) was the second surface; the team
page's "we had them at N%" (#10589) is the third. Three copies of one read is
how a ladder drifts, so the batch form lives here, once.

NO SECOND LADDER: the same statement (``PREMATCH_PRIOR_SQL``, bound by
``prematch_prior_binds`` so only settled, kicked-off rows read), the same row
shape (``prematch_row_to_reading``), the same resolver, the event route's
truthiness test on the opening columns, and the same paired rounding
(``rendered_duel_percents``). The served object is byte-for-byte the event
route's.

A failed read costs the caller the venue rungs and nothing else: it runs in a
SAVEPOINT so an error cannot poison the transaction the caller is still using,
and every row then answers from its books rung alone, as the page would with no
venue snapshots.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import text

from app.utils.graded_card import rendered_duel_percents
from app.utils.kalshi_occurrence_start import loaded_sport_key
from app.utils.prematch_reading import (
    PREMATCH_PRIOR_SQL,
    prematch_prior_binds,
    prematch_row_to_reading,
    resolve_prematch_reading,
)

logger = logging.getLogger(__name__)


async def settled_prematch_odds_by_event(
    db: Any,
    events: Iterable[Any],
    *,
    opening: Optional[Callable[[Any], tuple]] = None,
    surface: str = "list",
) -> dict[int, dict]:
    """``{event_id: prematch_odds}`` for every settled row the ladder answers.

    ``opening`` maps a row to its ``(home, away)`` books rung; the default is the
    row's own opening columns, which is what the event route reads. A caller
    whose rows carry a folded opening line (the hub, #5853) passes it here.

    ``surface`` only names the caller in the log lines.

    Rows that are not settled, or that the ladder cannot answer, are absent —
    never ``None`` — so a caller's ``.get(id)`` is its whole test.
    """
    events = list(events)
    binds = prematch_prior_binds(events)
    if binds is None:
        return {}

    by_event: dict = {}
    try:
        nested = await db.begin_nested()
        try:
            for row in (await db.execute(text(PREMATCH_PRIOR_SQL), binds)).all():
                by_event.setdefault(row.event_id, {}).setdefault(
                    row.source, prematch_row_to_reading(row)
                )
        except Exception:
            try:
                await nested.rollback()
            except Exception:  # noqa: BLE001 — the read's error is the one to report
                pass
            raise
        await nested.commit()
    except Exception as exc:  # noqa: BLE001 — one optional key, never the page
        by_event = {}
        logger.warning(
            "%s: pre-match venue read failed (%s) — books rung only",
            surface,
            type(exc).__name__,
        )

    settled_ids = set(binds["ids"])
    served: dict[int, dict] = {}
    for e in events:
        if e.id not in settled_ids:
            continue
        open_home, open_away = (
            opening(e)
            if opening is not None
            else (e.opening_home_probability, e.opening_away_probability)
        )
        try:
            reading = resolve_prematch_reading(
                by_source=by_event.get(e.id, {}),
                books_home=float(open_home) if open_home else None,
                books_away=float(open_away) if open_away else None,
                sport=loaded_sport_key(e) or "",
            )
            if reading is None:
                continue
            away_pct, home_pct = rendered_duel_percents(
                reading["away_probability"], reading["home_probability"]
            )
        except Exception:  # noqa: BLE001 — gotcha #42: one row, never the page
            logger.exception("%s: event %s pre-match reading failed", surface, e.id)
            continue
        served[int(e.id)] = {
            "home_probability": reading["home_probability"],
            "away_probability": reading["away_probability"],
            "home_rendered_percent": home_pct,
            "away_rendered_percent": away_pct,
            "source": reading["source"],
        }
    return served
