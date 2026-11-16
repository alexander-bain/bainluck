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

import asyncio
import logging
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping, Optional

from sqlalchemy import text

from app.utils.graded_card import rendered_duel_percents
from app.utils.kalshi_occurrence_start import loaded_sport_key
from app.utils.prematch_reading import (
    fetch_prematch_prior_rows,
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
    status_of: Optional[Callable[[Any], str]] = None,
    absorbed_ids: Optional[Mapping[int, Iterable[int]]] = None,
    timeout_ms: Optional[int] = None,
) -> dict[int, dict]:
    """``{event_id: prematch_odds}`` for every settled row the ladder answers.

    ``opening`` maps a row to its ``(home, away)`` books rung; the default is the
    row's own opening columns, which is what the event route reads. A caller
    whose rows carry a folded opening line (the hub, #5853) passes it here.

    ``status_of`` uses the status the card serves, after venue settlement.
    ``absorbed_ids`` carries already-proven twins, read at the survivor's
    kickoff, own source first and then twins in id order, as on detail.
    ``timeout_ms`` bounds the optional read without leaking SET LOCAL into
    later stages. Zero skips the venue read and retains the books fallback.
    ``surface`` only names the caller in the log lines.

    Rows that are not settled, or that the ladder cannot answer, are absent —
    never ``None`` — so a caller's ``.get(id)`` is its whole test.
    """
    events = list(events)
    candidates = events if status_of is None else [
        SimpleNamespace(id=e.id, status=status_of(e), commence_time=e.commence_time)
        for e in events
    ]
    binds = prematch_prior_binds(candidates)
    if binds is None:
        return {}

    settled_ids = set(binds["ids"])
    source_ids = {eid: [eid] for eid in settled_ids}
    for event_id, cutoff in list(zip(binds["ids"], binds["cutoffs"])):
        twins = sorted(set((absorbed_ids or {}).get(event_id, ())) - {event_id})
        source_ids[event_id].extend(twins)
        binds["ids"].extend(twins)
        binds["cutoffs"].extend([cutoff] * len(twins))

    by_event: dict = {}
    try:
        if timeout_ms is None or timeout_ms > 0:
            nested = await db.begin_nested()
            try:
                if timeout_ms is not None:
                    await db.execute(text(f"SET LOCAL statement_timeout = '{int(timeout_ms)}ms'"))
                for row in await fetch_prematch_prior_rows(db, binds):
                    by_event.setdefault(row.event_id, {}).setdefault(
                        row.source, prematch_row_to_reading(row)
                    )
            except (Exception, asyncio.CancelledError):
                try:
                    await nested.rollback()
                except Exception:  # noqa: BLE001 — preserve the original error
                    pass
                raise
            if timeout_ms is None:
                await nested.commit()
            else:
                await nested.rollback()
    except Exception as exc:  # noqa: BLE001 — one optional key, never the page
        by_event = {}
        logger.warning(
            "%s: pre-match venue read failed (%s) — books rung only",
            surface,
            type(exc).__name__,
        )

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
            by_source = {}
            for source_id in source_ids[e.id]:
                for source, row in by_event.get(source_id, {}).items():
                    by_source.setdefault(source, row)
            reading = resolve_prematch_reading(
                by_source=by_source,
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


async def attach_settled_prematch_odds(
    db: Any, events: Iterable[Any], formatted: list[dict], folded: Mapping,
    *, absorbed_ids: Mapping[int, Iterable[int]], timeout_ms: int, surface: str,
) -> None:
    """Attach the detail page's prior after the list's folds and settlement."""
    status = {row["id"]: row.get("status") for row in formatted}
    twins = {eid: set(ids) for eid, ids in absorbed_ids.items()}
    for eid, numbers in folded.items():
        twins.setdefault(eid, set()).update(numbers.absorbed_ids)
    readings = await settled_prematch_odds_by_event(
        db, events, surface=surface, status_of=lambda e: status.get(e.id),
        opening=lambda e: folded[e.id].opening if e.id in folded else (
            e.opening_home_probability, e.opening_away_probability
        ),
        absorbed_ids=twins, timeout_ms=timeout_ms,
    )
    for row in formatted:
        if row["id"] in readings:
            row["prematch_odds"] = readings[row["id"]]
