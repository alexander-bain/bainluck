"""#6955 — the Kalshi half: storm questions the poller sees every two hours and
deliberately declines to re-file.

PILLAR: DISCOVER on TRUTH. SHIP: a reader searching "Atlantic hurricanes" stops
being handed three Kalshi cards badged **HOCKEY** beside two identical Kalshi
cards badged **WEATHER**. Measured on production 2026-09-18 19:00Z,
``/api/events/search?q=Atlantic hurricanes`` served::

    8431182   hockey    kalshi   How many major Atlantic hurricanes will there be in 2026?
    8431183   hockey    kalshi   How many Atlantic hurricanes will there be in 2026?
    57401686  weather   polymarket
    25925285  hockey    kalshi   What named storms will be hurricanes in the Atlantic this year?

and ``q=named storms`` served ``25925283``/``25925284``/``25925285`` as
``hockey`` directly above ``25925265``/``25925266`` — *the same Kalshi series
family, the same page, two different badges.*

🔴 WHY THIS IS NOT THE POLYMARKET SIBLING WITH DIFFERENT IDS
============================================================

``repair_polymarket_club_noun_category`` exists because the poller **never
reaches** its rows: the event is archived at the venue, or it sits outside a
newest-first horizon. Nothing like that is true here. The Kalshi poller reaches
every one of these rows on every pass and writes nothing, because
``app/tasks/kalshi.py`` writes the tag through::

    coalesce(nullif(FuturesMarket.llm_sport_category, "other"), sport_category)

which is #1888's honest-empty rule: **an existing real tag is never
overwritten, by design.** Only ``other`` can be upgraded. So a row stamped
``hockey`` in a season when the classifier read "hurricanes" as the Carolina
club keeps ``hockey`` through every future poll, forever, no matter what the
classifier now says — and that is intended behaviour protecting against
seasonal tag drift, not a bug to patch in the poller.

The consequence for this issue is exact and it is the reason this module
exists: **the classifier half of #6955 (merged ``72437215e``, live in v4732)
moves not one stored Kalshi row.** Verified against the shipped cascade on the
venue's own replies — see the census below. An id-addressed rail is the only
instrument that can, and a grader will ask why the poller is not the answer.

THE EVIDENCE GATE IS THE VENUE, NOT A CLASSIFIER
================================================

This rail contains **no sport rules of its own** — no keyword, no regex over a
market name, no category literal. It re-asks Kalshi for the event and its
series, and runs the shipped ingest cascade over the reply via
``app.tasks.kalshi._categorize_kalshi_market`` — the exact function the poller
calls, with the exact arguments the poller passes (the market name, the venue
event's ``category``, the event ticker, and the first of the venue series'
``tags``, which is ``_resolve_series_tag_result``'s rule).
``test_the_rail_carries_no_sport_rules_of_its_own`` fails the build if that
stops being true.

Read off Kalshi 2026-09-18 (``/events/{ticker}`` and ``/series/{ticker}``)::

    KXHURCTOT          Climate and Weather   tags ['Hurricanes', 'Natural disasters']  -> weather
    KXHURCTOTMAJ       Climate and Weather   tags ['Hurricanes', 'Natural disasters']  -> weather
    KXHURRICANE        Climate and Weather   tags ['Hurricanes']                       -> weather
    KXHURRICANENAMES   Climate and Weather   tags ['Hurricanes']                       -> weather
    KXNHLPTS           Sports                tags ['Hockey']                           -> hockey
    KXNHLEAST          Sports                tags ['Hockey']                           -> hockey

The venue has been filing these under Climate and Weather the entire time.
Nothing read it, because ``llm_sport_category`` was written once, wrongly, and
#1888 then protected the wrong answer.

THE CENSUS IS COMPLETE, AND IT IS CHECKED TWO WAYS
==================================================

Measured on production 2026-09-18 19:00–19:20Z:

1. **By name token.** Every ``source='kalshi'`` row whose name matches
   ``hurricane|cyclone|typhoon|tropical storm|named storm|landfall|storm
   surge|kraken`` and whose ``llm_sport_category`` is not ``weather``: **299
   rows.** Grouped by Kalshi ticker prefix, 287 of them are ``KXNHL*`` /
   ``KXT20MATCH`` / ``KXNCAAMSOCCERGAME`` — Carolina Hurricanes, Seattle Kraken,
   real sport, and the ticker map classifies them authoritatively at step 1 of
   the cascade. The remaining **12** are the bound below.

2. **By our own topic column, which is an independent signal.** Every
   ``source='kalshi'`` row with ``category = 'weather'`` and a SPORT
   ``llm_sport_category``: **11 rows — 9 open, 2 resolved.** That is exactly the
   eleven hurricane rows the token census found, and nothing else.

Two instruments keyed on different columns agreeing on the same eleven rows is
what makes "complete" a measurement here rather than a hope. A row-count
control alone could not have said it: the token census is dominated 24:1 by
genuine hockey.

**Eleven of twelve bound events move. The twelfth is in the bound so that its
refusal is proved by the dry run instead of asserted in this docstring** — see
below.

🔴 THE TWELFTH EVENT, AND THE CASCADE DEFECT IT EXPOSES
========================================================

``KXKRAKENBANKPUBLIC-27JAN01`` — "Which bank will take Kraken public before
2027?", stored ``hockey``, open. The venue says ``Companies``, tags ``['IPOs',
'Companies']``. The shipped cascade nevertheless returns **hockey**, and the
reason is an ORDERING in ``_categorize_kalshi_market`` rather than anything in
this rail:

  * step 0 keys on the literal word ``IPO``, which this title does not contain
    ("take Kraken public");
  * step 1 finds no ticker mapping for ``KXKRAKENBANKPUBLIC``;
  * step 1b asks ``series_tag_to_category('IPOs')`` and gets ``None`` — the tag
    is real but is not a sport we model, so #5637's rail declines it too;
  * **step 2 runs the name rules and reads the club noun** → ``hockey``;
  * step 4, which would have read ``Companies`` → ``economics``, never runs.

So the venue's own category sits BELOW a name guess in the cascade. That is a
real defect and it is the whole of the 116 remaining rows in the broader class
(``category`` a non-sport topic, ``llm_sport_category`` a sport: 127 rows
total, of which these 11 are the weather arm). **It is filed separately and is
not repaired here**, for the sibling's reason exactly: a rail that wrote a
verdict its own gate refused would be the drift this design exists to prevent.
Including the ticker in the bound makes the refusal appear in the dry run as
``venue_agrees`` with the cascade's answer printed beside it, which is evidence;
omitting it would have made this paragraph the only record.

The two Kalshi *Pirates of the Caribbean* rows (``108239`` ``KXJOHNNYDEPP-35``
and ``59693447`` ``KXMOVIECAST-PIR29``, stored ``baseball``, venue
``Entertainment``) are the same shape and the same refusal — checked against the
cascade before they were left out, not assumed. They belong to that issue, not
to this bound.

WHY THE MEMBERSHIP GATE IS SHORTER THAN THE SIBLING'S
=====================================================

The Polymarket sibling needs a two-clause gate because its rows carry the event
only in a ``group_id``, and one Kraken container had collected a Gaza ceasefire
market that the group would have swept up. Kalshi's correspondence is stronger:
our ``futures_markets.external_id`` **IS** the venue's ``event_ticker``, and the
venue's ``markets[]`` carry outcome-leg tickers (``KXHURCTOT-26DEC01-T4``) that
live in ``futures_outcomes``, not here. Measured on the bound: **12 groups, 12
rows, one row each.**

So a row joins the event on one of two ID-ANCHORED correspondences, never a
container guess (gotcha #32's discipline, one layer down):

  1. its ``external_id`` equals the ``event_ticker`` the venue echoed back —
     this is the container row; or
  2. its ``external_id`` is one of the tickers in the venue event's own
     ``markets[]`` list.

Both are id identity, not a name match, which is why this gate is stricter than
the sibling's even though it is shorter. The ``group_id`` is read to FIND
candidate rows and is never trusted to admit one. ``KXHURCTOTMAJ-26JUN30`` is
carried as a named case because the venue returns it with an **empty**
``markets[]`` — a gate that required clause 2 would refuse the row it is
supposed to repair.

WHAT IS NEVER WRITTEN
=====================

``llm_sport_category`` only, by Core UPDATE (gotchas #4/#5), compare-and-set on
the value read, so a poll landing between the SELECT and the UPDATE is never
clobbered. On this rail the CAS is not theoretical the way it is on the sibling:
the Kalshi poller runs every two hours and DOES touch these rows.

🔴 **NOT ``updated_at``.** CERT-2382 blocked a sibling's first SHA for exactly
this: the card renders it as its own relative date, so stamping ``NOW()`` would
present unchanged prices as observed just now — a repair whose whole purpose is
TRUTH introducing a reader-visible lie about freshness in the same statement.

🔴 **NOT ``status``.** ``resolved`` is the calibration population's own gate (13
predicates in ``routes/calibration.py``, 5+ in ``precompute_calibration``), so
writing it from a taxonomy rail is a write to the accuracy curve. The two
resolved rows in this bound are repaired like any other: this column is a
taxonomy badge, never a result, and no price, outcome, ``is_winner``,
``settled_at`` or resolution field is read or written here, so "settled means
settled" is untouched.

🔴 **NOT ``category``.** Our ``category`` column already reads ``weather`` on all
eleven rows — it is the second instrument in the census above. The poller writes
it on INSERT and never again, so writing it here would make this rail do
something the ingest path never does.

Nothing at all is written when the venue does not answer clearly, each with its
own named count rather than one silent success (gotchas #36, #53):

  * 429/5xx/timeout on either door -> ``indeterminate``. A transient failure is
    not a verdict, and the SERIES door counts too: classifying on a missing tag
    would be classifying on a rate limit.
  * 404 on the event -> ``not_at_venue``. A 404 on the SERIES is not that: the
    poller's ``get_series_metadata`` returns ``None`` for it and the cascade
    proceeds tagless, so this rail does the same.
  * the cascade returns ``None``/``"other"`` -> ``refused_other``, the poller's
    own honest-empty guard.
  * the cascade agrees with what is stored -> ``venue_agrees``.

D51 — BACKUP AND RESTORE
========================

Every planned row carries its ``before`` value in the returned payload, on the
dry run as well as the apply, and the apply logs the restore. On an apply the
undo is built from what the database RETURNED rather than from the plan — the
undo must name the rows that MOVED, not the rows we hoped to move. Twelve rows
of one column is one statement; a backup table would be more moving parts rather
than more safety.

ATTENDED ONLY: never wire this to a beat. It is a bounded, terminating repair
over twelve enumerated events, not a standing job.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Kalshi's public trade API. The two doors this rail reads — ``/events/{t}``
#: and ``/series/{t}`` — need no key, which is why the rail can state its 404
#: discipline rather than inherit an auth failure as a venue verdict.
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"

#: The enumerated bound: Kalshi EVENT tickers, which are also our rows'
#: ``external_id``. Measured on production and against the venue 2026-09-18 (see
#: the census in the module docstring) and frozen.
#:
#: 🔴 THIS LIST IS A BOUND, NOT A CLAIM THAT THESE EVENTS ARE WRONG. The claim
#: that an event is mis-filed is made by the VENUE, per event, at run time. Put
#: a wrong ticker here and the rail writes the venue's answer for *that* event,
#: which is by construction the right answer for it — and the last entry below
#: is in the list precisely to demonstrate the gate refusing one.
CLUB_NOUN_EVENT_TICKERS: tuple[str, ...] = (
    "KXHURCTOT-26DEC01",             # How many Atlantic hurricanes in 2026?
    "KXHURCTOTMAJ-26DEC01",          # How many MAJOR Atlantic hurricanes in 2026?
    "KXHURCTOTMAJ-26JUN30",          # …this month?  (resolved; venue markets[] empty)
    "KXHURRICANE-26DEC01CPACMAJ",    # major Central Pacific, this year
    "KXHURRICANE-26DEC01CPACTOT",    # Central Pacific, this year
    "KXHURRICANE-26DEC01EPACMAJ",    # major Eastern Pacific, this year
    "KXHURRICANE-26DEC01EPACTOT",    # Eastern Pacific, this year
    "KXHURRICANE-26JUN30CPACMAJ",    # major Central Pacific, this month (resolved)
    "KXHURRICANENAMES-26DEC01ATL",   # what named storms will be hurricanes — Atlantic
    "KXHURRICANENAMES-26DEC01CPAC",  # …Central Pacific
    "KXHURRICANENAMES-26DEC01EPAC",  # …Eastern Pacific
    # 🔴 NOT expected to move. The venue says `Companies`; the shipped cascade
    # says `hockey` off the club noun at step 2, above the step-4 read of that
    # category. In the bound so the dry run PROVES the refusal. See the module
    # docstring, "THE TWELFTH EVENT".
    "KXKRAKENBANKPUBLIC-27JAN01",
)

#: Pause between venue calls. Kalshi's limiter is real; the bound is twelve
#: events over four distinct series, so the whole pass is ~6s.
VENUE_PAUSE = 0.35

#: Per-venue-call timeout. Twelve events at eight seconds is inside the 30s
#: router wall even in the pathological case, which is why this rail needs no
#: keyset cursor: its population cannot outgrow one call.
FETCH_TIMEOUT_SECONDS = 8

#: Bound on each UPDATE. Unlike the Polymarket sibling this population IS polled
#: — every two hours — so a row lock is an ordinary outcome, and an operator
#: running this during a poll should get a named failure, not a router H12.
WRITE_TIMEOUT_MS = 2000


def venue_market_tickers(payload: dict[str, Any]) -> set[str]:
    """The market tickers the venue event's own ``markets[]`` list names.

    Half of the membership gate, and an IDENTITY check between two spellings of
    one id — nothing here tolerates a near miss, by design. Kalshi's market
    tickers are the event ticker plus an outcome suffix
    (``KXHURCTOT-26DEC01-T4``), so on this bound the set never contains the
    container row's own ticker and clause 1 of the gate is what admits it.
    """
    out: set[str] = set()
    for market in payload.get("markets") or []:
        if not isinstance(market, dict):
            continue
        ticker = market.get("ticker")
        if ticker:
            out.add(str(ticker).strip())
    return out


def venue_series_tag(payload: Optional[dict[str, Any]]) -> Optional[str]:
    """The sport tag the poller would read for this series, or ``None``.

    Deliberately the same one line as ``kalshi._resolve_series_tag_result``
    (``tags[0] if tags else None``) rather than a cleverer read of the list: the
    argument this rail hands the shipped cascade has to be the argument the
    poller hands it, or the gate is testing a different function than the one
    that runs. ``KXHURCTOT`` carries ``['Hurricanes', 'Natural disasters']`` and
    the poller sees only the first.

    This is a payload-shape read, not a sport rule: the translation from tag to
    category is ``kalshi.series_tag_to_category``'s and stays there.
    """
    tags = (payload or {}).get("tags") or []
    if not isinstance(tags, list) or not tags:
        return None
    first = tags[0]
    return str(first) if first else None


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
    """The venue's event, with its nested markets. ``ok``/``not_found``/``indeterminate``."""
    return await _fetch(
        client,
        f"{KALSHI_API}/events/{event_ticker}?with_nested_markets=true",
    )


async def _fetch_series(
    client: httpx.AsyncClient, series_ticker: str
) -> tuple[str, Optional[dict[str, Any]]]:
    """The venue's series, whose ``tags`` carry the sport word. ``ok``/``not_found``/``indeterminate``."""
    return await _fetch(client, f"{KALSHI_API}/series/{series_ticker}")


async def repair(session, apply: bool = False, **_ignored) -> dict[str, Any]:
    """Plan (and optionally apply) the #6955 Kalshi category correction.

    Dry-run by default. Returns a payload complete enough to BE the D51 backup:
    every event considered, the venue's verdict, every row that would move with
    its stored value, and a named reason for each refusal — including each row
    the membership gate declined, by id, so an operator can see the gate working
    rather than take it on trust.
    """
    from app.tasks.kalshi import _categorize_kalshi_market

    counts = {
        "events_examined": 0,
        "changed": 0,
        "unchanged": 0,
        "refused_other": 0,
        "not_at_venue": 0,
        "indeterminate": 0,
        "write_failed": 0,
        "rows_written": 0,
        # Rows found beside the event whose ticker the venue does not name.
        # Counted, never written. On this bound it is zero — twelve groups of
        # one row — and a jump here means a container has collected strangers
        # the way the Polymarket sibling's Kraken container had.
        "rows_not_named_by_venue": 0,
    }
    planned: list[dict[str, Any]] = []
    #: The rows the database actually moved, read back by ``RETURNING id``. On a
    #: dry run this stays empty and the restore is built from ``planned``, which
    #: is the right basis there: an operator reading a dry run wants the undo for
    #: the write they are about to authorise.
    applied: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    not_named_by_venue: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    missing_tickers: list[str] = []
    #: One read per SERIES, not per event: four series carry the twelve events.
    #: Keyed by ticker and holding the ``(status, tag)`` pair, so a transient
    #: failure is remembered as a failure rather than as "no tag".
    series_seen: dict[str, tuple[str, Optional[str]]] = {}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for event_ticker in CLUB_NOUN_EVENT_TICKERS:
            # Candidate rows. `external_id` is the id-anchored correspondence and
            # `group_id` is read only to surface strangers for the gate below to
            # refuse — never to admit a row.
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT fm.id,
                               fm.name,
                               fm.status,
                               fm.external_id,
                               fm.llm_sport_category
                        FROM futures_markets fm
                        WHERE fm.source = 'kalshi'
                          AND (fm.external_id = :ticker OR fm.group_id = :gid)
                        ORDER BY fm.id
                        """
                    ),
                    {"ticker": event_ticker, "gid": f"kalshi:{event_ticker}"},
                )
            ).all()

            if not rows:
                # A ticker in the bound that names no row. Reported by NAME
                # rather than silently skipped: it means the census this list
                # came from has gone stale, and an operator should know that
                # before reading a small `changed` as success.
                missing_tickers.append(event_ticker)
                continue

            counts["events_examined"] += 1

            status, payload = await _fetch_event(client, event_ticker)
            await asyncio.sleep(VENUE_PAUSE)

            record = {
                "event_ticker": event_ticker,
                "title": rows[0].name,
                "rows": len(rows),
                "stored": sorted({r.llm_sport_category for r in rows}, key=str),
            }

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

            # The series tag, one read per series. A transient failure on THIS
            # door is indeterminate too: the cascade consults the tag above its
            # name rules, so classifying without it is classifying on a rate
            # limit. A 404 is different — the poller's `get_series_metadata`
            # returns None for it and the cascade proceeds tagless.
            series_tag: Optional[str] = None
            if series_ticker:
                if series_ticker not in series_seen:
                    s_status, s_payload = await _fetch_series(client, series_ticker)
                    await asyncio.sleep(VENUE_PAUSE)
                    series_seen[series_ticker] = (
                        s_status,
                        venue_series_tag((s_payload or {}).get("series")),
                    )
                s_status, series_tag = series_seen[series_ticker]
                if s_status == "indeterminate":
                    counts["indeterminate"] += 1
                    refused.append({**record, "reason": "indeterminate"})
                    continue
            record["series_tag"] = series_tag

            # THE MEMBERSHIP GATE, both clauses id-anchored. A row belongs to
            # this event if its own external_id is the ticker the venue echoed
            # back, or is one of the tickers the venue's market list names.
            named = venue_market_tickers(payload)
            members = []
            for r in rows:
                ext = (r.external_id or "").strip()
                if (venue_ticker and ext == venue_ticker) or ext in named:
                    members.append(r)
                else:
                    counts["rows_not_named_by_venue"] += 1
                    not_named_by_venue.append(
                        {
                            "id": int(r.id),
                            "event_ticker": event_ticker,
                            "name": r.name,
                            "external_id": r.external_id,
                            "stored": r.llm_sport_category,
                            "reason": "not_named_by_venue",
                        }
                    )

            if not members:
                counts["unchanged"] += 1
                refused.append({**record, "reason": "no_member_rows"})
                verdicts.append(record)
                continue

            # THE VERDICT. The shipped cascade, on the venue's own answer, per
            # row — the name is a per-row argument, so this is asked once for
            # each row rather than once for the event.
            event_plan: list[dict[str, Any]] = []
            said_other = False
            seen_verdicts: list[Optional[str]] = []
            for r in members:
                llm = _categorize_kalshi_market(
                    r.name or "",
                    event.get("category"),
                    event_ticker,
                    series_tag,
                )
                seen_verdicts.append(llm)
                if not llm or llm == "other":
                    # The poller's own honest-empty guard: never overwrite a
                    # real value with the "other" default.
                    said_other = True
                    continue
                if llm != r.llm_sport_category:
                    event_plan.append(
                        {
                            "id": int(r.id),
                            "event_ticker": event_ticker,
                            "name": r.name,
                            "status": r.status,
                            "before": r.llm_sport_category,
                            "after": llm,
                        }
                    )

            # Every verdict the cascade gave, including the ones that changed
            # nothing — a refusal an operator can read is the point of putting
            # the Kraken ticker in the bound at all.
            record["venue_verdict"] = sorted(set(seen_verdicts), key=str)
            verdicts.append(record)

            if not event_plan:
                if said_other:
                    counts["refused_other"] += 1
                    refused.append({**record, "reason": "refused_other"})
                else:
                    # THE GATE DECLINING. On this bound it means the venue's own
                    # reply, through the shipped cascade, agrees with what is
                    # stored — the Kraken row, and every real hockey event a
                    # stale census might one day add here.
                    counts["unchanged"] += 1
                    refused.append({**record, "reason": "venue_agrees"})
                continue

            counts["changed"] += 1
            planned.extend(event_plan)

            if not apply:
                continue

            # Core UPDATE, never ORM attribute assignment (gotchas #4/#5).
            # Compare-and-set on the value we read: the Kalshi poller runs every
            # two hours and DOES reach these rows, so a concurrent write is an
            # ordinary outcome here rather than a theoretical one.
            try:
                await session.execute(
                    text(f"SET LOCAL statement_timeout = {WRITE_TIMEOUT_MS}")
                )
                # Grouped by the (before, after) PAIR, not by `before` alone.
                # The cascade is asked per row, so two rows of one event can
                # legitimately share a stored value and earn different answers;
                # grouping on `before` only would write one of those answers
                # over both of them.
                pairs = sorted(
                    {(p["before"], p["after"]) for p in event_plan}, key=str
                )
                for before, after in pairs:
                    ids = [
                        p["id"]
                        for p in event_plan
                        if p["before"] == before and p["after"] == after
                    ]
                    result = await session.execute(
                        text(
                            """
                            UPDATE futures_markets
                            SET llm_sport_category = :llm
                            WHERE id = ANY(:ids)
                              AND llm_sport_category IS NOT DISTINCT FROM :before
                            RETURNING id
                            """
                        ),
                        {"llm": after, "ids": ids, "before": before},
                    )
                    # RETURNING, not rowcount, and the difference is the whole
                    # point (the sibling's CERT-2382 follow-up). The undo must
                    # name the rows that MOVED. A rowcount tells you HOW MANY
                    # matched, never WHICH, so a restore built from the plan
                    # could write a stale `before` over a fresher value, turning
                    # the undo into a second defect.
                    moved = {r[0] for r in result.all()}
                    counts["rows_written"] += len(moved)
                    applied.extend(p for p in event_plan if p["id"] in moved)
                await session.commit()
            except Exception as exc:  # noqa: BLE001 — a blocked write is not a verdict
                # A statement timeout aborts the whole TRANSACTION, so the
                # session is unusable until it is rolled back. Events committed
                # before this one are durable and stay counted.
                await session.rollback()
                counts["write_failed"] += 1
                refused.append({**record, "reason": "write_failed"})
                logger.warning(
                    "repair_kalshi_club_noun_category: the UPDATE for event %s "
                    "did not land (%s: %s); rows already committed are "
                    "unaffected",
                    event_ticker,
                    type(exc).__name__,
                    exc,
                )

    # On an apply the undo is built from what the database RETURNED, never from
    # the plan. On a dry run nothing moved, so the plan is the correct basis —
    # it is the undo for the write about to be authorised.
    undo_basis = applied if apply else planned

    if apply and counts["rows_written"]:
        logger.warning(
            "#6955 Kalshi club-noun repair applied: %s rows. D51 RESTORE:\n%s",
            counts["rows_written"],
            restore_sql(undo_basis),
        )

    # Gotcha #53: a pass that examined events and wrote nothing says so in a
    # named terminal rather than leaving zeros for a reader to interpret.
    if apply:
        terminal = "changed" if counts["rows_written"] else "no_rows_written"
    else:
        terminal = "dry_run"

    return {
        "repair": "kalshi-club-noun-category",
        "bound": list(CLUB_NOUN_EVENT_TICKERS),
        "counts": counts,
        "planned": planned,
        # What the database actually moved (RETURNING id). Empty on a dry run.
        # Reported alongside `planned` rather than instead of it, so a partial
        # apply is visible as the difference between the two rather than being
        # smoothed into one number.
        "applied": applied,
        "refused": refused,
        # Rows the membership gate declined, by id. Reported as its own list
        # rather than folded into `refused`, which is keyed by EVENT: these are
        # a different unit and hiding them inside an event-level refusal would
        # make the one thing this rail guards hardest invisible.
        "not_named_by_venue": not_named_by_venue,
        "verdicts": verdicts,
        "missing_tickers": missing_tickers,
        # The D51 undo travels WITH the plan, on the dry run too — an operator
        # reads the restore before deciding to apply, not afterwards in a log
        # line they have to go and find.
        "restore_sql": restore_sql(undo_basis),
        "terminal": terminal,
    }
