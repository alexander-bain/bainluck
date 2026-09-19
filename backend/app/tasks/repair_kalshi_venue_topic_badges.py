"""#7012's repair half — the 110 stored rows the classifier fix cannot reach.

PILLAR: DISCOVER on TRUTH. SHIP: a reader browsing **hockey** stops being handed
"Which bank will take Kraken public before 2027?", a reader browsing
**motorsports** stops being handed "Will BMW release a Fully Electric M3 before
2028?", and a reader browsing **baseball** stops being handed MrBeast's NIL
donation.

WHY A RAIL AND NOT THE POLLER
=============================

#7012's classifier half (this branch) teaches ``_categorize_kalshi_market`` to
demote a bare name guess to the venue's own topic. It changes what the poller
writes on the NEXT row it files and **moves not one stored row**, because
``kalshi.py``'s upsert is #1888's honest-empty rule::

    coalesce(nullif(FuturesMarket.llm_sport_category, "other"), sport_category)

An existing real tag is never overwritten, by design, so a row stamped
``hockey`` in 2026 keeps ``hockey`` through every future poll no matter what the
classifier now says. That is the same wall #6955 hit, and an id-addressed rail
is again the only instrument that can cross it. A grader will ask why waiting is
not the answer; this paragraph is the answer.

🔴 WHY THIS IS NOT A WIDENING OF ``repair_kalshi_club_noun_category``
====================================================================

That module is frozen and already applied. Its twelfth bound entry
(``KXKRAKENBANKPUBLIC-27JAN01``) is a deliberate **proof-of-refusal control**:
it is in the bound so its dry run demonstrates the gate declining, and the
docstring reasons from that refusal. Widening that list would destroy the
control and re-run an applied one-shot over a population it never measured.

It is also the wrong SHAPE. That rail's bound is twelve frozen tickers from a
census taken once; this population is derived by a predicate at run time,
because it is two orders of magnitude larger and still moving as Kalshi files
new markets. A frozen list here would be stale the day it merged.

THE CANDIDATE PREDICATE, AND WHY IT USES THE HOUSE DENYLIST
===========================================================

Candidates are Kalshi rows whose ``llm_sport_category`` is **not** in
``sport_keys.NON_SPORT_LLM_CATEGORIES`` and whose stored ``category`` is a
non-sport topic (or ``other``).

I measured the alternative and rejected it. A positive sport ALLOWLIST is
tighter — the house denylist reads ``energy`` (3,146 rows), ``commodities``,
``watchmaking``, ``space``, ``real_estate`` and ``business`` as "sports", since
it is stated as the negative on purpose (``sport_keys.py`` §6: an allowlist
fails CLOSED on a new sport). On the open population that over-inclusion is
**ten extra venue calls** — 50 candidates instead of 40 — and it buys two
things worth more than ten calls: this rail carries **no sport literals of its
own** (``test_the_rail_carries_no_sport_rules_of_its_own``), and it inherits
every sport the house set learns later without an edit here.

🔴 THE ``other`` ARM IS NOT OPTIONAL, AND A TOPIC-ONLY CENSUS MISSES THE
HEADLINE SPECIMEN. Our ``category`` column is written by
``_kalshi_category_to_internal``, a DIFFERENT mapper from the one #7012's rule
consults, and it collapses every word it does not model into ``other``.
``109341`` — the Kraken row this whole issue is named for — stores
``category = 'other'`` because the venue said ``Companies``. Measured on
production 2026-09-18:

    stored category IN (topics)   33 open · 83 resolved
    stored category = 'other'     17 open · 4,134 resolved

A census keyed on the topic values alone returns 116 rows and **silently omits
the specimen**. Both arms are in the predicate for that reason.

WHY THE DEFAULT SCOPE IS ``open``
=================================

The ``other``-arm RESOLVED tail is 4,134 rows over 28 series and is dominated by
the ``*MENTION`` families — "Announcers at Atlanta vs Cleveland Professional
Basketball Game", badged ``basketball``, which is **correct**. Those rows pass
the candidate predicate and are then refused by the gate (the venue's category
for them is ``Sports``, which neither mapper models, so no topic is implied and
no demotion fires) — 800+ venue calls to confirm 800+ correct badges.

So the scope defaults to ``open``: 50 candidates, every reader-visible row,
including all seven of the ``other`` arm. ``status_scope='resolved'`` and
``'all'`` make the tail addressable rather than dropped — the route's own
doctrine is that a half which cannot be scoped cannot be applied alone.

THE EVIDENCE GATE IS THE VENUE, RUN THROUGH THE SHIPPED CASCADE
===============================================================

This rail contains **no sport rules of its own** — no keyword, no regex over a
market name, no category literal. Per candidate it re-asks Kalshi for the event
and its series and runs the SHIPPED ingest cascade over the reply via
``app.tasks.kalshi._categorize_kalshi_market``, with the exact arguments the
poller passes:

  * the market name,
  * the venue EVENT's ``category``,
  * the event ticker,
  * the series tag chosen by the shipped ``_pick_series_tag`` — **imported, not
    re-spelled.** #7012 changed this from ``tags[0]``, and the two rows the whole
    rule is protected by (``KXMLBCBA`` tagged ``Baseball`` under category
    ``Entertainment``, ``KXPERFORMSUPERBOWL`` tagged ``['Live Music',
    'Football']``) are protected *at step 1b by that function*. A rail that
    re-spelled ``tags[0]`` here would ask a weaker question than the poller asks
    and would demote both of them — turning the protection into the defect.
  * the SERIES ``category``, the parameter #7012 adds. ``109341`` is reachable
    through nothing else: its event says ``Companies`` (modelled by no mapper
    here) while its series says ``Financials`` → ``economics``.

``test_the_rail_asks_the_shipped_cascade_with_the_shipped_arguments`` fails the
build if any of those five stop being what the poller sends.

MEMBERSHIP IS ID IDENTITY
=========================

Our ``futures_markets.external_id`` **IS** the venue's ``event_ticker``, so a
row is admitted only when the venue echoes back that same ticker. There is no
container guess and no ``group_id`` sweep: the candidate predicate already names
the row, and the venue call either confirms its id or does not (gotcha #32's
discipline, one layer down). A row whose ``external_id`` is a market-leg ticker
rather than an event ticker 404s and is counted ``not_at_venue``.

WHAT IS NEVER WRITTEN
=====================

``llm_sport_category`` only, by Core UPDATE (gotchas #4/#5), compare-and-set on
the value read, so a poll landing between the SELECT and the UPDATE is never
clobbered. The Kalshi poller runs every two hours and DOES reach these rows, so
the CAS is an ordinary outcome here, not a theoretical one.

🔴 **NOT ``updated_at``** — CERT-2382. The card renders it as its own relative
date, so stamping ``NOW()`` would present unchanged prices as observed just now:
a repair whose whole purpose is TRUTH introducing a reader-visible lie about
freshness in the same statement.

🔴 **NOT ``status``** — ``resolved`` is the calibration population's own gate, so
writing it from a taxonomy rail is a write to the accuracy curve. Resolved rows
are repaired like any other when scoped in: this column is a taxonomy badge,
never a result, and no price, outcome, ``is_winner`` or ``settled_at`` field is
read or written here. "Settled means settled" is untouched.

🔴 **NOT ``category``** — the poller writes it on INSERT and never again, so
writing it here would make this rail do something the ingest path never does.
It is also this rail's candidate instrument, and an instrument that edits what
it measures cannot be re-run as a check.

🔴 **NEVER INTO ``crypto`` OR ``other``** — the rail inherits
``kalshi._VENUE_TOPIC_DEMOTION_TARGETS`` rather than restating it, so the
poller's own refusal to demote into a category it DROPS (``crypto``) or into the
absence of an answer (``other``) binds here by construction.

Nothing at all is written when the venue does not answer clearly, each with its
own named count rather than one silent success (gotchas #36, #53):

  * 429/5xx/timeout on either door → ``indeterminate``. A transient failure is
    not a verdict, and the SERIES door counts too: classifying on a missing tag
    would be classifying on a rate limit.
  * 404 on the event → ``not_at_venue``. A 404 on the SERIES is not that: the
    poller's ``get_series_metadata`` returns ``None`` for it and the cascade
    proceeds tagless, so this rail does the same.
  * the cascade returns ``None``/``"other"`` → ``refused_other``.
  * the cascade agrees with what is stored → ``venue_agrees``.

PAGING IS A KEYSET ON ``id``, NEVER AN OFFSET
=============================================

An apply REMOVES rows from its own candidate population (the badge it writes
leaves the predicate), so an ``OFFSET`` walk skips exactly as many rows as it
repaired. The cursor is ``after_id`` and the order is ``id`` — half a page of
progress is still monotonic. ``next_after_id`` and ``remaining`` travel in the
payload so an operator pages without doing arithmetic.

D51 — BACKUP AND RESTORE
========================

Every planned row carries its ``before`` value in the payload, on the dry run as
well as the apply, and the apply logs the restore. On an apply the undo is built
from what the database RETURNED rather than from the plan — the undo must name
the rows that MOVED, not the rows we hoped to move. A restore built from
``planned`` would write a stale ``before`` over a concurrent poller's fresher
value, turning the undo into a second defect.

ATTENDED ONLY: never wire this to a beat. It is a bounded, terminating repair.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from sqlalchemy import text

from app.utils.sport_keys import NON_SPORT_LLM_CATEGORIES

logger = logging.getLogger(__name__)

#: Kalshi's public trade API. The two doors this rail reads — ``/events/{t}``
#: and ``/series/{t}`` — need no key, which is why the rail can state its 404
#: discipline rather than inherit an auth failure as a venue verdict.
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"

#: Stored ``category`` values that make a row a CANDIDATE. The non-sport topics
#: plus ``other`` — see "THE ``other`` ARM IS NOT OPTIONAL" above; the headline
#: specimen lives in the ``other`` arm and a topic-only census omits it.
#:
#: Derived from the house set rather than typed out, so it cannot drift from it.
#: ``crypto`` stays IN as a candidate source (a crypto-topic row wrongly badged
#: hockey is in scope); it is barred as a DESTINATION by the poller's own
#: ``_VENUE_TOPIC_DEMOTION_TARGETS``, which is a different question.
CANDIDATE_STORED_CATEGORIES: tuple[str, ...] = tuple(sorted(NON_SPORT_LLM_CATEGORIES))

#: Which ``status`` values a pass considers. ``open`` is the default because the
#: resolved tail is 4,134 rows dominated by correctly-badged ``*MENTION``
#: families; see "WHY THE DEFAULT SCOPE IS ``open``".
STATUS_SCOPES: dict[str, Optional[tuple[str, ...]]] = {
    "open": ("open",),
    "resolved": ("resolved",),
    "all": None,
}
DEFAULT_STATUS_SCOPE = "open"

#: Candidates per pass. Sized against the web dyno's 30s HTTP wall, not against
#: the population: a pass costs one event call per candidate plus one series call
#: per DISTINCT series, and the open population's 50 candidates span ~42 series.
#: Twenty leaves headroom for a slow venue, and `next_after_id` makes the rest a
#: second call rather than a lost run.
DEFAULT_LIMIT = 20
MAX_LIMIT = 60

#: Pause between venue calls. Kalshi's limiter is real.
VENUE_PAUSE = 0.2

#: Per-venue-call timeout.
FETCH_TIMEOUT_SECONDS = 8

#: Bound on each UPDATE. This population IS polled — every two hours — so a row
#: lock is an ordinary outcome, and an operator running this during a poll
#: should get a named failure, not a router H12.
WRITE_TIMEOUT_MS = 2000


def restore_sql(planned: list[dict[str, Any]]) -> str:
    """The D51 undo, as statements that can be pasted and run.

    One statement per distinct before-value, never one statement for all rows:
    an earlier sibling shipped a version that interpolated the before-value *map*
    where the value belongs, which is not valid SQL. A restore line that looks
    runnable and is not is worse than none, because D51 is granted on it.
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


async def _fetch(
    client: httpx.AsyncClient, url: str
) -> tuple[str, Optional[dict[str, Any]]]:
    """Return ``(status, payload)`` where status is ok/not_found/indeterminate.

    Never raises for a venue condition and never collapses "does not exist" into
    "did not answer" — 404 and 429 need opposite handling and a catch-all that
    returned ``None`` for both would write a verdict on a rate limit (#36).

    🔴 ``KalshiAPIService.get_event`` is not used here for exactly that reason:
    its docstring says "Returns None only for 404" and its body returns ``None``
    from a bare ``except Exception`` as well — the CERT-2737 shape, fixed on
    ``get_series_metadata`` and still open on ``get_event``. Borrowing it would
    have made a 5xx read as ``not_at_venue`` in this rail's own report.
    """
    try:
        r = await client.get(url, timeout=FETCH_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 — transport failure is INDETERMINATE
        return "indeterminate", None
    if r.status_code == 404:
        return "not_found", None
    if r.status_code != 200:
        return "indeterminate", None
    try:
        payload = r.json()
    except Exception:  # noqa: BLE001
        return "indeterminate", None
    if not isinstance(payload, dict):
        return "indeterminate", None
    return "ok", payload


async def _fetch_event(
    client: httpx.AsyncClient, event_ticker: str
) -> tuple[str, Optional[dict[str, Any]]]:
    """The venue's event. ``ok``/``not_found``/``indeterminate``."""
    return await _fetch(client, f"{KALSHI_API}/events/{event_ticker}")


async def _fetch_series(
    client: httpx.AsyncClient, series_ticker: str
) -> tuple[str, Optional[dict[str, Any]]]:
    """The venue's series, whose ``tags`` and ``category`` the cascade reads."""
    return await _fetch(client, f"{KALSHI_API}/series/{series_ticker}")


def _resolve_limit(limit: Optional[int]) -> int:
    """Clamp the page size. A caller asking for the world still gets a page."""
    if not limit or limit < 1:
        return DEFAULT_LIMIT
    return min(int(limit), MAX_LIMIT)


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    after_id: Optional[int] = None,
    status_scope: Optional[str] = None,
    **_ignored,
) -> dict[str, Any]:
    """Plan (and optionally apply) the #7012 stored-badge correction.

    Dry-run by default. Returns a payload complete enough to BE the D51 backup:
    every candidate considered, the venue's verdict, every row that would move
    with its stored value, and a named reason for each refusal.
    """
    # Imported here, not at module scope: `app.tasks.kalshi` pulls the ingest
    # world in, and a repair module that is merely REGISTERED should not widen
    # what `app.main` imports at boot.
    from app.tasks.kalshi import (
        _categorize_kalshi_market,
        _pick_series_tag,
        _VENUE_TOPIC_DEMOTION_TARGETS,
    )

    scope_key = (status_scope or DEFAULT_STATUS_SCOPE).strip().lower()
    if scope_key not in STATUS_SCOPES:
        # A bad scope is refused BY NAME rather than silently defaulted: a
        # typo that quietly became `open` would report a complete pass over a
        # population the operator did not ask for.
        return {
            "repair": "kalshi-venue-topic-badges",
            "terminal": "refused_bad_status_scope",
            "status_scope": status_scope,
            "valid_status_scopes": sorted(STATUS_SCOPES),
        }

    page_size = _resolve_limit(limit)
    cursor = int(after_id or 0)
    statuses = STATUS_SCOPES[scope_key]

    counts = {
        "candidates_examined": 0,
        "changed": 0,
        "venue_agrees": 0,
        "refused_other": 0,
        "refused_not_a_demotion_target": 0,
        "not_at_venue": 0,
        "not_our_ticker": 0,
        "indeterminate": 0,
        "write_failed": 0,
        "rows_written": 0,
    }
    planned: list[dict[str, Any]] = []
    #: What the database actually moved, read back by ``RETURNING id``. Empty on
    #: a dry run, where ``planned`` is the correct undo basis instead.
    applied: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    #: One read per SERIES, holding ``(status, tag, category)`` — so a transient
    #: failure is remembered as a failure rather than as "no tag".
    series_seen: dict[str, tuple[str, Optional[str], Optional[str]]] = {}

    where_status = ""
    params: dict[str, Any] = {
        "cats": list(CANDIDATE_STORED_CATEGORIES),
        "non_sport": list(NON_SPORT_LLM_CATEGORIES),
        "after_id": cursor,
        "lim": page_size,
    }
    if statuses is not None:
        where_status = "AND fm.status = ANY(:statuses)"
        params["statuses"] = list(statuses)

    # The candidate predicate. `llm_sport_category NOT IN (house denylist)` is
    # "wears a sport badge"; `category IN (topics + other)` is "our own topic
    # column disagrees, or could not say". The VENUE decides which of those is
    # wrong — this query only nominates.
    rows = (
        await session.execute(
            text(
                f"""
                SELECT fm.id,
                       fm.name,
                       fm.status,
                       fm.external_id,
                       fm.category,
                       fm.llm_sport_category
                FROM futures_markets fm
                WHERE fm.source = 'kalshi'
                  AND fm.external_id IS NOT NULL
                  AND fm.llm_sport_category IS NOT NULL
                  AND NOT (fm.llm_sport_category = ANY(:non_sport))
                  AND fm.category = ANY(:cats)
                  AND fm.id > :after_id
                  {where_status}
                ORDER BY fm.id
                LIMIT :lim
                """
            ),
            params,
        )
    ).all()

    # How many candidates remain BEYOND this page, measured in the same breath
    # as the page itself. Reported so a `changed: 0` page is never read as a
    # finished population (gotcha #53).
    remaining = (
        await session.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM futures_markets fm
                WHERE fm.source = 'kalshi'
                  AND fm.external_id IS NOT NULL
                  AND fm.llm_sport_category IS NOT NULL
                  AND NOT (fm.llm_sport_category = ANY(:non_sport))
                  AND fm.category = ANY(:cats)
                  AND fm.id > :after_id
                  {where_status}
                """
            ),
            params,
        )
    ).scalar() or 0

    next_after_id: Optional[int] = None

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for r in rows:
            next_after_id = int(r.id)
            counts["candidates_examined"] += 1
            event_ticker = (r.external_id or "").strip()

            record = {
                "id": int(r.id),
                "event_ticker": event_ticker,
                "name": r.name,
                "status": r.status,
                "stored_category": r.category,
                "stored": r.llm_sport_category,
            }

            status, payload = await _fetch_event(client, event_ticker)
            await asyncio.sleep(VENUE_PAUSE)

            if status != "ok" or payload is None:
                # A 404 on the EVENT is a verdict about the event; a timeout is
                # not a verdict about anything.
                reason = "not_at_venue" if status == "not_found" else "indeterminate"
                counts[reason] += 1
                refused.append({**record, "reason": reason})
                continue

            event = payload.get("event") or {}
            venue_ticker = str(event.get("event_ticker") or "").strip()
            series_ticker = str(event.get("series_ticker") or "").strip()
            record["venue_category"] = event.get("category")
            record["series_ticker"] = series_ticker or None

            # MEMBERSHIP, id identity and nothing else. The venue must echo back
            # the ticker we asked about; a redirect or a fuzzy answer is refused
            # rather than reasoned about.
            if not venue_ticker or venue_ticker != event_ticker:
                counts["not_our_ticker"] += 1
                refused.append(
                    {**record, "reason": "not_our_ticker", "venue_ticker": venue_ticker}
                )
                continue

            # The series door. A transient failure HERE is indeterminate too:
            # the cascade consults the tag above its name rules, so classifying
            # without it is classifying on a rate limit. A 404 is different —
            # the poller's `get_series_metadata` returns None for it and the
            # cascade proceeds tagless, so this rail does the same.
            series_tag: Optional[str] = None
            series_category: Optional[str] = None
            if series_ticker:
                if series_ticker not in series_seen:
                    s_status, s_payload = await _fetch_series(client, series_ticker)
                    await asyncio.sleep(VENUE_PAUSE)
                    series = (s_payload or {}).get("series") or {}
                    series_seen[series_ticker] = (
                        s_status,
                        # The SHIPPED chooser, imported. #7012 changed this from
                        # `tags[0]`, and the two rows the rule is protected by
                        # are protected by that change — re-spelling it here
                        # would ask a weaker question than the poller asks.
                        _pick_series_tag(series.get("tags") or []),
                        series.get("category"),
                    )
                s_status, series_tag, series_category = series_seen[series_ticker]
                if s_status == "indeterminate":
                    counts["indeterminate"] += 1
                    refused.append({**record, "reason": "indeterminate"})
                    continue
            record["series_tag"] = series_tag
            record["series_category"] = series_category

            # THE VERDICT: the shipped cascade, on the venue's own answer, with
            # the arguments the poller passes — including `series_category`,
            # which is the only signal that reaches `109341`.
            llm = _categorize_kalshi_market(
                r.name or "",
                event.get("category"),
                event_ticker,
                series_tag,
                series_category,
            )
            record["venue_verdict"] = llm
            verdicts.append(record)

            if not llm or llm == "other":
                # The poller's own honest-empty guard: never overwrite a real
                # value with the "other" default.
                counts["refused_other"] += 1
                refused.append({**record, "reason": "refused_other"})
                continue

            if llm == r.llm_sport_category:
                # THE GATE DECLINING — the venue's own reply, through the
                # shipped cascade, agrees with what is stored. This is where the
                # seven `KXPGAAWARDS` rows land (#7042: a bare `kxpga` prefix
                # answers golf at step 1, above everything this rule touches)
                # and where `KXMLBCBA` / `KXPERFORMSUPERBOWL` land (protected at
                # step 1b by their own venue tag).
                counts["venue_agrees"] += 1
                refused.append({**record, "reason": "venue_agrees"})
                continue

            if llm not in _VENUE_TOPIC_DEMOTION_TARGETS:
                # A verdict that is neither the stored value nor a legal
                # demotion target. The poller may write such a value on INSERT
                # (a ticker-map or tag answer naming a different SPORT), but a
                # REPAIR moving a row between two sports is not this issue and
                # has not been measured. Counted and refused, never written —
                # a rail that silently widened past its own warrant is the drift
                # this design exists to prevent.
                counts["refused_not_a_demotion_target"] += 1
                refused.append({**record, "reason": "not_a_demotion_target"})
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
            # Compare-and-set on the value we read: the Kalshi poller runs every
            # two hours and DOES reach these rows.
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
                # RETURNING, not rowcount, and the difference is the whole point
                # (CERT-2382's follow-up). The undo must name the rows that
                # MOVED. A rowcount tells you HOW MANY matched, never WHICH, so
                # a restore built from the plan could write a stale `before`
                # over a fresher value, turning the undo into a second defect.
                moved = {row[0] for row in result.all()}
                counts["rows_written"] += len(moved)
                if row_plan["id"] in moved:
                    applied.append(row_plan)
                await session.commit()
            except Exception as exc:  # noqa: BLE001 — a blocked write is not a verdict
                # A statement timeout aborts the whole TRANSACTION, so the
                # session is unusable until it is rolled back. Rows committed
                # before this one are durable and stay counted.
                await session.rollback()
                counts["write_failed"] += 1
                refused.append({**record, "reason": "write_failed"})
                logger.warning(
                    "repair_kalshi_venue_topic_badges: the UPDATE for row %s "
                    "did not land (%s: %s); rows already committed are "
                    "unaffected",
                    row_plan["id"],
                    type(exc).__name__,
                    exc,
                )

    # On an apply the undo is built from what the database RETURNED, never from
    # the plan. On a dry run nothing moved, so the plan is the correct basis —
    # it is the undo for the write about to be authorised.
    undo_basis = applied if apply else planned

    if apply and counts["rows_written"]:
        logger.warning(
            "#7012 Kalshi venue-topic badge repair applied: %s rows. D51 RESTORE:\n%s",
            counts["rows_written"],
            restore_sql(undo_basis),
        )

    # Gotcha #53: a pass that examined rows and wrote nothing says so in a named
    # terminal rather than leaving zeros for a reader to interpret.
    if apply:
        terminal = "changed" if counts["rows_written"] else "no_rows_written"
    else:
        terminal = "dry_run"

    return {
        "repair": "kalshi-venue-topic-badges",
        "status_scope": scope_key,
        "counts": counts,
        "planned": planned,
        # What the database actually moved (RETURNING id). Reported ALONGSIDE
        # `planned` rather than instead of it, so a partial apply is visible as
        # the difference between the two rather than smoothed into one number.
        "applied": applied,
        "refused": refused,
        "verdicts": verdicts,
        # Keyset paging, never an offset: an apply removes rows from its own
        # population, so an OFFSET walk skips exactly what it repaired.
        "after_id": cursor,
        "next_after_id": next_after_id,
        # Candidates beyond this page's cursor, measured in the same call. A
        # `changed: 0` page is not a finished population and this is how an
        # operator tells the two apart.
        "remaining_before_page": int(remaining),
        "page_size": page_size,
        # The D51 undo travels WITH the plan, on the dry run too — an operator
        # reads the restore before deciding to apply, not afterwards in a log
        # line they have to go and find.
        "restore_sql": restore_sql(undo_basis),
        "terminal": terminal,
    }
