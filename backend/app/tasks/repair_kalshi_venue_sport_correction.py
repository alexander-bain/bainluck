"""#8029 — the sport-to-sport half `repair_kalshi_venue_topic_badges` measured and declined.

PILLAR: TRUTH. SHIP: a reader opening "Will MrBeast donate to East Carolina
University athletics NIL programs this year?" stops being told it is **BASEBALL**.

WHY A SECOND RAIL AND NOT A WIDENING OF THE FIRST
=================================================

`repair_kalshi_venue_topic_badges` already fetches this row, already asks the
shipped cascade, and already gets the right answer. It then refuses, by name, at
its own boundary::

    if llm not in _VENUE_TOPIC_DEMOTION_TARGETS:
        # ... a REPAIR moving a row between two sports is not this issue and
        # has not been measured. Counted and refused, never written.
        counts["refused_not_a_demotion_target"] += 1

That refusal is correct and stays. It is a DEMOTION rail: it moves a bare name
guess down onto the venue's non-sport topic, and `football` is not a topic. Its
suite pins the refusal with `test_a_sport_to_sport_verdict_is_refused_not_written`,
which asserts this very ticker's cascade answer is `football`. Widening that
module would delete its own control and re-scope a live rail past the population
it measured.

So this is the measurement that refusal asked for, plus the rail it warrants.

THE MEASUREMENT (authority/974, 2026-09-22, production)
=======================================================

The sibling's whole `status_scope=open` candidate population — every Kalshi row
stored under a sport whose stored `category` is a non-sport topic or `other` —
is **25 rows**, paged to exhaustion (20 + 5 + 0; `remaining_before_page`
25 -> 5 -> 0). Of those 25:

* 9 the venue AGREES with (7 `KXPGAAWARDS`, `KXMLBCBA`, `KXFA`, …),
* 15 the venue answers `other` for (refused by the honest-empty guard),
* **1** carries a venue verdict naming a DIFFERENT SPORT: `109401`.

So the reader-visible class is one row, and that is why the bound below is
enumerated rather than derived.

🔴 WHAT THAT NUMBER DOES **NOT** SAY. It is scoped to the sibling's candidate
predicate, which requires the stored `category` to be a non-sport topic or
`other`. A row whose stored `category` is itself a sport is not a candidate of
that census and is therefore unmeasured here. The wider "every Kalshi row whose
series tag names a different sport than we stored" population would cost one
venue call per series across the whole Kalshi shelf and has NOT been taken.
Nothing in this module may be read as a claim about it.

WHY THE ROW IS STUCK, AND WHY WAITING IS NOT THE ANSWER
=======================================================

The shipped classifier already gets this row right. Measured on the real name
and the real venue reply::

    _categorize_kalshi_market(name, "Social", "KXDONATEMRBEAST-27JAN",
                              series_tag="Football", series_category="Sports")
        -> "football"          # step 1b, the venue's own published tag
    _categorize_kalshi_market(name, "Social", "KXDONATEMRBEAST-27JAN")
        -> "baseball"          # no tag: the name rules, and the defect

`baseball` is what a pre-#5637 ingest wrote, reading "East Carolina University
**athletics**" — the Oakland A's token — with nothing competing. The scorer is
not at fault and must not be "fixed" here: `athletics` scores 1 for baseball and
1 for olympics, exactly as `Athletics vs. Detroit Tigers` (527 markets) and
`Avalanche vs. Blues` (244 markets) do, and those are RIGHT. A scoring rule that
refuses the tie would trade ~771 correct answers for ~287 wrong ones. Measured
2026-09-22 over all 16,609 distinct names carrying an ambiguity-table token.
The defect is not in the scorer; it is a stale row.

And the row cannot heal itself. #1888's honest-empty upsert is
`coalesce(nullif(llm_sport_category, 'other'), new)` — an existing REAL tag is
never overwritten — so `baseball` survives every future poll no matter what the
classifier now says. An id-addressed rail is again the only instrument that
crosses that wall.

THE GATES
=========

Five, and every one of them can only ever REFUSE:

1. **The bound.** `id` is in `BOUND`. Enumerated, frozen, measured above.
2. **Membership.** The venue echoes back the event ticker we asked about. Id
   identity, never a name or a fuzzy answer.
3. **The venue published a sport tag.** `series_tag_to_category` resolves the
   tag the SHIPPED chooser picks. This is the evidence — notice 40's "the
   venue's own structure first". A row whose series carries no sport tag has no
   warrant here and is refused.
4. **The cascade's answer IS the tag's answer.** The shipped
   `_categorize_kalshi_market` must return exactly what the tag resolved to.
   🔴 This is the gate that makes the rail safe, and it is not decoration: the
   cascade can also answer from the NAME (step 2), and a name guess is the very
   thing that put `baseball` in the row. Without this gate the rail would
   happily overwrite one name guess with another name guess. With it, the only
   value that can ever be written is the word the venue itself published.
5. **The move is sport -> a DIFFERENT sport.** The destination must not be
   `other` and must not be a non-sport category (those are the sibling's
   business, and its honest-empty guard already owns them), and it must differ
   from what is stored.

Writes `llm_sport_category` ONLY — not `category` (the sibling's candidate
instrument), not `status`, not `updated_at`, and nothing in the settlement or
price world. A taxonomy badge is never a result, so "settled means settled" is
untouched. Core UPDATE with compare-and-set on the value read (gotchas #4/#5),
bounded by a statement timeout because this population IS polled every two
hours. D51: `restore_sql` travels with the plan, built from RETURNING.

ATTENDED ONLY: never wire this to a beat. It is a terminating repair over an
enumerated bound.
"""

import asyncio
from typing import Any, Optional

from sqlalchemy import text

# The venue doors and the operational constants are the sibling's, imported
# rather than re-spelt. `_fetch` there is deliberately not `get_event` (#36: a
# catch-all that returns None for both 404 and 429 writes a verdict on a rate
# limit), and a second hand-rolled copy here would be the drift this import
# exists to prevent. A guard test asserts the identity.
from app.tasks.repair_kalshi_venue_topic_badges import (
    VENUE_PAUSE,
    WRITE_TIMEOUT_MS,
    _fetch_event,
    _fetch_series,
)
from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES

REPAIR_NAME = "kalshi-venue-sport-correction"

#: The enumerated bound. Measured on production 2026-09-22 (authority/974) by
#: paging `repair_kalshi_venue_topic_badges` at `status_scope=open` to
#: exhaustion: the single candidate of 25 whose venue verdict names a sport
#: other than the one stored.
#:
#: 🔴 THIS LIST IS A BOUND, NOT A CLAIM THAT THE ROW IS WRONG. The claim that
#: the row is wrong is made by the venue's own published tag, through the
#: shipped cascade, per row, at run time. Every gate below can still refuse it.
BOUND: tuple[int, ...] = (109401,)


def restore_sql(planned: list[dict[str, Any]]) -> str:
    """The D51 undo, as statements that can be pasted and run.

    One statement per distinct before-value, never one statement for all rows:
    a sibling once interpolated the before-value *map* where the value belongs,
    which is not valid SQL. A restore line that looks runnable and is not is
    worse than none, because D51 is granted on it.
    """
    by_before: dict[Optional[str], list[int]] = {}
    for row in planned:
        by_before.setdefault(row["before"], []).append(int(row["id"]))

    lines = []
    for before, ids in sorted(by_before.items(), key=lambda kv: str(kv[0])):
        ids_csv = ", ".join(str(i) for i in sorted(ids))
        value = "NULL" if before is None else f"'{before}'"
        lines.append(
            f"UPDATE futures_markets SET llm_sport_category = {value} "
            f"WHERE id IN ({ids_csv});"
        )
    return "\n".join(lines)


async def repair(session, apply: bool = False, **_ignored) -> dict[str, Any]:
    """Plan (and optionally apply) the #8029 sport-to-sport correction.

    Dry-run by default. Returns a payload complete enough to BE the D51 backup:
    every bound row considered, the venue's tag and verdict, every row that
    would move with its stored value, and a named reason for each refusal.
    """
    # Imported here, not at module scope: `app.tasks.kalshi` pulls the ingest
    # world in, and a repair module that is merely REGISTERED should not widen
    # what `app.main` imports at boot.
    from app.tasks.kalshi import (
        _categorize_kalshi_market,
        _pick_series_tag,
        series_tag_to_category,
    )

    import httpx

    counts = {
        "bound_size": len(BOUND),
        "rows_found": 0,
        "changed": 0,
        "not_at_venue": 0,
        "not_our_ticker": 0,
        "no_venue_sport_tag": 0,
        "verdict_not_from_tag": 0,
        "venue_agrees": 0,
        "refused_not_a_sport": 0,
        "indeterminate": 0,
        "write_failed": 0,
        "rows_written": 0,
    }
    verdicts: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []
    applied: list[int] = []

    rows = (
        await session.execute(
            text(
                """
                SELECT fm.id, fm.name, fm.status, fm.external_id,
                       fm.category, fm.llm_sport_category
                  FROM futures_markets fm
                 WHERE fm.source = 'kalshi'
                   AND fm.id = ANY(:ids)
                 ORDER BY fm.id
                """
            ),
            {"ids": list(BOUND)},
        )
    ).all()
    counts["rows_found"] = len(rows)

    series_seen: dict[str, tuple[str, Optional[str], Optional[str]]] = {}

    async with httpx.AsyncClient() as client:
        for r in rows:
            event_ticker = (r.external_id or "").strip()
            record: dict[str, Any] = {
                "id": int(r.id),
                "event_ticker": event_ticker,
                "name": r.name,
                "status": r.status,
                "stored_category": r.category,
                "stored": r.llm_sport_category,
            }

            if not event_ticker:
                counts["not_at_venue"] += 1
                refused.append({**record, "reason": "no_external_id"})
                continue

            status, payload = await _fetch_event(client, event_ticker)
            await asyncio.sleep(VENUE_PAUSE)
            if status == "not_found":
                counts["not_at_venue"] += 1
                refused.append({**record, "reason": "not_at_venue"})
                continue
            if status != "ok" or not payload:
                # A transport failure or a 429 is NOT evidence of anything
                # (#36, gotcha #53). It never becomes a verdict.
                counts["indeterminate"] += 1
                refused.append({**record, "reason": "indeterminate"})
                continue

            event = payload.get("event") or {}
            venue_ticker = str(event.get("event_ticker") or "").strip()
            series_ticker = str(event.get("series_ticker") or "").strip()
            record["venue_category"] = event.get("category")
            record["series_ticker"] = series_ticker or None

            # GATE 2 — membership by id identity. A redirect or a fuzzy answer
            # is refused rather than reasoned about.
            if not venue_ticker or venue_ticker != event_ticker:
                counts["not_our_ticker"] += 1
                refused.append(
                    {**record, "reason": "not_our_ticker", "venue_ticker": venue_ticker}
                )
                continue

            if not series_ticker:
                counts["no_venue_sport_tag"] += 1
                refused.append({**record, "reason": "no_series_ticker"})
                continue

            if series_ticker not in series_seen:
                s_status, s_payload = await _fetch_series(client, series_ticker)
                await asyncio.sleep(VENUE_PAUSE)
                series = (s_payload or {}).get("series") or {}
                series_seen[series_ticker] = (
                    s_status,
                    # The SHIPPED chooser, imported — it reads PAST the first
                    # tag, and re-spelling it here would ask a weaker question
                    # than the poller asks.
                    _pick_series_tag(series.get("tags") or []),
                    series.get("category"),
                )
            s_status, series_tag, series_category = series_seen[series_ticker]
            if s_status != "ok":
                # The series door decides this rail's entire warrant, so a
                # failure here is indeterminate even on a 404: classifying
                # without the tag is classifying on the very name guess the
                # rail exists to overwrite.
                counts["indeterminate"] += 1
                refused.append({**record, "reason": "indeterminate_series"})
                continue
            record["series_tag"] = series_tag
            record["series_category"] = series_category

            # GATE 3 — the venue published a sport tag we model.
            tag_category = series_tag_to_category(series_tag)
            record["tag_category"] = tag_category
            if not tag_category:
                counts["no_venue_sport_tag"] += 1
                refused.append({**record, "reason": "no_venue_sport_tag"})
                continue

            # THE VERDICT: the shipped cascade, on the venue's own answer, with
            # the arguments the poller passes.
            llm = _categorize_kalshi_market(
                r.name or "",
                event.get("category"),
                event_ticker,
                series_tag,
                series_category,
            )
            record["venue_verdict"] = llm
            verdicts.append(record)

            # GATE 4 — the cascade answered FROM THE TAG, not from the name.
            if llm != tag_category:
                counts["verdict_not_from_tag"] += 1
                refused.append({**record, "reason": "verdict_not_from_tag"})
                continue

            # GATE 5 — sport -> a DIFFERENT sport.
            if not llm or llm == "other" or llm in NON_SPORT_LLM_CATEGORIES:
                counts["refused_not_a_sport"] += 1
                refused.append({**record, "reason": "refused_not_a_sport"})
                continue
            if llm == r.llm_sport_category:
                counts["venue_agrees"] += 1
                refused.append({**record, "reason": "venue_agrees"})
                continue

            row_plan = {
                "id": int(r.id),
                "event_ticker": event_ticker,
                "name": r.name,
                "status": r.status,
                "before": r.llm_sport_category,
                "after": llm,
            }
            counts["changed"] += 1
            planned.append(row_plan)

            if not apply:
                continue

            # Core UPDATE, never ORM attribute assignment (gotchas #4/#5).
            # Compare-and-set on the value we read: the Kalshi poller runs
            # every two hours and DOES reach these rows.
            try:
                await session.execute(
                    text(f"SET LOCAL statement_timeout = {WRITE_TIMEOUT_MS}")
                )
                result = await session.execute(
                    text(
                        """
                        UPDATE futures_markets
                        SET llm_sport_category = :llm
                        WHERE id = :id
                          AND llm_sport_category IS NOT DISTINCT FROM :before
                        RETURNING id
                        """
                    ),
                    {
                        "llm": row_plan["after"],
                        "id": row_plan["id"],
                        "before": row_plan["before"],
                    },
                )
                # RETURNING, not rowcount. The undo must name the rows that
                # MOVED: a rowcount tells you HOW MANY matched, never WHICH, so
                # a restore built from the plan could write a stale `before`
                # over a fresher value, turning the undo into a second defect.
                moved = {row[0] for row in result.all()}
            except Exception:  # noqa: BLE001 — a lock or timeout is a RESULT
                await session.rollback()
                counts["write_failed"] += 1
                refused.append({**row_plan, "reason": "write_failed"})
                continue

            if moved:
                await session.commit()
                counts["rows_written"] += 1
                applied.append(row_plan["id"])
            else:
                # Compare-and-set lost: something moved the row under us.
                await session.rollback()
                counts["write_failed"] += 1
                refused.append({**row_plan, "reason": "concurrent_change"})

    return {
        "repair": REPAIR_NAME,
        "bound": list(BOUND),
        "counts": counts,
        "verdicts": verdicts,
        "planned": planned,
        "applied": applied,
        "refused": refused,
        # The undo names only what actually MOVED.
        "restore_sql": restore_sql(
            [p for p in planned if p["id"] in set(applied)]
        ) if apply else "",
        "terminal": "applied" if apply else "dry_run",
    }
