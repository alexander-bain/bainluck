"""Q460 — the fast lane's last mile: WebSocket price -> the number on the card.

WHAT WAS BROKEN. `worker-ws` has been streaming Kalshi prices into
`futures_outcomes.current_probability` in production for months, sub-second,
and none of it was visible. Measured 2026-08-30 18:32 UTC: 4 of 10 live Kalshi
outcomes moved inside a 25-second window, while `Event.win_probability_sources`
— the JSONB every hero and every card actually renders — advanced only on the
120-second `poll_live_prediction_markets` pass. Sampled three times across 90s,
the Kalshi blend stamp read 54s / 0s / 24s old: a clean 120s sawtooth. The fast
lane existed, worked, and stopped one table short of the number.

Alex's own specimen (Hawaii @ Stanford, 2026-08-29) is the cost. That event's
blend carried exactly one prediction-market source, and its in-game snapshots
land 240s / 360s / 600s / 1200s apart. A number that moves every four to twenty
minutes during a football game is what "constantly behind the action" means.

WHAT THIS DOES. After the WS flushes prices for a batch of outcomes, it hands
the affected event ids here. For each, this recomputes that source's home
probability from the rows the flush just wrote — via
`app/utils/live_blend.py`, the SAME expression the 120s poll uses, so the two
writers cannot disagree — and stamps `win_probability_sources`. Since Q501 it
also appends the matching `win_prob_snapshots` point, so the CHART moves on the
same beat as the number.

THE CHART POINT (Q501). This module originally declined to write
`win_prob_snapshots` on the grounds that a snapshot per tick would grow that
table ~60x for resolution nobody can see. That reasoning was about *per-tick*
writes, and it is still right — so the write is throttled on its own clock
(`DEFAULT_SNAPSHOT_INTERVAL_S`, 25s) rather than the blend's 2s one, and it goes
through the same `_create_or_update_win_prob_snapshot` helper the 120s poll uses,
which appends a row only when the value actually CHANGES and otherwise just
bumps `reading_count`/`valid_until` on the existing point. Upper bound is
therefore ~4.8x the 120s poll on a continuously-moving market and 0x on a flat
one — not 60x. What it buys is Alex's stated bar: a live match page gains a
chart point within a minute instead of within two.

Committed chart points have one finite FIFO owner for the consumer run.
Each point freezes its original database stamp time; chart transactions share
the existing three-session ceiling with preparation and quote stamps. A single
admitted event keeps its direct read/write path; multiple events prepare each fresh/pending
population, then commit one event per transaction. Fresh worker tails reread
current quotes in their write session. Fresh stamps
do not wait for older debt's preparation reads. Earlier
completed events publish and release their row locks while later events still
do stamp work. A waiting first event still delays later stamps, but cannot hold
an earlier event's committed stamp or publication.

THREE THINGS IT DELIBERATELY DOES NOT DO.

* **It does not go through Celery.** It is called in-process on the `worker-ws`
  dyno. The background queue is a known congestion point (GIN beat starvation),
  and a fast lane queued behind a slow one is not a fast lane.
* **It does not re-derive the inversion verdict per tick.**
  `_check_and_fix_inversion` costs a per-event `odds_snapshots` lookup, which is
  affordable every 120 seconds and not every 2. Orientation is a property of the
  LINKAGE, not of the price, so it is computed once and cached — and the 120s
  poll re-derives it authoritatively regardless, which bounds how long a wrong
  verdict can survive to one poll interval.

SAFETY POSTURE. Every failure here is swallowed and counted. This runs inside
the WS consumer's flush loop, and a blend refresh that raises must never take
down the price streaming that is the dyno's actual job (gotcha #42, one bad item
must not wipe the pass).
"""

from __future__ import annotations

from asyncio import CancelledError
import asyncio
import contextlib
from contextvars import ContextVar
from collections import deque
import itertools
import logging
import math
import os
import time
from dataclasses import dataclass, replace as _replace
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Awaitable, Callable, Container, Iterable, Optional

logger = logging.getLogger(__name__)

#: One receipt per preview capacity pass (#10090). Read beside the ledger's
#: `status=full` ALARM lines. Reservation maintenance can return compatible
#: residents below the total cap too; no_candidates alone does not identify
#: owner incompatibility. Counts describe the pass's observed residents,
#: not unmet demand or guaranteed admission. `live_over_6h` / `oldest_live_h`
#: identify older live residents. `idle` is
#: the ledger's hint of residents holding no valid pending preview;
#: `idle_attempted` counts idle reclaims tried (each re-proved under a row
#: lock, so a busy or protected row retires nothing). `end=deadline` means
#: the pass's one-second budget ran out before the next idle reclaim could
#: start. `attempted` stays the missing + retirable count.
#: `policy_attempted` counts idle residents offered to full-bucket policy
#: retirement, and `reclaimed` counts the idle + policy retirements Redis
#: acknowledged this pass, so a reclaim that never lands is visible. Report
#: only: nothing here changes admission, retirement, cap or TTL.
PREVIEW_CAPACITY_RECEIPT_FORMAT = (
    "live_blend_refresh[%s]: preview capacity pass end=%s candidates=%d missing=%d "
    "retirable=%d attempted=%d live=%d scheduled=%d suspended=%d other=%d "
    "live_over_6h=%d oldest_live_h=%s idle=%d idle_attempted=%d "
    "policy_attempted=%d reclaimed=%d")
#: Most idle residents one capacity pass offers each retirement path (#10090).
#: Each path proves its whole batch in ONE locked DB statement and sends it on
#: ONE Redis connection; one statement and one lock wait per resident spent
#: the pass's one-second budget before the pass reached most of them.
PREVIEW_CAPACITY_BATCH = 32
PREVIEW_CAPACITY_LIVE_OLD_HOURS = 6.0


#: Per-event floor between fast-lane recomputes, equal to the WS's 2s flush:
#: every flush that carries a new price for an event may stamp it. It was 5s
#: (the 2026-08-30 "<=1 change/~5s" live look), which on a liquid market kept
#: real prices off the page — Alex's required benchmark (Angelini v Johns,
#: 2026-09-28) moves Kalshi 77 -> 80 -> 85 -> 84 two seconds apart, and at 5s
#: the 85 was stored and never stamped. The write rate stays bounded by the
#: flush itself, by the unchanged-value arm (45s, below) and by the chart's own
#: 25s clock; what 2s adds is up to one blend UPDATE per moving event per flush.
DEFAULT_MIN_REFRESH_INTERVAL_S = 2.0

#: How long an event whose batch FAILED waits before it is attempted again —
#: the 5s the success floor used to give it for free. A failed transaction is
#: usually a database in trouble, and at the 2s floor every flush would open a
#: fresh session against it for the same owed stamp. Row-lock retries are not
#: failures and stay due at once.
DEFAULT_FAILED_RETRY_INTERVAL_S = 5.0

#: #11317 P2 — the longest a bundled pair the current-book proof refused waits
#: with none of its proof inputs changed before it is read again. One shared
#: sweep for every parked pair, so a quiet refused slate costs one read every
#: sweep instead of one per pair per 2 s floor. A change to any input the proof
#: reads wakes the pair at once (`current_book_signature`); the sweep is the
#: backstop for a row another writer changed (the poll).
BOOK_REFUSED_SWEEP_S = 10.0

#: How long a cached inversion verdict stays good. One poll interval plus slack:
#: the 120s poll re-derives it authoritatively, so this never has to be the
#: durable answer, only a cheap one that cannot be stale for long.
DEFAULT_INVERSION_TTL_S = 150.0

#: When the recomputed value rounds to what is already stored, the write is
#: still worth making occasionally — `updated_at` is what drives the hero's
#: recency decay (#1829), so a source that goes quiet must still look ALIVE
#: rather than progressively losing weight. Just not on every flush.
#:
#: #5661 — and only when the venue WAS re-read. "Quiet" and "dead" recompute
#: the same number from the same rows; see `restamp_records_no_observation`.
UNCHANGED_RESTAMP_INTERVAL_S = 45.0

#: Per-event floor between fast-lane CHART points. Deliberately slower than the
#: blend's 2s throttle: the number wants to be as live as the socket, the line
#: only has to gain a point often enough that a watching user sees it grow.
#: 25s clears Alex's "within a minute" bar with margin while keeping
#: `win_prob_snapshots` growth to a small multiple of the 120s poll's.
DEFAULT_SNAPSHOT_INTERVAL_S = 25.0

#: live/035 — the CADENCE FLOOR, which is a different promise from the throttle
#: above. The throttle is a ceiling on how often a moving market may write; this
#: is a floor under how long a FLAT one may stay silent. Both are needed: without
#: the floor, `_create_or_update_win_prob_snapshot` writes nothing at all while
#: the price holds, so a tense goalless half draws as one straight segment
#: between its endpoints. 60s is Alex's stated bar and bounds the cost at one row
#: per minute per source per live event.
DEFAULT_SNAPSHOT_MAX_GAP_S = 60.0

#: #837 tail — the longest one event's stamp may QUEUE behind another
#: transaction's lock on its `events` row before it gives up and retries on the
#: next flush. Production 2026-09-24 23:16:09–23:16:20Z: the Polymarket arm's
#: stamp of one game waited 10.6s on a row a worker-realtime transaction held,
#: and because a batch is one transaction inside a serial flush loop, every
#: OTHER game's price froze with it — Brewers @ Phillies moved on the venue at
#: 23:16:12.452 and reached the page at 23:16:24.2. In that 32-minute capture the
#: arm waited >1s 34 times (17 of them ≥5s, 240s in all). Under the server's 1s
#: `deadlock_timeout` on purpose: a stamp that has stopped waiting cannot be the
#: party a deadlock is detected on, and cannot be the convoy the sibling arm
#: queues behind.
#:
#: #11138 — and the stamp's UPDATE carries the same number as its
#: `statement_timeout` (`SET_LOCK_AND_STATEMENT_TIMEOUT_SQL`). `lock_timeout` bounds
#: each lock ACQUISITION, and a row wait is several: the tuple-lock queue, then
#: the holder's transaction, then any writer that took the row first. Each
#: stayed under 500 ms while the statement did not — `pg_stat_statements` max
#: 15.97 s for this UPDATE since 2026-09-27, and v5763 10:36:27Z: Kalshi's stamp
#: of PM 15331282 wrote its clock at .419 and committed ~29.2, so the PM stamp
#: queued behind it gave up at 28.625 and published at 29.258 (1.39 s after the
#: quote). Local PG 14, holder then queued writer: 0.876 s under `lock_timeout`
#: alone, cancelled at 0.65 s with the statement bound.
DEFAULT_STAMP_LOCK_TIMEOUT_MS = 500

def _owed_budget_env(name, default, cast, low, high):
    """#10090 — read one owed-stamp budget setting from the environment.

    Read once at import. Missing or blank is the default; unparseable or
    non-finite is the default with one warning; out of range is clamped to
    [low, high] with one warning.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw.strip())
    except (TypeError, ValueError):
        value = None
    if value is None or (not isinstance(value, int) and not math.isfinite(value)):
        logger.warning(
            "live_blend_refresh: %s=%r is not a valid %s; using %r",
            name, raw, cast.__name__, default,
        )
        return default
    clamped = min(max(value, low), high)
    if clamped != value:
        logger.warning(
            "live_blend_refresh: %s=%r is outside [%r, %r]; using %r",
            name, raw, low, high, clamped,
        )
    return clamped


#: #10090 WORST bucket 1 — the optional reads below (normal ACK settlement and
#: durable normal recovery, each 0.25 s; preview capacity maintenance, inside its
#: 1 s pass) end at their deadline by cancelling the in-flight asyncpg execute.
#: SQLAlchemy handles that cancel as a disconnect, invalidates the pooled
#: connection and closes it, and the next checkout pays a new Postgres
#: connection with a cold statement cache, which itself can outlast 0.25 s.
#: Production 2026-10-28 21:49–21:59Z: ~225 such cancels on these reads (and
#: 500 more on the observation preview, which PR #11700 owns), every one of
#: worker-ws's 9–10 backends under 78 s old on a dyno up 90 minutes, and
#: Kalshi's slowest flush spending up to 8.9 s in checkout and connection
#: setup. Set to 1, the caller still stops waiting at the same deadline and
#: gets the same TimeoutError, but the read is ABANDONED, not cancelled: it
#: finishes on its own task and returns its connection to the pool. Default
#: off. Read at call time; a config var change restarts the dyno anyway.
OPTIONAL_DB_ABANDON_ENV = "LIVE_BLEND_ABANDON_OPTIONAL_DB"
#: An abandoned read still holds its session slot and connection; one that has
#: not finished this long after it started is cancelled after all.
OPTIONAL_DB_ABANDON_LIMIT_S = 5.0


class OptionalDbAbandoned(TimeoutError):
    """The deadline passed and the read was left to finish on its own task."""


def optional_db_abandons() -> bool:
    return os.getenv(OPTIONAL_DB_ABANDON_ENV, "").strip().lower() in ("1", "true", "on", "yes")


#: Its runtime trial name (`app.tasks.speed_switches`). ``alternate`` abandons
#: every read in the "on" periods: the switch acts on the shared connection
#: pool, so alternating periods is its faithful comparison. ``ab`` abandons only
#: the reads whose games are ALL in the trial's half (one event-id parity), so no
#: game outside the half ever has a switched read; a read about games of both
#: halves stays off, and so does the normal recovery page read, which names no
#: game until it returns. Its effect still reaches both halves' deliveries
#: through the pool.
OPTIONAL_DB_SWITCH = "abandon_optional_db"
#: `FRESH_FLUSH_PENDING_ATTEMPTS`'s runtime trial name: ``alternate`` between two
#: values by period, read once per flush (`_fresh_flush_pending_attempts`).
PENDING_ATTEMPTS_SWITCH = "pending_attempts"
#: `ADMITTED_DEBT_SLOTS`'s runtime trial name: ``alternate`` between two values
#: by period, read once per door admission (`_admitted_debt_slots`).
ADMITTED_DEBT_SLOTS_SWITCH = "admitted_debt_slots"
#: #10090 R8b runtime trial (``alternate`` 0/1, today 0), read once per mixed
#: `refresh` (`_release_unattempted_debt`): a call releases from its fence the
#: old events it will not attempt as soon as it knows which those are — before
#: its fresh stamps when the choice needs no read, else when the old
#: population's live-first read returns — instead of after the fresh stamps.
RELEASE_UNATTEMPTED_DEBT_SWITCH = "release_unattempted_debt"
#: #10090 runtime trial (``alternate`` 0/1, today 0), read once per cohort a
#: catalog handover carries over committed (`keep_committed`): on, the next
#: `refresh` stamps those events as its fresh population instead of as old debt
#: under the per-flush allowance. Production 2026-10-29 15:36:25Z: one handover
#: turned 18 bridged events into debt at once; FRESH_FLUSH_PENDING_ATTEMPTS=3
#: let about three through per call, so the last waited 10.5 s.
HANDOVER_FRESH_SWITCH = "handover_fresh"
#: `ADMITTED_STAMP_BATCH`'s runtime trial name: ``alternate`` between two values
#: by period, read once per admitted worker turn that could batch
#: (`_admitted_stamp_batch`).
ADMITTED_STAMP_BATCH_SWITCH = "admitted_stamp_batch"
#: `ADMITTED_LIVE_BATCH`'s runtime trial name: ``alternate`` between two values
#: by period, read once per admitted worker turn whose pick is a live game with
#: more live games queued (`_admitted_live_batch_size`).
ADMITTED_LIVE_BATCH_SWITCH = "admitted_live_batch"
#: #10090 runtime trial (``alternate`` 0/1, today 0), read once per debt drain
#: that a caller says is deferred only by a buffered, not yet written withdrawal
#: (`withdrawing_event_ids`): on, an already committed throttle-deferred price
#: is stamped past it. Production 2026-10-29 17:35:36Z: 15331111's committed
#: price waited 45 s while its legs drew thousands of wide books a minute, each
#: one re-buffering a withdrawal that priced nothing out; none was written
#: in flight, yet every flush's drain excluded the event.
OWED_PAST_WITHDRAWAL_SWITCH = "owed_past_withdrawal"
#: #10090 runtime trial (``alternate`` 0/1, today 0), read once per row-lock
#: skip (`_lock_retry_prompt`): on, a stamp that gave up on a row lock is
#: attempted again as a later call's FRESH population once its delay below has
#: passed, instead of joining the back of the owed queue. That queue drains one
#: event per fresh-bearing flush (FRESH_FLUSH_PENDING_ATTEMPTS) plus one per door
#: admission (ADMITTED_DEBT_SLOTS), so on a busy socket the lock-skipped price
#: waited out every event owed ahead of it. Production 2026-10-29 17:40:49.7Z:
#: Kalshi event 15335270 skipped once and was stamped 97.8 s later with no
#: attempt in between.
LOCK_RETRY_PROMPT_SWITCH = "lock_retry_prompt"
#: How long after the Nth skip in a row (N from 0) its prompt attempt is due.
#: Its length is the bound: a row still locked after these many prompt attempts
#: is ordinary debt again, so a lock that persists costs at most these attempts
#: (each behind the same statement bound), never a loop.
LOCK_RETRY_PROMPT_DELAYS_S = (1.0, 2.0, 4.0)
#: #10090 runtime trial (``alternate`` 0/1, today 0), read when a debt drain or
#: door admission finds a lock retry deferred only by a buffered, not yet
#: written withdrawal (`withdrawing_event_ids`): on, the retry is taken past
#: it as `owed_past_withdrawal` takes throttle-deferred debt, its prompt
#: included. Production 2026-10-29: PM lock holds were 22.9% of held seconds,
#: on the busy wide-book games whose buffer never clears, so a due
#: `lock_retry_prompt` stayed out flush after flush.
LOCK_RETRY_PAST_WITHDRAWAL_SWITCH = "lock_retry_past_withdrawal"
#: #10090 runtime trial (``ab``/``alternate`` 0/1, today 0), read per event when
#: a committed price write hands its RETURNING rows over (`note_committed_rows`):
#: on, a live event's preview is composed from those rows patched into the
#: refresher's last read graph and proposed at once, with that read's ticket,
#: revision and base, before the stamp's own session, ticket and SELECT. Redis
#: refuses an open on a stale ticket (`read_required`) and an older context
#: that would change the event's class (`stale_context`; a same-class one
#: passes, `keep_class`); a continue is guarded by its chain, which every
#: retire/terminal removes. The ordinary refresh runs behind it either way, so
#: a refusal costs only the head start. Production 2026-10-29
#: 23:28-23:52Z (discover): live recv->stamped_at p50 187 ms Kalshi / 279 ms PM,
#: about half of it after the price commit.
PREVIEW_FROM_COMMIT_SWITCH = "preview_from_commit"
#: How old a cached read graph may be when a commit is composed onto it. The
#: rows this process commits are patched in; a write by another process (a
#: REST-poll price, a backfill or sweep settlement, an event status change) is
#: unseen until the next read. This is a TRUTH window, not just a speed knob:
#: for up to this long a preview may be composed over such a change, until the
#: ordinary refresh behind it corrects it. Raising it needs a fresh review.
PREVIEW_GRAPH_MAX_AGE_S = 3.0
#: How long a committed row is noted for a read already in flight to patch in:
#: past the graph age, so no graph young enough to compose can predate it.
PREVIEW_NOTE_RETENTION_S = 2 * PREVIEW_GRAPH_MAX_AGE_S
#: Live preview events whose last read graph is kept (oldest read dropped).
PREVIEW_GRAPH_MAX_EVENTS = 512
#: The outcome columns a committed price write returns and the patch replaces.
#: A row missing any of them is not patched (its event is not composed).
COMMIT_PATCH_FIELDS = ("current_probability", "last_updated", "is_winner", "resolution_source")
#: #10090 `preview_at_receipt` (speed switch, default off): a live event's
#: preview is composed from the prices the socket just RECEIVED, before their
#: price write, on the refresher's last read graph (the stamp's own read: its
#: rows, ticket, revision and committed bag), and proposed through the same
#: ledger. The write and the stamp run unchanged behind it; the stamp's commit
#: retires the preview once it carries that observation. Composition runs on
#: its own task, never in a flush or a stamp. Which venues it applies to is
#: `PREVIEW_AT_RECEIPT_VENUES_ENV`.
PREVIEW_AT_RECEIPT_SWITCH = "preview_at_receipt"
#: ``polymarket`` (default), ``kalshi`` or ``all``: the venues whose refresher
#: the switch turns on. Both reach the same receipt seam (`HeldRowQuotes.
#: note_input`), so one switch serves both; anything else reads ``polymarket``.
PREVIEW_AT_RECEIPT_VENUES_ENV = "PREVIEW_AT_RECEIPT_VENUES"
#: At most one receipt preview per event per this long. A burst of ticks for
#: one game is coalesced into its newest prices; an event quiet for this long
#: is composed on its first tick with no wait. 0.25 s adds at most a quarter
#: second to a moved price (the target is well under one second) and caps one
#: game at four compositions a second however fast its book ticks.
RECEIPT_PREVIEW_INTERVAL_S = 0.25
#: Speed may set the interval (seconds, 0.05-2.0) without a release; anything
#: else keeps `RECEIPT_PREVIEW_INTERVAL_S`. Read per worker pass.
RECEIPT_PREVIEW_INTERVAL_ENV = "PREVIEW_AT_RECEIPT_INTERVAL_S"
#: How old the read graph a receipt is composed onto may be. Only the rows'
#: structure (markets, ranks, statuses, the committed bag) comes from it: every
#: leg the socket received since is overlaid from memory. A write by another
#: process to a leg NOT received since, a settlement or an event status change
#: is unseen for up to this long; the stamp behind it corrects or revokes the
#: preview. A TRUTH window like `PREVIEW_GRAPH_MAX_AGE_S`: wider because a
#: held game's next stamp read is 13-21 s away under load (2026-10-31), and a
#: graph that old is exactly the case this exists for. Review before raising.
RECEIPT_GRAPH_MAX_AGE_S = 60.0
#: Speed may set the graph age (seconds, 3-60) without a code change; anything
#: else keeps `RECEIPT_GRAPH_MAX_AGE_S`. 60 = the preview's own lifetime: the
#: graph is the stamp read the page already shows, so a receipt on it is never
#: older than the screen (2026-10-31: 15 s dropped ~28% of PM live compositions
#: to the stamp path exactly when stamps queued).
RECEIPT_GRAPH_MAX_AGE_ENV = "PREVIEW_AT_RECEIPT_GRAPH_MAX_AGE_S"
#: The receipt worker logs its cumulative `receipt_preview_stats` at most this often.
RECEIPT_STATS_LOG_INTERVAL_S = 60.0
#: Received quotes are kept this long for the overlay: the preview's own
#: uncommitted lifetime (`blend_preview.DEFAULT_MAX_UNCOMMITTED_S`).
RECEIPT_QUOTE_RETENTION_S = 60.0


def _optional_db_key(event_ids) -> Optional[int]:
    """An event id standing for a read's games when all share one id parity, else None.

    None keeps the read off in an ``ab`` trial: a read about games of both halves
    would otherwise be switched for games outside the trial's half.
    """
    try:
        ids = [int(event_id) for event_id in event_ids]
    except (TypeError, ValueError):
        return None
    if not ids or len({event_id % 2 for event_id in ids}) != 1:
        return None
    return ids[0]


def _fresh_flush_pending_attempts() -> int:
    """This flush's old-stamp allowance: a running alternation's arm, else the setting."""
    try:
        return _optional_db_trial().value(PENDING_ATTEMPTS_SWITCH, FRESH_FLUSH_PENDING_ATTEMPTS)
    except Exception:  # noqa: BLE001 — a switch read never fails a flush
        return FRESH_FLUSH_PENDING_ATTEMPTS


def _admitted_debt_slots() -> int:
    """This admission's debt slots: a running alternation's arm, else the setting."""
    try:
        return _optional_db_trial().value(ADMITTED_DEBT_SLOTS_SWITCH, ADMITTED_DEBT_SLOTS)
    except Exception:  # noqa: BLE001 — a switch read never fails an admission
        return ADMITTED_DEBT_SLOTS


def _admitted_stamp_batch() -> int:
    """This worker turn's batch size: a running alternation's arm, else the setting."""
    try:
        return _optional_db_trial().value(ADMITTED_STAMP_BATCH_SWITCH, ADMITTED_STAMP_BATCH)
    except Exception:  # noqa: BLE001 — a switch read never fails a stamp
        return ADMITTED_STAMP_BATCH


def _admitted_live_batch_size() -> int:
    """This worker turn's LIVE batch size: a running alternation's arm, else the setting."""
    try:
        return _optional_db_trial().value(ADMITTED_LIVE_BATCH_SWITCH, ADMITTED_LIVE_BATCH)
    except Exception:  # noqa: BLE001 — a switch read never fails a stamp
        return ADMITTED_LIVE_BATCH


def _release_unattempted_debt() -> bool:
    """This call's `release_unattempted_debt` arm; off on any switch error."""
    try:
        return bool(_optional_db_trial().value(RELEASE_UNATTEMPTED_DEBT_SWITCH, 0))
    except Exception:  # noqa: BLE001 — a switch read never fails a flush
        return False


def _handover_fresh() -> bool:
    """This hand-over's `handover_fresh` arm; off on any switch error."""
    try:
        return bool(_optional_db_trial().value(HANDOVER_FRESH_SWITCH, 0))
    except Exception:  # noqa: BLE001 — a switch read never fails a hand-over
        return False


def _owed_past_withdrawal() -> bool:
    """This drain's `owed_past_withdrawal` arm; off on any switch error."""
    try:
        return bool(_optional_db_trial().value(OWED_PAST_WITHDRAWAL_SWITCH, 0))
    except Exception:  # noqa: BLE001 — a switch read never fails a flush
        return False


def _lock_retry_prompt() -> bool:
    """This row-lock skip's `lock_retry_prompt` arm; off on any switch error."""
    try:
        return bool(_optional_db_trial().value(LOCK_RETRY_PROMPT_SWITCH, 0))
    except Exception:  # noqa: BLE001 — a switch read never fails a stamp
        return False


def _lock_retry_past_withdrawal() -> bool:
    """This drain's `lock_retry_past_withdrawal` arm; off on any switch error."""
    try:
        return bool(_optional_db_trial().value(LOCK_RETRY_PAST_WITHDRAWAL_SWITCH, 0))
    except Exception:  # noqa: BLE001 — a switch read never fails a flush
        return False


_NOT_RETURNED = object()


def _field_ranks(prices) -> list:
    """Each leg's `rank` under `field_rank_expr` (``rank()``, DESC NULLS LAST,
    ties share a number): what a write's re-rank of the market stores."""
    keys = [(0, 0.0) if price is None else (1, float(price)) for price in prices]
    return [1 + sum(other > key for other in keys) for key in keys]


def _patched_group(group, returned: dict) -> Optional[list]:
    """``group`` with each committed row in ``returned`` (outcome id -> its
    `COMMIT_PATCH_FIELDS`) newer than the graph's copy patched in. Rows are
    replaced, never mutated. None when a patched market's cached `rank`s are
    not what its write's re-rank (`rerank_market_fields_stmt`) stores."""
    from types import SimpleNamespace

    patched = []
    for entry in group:
        outcomes, changed = [], False
        for row in entry.outcomes:
            values = returned.get(row.id)
            stored = getattr(row, "last_updated", None)
            if values is None or (stored is not None and values["last_updated"] <= stored):
                outcomes.append(row)
            else:
                outcomes.append(SimpleNamespace(**{**vars(row), **values}))
                changed = True
        if not changed:
            patched.append(entry)
            continue
        if [row.rank for row in outcomes] != _field_ranks(
                [row.current_probability for row in outcomes]):
            return None
        patched.append(_replace(entry, outcomes=outcomes))
    return patched


def _unoverlaid_group(group, original_rows: dict, originals: dict) -> Optional[list]:
    """``group`` with every held-quote copy (`HeldRowQuotes.overlay_event`)
    replaced by the row as read; None if one cannot be found. New entries:
    the caller's group is never mutated."""
    restored = []
    for entry in group:
        if all(id(row) in original_rows for row in entry.outcomes):
            restored.append(entry)
            continue
        outcomes = [row if id(row) in original_rows else originals.get(row.id)
                    for row in entry.outcomes]
        if any(row is None for row in outcomes):
            return None
        restored.append(_replace(entry, outcomes=outcomes))
    return restored


def _prune_notes(notes: dict, now: float, noted_at) -> None:
    """Drop notes older than `PREVIEW_NOTE_RETENTION_S` (oldest first)."""
    while notes:
        key = next(iter(notes))
        if now - noted_at(notes[key]) <= PREVIEW_NOTE_RETENTION_S:
            break
        del notes[key]


def forget_preview_outcomes(refresher, outcome_ids) -> None:
    """`LiveBlendRefresher.forget_preview_outcomes` on the refresher a writer
    holds, for rows it changed outside a price write. Nothing for a refresher
    without it. Never raises."""
    forget = getattr(refresher, "forget_preview_outcomes", None)
    if callable(forget):
        with contextlib.suppress(Exception):
            forget(list(outcome_ids))


def _preview_from_commit_possible() -> bool:
    """Whether any event may have `preview_from_commit` on now; False on error."""
    try:
        trial = _optional_db_trial()
        return (trial.state(PREVIEW_FROM_COMMIT_SWITCH).mode != "off"
                or bool(trial.value(PREVIEW_FROM_COMMIT_SWITCH, 0)))
    except Exception:  # noqa: BLE001 — a switch read never fails a read or write
        return False


def _preview_from_commit(event_id) -> bool:
    """This event's `preview_from_commit` arm; off on any switch error."""
    try:
        trial = _optional_db_trial()
        if trial.state(PREVIEW_FROM_COMMIT_SWITCH).mode == "ab":
            return trial.arm(PREVIEW_FROM_COMMIT_SWITCH, int(event_id))
        return bool(trial.value(PREVIEW_FROM_COMMIT_SWITCH, 0))
    except Exception:  # noqa: BLE001 — a switch read never fails a write
        return False


def _receipt_graph_max_age() -> float:
    """`RECEIPT_GRAPH_MAX_AGE_ENV` when set to 3-60, else the default."""
    try:
        value = float(os.environ[RECEIPT_GRAPH_MAX_AGE_ENV])
    except (KeyError, ValueError):
        return RECEIPT_GRAPH_MAX_AGE_S
    return value if 3.0 <= value <= 60.0 else RECEIPT_GRAPH_MAX_AGE_S


def _receipt_interval() -> float:
    """`RECEIPT_PREVIEW_INTERVAL_ENV` when set to 0.05-2.0, else the default."""
    try:
        value = float(os.environ[RECEIPT_PREVIEW_INTERVAL_ENV])
    except (KeyError, ValueError):
        return RECEIPT_PREVIEW_INTERVAL_S
    return value if 0.05 <= value <= 2.0 else RECEIPT_PREVIEW_INTERVAL_S


def _receipt_venue(source) -> bool:
    """Whether `PREVIEW_AT_RECEIPT_VENUES_ENV` names this source's venue."""
    venues = os.getenv(PREVIEW_AT_RECEIPT_VENUES_ENV, "").strip().lower()
    if venues not in ("polymarket", "kalshi", "all"):
        venues = "polymarket"
    return venues == "all" or venues == source


def _preview_at_receipt_possible(source) -> bool:
    """Whether any of this source's events may preview at receipt now."""
    try:
        if not _receipt_venue(source):
            return False
        trial = _optional_db_trial()
        return (trial.state(PREVIEW_AT_RECEIPT_SWITCH).mode != "off"
                or bool(trial.value(PREVIEW_AT_RECEIPT_SWITCH, 0)))
    except Exception:  # noqa: BLE001 — a switch read never fails a read or write
        return False


def _preview_at_receipt(source, event_id) -> bool:
    """This event's `preview_at_receipt` arm; off on any switch error."""
    try:
        if not _receipt_venue(source):
            return False
        trial = _optional_db_trial()
        if trial.state(PREVIEW_AT_RECEIPT_SWITCH).mode == "ab":
            return trial.arm(PREVIEW_AT_RECEIPT_SWITCH, int(event_id))
        return bool(trial.value(PREVIEW_AT_RECEIPT_SWITCH, 0))
    except Exception:  # noqa: BLE001 — a switch read never fails a write
        return False


def _switch_tags(event_id, at: Optional[float] = None) -> str:
    """`` sw=<name>:<arm>`` for each running speed-switch trial, else empty.

    ``at`` is the wall time the line describes; default now. A tail receipt's
    arm is the one in force when its drain attempt closed, not the arms its
    stamp waited through.
    """
    try:
        return _optional_db_trial().tags(int(event_id), at)
    except Exception:  # noqa: BLE001 — a receipt line never fails on its tag
        return ""


def _optional_db_trial():
    from app.tasks.speed_switches import speed_switches

    return speed_switches()


class _CapacityReadGate:
    """Where an optional read is, so its deadline abandons only the read.

    ``reading`` covers checkout through the first result; past it the body is
    in Redis work that the pass deadline still cancels, as it always did.
    ``abandoned`` tells a body whose read outlived the pass to stop there.
    """

    __slots__ = ("reading", "abandoned")

    def __init__(self):
        self.reading = False
        self.abandoned = False

    def read_done(self) -> bool:
        """Leave the read phase; True if the pass already left without it."""
        self.reading = False
        return self.abandoned


# Old stamp retries must not occupy an entire periodic flush while fresh quote
# writes wait for the next one. Cooperative: finish each attempted transaction
# and publication; never cancel a stamp merely because this budget elapsed.
# #10090 — env `PENDING_STAMP_BUDGET_S` (0.25..5.0) so values are tried by config.
PENDING_STAMP_BUDGET_S = _owed_budget_env("PENDING_STAMP_BUDGET_S", 1.0, float, 0.25, 5.0)
# #10090 — a flush that carries fresh event IDs attempts at most this many old
# stamps across all of its refresh calls; the rest stay owed in continuation
# order for a quiet flush, which keeps the full time budget above. Without it a
# busy flush's old debt ran serially for up to that second after its fresh work.
# Env `FRESH_FLUSH_PENDING_ATTEMPTS` (1..32); above 1 the time budget above
# still stops the serial old work.
FRESH_FLUSH_PENDING_ATTEMPTS = _owed_budget_env("FRESH_FLUSH_PENDING_ATTEMPTS", 1, int, 1, 32)
# #10090 — how many owed events a running call's door (`admit_fresh`) stamps at
# once beside its admitted cohorts. The attempt count above is spent only when a
# NEW `refresh` starts; a call that keeps admitting a busy slate outlives that,
# and its door alone drains the debt. One at a time, 24 owed Polymarket events
# committed at 23:16:43.5Z 2026-10-28 were stamped in event-id order over 30 s.
# Env `ADMITTED_DEBT_SLOTS` (1..3, the stamp workers); 1 is today's behaviour.
ADMITTED_DEBT_SLOTS = _owed_budget_env("ADMITTED_DEBT_SLOTS", 1, int, 1, 3)
# #10090 — how many queued NON-LIVE admitted events one stamp worker takes into
# one transaction: one session and slot, one read, one COMMIT and one
# publication for all of them, each event keeping its own savepoint and lock
# budget (#837). Production 15:37–15:44Z 2026-10-29 (Kalshi, v5950): the run's
# refresh was open 39–47 s a minute while about half of its ~300 attempts a
# minute stamped nothing (`unobserved` + `no_reading`), each paying its own
# checkout, read and commit on one of FRESH_STAMP_WORKERS slots. Taken only
# while no live game waits, from the head of the queue, and only events of the
# same admitted cohort (same flush clock and stored wall); a live game is never
# in one. Env `ADMITTED_STAMP_BATCH` (1..8); 1 is today's behaviour.
ADMITTED_STAMP_BATCH = _owed_budget_env("ADMITTED_STAMP_BATCH", 1, int, 1, 8)
# #10090 — how many queued LIVE admitted events of ONE cohort one stamp worker
# takes into one transaction (the live counterpart of ADMITTED_STAMP_BATCH):
# one session slot, one checkout, one read statement, one COMMIT and one
# publication for all of them, each event in its own savepoint with its own
# lock budget, locked in ascending id (`_refresh_batch`). Production
# 16:01-16:35Z 2026-10-31 (Polymarket, v6005, ~180 live games): every minute
# line read `stamp_tx` = `events` — one event per transaction — because the
# live lane is FIFO singletons by construction and `_admitted_batch` batches
# non-live heads only, and only while no live game waits, which on a Saturday
# is never. 600-740 transactions a minute on three workers ~97% busy, ~250
# attempts queued, so each live game's turn came every ~15-20 s. Taken from
# the HEAD of the live queue only, in pick order, same flush clock and stored
# wall as the picked event (one admission's cohort), stopping at the first
# event that differs or is no longer live; a reader-held pick taken from the
# middle of the queue is joined only by head events of its own cohort. Nothing
# is reordered or skipped. The extra events count against ADMITTED_LIVE_RUN
# exactly as their own picks would, so pre-game stamps keep today's share.
# Env `ADMITTED_LIVE_BATCH` (1..8); 1 is today's behaviour.
ADMITTED_LIVE_BATCH = _owed_budget_env("ADMITTED_LIVE_BATCH", 1, int, 1, 8)
_OWED_BUDGET_LOGGED = False
#: #10090 — the pid that printed the speed-switch start line (a forked venue
#: process prints its own).
_SPEED_SWITCH_LOGGED_PID: Optional[int] = None

# #10090 — fixed fresh-stamp workers per refresh. Two disjoint stamps waiting
# on rows/publication must not hold a third ready fresh event. Each holds one
# session only inside its stamp; with a consumer's price writer and standalone
# writer that is the lent engine's five connections (pool 3 + overflow 2).
# Env `FRESH_STAMP_WORKERS` (1..8, read once at import); 3 is today's
# behaviour. Everything sized from it follows: the session slots, the live
# debt allowance, and the consumer engine's pool (`base._get_task_engine`:
# these workers plus the two writers' connections, never below today's 5).
FRESH_STAMP_WORKERS = _owed_budget_env("FRESH_STAMP_WORKERS", 3, int, 1, 8)

#: #10090 — `_read_groups` returns one row per (market, outcome), and before
#: this every row carried its event's JSON (the preview's full source bag, or
#: this source's entry) and its market's content-understanding object, decoded
#: on the venue loop for each row while only the first row of each was used.
#: Production 2026-10-31 04:4xZ, v5997: the live Lakers–Warriors event read
#: 1,157 Polymarket rows (387 markets, mostly player props) against ~10 for
#: Kalshi's game-only join, and PM's `stamp_read` was 47-54 s/min (0.10 s per
#: transaction, 6x Kalshi) with `loop_busy` far above `loop_idle`. Local PG at
#: that shape: 18.5 ms per read, of which ~5 ms was 2,314 JSON decodes and ~3 ms
#: parsing the 1.7 MB they rode in. On (default), the same single statement
#: (one snapshot) sends each JSON value on exactly one row of its event or
#: market (`row_number() = 1`) and NULL on the rest; the graph built from it is
#: identical. ``STAMP_READ_JSON_ONCE=0`` restores the per-row read. Read at
#: call time; a config change restarts the dyno anyway.
STAMP_READ_JSON_ONCE_ENV = "STAMP_READ_JSON_ONCE"


def stamp_read_json_once() -> bool:
    return os.getenv(STAMP_READ_JSON_ONCE_ENV, "1").strip() != "0"


# #10090 `stamp_wait_reason` — why a LIVE game's oldest unstamped input is
# still waiting once it is STAMP_WAIT_BUDGET_S old. Production 03:40Z
# 2026-10-31 (Polymarket 15331470, live soccer): an input received 03:40:12.988
# was stamped at 03:42:10.714, 117.7 s later, and nothing retained said whether
# it was queued, held, refused or never owed. Classified from state this
# refresher already holds, at debt selection (`refresh`, `admit_fresh`) and
# after each attempted read (`_refresh_batch`); at most one line per event per
# STAMP_WAIT_LINE_INTERVAL_S (an episode that printed one also prints its
# closing STAMPED), plus a per-minute count of events by reason on the venue
# minute line (`StampSpans.wait_reasons`). Log only: no await, lock or query.
# ``STAMP_WAIT_REASON_LOG=0`` turns it off.
STAMP_WAIT_REASON_ENV = "STAMP_WAIT_REASON_LOG"
STAMP_WAIT_BUDGET_S = 5.0
STAMP_WAIT_LINE_INTERVAL_S = 60.0
#: What an attempted read did with the event (`_dispositions`), as a reason.
#: A raw `stamped` read ends an input wait only after receipt coverage.
#: A successful write without that coverage is READ_UNCOVERED.
STAMP_WAIT_DISPOSITIONS = {
    "stamped": "STAMPED",
    "no_reading": "NO_VALID_READING",
    "stale": "NO_VALID_READING",
    "no_market": "CATALOG_CLOSED",
    "no_row": "CATALOG_CLOSED",
    "lock": "ROW_LOCK_SKIPPED",
    "unchanged": "READ_UNCHANGED",
    "unobserved": "READ_UNCHANGED",
    "preview_only": "READ_UNCHANGED",
    "error": "READ_ERROR",
}


def stamp_wait_reason_on() -> bool:
    return os.getenv(STAMP_WAIT_REASON_ENV, "1").strip() != "0"


class StampWaitLog:
    """#10090 — the `stamp_wait_reason` lines' rate limit, per event.

    An episode is one oldest-unstamped input (its `seq`); it ends when a read
    covers that input or the input stops being the oldest owed one. `seen`
    counts every reason noted since the episode's last line, so a line names
    each cause the wait passed through, not only the latest. Pure bookkeeping.
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self._episodes: dict[int, dict] = {}
        self._last_line: dict[int, float] = {}
        self.lines = 0
        self.errors = 0

    def note(self, event_id: int, reason: str, obligation: tuple, now: float, *,
             run: str, site: str, held_tag: str = "") -> None:
        seq, outcome_id, age, committed = obligation
        episode = self._episodes.get(event_id)
        if episode is None or episode["seq"] != seq:
            episode = self._episodes[event_id] = {
                "seq": seq, "seen": {}, "printed": False, "admitted_age": None,
            }
        seen = episode["seen"]
        seen[reason] = seen.get(reason, 0) + 1
        if reason == "ADMITTED" and episode["admitted_age"] is None:
            episode["admitted_age"] = age
        last = self._last_line.get(event_id)
        due = last is None or now - last >= STAMP_WAIT_LINE_INTERVAL_S
        if reason == "STAMPED":
            del self._episodes[event_id]
            if not (due or episode["printed"]):
                return
        elif not due:
            return
        else:
            episode["printed"] = True
        self._last_line[event_id] = now
        self.lines += 1
        logger.info(
            "live_blend_refresh[%s]: stamp_wait_reason=%s run=%s venue=%s event=%s "
            "outcome=%s seq=%s age_s=%.3f committed_seq=%s committed_age_s=%s "
            "admitted_age_s=%s seen=%s site=%s%s",
            self.source, reason, run, self.source, event_id, outcome_id, seq, age,
            "-" if committed is None else committed[0],
            "-" if committed is None else f"{committed[1]:.3f}",
            "-" if episode["admitted_age"] is None else f"{episode['admitted_age']:.3f}",
            ",".join(f"{name}:{count}" for name, count in sorted(seen.items())),
            site, held_tag,
        )
        episode["seen"] = {}

    def retain(self, event_ids, now: float) -> None:
        """Episodes of events no longer waiting end; rate-limit marks older
        than the interval go."""
        for event_id in [eid for eid in self._episodes if eid not in event_ids]:
            del self._episodes[event_id]
        for event_id in [eid for eid, at in self._last_line.items()
                         if now - at >= STAMP_WAIT_LINE_INTERVAL_S]:
            del self._last_line[event_id]


# #10090 `price_commit_ack_wall` — when the price transaction that carried a
# tail receipt's held input (`rev`) returned successfully, on this process's
# wall clock. Production 03:00-05:36Z 2026-10-31 (Argon, 89 PM chains):
# receive -> `stored_wall` was p50 0.53 s / p90 4.0 s against Kalshi's 0.10 /
# 0.21, and `stored_wall` is sampled when marks are OFFERED to the refresher,
# so a slow price COMMIT and a committed price waiting to be offered read the
# same. Sampled at the writer's synchronous success seam, bound to that
# write's own frozen marks for the rows it returned, kept on the chain's
# original input (a later superseding write never fills it). None for an
# overlay-only, skipped, non-returning or unacknowledged input; an overlay
# offer that precedes the acknowledgement keeps that order. A local
# acknowledgement clock, not the database COMMIT time. Log only: no await,
# lock or query. ``PRICE_COMMIT_ACK_LOG=0`` turns it off.
PRICE_COMMIT_ACK_LOG_ENV = "PRICE_COMMIT_ACK_LOG"
#: Acknowledgements waiting for their chain: per event, and events in all.
PRICE_COMMIT_ACK_PER_EVENT = 8
PRICE_COMMIT_ACK_EVENTS = 2048


def price_commit_ack_log_on() -> bool:
    return os.getenv(PRICE_COMMIT_ACK_LOG_ENV, "1").strip() != "0"


def note_price_commit_ack(receipts, marks, wall: Optional[float]) -> None:
    """A writer's `price_commit_ack_wall`: ``marks`` are the inputs of the
    rows its committed transaction returned, ``wall`` the clock it sampled at
    the success seam (None: switch off, or no acknowledgement). Never raises."""
    if wall is None or receipts is None:
        return
    try:
        receipts.note_commit_ack(marks, wall)
    except Exception:
        logger.warning("tail receipt: price commit ack failed", exc_info=True)


# #10090 — an observation-preview read whose caller stopped waiting at its
# 0.25 s deadline is left to end by itself instead of being cancelled. A
# cancelled SELECT invalidates its pooled connection and then holds its slot
# through the graceful close (production 18:04–18:10Z 2026-10-28: a median
# 443 ms past the deadline). It keeps its session slot and connection until it
# actually ends, so at most this many run per refresher; past it a read is
# cancelled the old way. One that is still running this long after its caller
# left is cancelled the old way too.
OBSERVATION_READ_DETACHED_MAX = 1
OBSERVATION_READ_DETACHED_S = 2.0

# An abandoned read keeps its session slot until it finishes. Across every
# kind here AND the detached observation read (`_detached_reads`,
# `OBSERVATION_READ_DETACHED_MAX`), at most this many hold a slot at once, so two of the
# FRESH_STAMP_WORKERS slots always stay for fresh stamps (lane1b's 2255Z
# composition finding: separate per-kind limits let four optional tasks
# compete for three slots). While the share is taken every optional kind's next
# opportunity passes exactly as it does when the slots are taken, and a read
# that reaches its deadline then is cancelled, as it is with the switch off.
# More workers (`FRESH_STAMP_WORKERS` above 3) never widen this share past
# today's 1: each held read pins a pool connection, and the added workers are
# for stamps.
OPTIONAL_DB_HELD_MAX = max(0, min(FRESH_STAMP_WORKERS - 2, 1))

# #10090 — admitted cohorts are stamped live-first, as a call's own population
# is. Stage trace 02:14Z 2026-10-15: a live game's admitted stamp started
# 6.43 s after admission and then took 95 ms; 134 events were held by the call
# then, which does not say how many were queued ahead of it, their status, or
# what the three workers were waiting on. This orders a known-live event ahead
# of queued non-live ones when a worker comes free; it cannot preempt an
# occupied worker. After this many live stamps in a row, a waiting non-live
# event goes next, so pre-game prices keep progressing while live ones lead.
ADMITTED_LIVE_RUN = 3

# #10090 held-first stamps — a live game a reader holds open (its
# `live:event:<id>` stream, `reader_presence.HeldEventCache`) is stamped
# before live games nobody is watching when stamps are queued. Production
# 15:35-15:40Z 2026-10-31 (Polymarket, G4F13, ~150 live events): hold -> stamp
# took 9-21 s, `stamp_wait_reason` QUEUED_OR_RUNNING 348, at ~14 stamps/s,
# and the queue was FIFO among live games, so an open page waited every other
# game's turn. Only the ORDER among queued events changes: one attempt per
# event, its cohort, clock, supersession and fences as before. After
# READER_FIRST_RUN held stamps in a row while an unheld live game waited, the
# oldest unheld one goes next, so unheld games keep at least one turn in
# READER_FIRST_RUN + 1. ``STAMP_READER_FIRST=0`` restores the old order; an
# unreadable or stale held set is empty, which is the old order too.
STAMP_READER_FIRST_ENV = "STAMP_READER_FIRST"
READER_FIRST_RUN = 3


def stamp_reader_first_on() -> bool:
    return os.getenv(STAMP_READER_FIRST_ENV, "1").strip() != "0"


def _reader_held_tag(source, event_id) -> str:
    """` reader_held=0|1` for a log line; empty with no source or a failing one."""
    if source is None:
        return ""
    try:
        return f" reader_held={int(event_id in source())}"
    except Exception:  # noqa: BLE001 — a log tag never fails its line
        return ""


# #10090 held-owed-fresh — a LIVE game a reader holds open whose committed
# price is OWED (its own offer was refused: the game's stamp was queued or
# running, its cohort unfinished, or it was under the floor) does not wait for
# the door's one live-debt slot. Production 16:16-16:31Z 2026-10-31 (v6005,
# four held Polymarket games, held-first on): the price reached the reader in
# ~0.85 s when its offer was admitted, but a refused price went to plain debt
# and the next stamp that carried it came p50 4.3 s / p90 12-19 s later —
# the live-debt slot is held by an unheld rider for its whole queue turn
# (15-20 s), and `stamp_wait_reason` saw LIVE_DEBT_SLOT_BUSY on the held
# games' episodes; once ADMITTED the held game stamped in 0.28 s. On, the
# first admission that finds such a game admissible (not fenced, not
# excluded, due) takes it as a cohort member on that flush's clock, picked
# held-first, outside the debt slots. Unheld debt keeps its slots and turns;
# the live pick bound (READER_FIRST_RUN) is unchanged. ``STAMP_HELD_OWED_FRESH=1``
# turns it on; off (default), or with no held set, the order is today's.
STAMP_HELD_OWED_FRESH_ENV = "STAMP_HELD_OWED_FRESH"


def stamp_held_owed_fresh_on() -> bool:
    return os.getenv(STAMP_HELD_OWED_FRESH_ENV, "0").strip() == "1"


# #10090 write-under-queued — a game whose stamp attempt is QUEUED (admitted,
# no worker has started it) is fenced from the price write exactly as one
# whose stamp is RUNNING. On the saturated Polymarket lane (~250 attempts
# queued, a turn 6-60 s) every newer price of an unheld game therefore stays
# buffered for the whole wait, the stamp that finally lands carries a price as
# old as the wait, and the current price waits a second whole turn. Production
# 19:58-20:03Z 2026-10-31 (v6012, `readout.txt`): Polymarket LIVE chains
# recv -> stamp p50 5.9 s / p90 11.1 s, pre-game p50 28 s / p90 64 s, and the
# newest input a stamp carried was p50 3.5 s old. The fence protects a RUNNING
# attempt's read — its basis must not predate a committed price its stamp is
# then dated after (I2, #8910); a queued attempt has read nothing, so for it
# the fence protects nothing and costs the game a turn. On, the game flush may
# write an event whose attempt is queued (`fenced_event_ids`: the next N picks
# per queue, or every queued attempt with ``all``). It takes a write lease
# first (`writing_begin` / `writing_end`): no queued attempt of an event under
# write starts until that write has returned, so a read never straddles its
# own event's write (I1). The committed cohort then RIDES the queued attempt
# (`admit_fresh` re-stages its newest input onto it — no debt, no second
# attempt) instead of being refused as HELD. A running attempt is fenced as
# before; a cohort committed after its read started is kept owed as before;
# the call's own fresh population (startup, a hand-over's carried events) is
# fenced as before. Unset or ``0`` (default): today's fence, byte for byte.
STAMP_WRITE_UNDER_QUEUED_ENV = "STAMP_WRITE_UNDER_QUEUED"
#: A worker that finds every queued attempt under a write lease re-checks at
#: least this often; a lease never outlives its flush.
WRITE_LEASE_WAIT_S = 0.25
#: An absorb right (`writing_end` granted it to a still-queued attempt) is
#: spent at the cohort's offer, which follows its commit in the same flush;
#: one not offered within this many seconds has expired.
WRITE_RIGHT_TTL_S = 5.0


def stamp_write_under_queued() -> Optional[int]:
    """The fence-lift horizon: None off (default); 0 every queued attempt
    (``all``); N > 0 the next N picks per queue. Read at each use; anything
    unparseable is off."""
    raw = os.getenv(STAMP_WRITE_UNDER_QUEUED_ENV, "0").strip().lower()
    if raw in ("", "0", "off", "false", "no"):
        return None
    if raw in ("all", "every", "*"):
        return 0
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


# #10090 (Argon flush-loop Rank 2) — a due throttle-deferred LIVE event rides
# a running call's door outside its debt slots, at most this many at a time.
# Production 2026-10-30 00:18Z (Kalshi 15338515, origin=throttle,
# lock_retries=0): the one debt slot is shared with pre-game debt, so a live
# game's throttled price waited its turn behind it. Owed stamps riding the door
# (debt slots plus this allowance) hold at most FRESH_STAMP_WORKERS - 1
# admitted workers, so one always stays for a later fresh cohort: the
# allowance is what the debt slots leave of that (`_admitted_live_debt_slots`;
# 1 with today's one slot, none once a trial runs 2 or 3). A row-lock retry
# keeps the shared slot's turn order: it may wait out a whole lock budget, and
# Root's fairness case (a locked event due again at once) must not take a
# worker every admission.
ADMITTED_LIVE_DEBT_SLOTS = max(0, FRESH_STAMP_WORKERS - 1 - ADMITTED_DEBT_SLOTS)


def _admitted_live_debt_slots(slots: int) -> int:
    """The live allowance beside ``slots`` debt slots (this admission's)."""
    return max(0, FRESH_STAMP_WORKERS - 1 - slots)

# Includes the point currently writing and reservations before quote COMMIT.
# The writer's ordinary backlog. Past it a newly due stamp does not wait
# (#11138) and still owes its point at its own observation time, paid when
# the writer drains without another quote (#11181). No point drops.
HISTORY_POINT_LIMIT = 64
# The memory bound beyond the ordinary backlog. Points are owed at most one per
# event per snapshot interval, so a held writer reaches it only after minutes
# (a 100-event slate owes 4 a second: ~4 minutes). Past it a point is still
# owed and the stamp still never waits: the point lives only in its durable
# `owed_chart_points` row until memory has room to load it (#11181,
# `OwedChartCustody`).
HISTORY_SPILL_LIMIT = 1024

#: #837 receipt — the per-event floor between receipt lines for chains that
#: cannot qualify as a quiet tail (a busy market's routine deferrals, a held
#: price that rounded to the stored value). Those are summarised with a count.
#: A quiet stamp and every abnormal chain are never held back by it.
TAIL_RECEIPT_COALESCE_S = 60.0

#: #10090 delivery receipt — one line per source × LIVE event × UTC minute:
#: what the consumer received for that game (raw / accepted / changed /
#: repeats, per outcome) and which published revisions carried it. Alex,
#: 2026-10-06: incoming rate, browser arrival rate and lag are three separate
#: numbers; the page capture sees only the second, and nothing on the consumer
#: side said how many inputs one game had or which `rev` a given input reached
#: the page as. Bounded to events whose latest stamp was `live`, so a slate of
#: upcoming games and futures writes no lines.
DELIVERY_RECEIPT_WINDOW_S = 60.0
#: Per line. A live game stamps at most once per 2 s flush (~30 a minute), so
#: the cap only bites if the throttle is changed; the overflow is counted.
DELIVERY_RECEIPT_MAX_STAMPS = 40
#: Inputs awaiting their stamp, per event. A stamp normally takes all of them
#: within one flush; the bound only stops a never-stamped event from growing.
DELIVERY_RECEIPT_MAX_PENDING = 512
#: Lines per source per minute. worker-ws logs drain to Better Stack; a full
#: evening slate must not turn the receipt into the dyno's loudest line. The
#: most active games are written; the rest are counted in one overflow line.
DELIVERY_RECEIPT_MAX_EVENTS = 30
#: #10090 field 2 — preview publications listed per line, like `stamps`; the
#: overflow is counted in `previews_dropped`.
DELIVERY_RECEIPT_MAX_PREVIEWS = 40
#: A receipt line longer than this is trimmed before it is written: logplex
#: cuts 10,000+ character lines (a busy game's `outcomes=` alone overran it,
#: losing every stamp after it). Shed order: preview items carrying no
#: `first_new_recv`, then outcome items (fewest accepted first, counted in
#: `outcomes_dropped`; the line's totals still cover every outcome), then the
#: oldest previews (`previews_dropped`). Stamps are never shed.
DELIVERY_RECEIPT_MAX_LINE_CHARS = 9000
#: The receipt line's fixed shape. `stamps` items are
#: rev@stamped_at@newest_recv@oldest_recv@covered@first_new_recv; `previews`
#: items are base_rev:seq@published_at@first_new_recv (`ReaderTrail`).
#: `trail_retired` is superseded:N,flushed:N,settled:N — trail inputs that
#: left uncredited (F2) — and `trail_first_skipped` the headline inputs with no
#: prior this run that never joined (F1).
DELIVERY_RECEIPT_FORMAT = (
    "live_blend_refresh[%s]: delivery-receipt run=%s event=%s "
    "window_start=%s window_s=%.3f raw=%d accepted=%d changed=%d "
    "repeats=%d first=%d outcomes=%s stamps=%s stamps_dropped=%d "
    "writer=%s previews=%s previews_dropped=%d trail_dropped=%d "
    "trail_retired=%s trail_first_skipped=%d outcomes_dropped=%d%s"
)
#: #10090 field 3 — the same `stamps=` item, from a writer of this process
#: other than the arm's own stamp (a Polymarket withdrawal), one line per
#: revision of a live event.
WRITER_RECEIPT_FORMAT = (
    "live_blend_refresh[%s]: writer-receipt writer=%s event=%s stamps=%s"
)


#: #10090 — the live games a consumer run's receipt knew, left for the next run
#: of the same source. Process-local, like `_pending_handoff`: without it every
#: recycle would count nothing for a live game until its first stamp of the new
#: run, and that stamp would read covered=0.
_live_handoff: dict[str, frozenset] = {}


def _mono() -> float:
    """The refresher's monotonic clock — one seam, so a rig can drive time
    without patching `time.monotonic` under the event loop."""
    return time.monotonic()


def _wall() -> float:
    """The dyno's wall clock (epoch seconds, UTC) — same seam, same reason."""
    return time.time()


def _stamp_span_clock() -> float:
    """#10090 `StampSpans`' monotonic clock. Its own seam, so the spans never
    take a reading from (or advance) a rig's `_mono`."""
    return time.monotonic()


def _stamp_span_cpu() -> float:
    """#10090 `StampSpans`: CPU seconds on this thread, the event loop's."""
    return time.thread_time()


class StampSpans:
    """#10090 — where this refresher's stamp time went, per venue minute line.

    Every `_refresh_batch` transaction, from any caller (game flush, side
    loops, admitted workers, debt), on wall clock:

    - `slot`: waiting for one of the FRESH_STAMP_WORKERS session slots, then
      opening the session.
    - `read`: `_read_groups` and the cold orientation fallback (`_oriented`).
      An AsyncSession checks its connection out on its first statement, so pool
      checkout lands here (in `write` for a prepared group).
    - `compute`: the synchronous rest of the transaction body (readings,
      proofs, frames). Nothing in it awaits, so it is CPU on the loop.
    - `write`: the lock-budget SET plus the stamp's savepoint scope (its row
      UPDATE, owed chart point and custody INSERTs, savepoint release or
      rollback).
    - `commit`: leaving the session (COMMIT, close) and its slot.
    - `publish`: previews published inside the transaction, then everything
      after COMMIT (committed frames and preview settlement).

    `prepared` reads (`_prepare_groups`, one shared read for several fresh
    events, no stamp of its own) add their slot wait and read to `slot` and
    `read` and are counted apart from `stamp_tx`.

    `checkout` is the part of `read`/`write` spent until the consumer pool
    handed a connection over (`ws_consumer_sessions.checkout_probe`), and
    `pool_full=K/P` is K of P probed transactions whose body began with every
    pool connection out. Both are nested, never added to the buckets.

    LOOP WAIT. The exact time a ready stamp waited for the loop is not
    attributable without hooking every resume. What the line gives instead,
    from two thread-CPU reads per transaction: `loop_busy`, the loop thread's
    CPU spent while stamps awaited (other tasks, plus the stamp's own work
    inside its awaits), the upper bound on that wait; and `loop_idle`, the
    awaited time with the loop thread idle, which is time spent truly waiting
    on the database, the pool or Redis. Mostly `loop_busy` means more workers
    will not help; mostly `loop_idle` means they can.

    `stamp_read_rows` is the rows every `_read_groups` statement returned
    (stamps, prepared and observation-preview reads alike) and
    `stamp_read_json` the JSON values those rows carried, each decoded on the
    loop (`STAMP_READ_JSON_ONCE`: one per event and market instead of two per
    row).

    `workers` is FRESH_STAMP_WORKERS; `slots_max`/`slots_mean` are slots in
    use (any holder, the stamp included) as each transaction got its own;
    `slot_full` is how many transactions found no slot free and waited.

    Transactions overlap, so every bucket is stamp-seconds and can sum past
    60 s a minute. A transaction joins the minute it ends in. Log only:
    monotonic deltas, no await, no query.
    """

    SPANS = ("slot", "read", "compute", "write", "commit", "publish")

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.transactions = 0
        self.events = 0
        self.prepared = 0
        self.spent = dict.fromkeys(self.SPANS, 0.0)
        self.checkout = 0.0
        self.pool_full = 0
        self.probed = 0
        self.busy = 0.0
        self.idle = 0.0
        self.slots_max = 0
        self.slots_sum = 0
        self.slots_seen = 0
        self.slot_full = 0
        self.read_rows = 0
        self.read_json = 0
        #: #10090 `stamp_wait_reason`: reason -> the events that waited for it.
        self.wait_reasons: dict[str, set] = {}
        #: #10090 write-under-queued: committed cohorts that rode a queued
        #: attempt (`admit_fresh` ABSORBED) and worker turns that found every
        #: queued attempt under a write lease. Printed only when either is
        #: non-zero, so the line is unchanged with the switch off.
        self.absorbed = 0
        self.lease_waits = 0

    def add_prepared(self, slot_s: float, read_s: float) -> None:
        self.prepared += 1
        self.spent["slot"] += max(0.0, slot_s)
        self.spent["read"] += max(0.0, read_s)

    def line(self) -> str:
        spent = self.spent
        mean = self.slots_sum / self.slots_seen if self.slots_seen else 0.0
        return (
            f"stamp_tx={self.transactions} events={self.events} "
            f"prepared={self.prepared} "
            f"stamp_slot={spent['slot']:.1f}s stamp_read={spent['read']:.1f}s "
            f"stamp_read_rows={self.read_rows} stamp_read_json={self.read_json} "
            f"stamp_compute={spent['compute']:.1f}s "
            f"stamp_write={spent['write']:.1f}s "
            f"stamp_commit={spent['commit']:.1f}s "
            f"stamp_publish={spent['publish']:.1f}s "
            f"stamp_checkout={self.checkout:.1f}s "
            f"pool_full={self.pool_full}/{self.probed} "
            f"loop_busy={self.busy:.1f}s loop_idle={self.idle:.1f}s "
            f"workers={FRESH_STAMP_WORKERS} slots_max={self.slots_max} "
            f"slots_mean={mean:.1f} slot_full={self.slot_full}"
        ) + (
            " wait_reasons=" + ",".join(
                f"{reason}:{len(events)}"
                for reason, events in sorted(self.wait_reasons.items())
            )
            if self.wait_reasons else ""
        ) + (
            f" write_under_queued=absorbed:{self.absorbed},lease_waits:{self.lease_waits}"
            if self.absorbed or self.lease_waits else ""
        )


class _StampSpan:
    """Times its body into one `_StampTx` bucket. Sync or async ``with``; the
    async form never suspends."""

    __slots__ = ("_tx", "_bucket", "_started")

    def __init__(self, tx: "_StampTx", bucket: str) -> None:
        self._tx = tx
        self._bucket = bucket

    def __enter__(self) -> None:
        self._started = _stamp_span_clock()

    def __exit__(self, *_exc) -> bool:
        self._tx.spent[self._bucket] += _stamp_span_clock() - self._started
        return False

    async def __aenter__(self) -> None:
        self.__enter__()

    async def __aexit__(self, *exc) -> bool:
        return self.__exit__(*exc)


class _StampBody:
    """The transaction body's bounds, entered once the session is open."""

    __slots__ = ("_tx", "_probe_cm")

    def __init__(self, tx: "_StampTx") -> None:
        self._tx = tx
        self._probe_cm = None

    async def __aenter__(self) -> None:
        tx = self._tx
        tx.body_started = _stamp_span_clock()
        free = getattr(tx.slots, "_value", None)
        if isinstance(free, int):
            tx.slots_in_use = max(0, FRESH_STAMP_WORKERS - free)
        try:
            from app.tasks.ws_consumer_sessions import checkout_probe

            self._probe_cm = checkout_probe(_stamp_span_clock)
            tx.probe = self._probe_cm.__enter__()
        except Exception:  # a log field never fails a stamp
            self._probe_cm = tx.probe = None

    async def __aexit__(self, *_exc) -> bool:
        tx = self._tx
        tx.body_ended = _stamp_span_clock()
        awaited = sum(tx.spent.values())
        tx.compute = max(0.0, tx.body_ended - tx.body_started - awaited)
        if self._probe_cm is not None:
            with contextlib.suppress(Exception):  # exited in another context
                self._probe_cm.__exit__(None, None, None)
        return False


class _StampTx:
    """One `_refresh_batch` transaction's spans (`StampSpans`).

    As an async context manager it brackets the whole ``async with``: entered
    before the session slot is taken, left after COMMIT and the slot's release.
    The publication after it is added by `published`.
    """

    __slots__ = (
        "spans", "events", "slots", "spent", "started", "cpu_started",
        "body_started", "body_ended", "compute", "ended", "cpu_ended",
        "slots_in_use", "slot_full_at_start", "probe",
    )

    def __init__(self, spans: Optional[StampSpans], events: int, slots) -> None:
        self.spans = spans
        self.events = events
        self.slots = slots
        self.spent = {"read": 0.0, "write": 0.0, "publish": 0.0}
        self.started = self.cpu_started = None
        self.body_started = self.body_ended = None
        self.compute = 0.0
        self.ended = self.cpu_ended = None
        self.slots_in_use = None
        self.slot_full_at_start = False
        self.probe = None

    def span(self, bucket: str) -> _StampSpan:
        return _StampSpan(self, bucket)

    def body(self) -> _StampBody:
        return _StampBody(self)

    async def __aenter__(self) -> "_StampTx":
        self.started = _stamp_span_clock()
        self.cpu_started = _stamp_span_cpu()
        spans = self.spans
        locked = getattr(self.slots, "locked", None)
        if spans is not None and callable(locked):
            with contextlib.suppress(Exception):
                if locked():
                    self.slot_full_at_start = True
        return self

    async def __aexit__(self, *_exc) -> bool:
        self.ended = _stamp_span_clock()
        self.cpu_ended = _stamp_span_cpu()
        spans = self.spans
        if spans is None:
            return False
        spans.transactions += 1
        spans.events += self.events
        spans.slot_full += self.slot_full_at_start
        spent = spans.spent
        wall = self.ended - self.started
        if self.body_started is None:  # never got a session: all slot
            spent["slot"] += wall
        else:
            spent["slot"] += self.body_started - self.started
            body_ended = self.body_ended if self.body_ended is not None else self.ended
            spent["commit"] += self.ended - body_ended
        spent["compute"] += self.compute
        for bucket, seconds in self.spent.items():
            spent[bucket] += seconds
        busy = max(0.0, min(self.cpu_ended - self.cpu_started, wall) - self.compute)
        spans.busy += busy
        spans.idle += max(0.0, wall - self.compute - busy)
        if self.slots_in_use is not None:
            spans.slots_max = max(spans.slots_max, self.slots_in_use)
            spans.slots_sum += self.slots_in_use
            spans.slots_seen += 1
        probe = self.probe
        if probe is not None and self.body_started is not None:
            spans.probed += 1
            spans.pool_full += bool(probe.full_at_start)
            if probe.checked_out_at is not None:
                spans.checkout += max(0.0, probe.checked_out_at - self.body_started)
        return False

    def published(self) -> None:
        """The publication after COMMIT ended (or raised): add it."""
        spans = self.spans
        if spans is None or self.ended is None:
            return
        wall = max(0.0, _stamp_span_clock() - self.ended)
        busy = min(wall, max(0.0, _stamp_span_cpu() - self.cpu_ended))
        spans.spent["publish"] += wall
        spans.busy += busy
        spans.idle += wall - busy


# Call-local timing for the existing optional-read failure receipt. A fetch
# cancellation alone cannot say whether checkout/admission consumed its budget.
# Ordinary stamp reads have no timing state; no payloads or event IDs are kept.
_observation_read_timing: ContextVar[dict | None] = ContextVar(
    "observation_read_timing", default=None,
)


@contextlib.contextmanager
def _observation_read_step(name):
    timing = _observation_read_timing.get()
    if timing is None:
        yield
        return
    started = _mono()
    timing[name + "_start_ms"] = (started - timing["started_s"]) * 1000
    timing[name + "_completed"] = False
    try:
        yield
        timing[name + "_completed"] = True
    finally:
        timing[name + "_ms"] = (_mono() - started) * 1000


class _ObservationReadAbandoned(Exception):
    """The preview caller stopped waiting: no statement or retirement follows."""


class _ObservationReadTimeout(TimeoutError):
    """The observation-preview read outlived its wait: counted as
    ``observation_timeouts``, not as a publish error (#10090 receipt)."""


class _ObservationRead:
    """One optional preview graph read, shared by its caller and its task."""

    __slots__ = ("timing", "waiting", "graph", "ceiling")

    def __init__(self, timing: dict) -> None:
        self.timing = timing
        self.waiting = True  # cleared, never set again, when the caller stops
        self.graph = None
        self.ceiling = False


def _observation_read_summary(timing):
    if timing is None:
        return None
    return {key: round(value, 3) if type(value) is float else value
            for key, value in timing.items() if key != "started_s"}


def _iso(wall: Optional[float]) -> Optional[str]:
    if wall is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(wall, timezone.utc).isoformat(timespec="milliseconds")


class PreviewSettlementUncertain(RuntimeError):
    """A settlement did not produce a parsed reply; keep its locked proof alive."""


@dataclass(frozen=True)
class InputMark:
    """One accepted venue input, as the socket received it.

    `seq` counts every accepted input of one consumer run, same-price repeats
    included; `event_ordinal` is how many inputs THIS event had received when
    this one arrived. The receipt's "did anything arrive after the held price"
    is the difference between the event's running count and that ordinal —
    which a stored `price_changed_at` cannot answer, because a repeat or a
    move that rounds to the stored value leaves it untouched.
    """

    seq: int
    event_id: int
    outcome_id: int
    probability: float
    kind: str
    recv_wall: float
    recv_mono: float
    venue_ts_ms: Optional[int]
    event_ordinal: int


@dataclass
class _TailChain:
    origin: str  # "throttle" | "lock" | "batch"
    rev: InputMark  # the revision whose committed write was held
    stamp_rev: InputMark  # the newest committed revision before the close
    stored_wall: float
    opened_wall: float
    opened_mono: float
    later_committed: int = 0
    lock_retries: int = 0
    commit_failures: int = 0
    batch_failures: int = 0
    #: #10090 `price_commit_ack_wall` of `rev` itself, never of `stamp_rev`.
    commit_ack_wall: Optional[float] = None


class TailReceipts:
    """#837 — one receipt per held price: received, stored, held, stamped.

    WHY. The deferred-tail stamp exists (`_throttle_deferred`, `_lock_retry`),
    but nothing said, for ONE event, which price was held, when it arrived, and
    whether the stamp that finally carried it was the quiet flush or another
    tick. The aggregate `throttled=`/`stamped=` counts cannot. Codex's review of
    the first draft (2026-09-25 16:20Z) also showed why a receipt must not read
    "quiet" off the final flush: refresh 1000 → held 1001 → a second input
    1003 → stamp 1006 printed quiet=True and held 6s, when the input at 1003
    intervened and the price was held 5s. So a chain opens at the hold, counts
    EVERY later input for the event (same-price and not-yet-flushed ones
    included) and every later committed write, and `quiet` is only
    `later_inputs == 0`.

    CLOCK DOMAINS, stated because they must not be mixed: `*_wall` fields are the
    dyno clock. `stamped_at` is the database write clock, byte-for-byte the JSONB
    `updated_at` and the SSE frame's, so the receipt joins to what was served.
    `*_s` durations are monotonic on the same process. `venue_ts_ms` is the
    venue's clock, copied raw. The database clock (`price_changed_at`,
    `captured_at`) is a fourth domain the receipt does not assert against.

    VOLUME. One line per chain, never per flush. A chain closes only at a due
    refresh, so the always-logged class (quiet stamps, lock and failure chains,
    recycle/shutdown resets) is at most one line per event per throttle
    interval; routine chains are coalesced per event (`TAIL_RECEIPT_COALESCE_S`).
    A `tail-receipt summary` line per consumer run says the instrument was on —
    the absence of a receipt proves nothing without it.

    Pure bookkeeping, nothing awaited, and every entry point is wrapped by its
    caller: a receipt that fails must never cost a price (gotcha #42).
    """

    COALESCIBLE = frozenset(
        {"stamped", "unchanged", "preview_only", "unobserved", "no_reading", "no_row", "no_market"}
    )

    def __init__(self, source: str, *, coalesce_s: float = TAIL_RECEIPT_COALESCE_S) -> None:
        import uuid

        self.source = source
        #: Sequences restart with every consumer run; the run id is what stops
        #: a seq from one run being read against another's across a recycle.
        self.run = uuid.uuid4().hex[:8]
        self.coalesce_s = coalesce_s
        self._seq = 0
        self._inputs_by_event: dict[int, int] = {}
        self._last_seq_by_event: dict[int, int] = {}
        self._staged: dict[int, InputMark] = {}
        self._staged_wall: Optional[float] = None
        self._open: dict[int, _TailChain] = {}
        #: #10090 `price_commit_ack_wall`s no chain has taken yet: event id ->
        #: {input seq: wall}. Bounded (`PRICE_COMMIT_ACK_*`).
        self._commit_acks: dict[int, dict[int, float]] = {}
        self._last_logged: dict[int, float] = {}
        self._coalesced: dict[int, int] = {}
        self.stats: dict[str, int] = {
            "inputs": 0, "opened": 0, "logged": 0, "coalesced": 0,
            "delivery_lines": 0,
        }
        # #10090 delivery receipt state (see `DELIVERY_RECEIPT_WINDOW_S`).
        self._window_start: Optional[float] = None
        self._window: dict[int, dict] = {}
        #: Per LIVE event only: worker-ws carries ~100k open-contract outcomes
        #: and runs near its memory quota, so nothing here is kept for an event
        #: until a stamp has said it is live, and it is dropped when it is not.
        self._last_p: dict[int, dict[int, float]] = {}
        self._uncovered: dict[int, deque] = {}
        self._committed: dict[int, InputMark] = {}
        self._live_events: set[int] = set(_live_handoff.pop(source, frozenset()))
        #: #10090 total unnecessary delay: what live readers still lack, per
        #: publication (`app.utils.reader_trail`). Live events only.
        from app.utils.reader_trail import ReaderTrail

        self._trail = ReaderTrail()
        #: Outcome-id sets the arm keeps IN PLACE that the headline read leaves
        #: out (props, non-blend series): their inputs never join the trail.
        self.trail_excluded: tuple = ()
        #: The frame value each live event's in-flight stamp publishes, by
        #: revision; taken by `_note_stamp` once that stamp committed.
        self._stamp_frames: dict[int, tuple] = {}
        #: Coverage starts no earlier than this run did, nor before a game was
        #: first stamped live in it: a minute line must never claim seconds the
        #: consumer was not watching (Root's 57 s repro: 3 inputs in 3 s read
        #: as 3 in 60 s, a 20x understatement).
        self._run_start = _wall()
        self._live_since: dict[int, float] = {}
        #: #10090 decision J: this venue's `ConfirmedAt`, or None (wired by
        #: the consumer, which also hands it each headline input's mark).
        #: Fed every resolution below.
        self.confirmed = None
        #: #10090 held-first stamps: the event ids a reader holds (wired by
        #: the consumer); a line then says ` reader_held=0|1`, switch on or off.
        self.reader_held: Optional[Callable[[], Container[int]]] = None

    # ── the socket's side ────────────────────────────────────────────────────

    def note_raw(self, event_id: Optional[int]) -> None:
        """#10090 — one venue message for a contract of this event, counted
        BEFORE the price policy decides whether it is a price. `raw` minus
        `accepted` is what the policy refused (one-sided books, terminal
        prices); a message that maps to no event is not this game's."""
        if event_id is None:
            return
        self._roll(_wall())
        if event_id in self._live_events:
            self._bucket(event_id)["raw"] += 1

    def note_input(
        self,
        event_id: Optional[int],
        outcome_id: int,
        probability: float,
        kind: str,
        venue_ts=None,
    ) -> Optional[InputMark]:
        """Stamp one accepted input. Called under the socket's buffer lock, so
        `seq` order is buffer order."""
        if event_id is None:
            return None
        self._seq += 1
        self.stats["inputs"] += 1
        ordinal = self._inputs_by_event.get(event_id, 0) + 1
        self._inputs_by_event[event_id] = ordinal
        self._last_seq_by_event[event_id] = self._seq
        try:
            venue_ms = int(venue_ts) if venue_ts is not None else None
        except (TypeError, ValueError):
            venue_ms = None
        mark = InputMark(
            seq=self._seq, event_id=event_id, outcome_id=outcome_id,
            probability=probability, kind=kind, recv_wall=_wall(),
            recv_mono=_mono(), venue_ts_ms=venue_ms, event_ordinal=ordinal,
        )
        try:
            self._count_input(mark)
        except Exception:
            # The delivery count is evidence about evidence; it must never cost
            # the caller the mark (#837's chain needs it).
            logger.warning("tail receipt: delivery count failed", exc_info=True)
        return mark

    # ── #10090 delivery receipt ──────────────────────────────────────────────

    def _bucket(self, event_id: int) -> dict:
        bucket = self._window.get(event_id)
        if bucket is None:
            observed_from = max(
                self._window_start if self._window_start is not None else self._run_start,
                self._run_start,
                self._live_since.get(event_id, self._run_start),
            )
            bucket = self._window[event_id] = {
                "raw": 0, "outcomes": {}, "stamps": [], "stamps_dropped": 0,
                "previews": [], "previews_dropped": 0, "from": observed_from,
            }
        return bucket

    def _count_input(self, mark: InputMark) -> None:
        """Accepted, and whether it CHANGED this outcome's price: a repeat is a
        venue message at the price we already held — transport, not news. The
        first input of a run for an outcome has no prior and says so."""
        self._roll(mark.recv_wall)
        if mark.event_id not in self._live_events:
            return
        per = self._bucket(mark.event_id)["outcomes"].setdefault(
            mark.outcome_id, [0, 0, 0, 0],  # accepted, changed, repeats, first
        )
        per[0] += 1
        last = self._last_p.setdefault(mark.event_id, {})
        prior = last.get(mark.outcome_id)
        per[1 if prior is not None and prior != mark.probability
            else 2 if prior is not None else 3] += 1
        last[mark.outcome_id] = mark.probability
        self._uncovered.setdefault(
            mark.event_id, deque(maxlen=DELIVERY_RECEIPT_MAX_PENDING)
        ).append((mark.seq, mark.recv_wall, mark.outcome_id))
        # Last: the trail is the newest receipt, and never costs the others.
        # F1: a first input has nothing to differ from, so it never joins.
        headline = not any(mark.outcome_id in ids for ids in self.trail_excluded)
        self._trail.note_input(
            mark, headline and prior is not None and prior != mark.probability,
            first=headline and prior is None,
        )

    def _note_stamp(self, event_id: int, disposition: tuple) -> None:
        """A committed stamp: the published `rev`, its `stamped_at` (the SSE
        frame's `updated_at`, byte for byte), and the inputs it carried — every
        input of this event up to the newest committed one, so a stamp that
        coalesced many inputs says how many (`covered`) and how old the oldest
        was. Inputs that arrived after the committed one wait for the next.

        #10090 field 1: the item's sixth part is `first_new_recv`, the receipt
        of the oldest input this stamp is the FIRST publication to carry to
        readers, judged against the last value published by preview or stamp
        (`ReaderTrail.stamp`); `-` when it carried no change readers lacked."""
        rev = disposition[4] if len(disposition) > 4 else None
        status = disposition[5] if len(disposition) > 5 else None
        was_live = event_id in self._live_events
        mark = self._committed.pop(event_id, None)
        frame = self._stamp_frames.pop(event_id, None)
        if len(disposition) > 6 and disposition[6] is False:
            # A queued fresh stamp reread the board. The staged input is not
            # joined to that reading; only the exact observation trace can
            # make that claim. Record the stamp without input coverage.
            mark = None
        if status == "live":
            if not was_live:
                self._live_since[event_id] = _wall()
            self._live_events.add(event_id)
        elif not was_live:
            return
        covered, oldest = 0, None
        pending = self._uncovered.get(event_id)
        if mark is not None and pending:
            while pending and pending[0][0] <= mark.seq:
                _seq, wall, _outcome = pending.popleft()
                covered += 1
                if oldest is None:
                    oldest = wall
        first_new = None
        try:
            # The frame's own value, only if it is THIS stamp's (same revision).
            value = frame[1] if frame is not None and frame[0] == rev else None
            first_new = self._trail.stamp(
                event_id, value, rev, mark.seq if mark is not None else None,
            )
        except Exception:
            logger.warning("tail receipt: trail stamp failed", exc_info=True)
        if status is not None and status != "live":
            # This stamp is still the game's (its minute was live); after it,
            # nothing more is kept for the event.
            self._live_events.discard(event_id)
            self._uncovered.pop(event_id, None)
            self._last_p.pop(event_id, None)
            self._live_since.pop(event_id, None)
            self._trail.forget(event_id)
        self._roll(_wall())
        bucket = self._bucket(event_id)
        if len(bucket["stamps"]) >= DELIVERY_RECEIPT_MAX_STAMPS:
            bucket["stamps_dropped"] += 1
            return
        bucket["stamps"].append("@".join((
            "-" if rev is None else str(rev),
            str(disposition[2]),
            _iso(mark.recv_wall) if mark is not None else "-",
            _iso(oldest) or "-",
            str(covered),
            _iso(first_new) or "-",
        )))

    def note_stamp_frame(self, event_id: int, rev, probability, status) -> None:
        """The value a stamp's frame publishes, noted when the frame is built
        (before COMMIT); `_note_stamp` takes it only for the same revision, so
        a stamp that rolled back leaves nothing it could be credited with."""
        if status == "live" or event_id in self._live_events:
            self._stamp_frames[event_id] = (rev, probability)

    def note_committed_rows(self, rows) -> None:
        """A price write's committed RETURNING rows, before any await: the
        trail inputs they stored are committed (`ReaderTrail`)."""
        self._trail.note_committed_rows(rows)

    def settle(self, event_id: int, rows) -> None:
        """F2(c): a live event's reading changed nothing readers see; the
        committed inputs whose prices it blended leave the trail uncredited
        (`ReaderTrail.settle`)."""
        if event_id in self._live_events:
            self._trail.settle(event_id, rows)

    def note_preview(self, frame: dict, meta, reply) -> None:
        """#10090 fields 1+2 — one ledger send, after it (`observe_publication`).
        Only what Redis PUBLISHED reached readers. A blend of a live event is
        listed as base_rev:seq@published_at@first_new_recv; a revoke drops
        readers back to the committed value (`ReaderTrail.revoke`)."""
        if not reply or reply[0] != "published":
            return
        preview = frame.get("preview") or {}
        kind = preview.get("kind")
        event_id = frame.get("event_id")
        if event_id not in self._live_events or kind not in ("blend", "revoke"):
            return
        wall = _wall()
        if kind == "revoke":
            self._trail.revoke(event_id, wall)
            return
        _seen, first_new = self._trail.preview(event_id, frame.get("p"), preview.get("base_rev"))
        self._roll(wall)
        bucket = self._bucket(event_id)
        if len(bucket["previews"]) >= DELIVERY_RECEIPT_MAX_PREVIEWS:
            bucket["previews_dropped"] += 1
            return
        base = preview.get("base_rev")
        bucket["previews"].append("%s:%s@%s@%s" % (
            "-" if base is None else base, preview.get("seq", "-"), _iso(wall),
            _iso(first_new) or "-",
        ))

    def note_writer_revision(self, writer: str, event_id: int, rev, stamped_at) -> None:
        """#10090 field 3 — a revision this process's OTHER writer published
        for a live event (a Polymarket withdrawal's invalidation). Its frame
        carries no value, so it is credited with no input (`-`), and what
        readers show next is unknown here (`ReaderTrail.revision`)."""
        if event_id not in self._live_events:
            return
        self._trail.revision(event_id, rev)
        logger.info(
            WRITER_RECEIPT_FORMAT, self.source, writer, event_id,
            "@".join(("-" if rev is None else str(rev), str(stamped_at), "-", "-", "0", "-")),
        )

    def _roll(self, wall: float, *, final: bool = False) -> None:
        """Close the UTC minute once the clock has left it (or at exit), one
        line per live event that had a message, an input or a stamp in it."""
        size = DELIVERY_RECEIPT_WINDOW_S
        if self._window_start is None:
            self._window_start = math.floor(wall / size) * size
            return
        if not final and wall < self._window_start + size:
            return
        window_end = wall if final else self._window_start + size
        # Only live games ever get a bucket (`note_raw`, `_count_input`,
        # `_note_stamp` all check); the most active are written.
        ranked = sorted(
            self._window,
            key=lambda eid: (-sum(v[0] for v in self._window[eid]["outcomes"].values()),
                             -len(self._window[eid]["stamps"]), eid),
        )
        kept = ranked[:DELIVERY_RECEIPT_MAX_EVENTS]
        for event_id in sorted(kept):
            self._emit(event_id, self._window[event_id], window_end)
        if len(ranked) > len(kept):
            logger.info(
                "live_blend_refresh[%s]: delivery-receipt-overflow run=%s "
                "window_start=%s events_dropped=%d dropped=%s",
                self.source, self.run, _iso(self._window_start),
                len(ranked) - len(kept), ",".join(map(str, sorted(ranked[len(kept):])[:50])),
            )
        self._window = {}
        self._window_start = math.floor(wall / size) * size

    def _emit(self, event_id: int, bucket: dict, window_end: float) -> None:
        """`window_start`/`window_s` are the seconds this run actually watched
        the game inside the minute — never the minute's floor before it.
        Bounded to `DELIVERY_RECEIPT_MAX_LINE_CHARS` in the shed order that
        constant names (each item counted), never by dropping a stamp."""
        per = bucket["outcomes"]
        totals = [sum(v[i] for v in per.values()) for i in range(4)]
        self.stats["delivery_lines"] += 1
        previews = list(bucket.get("previews", ()))
        previews_dropped = bucket.get("previews_dropped", 0)
        trail_dropped = self._trail.dropped(event_id, reset=True)
        retired, first_skipped = self._trail.retired(event_id, reset=True)
        trail_retired = ",".join(f"{reason}:{count}" for reason, count in retired.items())
        shown = {oid: f"{oid}:{v[0]}:{v[1]}:{v[2]}:{v[3]}" for oid, v in per.items()}
        quiet_first = sorted(per, key=lambda oid: (per[oid][0], oid))
        tags = _switch_tags(event_id, bucket["from"])

        def line():
            return DELIVERY_RECEIPT_FORMAT % (
                self.source, self.run, event_id, _iso(bucket["from"]),
                max(0.0, window_end - bucket["from"]),
                bucket["raw"], *totals,
                ",".join(item for _, item in sorted(shown.items())) or "-",
                ";".join(bucket["stamps"]) or "-", bucket["stamps_dropped"],
                self.source, ";".join(previews) or "-",
                previews_dropped, trail_dropped, trail_retired, first_skipped,
                len(per) - len(shown), tags,
            )

        message = line()
        while len(message) > DELIVERY_RECEIPT_MAX_LINE_CHARS:
            idle = [i for i, item in enumerate(previews) if item.endswith("@-")]
            if idle:
                previews.pop(idle[0])
                previews_dropped += 1
            elif quiet_first:
                # As many of the quietest as cover the excess, so a 500-outcome
                # game is not re-formatted once per item; never more than the
                # one-at-a-time loop would shed (the loop re-checks).
                excess = len(message) - DELIVERY_RECEIPT_MAX_LINE_CHARS
                while quiet_first and excess > 0:
                    excess -= len(shown.pop(quiet_first.pop(0))) + 1
            elif previews:
                previews.pop(0)
                previews_dropped += 1
            else:
                break
            message = line()
        logger.info("%s", message)

    def aged_obligations(self, wall: float, budget_s: float, event_ids=None) -> dict:
        """#10090 `stamp_wait_reason` — each LIVE event's oldest input no
        stamp has covered yet, once it is ``budget_s`` old (of ``event_ids``
        only, when given): event id -> (seq, outcome id, age s, and the
        newest committed input's (seq, age s) or None). Pure read."""
        aged = {}
        candidates = self._uncovered if event_ids is None else event_ids
        for event_id in candidates:
            pending = self._uncovered.get(event_id)
            if not pending or event_id not in self._live_events:
                continue
            seq, recv_wall, outcome_id = pending[0]
            age = wall - recv_wall
            if age < budget_s:
                continue
            committed = self._committed.get(event_id)
            aged[event_id] = (
                seq, outcome_id, age,
                None if committed is None else (committed.seq, wall - committed.recv_wall),
            )
        return aged

    def unowed(self, marks: Iterable[InputMark]) -> None:
        """#10090 (A1) — committed inputs no stamp reads (a live game's prop
        board): they leave the stamp-coverage queue without being 'covered'."""
        upto: dict[int, dict[int, int]] = {}
        for mark in marks:
            upto.setdefault(mark.event_id, {})[mark.outcome_id] = mark.seq
        for event_id, delivered in upto.items():
            pending = self._uncovered.get(event_id)
            if pending:
                # Every input of a delivered outcome up to the one its commit
                # carried, repeats included.
                kept = [entry for entry in pending
                        if entry[0] > delivered.get(entry[2], -1)]
                pending.clear()
                pending.extend(kept)

    def stage(self, marks: Iterable[InputMark]) -> None:
        """The revisions a flush just COMMITTED — called after the commit and
        immediately before `refresh`, which takes them. Per event, the newest
        input the write carried."""
        self._staged, self._staged_wall = self.staged_for(marks)

    @staticmethod
    def staged_for(marks: Iterable[InputMark]) -> tuple[dict[int, InputMark], float]:
        """`stage`'s per-event newest mark, without taking the staging slot —
        for a cohort admitted into a refresh that already took its own."""
        staged: dict[int, InputMark] = {}
        for mark in marks:
            held = staged.get(mark.event_id)
            if held is None or mark.seq > held.seq:
                staged[mark.event_id] = mark
        return staged, _wall()

    def roll(self) -> None:
        """Close the delivery minute if the clock has left it. Every flush
        reaches here (via `take_staged` or `refresh_pending`), so a minute
        closes within a flush of its end even when no input arrives."""
        self._roll(_wall())

    def take_staged(self) -> tuple[dict[int, InputMark], Optional[float]]:
        self._roll(_wall())
        staged, wall = self._staged, self._staged_wall
        self._staged, self._staged_wall = {}, None
        return staged, wall

    # ── #10090 `price_commit_ack_wall` (the writer's side) ───────────────────

    def note_commit_ack(self, marks: Iterable[Optional[InputMark]], wall: float) -> None:
        """The price transaction carrying these exact inputs returned at
        ``wall``. An open chain held on one of them takes it now (its offer
        came first); otherwise it waits for the chain that input opens. An
        input's first acknowledgement is its clock."""
        for mark in marks:
            if mark is None:
                continue
            chain = self._open.get(mark.event_id)
            if chain is not None and chain.rev.seq == mark.seq:
                if chain.commit_ack_wall is None:
                    chain.commit_ack_wall = wall
                continue
            acks = self._commit_acks.get(mark.event_id)
            if acks is None:
                if len(self._commit_acks) >= PRICE_COMMIT_ACK_EVENTS:
                    del self._commit_acks[next(iter(self._commit_acks))]
                acks = self._commit_acks[mark.event_id] = {}
            acks.setdefault(mark.seq, wall)
            if len(acks) > PRICE_COMMIT_ACK_PER_EVENT:
                del acks[min(acks)]

    def _prune_commit_acks(self, event_id: int, below_seq: int) -> None:
        """Acknowledgements of this event's inputs older than ``below_seq``:
        a staging that offered a newer input superseded them."""
        acks = self._commit_acks.get(event_id)
        if acks is None:
            return
        for seq in [seq for seq in acks if seq < below_seq]:
            del acks[seq]
        if not acks:
            del self._commit_acks[event_id]

    # ── the refresher's side ─────────────────────────────────────────────────

    def _open_chain(self, origin, mark, stored_wall, now) -> _TailChain:
        chain = _TailChain(
            origin=origin, rev=mark, stamp_rev=mark,
            stored_wall=stored_wall if stored_wall is not None else _wall(),
            opened_wall=_wall(), opened_mono=now,
        )
        acks = self._commit_acks.get(mark.event_id)
        if acks is not None:
            chain.commit_ack_wall = acks.pop(mark.seq, None)
            if not acks:
                del self._commit_acks[mark.event_id]
        self._open[mark.event_id] = chain
        self.stats["opened"] += 1
        return chain

    def observe(self, staged, stored_wall, due: set, now: float) -> None:
        """Before the batch: a committed revision for an event with an open
        chain is a later write inside the hold; one for an event the throttle
        is holding opens a chain."""
        for event_id, mark in staged.items():
            if self._commit_acks:
                self._prune_commit_acks(event_id, mark.seq)
            held = self._committed.get(event_id)
            if event_id in self._live_events and (held is None or mark.seq > held.seq):
                self._committed[event_id] = mark
            if event_id in self._live_events:
                try:
                    self._trail.note_flushed(event_id, mark.seq)
                except Exception:
                    logger.warning("tail receipt: trail flush failed", exc_info=True)
            chain = self._open.get(event_id)
            if chain is not None:
                chain.later_committed += 1
                chain.stamp_rev = mark
            elif event_id not in due:
                self._open_chain("throttle", mark, stored_wall, now)

    def resolve(self, due, dispositions, staged, stored_wall, now) -> None:
        """After a batch that COMMITTED: close each attempted chain on what the
        batch did with it. A lock skip keeps (or opens) the chain — the retry
        is the path, and it is counted."""
        if self.confirmed is not None:
            for event_id in due:
                try:
                    self.confirmed.resolved(
                        event_id, dispositions.get(event_id, ("no_market",)))
                except Exception:
                    logger.warning("tail receipt: confirmed_at resolve failed", exc_info=True)
        for event_id in due:
            disposition = dispositions.get(event_id, ("no_market",))
            if disposition[0] == "stamped":
                try:
                    self._note_stamp(event_id, disposition)
                except Exception:
                    # Never at the expense of closing this or any other chain.
                    logger.warning("tail receipt: delivery stamp failed", exc_info=True)
            chain = self._open.get(event_id)
            if disposition[0] == "lock":
                if chain is None:
                    mark = staged.get(event_id)
                    if mark is None:
                        continue
                    chain = self._open_chain("lock", mark, stored_wall, now)
                chain.lock_retries += 1
                continue
            if chain is not None:
                self._close(event_id, disposition[0], now, disposition=disposition)

    def resolve_failed(
        self, due, dispositions, staged, stored_wall, requeued, exc, now,
    ) -> None:
        """After a batch that did NOT commit. A stamp the batch had made rolled
        back with it — `commit_failed`; otherwise the batch died first —
        `batch_failed`. The refresher retains all due events, so their chains
        stay open and count the failure. The defensive dropped result is only
        for a caller that explicitly omits an event from `requeued`."""
        if self.confirmed is not None:
            try:
                self.confirmed.failed(due)
            except Exception:
                logger.warning("tail receipt: confirmed_at failure failed", exc_info=True)
        for event_id in due:
            disposition = dispositions.get(event_id, ("",))
            failure = "commit_failed" if disposition[0] == "stamped" else "batch_failed"
            chain = self._open.get(event_id)
            if chain is None:
                mark = staged.get(event_id)
                if mark is None or event_id not in requeued:
                    continue
                origin = "lock" if disposition[0] == "lock" else "batch"
                chain = self._open_chain(origin, mark, stored_wall, now)
                if origin == "lock":
                    chain.lock_retries += 1
            if event_id in requeued:
                if failure == "commit_failed":
                    chain.commit_failures += 1
                else:
                    chain.batch_failures += 1
                continue
            self._close(event_id, f"dropped_{failure}", now, error=type(exc).__name__)

    def close_all(self, reason: str) -> None:
        """The consumer is exiting: every chain still open was never stamped by
        this run, and the next run's fresh refresher cannot inherit it."""
        if self.confirmed is not None:
            with contextlib.suppress(Exception):
                self.confirmed.close()
        now = _mono()
        open_at_close = len(self._open)
        for event_id in sorted(self._open):
            self._close(event_id, reason, now)
        self._commit_acks.clear()
        # #10090 — the partial minute the run ended in, with its real length,
        # and the live games for the next run of this source.
        self._roll(_wall(), final=True)
        _live_handoff[self.source] = frozenset(self._live_events)
        logger.info(
            "live_blend_refresh[%s]: tail-receipt summary run=%s reason=%s "
            "inputs=%d opened=%d logged=%d coalesced=%d open_at_close=%d "
            "delivery_lines=%d",
            self.source, self.run, reason, self.stats["inputs"],
            self.stats["opened"], self.stats["logged"], self.stats["coalesced"],
            open_at_close, self.stats["delivery_lines"],
        )

    def _close(self, event_id, result, now, *, disposition=(), error=None) -> None:
        chain = self._open.pop(event_id)
        later_inputs = self._inputs_by_event.get(event_id, 0) - chain.rev.event_ordinal
        quiet = later_inputs == 0 and chain.later_committed == 0
        value = previous = stamped_at = None
        if result == "stamped":
            _, value, stamped_at, previous = disposition[:4]
        elif result in ("unchanged", "preview_only", "unobserved", "stale"):
            value = disposition[1]
        moved = result == "stamped" and (previous is None or previous != value)

        coalescible = (
            result in self.COALESCIBLE
            and not (result == "stamped" and quiet)
            and chain.origin != "lock"
            and not chain.lock_retries
            and not chain.commit_failures
            and not chain.batch_failures
        )
        if coalescible:
            last = self._last_logged.get(event_id)
            if last is not None and (now - last) < self.coalesce_s:
                self._coalesced[event_id] = self._coalesced.get(event_id, 0) + 1
                self.stats["coalesced"] += 1
                return
            self._last_logged[event_id] = now

        self.stats["logged"] += 1
        rev, stamp_rev = chain.rev, chain.stamp_rev
        logger.info(
            "live_blend_refresh[%s]: tail-receipt run=%s event=%s result=%s "
            "quiet=%s moved=%s origin=%s rev_seq=%d rev_outcome=%s rev_p=%.6f "
            "rev_kind=%s rev_recv_wall=%s rev_venue_ts_ms=%s stored_wall=%s "
            "held_wall=%s stamp_rev_seq=%s stamped_at=%s value=%s previous=%s "
            "later_inputs=%d later_committed=%d last_input_seq=%s "
            "lock_retries=%d commit_failures=%d batch_failures=%d held_s=%.3f "
            "recv_to_close_s=%.3f coalesced=%d error=%s%s%s%s",
            self.source, self.run, event_id, result, quiet, moved, chain.origin,
            rev.seq, rev.outcome_id, rev.probability, rev.kind,
            _iso(rev.recv_wall), rev.venue_ts_ms, _iso(chain.stored_wall),
            _iso(chain.opened_wall),
            "-" if len(disposition) > 6 and disposition[6] is False else stamp_rev.seq,
            stamped_at, value, previous,
            later_inputs, chain.later_committed,
            self._last_seq_by_event.get(event_id), chain.lock_retries,
            chain.commit_failures, chain.batch_failures,
            now - chain.opened_mono, now - rev.recv_mono,
            self._coalesced.pop(event_id, 0), error,
            f" price_commit_ack_wall={_iso(chain.commit_ack_wall)}"
            if price_commit_ack_log_on() else "",
            _switch_tags(event_id),
            _reader_held_tag(self.reader_held, event_id),
        )


def atomic_stamp_expression(
    source: str, value: float, stamped_at=None, eligibility=None,
    observed_basis=None,
):
    """The SET expression that stamps ONE source key WITHOUT reading it first.

    live/305's defect, reproduced against real Postgres 2026-09-16: the Kalshi
    and Polymarket consumers run under one `asyncio.gather`
    (`run_kalshi_ws.py`), each owning its own `LiveBlendRefresher`, and each was
    doing SELECT -> merge in Python -> write the whole column back. Two arms
    that read the same snapshot and write 250 ms apart produce this:

        kalshi arm's private view : {'betting': 0.5, 'kalshi': 0.53}
        pm arm's private view     : {'betting': 0.5, 'polymarket': 0.52}
        WHAT THE DATABASE KEPT    : {'betting': 0.5, 'polymarket': 0.52}

    The later writer does not merely overwrite a stale sibling VALUE — it drops
    the sibling key the earlier writer just created, because the dict it merged
    into never contained it. That is the whole of the reported hero flicker: the
    same question published 89 ms apart as 0.51 and 0.475, each arm blending its
    own fresh price against a view of the other that the database no longer
    holds. It also explains the direction, which a simple staleness story cannot
    — the Kalshi arm held the HIGHER own price (0.53 vs 0.52) and published the
    LOWER aggregate, because its private copy had no Polymarket reading in it at
    all.

    So the merge moves to the server. ``a || b`` on JSONB is evaluated inside the
    UPDATE, and under READ COMMITTED a concurrent UPDATE on the same row blocks,
    then re-evaluates this expression against the row the winner committed —
    the same reason ``SET n = n + 1`` is safe where read-modify-write is not.
    Two arms can no longer erase each other no matter how they interleave.

    The semantics are `aggregation.stamp_source_reading`'s, expressed in SQL,
    and they must stay that way: the top-level `||` copies every sibling SOURCE
    through untouched, and the inner `||` copies every sibling KEY inside this
    source's own entry through untouched (`weight`, `home_probability`, and the
    eligibility record a writer that has not adopted it must never strip). A
    `None` eligibility omits the key rather than writing a null, so it cannot
    clear a record another writer left — the same non-destructive rule the
    Python helper documents.

    ``observed_basis`` follows the Python helper's OPPOSITE rule for that key
    (#8910): given, it is written bound to ``value``; omitted, any basis on the
    entry is removed, so a writer that cannot date its reading never leaves the
    previous reading's observation attached to a new value.
    """
    import json

    from sqlalchemy import Text, case, cast, func, literal, type_coerce
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import Event
    from app.utils.aggregation import OBSERVED_BASIS_KEY, OBSERVED_VALUE_KEY
    from app.utils.probability_eligibility import ELIGIBILITY_KEY

    # Production stamps inside the UPDATE, not before waiting for its row lock.
    # READ COMMITTED re-evaluates this expression against a concurrent updater's
    # committed tuple. A pre-lock Python clock can otherwise make the NEWER
    # aggregate look like an older replay to the phone (#837).
    # Explicit clocks remain available for deterministic historical/helper use.
    entry: dict = {"value": value}
    if stamped_at is not None:
        entry["updated_at"] = stamped_at.isoformat()
    if eligibility is not None:
        entry[ELIGIBILITY_KEY] = eligibility.to_entry()
    if observed_basis:
        entry[OBSERVED_BASIS_KEY] = dict(observed_basis)
        entry[OBSERVED_VALUE_KEY] = value

    empty = cast(literal("{}"), JSONB)

    def as_object(expression):
        """`isinstance(x, dict)`, in SQL. COALESCE is NOT enough here.

        The column is nullable with no default, so it can hold SQL NULL *or*
        the JSONB scalar `null` — and `||` does not treat the second as empty,
        it PROMOTES it: `'null'::jsonb || '{"k":"v"}'::jsonb` evaluates to
        `[null, {"k": "v"}]`. A COALESCE-only guard would therefore turn the
        blend column into an ARRAY on the first stamp of such a row, which the
        Python helper's `dict(sources or {})` / `isinstance(existing, dict)`
        never could. Caught by the real-Postgres gate, not by review.
        """
        return case((func.jsonb_typeof(expression) == "object", expression), else_=empty)

    column = Event.win_probability_sources
    entry_expression = cast(literal(json.dumps(entry)), JSONB)
    if stamped_at is None:
        entry_expression = entry_expression.concat(
            func.jsonb_build_object("updated_at", func.clock_timestamp())
        )
    prior_entry = as_object(column[source])
    if not observed_basis:
        for key in (OBSERVED_BASIS_KEY, OBSERVED_VALUE_KEY):
            prior_entry = type_coerce(
                prior_entry.op("-")(cast(literal(key), Text)), JSONB
            )
    merged_entry = prior_entry.concat(entry_expression)
    return as_object(column).concat(
        func.jsonb_build_object(cast(literal(source), Text), merged_entry)
    )


def observation_admits_clause(source: str, observed_basis):
    """WHERE clause: the stored entry saw none of these rows LATER than this reading.

    #8910 (F3 of the other-writers review, plus Codex's re-observation
    variant). This lane reads its rows, orients, then stamps; the two-minute
    poll can re-observe the venue after a goal, compare under its row lock and
    stamp the post-goal price inside that window. The stamp that followed wrote
    the pre-goal price with the NEWEST clock — the worst shape, because every
    clock guard downstream (the poll's, the phone's #920 ordering, the chart's
    strictly-newer rule) then trusts the older price. The unchanged re-stamp arm
    does the same when the lane re-observed the old value before the poll wrote.

    The decision therefore lives IN the stamping UPDATE rather than in a read
    before it: under READ COMMITTED an UPDATE that waited on the poll's lock
    re-evaluates its WHERE against the row the poll committed, so the comparison
    holds at the commit with no lock of this lane's own and no extra round trip.
    It is `aggregation.reading_regresses_stored_observation` in SQL, and must
    stay that: per contributor, the stored basis trusted only while bound to a
    NUMERIC stored value (Codex, on 30162c4dd6: JSON equality alone trusted
    `"0.6" = "0.6"`, `true = true` and `null = null`, which the Python rule
    abstains on — a malformed entry would then refuse the very write that
    repairs it; a jsonb number is always finite, so `number` is the whole of
    `_finite_number`), a non-number clock on either side ignored (never cast — a
    malformed stored string must not abort the batch), and no shared row means
    no opinion.

    ``None`` when this reading has no basis: the stamp then runs unguarded, as
    it always has, and strips the old basis (`atomic_stamp_expression`).
    """
    from sqlalchemy import bindparam, text
    from sqlalchemy.dialects.postgresql import JSONB

    from app.utils.aggregation import OBSERVED_BASIS_KEY, OBSERVED_VALUE_KEY

    if not observed_basis:
        return None
    entry = (
        "(CASE WHEN jsonb_typeof(events.win_probability_sources) = 'object' "
        "AND jsonb_typeof(events.win_probability_sources -> :obs_source) = 'object' "
        "THEN events.win_probability_sources -> :obs_source "
        "ELSE '{}'::jsonb END)"
    )
    stored_basis = (
        f"(CASE WHEN jsonb_typeof({entry} -> '{OBSERVED_BASIS_KEY}') = 'object' "
        f"AND jsonb_typeof({entry} -> 'value') = 'number' "
        f"AND {entry} -> '{OBSERVED_VALUE_KEY}' = {entry} -> 'value' "
        f"THEN {entry} -> '{OBSERVED_BASIS_KEY}' ELSE '{{}}'::jsonb END)"
    )
    return text(
        "NOT EXISTS (SELECT 1 "
        f"FROM jsonb_each({stored_basis}) AS stored_seen(row_key, seen) "
        "JOIN jsonb_each(:obs_basis) AS this_seen(row_key, seen) "
        "ON this_seen.row_key = stored_seen.row_key "
        "WHERE jsonb_typeof(stored_seen.seen) = 'number' "
        "AND jsonb_typeof(this_seen.seen) = 'number' "
        "AND (stored_seen.seen)::numeric > (this_seen.seen)::numeric)"
    ).bindparams(
        bindparam("obs_source", value=source),
        bindparam("obs_basis", value=dict(observed_basis), type_=JSONB),
    )


#: #10090 — set to 1, a stamp writes its `<source>_price_publish` intent in the
#: stamping statement itself (`stamp_with_publication_intent`) instead of a
#: second INSERT round trip after it. Default off. Read at call time.
STAMP_FUSED_INTENT_ENV = "LIVE_STAMP_FUSED_INTENT"


def stamp_fuses_intent() -> bool:
    return os.getenv(STAMP_FUSED_INTENT_ENV, "").strip().lower() in ("1", "true", "on", "yes")


def stamp_with_publication_intent(stamp, *, source: str, intent_source: str,
                                  event_id: int, value: float):
    """The stamp UPDATE and its publication intent as ONE statement.

    ``stamp`` is the stamp's UPDATE with its RETURNING of the bag and revision.
    It becomes a data-modifying CTE; the intent INSERT selects from that CTE's
    output, and the statement returns the same row the UPDATE alone returned
    (no row when it matched nothing or the admits guard refused). The INSERT
    reads only the RETURNING row, never a snapshot of `events`, so the revision
    is the trigger's post-wait value and `updated_at` the clock the bag stored,
    exactly as the separate INSERT read them back from Python. Its filter is
    the separate path's skip: no bag (SQL or JSON null), or no revision, owes
    no intent. A bag of any other non-object shape raised in Python before the
    INSERT and rolled the stamp back; it still does, taking this row too. One
    statement, one `statement_timeout`; the INSERT takes no row lock (no
    foreign key), and any failure rolls both back with the stamp's scope.
    """
    from sqlalchemy import Float, Integer, String, func, insert, literal, select

    from app.models.models import OwedChartPoint

    stamped = stamp.cte("stamped")
    bag = stamped.c.win_probability_sources
    rev = stamped.c.win_probability_sources_rev
    intent = insert(OwedChartPoint).from_select(
        ["source", "event_id", "value", "reading"],
        select(
            literal(intent_source, String),
            literal(event_id, Integer),
            literal(value, Float),
            func.jsonb_build_object(
                literal("rev", String), rev,
                literal("updated_at", String), bag[source]["updated_at"],
            ),
        # `jsonb_typeof` is NULL for SQL NULL and 'null' for JSON null; both
        # decode to Python None, which the separate path skips.
        ).where(func.jsonb_typeof(bag) != "null", rev.is_not(None)),
    ).cte("publication_intent")
    return select(bag, rev).add_cte(intent)


def restamp_records_no_observation(
    value: float, observed_at, sources, source: str,
) -> bool:
    """True when stamping ``value`` now would re-date a price nobody re-read.

    #5661, production 2026-09-26 14:24Z, Slovenia v Scotland (15290677): the
    moneyline's three Polymarket rows were last written at 13:28Z and Gamma was
    trading Slovenia at 0.225, while the served `polymarket` leg read 0.405
    stamped 14:24:35Z. This lane is handed an event whenever ANY of its
    outcomes flushes — the exact-score and corners books were ticking — so it
    recomputed 0.405 from the frozen moneyline, found it unchanged, and the
    45-second re-stamp above dated it with the database clock. It also drew a
    fresh 0.405 chart point each time, so the source line ran flat to the edge
    and looked current.

    That is #4028's forgery arriving through the one writer its fix never
    reached — the 120s poll and the 15-minute matcher both stamp
    `oldest_observation_time` — and here it does a second kind of damage: the
    poll orders its population stalest-first by exactly this stamp and drops
    the freshest end when its fetch window closes (2,534 Polymarket rows that
    pass). A forged-fresh stamp therefore parks the event behind every other
    game, so the one writer that WOULD re-read Gamma never reaches it. The
    fake heartbeat is what keeps the real refresh away.

    So the rule `source_observation_time` states — a re-stamp is only honest
    when it records a re-observation — applies here too: an UNCHANGED value may
    be re-stamped only if the rows it came from were seen AFTER the stamp the
    row already carries. A socket tick or a poll touch writes `last_updated`,
    so a quiet-but-healthy book still re-stamps; a book no writer has seen does
    not. Nothing is lost on weight: the hero's relative decay has a 10-minute
    grace, and the leg that ages past it is exactly the one that should.

    Deliberately narrow, and it ABSTAINS (returns False, i.e. today's
    behaviour) whenever it cannot know:

    * a MOVED value is never refused — every real move keeps #837's database
      clock, which the clients use to order frames;
    * ``observed_at`` None (a contributor that cannot say when it was seen,
      `oldest_observation_time`'s contract) or no parseable stored entry means
      there is nothing to compare, and "unknown" is not "stale".
    """
    from app.utils.aggregation import parse_source_entry

    if observed_at is None or not isinstance(sources, dict):
        return False
    stored_value, stored_at = parse_source_entry(sources.get(source))
    if stored_value is None or stored_at is None:
        return False
    if round(stored_value, 4) != value:
        return False
    return observed_at <= stored_at


def heartbeat_deadline(max_gap_s: float, sample_interval_s: float) -> float:
    """The age at which an unchanged value must be re-recorded, given sampling.

    A deadline is not the same thing as a sampling period, and setting the two
    equal quietly misses the bar. This path only *checks* every
    ``sample_interval_s``, so a deadline of exactly ``max_gap_s`` is first
    observed to be breached one whole sample LATE — the real worst-case gap
    becomes ``max_gap_s + sample_interval_s``. Subtracting the period means the
    sample that crosses the deadline lands at or before it, so the guarantee the
    caller asked for is the guarantee the table gets.
    """
    return max(1.0, float(max_gap_s) - float(sample_interval_s))


@dataclass(frozen=True)
class _ChartMarket:
    name: Optional[str]
    id: Optional[int]


@dataclass(frozen=True)
class _ChartOutcome:
    name: Optional[str]


@dataclass(frozen=True)
class _ChartReading:
    home_probability: Optional[float]
    away_probability: Optional[float]
    draw_probability: Optional[float]
    yes_probability: Optional[float]
    market: _ChartMarket
    outcome: _ChartOutcome
    snapshot_observed_at: object
    owned_history: bool = True
    #: #11181 — this point's `owed_chart_points` row, settled with the point.
    custody_id: Optional[int] = None


def _chart_reading(reading, observed_at):
    """Freeze only chart scalars before the stamp session closes (#10090)."""
    market = getattr(reading, "market", None)
    outcome = getattr(reading, "outcome", None)
    return _ChartReading(
        home_probability=getattr(reading, "home_probability", None),
        away_probability=getattr(reading, "away_probability", None),
        draw_probability=getattr(reading, "draw_probability", None),
        yes_probability=getattr(reading, "yes_probability", None),
        market=_ChartMarket(
            name=getattr(market, "name", None),
            id=getattr(market, "id", None),
        ),
        outcome=_ChartOutcome(name=getattr(outcome, "name", None)),
        snapshot_observed_at=observed_at,
    )


class OwedChartCustody:
    """#11181 — durable custody of committed chart observations.

    WHY. A committed stamp owes its chart point at its own observation time,
    and the chart writer can be held for seconds by another transaction's lock
    on `win_prob_snapshots` (production v5763 13:01:22Z: Kalshi's writer held
    5.364 s at 64 owed). Memory alone cannot meet an unwaiting headline, every
    observation and a finite bound at once, and it empties on a restart. So
    each owed point is also a row in `owed_chart_points`:

    * `record` INSERTs it inside the stamp's own event scope. The stamp commits
      only with its row and a failed INSERT fails the stamp. The table has no
      foreign key, so the insert takes no lock on the event or on any chart row.
    * `settle` DELETEs it first, in the same savepoint that writes the point.
      A row that is gone was already paid (a commit whose acknowledgement a
      crash lost, or another process's drain), and nothing is written twice.
    * `load` reads this source's rows that memory does not hold, oldest commit
      id first, so the drain recovers what past the memory bound or through a
      restart lives only here, in each event's own order.
    """

    async def record(self, session, source: str, event_id: int, value, reading) -> int:
        from sqlalchemy import insert

        from app.models.models import OwedChartPoint

        return (
            await session.execute(
                insert(OwedChartPoint)
                .values(
                    source=source,
                    event_id=event_id,
                    value=value,
                    reading=_chart_reading_payload(reading),
                )
                .returning(OwedChartPoint.id)
            )
        ).scalar_one()

    async def settle(self, session, custody_id: int) -> bool:
        from sqlalchemy import delete

        from app.models.models import OwedChartPoint

        return (
            await session.execute(
                delete(OwedChartPoint)
                .where(OwedChartPoint.id == custody_id)
                .returning(OwedChartPoint.id)
            )
        ).first() is not None

    async def load(self, session, source: str, held_ids, limit: int) -> list[tuple]:
        from sqlalchemy import select

        from app.models.models import OwedChartPoint

        query = select(
            OwedChartPoint.id, OwedChartPoint.event_id,
            OwedChartPoint.value, OwedChartPoint.reading,
        ).where(OwedChartPoint.source == source)
        if held_ids:
            query = query.where(OwedChartPoint.id.not_in(sorted(held_ids)))
        rows = await session.execute(query.order_by(OwedChartPoint.id).limit(limit))
        return [tuple(row) for row in rows.all()]


def _chart_reading_payload(reading) -> dict:
    """The frozen chart scalars as JSON; the observation time stays verbatim."""
    observed_at = reading.snapshot_observed_at
    if isinstance(observed_at, datetime):
        observed_at = observed_at.isoformat()
    return {
        "home_probability": reading.home_probability,
        "away_probability": reading.away_probability,
        "draw_probability": reading.draw_probability,
        "yes_probability": reading.yes_probability,
        "market_name": reading.market.name,
        "market_id": reading.market.id,
        "outcome_name": reading.outcome.name,
        "observed_at": observed_at,
    }


def _chart_reading_from_payload(custody_id: int, payload: dict) -> _ChartReading:
    return _ChartReading(
        home_probability=payload.get("home_probability"),
        away_probability=payload.get("away_probability"),
        draw_probability=payload.get("draw_probability"),
        yes_probability=payload.get("yes_probability"),
        market=_ChartMarket(name=payload.get("market_name"), id=payload.get("market_id")),
        outcome=_ChartOutcome(name=payload.get("outcome_name")),
        snapshot_observed_at=payload.get("observed_at"),
        custody_id=custody_id,
    )


#: #10090 — float tolerance on the per-event floor when it is read on the
#: flush-start clock. Consecutive starts are `period` apart by construction
#: (`run_flush_cadence`), but `(t + p) - t` can come back short of `p` at
#: dyno-uptime magnitudes when `p` is not a power of two (`WS_PRICE_FLUSH_SECONDS`
#: is an env knob: t = 1,000,000.1, p = 0.1 gives 0.09999999997671694), which
#: would throttle the very flush the floor is meant to admit. A microsecond is
#: far below any real cadence.
FLUSH_CLOCK_SLACK_S = 1e-6


async def run_flush_cadence(
    flush, period: float, stop=None, *, failed_retry_interval_s: Optional[float] = None,
    wake=None, work_count: Optional[Callable[[], int]] = None,
    wake_coalesce_s: Optional[float] = None,
) -> None:
    """#10090 — start a flush every ``period`` seconds, START to START.

    WHY. Both sockets used to `sleep(PRICE_FLUSH_SECONDS)` AFTER each flush
    finished, so the real cycle was the period PLUS the flush's own work, and a
    tick arriving just after a batch was taken waited for both. Production
    2026-10-06 16:01:37→16:02:37Z, the Kalshi stats line: 29→37 flushes in 60 s
    with ~4,600 updates buffered in that minute — one flush per ~7.5 s on a 2 s
    setting, i.e. ~5.5 s of work plus the 2 s sleep on every cycle. The work is
    not removed here; the sleep stops being added on top of it.

    WHAT IS PRESERVED.

    * One flush at a time. The next starts only after the current one returns,
      so a slow flush makes the next start late — never two in flight — and the
      buffer keeps coalescing per outcome meanwhile (backpressure unchanged).
    * The ceiling. Actual work starts at most once per ``period``. Unchanged
      callers count every flush; opt-in callers distinguish empty probes from
      attempted work. A flush taking longer than ``period`` is followed by
      the next at once (rate ``1/work``, not more).
    * The retry interval. A flush that reports failure (returns ``False``) waits
      a full ``period`` from when it FAILED, exactly as before. An opt-in caller
      may pass ``failed_retry_interval_s`` to keep its previous retry delay while
      shortening only its healthy timer (#10662). Unchanged callers retain their
      configured period, including custom periods.
    * Unchanged callers first flush one ``period`` after the loop starts.
      An opt-in wake may start unused budget sooner, including after idle.
    * An opt-in ``wake_coalesce_s`` gives a woken flush ONE fixed pause before
      it starts, so frames already arriving in the same burst (both legs of a
      game sent back to back) enter the buffer before it snapshots. Without it
      the wake ran between two such frames: the event stamped half-updated and
      its second leg waited out the per-event floor (9aab164651). The pause is
      fixed, never extended by later arrivals, never waits for a missing leg,
      and applies only to a wake — timer, retry and back-to-back flushes under
      continuous input never pay it.

    ``flush`` is called with the flush's start on the refresher's clock
    (`_mono`), which the refresher uses for its per-event floor. Actual work
    starts remain at least ``period`` apart; an empty probe stamped nothing,
    so a subsequent input may wake sooner without bypassing that floor.

    #10657 — ``stop`` (an ``asyncio.Event``) ends the loop at its next turn.
    The consumer sets it before it cancels the loop, because a cancellation
    alone is not a stop: one lost inside a flush's dependencies left an
    earlier run's loop calling ``refresh_pending`` on that run's CLOSED
    sessions every 6 s on production (2026-10-07 02:53Z, 33 and 9 events,
    across a recycle). Checked after every sleep and every flush; a stopped
    loop never starts another flush — the consumer's own drain is the last.
    """
    # An opt-in buffered-input event may shorten only an unused timer phase.
    # `work_count` belongs to the caller: it increments inside the actual flush
    # when price/withdrawal/debt work was attempted. Empty timer probes therefore
    # cannot spend the real-work budget. No callback spawns a task per tick.
    # Unchanged callers still count every flush, with their original first wait.
    import asyncio

    def stopped() -> bool:
        return stop is not None and stop.is_set()

    retry_period = period if failed_retry_interval_s is None else failed_retry_interval_s
    due = _mono() + period
    not_before = _mono()  # no actual flush has used the budget yet
    while not stopped():
        wait = due - _mono()
        if wait > 0:
            if wake is None or _mono() < not_before:
                # Budget/retry waits never wake early. Ticks coalesce into the
                # same Event while this sleep retains the full fixed bound.
                await asyncio.sleep(wait)
            else:
                try:
                    async with asyncio.timeout(wait):
                        await wake.wait()
                except TimeoutError:
                    pass  # retain ordinary timer/debt probes during quiet input
                else:
                    wake.clear()
                    if wake_coalesce_s:
                        await asyncio.sleep(wake_coalesce_s)
                        if stopped():
                            return
                    due = _mono()
                    continue
            if stopped():
                return
        started = max(due, _mono())
        before = work_count() if work_count is not None else None
        if wake is not None:
            # Clear BEFORE the flush captures its batch. A tick during its
            # work sets the same bounded event for the next eligible turn.
            wake.clear()
        ok = await flush(started)
        used = work_count is None or work_count() != before
        due = started + period if ok is not False else _mono() + retry_period
        if used or ok is False:
            not_before = due


#: #10657 — how long a consumer waits, after its final drain, for its stopped
#: flush and stats loops to return. A loop mid-flush finishes that flush (its
#: sessions are still open until the consumer returns); one still running
#: after this is reported by name, never waited on forever.
LOOP_REAP_TIMEOUT_S = 15.0

#: #10090 idle bound: closed `HeldRowQuotes` samplers still unwinding their
#: cancellation, by source, until that source's run reaps its loops. The final
#: drain parks cancelled observation-preview reads here too.
_closing_samplers: dict[Optional[str], set] = {}


def _park_closing_sampler(source: Optional[str], task) -> None:
    if task is not None and not task.done():
        _closing_samplers.setdefault(source, set()).add(task)


async def reap_stopped_loops(source: str, tasks, *, timeout_s: float = LOOP_REAP_TIMEOUT_S) -> int:
    """Wait (bounded) for a consumer run's stopped loops; return how many are
    STILL running. Never raises and never cancels again: the caller already
    set the stop event and cancelled them. A non-zero return is logged as an
    error because that loop outlives its run (#10657)."""
    import asyncio

    deadline = asyncio.get_running_loop().time() + timeout_s
    still: set = set()
    try:
        pending = [t for t in tasks if t is not None and not t.done()]
        if pending:
            try:
                _done, still = await asyncio.wait(pending, timeout=timeout_s)
            except Exception:
                still = {t for t in pending if not t.done()}
        if still:
            logger.error(
                "live_blend_refresh[%s]: %d consumer loop(s) still running %.0fs "
                "after the run stopped them: %s",
                source, len(still), timeout_s,
                sorted(getattr(t, "get_name", lambda: "?")() for t in still),
            )
    finally:
        # The run's closed idle samplers (`hand_off_pending`, replacement) join
        # here even when a cancellation lands on this reap (812/903 review).
        unreaped = await _join_closing_samplers(source, deadline)
    return len(still) + unreaped


async def _join_closing_samplers(source: Optional[str], deadline: float) -> int:
    """Join `source`'s closed idle samplers by `deadline`; return how many still run.

    A cancellation landing here is held until they finish or the budget ends,
    then re-raised. A sampler still running stays registered (its next reap
    owns it) and is logged; nothing is cancelled again.
    """
    loop = asyncio.get_running_loop()
    interrupted: Optional[BaseException] = None
    while True:
        pending = {t for t in _closing_samplers.get(source, ()) if not t.done()}
        if pending:
            _closing_samplers[source] = pending
        else:
            _closing_samplers.pop(source, None)
        remaining = deadline - loop.time()
        if not pending or remaining <= 0:
            break
        try:
            await asyncio.wait(pending, timeout=remaining)
        except asyncio.CancelledError as exc:
            interrupted = exc
    if pending:
        logger.error(
            "live_blend_refresh[%s]: %d idle bound sampler(s) still unwinding at the reap deadline",
            source, len(pending),
        )
    if interrupted is not None:
        raise interrupted
    return len(pending)


# Event context needed by the prepared resolver/stamp, including aggregate
# fallbacks. Unrelated score/metadata JSON must not ride every linked prop row.
PREPARED_EVENT_FIELDS = (
    "id",
    "sport_key",
    "home_team_name",
    "away_team_name",
    "status",
    "completed_at",
    "commence_time",
    "win_probability_sources",
    "espn_win_prob_home",
    "opening_home_probability",
)

# Resolver identity, semantic/settlement admission and exact observation clocks.
# Descriptions, images, calibration, volume and other presentation columns do
# not participate in the live reading and must not hydrate/copy on every quote.
PREPARED_MARKET_FIELDS = (
    "id", "source", "external_id", "event_id", "name", "status", "market_metadata",
)
PREPARED_OUTCOME_FIELDS = (
    "id", "market_id", "name", "rank", "current_probability", "last_updated", "is_winner",
    "external_id", "resolution_source",
)


def _json_row_patch(fill, row) -> dict:
    """#10090 `STAMP_READ_JSON_ONCE`: the event JSON fields one row carries."""
    patch: dict = {}
    fill(row, patch)
    return patch


class HeldRowQuotes:
    """#11138 — a received quote whose price-row write a lock holds.

    The stamp derives a source's value from `futures_outcomes`, so a foreign
    transaction holding one price row (catalog, rerank, resolution) held the
    blend with it: local real-PG lab on cdd20661, PM .82 reached the folded
    hero after 3.69 s while Kalshi, arriving 350 ms later, took 64 ms.

    ORDERED BY A DATABASE-CLOCK LOWER BOUND, NEVER BY WORKER WALL TIME. A
    `clock_timestamp()` sample that COMPLETED before an input was accepted is a
    lower bound for that input in the same clock domain as
    `futures_outcomes.last_updated` (written by `now()` on the same primary).
    The bound is frozen when the input is accepted (`note_input`) and carried
    with the flush's own chunk snapshot (`bound_for`), so a retry, a later
    sample or a newer tick on the same leg can never re-date it. A stored row
    at or after its bound is ambiguous: the stored row is kept and the ordinary
    price writer resolves the debt. No clock-offset estimate, no future stamp.

    WHOLE EVENT OR NOTHING (lane1 review B1/B2, 2026-10-17). Admission takes
    one event's legs from ONE chunk snapshot, and the overlay applies to every
    held leg of an event or to none (`overlay_event`), so a stamp never mixes
    two venue snapshots: on a three-way market that would print a field no
    venue ever quoted.

    Nothing uncommitted is published: the stamp that carries a held quote
    commits on the events row as before, with `observed_value` and a per-row
    `observed_basis` naming the bound. That committed stamp is the durability
    point; the price row is a projection the existing buffer keeps retrying.
    A later stamp built from the still-held row has an earlier basis and
    `observation_admits_clause` refuses it in the UPDATE, after a restart too,
    when this object is empty.

    Bounded: one input record per accepted outcome and one quote per held
    outcome, released when its write lands or its book is withdrawn.
    """

    #: One optional DB round trip per nonempty game chunk. A sample that times
    #: out backs later samples off. Preview owners get one early recovery
    #: opportunity; sustained failure then costs at most one timeout per long
    #: window however many chunks a flush plans.
    SAMPLE_TIMEOUT_S = 0.15
    SAMPLE_BACKOFF_S = 5.0
    #: One early recovery probe per preview-clock failure episode, then the
    #: existing long backoff. A brief DB timeout must not freeze observations
    #: for five seconds after reads recover. No accepted input is re-dated.
    SAMPLE_RECOVERY_S = 0.25
    #: #10090 — `stored_at_or_after` waits at most this for a relation lock.
    AMBIGUITY_READ_LOCK_TIMEOUT_MS = 10
    #: #10090 IDLE BOUND (Root page max, run 20261021T111728). Samples run only
    #: after a phase commits, so after a quiet spell the newest completed one is
    #: as old as the source's previous phase, and the first input after it
    #: previews THAT time (PM venue 11:18:01.262 printed 11:17:59.866). While
    #: an input for one of the owner's preview events arrived within
    #: IDLE_ACTIVE_S, ONE task per instance re-reads the same sample about
    #: every IDLE_SAMPLE_S (plus read time; grace and backoff stretch it — a
    #: period, not a latency guarantee), with the same timeout and backoff, on
    #: the same pool. It never starts a read while one is in flight; a phase
    #: may still start beside an idle read, and the ordinal keeps the newer.
    #: The semantics are unchanged: a sample that completed before
    #: acceptance, frozen at `note_input`. Lifecycle: `close()` latches; the
    #: owner's teardown (`hand_off_pending`) or replacement (the refresher's
    #: `held_quotes` setter) closes it and `reap_stopped_loops` joins it.
    IDLE_SAMPLE_S = 0.25
    IDLE_ACTIVE_S = 30.0
    #: An input noted after the last sample STARTED is owed its phase's own
    #: post-commit sample; the idle task leaves that phase this long first.
    #: Later inputs cannot restart that grace while a slow phase is outstanding.
    IDLE_PHASE_GRACE_S = 1.0

    def __init__(self) -> None:
        self._quotes: dict[int, tuple[float, float]] = {}
        self._input_bounds: dict[int, tuple[int, float, float | None]] = {}
        self._database_bound: float | None = None
        self._sample_backoff_until = 0.0
        self._sample_failure_episode = False
        self._sample_failure_ordinal = 0
        self.sample_failures = 0
        # Idle bound (class doc). The owning refresher installs its CURRENT
        # preview events; empty means no idle sampling at all.
        self.preview_events: Callable[[], Container[int]] = frozenset
        #: #10090 `preview_at_receipt`: the owning refresher's receipt seam,
        #: told every accepted input with its frozen bound. None: nothing.
        self.on_receipt: Optional[Callable[[Any, Optional[float]], None]] = None
        self._sessions = None
        self._idle_task: Optional[asyncio.Task] = None
        self._closed = False
        self._sample_started = 0  # ordinal of the newest sample started
        self._sample_published = 0  # ordinal of the sample `_database_bound` holds
        self._graph_sample_ordinal = 0
        self._graph_idle_recovery_used = False
        self._sampling = 0
        self._last_sample_started = -math.inf
        self._last_sample_done = -math.inf
        self._last_input_at = -math.inf
        self._phase_grace_started = -math.inf
        self._last_preview_input_at = -math.inf
        self.idle_samples = 0
        self.idle_skips = 0

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    @staticmethod
    async def _sleep(seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def sample_database_clock(self, sessions) -> bool:
        """Bounded read; only inputs accepted AFTER it completes may use it."""
        from sqlalchemy import func, select

        if self._now() < self._sample_backoff_until:
            return False
        if self._sample_failure_episode:
            if self._sampling:
                return False
            # Consume the recovery opportunity BEFORE the first await. A
            # concurrent caller or cancellation cannot multiply early probes.
            self._sample_backoff_until = self._now() + self.SAMPLE_BACKOFF_S
        self._sessions = sessions
        self._sample_started += 1
        ordinal = self._sample_started
        self._sampling += 1
        self._last_sample_started = self._now()
        try:
            async with asyncio.timeout(self.SAMPLE_TIMEOUT_S):
                async with sessions() as session:
                    value = (await session.execute(select(func.clock_timestamp()))).scalar_one()
                # Publish the sample only after the session has fully exited,
                # and never over one that STARTED later: an idle read that
                # overlapped a phase's post-commit read must not replace it.
                if ordinal > self._sample_published:
                    self._sample_published = ordinal
                    self._database_bound = value.timestamp()
                # A later graph may own the published timestamp, but a genuine
                # standalone success still proves this failure episode ended.
                if ordinal > self._sample_failure_ordinal:
                    self._sample_failure_episode = False
                    self._sample_backoff_until = 0.0
                    self._graph_idle_recovery_used = False
                self._last_sample_done = self._now()
                return True
        except Exception:
            # The ordinary price writer stays available when the optional fast
            # path cannot establish an order. Cancellation still propagates.
            self.sample_failures += 1
            if ordinal > self._sample_published:
                delay = (
                    self.SAMPLE_RECOVERY_S
                    if not self._sample_failure_episode and self.preview_events()
                    else self.SAMPLE_BACKOFF_S
                )
                self._sample_failure_episode = True
                self._sample_failure_ordinal = max(self._sample_failure_ordinal, ordinal)
                self._sample_backoff_until = max(
                    self._sample_backoff_until, self._now() + delay
                )
            return False
        finally:
            self._sampling -= 1

    def begin_write_clock(self) -> tuple[int, float]:
        """Reserve ordering for a clock returned by a caller-owned price write.

        Do not block idle sampling behind a possibly held price transaction.
        The caller must discard this ticket on failed/cancelled session exit.
        """
        self._sample_started += 1
        return self._sample_started, self._now()

    def publish_write_clock(self, ticket, value) -> bool:
        """After successful transaction exit, bound FUTURE inputs only.

        A committed write is not proof that the shorter standalone clock probe
        recovered. Keep its failure/backoff and graph-recovery allowance intact.
        False keeps the caller's existing standalone sample as fallback.
        """
        if self._closed or ticket is None or not isinstance(value, datetime):
            return False
        bound = value.timestamp()
        if not math.isfinite(bound):
            return False
        ordinal, started = ticket
        if ordinal <= self._sample_published:
            return self._database_bound is not None and self._database_bound >= bound
        self._sample_published = ordinal
        self._database_bound = bound
        self._last_sample_started = max(self._last_sample_started, started)
        self._last_sample_done = self._now()
        return True

    def note_input(self, mark) -> None:
        """Freeze the newest completed sample as this input's lower bound."""
        self._input_bounds[mark.outcome_id] = (
            mark.seq, round(float(mark.probability), 6), self._database_bound,
        )
        on_receipt = self.on_receipt
        if on_receipt is not None:
            try:
                on_receipt(mark, self._database_bound)
            except Exception:  # noqa: BLE001 — a preview never fails an input
                pass
        now = self._now()
        if self._last_input_at <= self._last_sample_started:
            self._phase_grace_started = now
        self._last_input_at = now
        if getattr(mark, "event_id", None) in self.preview_events():
            self._last_preview_input_at = now
            self._start_idle_sampler()

    def _start_idle_sampler(self) -> None:
        if self._closed or self._sessions is None or (
                self._idle_task is not None and not self._idle_task.done()):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._idle_task = loop.create_task(self._idle_sampler(), name="held-quotes-idle-bound")

    async def _idle_sampler(self) -> None:
        """Keep the bound fresh while preview inputs arrive; exits by itself."""
        try:
            while not self._closed:
                now = self._now()
                graph_recovery_deadline = None
                if (now - self._last_preview_input_at >= self.IDLE_ACTIVE_S
                        or not self.preview_events()):
                    return
                due = self._last_sample_done + self.IDLE_SAMPLE_S
                if self._last_input_at > self._last_sample_started:
                    due = max(due, self._phase_grace_started + self.IDLE_PHASE_GRACE_S)
                if (self._sample_failure_episode and not self._sampling
                        and not self._graph_idle_recovery_used
                        and self._graph_sample_ordinal > self._sample_failure_ordinal
                        and now >= due
                        and now < self._sample_backoff_until
                        and now - self._last_preview_input_at >= self.IDLE_PHASE_GRACE_S):
                    # A successful graph is evidence for ONE recovery probe
                    # after traffic quiets, not a reset on every busy read.
                    # Consume before awaiting, including cancellation/failure.
                    self._graph_idle_recovery_used = True
                    graph_recovery_deadline = self._sample_backoff_until
                    self._sample_backoff_until = min(self._sample_backoff_until, now)
                due = max(due, self._sample_backoff_until)
                if now < due:
                    await self._sleep(min(due - now, self.IDLE_SAMPLE_S))
                    continue
                if self._sampling:
                    self.idle_skips += 1  # a phase's read is in flight
                    await self._sleep(self.IDLE_SAMPLE_S)
                    continue
                self.idle_samples += 1
                probe_ordinal = self._sample_started + 1
                try:
                    await self.sample_database_clock(self._sessions)
                finally:
                    if (graph_recovery_deadline is not None
                            and self._sample_failure_episode
                            and self._sample_failure_ordinal <= probe_ordinal):
                        # The extra attempt must not postpone the original
                        # retry, nor shorten a newer caller's failure episode.
                        self._sample_backoff_until = min(
                            self._sample_backoff_until, graph_recovery_deadline,
                        )
        except Exception:
            logger.warning("held quotes: idle bound sampler stopped", exc_info=True)

    def close(self) -> Optional[asyncio.Task]:
        """Latch closed and cancel the idle sampler; it never starts again.

        Returns the still-running task for the owner to join (or None).
        """
        self._closed = True
        task, self._idle_task = self._idle_task, None
        if task is None or task.done():
            return None
        task.cancel()
        return task

    def bound_for(self, mark) -> float | None:
        """This exact input's frozen bound, or None (another input, or none yet).

        Read under the consumer's buffer lock in the same block that snapshots
        the chunk's prices and marks, so the bound travels with the snapshot
        and a newer tick arriving during the write cannot drop one leg.
        """
        if mark is None:
            return None
        entry = self._input_bounds.get(getattr(mark, "outcome_id", None))
        if entry is None or entry[2] is None or entry[0] != getattr(mark, "seq", None):
            return None
        if entry[1] != round(float(mark.probability), 6):
            return None
        return entry[2]

    def hold(self, quotes: dict[int, tuple[float, float]]) -> set[int]:
        """Record ``{outcome_id: (price, frozen_bound)}``; returns ids that changed."""
        changed = set()
        for oid, (price, bound) in quotes.items():
            if bound is None:
                continue  # no completed sample preceded this input: no fast path
            # The price row stores NUMERIC(7, 6): read what it will hold.
            entry = (round(float(price), 6), float(bound))
            if self._quotes.get(oid) != entry:
                self._quotes[oid] = entry
                changed.add(oid)
        return changed

    def _new_bounds(self, quotes) -> dict[int, float]:
        """``{outcome_id: bound}`` for the quotes not already held as given."""
        return {
            oid: float(bound)
            for oid, (price, bound) in quotes.items()
            if bound is not None
            and self._quotes.get(oid) != (round(float(price), 6), float(bound))
        }

    def has_new_quotes(self, quotes) -> bool:
        """Whether admission may read (`stored_at_or_after`) or change a held
        observation. False exactly when that read would be skipped, so the
        Kalshi cadence (Root attempt32) counts only admission that can work."""
        return bool(self._new_bounds(quotes))

    async def stored_at_or_after(self, sessions, quotes) -> set[int] | None:
        """#10090 — the ids among NEW ``{outcome_id: (price, bound)}`` whose
        stored row is already at or after its bound: `_ambiguous`, read before
        the hold instead of inside the stamp.

        Held anyway, such a quote owed its event a stamp the overlay refuses,
        so it republished the stored row while the event fence kept the price
        write that carries the quote out (Root attempt20, real PG: the stored
        .70 stamp ran 171→580 ms, two retries fenced behind it, .82 published
        at 664 ms; attempt19 1000.563 ms). An unchanged quote is not read
        again. A row lock never blocks this read; a relation lock gets
        AMBIGUITY_READ_LOCK_TIMEOUT_MS. None means unknown: the caller holds
        as before. It shares the sample's backoff window both ways.
        """
        from sqlalchemy import select

        from app.models.models import FuturesOutcome
        from app.utils.aggregation import _coerce_timestamp
        from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, lock_timeout_value

        new = self._new_bounds(quotes)
        if not new:
            return set()
        if self._now() < self._sample_backoff_until:
            return None
        try:
            async with asyncio.timeout(self.SAMPLE_TIMEOUT_S):
                async with sessions() as session:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(self.AMBIGUITY_READ_LOCK_TIMEOUT_MS)},
                    )
                    rows = (await session.execute(
                        select(FuturesOutcome.id, FuturesOutcome.last_updated)
                        .where(FuturesOutcome.id.in_(sorted(new)))
                    )).all()
        except Exception:
            # Shares the sample's window: a sick pool still costs one timeout
            # per window, and later sample attempts back off behind this one.
            self.sample_failures += 1
            self._sample_failure_episode = True
            self._sample_failure_ordinal = self._sample_started
            self._sample_backoff_until = self._now() + self.SAMPLE_BACKOFF_S
            return None
        found = set()
        for oid, last_updated in rows:
            stored = _coerce_timestamp(last_updated)
            if stored is not None and stored.timestamp() >= new[oid]:
                found.add(oid)
        return found

    def release(self, outcome_ids: Iterable[int]) -> None:
        for oid in outcome_ids:
            self._quotes.pop(oid, None)

    def __contains__(self, outcome_id) -> bool:
        return outcome_id in self._quotes

    def _ambiguous(self, outcome) -> bool:
        from app.utils.aggregation import _coerce_timestamp

        held = self._quotes.get(getattr(outcome, "id", None))
        if held is None:
            return False
        stored = _coerce_timestamp(getattr(outcome, "last_updated", None))
        return stored is not None and stored.timestamp() >= held[1]

    def overlay_event(self, entries) -> None:
        """Every held leg of one event, or none: one ambiguous leg defers all.

        ``entries`` are one event's `MarketOutcomes`. Each entry's outcome list
        is replaced by its overlaid copy; no outcome object is mutated.
        """
        entries = list(entries)
        if any(self._ambiguous(o) for entry in entries for o in entry.outcomes):
            return
        # #10090 (K1): bundled Challenger children are separate
        # contracts in one market. An unheld sibling committed after a held
        # leg's frozen bound makes that mixed snapshot ambiguous. Scope this
        # new refusal to the bundled branch; other venue/pair rules stay as-is.
        from app.utils.aggregation import _coerce_timestamp

        for entry in entries:
            market = getattr(entry, "market", None)
            ticker = (getattr(market, "external_id", None) or "").upper()
            if not (
                getattr(market, "source", None) == "kalshi"
                and ticker.startswith("KXATPCHALLENGERMATCH-")
                and len(ticker.split("-")) == 2
                and len(entry.outcomes) == 2
            ):
                continue
            bounds = [
                self._quotes[row.id][1] for row in entry.outcomes
                if getattr(row, "id", None) in self._quotes
            ]
            if len(bounds) != 1:
                continue
            for row in entry.outcomes:
                if getattr(row, "id", None) in self._quotes:
                    continue
                stored = _coerce_timestamp(getattr(row, "last_updated", None))
                if stored is not None and stored.timestamp() >= bounds[0]:
                    return
        for entry in entries:
            entry.outcomes[:] = [self.overlaid(o) for o in entry.outcomes]

    def overlaid(self, outcome):
        """This outcome as the stamp should read it: a COPY carrying the held
        quote when the stored row is strictly older than its bound, else the
        outcome itself.

        A copy and not an assignment, deliberately: the namespaces
        `_read_groups` builds are read material for one stamp, and nothing
        here may look like (or become) a write to a `futures_outcomes` row —
        the price row's only writer is the consumer's chunk UPDATE.
        """
        from datetime import datetime, timezone
        from types import SimpleNamespace

        held = self._quotes.get(getattr(outcome, "id", None))
        if held is None or self._ambiguous(outcome):
            return outcome
        price, bound = held
        return SimpleNamespace(**{
            **vars(outcome),
            "current_probability": price,
            "last_updated": datetime.fromtimestamp(bound, timezone.utc),
        })


class _FreshAdmission:
    """#10090 — the door a running `refresh` holds open for committed cohorts.

    One refresh owns the refresher at a time. A whole cohort its caller
    COMMITS after that refresh began joins it here (`admit_fresh`) instead of
    waiting for every earlier stamp to return. Fixed for the call: its flush
    clock, everything it took or admitted (``events``), its same-event fence
    (``holding``: those whose stamp is still queued or running; one that has
    returned may be admitted again, #10090), the FRESH_STAMP_WORKERS session
    slots every one of its stamp
    and preparation sessions holds, and its one frame sender. Each admitted
    event keeps its own staged input mark, retry origin and flush clock: a
    LATER flush's cohort may join while the call's own stamps are unfinished
    (``own_done``), and is stamped on its own flush's clock, never the call's.
    """

    def __init__(self, flush_started, clock, events, *, release_wake=None) -> None:
        import asyncio

        self.flush_started = flush_started
        self.clock = clock
        self.events: set[int] = set(events)
        self.holding: set[int] = set(events)
        #: Admitted events waiting for a stamp worker: live games (their
        #: latest read said live) in ``live_queue``, every other in ``queue``.
        self.queue: deque = deque()
        self.live_queue: deque = deque()
        self.live_run = 0
        #: #10090 held-first: held live stamps started in a row while an
        #: unheld live game waited (READER_FIRST_RUN).
        self.held_run = 0
        self.workers: set = set()
        self.admitted: set[int] = set()
        self.retry: set[int] = set()
        self.completed: set[int] = set()
        self.failed: set[int] = set()
        self.staged: dict[int, InputMark] = {}
        self.stored_wall: dict[int, Optional[float]] = {}
        #: Each admitted event's own flush clock (its cohort's `flush_started`).
        self.clocks: dict[int, float] = {}
        #: Set once the call's own stamps have returned. #10090: it no longer
        #: closes the door — an admitted stamp held past it (a row lock, a slow
        #: frame) shut every later game out until it returned. The door closes
        #: when the admitted workers go idle (`_admission_join`) or when a
        #: lifecycle drain stops admitting (`stop_admitting`); either way the
        #: call then drains only what was queued before the close.
        self.own_done = False
        self.closed = False
        #: #10090 — the owed (debt) events this call is stamping beside its
        #: admitted cohorts: debt keeps progressing while a call lives on, but
        #: never holds more than ADMITTED_DEBT_SLOTS stamp workers (default 1).
        self.debts: set[int] = set()
        #: #10090 — owed LIVE events stamped beside the cohorts outside
        #: `debts` (ADMITTED_LIVE_DEBT_SLOTS): pre-game debt never holds a
        #: live game's turn.
        self.live_debts: set[int] = set()
        self.publish: Optional[Callable[[list[dict]], Awaitable[None]]] = None
        self.publish_inline: Optional[Callable[[list[dict]], Awaitable[None]]] = None
        #: #10090 — per event, how many of its attempts in this call have
        #: returned (or gone back to debt), and a future resolved at the next
        #: one: a lifecycle wait drains a fixed frontier of attempts by these
        #: counts, so a re-admitted event's NEW attempt cannot extend it.
        self.released: dict[int, int] = {}
        self._released_signal = None
        #: #10090 functional release wake (the PM stamp owner's): told of
        #: every actual release so a game flush that fenced a newer quote on
        #: these events runs now, not at the next periodic timer.
        self.release_wake: Optional[Callable[[Iterable[int]], None]] = release_wake
        #: #10090 stage trace only (None unless one is configured): told of
        #: every actual release. Never raises into the fence.
        self.on_release: Optional[Callable[[Iterable[int]], None]] = None

    @property
    def debt(self) -> Optional[int]:
        """The owed event in the door's slot, as with one slot (the default);
        with more slots, or a live game riding its own allowance
        (`live_debts`), the lowest-numbered of them."""
        riding = self.debts | self.live_debts
        return min(riding) if riding else None

    def next_queued(
        self, held: Container[int] = frozenset(), skip: Container[int] = (),
    ) -> Optional[int]:
        """The admitted event the next free worker stamps: the oldest live
        one, unless ADMITTED_LIVE_RUN live stamps in a row have started while
        a non-live one waited — then that oldest non-live one. Among live
        ones, the oldest a reader holds (``held``) goes first, unless
        READER_FIRST_RUN of those in a row have started while an unheld one
        waited — then the oldest unheld one.

        #10090 write-under-queued: an event in ``skip`` (its price rows are
        under a write lease) is left queued in place and the next eligible
        one is taken; the pre-game turn a leased pre-game head would have
        taken goes to a live one rather than idling the worker (the lease
        ends within the flush and the head keeps its place). None when every
        queued event is skipped. An empty ``skip`` is today's pick exactly."""
        if self.live_queue and (not self.queue or self.live_run < ADMITTED_LIVE_RUN):
            picked = self._next_live(held, skip)
            if picked is not None:
                if self.queue:
                    self.live_run += 1
                return picked
        picked = self._first_eligible(self.queue, skip)
        if picked is not None:
            self.live_run = 0
            return picked
        if skip and self.live_queue:
            return self._next_live(held, skip)
        return None

    @staticmethod
    def _first_eligible(queue: deque, skip: Container[int]) -> Optional[int]:
        if not skip:
            return queue.popleft() if queue else None
        for index, event_id in enumerate(queue):
            if event_id not in skip:
                del queue[index]
                return event_id
        return None

    def _next_live(self, held: Container[int], skip: Container[int] = ()) -> Optional[int]:
        live_queue = self.live_queue
        if not skip:
            if not held:
                return live_queue.popleft()
            eligible = list(enumerate(live_queue))
        else:
            eligible = [(i, eid) for i, eid in enumerate(live_queue) if eid not in skip]
            if not eligible:
                return None

        def take(position: int) -> int:
            index, event_id = eligible[position]
            del live_queue[index]
            return event_id

        if not held:
            return take(0)
        first_held = next((p for p, (_i, eid) in enumerate(eligible) if eid in held), None)
        if first_held is None:
            self.held_run = 0
            return take(0)
        unheld_waiting = first_held > 0 or any(eid not in held for _i, eid in eligible)
        if not unheld_waiting:
            self.held_run = 0
            return take(0)
        if self.held_run >= READER_FIRST_RUN:
            self.held_run = 0
            first_unheld = next(p for p, (_i, eid) in enumerate(eligible) if eid not in held)
            return take(first_unheld)
        self.held_run += 1
        return take(first_held)

    def release(self, event_ids) -> None:
        """These events' stamps returned, or went back to debt unstamped."""
        self.holding.difference_update(event_ids)
        self.debts.difference_update(event_ids)
        self.live_debts.difference_update(event_ids)
        for event_id in event_ids:
            self.released[event_id] = self.released.get(event_id, 0) + 1
        signal, self._released_signal = self._released_signal, None
        if signal is not None and not signal.done():
            signal.set_result(None)
        if self.release_wake is not None:
            self.release_wake(event_ids)
        if self.on_release is not None:
            with contextlib.suppress(Exception):
                self.on_release(event_ids)

    def released_signal(self):
        """A future resolved at this call's next `release`."""
        import asyncio

        if self._released_signal is None:
            self._released_signal = asyncio.get_running_loop().create_future()
        return self._released_signal


class _HoldingFrontier:
    """#10090 — the attempts one call holds (queued or running) at one instant.

    Drained once each has returned or gone back to debt. Counted per attempt,
    not read from `holding`: an event re-admitted after its frontier attempt
    returned is holding again, and waiting on `holding` would wait for that
    later attempt too — so continuous arrivals could extend the wait forever.
    """

    def __init__(self, window: "_FreshAdmission") -> None:
        self.window = window
        self.counts = {eid: window.released.get(eid, 0) for eid in window.holding}

    def drained(self) -> bool:
        released = self.window.released
        return all(released.get(eid, 0) > n for eid, n in self.counts.items())

    def changed(self):
        """A future resolved when one more attempt of this call returns."""
        return self.window.released_signal()


class LiveBlendRefresher:
    """Stateful per-source refresher, owned by one WS consumer run.

    State (throttles, inversion verdicts) is per-instance rather than global so
    the Kalshi and Polymarket consumers on the shared dyno cannot evict each
    other's entries, and so a reconnect starts clean.
    """

    @property
    def held_quotes(self) -> Optional[HeldRowQuotes]:
        return self.__dict__.get("_held_quotes")

    @held_quotes.setter
    def held_quotes(self, quotes: Optional[HeldRowQuotes]) -> None:
        previous = self.__dict__.get("_held_quotes")
        self.__dict__["_held_quotes"] = quotes
        if isinstance(previous, HeldRowQuotes) and previous is not quotes:
            # A replaced instance's idle sampler must not outlive it.
            _park_closing_sampler(getattr(self, "source", None), previous.close())
        if isinstance(quotes, HeldRowQuotes):
            # #10090 idle bound: this refresher's CURRENT preview events gate
            # the owner's idle sampler (legacy single-source and ledger alike).
            quotes.preview_events = lambda: getattr(self, "preview_events", frozenset())
            # #10090 `preview_at_receipt`: every accepted input, both venues.
            quotes.on_receipt = self._note_receipt_input

    def __init__(
        self,
        source: str,
        *,
        owns_preview_maintenance: bool = True,
        min_refresh_interval_s: float = DEFAULT_MIN_REFRESH_INTERVAL_S,
        failed_retry_interval_s: float = DEFAULT_FAILED_RETRY_INTERVAL_S,
        inversion_ttl_s: float = DEFAULT_INVERSION_TTL_S,
        unchanged_restamp_interval_s: float = UNCHANGED_RESTAMP_INTERVAL_S,
        snapshot_interval_s: float = DEFAULT_SNAPSHOT_INTERVAL_S,
        snapshot_max_gap_s: float = DEFAULT_SNAPSHOT_MAX_GAP_S,
        stamp_lock_timeout_ms: Optional[int] = DEFAULT_STAMP_LOCK_TIMEOUT_MS,
        session_factory=None,
        observation_read_factory=None,
        chart_custody: Optional[OwedChartCustody] = None,
    ) -> None:
        self.source = source
        global _OWED_BUDGET_LOGGED
        if not _OWED_BUDGET_LOGGED:
            # #10090 — once per process, so a readout binds a window to its setting.
            _OWED_BUDGET_LOGGED = True
            logger.info(
                "live_blend_refresh[%s]: owed-stamp budget "
                "FRESH_FLUSH_PENDING_ATTEMPTS=%d PENDING_STAMP_BUDGET_S=%.3g "
                "ADMITTED_DEBT_SLOTS=%d ADMITTED_STAMP_BATCH=%d FRESH_STAMP_WORKERS=%d",
                source, FRESH_FLUSH_PENDING_ATTEMPTS, PENDING_STAMP_BUDGET_S,
                ADMITTED_DEBT_SLOTS, ADMITTED_STAMP_BATCH, FRESH_STAMP_WORKERS,
            )
        global _SPEED_SWITCH_LOGGED_PID
        if _SPEED_SWITCH_LOGGED_PID != os.getpid():
            # #10090 — once per process, the switchboard's readback: whether
            # the layer is on and today's values a trial alternates against.
            # Environment only; no Redis read.
            from app.tasks.speed_switches import today_env_in_force, trials_enabled

            _SPEED_SWITCH_LOGGED_PID = os.getpid()
            # Each switch whose today SPEED_SWITCH_TODAY_<NAME> sets; none, none shown.
            overrides = "".join(f" {name}={value}"
                                for name, value in today_env_in_force().items())
            logger.info(
                "speed_switch[pid=%d]: layer SPEED_SWITCH_TRIALS=%s "
                "today pending_attempts=%d abandon_optional_db=%d "
                "admitted_debt_slots=%d admitted_stamp_batch=%d%s",
                os.getpid(), "on" if trials_enabled() else "off",
                FRESH_FLUSH_PENDING_ATTEMPTS, int(optional_db_abandons()),
                ADMITTED_DEBT_SLOTS, ADMITTED_STAMP_BATCH, overrides,
            )
        #: #11181 — durable custody of owed chart points. Both production
        #: consumers pass one (guarded); None keeps every owed point in memory.
        self._chart_custody = chart_custody
        #: Rows may exist that memory does not hold: past its bound, or from a
        #: run or process before this one, so a new refresher starts by reading.
        self._custody_backlog = chart_custody is not None
        #: Points committed to custody alone, or possibly committed (a stamp
        #: whose COMMIT outcome is unknown); a load that overlaps one cannot
        #: conclude the table is drained.
        self._custody_only_committed = 0
        #: Custody-only points committed by this process, by row id: the
        #: publication each still waits on, and (capped at the memory bound)
        #: its snapshot clock, so a load treats it exactly as memory would.
        self._custody_ready: dict[int, asyncio.Event] = {}
        self._custody_clock: dict[int, float] = {}
        #: #11138 — the owning consumer's `HeldRowQuotes`, or None (no overlay).
        self.held_quotes = None
        #: #10090 — the Kalshi WS owner's current-book proof for the bundled
        #: Challenger pair (`compute_source_home_probability`). Off unless the
        #: owner installs all of them before its first refresh can run: the
        #: requirement, the midpoint and primary-price readers, and the landed
        #: primary-quote reader (`current_primary_input(row, held, overlaid=)`).
        self.require_current_book_proof = False
        self.current_book_midpoint = None
        self.current_book_primary_price = None
        self.current_primary_input = None
        #: #11317 P2 — optional: ticker -> a comparable value of every
        #: in-memory input the proof reads for that ticker (book, accepted
        #: primary input, its custody, the held quote). Installed ⇒ a refused
        #: pair is PARKED until one of its values changes (or the shared sweep
        #: runs) instead of being read again every flush. None ⇒ the refusal
        #: re-queues on every flush, as before.
        self.current_book_signature = None
        #: Parked refused pairs: event id -> (tickers, signature at refusal).
        #: Still owed (handed off at a recycle), not yet worth a read.
        self._book_refused: dict[int, tuple] = {}
        self._book_refused_sweep_at: Optional[float] = None
        #: #2471 — the owning consumer's session factory, so the stamp borrows
        #: the consumer's one engine instead of building a pool per batch.
        #: None ⇒ ``app.tasks.base.get_task_session``, looked up per batch.
        self._session_factory = session_factory
        self._observation_read_factory = observation_read_factory
        self.min_refresh_interval_s = min_refresh_interval_s
        self.failed_retry_interval_s = failed_retry_interval_s
        self.inversion_ttl_s = inversion_ttl_s
        self.unchanged_restamp_interval_s = unchanged_restamp_interval_s
        self.snapshot_interval_s = snapshot_interval_s
        self.snapshot_max_gap_s = snapshot_max_gap_s
        #: None or 0 waits as long as Postgres lets it (the pre-#837-tail
        #: behaviour, kept reachable for the deadlock-containment rig).
        self.stamp_lock_timeout_ms = stamp_lock_timeout_ms
        #: Events whose stamp gave up on a lock. Carried into the NEXT refresh
        #: whatever that flush's batch holds: the price that was not stamped is
        #: already in `futures_outcomes`, so waiting for the event to tick again
        #: would strand it on a quiet market.
        self._lock_retry: set[int] = set()
        #: #837 tail — events whose price was written while their throttle was
        #: running. Stamped by the first flush after the throttle expires,
        #: whatever that flush's batch holds. Dropped instead, the stored price
        #: waited for another tick on ANY outcome of the game: production
        #: 2026-09-25 02:47:45–55Z, Padres @ Dodgers' 0.605 was written during
        #: the throttle; the moneyline sent nothing more until 02:47:57.5, so
        #: the stamp at 02:47:52 happened only because another of the game's
        #: markets ticked. On a quiet game the wait is the next tick or the
        #: 120s poll.
        self._throttle_deferred: set[int] = set()
        #: #10090 `handover_fresh` — owed events a lifecycle hand-over carried
        #: over committed (`keep_committed`); the next `refresh` that finds one
        #: due stamps it as fresh. Always a subset of what is still owed.
        self._carried_fresh: set[int] = set()
        #: #10090 `lock_retry_prompt` — row-lock skips owed a prompt attempt:
        #: event id -> the `_mono` time it is due. Always within `_lock_retry`.
        self._lock_prompt_at: dict[int, float] = {}
        #: Prompt attempts taken in an event's current run of row-lock skips.
        self._lock_prompt_taken: dict[int, int] = {}
        self._pending_continuation: list[int] = []
        self._pending_flush_started: Optional[float] = None
        #: This flush's old-stamp allowance, read when the flush starts.
        self._pending_attempts_limit = FRESH_FLUSH_PENDING_ATTEMPTS
        self._pending_started_at: Optional[float] = None
        self._pending_attempted = False
        self._pending_attempts = 0
        self._pending_fresh_flush = False
        #: #10090 — the latest flush whose committed cohort a running call of
        #: an EARLIER flush admitted; that flush is fresh-bearing when its own
        #: `refresh` begins.
        self._admitted_fresh_flush: Optional[float] = None
        #: #10090 — the turn order of owed events riding a running call's
        #: door (`window.debts`): a newly owed event joins the back, and each one
        #: taken goes to the back, so a row lock that is due again at once
        #: cannot take every turn from a writable sibling.
        self._debt_rotation: list[int] = []
        self._last_refresh_at: dict[int, float] = {}
        #: #10090 — the newest clock a caller has handed `_due`, and `_mono`
        #: when it was handed: the floor's "now", whatever the caller's clock.
        self._clock_high: Optional[tuple[float, float]] = None
        #: #10090 — per event, that current clock when it was last stamped
        #: (`_last_refresh_at` is the caller's clock, which may be a long
        #: flush's start). Read only while `_last_refresh_at` holds the event.
        self._last_refresh_current: dict[int, float] = {}
        #: Events whose last batch failed -> the monotonic time before which
        #: they are not due, whatever the throttle says.
        self._failed_hold_until: dict[int, float] = {}
        self._last_write_at: dict[int, float] = {}
        self._last_written_value: dict[int, float] = {}
        self._last_snapshot_at: dict[int, float] = {}
        # Local151 durable normal-price intent; no full frames retained in memory.
        self._normal_source = self.source + "_price_publish"
        self._normal_task = None
        #: #10090 — optional reads abandoned at their deadline, by kind, still
        #: finishing on their own task (`OPTIONAL_DB_ABANDON_ENV`).
        self._optional_db_running: dict[str, asyncio.Task] = {}
        self._optional_db_limits: dict[asyncio.Task, asyncio.TimerHandle] = {}
        self.optional_db_abandoned = 0
        self._normal_retry_at = 0.0
        self._normal_closed = False
        self._normal_has_debt = True  # one recovery discovery on startup
        self._normal_epoch = 0
        self._normal_after = 0
        self._normal_horizon = None
        # Positively acknowledged revisions, highest per event, settled by the
        # next recovery opportunity rather than on the publication path.
        self._normal_acked: dict[int, int] = {}
        # Revisions this process committed whose publication has not resolved
        # (held from before COMMIT). Discovery leaves them to that publication.
        self._normal_inflight: set[tuple[int, int]] = set()
        # One owner across refresh calls. A chart session cannot borrow slots
        # from a newer admission window or escape the three-session ceiling.
        self._session_slots = asyncio.Semaphore(FRESH_STAMP_WORKERS)
        #: #10090 — this minute's stamp transaction spans, for the venue line.
        self.stamp_spans = StampSpans()
        #: #10090 `stamp_wait_reason` lines (`STAMP_WAIT_REASON_ENV`).
        self.stamp_waits = StampWaitLog(source)
        self._history: list[tuple] = []
        self._history_task: Optional[asyncio.Task] = None
        self._history_count = 0  # committed debt plus pre-COMMIT reservations
        self._history_limit = HISTORY_POINT_LIMIT
        self._history_spill_limit = HISTORY_SPILL_LIMIT
        self._history_changed = asyncio.Event()
        self._history_reserved: dict[int, float] = {}
        self._history_retry_at: dict[int, float] = {}
        self._inversion: dict[int, tuple[float, bool]] = {}
        self.stats: dict[str, int] = {
            "considered": 0,
            "throttled": 0,
            "no_reading": 0,
            # #11317 — of `no_reading`, readings the bundled pair's current-book
            # proof withheld. `no_reading - bundled_refused` is every other cause.
            "bundled_refused": 0,
            "stamped": 0,
            "unchanged_skipped": 0,
            # #5661 — an unchanged value whose rows no writer has re-read since
            # the stored stamp. Not re-dated; see `restamp_records_no_observation`.
            "unobserved_skipped": 0,
            # #8910 — readings refused because the poll or the matcher had
            # already stored a later observation of the same rows.
            "stale_readings_refused": 0,
            "snapshots_written": 0,
            "snapshots_deduped": 0,
            "errors": 0,
            # live/034 S1 — SSE fanout. Counted so a publisher that is failing
            # every time is visible; a push path that dies quietly looks exactly
            # like a quiet market (gotcha #53).
            "published": 0,
            "publish_errors": 0,
            # #10090 — committed frames sent without `source_snapshot`
            # (no exact singleton revision, or a map that is not strict JSON).
            "source_snapshot_omitted": 0,
            # #837 tail — stamps that stopped waiting on another transaction's
            # row lock and were re-queued. Not an error: the retry is the path.
            "lock_skipped": 0,
            # #11138/#11181 — due chart points owed past the ordinary backlog
            # without waiting; each is still paid at its own time.
            "history_deferred": 0,
            # #11181 — due points carried by their custody row alone (past
            # the memory bound, or behind rows memory does not hold yet) until
            # a load moves them into memory in their event's order.
            "history_custody_only": 0,
            # #11181 — custody rows already settled when their point came up
            # (a commit whose acknowledgement was lost, or another drain).
            "history_already_paid": 0,
            # #10090 — owed points retired because their event row was deleted
            # after the stamp committed (seen on a retry only; ids never reuse).
            "history_event_gone": 0,
            # #9484 — committed market invalidations (`live:market:{id}`) this
            # consumer's writers published through the same client. Counted
            # for the same reason as `published`: a quiet market and a dead
            # market publisher must not look alike.
            "market_published": 0,
            "market_publish_errors": 0,
        }
        #: Lazily-built async Redis client, reused for the life of this
        #: refresher. Built on first publish rather than in __init__ so a
        #: consumer run that never stamps anything never opens a connection.
        self._redis = None
        #: #837 receipt — attached by a consumer that stamps its inputs
        #: (`TailReceipts`); None leaves this refresher exactly as it was.
        self.receipts: Optional[TailReceipts] = None
        #: What the current batch did with each event it attempted, for the
        #: receipt. Filled by `_refresh_batch`, read only after it returns.
        self._dispositions: dict[int, tuple] = {}
        #: #10090 — open only while a `refresh` runs (see `admit_fresh`).
        self._admission: Optional[_FreshAdmission] = None
        #: #10090 — events whose latest stamp read said live: admitted ones
        #: are stamped ahead of the rest (`_FreshAdmission.next_queued`).
        self._live_event_ids: set[int] = set()
        #: #10090 held-first stamps (STAMP_READER_FIRST_ENV): the event ids a
        #: reader holds open, installed by a consumer
        #: (`reader_presence.held_event_cache().event_ids`); None keeps the
        #: old order.
        self.reader_held: Optional[Callable[[], Container[int]]] = None
        self._held_debt_run = 0
        #: #10090 — the running call's same-event fence (`holding_event_ids`).
        #: None from a call's first turn until it opens its door.
        self._holding: Optional[set[int]] = None
        #: #10090 — resolved when the next call opens its door
        #: (`admission_opened`).
        self._admission_signal = None
        #: #10090 write-under-queued (STAMP_WRITE_UNDER_QUEUED) — events whose
        #: price rows a caller is writing now (`writing_begin`): no queued
        #: attempt of theirs starts until `writing_end`.
        self._writing: set[int] = set()
        #: Events a write returned for while their attempt was still queued:
        #: event id -> the `_mono` time of that return. Their next committed
        #: cohort rides the attempt (`admit_fresh`) rather than being refused.
        self._written_queued: dict[int, float] = {}
        #: Resolved at the next `writing_end`, for a worker that found every
        #: queued attempt under a lease.
        self._writing_signal = None
        #: #10090 — optional callback notified when held events release so a
        #: socket flush loop that fenced a newer quote on those events wakes.
        self.release_wake: Optional[Callable[[Iterable[int]], None]] = None
        #: #10090 — provisional preview (`app.utils.blend_preview`): the
        #: supported sources validate every arriving event. The scope is
        #: stateless: events arriving after startup need no enrollment.
        from app.utils.blend_preview import PreviewEventScope, preview_events_for

        self.preview_events: PreviewEventScope | frozenset = preview_events_for(self.source)
        self.preview = bool(self.preview_events)
        # Short-lived transaction helpers have no task lifecycle to drain.
        # This ownership argument does not change DNPL eligibility or reads.
        self._owns_preview_maintenance = owns_preview_maintenance
        self._preview_maintenance_task = None
        self._preview_maintenance_after = 0.0
        self._preview_maintenance_closed = False
        self.preview_stats: dict[str, int] = {
            "published": 0, "revoked": 0, "fenced": 0, "publish_errors": 0,
        }
        #: #10090 preview receipt — capacity passes by `end`, and the
        #: per-minute line itself (`app.utils.preview_receipt`). Log only.
        self._capacity_ends: dict[str, int] = {}
        self.preview_receipt = None
        if self.preview:
            from app.utils.preview_receipt import PreviewReceipt

            # Late-bound, so a rig that drives the module's clocks drives it.
            self.preview_receipt = PreviewReceipt(
                self.source, self._preview_receipt_counters,
                mono=lambda: _mono(), wall=lambda: _wall())
        #: #10090 — observation-preview reads still running after their caller
        #: stopped waiting (`OBSERVATION_READ_DETACHED_MAX`), and what became of
        #: them; reported on the read-unavailable line.
        self._detached_reads: set[asyncio.Task] = set()
        self.observation_read_stats: dict[str, int] = {
            "detached": 0, "finished": 0, "capped": 0, "ceiling_cancelled": 0,
        }
        #: #10090 `preview_from_commit` — each live preview event's last read
        #: graph: event id -> (`_mono` of the read, event, group). Replaced, never
        #: mutated: a committed row or stamp installs a patched copy.
        self._preview_graphs: dict[int, tuple] = {}
        #: Outcome id -> the cached event whose graph holds it.
        self._preview_graph_outcomes: dict[int, int] = {}
        #: Committed outcomes awaiting composition: event id -> {outcome id:
        #: the `last_updated` its write returned}. One worker drains it.
        self._commit_preview_due: dict[int, dict[int, Any]] = {}
        #: Outcome id -> (`_mono` noted, its committed `COMMIT_PATCH_FIELDS`),
        #: oldest note first, kept `PREVIEW_NOTE_RETENTION_S`.
        self._noted_commits: dict[int, tuple] = {}
        #: Outcome id -> `_mono` when this process last changed it outside a
        #: price write (`forget_preview_outcomes`), oldest first, kept as long.
        self._forgotten_outcomes: dict[int, float] = {}
        self._commit_preview_task: Optional[asyncio.Task] = None
        self.commit_preview_stats: dict[str, int] = {"proposed": 0, "errors": 0}
        #: #10090 `preview_at_receipt` — outcome id -> the newest received
        #: quote: (price as the row stores it, frozen DB-clock bound, input seq,
        #: event id, routing token, `_mono` noted). Oldest note first.
        self._receipt_quotes: dict[int, tuple] = {}
        #: Events with a quote not yet composed (insertion order); one worker.
        self._receipt_due: dict[int, None] = {}
        #: Events whose previewed legs a withdrawal or settlement took away.
        self._receipt_withdrawn: dict[int, None] = {}
        #: event id -> every leg of the markets its last receipt reading was
        #: derived from (empty: it had none). A tick on any other leg (a prop,
        #: a spread) is kept for the overlay but composes nothing. Dropped
        #: whenever the event's graph is replaced, so a change of speaking
        #: market is found by the next tick's composition.
        self._receipt_speaking: dict[int, frozenset] = {}
        #: event id -> (`_mono` of its last receipt composition, the ledger seq
        #: of the receipt proposal still pending or None, its whole-percent blend).
        self._receipt_last: dict[int, tuple] = {}
        self._receipt_task: Optional[asyncio.Task] = None
        self._receipt_wake: Optional[asyncio.Event] = None
        #: Installed by a consumer whose routing can change under it (the
        #: Polymarket catalog handover): the current routing token, or None
        #: while the maps are changing. None installed: one fixed routing.
        self.receipt_route: Optional[Callable[[], Any]] = None
        self.receipt_preview_stats: dict[str, int] = {
            "noted": 0, "proposed": 0, "unchanged": 0, "no_graph": 0, "old_graph": 0,
            "ambiguous": 0, "not_admitted": 0, "returned": 0, "withdrawn": 0, "errors": 0,
            # Skips before composition (counted only; same returns as before):
            "no_bound": 0, "routing": 0, "kept_no_graph": 0, "not_speaking": 0,
        }
        #: Wall seconds spent composing receipt previews (local CPU, no await).
        self.receipt_compose_s = 0.0
        #: Monotonic time of the last `receipt-preview stats` line (0: none yet).
        self._receipt_stats_logged_at = 0.0
        #: Per class, event id -> count since the last stats line (top ids logged).
        self._receipt_class_events: dict[str, dict[int, int]] = {}
        #: #10090 headline clock: event id -> (recv mono of its oldest headline
        #: input not yet on screen, how it is waiting). A headline input is a
        #: received leg of the event's kept graph on the market that speaks.
        self._hl_pending: dict[int, list] = {}
        self._hl_samples: list[tuple[float, int, str]] = []
        self._hl_late = 0
        self._hl_fallback: dict[str, int] = {}

    # ── throttling ───────────────────────────────────────────────────────────

    def _due(self, event_id: int, now: float) -> bool:
        hold = self._failed_hold_until.get(event_id)
        if hold is not None:
            if now < hold:
                return False
            del self._failed_hold_until[event_id]
        return self._floor_passed(event_id, now, self._current_clock(now))

    def _floor_passed(self, event_id: int, now: float, current: float) -> bool:
        last = self._last_refresh_at.get(event_id)
        if last is None:
            return True
        floor = self.min_refresh_interval_s - FLUSH_CLOCK_SLACK_S
        if now - last >= floor:  # the caller's clock on both sides, as before
            return True
        # #10090 (Argon flush-loop Rank 2): or a floor after the stamp on the
        # current clock, on both sides. A Kalshi main flush hands its own start
        # to every admission for its whole 3-7 s, so an event a LATER clock had
        # stamped (a write beside it, a later flush's cohort) read as under the
        # floor all that time and waited for the next flush. Never the current
        # clock against `last` alone (lane1's R1 on 0b2a452d): a stamp taken on
        # that flush's start is recorded at the start, and every admission past
        # start + floor would stamp it again inside the floor.
        stamped = self._last_refresh_current.get(event_id, last)
        return current - max(stamped, last) >= floor

    def _due_unchanged(self, event_id: int, now: float) -> bool:
        """`_due`, changing nothing: no expired hold is dropped and no clock
        is recorded (`stamp_wait_reason` only)."""
        hold = self._failed_hold_until.get(event_id)
        if hold is not None and now < hold:
            return False
        high = self._clock_high
        current = now
        if high is not None and now <= high[0]:
            current = max(now, high[0] + max(0.0, _mono() - high[1]))
        return self._floor_passed(event_id, now, current)

    def _reader_held_ids(self) -> Container[int]:
        """#10090 held-first: the held event ids, or empty (the old order)
        with the switch off, no source installed, or a failing one."""
        source = self.reader_held
        if source is None or not stamp_reader_first_on():
            return frozenset()
        try:
            return source()
        except Exception:  # noqa: BLE001 — ordering never fails a stamp
            return frozenset()

    # ── #10090 `stamp_wait_reason`: why a live game's input still waits ──────

    def _stamp_wait_reason(self, event_id: int, now: float, *, excluded=(),
                           due_reason: str) -> str:
        """The reason an owed LIVE event is not being stamped right now, from
        state already held; ``due_reason`` is the caller's for one that is
        owed, due and still not taken."""
        window = self._admission
        if window is not None and event_id in window.holding:
            return "QUEUED_OR_RUNNING"
        if event_id in excluded:
            return "COHORT_UNFINISHED_OR_WITHDRAWAL"
        hold = self._failed_hold_until.get(event_id)
        if hold is not None and now < hold:
            return "RETRY_HOLD"
        if event_id in self._book_refused:
            return "NO_VALID_READING"
        if event_id not in self._lock_retry and event_id not in self._throttle_deferred:
            # Nothing owed here: not committed yet (the writer's side), or a
            # stamp that reread the board carried it without crediting it.
            return "NOT_OWED"
        if not self._due_unchanged(event_id, now):
            return "NOT_DUE"
        return due_reason

    def _stamp_wait_sweep(self, site: str, now: float, *, taken=(), excluded=(),
                          due_reason: str) -> None:
        """Debt selection: one reason per live event whose oldest unstamped
        input is past STAMP_WAIT_BUDGET_S; ``taken`` are ADMITTED. Never raises."""
        receipts = getattr(self, "receipts", None)
        waits = getattr(self, "stamp_waits", None)
        if receipts is None or waits is None or not stamp_wait_reason_on():
            return
        try:
            mono = _mono()
            aged = receipts.aged_obligations(_wall(), STAMP_WAIT_BUDGET_S)
            for event_id, obligation in aged.items():
                reason = "ADMITTED" if event_id in taken else self._stamp_wait_reason(
                    event_id, now, excluded=excluded, due_reason=due_reason,
                )
                self._stamp_wait_noted(waits, event_id, reason, obligation, mono, site)
            waits.retain(aged, mono)
        except Exception:
            self._stamp_wait_failed(waits)

    def _stamp_wait_read(self, event_ids, dispositions: dict) -> None:
        """After an attempted read: what the read did with each aged live
        event (`STAMP_WAIT_DISPOSITIONS`). Never raises."""
        receipts = getattr(self, "receipts", None)
        waits = getattr(self, "stamp_waits", None)
        if receipts is None or waits is None or not stamp_wait_reason_on():
            return
        try:
            mono = _mono()
            aged = receipts.aged_obligations(_wall(), STAMP_WAIT_BUDGET_S, event_ids)
            for event_id, obligation in aged.items():
                disposition = dispositions.get(event_id) or ("no_market",)
                reason = STAMP_WAIT_DISPOSITIONS.get(disposition[0], "READ_ERROR")
                if reason == "STAMPED":
                    # A committed stamp is not necessarily input coverage.
                    continue
                self._stamp_wait_noted(waits, event_id, reason, obligation, mono, "read")
        except Exception:
            self._stamp_wait_failed(waits)

    def _resolve_receipt_wait(self, receipts, due, *args):
        """Resolve receipts as before; close a wait only when its input leaves.

        A queued fresh reread carries no staged-input proof; an ordinary stamp
        can precede a newer uncommitted input too. Neither ends that input's wait.
        """
        waits = getattr(self, "stamp_waits", None)
        aged = {}
        if waits is not None and stamp_wait_reason_on():
            try:
                aged = receipts.aged_obligations(_wall(), STAMP_WAIT_BUDGET_S, due)
            except Exception:
                self._stamp_wait_failed(waits)
        self._receipt_call(receipts.resolve, due, *args)
        if not aged:
            return
        try:
            dispositions = args[0]
            mono = _mono()
            for event_id, obligation in aged.items():
                if dispositions.get(event_id, ("",))[0] != "stamped":
                    continue
                disposition = dispositions[event_id]
                pending = receipts._uncovered.get(event_id)
                committed = obligation[3]
                input_proof = len(disposition) <= 6 or disposition[6] is not False
                covered = (input_proof and committed is not None
                           and committed[0] >= obligation[0]
                           and (not pending or pending[0][0] > obligation[0]))
                closed = len(disposition) > 5 and disposition[5] not in (None, "live")
                reason = ("STAMPED" if covered else
                          "CATALOG_CLOSED" if closed else "READ_UNCOVERED")
                self._stamp_wait_noted(waits, event_id, reason, obligation, mono, "read")
        except Exception:
            self._stamp_wait_failed(waits)

    def _stamp_wait_noted(self, waits, event_id, reason, obligation, mono, site) -> None:
        spans = getattr(self, "stamp_spans", None)
        if spans is not None:
            spans.wait_reasons.setdefault(reason, set()).add(event_id)
        waits.note(event_id, reason, obligation, mono,
                   run=getattr(self.receipts, "run", "-"), site=site,
                   held_tag=_reader_held_tag(self.reader_held, event_id))

    def _stamp_wait_failed(self, waits) -> None:
        waits.errors += 1
        if waits.errors == 1 or waits.errors % 1000 == 0:
            with contextlib.suppress(Exception):
                logger.warning(
                    "live_blend_refresh[%s]: stamp_wait_reason failed (%d)",
                    self.source, waits.errors, exc_info=True,
                )

    def _record_stamp_clock(self, event_ids: Iterable[int], now: float) -> None:
        """#10090 — the current clock as these events' stamp starts (`_due`'s
        second rule), never back in time. Every `_refresh_batch` caller calls
        it first, beside the caller's clock that `_refresh_batch` records."""
        current = self._current_clock(now)
        for event_id in event_ids:
            stamped = self._last_refresh_current.get(event_id)
            if event_id not in self._last_refresh_at or stamped is None:
                self._last_refresh_current[event_id] = current
            else:
                self._last_refresh_current[event_id] = max(stamped, current)

    def _current_clock(self, now: float) -> float:
        """#10090 — the newest clock any caller has handed this refresher,
        advanced by the time since. Every caller's clock is a `_mono` reading,
        so it never runs ahead of real time."""
        mono = _mono()
        high = self._clock_high
        if high is None or now > high[0]:  # a repeated clock is not newer
            self._clock_high = high = (now, mono)
        return max(now, high[0] + max(0.0, mono - high[1]))

    # ── inversion orientation, cached ────────────────────────────────────────

    async def _oriented(
        self, session, event_id: int, home_prob: float, *, reading=None,
        before_fallback: Optional[Callable[[], Awaitable[None]]] = None,
        fallback_scope: Optional[Callable[[], Any]] = None,
    ) -> float:
        """Apply the inversion verdict, computing it at most once per TTL.

        Returns the home probability the poll would have written. The verdict is
        cached as a BOOLEAN (did this linkage need flipping), not as a value —
        caching the value would pin a price, which is the opposite of the point.
        """
        from app.utils.live_blend import has_proven_home_orientation

        if reading is not None and has_proven_home_orientation(reading):
            # #8814: a stale book can disagree with a correctly named soccer
            # quote. Its cached binary flip would also erase the real draw.
            # Discard that contradicted verdict, including for later ticks
            # whose partial board no longer proves the named home orientation.
            self._inversion.pop(event_id, None)
            return reading.home_probability

        now = time.monotonic()
        cached = self._inversion.get(event_id)
        if cached is not None and now < cached[0]:
            return 1.0 - home_prob if cached[1] else home_prob

        from app.tasks.prediction_market_matching import _check_and_fix_inversion

        if before_fallback is not None:
            # Preserve the existing bound on the cold Event/OddsSnapshot reads.
            await before_fallback()
        if fallback_scope is None:
            corrected = await _check_and_fix_inversion(
                session, event_id, home_prob, self.source,
            )
        else:
            # #10090: siblings share the transaction, so a failed cold read
            # rolls back only its own savepoint, never their stamps.
            async with fallback_scope():
                corrected = await _check_and_fix_inversion(
                    session, event_id, home_prob, self.source,
                )
        flipped = not math.isclose(corrected, home_prob, rel_tol=0.0, abs_tol=1e-9)
        self._inversion[event_id] = (now + self.inversion_ttl_s, flipped)
        return corrected

    # ── the refresh itself ───────────────────────────────────────────────────

    async def refresh(
        self, event_ids: Iterable[int], *, flush_started: Optional[float] = None,
        defer_event_ids: Iterable[int] = (),
        withdrawing_event_ids: Iterable[int] = (),
    ) -> dict[str, int]:
        """Recompute and stamp the blend for these events. Never raises.

        #10090 ``withdrawing_event_ids``: those of ``defer_event_ids`` deferred
        only by a buffered withdrawal the caller has not started writing. With
        `owed_past_withdrawal` on, a throttle-deferred one is not excluded
        (`_past_withdrawal`), and with `lock_retry_past_withdrawal` on, a lock
        retry is not; fresh events still are.

        #10090 — ``flush_started`` is the socket flush's start on `_mono`
        (`run_flush_cadence`). When given, the per-event floor, the failed-retry
        hold and the batch's own interval bookkeeping read THAT clock rather
        than the moment this call happens to run. Flush starts are a period
        apart; refresh calls are not — they trail their flush's write by
        whatever it cost, so a slow write followed by a fast one put two
        refreshes under the floor and the second flush's committed price waited
        a whole extra flush for its stamp. Receipts keep the real clock: they
        time the hold, not the schedule. Omitted, behaviour is unchanged.
        """
        self._start_history()
        self._holding = None
        now = _mono()
        clock = now if flush_started is None else flush_started
        receipts = self.receipts
        staged, stored_wall = (
            self._receipt_call(receipts.take_staged) if receipts is not None else None
        ) or ({}, None)
        if self.preview_receipt is not None:
            self._receipt_call(self.preview_receipt.roll)
        self._wake_book_refused(now)
        retry = set(self._lock_retry)
        deferred = set(self._throttle_deferred)
        fresh = set(event_ids)
        wanted = fresh | retry | deferred
        if self._lock_prompt_at or self._lock_prompt_taken:
            # No stamp is in flight between calls: one no longer owed as a
            # lock retry was stamped or released, so its run of skips is over.
            for owed in (self._lock_prompt_at, self._lock_prompt_taken):
                for eid in [eid for eid in owed if eid not in retry]:
                    del owed[eid]
        # A caller may still be writing this event's price/withdrawal cohort.
        # Leave its fresh inputs and existing debt owed without reading a
        # partial board; ordinary callers retain the same admission behavior.
        excluded = set(defer_event_ids)
        excluded.difference_update(
            self._past_withdrawal(withdrawing_event_ids, fresh, retry, deferred)
        )
        due = [eid for eid in wanted if eid not in excluded and self._due(eid, clock)]
        handed_over = frozenset()
        if self._carried_fresh:
            # #10090 `handover_fresh`: a committed cohort a hand-over carried
            # over is this call's fresh, not old debt. One not due yet stays
            # carried; one no longer owed was stamped by another path.
            self._carried_fresh.intersection_update(wanted)
            carried = self._carried_fresh.intersection(due)
            self._carried_fresh.difference_update(carried)
            fresh |= carried
            handed_over = frozenset(carried)
        self._pending_continuation = [
            eid for eid in self._pending_continuation if eid in wanted
        ]
        if flush_started != self._pending_flush_started:
            self._pending_flush_started = flush_started
            self._pending_attempts_limit = _fresh_flush_pending_attempts()
            self._pending_started_at = None
            self._pending_attempted = False
            self._pending_attempts = 0
            self._pending_fresh_flush = (
                flush_started is not None
                and flush_started == self._admitted_fresh_flush
            )
        if flush_started is not None and fresh:
            # Sticky for the flush: old attempts made before its first fresh
            # call count against the same allowance, so none is added after.
            self._pending_fresh_flush = True
        if self._lock_prompt_at:
            # #10090 `lock_retry_prompt`: a row-lock skip whose prompt attempt
            # is due is this call's fresh, not debt behind the allowance. It
            # does not make the flush fresh-bearing: a quiet flush keeps its
            # time budget for the rest of the debt.
            fresh |= self._take_lock_prompts(retry.intersection(due), now)

        def pending_budget_spent():
            if flush_started is None:
                return False
            if (
                self._pending_fresh_flush
                and self._pending_attempts >= self._pending_attempts_limit
            ):
                return True
            return (
                self._pending_attempted
                and self._pending_started_at is not None
                and _mono() - self._pending_started_at >= PENDING_STAMP_BUDGET_S
            )

        # A flush can call refresh more than once. Once its old-work budget is
        # spent, leave all remaining debt owed without repeating its read. Fresh
        # committed prices are always admitted, even within that same flush.
        if pending_budget_spent():
            due = [eid for eid in due if eid in fresh]
        # A queued retry leaves the set only when a batch actually takes it.
        self._lock_retry = retry.difference(due)
        # A throttled event is owed the price it just had written, so it waits
        # for its throttle rather than for its next tick.
        self._throttle_deferred = wanted.difference(due)
        # A parked pair this batch reads is no longer parked; a refusal in
        # this read parks it again with the inputs it was refused on.
        for event_id in due:
            self._book_refused.pop(event_id, None)
        # Owed, due and not excluded, yet not taken: only the debt budget.
        self._stamp_wait_sweep(
            "refresh", clock, taken=due, excluded=excluded,
            due_reason="DEBT_BUDGET_SPENT",
        )
        self.stats["considered"] += len(due)
        # Counted once per throttled price, not once per flush it waits out.
        skipped = len(self._throttle_deferred.difference(deferred))
        if skipped > 0:
            self.stats["throttled"] += skipped
        if receipts is not None:
            self._observe_committed(receipts, staged, stored_wall, set(due), now)
        if self._stage_hook("stage_admission") is not None:
            self._stage_trace(
                "stage_admission", "REFRESH", None, wanted,
                due=due, excluded=excluded, fresh=fresh, flush_started=flush_started,
            )
        if not due:
            if self.release_wake is not None and wanted:
                self.release_wake(wanted)
            return self.stats

        self._dispositions = {}
        completed: set[int] = set()
        failed_groups: set[int] = set()
        budget_deferred: set[int] = set()
        publishing = None
        waiting_frames = []
        reread_events: set[int] = set()
        import asyncio

        publication_lock = asyncio.Lock()

        async def publication_done(*, cancel=False, cancel_on_interrupt=True):
            nonlocal publishing
            if publishing is None:
                return
            import asyncio

            if cancel and not publishing.cancelling():
                publishing.cancel()
            interrupted = None
            while not publishing.done():
                try:
                    await asyncio.wait({publishing})
                except CancelledError as exc:
                    interrupted = exc
                    if cancel_on_interrupt and not publishing.cancelling():
                        publishing.cancel()
            task, publishing = publishing, None
            if interrupted is not None:
                # Retrieve even an unexpected failure before propagating the
                # interruption; no publication task may outlive this refresh.
                if not task.cancelled():
                    task.exception()
                raise interrupted
            if task.cancelled():
                if not cancel:
                    raise CancelledError
            else:
                try:
                    task.result()
                except Exception:
                    self.stats["errors"] += 1
                    logger.exception(
                        "live_blend_refresh[%s]: publication task failed", self.source,
                    )

        async def publish_committed(frames):
            nonlocal publishing

            if not frames:
                return
            # Record definitely-unsent frames before waiting for ownership.
            # Concurrent stamps may commit, but only one sender owns the socket.
            waiting_frames.append(frames)
            async with publication_lock:
                await publication_done()
                waiting_frames.remove(frames)
                # No cancellation point between removing and submitting frames.
                publishing = self._publish_prices_task(frames)

        async def publish_inline(frames):
            # The singleton still sends its own frames before its stamp
            # returns. The lock only orders them with an admitted cohort's.
            async with publication_lock:
                await publication_done()
                await self._publish_prices(frames)

        def committed(group_ids):
            # Called synchronously AFTER COMMIT and cache installation, BEFORE
            # the first publication await. Interrupted delivery does not undo
            # a stored stamp or promise replay; _publish keeps its own contract.
            completed.update(group_ids)
            for event_id in group_ids:
                disposition = self._dispositions.get(event_id, ())
                if event_id in reread_events and disposition[:1] == ("stamped",):
                    self._dispositions[event_id] = disposition[:6] + (False,)
            if receipts is not None:
                self._resolve_receipt_wait(
                    receipts,
                    group_ids,
                    self._dispositions,
                    staged,
                    stored_wall,
                    _mono(),
                )

        # #10090 — while this call runs, a cohort its caller commits later
        # joins it on a free stamp worker (`admit_fresh`) rather than waiting
        # for every stamp below to return. Its frames go through this call's
        # one sender; its sessions share this call's FRESH_STAMP_WORKERS slots.
        window = _FreshAdmission(flush_started, clock, due, release_wake=self.release_wake)
        window.publish = publish_committed
        window.publish_inline = publish_inline
        # #10090 write-under-queued: a right granted under the previous call's
        # window names an attempt that is gone; this call's events are staged
        # by this call.
        self._written_queued.clear()
        if self._stage_hook("attempt_released") is not None:
            window.on_release = lambda ids: self._stage_trace("attempt_released", ids)
        self._admission = window
        self._holding = window.holding
        not_due = wanted.difference(due)
        if not_due and self.release_wake is not None:
            self.release_wake(not_due)
        signal, self._admission_signal = self._admission_signal, None
        if signal is not None and not signal.done():
            signal.set_result(None)
        interrupted = False
        # #10090 R8b: the old population's live-first read, started beside the
        # fresh stamps when `release_unattempted_debt` is on (see below).
        early_read = None
        try:
            # One event already owns its transaction. For multiple admitted events,
            # prepare once and commit each independently so a later row lock cannot
            # hold an earlier stamp or its publication until the batch ends.
            if len(due) == 1:
                pending_only = due[0] not in fresh
                if pending_only and flush_started is not None:
                    if self._pending_started_at is None:
                        self._pending_started_at = _mono()
                    self._pending_attempted = True
                    self._pending_attempts += 1
                self._pending_continuation = [
                    eid for eid in self._pending_continuation if eid not in due
                ]
                try:
                    self._record_stamp_clock(due, clock)
                    await self._refresh_batch(due, clock)
                except CancelledError as exc:
                    # #10090 review: a recycle can cancel this stamp after its
                    # prices committed and left the buffer, so no later input
                    # re-asks for it. Keep it owed for the hand-off exactly as the
                    # grouped arm below does, with the retry/deferred work it took.
                    # A cancel that lands after COMMIT (while publishing) costs one
                    # redundant re-stamp, never a lost one.
                    self._refresh_failed(
                        due,
                        retry,
                        clock,
                        receipts,
                        staged,
                        stored_wall,
                        exc,
                        hold=False,
                    )
                    failed_groups.update(due)
                    raise
                except Exception as exc:
                    self.stats["errors"] += 1
                    logger.exception("live_blend_refresh[%s]: batch failed", self.source)
                    if pending_only:
                        self._trial_attempt_failed(flush_started, exc)
                    self._refresh_failed(
                        due,
                        retry,
                        clock,
                        receipts,
                        staged,
                        stored_wall,
                        exc,
                    )
                    failed_groups.update(due)
                else:
                    completed.update(due)
                    if receipts is not None:
                        self._resolve_receipt_wait(
                            receipts,
                            due,
                            self._dispositions,
                            staged,
                            stored_wall,
                            _mono(),
                        )
                finally:
                    window.release(due)

            # Read/stamp fresh prices before reading older debt. Each nonempty
            # population prepares one view for order and the initial worker
            # claims. Queued fresh stamps reread below; old debt and the
            # singleton path above keep their existing read behavior.
            populations = () if len(due) == 1 else (
                fresh.intersection(due), set(due).difference(fresh),
            )
            if (
                populations
                and len(populations[1]) > 1
                and flush_started is not None
                and self._pending_fresh_flush
                and _release_unattempted_debt()
            ):
                # #10090 R8b (`release_unattempted_debt`): the old events this
                # call will not attempt leave its fence as soon as it knows
                # which those are, so they become ordinary debt the door can
                # take, and their newer prices can be written, while the fresh
                # stamps run — not after them (15330559 held 21.7-30.4 s). The
                # attempted ones, and the order, are exactly today's.
                fresh_population, old = populations
                carried = [eid for eid in self._pending_continuation if eid in old]
                left = self._pending_attempts_limit - self._pending_attempts

                def release_unattempted(remainder, front):
                    budget_deferred.update(remainder)
                    self._lock_retry.update(remainder.intersection(retry))
                    self._throttle_deferred.update(remainder.difference(retry))
                    # The continuation the budget cut below would have left.
                    self._pending_continuation = front + [
                        eid for eid in self._pending_continuation if eid not in old
                    ]
                    window.release(remainder)

                if left == 1 and carried:
                    # The continuation head is the one attempt: no read decides it.
                    release_unattempted(old.difference(carried[:1]), carried)
                    populations = (fresh_population, set(carried[:1]))
                elif (
                    0 < left < len(old)
                    # A session slot free beyond the fresh stamps' own: the
                    # slots are shared with the history/recovery/preview owners.
                    and self._session_slots._value > len(fresh_population)
                ):
                    # The live-first read decides: run it beside the fresh
                    # stamps (they leave a stamp worker free, so none waits for
                    # its session) and release the rest when it returns.
                    async def read_old_population():
                        prepared = await self._prepare_groups(list(old))

                        def live_first(event_id: int) -> tuple[bool, int]:
                            context = prepared.get(event_id)
                            return (context is None or context[0].status != "live", event_id)

                        queued = set(carried)
                        ordered = carried + sorted(
                            (eid for eid in old if eid not in queued), key=live_first,
                        )
                        attempt = ordered[:left]
                        # The whole order: a call cancelled before its attempts
                        # leaves them ahead of the events it released.
                        release_unattempted(set(ordered[left:]), ordered)
                        return set(attempt), prepared

                    early_read = asyncio.create_task(read_old_population())
            for population in populations:
                if not population:
                    continue
                early_prepared = early_failure = None
                if early_read is not None and population.isdisjoint(fresh):
                    read, early_read = early_read, None
                    try:
                        population, early_prepared = await read
                    except Exception as exc:  # handled as a failed preparation below
                        early_failure = exc
                        with contextlib.suppress(Exception):
                            _optional_db_trial().trip(RELEASE_UNATTEMPTED_DEBT_SWITCH, exc)
                pending_only = population.isdisjoint(fresh)
                if pending_only and pending_budget_spent():
                    # A repeated mixed call may have consumed the remaining
                    # budget on its fresh work since the admission check above.
                    # Do not read old debt when no old stamp can be attempted.
                    budget_deferred.update(population)
                    self._lock_retry.update(population.intersection(retry))
                    self._throttle_deferred.update(population.difference(retry))
                    window.release(population)
                    continue
                if pending_only and flush_started is not None:
                    if self._pending_started_at is None:
                        self._pending_started_at = _mono()
                # A fresh-bearing flush with one old attempt left and a due
                # continuation head attempts exactly that head, which the
                # shared read below could not reorder. It reads its own group,
                # as a singleton does, instead of first reading every old
                # event. The rest stay owed in their continuation order; debt
                # without one gets its live-first order from a later read. A
                # single old event without a head has no order to decide
                # either, so it reads its own group the same way.
                carried = [
                    eid for eid in self._pending_continuation if eid in population
                ]
                head = None
                if (
                    pending_only
                    and flush_started is not None
                    and self._pending_fresh_flush
                    and self._pending_attempts_limit - self._pending_attempts == 1
                ):
                    if carried:
                        head = carried[0]
                    elif len(population) == 1:
                        (head,) = population
                head_only = head is not None
                # A fresh population that fits the fixed workers has no claim
                # order to decide: every event starts at once. Each stamp reads
                # its own group in its own write session, as a singleton does,
                # rather than every stamp first waiting on a separate session's
                # read of all of them. A read failure stays with its own event.
                prepared = None
                own_read = None
                try:
                    if early_failure is not None:
                        raise early_failure
                    if early_prepared is not None:
                        # Order only: it was read before the fresh stamps, so
                        # each attempt below reads its own group again.
                        if not head_only:
                            prepared = early_prepared
                    elif not head_only and (
                        pending_only or len(population) > FRESH_STAMP_WORKERS
                    ):
                        if pending_only or population.isdisjoint(handed_over):
                            prepared = await self._prepare_groups(list(population))
                        else:
                            # #10090 `handover_fresh`: carried hand-over events
                            # (a shed of ~115-244) take their live flag from the
                            # set the door routes by, not from a shared read of
                            # every event. That read is order only (each queued
                            # stamp rereads its own group) and `_read_groups`
                            # builds all its rows in one synchronous pass: ~14k
                            # rows, ~1-1.7 s of venue loop CPU at production's
                            # ~5-7 ms per event read. This call's own events are
                            # read as before; no stamp is handed this read.
                            own = population.difference(handed_over)
                            own_read = await self._prepare_groups(list(own)) if own else {}
                except Exception as exc:
                    self.stats["errors"] += 1
                    logger.exception(
                        "live_blend_refresh[%s]: preparation failed for %s",
                        self.source, population,
                    )
                    self._refresh_failed(
                        population, retry, clock, receipts, staged, stored_wall, exc,
                    )
                    failed_groups.update(population)
                    window.release(population)
                    continue

                # Preserve live-first order within each population and numeric
                # tie-breaking; missing prepared rows remain due as non-live.
                # #10090 held-first: within each, events a reader holds first.
                held = (
                    self._reader_held_ids()
                    if prepared is not None or own_read is not None else frozenset()
                )

                def stamp_order(event_id: int) -> tuple[bool, bool, int]:
                    if own_read is not None:
                        if event_id in handed_over:
                            live = event_id in self._live_event_ids
                        else:
                            context = own_read.get(event_id)
                            live = context is not None and context[0].status == "live"
                        return (not live, event_id not in held, event_id)
                    if prepared is None:
                        return (False, False, event_id)
                    context = prepared.get(event_id)
                    return (
                        context is None or context[0].status != "live",
                        event_id not in held,
                        event_id,
                    )

                ordered = sorted(population, key=stamp_order)
                if pending_only:
                    # Finish last flush's unattempted debt before beginning a
                    # new live-first debt cycle. Fresh remains ahead of both;
                    # repeated locked live IDs cannot starve quieter old debt.
                    queued = set(carried)
                    ordered = carried + [eid for eid in ordered if eid not in queued]

                async def stamp_event(event_id, *, read_current=False):
                    self._pending_continuation = [
                        eid for eid in self._pending_continuation if eid != event_id
                    ]
                    if pending_only and flush_started is not None:
                        self._pending_attempted = True
                        self._pending_attempts += 1
                    group_ids = [event_id]
                    if read_current:
                        reread_events.add(event_id)
                    try:
                        self._record_stamp_clock(group_ids, clock)
                        await self._refresh_batch(
                            group_ids,
                            clock,
                            # None (no shared read): this session reads it.
                            prepared=None if read_current else prepared,
                            on_committed=committed,
                            publish_committed=publish_committed,
                        )
                    except Exception as exc:
                        self.stats["errors"] += 1
                        logger.exception(
                            "live_blend_refresh[%s]: group failed for %s",
                            self.source,
                            group_ids,
                        )
                        if pending_only:
                            self._trial_attempt_failed(flush_started, exc)
                        if not completed.issuperset(group_ids):
                            self._refresh_failed(
                                group_ids,
                                retry,
                                clock,
                                receipts,
                                staged,
                                stored_wall,
                                exc,
                            )
                            failed_groups.update(group_ids)
                    else:
                        # Empty/no-market groups also finished successfully.
                        if not completed.issuperset(group_ids):
                            committed(group_ids)
                    finally:
                        window.release(group_ids)

                if head_only:
                    await stamp_event(head)
                    remaining = population.difference({head})
                    budget_deferred.update(remaining)
                    self._lock_retry.update(remaining.intersection(retry))
                    self._throttle_deferred.update(remaining.difference(retry))
                    window.release(remaining)
                    self._pending_continuation = carried[1:] + [
                        eid for eid in self._pending_continuation
                        if eid not in population
                    ]
                elif not pending_only:
                    # FRESH_STAMP_WORKERS fixed workers claim fresh IDs in
                    # order; waiting stamps cannot hold every fresh sibling
                    # behind their row locks. No population-sized fanout.
                    event_ids = iter(ordered)

                    async def fresh_worker(initial_event_id):
                        await stamp_event(initial_event_id)
                        for event_id in event_ids:
                            # Another stamp/publication may have waited since
                            # preparation. Read current quotes and their actual
                            # observation clocks in this event's write session.
                            # Cost: one joined read per queued fresh event.
                            await stamp_event(event_id, read_current=True)

                    # Claim every initial ID before scheduling any worker:
                    # even a worker completing without yielding cannot consume
                    # a sibling's initial prepared slot. No population fanout.
                    initial_events = [
                        next(event_ids)
                        for _ in range(min(FRESH_STAMP_WORKERS, len(ordered)))
                    ]
                    workers = {
                        asyncio.create_task(fresh_worker(event_id))
                        for event_id in initial_events
                    }
                    try:
                        active = workers.copy()
                        while active:
                            done, active = await asyncio.wait(
                                active, return_when=asyncio.FIRST_COMPLETED,
                            )
                            for task in done:
                                task.result()
                    except BaseException:
                        # Join stamp cleanup before computing cancellation debt.
                        # Repeated consumer cancellation cannot abandon a session
                        # or a worker that owns publication cleanup.
                        for task in workers:
                            if not task.done() and not task.cancelling():
                                task.cancel()
                        active = {task for task in workers if not task.done()}
                        while active:
                            try:
                                _, active = await asyncio.wait(active)
                            except CancelledError:
                                continue
                        for task in workers:
                            if not task.cancelled():
                                task.exception()
                        raise
                else:
                    for index, event_id in enumerate(ordered):
                        if pending_budget_spent():
                            remaining = set(ordered[index:])
                            budget_deferred.update(remaining)
                            self._lock_retry.update(remaining.intersection(retry))
                            self._throttle_deferred.update(remaining.difference(retry))
                            window.release(remaining)
                            self._pending_continuation = ordered[index:] + [
                                eid for eid in self._pending_continuation
                                if eid not in population
                            ]
                            break
                        await stamp_event(event_id, read_current=early_prepared is not None)
            # Admitted cohorts finish inside this call; the door closes with
            # no turn between its last worker ending and the close (or when a
            # lifecycle drain stops admitting), so the remaining drain is
            # bounded by what was queued before it.
            window.own_done = True
            await self._admission_join(window)
            await publication_done()
        except CancelledError as exc:
            interrupted = True
            remaining = set(due).difference(completed, failed_groups, budget_deferred)
            if remaining:
                self._refresh_failed(
                    remaining,
                    retry,
                    clock,
                    receipts,
                    staged,
                    stored_wall,
                    exc,
                    hold=False,
                )
            raise
        except Exception as exc:
            # Setup can fail between populations after earlier stamps committed.
            # Only unfinished work remains owed, including immediately due locks.
            self.stats["errors"] += 1
            logger.exception("live_blend_refresh[%s]: preparation failed", self.source)
            self._refresh_failed(
                set(due).difference(completed, failed_groups, budget_deferred),
                retry,
                clock,
                receipts,
                staged,
                stored_wall,
                exc,
            )
        finally:
            # Cancellation or any pre-commit failure must not leave a sender
            # running beside the consumer's final drain or next refresh. An
            # admitted stamp ends first: it may still submit a frame.
            try:
                if early_read is not None:
                    # Never awaited: the call failed or was cancelled first. Its
                    # old population stays owed (above); no read outlives it.
                    early_read.cancel()
                    while not early_read.done():
                        try:
                            await asyncio.wait({early_read})
                        except CancelledError:
                            continue
                    if not early_read.cancelled():
                        early_read.exception()
                await self._admission_close(window, cancel=interrupted)
            finally:
                try:
                    await publication_done(cancel=True)
                finally:
                    if waiting_frames:
                        import asyncio

                        # These committed frames were NEVER submitted. Finish one
                        # bounded send before exit; do not retry the predecessor's
                        # uncertain send or interrupt this cleanup on a second
                        # consumer cancellation. _publish retains its 5s bound.
                        frames = [frame for group in waiting_frames for frame in group]
                        waiting_frames.clear()
                        publishing = self._publish_prices_task(frames)
                        await publication_done(cancel_on_interrupt=False)
        return self.stats

    def _refresh_failed(
        self,
        due,
        retry,
        clock,
        receipts,
        staged,
        stored_wall,
        exc,
        *,
        hold=True,
    ) -> None:
        # The outcome prices already committed before this refresh. Keep
        # every owed stamp if its transaction fails, even when no further
        # venue input arrives. Ordinary retries wait out the failed-retry
        # hold; only existing row-lock retries remain due at once.
        failed = set(due).difference(self._lock_retry, retry)
        self._throttle_deferred.update(set(due).difference(self._lock_retry))
        for event_id in failed if hold else ():
            self._failed_hold_until[event_id] = clock + self.failed_retry_interval_s
        for event_id in retry.intersection(due):
            self._lock_retry.add(event_id)
            self._last_refresh_at.pop(event_id, None)
            self._throttle_deferred.discard(event_id)
        if receipts is not None:
            self._receipt_call(
                receipts.resolve_failed,
                due,
                self._dispositions,
                staged,
                stored_wall,
                self._lock_retry | self._throttle_deferred,
                exc,
                _mono(),
            )

    def _stage_hook(self, name):
        """#10090: an optional stage-trace hook, None when no trace has it."""
        return getattr(getattr(self.receipts, "exact_trace", None), name, None)

    def _stage_trace(self, name, *args, **kwargs):
        """#10090: call an optional stage-trace hook. Synchronous, never raises."""
        hook = self._stage_hook(name)
        if hook is not None:
            with contextlib.suppress(Exception):
                hook(*args, **kwargs)

    def _trace_selection(self, selections, event_id, token, disposition, *, route,
                         reading=None, value=None, contributing=None, basis=None,
                         reason=None, then="NONE"):
        """#10090: SELECTED for a traced event's decision. Never raises.

        A PROPOSE decision's ``sel`` is kept in ``selections`` so its proposal
        carries it (`_trace_proposal`).
        """
        hook = self._stage_hook("selection")
        if hook is None:
            return
        try:
            if basis is None and contributing is not None:
                from app.utils.aggregation import observation_basis

                basis = observation_basis(contributing)
            sel = hook(token, self.source, disposition, route=route, reading=reading,
                       value=value, basis=basis, reason=reason, then=then)
            if sel is not None and selections is not None:
                selections[event_id] = sel
        except Exception:
            pass

    def _selections_closer(self, selections):
        """#10090: close ``selections`` on exit; a no-op context without a trace."""
        if selections is None:
            return contextlib.nullcontext()

        @contextlib.asynccontextmanager
        async def closer():
            try:
                yield
            finally:
                if selections:
                    self._stage_trace("selections_closed", list(selections.values()))

        return closer()

    def _trace_proposal(self, sel, ops, event_id, ledger) -> None:
        """#10090: a traced selection rides its proposal into the ledger call.

        The op gains ``_trace`` (never sent: `_mutate` builds its argv from
        named keys). No proposal op means the selection ends here, named.
        """
        hook, clock = self._stage_hook("readset"), self._stage_hook("clock")
        if hook is None or clock is None:
            return
        try:
            for op in ops:
                if (isinstance(op, dict) and op.get("ledger_op") == "propose"
                        and op.get("event_id") == event_id and op.get("source") == self.source):
                    op["_trace"] = (sel, clock, hook)
                    return
            self._stage_trace(
                "selection_unsent", sel, "NOT_PROPOSED" if ledger else "NOT_LEDGER",
                [op.get("ledger_op") or "frame" for op in ops if isinstance(op, dict)],
            )
        except Exception:
            pass

    def _receipt_call(self, fn, *args):
        """Receipts are evidence about the price path, never part of it."""
        try:
            return fn(*args)
        except Exception:
            logger.warning(
                "live_blend_refresh[%s]: tail receipt failed",
                self.source,
                exc_info=True,
            )
            return None

    def _observe_committed(self, receipts, staged, stored_wall, due, now) -> None:
        """`TailReceipts.observe`, and the same committed marks for the preview
        receipt's recv→publish clock."""
        self._receipt_call(receipts.observe, staged, stored_wall, due, now)
        if self.preview_receipt is not None:
            self._receipt_call(self.preview_receipt.committed, staged)
        confirmed = getattr(receipts, "confirmed", None)
        if confirmed is not None and due:
            # #10090 decision J: these events' batch may preview or stamp
            # before it resolves; nothing they hold is confirmed until then.
            self._receipt_call(
                confirmed.begin, due,
                {eid for eid in due if eid in getattr(self, "preview_events", ())},
            )

    def _stored_entry_is(self, stored_row, value) -> bool:
        """The row's STORED entry for this source is ``value`` (lane1 S1)."""
        entry = (getattr(stored_row, "win_probability_sources", None) or {})
        entry = entry.get(self.source) if isinstance(entry, dict) else None
        stored = entry.get("value") if isinstance(entry, dict) else None
        try:
            return round(float(stored), 6) == round(float(value), 6)
        except (TypeError, ValueError):
            return False

    def _settle_trail(self, event_id: int, group, *, stored_row, value) -> None:
        """#10090 F2(c): an `unchanged`/`unobserved` reading wrote nothing. When
        the row's stored entry for this source is its ``value`` (lane1 S1: the
        poll and the matcher write the same entry, so agreeing with process
        memory is not enough), the committed inputs whose prices it blended
        changed nothing readers see (`TailReceipts.settle`). Log-only."""
        receipts = self.receipts
        if receipts is None:
            return

        def settle():
            if self._stored_entry_is(stored_row, value):
                receipts.settle(event_id, [row for entry in group for row in entry.outcomes])

        self._receipt_call(settle)

    def _note_confirm_basis(self, event_id: int, contributing, *, stored_row=None,
                            value=None) -> None:
        """#10090 decision J: the rows an agreeing disposition blended, for
        `ConfirmedAt` to compare later inputs against (`TailReceipts.resolve`
        hands it the disposition after the commit).

        ``stored_row`` (an `unchanged`/`unobserved` disposition, which writes
        nothing): staged only when the row's STORED entry for this source is
        ``value`` (lane1 S1). That comparison is against process memory; the
        poll and the matcher write the same entry, so a reading that matches
        memory may not be what readers were last sent — then nothing is
        staged and the event is unknown until this source's next stamp."""
        confirmed = getattr(self.receipts, "confirmed", None)
        if confirmed is None:
            return
        if stored_row is not None and not self._stored_entry_is(stored_row, value):
            return
        self._receipt_call(confirmed.note_basis, event_id, contributing)

    def _note_confirm_unpublishable(self, event_id: int) -> None:
        """#10090 decision J (lane1 R2): this attempt's frame failed, so no
        reader receives what it stamped."""
        confirmed = getattr(self.receipts, "confirmed", None)
        if confirmed is not None:
            self._receipt_call(confirmed.unpublishable, event_id)

    def _note_confirm_published(self, acknowledged, unacknowledged) -> None:
        """#10090 decision J (lane1 R2): the publisher's answer, per
        (event, revision): only an acknowledged frame is on readers' screens."""
        confirmed = getattr(self.receipts, "confirmed", None)
        if confirmed is not None and (acknowledged or unacknowledged):
            self._receipt_call(confirmed.published, acknowledged, unacknowledged)

    def _preview_receipt_counters(self) -> dict:
        """This arm's cumulative counts for the preview receipt. Reads the
        process registry only if one was already built — never builds it."""
        from app.utils import blend_preview

        counts = {key: self.preview_stats.get(key, 0) for key in (
            "published", "revoked", "ledger_recomposed", "ledger_superseded",
            "withdrawn", "fenced", "authority_refused", "publish_errors")}
        counts["no_reading"] = self.stats.get("no_reading", 0)
        counts["observation_timeouts"] = self.preview_stats.get("observation_timeouts", 0)
        registry = blend_preview._REGISTRY
        for (source, status), n in getattr(registry, "refusal_counts", {}).items():
            if source == self.source:
                counts[f"refused:{status}"] = n
        for (source, phase), n in getattr(registry, "read_required_phases", {}).items():
            if source == self.source:
                counts[f"read_required:{phase}"] = n
        for end, n in self._capacity_ends.items():
            counts[f"capacity:{end}"] = n
        return counts

    def _preview_observer(self):
        """The ledger send's observer: the stage trace's (if any), the preview
        receipt's, then the delivery receipt's trail (#10090 fields 1+2). Each
        is read-only, runs after the send, and cannot cost the others."""
        trace, receipt = self._stage_hook("preview"), self.preview_receipt
        observers = [fn for fn in (
            trace,
            None if receipt is None else receipt.published,
            getattr(getattr(self, "receipts", None), "note_preview", None),
            getattr(self, "_hl_published", None),
        ) if fn is not None]
        if not observers:
            return None
        if len(observers) == 1:
            return observers[0]

        def observe(frame, meta, reply):
            for fn in observers:
                try:
                    fn(frame, meta, reply)
                except Exception:
                    pass
        return observe

    async def refresh_pending(
        self,
        *,
        flush_started: Optional[float] = None,
        defer_event_ids: Iterable[int] = (),
        withdrawing_event_ids: Iterable[int] = (),
    ) -> dict[str, int]:
        """#837 tail — stamp only the deferred events. Never raises.

        For the socket's flush when it has no new prices to write: `refresh`
        is otherwise only reached after a price write, and a deferred event on a
        quiet market would wait for a tick that may not come. Deferred means a
        row lock gave up OR the throttle held a written price. Returns at once,
        without opening a session, when nothing is queued or nothing queued is
        due yet.
        """
        self._start_normal_recovery()
        self._start_history()
        if (not self._lock_retry and not self._throttle_deferred
                and not self._book_refused_woken(_mono())):
            # Nothing owed is due here, so an aged input is not owed at all
            # (or parked, or held): no `refresh` will run to say so.
            self._stamp_wait_sweep(
                "pending", _mono() if flush_started is None else flush_started,
                excluded=set(defer_event_ids), due_reason="NOT_OWED",
            )
            if self.receipts is not None:
                # #10090: a quiet flush still closes a finished minute.
                self._receipt_call(self.receipts.roll)
            if self.preview_receipt is not None:
                self._receipt_call(self.preview_receipt.roll)
            return self.stats
        return await self.refresh(
            (), flush_started=flush_started, defer_event_ids=defer_event_ids,
            withdrawing_event_ids=withdrawing_event_ids,
        )

    def pending_event_ids(self) -> frozenset:
        """Every event this refresher still owes a stamp (#9462 review).

        #11317 P2: a parked refused pair counts only once it is worth a read
        again (`_book_refused_woken`); until then it spends no flush. It stays
        owed all the same: `hand_off_pending` carries it through a recycle.
        """
        return frozenset(
            self._lock_retry | self._throttle_deferred
            | self._book_refused_woken(_mono())
        )

    def _past_withdrawal(self, withdrawing, fresh=(), retry=None, deferred=None) -> set[int]:
        """#10090 `owed_past_withdrawal`: the owed events a drain may stamp
        although its caller still defers them, because the only thing pending
        is a buffered withdrawal no write has started. Their prices are already
        committed; the withdrawal, when it lands, is ordered after the stamp by
        the same-event fence (`join_stamp_reading`) and owes its own stamp.
        Throttle-deferred events only: a fresh cohort keeps waiting for its
        withdrawal, and a lock retry keeps its own path (`_lock_retry_past`).
        Empty when the switch is off, and without reading it when nothing is
        withdrawing.
        """
        withdrawing = set(withdrawing)
        if not withdrawing:
            return set()
        retry = self._lock_retry if retry is None else retry
        deferred = self._throttle_deferred if deferred is None else deferred
        passable = withdrawing.intersection(deferred).difference(retry, fresh)
        if passable and not _owed_past_withdrawal():
            passable = set()
        return passable | self._lock_retry_past(withdrawing, fresh, retry)

    def _lock_retry_past(self, withdrawing, fresh=(), retry=None) -> set[int]:
        """#10090 `lock_retry_past_withdrawal`: the lock retries a drain or a
        door may take although their caller still defers them, for the same
        reason as `_past_withdrawal`'s debt: their prices are committed, and
        the only thing pending is a buffered withdrawal no write has started.
        `_due` still gates each as it gates any lock retry (a failed-retry
        hold included), and a due prompt (`_take_lock_prompts`) is taken as it
        would be with nothing withdrawing. A fresh cohort keeps waiting. Empty when the switch is
        off, and without reading it when no lock retry is withdrawing.
        """
        withdrawing = set(withdrawing)
        if not withdrawing:
            return set()
        retry = self._lock_retry if retry is None else retry
        passable = withdrawing.intersection(retry).difference(fresh)
        if not passable or not _lock_retry_past_withdrawal():
            return set()
        return passable

    def owed_beside(
        self, defer_event_ids: Iterable[int], withdrawing_event_ids: Iterable[int] = (),
    ) -> frozenset:
        """#10090 — the owed events a drain beside ``defer_event_ids`` can take
        (`pending_event_ids` less the deferred ones, less `_past_withdrawal`'s),
        so a caller's "anything owed?" test agrees with the drain it starts."""
        excluded = set(defer_event_ids).difference(
            self._past_withdrawal(withdrawing_event_ids)
        )
        return frozenset(self.pending_event_ids().difference(excluded))

    # ── #11317 P2: a refused bundled pair waits for a changed input ──────────

    def _book_signature(self, tickers) -> tuple:
        reader = self.current_book_signature
        return tuple(reader(ticker) for ticker in tickers)

    def _park_book_refused(self, event_id: int, group) -> None:
        """The current-book proof refused this event's bundled pair.

        Before: re-queued as throttle-deferred, so every flush read it again
        and was refused again on the same book (v5810: no_reading ≈ 5.7×
        stamped). Now, when the owner installed `current_book_signature`, the
        pair is parked with the value of every in-memory input the proof read;
        it is read again when one of them changes, when a fresh price for the
        event arrives (a batch takes it as usual) or at the shared sweep.
        Synchronous, called from inside the proof: the values recorded are the
        ones the refusal saw, with no await between.
        """
        tickers = ()
        if self.current_book_signature is not None:
            tickers = tuple(sorted({
                row.external_id
                for entry in group
                if getattr(entry.market, "source", None) == "kalshi"
                and (getattr(entry.market, "external_id", None) or "").upper()
                .startswith("KXATPCHALLENGERMATCH-")
                for row in entry.outcomes
                if isinstance(getattr(row, "external_id", None), str)
            }))
        try:
            signature = self._book_signature(tickers) if tickers else None
        except Exception:
            signature = None
        if signature is None:
            self._throttle_deferred.add(event_id)
            return
        if not self._book_refused or self._book_refused_sweep_at is None:
            self._book_refused_sweep_at = _mono() + BOOK_REFUSED_SWEEP_S
        self._book_refused[event_id] = (tickers, signature)

    def _book_refused_woken(self, now: float) -> set[int]:
        """Parked pairs worth a read now. Pure: moves nothing."""
        if not self._book_refused:
            return set()
        sweep = self._book_refused_sweep_at
        if self.current_book_signature is None or (sweep is not None and now >= sweep):
            return set(self._book_refused)
        woken = set()
        for event_id, (tickers, signature) in self._book_refused.items():
            try:
                changed = self._book_signature(tickers) != signature
            except Exception:
                changed = True  # an unreadable input is not proof of no change
            if changed:
                woken.add(event_id)
        return woken

    def _wake_book_refused(self, now: float) -> None:
        """Move the woken parked pairs back into the ordinary deferred debt."""
        woken = self._book_refused_woken(now)
        if not woken:
            return
        for event_id in woken:
            del self._book_refused[event_id]
        self._throttle_deferred.update(woken)
        if not self._book_refused:
            self._book_refused_sweep_at = None

    def holding_event_ids(self) -> Optional[frozenset]:
        """#10090 — the running call's events whose stamp is queued or running.

        A caller may write a newer price for any other event the call took:
        its stamp has returned, so a new stamp is ordered after it (one frame
        sender) and reads the newer board. None before the call's first turn
        has opened its door (`refresh`'s first turn follows its task's
        creation, so a caller that yields once after creating it sees the set).
        """
        return None if self._holding is None else frozenset(self._holding)

    def fenced_event_ids(self) -> Optional[frozenset]:
        """#10090 write-under-queued — the running call's events a price write
        must not touch.

        Off (default), exactly `holding_event_ids`: every event whose stamp is
        queued or running. On (`STAMP_WRITE_UNDER_QUEUED`), the events whose
        attempt is RUNNING or still unclaimed in the call's own fresh
        population, plus the admitted queue beyond the lift horizon: with
        ``all`` no queued admitted attempt fences; with N the next N picks of
        each queue (and every queued live game a reader holds, picked first)
        stop fencing, so their newest price is written by the flush before
        their turn and the stamp carries it. None before the call opens its
        door, as `holding_event_ids`. A caller writing an event this returns
        as unfenced takes the write lease (`writing_begin`) first.
        """
        holding = self.holding_event_ids()
        horizon = stamp_write_under_queued()
        window = self._admission
        if holding is None or horizon is None or window is None:
            return holding
        if horizon == 0:
            lifted = set(window.live_queue)
            lifted.update(window.queue)
        else:
            lifted = set(itertools.islice(window.live_queue, horizon))
            lifted.update(itertools.islice(window.queue, horizon))
            held = self._reader_held_ids()
            if held:
                lifted.update(eid for eid in window.live_queue if eid in held)
        return holding.difference(lifted) if lifted else holding

    def writing_begin(self, event_ids: Iterable[int]) -> None:
        """#10090 write-under-queued — the caller is about to write these
        events' price rows (a flush's whole planned cohort, before its first
        chunk): until `writing_end` no queued attempt of theirs starts, so an
        attempt's read never straddles a write of its own event. A new write
        supersedes any unspent absorb right. Synchronous; harmless when the
        switch is off (nothing is skipped: the fence kept these fenced)."""
        event_ids = set(event_ids)
        self._writing.update(event_ids)
        for event_id in event_ids:
            self._written_queued.pop(event_id, None)

    def writing_end(self, event_ids: Iterable[int], *, written: Iterable[int] = ()) -> None:
        """#10090 write-under-queued — the caller's writes of these events
        have returned (``written``: those whose rows it committed). A written
        event whose attempt is still queued gains the right to ride that
        attempt with its committed cohort at the offer that follows
        (`admit_fresh`): the attempt has read nothing yet and, admitted after
        this return, will read the rows just committed. Wakes a worker waiting
        on the lease. Synchronous."""
        event_ids = set(event_ids)
        self._writing.difference_update(event_ids)
        written = set(written) & event_ids
        window = self._admission
        if (
            written and window is not None and not window.closed
            and stamp_write_under_queued() is not None
        ):
            queued = set(window.live_queue)
            queued.update(window.queue)
            now = _mono()
            for event_id in written:
                if event_id in queued:
                    self._written_queued[event_id] = now
        signal, self._writing_signal = self._writing_signal, None
        if signal is not None and not signal.done():
            signal.set_result(None)

    def writing_yield(self, event_ids: Iterable[int]) -> frozenset:
        """#10090 write-under-queued — the caller holding a lease on these
        events is about to WAIT for the running call to end (a join inside its
        chunk loop). A queued attempt of a leased event cannot start until
        that lease ends, and the lease cannot end until the caller resumes:
        so their queued attempts are handed back to debt here, exactly as
        `shed_queued` hands a hand-over's (read nothing, sent no frame, owed
        with no hold), and the call drains. Their rows are still being
        written; the offer after their last chunk admits a fresh attempt on
        the whole cohort. Returns the attempts handed back. Synchronous."""
        window = self._admission
        if window is None:
            return frozenset()
        leased = set(event_ids)
        shed = [eid for eid in window.live_queue if eid in leased]
        shed += [eid for eid in window.queue if eid in leased]
        if not shed:
            return frozenset()
        for queue in (window.live_queue, window.queue):
            for event_id in [eid for eid in queue if eid in leased]:
                queue.remove(event_id)
        window.admitted.difference_update(shed)
        for event_id in shed:
            self._written_queued.pop(event_id, None)
            self._refresh_failed(
                [event_id], window.retry, window.clocks.get(event_id, window.clock),
                self.receipts,
                {event_id: window.staged[event_id]} if event_id in window.staged else {},
                window.stored_wall.get(event_id),
                CancelledError(), hold=False,
            )
        window.release(shed)
        return frozenset(shed)

    def _absorb_right(self, event_id: int, now: float) -> bool:
        """Whether this event's committed cohort rides its queued (or just
        started) attempt: a write returned for it while it was queued, within
        WRITE_RIGHT_TTL_S. A live right is spent here; an expired one is
        dropped."""
        granted = self._written_queued.get(event_id)
        if granted is None:
            return False
        del self._written_queued[event_id]
        return now - granted <= WRITE_RIGHT_TTL_S

    def _ride_queued(self, window: _FreshAdmission, absorbed: set, marks) -> None:
        """Re-stage each absorbed event's newest committed input onto its
        queued attempt, exactly as an admission stages a taken event's, so the
        receipt the attempt resolves covers this cohort (no chain opens: the
        event counts as due)."""
        receipts = self.receipts
        if receipts is None or not absorbed:
            return
        staged, wall = self._receipt_call(receipts.staged_for, marks) or ({}, None)
        staged = {eid: m for eid, m in staged.items() if eid in absorbed}
        self._observe_committed(receipts, staged, wall, set(absorbed), _mono())
        for event_id, mark in staged.items():
            window.staged[event_id] = mark
            window.stored_wall[event_id] = wall

    async def _wait_for_write_lease(self) -> None:
        """A worker found every queued attempt under a write lease: wait for
        the next `writing_end`, at most WRITE_LEASE_WAIT_S, then look again."""
        import asyncio

        loop = asyncio.get_running_loop()
        spans = getattr(self, "stamp_spans", None)
        if spans is not None:
            spans.lease_waits += 1
        signal = self._writing_signal
        if signal is None or signal.done() or signal.get_loop() is not loop:
            signal = self._writing_signal = loop.create_future()
        try:
            await asyncio.wait_for(asyncio.shield(signal), timeout=WRITE_LEASE_WAIT_S)
        except asyncio.TimeoutError:
            pass

    def holding_frontier(self) -> Optional[_HoldingFrontier]:
        """#10090 — the running call's attempts queued or running right now,
        as a frontier a lifecycle wait can drain while the call keeps
        admitting later cohorts (none of which it waits for). None when no
        call is running. Synchronous; never closes the door."""
        window = self._admission
        return None if window is None else _HoldingFrontier(window)

    def admission_opened(self):
        """#10090 — a future resolved when the next call opens its door.

        A call's task created this turn has no window until its first turn
        runs, so `holding_frontier` reads None for a call that is about to
        hold attempts. A lifecycle wait awaits this (beside the task, which
        may end without opening one) rather than polling for the first turn.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        signal = self._admission_signal
        if signal is None or signal.done() or signal.get_loop() is not loop:
            signal = self._admission_signal = loop.create_future()
        return signal

    def adopt_pending(self, event_ids: Iterable[int]) -> None:
        """Take over stamps a previous run of this source still owed.

        Queued as throttle-deferred: this refresher has never stamped them, so
        the first flush (`refresh` or `refresh_pending`) finds them due.
        """
        self._throttle_deferred.update(event_ids)

    def _schedule_lock_prompt(self, event_id: int) -> None:
        """#10090 `lock_retry_prompt` — this event's stamp just gave up on a
        row lock. On, and while its run of skips has prompt attempts left,
        its next attempt is due `LOCK_RETRY_PROMPT_DELAYS_S` from now as fresh
        (`_take_lock_prompts`). Off (today, and any switch error), or once
        those are spent, it is ordinary debt exactly as before."""
        taken = self._lock_prompt_taken.get(event_id, 0)
        if taken < len(LOCK_RETRY_PROMPT_DELAYS_S) and _lock_retry_prompt():
            self._lock_prompt_at[event_id] = _mono() + LOCK_RETRY_PROMPT_DELAYS_S[taken]

    def _take_lock_prompts(self, candidates: Iterable[int], now: float) -> set[int]:
        """The candidates whose prompt attempt is due at ``now``; each is
        taken (no longer scheduled) and counted against its run's bound."""
        prompt = set()
        for event_id in candidates:
            at = self._lock_prompt_at.get(event_id)
            if at is not None and at <= now:
                prompt.add(event_id)
        for event_id in prompt:
            del self._lock_prompt_at[event_id]
            self._lock_prompt_taken[event_id] = self._lock_prompt_taken.get(event_id, 0) + 1
        return prompt

    def keep_owed(self, event_ids: Iterable[int], *, marks: Iterable[InputMark] = ()) -> None:
        """#10090 — record what `refresh` records for an event it must defer.

        For a caller whose committed events are all still being written by its
        own flush (`defer_event_ids`): joining the running call only to start a
        `refresh` that defers every one of them waits out the WHOLE call, and
        the next flush with it, for no stamp. The debt is the same: queued as
        throttle-deferred, counted once as throttled, and the cohort's newest
        committed input opens its receipt chain as a deferred one does. The
        staging slot is not touched (a running call may own it). Synchronous.
        """
        event_ids = set(event_ids)
        self._stage_trace("stage_admission", "KEEP_OWED", "KEPT_OWED", event_ids)
        throttled = event_ids.difference(self._throttle_deferred)
        self._throttle_deferred.update(event_ids)
        if throttled:
            self.stats["throttled"] += len(throttled)
        receipts = self.receipts
        if receipts is not None:
            staged, wall = self._receipt_call(receipts.staged_for, marks) or ({}, None)
            staged = {eid: m for eid, m in staged.items() if eid in event_ids}
            self._observe_committed(receipts, staged, wall, set(), _mono())

    def keep_committed(
        self, event_ids: Iterable[int], *, marks: Iterable[InputMark] = (),
    ) -> None:
        """#10090 — `keep_owed` for a cohort a lifecycle step hands over
        ALREADY COMMITTED: the catalog handover's bridged transfer
        (`_PMBridgeWriter.transfer`), whose drain fenced the game flush that
        would have stamped it as fresh. With `handover_fresh` on, the next
        `refresh` that finds these events due stamps them as fresh — live
        first, on the fixed workers, outside FRESH_FLUSH_PENDING_ATTEMPTS — so
        one handover's whole cohort does not drain a few events per call.
        Off (today, and any switch error) it is exactly `keep_owed`.
        """
        event_ids = set(event_ids)
        self.keep_owed(event_ids, marks=marks)
        if event_ids and _handover_fresh():
            self._carried_fresh.update(event_ids)

    # ── #10090: admitting a committed cohort into the running refresh ────────

    def admit_fresh(
        self,
        event_ids: Iterable[int],
        *,
        flush_started: Optional[float],
        marks: Iterable[InputMark] = (),
        defer_event_ids: Iterable[int] = (),
        withdrawing_event_ids: Iterable[int] = (),
    ) -> frozenset:
        """Hand a newly COMMITTED whole cohort to the running `refresh`.

        Returns the events this refresher now owns: each is stamped before the
        running call returns, on a free one of its stamp workers, or is left
        owed exactly as a `refresh` would leave it (throttled). Each is due,
        stamped and held on ITS flush's clock (``flush_started``): a cohort of
        a LATER flush than the running call's joins it for as long as the call
        admits (#10090: until its admitted workers go idle or a lifecycle
        drain calls `stop_admitting`), so a new batch never waits for an
        unrelated older stamp, however long that one is held. Beside it, at
        most this admission's debt slots of due owed events at a time
        (`window.debts`; ADMITTED_DEBT_SLOTS, default one, unless an
        `admitted_debt_slots` trial's arm says otherwise) are stamped too, so
        debt progresses while the call lives on; they are not in the returned set.
        Empty means the caller keeps them for its next `refresh`, as before:
        no call is admitting, the clock is earlier, or there is none (the final
        drain keeps its own contract), or the event is fenced — the running call is
        still stamping it (an earlier attempt that has returned does not
        fence a newer price, #10090), or the caller is still writing its cohort
        (``defer_event_ids``) — so no partial board is read and no two stamps
        of one event overlap or reorder. ``marks`` are the cohort's committed
        inputs; they are kept with the admitted events, never staged over
        the running call's own. Synchronous: nothing is awaited here.
        """
        window = self._admission
        if (
            window is None or window.closed or flush_started is None
            or window.flush_started is None
        ):
            if self._stage_hook("stage_admission") is not None:
                self._stage_trace(
                    "stage_admission", "ADMIT", "NO_ADMITTING_CALL", event_ids,
                    flush_started=flush_started,
                )
            return frozenset()
        if flush_started != window.flush_started and flush_started < window.flush_started:
            if self._stage_hook("stage_admission") is not None:
                self._stage_trace(
                    "stage_admission", "ADMIT", "EARLIER_CLOCK", event_ids,
                    flush_started=flush_started,
                )
            return frozenset()
        excluded = set(defer_event_ids)
        event_ids = list(event_ids)  # read again below (trace, door)
        # #10090 write-under-queued (STAMP_WRITE_UNDER_QUEUED): a committed
        # cohort of an event whose attempt is still queued — or started only
        # after the write that carried this cohort returned (`writing_end`
        # granted the right while it was queued) — RIDES that attempt: its
        # newest input is re-staged onto it below, no debt is kept and no
        # chain opens, and the attempt reads these rows at its turn. An event
        # whose attempt was running before the write is refused as HELD, as
        # before: its read may predate the commit.
        absorbed: set[int] = set()
        if self._written_queued:
            # A right outlives neither the attempt it was granted for (one
            # whose attempt has returned is admitted again as today) nor its
            # TTL nor the switch; a bridged or side write grants none.
            for eid in [eid for eid in self._written_queued if eid not in window.holding]:
                del self._written_queued[eid]
            if stamp_write_under_queued() is None:
                self._written_queued.clear()
            now_mono = _mono()
            for eid in event_ids:
                if eid in window.holding and eid not in excluded and self._absorb_right(eid, now_mono):
                    absorbed.add(eid)
        if self._stage_hook("stage_admission") is not None:
            for eid in event_ids:
                if eid in excluded or eid in window.holding:
                    self._stage_trace(
                        "stage_admission", "ADMIT",
                        "DEFERRED_UNFINISHED" if eid in excluded
                        else "ABSORBED" if eid in absorbed else "HELD",
                        (eid,), flush_started=flush_started,
                    )
        taken = {
            eid for eid in event_ids
            if eid not in excluded and eid not in window.holding
        }
        cohort = frozenset(taken)
        if self._lock_prompt_at:
            # #10090 `lock_retry_prompt`: a row-lock skip whose prompt attempt
            # is due rides this admission beside the cohort, outside the debt
            # slots, as it would be fresh in a new `refresh`. With
            # `lock_retry_past_withdrawal` on, a buffered withdrawal does not
            # keep it out.
            prompt_excluded = excluded.difference(
                self._lock_retry_past(withdrawing_event_ids, event_ids)
            )
            taken |= self._take_lock_prompts(
                (
                    eid for eid in self._lock_retry
                    if eid not in prompt_excluded and eid not in window.holding
                    and self._due(eid, flush_started)
                ),
                _mono(),
            )
        slots = _admitted_debt_slots()
        free = slots - len(window.debts)
        # Live throttle debt only; a row-lock retry is never "live" here.
        live = self._live_event_ids
        live_owed = (live & self._throttle_deferred) - self._lock_retry
        if live_owed and stamp_held_owed_fresh_on():
            # #10090 held-owed-fresh (STAMP_HELD_OWED_FRESH): an owed LIVE game
            # a reader holds open joins this admission as a cohort member —
            # on this flush's clock, picked held-first — rather than waiting
            # for the live-debt slot an unheld rider holds for a whole queue
            # turn. The same gate as the cohort's: never fenced (one attempt
            # per event), never an unfinished cohort or buffered withdrawal
            # (``excluded``), and due — as the debt pass takes only due games;
            # a not-due one would leave `_pending_continuation` and join
            # ``window.events`` for nothing (Authority N1).
            held = self._reader_held_ids()
            if held:
                taken |= {
                    eid for eid in live_owed
                    if eid in held and eid not in taken and eid not in excluded
                    and eid not in window.holding and self._due(eid, flush_started)
                }
        live_free = _admitted_live_debt_slots(slots) - len(window.live_debts)
        debt_excluded = excluded
        if free > 0 or (live_free > 0 and live_owed):
            # #10090: a call that keeps admitting may outlive the moment a new
            # `refresh` would have taken the debt, so the oldest due owed events
            # ride along — at most this admission's `slots` at a time, behind
            # the cohort, never fenced. Live games first, on their own allowance
            # (Argon Rank 2): pre-game debt never holds a live turn. The shared
            # slots keep turn order, where a live game takes only its own turn:
            # sorted live-first there, a live game owed again at every admission
            # took every shared turn from lock retries and pre-game debt
            # (lane1's R3 on 0b2a452d).
            self._wake_book_refused(_mono())
            owed = self._lock_retry | self._throttle_deferred
            rotation = [eid for eid in self._debt_rotation if eid in owed]
            rotation += sorted(owed.difference(rotation))
            order = [eid for eid in self._pending_continuation if eid in owed]
            order += [eid for eid in rotation if eid not in order]
            # #10090 `owed_past_withdrawal`: debt deferred only by a buffered
            # withdrawal may ride; the cohort itself is excluded as before.
            debt_excluded = excluded.difference(
                self._past_withdrawal(withdrawing_event_ids, event_ids)
            )
            live_order = [eid for eid in order if eid in live_owed]
            if len(live_order) > live_free > 0:
                # #10090 held-first: a held live game takes the live
                # allowance before unheld ones, each keeping its turn order;
                # after READER_FIRST_RUN such admissions the rotation order
                # alone decides one, so unheld debt keeps its turns.
                held = self._reader_held_ids()
                if (held and any(eid in held for eid in live_order)
                        and any(eid not in held for eid in live_order)):
                    if self._held_debt_run < READER_FIRST_RUN:
                        live_order.sort(key=lambda eid: eid not in held)
                        self._held_debt_run += 1
                    else:
                        self._held_debt_run = 0
            passes = (
                (window.live_debts, live_free, live_order),
                (window.debts, free, order),
            )
            for riding, room, candidates in passes:
                for eid in candidates:
                    if room <= 0:
                        break
                    if eid in taken or eid in debt_excluded or eid in window.holding:
                        continue
                    if self._due(eid, flush_started):
                        taken.add(eid)
                        riding.add(eid)
                        room -= 1
                        rotation.remove(eid)
                        rotation.append(eid)
            self._debt_rotation = rotation
        if absorbed:
            self._ride_queued(window, absorbed, marks)
            spans = getattr(self, "stamp_spans", None)
            if spans is not None:
                spans.absorbed += len(absorbed)
            if flush_started == self._pending_flush_started:
                # A committed price of this flush rides the call: the flush is
                # fresh-bearing, as it would be had the door taken it.
                self._pending_fresh_flush = True
            else:
                self._admitted_fresh_flush = flush_started
        if not taken:
            self._stamp_wait_sweep(
                "admit", flush_started, excluded=debt_excluded,
                due_reason="LIVE_DEBT_SLOT_BUSY",
            )
            return frozenset(absorbed)
        # #10090: an event whose earlier stamp in this call has returned is
        # admitted again for its newer committed price. That attempt is retired
        # whole: its admission, outcome, clock, retry origin and input mark are
        # settled, none pays for this one, and a throttled newer price is debt,
        # never an unfinished attempt at close.
        again = taken.intersection(window.events)
        for attempt in (window.admitted, window.completed, window.failed, window.retry):
            attempt.difference_update(again)
        for event_id in again:
            window.clocks.pop(event_id, None)
            window.staged.pop(event_id, None)
            window.stored_wall.pop(event_id, None)
        clock = flush_started
        due = sorted(eid for eid in taken if self._due(eid, clock))
        if self._stage_hook("stage_admission") is not None:
            for eid in taken:
                self._stage_trace(
                    "stage_admission", "ADMIT",
                    ("DEBT_" if eid not in cohort and (
                        eid in window.debts or eid in window.live_debts
                    ) else "")
                    + ("ADMITTED" if eid in due else "THROTTLED"),
                    (eid,), flush_started=flush_started,
                )
        throttled = taken.difference(due, self._throttle_deferred)
        self._throttle_deferred.update(taken.difference(due))
        if throttled:
            self.stats["throttled"] += len(throttled)
        retry = self._lock_retry.intersection(due)
        self._lock_retry.difference_update(due)
        self._throttle_deferred.difference_update(due)
        for event_id in due:
            self._book_refused.pop(event_id, None)
        self._pending_continuation = [
            eid for eid in self._pending_continuation if eid not in taken
        ]
        # Sticky for the flush, exactly as a fresh `refresh` call would be. A
        # later flush's allowance is not the running call's to spend: it is
        # marked for that flush's own first `refresh`. Debt alone is not fresh.
        if cohort and flush_started == self._pending_flush_started:
            self._pending_fresh_flush = True
        elif cohort:
            self._admitted_fresh_flush = flush_started
        self.stats["considered"] += len(due)
        window.events.update(taken)
        receipts = self.receipts
        if receipts is not None:
            staged, wall = self._receipt_call(receipts.staged_for, marks) or ({}, None)
            staged = {eid: m for eid, m in staged.items() if eid in taken}
            self._observe_committed(receipts, staged, wall, set(due), _mono())
            for event_id in due:
                if event_id in staged:
                    window.staged[event_id] = staged[event_id]
                    window.stored_wall[event_id] = wall
        if due:
            import asyncio

            window.admitted.update(due)
            window.holding.update(due)
            window.clocks.update(dict.fromkeys(due, clock))
            window.retry.update(retry)
            if slots > 1 or not window.live_debts.isdisjoint(due):
                # Debt rides behind the cohort that let it in: with more than
                # one slot (or live debt beside it), owed events with lower ids
                # would otherwise take every worker (and session slot) ahead of
                # these fresh prices.
                due = [eid for eid in due if eid in cohort] + [
                    eid for eid in due if eid not in cohort
                ]
            window.live_queue.extend(eid for eid in due if eid in live)
            window.queue.extend(eid for eid in due if eid not in live)
            # A finished worker consumes nothing more: reap it (its outcome
            # retrieved) so it never holds a worker place while the running
            # call's own stamps keep `_admission_join` from reaching it.
            finished = {task for task in window.workers if task.done()}
            window.workers.difference_update(finished)
            for task in finished:
                if not task.cancelled():
                    task.exception()
            for _ in range(min(FRESH_STAMP_WORKERS - len(window.workers), len(due))):
                window.workers.add(asyncio.create_task(self._admitted_worker(window)))
        # Owed, due and not excluded, yet not taken: no debt slot was free.
        self._stamp_wait_sweep(
            "admit", flush_started, taken=frozenset(due), excluded=debt_excluded,
            due_reason="LIVE_DEBT_SLOT_BUSY",
        )
        return cohort | absorbed if absorbed else cohort

    def stop_admitting(self) -> None:
        """#10090 — a lifecycle drain (final, cancellation, catalog change, a
        joined fallback) is about to wait for the running call: close its door
        first, so the wait covers what is already queued, never a later
        arrival. Synchronous; the call ends once its queue has drained."""
        window = self._admission
        if window is not None:
            window.closed = True

    def shed_queued(self) -> frozenset:
        """#10090 — `stop_admitting` for a drain that holds every flush while
        it waits (the PM catalog handover's `stamps` phase): also hand back
        each admitted attempt no worker has started, so the wait covers only
        the attempts already running. A shed attempt read nothing and sent no
        frame; its committed price stays owed with no failed-retry hold, as
        a cancelled close leaves an admitted attempt whose worker never ran
        (`_admission_close`), and the next call stamps it on the board as
        it is then. Returns the shed events. Synchronous."""
        window = self._admission
        if window is None:
            return frozenset()
        window.closed = True
        shed = [*window.live_queue, *window.queue]
        window.live_queue.clear()
        window.queue.clear()
        if not shed:
            return frozenset()
        window.admitted.difference_update(shed)
        for event_id in shed:
            self._refresh_failed(
                [event_id], window.retry, window.clocks.get(event_id, window.clock),
                self.receipts,
                {event_id: window.staged[event_id]} if event_id in window.staged else {},
                window.stored_wall.get(event_id),
                CancelledError(), hold=False,
            )
        window.release(shed)
        if _handover_fresh():
            # #10090 `handover_fresh`: the shed attempts are the next call's
            # FRESH population (live first, held first, on the fixed workers,
            # outside FRESH_FLUSH_PENDING_ATTEMPTS), as a carried bridged
            # cohort is — not debt that drains a rider or two per queue turn.
            # Production 16:01-16:41Z 2026-10-31 (v6005, ~180 live PM games):
            # six handovers shed 115-244 queued attempts each; 57% of the
            # hour's moved live chains and 33 of its 40 worst carried a shed
            # instant as `held_wall`, a quiet game's re-stamp then 30-160 s.
            self._carried_fresh.update(shed)
        return frozenset(shed)

    def admitting(self) -> bool:
        """#10090 — a running call is still taking later flushes' cohorts."""
        window = self._admission
        return window is not None and not window.closed

    async def _admitted_worker(self, window: _FreshAdmission) -> None:
        while window.live_queue or window.queue:
            # #10090 write-under-queued: an event whose price rows are under a
            # write lease is not started until the write has returned.
            skip = (
                self._writing
                if self._writing and stamp_write_under_queued() is not None else ()
            )
            # Read before the pick: a non-live head taken while a live game
            # waits (ADMITTED_LIVE_RUN) is stamped alone, as today.
            live_waiting = bool(window.live_queue)
            event_id = window.next_queued(
                self._reader_held_ids() if live_waiting else frozenset(), skip,
            )
            if event_id is None:
                await self._wait_for_write_lease()
                continue
            group_ids = [event_id]
            live_batch = False
            if not live_waiting and window.queue:
                group_ids = self._admitted_batch(window, event_id, skip)
            elif live_waiting and window.live_queue and event_id in self._live_event_ids:
                # #10090 `admitted_live_batch`: the picked live game and the
                # head live games of its own cohort share one transaction.
                group_ids = self._admitted_live_batch(window, event_id, skip)
                live_batch = len(group_ids) > 1
            await self._stamp_admitted(window, group_ids, live_batch=live_batch)

    def _admitted_live_batch(
        self, window: _FreshAdmission, head: int, skip: Container[int] = (),
    ) -> list[int]:
        """#10090 — the picked LIVE event and, when an `ADMITTED_LIVE_BATCH`
        above one is in force, the queued live events at the head of the live
        queue from the same cohort: head of the queue only, in queue order,
        stopping at the first event that is no longer live by now or carries
        another flush clock or stored wall (or, write-under-queued, is under a
        write lease — ``skip``). Nothing is reordered or skipped; an event
        not taken stays at the head for the next turn. Each extra event
        counts against ADMITTED_LIVE_RUN as its own pick would, so a waiting
        pre-game event keeps today's one turn in ADMITTED_LIVE_RUN + 1 live
        EVENTS, not live transactions."""
        limit = _admitted_live_batch_size()
        live = self._live_event_ids
        if limit <= 1 or head not in live:
            return [head]
        clock = window.clocks.get(head, window.clock)
        stored_wall = window.stored_wall.get(head)
        group_ids = [head]
        live_queue = window.live_queue
        while live_queue and len(group_ids) < limit:
            if window.queue and window.live_run >= ADMITTED_LIVE_RUN:
                break
            event_id = live_queue[0]
            if (
                event_id not in live
                or event_id in skip
                or window.clocks.get(event_id, window.clock) != clock
                or window.stored_wall.get(event_id) != stored_wall
            ):
                break
            group_ids.append(live_queue.popleft())
            if window.queue:
                window.live_run += 1
        return group_ids

    def _admitted_batch(
        self, window: _FreshAdmission, head: int, skip: Container[int] = (),
    ) -> list[int]:
        """#10090 — the non-live head and, when an `ADMITTED_STAMP_BATCH`
        above one is in force, the queued events that follow it from the same
        cohort: the head of the queue only, in queue order, stopping at the
        first event that is live by now or carries another flush clock or
        stored wall (or is under a write lease — ``skip``), or the moment a
        live game is queued. Nothing is reordered or skipped; an event not
        taken stays at the head for the next turn."""
        limit = _admitted_stamp_batch()
        live = self._live_event_ids
        if limit <= 1 or head in live:
            return [head]
        clock = window.clocks.get(head, window.clock)
        stored_wall = window.stored_wall.get(head)
        group_ids = [head]
        queue = window.queue
        while queue and len(group_ids) < limit and not window.live_queue:
            event_id = queue[0]
            if (
                event_id in live
                or event_id in skip
                or window.clocks.get(event_id, window.clock) != clock
                or window.stored_wall.get(event_id) != stored_wall
            ):
                break
            group_ids.append(queue.popleft())
        return group_ids

    async def _stamp_admitted(
        self, window: _FreshAdmission, group_ids: list[int], *, live_batch: bool = False,
    ) -> None:
        """Admitted events read in their own session after their cohort
        committed, exactly as a singleton stamp reads, published through the
        running call's one sender. Never raises but for cancellation.

        One event (today) owns its whole transaction. Several (an
        `ADMITTED_STAMP_BATCH` above one, `_admitted_batch`, or an
        `ADMITTED_LIVE_BATCH` above one, `_admitted_live_batch` — ``live_batch``)
        share one session, read and COMMIT, each in its own savepoint with its
        own lock budget; they share one flush clock and stored wall by
        construction."""
        receipts = self.receipts
        staged = {
            event_id: window.staged[event_id]
            for event_id in group_ids if event_id in window.staged
        }
        stored_wall = window.stored_wall.get(group_ids[0])
        clock = window.clocks.get(group_ids[0], window.clock)

        def committed(ids):
            window.completed.update(ids)
            if receipts is not None:
                self._resolve_receipt_wait(
                    receipts, ids, self._dispositions, staged,
                    stored_wall, _mono(),
                )

        try:
            self._record_stamp_clock(group_ids, clock)
            await self._refresh_batch(
                group_ids, clock,
                on_committed=committed, publish_committed=window.publish,
            )
        except Exception as exc:
            self.stats["errors"] += 1
            logger.exception(
                "live_blend_refresh[%s]: admitted group failed for %s",
                self.source, group_ids,
            )
            if (
                not window.debts.isdisjoint(group_ids)
                and len(window.debts) > ADMITTED_DEBT_SLOTS
            ):
                # An owed stamp only an `admitted_debt_slots` trial let in beside
                # the setting's has failed: that trial switches off in this
                # process (automatic switch-back on error); the stamps already
                # in flight finish and no new debt rides past the setting.
                _optional_db_trial().trip(ADMITTED_DEBT_SLOTS_SWITCH, exc)
            if live_batch and len(group_ids) > ADMITTED_LIVE_BATCH:
                # A live batch only an `admitted_live_batch` trial formed has
                # failed: that trial switches off in this process; its events
                # stay owed exactly as a failed singleton's do.
                _optional_db_trial().trip(ADMITTED_LIVE_BATCH_SWITCH, exc)
            elif not live_batch and len(group_ids) > ADMITTED_STAMP_BATCH:
                # A batch only an `admitted_stamp_batch` trial formed has
                # failed: that trial switches off in this process; its events
                # stay owed exactly as a failed singleton's do.
                _optional_db_trial().trip(ADMITTED_STAMP_BATCH_SWITCH, exc)
            unfinished = [
                event_id for event_id in group_ids if event_id not in window.completed
            ]
            if unfinished:
                window.failed.update(unfinished)
                self._refresh_failed(
                    unfinished, window.retry, clock, receipts, staged,
                    stored_wall, exc,
                )
        else:
            unfinished = [
                event_id for event_id in group_ids if event_id not in window.completed
            ]
            if unfinished:
                committed(unfinished)
        finally:
            window.release(group_ids)

    async def _admission_join(self, window: _FreshAdmission) -> None:
        """Wait for every admitted stamp; close the door in the same turn the
        last one is seen finished, so nothing is admitted that no one joins."""
        import asyncio

        while window.workers:
            done, _ = await asyncio.wait(set(window.workers))
            window.workers.difference_update(done)
            for task in done:
                if not task.cancelled():
                    task.exception()
        window.closed = True

    async def _admission_close(self, window: _FreshAdmission, *, cancel: bool) -> None:
        """End admission for this call. On cancellation the admitted stamps are
        cancelled and joined — a repeated cancellation is recorded, never
        obeyed early — and every admitted event that did not commit stays
        owed with no failed-retry hold, including one whose worker never ran
        its first turn."""
        import asyncio

        window.closed = True
        interrupted = None
        while True:
            active = {task for task in window.workers if not task.done()}
            if not active:
                break
            if cancel:
                for task in active:
                    if not task.cancelling():
                        task.cancel()
            try:
                await asyncio.wait(active)
            except CancelledError as exc:
                interrupted = exc
                cancel = True
        for task in window.workers:
            if not task.cancelled():
                task.exception()
        window.workers.clear()
        # Only now: a worker still joining above takes its session slot here.
        if self._admission is window:
            self._admission = None
        unfinished = window.admitted.difference(window.completed, window.failed)
        for event_id in sorted(unfinished):
            self._refresh_failed(
                [event_id], window.retry, window.clocks.get(event_id, window.clock),
                self.receipts,
                {event_id: window.staged[event_id]} if event_id in window.staged else {},
                window.stored_wall.get(event_id),
                interrupted or CancelledError(), hold=False,
            )
        if interrupted is not None:
            raise interrupted

    async def _read_groups(self, session, event_ids: list[int], *, overlay_held=True,
                           clock_sample=None, stopped_waiting=None) -> dict[int, tuple]:
        from copy import deepcopy
        from types import SimpleNamespace
        from sqlalchemy import (
            ARRAY, Integer, and_, any_, bindparam, case, cast, func, literal, null, or_, select,
        )
        from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport
        from app.utils.live_blend import MarketOutcomes
        from app.utils.content_understanding import CONTENT_UNDERSTANDING_KEY
        from app.utils.prediction_market_matching import (
            COMBAT_FIGHT_WINNER_PREFIXES, TENNIS_MATCH_WINNER_PREFIXES,
        )

        # One fresh statement snapshot of graph, admission and quotes. No ORM
        # hydration and no per-quote Market -> Event -> Outcome round trips.
        # The OUTER JOIN keeps empty/prop markets: group length gates devig.
        outcome_join = FuturesOutcome.market_id == FuturesMarket.id
        if self.source == "kalshi":
            # Exact feeds_win_prob_blend ticker rule, using its shared sets.
            # Missing/empty tickers retain the resolver's name fallback.
            prefix = func.split_part(func.lower(FuturesMarket.external_id), "-", 1)
            outcome_join = and_(
                outcome_join,
                or_(
                    FuturesMarket.external_id.is_(None),
                    FuturesMarket.external_id == "",
                    prefix.endswith("game"),
                    prefix.in_(sorted(
                        COMBAT_FIGHT_WINNER_PREFIXES | TENNIS_MATCH_WINNER_PREFIXES
                    )),
                ),
            )
        elif self.source == "polymarket":
            from app.services.polymarket_api import GAMMA_FULL_CONTEST_WINNER_TYPES
            from app.utils.content_understanding import (
                CONTENT_UNDERSTANDING_KEY,
                CONTENT_UNDERSTANDING_VERSION,
            )

            # A known venue refusal cannot speak in the resolver, including
            # as a devig sibling. Omit only its OUTCOMES, keeping the market
            # shell and group length. Unknown/malformed/future/older records
            # retain their outcomes; no title or inferred class gates this read.
            understanding = FuturesMarket.market_metadata[CONTENT_UNDERSTANDING_KEY]
            version = understanding["v"]
            semantic = understanding["semantic_type"]
            venue = understanding["venue_type"]
            known_refusal = and_(
                func.jsonb_typeof(FuturesMarket.market_metadata) == "object",
                func.jsonb_typeof(understanding) == "object",
                func.jsonb_typeof(version) == "number",
                version.astext == str(CONTENT_UNDERSTANDING_VERSION),
                func.jsonb_typeof(semantic) == "string",
                semantic.astext != "",
                func.jsonb_typeof(venue) == "string",
                venue.astext != "",
                venue.astext.not_in(sorted(GAMMA_FULL_CONTEST_WINNER_TYPES)),
            )
            # Missing JSON paths are SQL NULL: absence is never a refusal.
            outcome_join = and_(outcome_join, ~func.coalesce(known_refusal, False))
        # Only the raw content-understanding record participates in prepared
        # market admission. Keep that entire record, including malformed and
        # older versions, while leaving unrelated catalog JSON in PostgreSQL.
        fields = (
            (FuturesMarket, PREPARED_MARKET_FIELDS),
            (Event, PREPARED_EVENT_FIELDS),
            (FuturesOutcome, PREPARED_OUTCOME_FIELDS),
        )
        # #10090: a preview is composed BEFORE the UPDATE, so it needs the
        # whole committed bag and the revision that dates it. A plain read: it
        # waits on no row lock. Not selected unless this arm previews a
        # canary event in this batch: any other read is the statement it was.
        # #10090 `STAMP_READ_JSON_ONCE`: each JSON value rides one row of its
        # event / market. The trailing flags say which row; Python reads the
        # value from that row only, so any row order builds the same graph.
        once = stamp_read_json_once()
        if once:
            market_json_row = func.row_number().over(
                partition_by=(FuturesMarket.event_id, FuturesMarket.id),
                order_by=FuturesOutcome.id,
            ) == 1
            event_json_row = func.row_number().over(
                partition_by=FuturesMarket.event_id,
                order_by=(FuturesMarket.id, FuturesOutcome.id),
            ) == 1

            def market_json(expr):
                return case((market_json_row, expr), else_=null())

            def event_json(expr):
                return case((event_json_row, expr), else_=null())

            json_flags = (market_json_row.label("market_json_row"),
                          event_json_row.label("event_json_row"))
        else:
            def market_json(expr):
                return expr

            event_json = market_json
            json_flags = ()
        preview_columns = (
            (event_json(Event.win_probability_sources).label("preview_sources"),
             Event.win_probability_sources_rev.label("preview_rev"),
             func.statement_timestamp().label("preview_context_at"))
            if not getattr(self, "preview_events", frozenset()).isdisjoint(event_ids)
            else ()
        )
        # Capture BEFORE the statement, not when a prepared plan is later
        # published. Retirement invalidates this proof without renewing it.
        # A read its caller left while it waited for a slot or connection
        # does no admission read either (#10090).
        if stopped_waiting is not None and stopped_waiting():
            raise _ObservationReadAbandoned
        # `preview_from_commit`: a kept graph is as old as its ticket.
        read_started = _mono()
        with _observation_read_step("admission"):
            preview_ticket = (
                await self._preview_admission_read() if preview_columns else None
            )
        # An observation preview whose caller stopped waiting issues no
        # statement, and stops once its statement returns: the connection goes
        # back to the pool normally and nothing below runs (#10090).
        if stopped_waiting is not None and stopped_waiting():
            raise _ObservationReadAbandoned
        with _observation_read_step("query"):
            result = (
                await session.execute(
                    select(*(
                        Sport.key.label("sport_key") if model is Event and key == "sport_key"
                        else (cast(null(), Event.win_probability_sources.type)
                         if preview_columns else
                         event_json(Event.win_probability_sources.op("->")(
                             literal(self.source)))).label(key)
                        if model is Event and key == "win_probability_sources"
                        else market_json(func.jsonb_build_object(
                            CONTENT_UNDERSTANDING_KEY,
                            FuturesMarket.market_metadata[CONTENT_UNDERSTANDING_KEY],
                        )).label(key)
                        if model is FuturesMarket and key == "market_metadata"
                        else getattr(model, key)
                        for model, keys in fields for key in keys
                    ), *json_flags, *preview_columns, *(
                        (func.clock_timestamp().label("observation_clock"),)
                        if clock_sample is not None else ()
                    ))
                    .select_from(FuturesMarket)
                    .join(Event, Event.id == FuturesMarket.event_id)
                    .outerjoin(Sport, Sport.id == Event.sport_id)
                    .outerjoin(FuturesOutcome, outcome_join)
                    .where(
                        FuturesMarket.source == self.source,
                        # One array parameter: one statement shape, so one
                        # prepared statement per connection whatever the
                        # batch size (an expanding IN made one per length).
                        FuturesMarket.event_id == any_(bindparam(
                            "event_ids", list(event_ids), type_=ARRAY(Integer),
                        )),
                    )
                )
            )
            rows = result.all()
            # The flags are found by NAME: a result without them (a rig's
            # canned rows) is read exactly as before, every row its own JSON.
            keys = getattr(result, "keys", None)
            once = once and callable(keys) and "event_json_row" in keys()
        if stopped_waiting is not None and stopped_waiting():
            raise _ObservationReadAbandoned
        if clock_sample is not None and rows:
            # Read DB time in the existing statement, without another pool
            # checkout. The caller may adopt it only after its scope succeeds.
            clock_sample["value"] = min(row[-1] for row in rows)
            rows = [row[:-1] for row in rows]
        grouped: dict[int, tuple] = {}
        entries: dict[int, MarketOutcomes] = {}
        held = self.held_quotes if overlay_held else None
        n_market, n_event = len(PREPARED_MARKET_FIELDS), len(PREPARED_EVENT_FIELDS)
        metadata_at = PREPARED_MARKET_FIELDS.index("market_metadata")
        source_at = n_market + PREPARED_EVENT_FIELDS.index("win_probability_sources")
        flags_at = n_market + n_event + len(PREPARED_OUTCOME_FIELDS)
        # `STAMP_READ_JSON_ONCE`: markets / events whose JSON row is still to come.
        json_owed: set = set()
        json_cells = 0

        def event_json_from(row, target):
            # Before the UPDATE only this source's restamp guard reads
            # the JSON. The full aggregate uses UPDATE RETURNING below.
            source_value = row[source_at]
            if preview_columns:
                # This same SELECT already returned the full bag. Avoid
                # transferring/decoding its source again on every row.
                # Preserve the two independently decoded JSON owners,
                # copying only once per event, including nested values.
                full_sources = row[-3]
                source_value = (deepcopy(full_sources.get(self.source))
                                if isinstance(full_sources, dict) else None)
            target["win_probability_sources"] = {self.source: source_value}
            if preview_columns:
                # This SELECT proves an authoritative null bag is
                # empty at preview_rev, including before the first
                # source stamp commits. Missing reads and malformed
                # non-null roots must still fail closed downstream.
                target["preview_sources"] = {} if row[-3] is None else row[-3]

        for row in rows:
            market_id = row[0]
            event_id = row[n_market]
            if once:
                market_row, event_row = row[flags_at], row[flags_at + 1]
                json_cells += bool(market_row) + bool(event_row)
            entry = entries.get(market_id)
            if entry is None:
                market = SimpleNamespace(**dict(zip(
                    PREPARED_MARKET_FIELDS, row[:n_market]
                )))
                if once and not market_row:
                    json_owed.add(("market", market_id))
                event_values = row[n_market:n_market + n_event]
                if event_id not in grouped:
                    context = dict(zip(PREPARED_EVENT_FIELDS, event_values))
                    if once and not event_row:
                        json_owed.add(("event", event_id))
                    else:
                        event_json_from(row, context)
                    if preview_columns:
                        # Trailing columns; the outcome slice below zips by
                        # field name, so they never reach an outcome row.
                        context["preview_rev"] = row[-2]
                        context["preview_context_at"] = row[-1]
                        context["preview_read_ticket"] = preview_ticket
                    grouped[event_id] = (
                        SimpleNamespace(**context),
                        [],
                    )
                elif once and event_row:
                    vars(grouped[event_id][0]).update(_json_row_patch(event_json_from, row))
                    json_owed.discard(("event", event_id))
                event, group = grouped[event_id]
                entry = MarketOutcomes(
                    market=market,
                    outcomes=[],
                    event_has_result=event.completed_at is not None,
                    event_commence_time=(
                        event.commence_time
                        if event.status == "live" and event.completed_at is None
                        else None
                    ),
                )
                entries[market_id] = entry
                group.append(entry)
            elif once:
                if market_row:
                    entry.market.market_metadata = row[metadata_at]
                    json_owed.discard(("market", market_id))
                if event_row:
                    vars(grouped[event_id][0]).update(_json_row_patch(event_json_from, row))
                    json_owed.discard(("event", event_id))
            outcome_values = row[n_market + n_event:]
            if outcome_values[0] is not None:
                outcome = SimpleNamespace(**dict(zip(
                    PREPARED_OUTCOME_FIELDS, outcome_values
                )))
                entry.outcomes.append(outcome)
        if json_owed:
            # `row_number() = 1` exists in every partition, so this is a broken
            # statement, never a quiet market or event: refuse the graph.
            raise RuntimeError(f"_read_groups: no JSON row for {sorted(json_owed)[:5]}")
        spans = getattr(self, "stamp_spans", None)
        if spans is not None:
            spans.read_rows += len(rows)
            spans.read_json += json_cells if once else 2 * len(rows)
        # Strong references prevent id reuse while held.overlay_event replaces
        # rows. Membership by id is safe until classification below completes.
        original_rows = {id(row): row for _event, group in grouped.values()
                         for entry in group for row in entry.outcomes}
        if held is not None:
            for _event, group in grouped.values():
                held.overlay_event(group)
        if getattr(self, "current_primary_input", None) is not None:
            for _event, group in grouped.values():
                for entry in group:
                    for row in entry.outcomes:
                        row._primary_quote_overlaid = id(row) not in original_rows
        if preview_ticket is not None:
            self._remember_preview_graphs(grouped, original_rows, read_started)
        if preview_ticket is not None:
            # Marked so a caller whose deadline lands here cancels it as before:
            # a retirement writes Redis and the row, never after its caller left.
            with _observation_read_step("retire"):
                await self._retire_terminal_preview_read(grouped, preview_ticket)
        return grouped

    async def _prepare_groups(self, event_ids: list[int]) -> dict[int, tuple]:
        """Read one fresh scalar graph owned only by this refresh call.

        `_read_groups` materializes plain namespaces from scalar query rows,
        including newly decoded JSON. No ORM objects or shared cache escape
        the transaction, so rebuilding and recursively copying that graph
        again only delays the first stamp. Each event's group belongs to one
        worker. Queued fresh events still reread their current quotes; the
        cold orientation fallback still reads in the stamp's own session.
        """
        from app.tasks.base import get_task_session

        factory = self._session_factory or get_task_session
        started = _stamp_span_clock()  # #10090 `StampSpans` (`prepared`)
        async with self._session_slot(), factory() as session:
            entered = _stamp_span_clock()
            try:
                return await self._read_groups(session, event_ids)
            finally:
                spans = getattr(self, "stamp_spans", None)
                if spans is not None:
                    spans.add_prepared(entered - started, _stamp_span_clock() - entered)

    def _session_slot(self):
        """The run's existing three slots, across quote and history owners."""
        return self._session_slots

    @contextlib.asynccontextmanager
    async def _history_reservations(self, event_ids, now, owed):
        """Reserve debt space before a transaction can owe a point.

        Same-event quotes remain serial under the consumer's existing fence.
        Distinct due observations are never dropped or coalesced. Past the
        ordinary backlog a due stamp still owes its point and does not wait
        (#11138): production v5763 13:01:22Z, Kalshi's writer held 5.364 s at
        64 owed, held 15331223's .375 for 5.8 s behind three due stamps. The
        point keeps its observation time and the writer pays it without
        another quote (#11181). Past the memory bound (`HISTORY_SPILL_LIMIT`),
        or while custody holds rows memory does not, a committed point is
        carried by its custody row alone and loaded in its event's order.
        """
        reserved = set()
        kept = set()
        ready = asyncio.Event()
        try:
            for eid in event_ids:
                last = self._history_reserved.get(eid, self._last_snapshot_at.get(eid))
                if last is not None and now - last < self.snapshot_interval_s:
                    continue
                if self._history_count >= self._history_limit:
                    self._start_history()
                    self.stats["history_deferred"] += 1
                self._history_count += 1
                reserved.add(eid)
            try:
                yield reserved, ready
            except BaseException:
                self._note_normal_debt()
                # A COMMIT whose acknowledgement was lost may still have
                # stored this transaction's custody rows: the next drain reads,
                # and a load already in flight cannot conclude it saw them.
                if reserved and self._chart_custody is not None:
                    self._custody_backlog = True
                    self._custody_only_committed += 1
                raise
            # The nested session has now exited with a successful COMMIT.
            for eid, value, reading in owed:
                self._history_reserved[eid] = now
                custody_id = getattr(reading, "custody_id", None)
                if custody_id is not None and (
                    self._custody_backlog
                    or len(self._history)
                    >= self._history_limit + self._history_spill_limit
                ):
                    self._custody_backlog = True
                    self._custody_only_committed += 1
                    self._custody_ready[custody_id] = ready
                    if len(self._custody_clock) < (
                        self._history_limit + self._history_spill_limit
                    ):
                        self._custody_clock[custody_id] = now
                    self.stats["history_custody_only"] += 1
                    continue
                self._history.append((eid, value, reading, now, ready))
                kept.add(eid)
        finally:
            self._history_count -= len(reserved - kept)
            self._history_changed.set()

    def _start_history(self, *, force=False):
        if self._history_task and not self._history_task.done():
            return
        load = not force and self._custody_backlog
        if not self._history and not load:
            return
        if not force and not load and all(
            _mono() < self._history_retry_at.get(point[0], 0.0)
            for point in self._history
        ):
            return
        self._history_task = asyncio.create_task(self._drain_history(force=force))

    async def _drain_history(self, *, force=False):
        from app.tasks.base import get_task_session

        factory = self._session_factory or get_task_session
        failed = set()
        cursor = 0
        try:
            while True:
                while cursor < len(self._history):
                    point = self._history[cursor]
                    eid, value, reading, observed_clock, ready = point
                    # A failed event keeps its original FIFO, but cannot strand a
                    # healthy sibling's history behind its own retry hold.
                    if eid in failed or (
                        not force and _mono() < self._history_retry_at.get(eid, 0.0)
                    ):
                        cursor += 1
                        continue
                    await ready.wait()  # publication was attempted after COMMIT
                    if not await self._write_owed_snapshots(
                        [(eid, value, reading)],
                        observed_clock,
                        factory,
                        verify_event=eid in self._history_retry_at,
                    ):
                        failed.add(eid)
                        self._history_retry_at[eid] = (
                            _mono() + self.failed_retry_interval_s
                        )
                        cursor += 1
                        self._history_changed.set()
                        continue
                    self._history.pop(cursor)
                    self._history_count -= 1
                    self._history_retry_at.pop(eid, None)
                    # A custody row outside memory may still owe this event a
                    # later point; its reservation clock stays until loaded.
                    if not self._custody_backlog and not any(
                        point[0] == eid for point in self._history
                    ):
                        self._history_reserved.pop(eid, None)
                    self._history_changed.set()
                # The final drain of a run reads no custody: its rows are
                # durable and the next run of the source starts by loading them.
                if force or not await self._load_custody(factory):
                    break
        except Exception:
            self.stats["errors"] += 1
            for eid, *_ in self._history:
                self._history_retry_at[eid] = _mono() + self.failed_retry_interval_s
            logger.exception(
                "live_blend_refresh[%s]: history owner failed; debt retained",
                self.source,
            )
        finally:
            self._history_changed.set()

    async def _load_custody(self, factory) -> int:
        """#11181 — move custody rows memory does not hold into memory.

        Oldest commit id first, at most the room memory has. Same-event points
        commit serially, so ids keep each event's observation order, and while
        any row is outside memory every newly committed point also stays there
        (`_history_reservations`): no later point of an event is ever written
        ahead of an earlier one. A row another drain already paid is found
        gone by `settle`, never written twice. Returns how many rows it moved.
        """
        if not self._custody_backlog or self._chart_custody is None:
            return 0
        room = self._history_limit + self._history_spill_limit - len(self._history)
        if room <= 0:
            return 0
        self._custody_ready = {
            cid: ready for cid, ready in self._custody_ready.items()
            if not ready.is_set()
        }
        committed_before = self._custody_only_committed
        held = {
            reading.custody_id for _, _, reading, _, _ in self._history
            if getattr(reading, "custody_id", None) is not None
        }
        async with self._session_slot(), factory() as session:
            rows = await self._chart_custody.load(session, self.source, held, room)
        done = asyncio.Event()
        done.set()
        for custody_id, eid, value, payload in rows:
            ready = self._custody_ready.pop(custody_id, done)
            # A row from an earlier process carries no clock of this one: the
            # reservation that admitted it already spaced it on the cadence.
            self._history.append((
                eid, value, _chart_reading_from_payload(custody_id, payload),
                self._custody_clock.pop(custody_id, None), ready,
            ))
            self._history_count += 1
        if len(rows) < room and self._custody_only_committed == committed_before:
            # Everything committed before this read was visible to it.
            self._custody_backlog = False
        return len(rows)

    async def drain_history(self):
        """One final attempt, joined through repeated cancellation before close.

        Failed scalar debt stays in the queue for the next run. The owner never
        republishes frames or turns history-only debt into blend debt.
        """
        interrupted = None
        # Before any await: a read its caller left ends the old way now, and
        # the run's bounded reap joins it before the engine is disposed.
        for task in list(getattr(self, "_detached_reads", ())):
            task.cancel()
            _park_closing_sampler(getattr(self, "source", None), task)
        try:
            await self._close_preview_maintenance()
        except asyncio.CancelledError as exc:
            interrupted = exc
        try:
            await self._close_commit_preview()
        except asyncio.CancelledError as exc:
            interrupted = exc
        try:
            await self._close_receipt_preview()
        except asyncio.CancelledError as exc:
            interrupted = exc
        try:
            await self._close_normal_recovery()
        except asyncio.CancelledError as exc:
            interrupted = exc
        try:
            await self._close_optional_db()
        except asyncio.CancelledError as exc:
            interrupted = exc
        self._start_history(force=True)
        task = self._history_task
        while task is not None and not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError as exc:
                interrupted = exc
        if task is not None and not task.cancelled():
            task.exception()
        if interrupted is not None:
            raise interrupted

    @contextlib.asynccontextmanager
    async def _event_stamp_scope(self, session, *, single_event: bool, span=None):
        """One event already owns the transaction; only siblings need a savepoint.

        ``span`` (#10090 `StampSpans`) times the whole scope, its savepoint
        and any rollback included. Log only.
        """
        with span if span is not None else contextlib.nullcontext():
            if not single_event:
                async with session.begin_nested():
                    yield
                return
            try:
                yield
            except BaseException:
                # A lock timeout aborts PostgreSQL's transaction. Without the
                # redundant event SAVEPOINT, rollback the whole single-event
                # transaction before the caller handles/requeues the failure.
                await session.rollback()
                raise

    async def _refresh_batch(
        self,
        event_ids: list[int],
        now: float,
        *,
        prepared: Optional[dict[int, tuple]] = None,
        on_committed: Optional[Callable[[list[int]], None]] = None,
        publish_committed: Optional[Callable[[list[dict]], Awaitable[None]]] = None,
    ) -> None:
        from types import SimpleNamespace

        from sqlalchemy import update

        from app.models.models import Event
        from app.tasks.base import get_task_session
        from app.utils.aggregation import (
            compute_aggregate_probability,
            observation_basis,
            oldest_observation_time,
        )
        from app.utils.live_blend import compute_source_home_probability
        from app.utils.live_push import build_frame, build_source_snapshot
        from app.utils.repair_lock_budget import (
            RESET_STATEMENT_TIMEOUT_SQL, SET_LOCK_AND_STATEMENT_TIMEOUT_SQL,
            SET_LOCK_TIMEOUT_SQL, SET_STATEMENT_TIMEOUT_SQL, is_lock_timeout,
            is_query_canceled, lock_timeout_value,
        )

        # live/034 S1 — frames are COLLECTED here and published after the
        # session context exits cleanly, never inside the loop. Publishing
        # mid-transaction would broadcast a number that a later failure in the
        # same batch could roll back, and an un-take-back-able push of a value
        # the database never kept is worse than a push that never happened.
        pending: list[dict] = []
        # #10702: bind exact committed input marks to this reading's actual
        # contributor observations. Nothing is emitted before outer COMMIT.
        exact_trace = getattr(self.receipts, "exact_trace", None)
        trace_bases: dict = {}
        self._stage_trace("attempt_start", event_ids, now)
        # #837 tail (Codex review of #8490) — and for the same reason the
        # write bookkeeping is COLLECTED and applied only after the commit. A
        # released savepoint is not a committed stamp: recorded there, a failed
        # commit left `_should_write` believing the price was stored, so the
        # retry of a lock-deferred event skipped it as unchanged and the price
        # was lost for good.
        written: dict[int, float] = {}
        # #10090 (preview arm only): each canary event's RETURNING bag.
        committed_bags: dict[int, tuple] = {}
        # #10090: the chart points the committed stamps owe, in stamp order.
        owed_snapshots: list[tuple] = []

        # Stamp the throttle for EVERY event we are about to attempt, before any
        # of them can fail to resolve. Stamping per-resolved-event instead would
        # leave an event with no linked markets of this source permanently
        # "due", and every batch opens a session (and, outside a consumer
        # that lends its engine (#2471), a fresh engine and connection pool) —
        # so that event would query Postgres every 2-second flush, forever, to
        # discover the same nothing.
        for event_id in event_ids:
            # Never back in time: an older flush clock than the stamp already
            # recorded would let the caller-clock floor pass early (the current
            # clock's record is `_record_stamp_clock`, by every caller).
            last = self._last_refresh_at.get(event_id)
            self._last_refresh_at[event_id] = now if last is None else max(last, now)

        if self._session_factory is not None:
            get_task_session = self._session_factory  # #2471: the consumer's
        # #10090: a stage trace's selection receipts, only while one is
        # attached (None otherwise: no receipt work in this attempt). Every
        # PROPOSE selection still open when the attempt exits, by any route
        # (a lock-budget raise, a cancellation), is closed as unsent.
        select_open = self._stage_hook("selection_open")
        selections: Optional[dict[int, tuple]] = None if select_open is None else {}
        # #10090: this transaction's spans (`StampSpans`): slot to COMMIT, its
        # body's awaited spans, then the publication after it. Log only.
        tx = _StampTx(
            getattr(self, "stamp_spans", None), len(event_ids),
            getattr(self, "_session_slots", None),
        )
        async with (
            tx,
            self._normal_holds() as held,
            self._history_reservations(event_ids, now, owed_snapshots) as reservation,
            self._session_slot(), get_task_session() as session,
            self._selections_closer(selections),
            tx.body(),
        ):
            reserved, history_ready = reservation
            self._stage_trace("attempt_session", event_ids)
            if prepared is None:
                with tx.span("read"):
                    grouped = await self._read_groups(session, event_ids)
            else:
                grouped = {
                    eid: prepared[eid] for eid in event_ids if eid in prepared
                }
            for eid in event_ids:
                if eid in grouped and getattr(grouped[eid][0], "status", None) == "live":
                    self._live_event_ids.add(eid)
                else:
                    self._live_event_ids.discard(eid)
            if not grouped:
                self._stamp_wait_read(event_ids, {})
                if self.preview:
                    # #10090: this source spoke for none of these events, so
                    # none of its pending values may keep speaking.
                    with tx.span("publish"):
                        await self._publish_previews(self._preview_settlement(
                            event_ids, grouped, {}, set(), {},
                        ))
                return

            # #837 — ONE LOCK ORDER, ONE SAVEPOINT PER EVENT WITH SIBLINGS.
            # A single event owns its whole transaction, so its stamp scope
            # rolls back that transaction on failure instead of paying an
            # extra SAVEPOINT/RELEASE pair on every successful stamp.
            # This batch stamps
            # every event in a single transaction, and the sibling arm (the other
            # venue's consumer, same class, same column) does the same
            # concurrently. Walked in join order, two overlapping batches locked
            # the same `events` rows in opposite orders and Postgres killed one:
            # production 2026-09-24, 5 `deadlock detected` in 13 minutes on a
            # nine-game slate. And the per-event `except` below could not contain
            # it — a deadlock ABORTS the transaction, so every later UPDATE in the
            # batch failed ("current transaction is aborted") and the commit threw
            # away the stamps that had already succeeded: a whole batch of live
            # headlines silently held back until the next price. Ascending id in
            # BOTH arms removes the cycle between them; the savepoint confines any
            # other failure (a third writer, a bad row) to the one event it hit.
            #
            # #837 tail — and no event waits on a lock long enough to hold the
            # rest back (see `DEFAULT_STAMP_LOCK_TIMEOUT_MS`). Transaction-local,
            # set here rather than at session open so the joins above keep their
            # ordinary waits; a timed-out stamp rolls back only its savepoint.
            lock_budget_set = False
            lock_budget_failed = False
            # #11138: armed only at the stamp, so the cold orientation reads
            # keep the lock budget alone. Once armed it stays for the rest of
            # the transaction (one event in every production refresh).
            statement_bound_set = False

            async def ensure_lock_budget(*, whole_statement=False):
                nonlocal lock_budget_set, lock_budget_failed, statement_bound_set
                if not self.stamp_lock_timeout_ms or (
                    lock_budget_set
                    and (statement_bound_set or not whole_statement)
                ):
                    return
                if not whole_statement:
                    budget_sql = SET_LOCK_TIMEOUT_SQL
                elif lock_budget_set:
                    budget_sql = SET_STATEMENT_TIMEOUT_SQL
                else:
                    budget_sql = SET_LOCK_AND_STATEMENT_TIMEOUT_SQL
                try:
                    await session.execute(
                        budget_sql,
                        {"ms": lock_timeout_value(self.stamp_lock_timeout_ms)},
                    )
                except Exception:
                    # Budget setup used to fail outside the event loop. Keep
                    # its whole-batch rollback/requeue, never swallow it as a
                    # single failed event in an unbounded transaction.
                    lock_budget_failed = True
                    raise
                lock_budget_set = True
                statement_bound_set = statement_bound_set or whole_statement

            async def sibling_fallback():
                # #10090 (`admitted_stamp_batch`): a sibling's stamp may have
                # armed the whole-statement bound; the cold orientation reads
                # keep the lock budget alone (#11138), as in a one-event batch.
                nonlocal lock_budget_failed, statement_bound_set
                if statement_bound_set:
                    try:
                        await session.execute(RESET_STATEMENT_TIMEOUT_SQL)
                    except Exception:
                        lock_budget_failed = True
                        raise
                    statement_bound_set = False
                await ensure_lock_budget()

            # #10090 (preview arm only): canary readings awaiting their
            # UPDATE, the preview seq each published, and canary events whose
            # attempt failed.
            preview_plans: dict[int, tuple] = {}
            preview_only: set[int] = set()
            preview_seq: dict[int, int] = {}
            preview_failed: set[int] = set()
            # #10090: compute and publish eligible previews before any event's
            # UPDATE so one row-lock wait cannot hold back a sibling display.
            # Persistence retains the same sorted lock order (#837).
            ordered = sorted(grouped)
            preview_ids = [eid for eid in ordered if eid in self.preview_events]
            if preview_ids:
                work = ([("compute", eid) for eid in preview_ids] + [("preview", None)]
                        + [("stamp" if eid in self.preview_events else "both", eid)
                           for eid in ordered])
            else:
                work = [("both", eid) for eid in ordered]
            for phase, event_id in work:
                if phase == "preview":
                    with tx.span("publish"):
                        await self._preview_before_stamp(
                            grouped, preview_plans, preview_seq, observation_only=preview_only,
                            **({"selections": selections} if selections else {}),
                        )
                    continue
                if phase == "stamp" and (event_id not in preview_plans or event_id in preview_only):
                    continue
                event, group = grouped[event_id]
                try:
                    if phase == "stamp":
                        refused, proof_kwargs, reading, value, contributing = preview_plans[event_id]
                    else:
                        token = None if select_open is None else select_open(event_id)
                        route = "refresh" if phase == "compute" else "refresh_no_preview"
                        refused = []
                        proof_kwargs = self._current_reading_proof(event_id, group, refused)
                        reading = compute_source_home_probability(
                            group, event.home_team_name, event.away_team_name,
                            **proof_kwargs,
                        )
                        if reading is None:
                            self.stats["no_reading"] += 1
                            if refused:
                                self.stats["bundled_refused"] += 1
                            self._dispositions[event_id] = ("no_reading",)
                            if token is not None:
                                self._trace_selection(
                                    None, event_id, token,
                                    "refusal" if refused else "no_reading", route=route,
                                    reason="current_book_refused" if refused else None,
                                )
                            continue

                        with tx.span("read"):
                            home_prob = await self._oriented(
                                session, event_id, reading.home_probability, reading=reading,
                                **({"before_fallback": ensure_lock_budget} if len(grouped) == 1
                                   else {"before_fallback": sibling_fallback,
                                         "fallback_scope": session.begin_nested}),
                            )
                        value = round(home_prob, 4)

                        # #5661 — before the throttle decides WHEN to re-stamp, ask
                        # WHETHER there is anything to re-stamp. The row's own
                        # stored entry is the reference (not this process's memory,
                        # which a dyno restart empties), and the reading's rows are
                        # the ones the number came from, as the 120s poll dates it.
                        contributing = (
                            getattr(reading, "contributing_outcomes", None)
                            or (getattr(reading, "outcome", None),)
                        )
                        if restamp_records_no_observation(
                            value,
                            oldest_observation_time(contributing),
                            getattr(event, "win_probability_sources", None),
                            self.source,
                        ):
                            self.stats["unobserved_skipped"] += 1
                            self._dispositions[event_id] = ("unobserved", value)
                            self._note_confirm_basis(
                                event_id, contributing, stored_row=event, value=value)
                            self._settle_trail(event_id, group, stored_row=event, value=value)
                            if phase == "compute":
                                # A periodic durable read can predate an already
                                # accepted observation preview. Let its registry
                                # judge that basis without requesting persistence.
                                preview_plans[event_id] = (
                                    refused, proof_kwargs, reading, value, contributing,
                                )
                                preview_only.add(event_id)
                            if token is not None:
                                self._trace_selection(
                                    selections, event_id, token, "unobserved", route=route,
                                    reading=reading, value=value, contributing=contributing,
                                    then="PROPOSE" if phase == "compute" else "NONE",
                                )
                            continue

                        if not self._should_write(event_id, value, now):
                            self.stats["unchanged_skipped"] += 1
                            self._dispositions[event_id] = ("unchanged", value)
                            self._note_confirm_basis(
                                event_id, contributing, stored_row=event, value=value)
                            self._settle_trail(event_id, group, stored_row=event, value=value)
                            # Persistence cadence does not own display admission.
                            # Only a complete contributing observation can try
                            # this route; the registry proves it newer than the
                            # stored reading and its pending observation. There
                            # is no event UPDATE or lock/retry debt for this arm.
                            if phase == "compute" and observation_basis(contributing):
                                preview_plans[event_id] = (
                                    refused, proof_kwargs, reading, value, contributing,
                                )
                                preview_only.add(event_id)
                                self._dispositions[event_id] = ("preview_only", value)
                            if token is not None:
                                self._trace_selection(
                                    selections, event_id, token,
                                    self._dispositions[event_id][0], route=route,
                                    reading=reading, value=value, contributing=contributing,
                                    then=("PROPOSE" if self._dispositions[event_id][0]
                                          == "preview_only" else "NONE"),
                                )
                            continue

                        if phase == "compute":
                            preview_plans[event_id] = (
                                refused, proof_kwargs, reading, value, contributing,
                            )
                            if token is not None:
                                self._trace_selection(
                                    selections, event_id, token, "proposal", route=route,
                                    reading=reading, value=value, contributing=contributing,
                                    then="PROPOSE",
                                )
                            continue
                        if token is not None:
                            self._trace_selection(
                                None, event_id, token, "stamp", route=route,
                                reading=reading, value=value, contributing=contributing,
                                then="PERSIST",
                            )

                    # The database assigns the write clock; RETURNING below
                    # supplies that exact clock to the frame and tail receipt.
                    # A Python timestamp taken before the awaited UPDATE could
                    # precede a sibling's stamp despite committing after it.
                    # Core update, never ORM attribute assignment (gotcha #4),
                    # and a server-side merge rather than a read-modify-write:
                    # the sibling arm streaming the OTHER venue writes this same
                    # column concurrently (see `atomic_stamp_expression`).
                    #
                    # RETURNING is load-bearing, not a convenience. The frame
                    # below must carry the aggregate of what the database KEPT,
                    # including whatever the sibling arm committed a moment ago.
                    # Publishing the aggregate of this arm's own private copy is
                    # the second half of live/305's flicker: the row would be
                    # right and the wire still wrong.
                    #
                    # #8910: and the stamp is CONDITIONAL on no other writer
                    # having stored a later observation of these rows — every
                    # stamp, moved or re-stamped. See `observation_admits_clause`
                    # for why the condition lives in this UPDATE.
                    basis = observation_basis(contributing)
                    admits = observation_admits_clause(self.source, basis)
                    # Known-orientation readings that were refused above need
                    # no SET command. Every actual stamp still installs the
                    # same budget before its savepoint and row UPDATE, and
                    # (#11138) bounds that UPDATE as a whole statement.
                    with tx.span("write"):
                        await ensure_lock_budget(whole_statement=True)
                    async with self._event_stamp_scope(
                        session, single_event=len(grouped) == 1, span=tx.span("write"),
                    ):
                        if proof_kwargs:
                            checked = compute_source_home_probability(
                                group, event.home_team_name, event.away_team_name, **proof_kwargs,
                            )
                            if (checked is None or checked.home_probability != reading.home_probability
                                    or checked.contributing_outcomes != reading.contributing_outcomes):
                                self.stats["no_reading"] += 1
                                self._dispositions[event_id] = ("no_reading",)
                                continue
                        # `synchronize_session=False`: the ORM cannot evaluate
                        # the guard's SQL in Python, and its "fetch" fallback
                        # rewrites RETURNING to the primary key — the frame
                        # would then be built from an event id, not the blend.
                        stamp = (
                            update(Event)
                            .where(Event.id == event_id)
                            .execution_options(synchronize_session=False)
                        )
                        if admits is not None:
                            stamp = stamp.where(admits)
                        # #9051: the row's revision rides the same RETURNING,
                        # so the frame names exactly the write it reports.
                        stamp = stamp.values(
                            win_probability_sources=atomic_stamp_expression(
                                self.source,
                                value,
                                eligibility=reading.eligibility,
                                observed_basis=basis,
                            )
                        ).returning(
                            Event.win_probability_sources,
                            Event.win_probability_sources_rev,
                        )
                        fused_intent = stamp_fuses_intent()
                        if fused_intent:
                            stamp = stamp_with_publication_intent(
                                stamp, source=self.source,
                                intent_source=self._normal_source,
                                event_id=event_id, value=value,
                            )
                        stamped_row = (await session.execute(stamp)).first()
                        new_sources, new_rev = (
                            (None, None) if stamped_row is None else stamped_row
                        )
                        if new_sources is None and admits is not None:
                            # Refused: the poll or the matcher stored a later
                            # observation of these rows since this batch read
                            # them. No chart point, no frame, and NOT recorded
                            # as written, so the next flush reads again rather
                            # than taking this value as already stored. (A row
                            # deleted mid-batch lands here too; skipping it is
                            # right either way.)
                            self.stats["stale_readings_refused"] += 1
                            self._dispositions[event_id] = ("stale", value)
                            continue
                        if new_sources is None:
                            # The UPDATE matched nothing, so there is no stored blend
                            # to publish an aggregate of. Reachable only if the row
                            # went away between the join above and here; `_or_none`
                            # rather than `scalar_one` because that is a benign race
                            # to skip, not a traceback to log on the dyno whose job
                            # is streaming prices.
                            self.stats["no_reading"] += 1
                            self._dispositions[event_id] = ("no_row",)
                            continue

                        stamped_at = new_sources[self.source]["updated_at"]
                        # Intent and source revision COMMIT together. A crash
                        # before publication cannot erase the last recovery duty.
                        # Same revision rule as `build_frame`: a writer with no
                        # integer revision makes no claim, so it owes no intent
                        # and its stamp is not refused for lacking one.
                        # With `fused_intent` the stamping statement already
                        # wrote it, under the same condition.
                        if (not fused_intent and isinstance(new_rev, int)
                                and not isinstance(new_rev, bool)):
                            from sqlalchemy import insert
                            from app.models.models import OwedChartPoint
                            await session.execute(insert(OwedChartPoint).values(
                                source=self._normal_source, event_id=event_id,
                                value=value, reading={"rev": new_rev,
                                                      "updated_at": stamped_at},
                            ))
                        # Scalar extraction is still inside the event scope:
                        # if it fails, this stamp cannot commit without its
                        # due chart obligation.
                        chart_reading = (
                            _chart_reading(reading, stamped_at)
                            if event_id in reserved else None
                        )
                        # #11181: the owed point's durable row, in this same
                        # scope. A stamp commits only with it; an INSERT into a
                        # table with no foreign key takes no row lock to wait on.
                        if chart_reading is not None and self._chart_custody is not None:
                            chart_reading = _replace(
                                chart_reading,
                                custody_id=await self._chart_custody.record(
                                    session, self.source, event_id, value,
                                    chart_reading,
                                ),
                            )

                    # Noted only once the stamp scope has succeeded (a stamp
                    # that rolled back must not read as written), and applied only
                    # once the transaction commits — see `written` above.
                    written[event_id] = value
                    if event_id in self.preview_events:
                        committed_bags[event_id] = (new_sources, new_rev, event)

                    # #10090: the chart point is written AFTER this commit and
                    # its publication (`_write_owed_snapshots`), never inside the
                    # stamp's transaction, so chart SQL no longer delays the
                    # stamp's COMMIT or extends its event-row lock. Observed, not
                    # attributed: production 2026-10-11 00:52:30Z (BOS–PHI
                    # 15323924) one frame arrived ~3.0 s after its stamp against
                    # 0.05–0.19 s for its neighbours; no worker/history/lock
                    # receipt ties that interval to a chart write.
                    # Most changed quotes arrive before the chart clock is due;
                    # those owe nothing and open no second session.
                    if chart_reading is not None:
                        owed_snapshots.append((event_id, value, chart_reading))
                    if exact_trace is not None:
                        with contextlib.suppress(Exception):
                            if exact_trace.tracks_event(event_id):
                                trace_bases[event_id] = (basis, new_rev, stamped_at)
                    # #837 receipt — trusted only after the commit;
                    # `previous` says whether it MOVED.
                    self._dispositions[event_id] = (
                        "stamped", value, stamped_at,
                        self._last_written_value.get(event_id),
                        # #10090 delivery receipt: the revision the frame
                        # publishes, and whether the game is live.
                        new_rev, event.status,
                    )
                    self._note_confirm_basis(event_id, contributing)

                    # The AGGREGATE, computed off the sources JSONB the server
                    # RETURNED — the number the hero renders, not this one
                    # source's price ("the blend is the product"). The shim
                    # carries that post-write JSONB with the event's own
                    # fallback fields; `compute_aggregate_probability` reads
                    # all of them through `getattr`, so a namespace is a
                    # faithful stand-in for the row without re-reading it.
                    #
                    # `new_sources` is the database's copy, so it already
                    # contains the sibling arm's latest reading. That is what
                    # makes two frames published 89 ms apart agree.
                    #
                    # Attributes are pulled off the ORM object HERE, inside the
                    # session — after it closes they are expired and touching
                    # one would emit a lazy load against a dead session
                    # (gotcha #6).
                    shim = SimpleNamespace(
                        win_probability_sources=new_sources,
                        status=event.status,
                        espn_win_prob_home=getattr(
                            event, "espn_win_prob_home", None
                        ),
                        opening_home_probability=(
                            event.opening_home_probability
                        ),
                    )
                    frame = build_frame(
                        event_id=event_id,
                        probability=compute_aggregate_probability(
                            shim, event.status,
                        ),
                        source=self.source,
                        source_value=value,
                        updated_at=stamped_at,
                        status=event.status,
                        rev=new_rev,
                    )
                    # #10090: the row's complete public sources, from the same
                    # RETURNING bag and revision as `p`. No query. Published
                    # with the frame after COMMIT, or not at all.
                    note_frame = getattr(
                        getattr(self, "receipts", None), "note_stamp_frame", None,
                    )
                    if note_frame is not None:
                        # #10090: the value this stamp's frame shows readers.
                        self._receipt_call(
                            note_frame, event_id, new_rev, frame["p"], event.status,
                        )
                    snapshot = build_source_snapshot(
                        event_id, frame["rev"], new_sources,
                    )
                    if snapshot is None:
                        self.stats["source_snapshot_omitted"] += 1
                    else:
                        frame["source_snapshot"] = snapshot
                    pending.append(frame)
                    # Held before COMMIT: no recovery read can see this
                    # intent before this process has claimed its publication.
                    held |= self._normal_revisions([frame])
                    self._normal_inflight |= held
                except Exception as exc:
                    if lock_budget_failed:
                        raise
                    # #11138: a cancel after the stamp armed its statement
                    # bound is that bound — the row wait ran past its budget.
                    statement_bound = (
                        statement_bound_set and is_query_canceled(exc)
                    )
                    if is_lock_timeout(exc) or statement_bound:
                        # Another transaction holds this row. Its price is
                        # already stored; stamp it on the next flush, due at
                        # once, instead of freezing every other event's stamp
                        # behind a lock this arm does not control.
                        self.stats["lock_skipped"] += 1
                        self._dispositions[event_id] = ("lock",)
                        self._lock_retry.add(event_id)
                        self._last_refresh_at.pop(event_id, None)
                        self._schedule_lock_prompt(event_id)
                        logger.info(
                            "live_blend_refresh[%s]: event %s row locked >%sms, "
                            "re-queued for the next flush%s",
                            self.source,
                            event_id,
                            self.stamp_lock_timeout_ms,
                            " (statement bound)" if statement_bound else "",
                        )
                        continue
                    self.stats["errors"] += 1
                    if event_id in self.preview_events:
                        preview_failed.add(event_id)
                    # A committed stamp whose frame failed is still stamped.
                    self._dispositions.setdefault(event_id, ("error",))
                    self._note_confirm_unpublishable(event_id)
                    logger.exception(
                        "live_blend_refresh[%s]: event %s failed",
                        self.source, event_id,
                    )

        # Session closed and committed — only now is the pushed number a number
        # the database actually kept, and only now is it "written".
        self._stage_trace("attempt_committed", event_ids, self._dispositions)
        # Note raw non-stamp read outcomes before receipt resolution.
        # A committed write may leave this input uncovered; _resolve_receipt_wait
        # closes STAMPED only after the receipt actually covers that input.
        self._stamp_wait_read(event_ids, {
            eid: self._dispositions.get(eid, ("error",))
            for eid in event_ids if eid in grouped
        })
        for event_id, value in written.items():
            self._last_write_at[event_id] = now
            self._last_written_value[event_id] = value
        self.stats["stamped"] += len(written)
        for event_id, (new_sources, new_rev, _event) in committed_bags.items():
            self._preview_graph_committed(event_id, new_sources, new_rev)
        if exact_trace is not None:
            for event_id, (basis, revision, stamped_at) in trace_bases.items():
                with contextlib.suppress(Exception):
                    exact_trace.stamp(event_id, basis, revision, stamped_at)
        try:
            if on_committed is not None:
                on_committed(event_ids)
            if publish_committed is None:
                # Ordered with the running quote call's admitted frames.
                window = self._admission
                publish_committed = (
                    self._publish_prices if window is None else window.publish_inline
                )
            settled = []
            # Over every ATTEMPTED canary event, not only those in `grouped`:
            # a canary whose group left beside a non-canary sibling still owes
            # its `no_group` revoke (R3).
            if not self.preview_events.isdisjoint(event_ids):
                # Only canary frames depend on preview recomposition. Release
                # independent committed events through the existing sender
                # before optional ledger/publication I/O can hold them up.
                independent = [
                    frame for frame in pending
                    if frame["event_id"] not in self.preview_events
                ]
                pending = [
                    frame for frame in pending
                    if frame["event_id"] in self.preview_events
                ]
                if independent:
                    await publish_committed(independent)
                # After COMMIT, BEFORE the committed canary frames: a sibling still
                # pending is recomposed on the new base and goes out first, so
                # the committed frame (rev == that base) cannot briefly put the
                # sibling's older stored value back on the page. Revokes go
                # after it, so a retired preview gives way to the commit that
                # carries it, never to the older committed value. A
                # lock-deferred event keeps its preview.
                settled = self._preview_settlement(
                    event_ids, grouped, preview_seq, preview_failed, committed_bags,
                )
                settled = await self._prepare_ledger_previews(settled)
                await self._publish_previews(
                    [f for f in settled if f["preview"]["kind"] == "blend"]
                )
            await publish_committed(pending)
            if settled:
                await self._publish_previews(
                    [f for f in settled if f["preview"]["kind"] != "blend"]
                )
        except BaseException:
            # Frames that never reached `_publish_prices` release here; an
            # early release costs at most one redundant control, a lost one
            # would hide the intent from discovery for this process's life.
            self._release_normal(held)
            raise
        finally:
            # The debt was registered immediately after COMMIT, before the
            # first publication await. Cancellation cannot strand it.
            history_ready.set()
            self._start_history()
            tx.published()  # #10090 `StampSpans`: COMMIT to here is `publish`

    async def _write_owed_snapshots(
        self, owed: list[tuple], now: float, get_task_session,
        *, verify_event: bool = False,
    ) -> bool:
        """#10090 — report whether the owed points' transaction committed.

        Runs after the stamps COMMITTED and their frames were published (inline)
        or submitted to the ordered sender (grouped), in its own short
        transaction, so neither the stamp's COMMIT nor its hold on the event row
        waits on `win_prob_snapshots`. The run's single history owner awaits
        it, independently of the quote owner. A stamp that never commits owes
        no point and takes no slot, so its retry still draws one. Each point keeps its own savepoint, and its ORM writes are flushed
        inside it: one that cannot be written costs only itself, never another
        point and never the number already published.

        The stamp's lock budget is transaction-local and expired at its COMMIT,
        and the consumer sessions carry none of their own, so this transaction
        installs the same budget before any chart SQL. Without it a chart
        UPDATE queued behind another holder of the latest snapshot row waits
        out the resting statement timeout while the history slot stays taken. `stamp_lock_timeout_ms` falsy keeps it off, as
        it does for the stamp.

        `verify_event` (a retry of a point that already failed once): a point
        whose event row is gone is retired with its custody row instead of
        written, so a deleted event does not owe a chart write forever. The
        check runs after the settle, inside the point's savepoint; a lookup
        error or a failed COMMIT keeps the debt, as for any failed point.
        """
        from app.utils.repair_lock_budget import (
            SET_LOCK_TIMEOUT_SQL, lock_timeout_value,
        )

        counts = {
            key: self.stats[key]
            for key in ("snapshots_written", "snapshots_deduped", "history_event_gone")
        }
        try:
            async with (
                self._snapshot_slots_follow_the_commit(
                    [event_id for event_id, _, _ in owed]
                ),
                self._session_slot(),
                get_task_session() as session,
            ):
                if self.stamp_lock_timeout_ms:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(self.stamp_lock_timeout_ms)},
                    )
                for event_id, value, reading in owed:
                    async with session.begin_nested():
                        # #11181: settle first, in the point's own savepoint: a
                        # point that fails restores its row, and a row already
                        # gone was paid once and is not written again.
                        custody_id = getattr(reading, "custody_id", None)
                        if custody_id is not None and self._chart_custody is not None:
                            if not await self._chart_custody.settle(session, custody_id):
                                self.stats["history_already_paid"] += 1
                                continue
                        if verify_event:
                            from sqlalchemy import select

                            from app.models.models import Event

                            if (await session.execute(
                                select(Event.id).where(Event.id == event_id)
                            )).first() is None:
                                # The stamp committed against a row that has since
                                # been deleted, and ids are never reused: nothing is
                                # owed. The settle above commits with this savepoint.
                                self.stats["history_event_gone"] += 1
                                logger.warning(
                                    "live_blend_refresh[%s]: owed chart point retired, event %s gone",
                                    self.source, event_id,
                                )
                                continue
                        await self._maybe_snapshot(session, event_id, value, reading, now)
                        await session.flush()
            return True
        except BaseException as exc:
            for key, count in counts.items():
                self.stats[key] = count
            if isinstance(exc, asyncio.CancelledError):
                raise
            self.stats["errors"] += 1
            logger.exception(
                "live_blend_refresh[%s]: committed chart point remains owed",
                self.source,
            )
            return False

    @contextlib.asynccontextmanager
    async def _snapshot_slots_follow_the_commit(self, event_ids: list[int]):
        """Undo these chart points' throttle slots if their transaction does
        not commit.

        `_maybe_snapshot` takes its tentative slot BEFORE writing. An owned
        point that fails retains its separate reservation and retry hold; its
        successful-write slot must roll back with the transaction. Otherwise
        a retry would skip the immutable observation it still owes. Entered before the session
        and exited after it, so a failing or cancelled COMMIT reaches it.
        """
        prior = {eid: self._last_snapshot_at.get(eid) for eid in event_ids}
        try:
            yield
        except BaseException:
            for event_id, at in prior.items():
                if at is None:
                    self._last_snapshot_at.pop(event_id, None)
                else:
                    self._last_snapshot_at[event_id] = at
            raise

    def _client(self):
        """The one async Redis client this refresher publishes on, built lazily.

        Both publishers (event frames and #9484 market invalidations) take it
        from here, so a consumer holds one pool, not one per publisher — the
        #6515 census counts this as one construction site.
        """
        if self._redis is None:
            from app.tasks.redis_state import get_async_redis_client

            self._redis = get_async_redis_client()
        return self._redis

    async def publish_market_changes(self, session) -> int:
        """#9484: drain the market invalidations ``session`` staged and committed.

        Call AFTER the writer's ``get_task_session()`` block has exited, so only
        an outer commit that landed can publish (`market_quote_push` holds the
        rows until its after-commit hook moves them). It shares ``self._redis``
        with the event frames: one client per consumer, never one per flush,
        and it does not wait on ``refresh()`` — a standalone future has no
        event blend to stamp, and its quote is just as real. Never raises.
        """
        from app.utils.market_quote_push import take_committed_market_changes

        try:
            changes = take_committed_market_changes(session)
        except Exception:
            self.stats["market_publish_errors"] += 1
            logger.warning("live_blend_refresh[%s]: market detachment failed", self.source, exc_info=True)
            return 0
        return await self.publish_market_frames(changes)

    async def publish_market_frames(self, changes: list[dict]) -> int:
        """Publish already detached committed market invalidations."""
        from app.utils.market_quote_push import publish_market_changes

        try:
            sent = await publish_market_changes(changes, self._client())
        except Exception:
            self.stats["market_publish_errors"] += 1
            self._redis = None
            logger.warning(
                "live_blend_refresh[%s]: market publication failed",
                self.source, exc_info=True,
            )
            return 0
        self.stats["market_published"] += sent
        return sent

    async def _settle_normal_recovery(self, acknowledged):
        from sqlalchemy import text
        from app.tasks.base import get_task_session
        if not acknowledged:
            return
        if self._session_slots.locked() or self._optional_db_busy():
            # Never queue behind a stamp for a slot: the next opportunity
            # settles these. Checked with no await before the acquisition.
            self._remember_normal_acks(acknowledged)
            return
        factory = self._session_factory or get_task_session
        gate = _CapacityReadGate()

        async def settle():
            async with self._session_slot():
                gate.reading = True
                async with factory() as session:
                    # One roundtrip for the cohort: per-event DELETEs could spend
                    # the whole budget and roll back every already-paid intent,
                    # causing needless reader reconciliation on the next sweep.
                    event_ids, revisions = zip(*acknowledged)
                    await session.execute(text(
                        "DELETE FROM owed_chart_points AS owed USING "
                        "unnest(CAST(:event_ids AS integer[]), "
                        "CAST(:revisions AS bigint[])) AS ack(event_id, revision) "
                        "WHERE owed.source=:source AND owed.event_id=ack.event_id "
                        "AND (owed.reading->>'rev')::bigint<=ack.revision"
                    ), {"source": self._normal_source,
                        "event_ids": list(event_ids), "revisions": list(revisions)})

        # Settling an older ACK cannot erase a newer committed intent, so an
        # abandoned settlement that commits late settles the same rows.
        await self._optional_db("normal_ack", .25, settle,
                                _optional_db_key(event_id for event_id, _ in acknowledged),
                                gate=gate)

    def _note_normal_debt(self):
        self._normal_has_debt = True
        self._normal_epoch += 1

    @staticmethod
    def _normal_revisions(frames):
        # Exactly the revisions `_publish` can acknowledge: an int at the
        # frame's own event key. A revision-less frame owes no intent.
        return {
            (f["event_id"], f["rev"][str(f["event_id"])]) for f in frames
            if isinstance(f.get("rev"), dict)
            and type(f["rev"].get(str(f["event_id"]))) is int
        }

    def _release_normal(self, held):
        self._normal_inflight.difference_update(held)

    @contextlib.asynccontextmanager
    async def _normal_holds(self):
        """The stamp transaction's held intent revisions.

        A failed transaction releases them: its intents never committed, and
        a stale hold would hide an older owed revision of the same game from
        discovery.
        """
        held = set()
        try:
            yield held
        except BaseException:
            self._release_normal(held)
            raise

    def _publish_prices_task(self, frames):
        """`_publish_prices` as its own task. A task cancelled before its
        first step never runs the coroutine's release, so the task's
        completion releases too (a second release is a no-op)."""
        task = asyncio.create_task(self._publish_prices(frames))
        held = self._normal_revisions(frames)
        task.add_done_callback(lambda _task: self._release_normal(held))
        return task

    def _remember_normal_acks(self, acknowledged):
        for eid, rev in acknowledged:
            if rev > self._normal_acked.get(eid, -1):
                self._normal_acked[eid] = rev

    async def _publish_prices(self, frames):
        """Publish committed price frames; remember what Redis acknowledged.

        No database work here. Settling an intent needs a session, and the
        publication lock orders the next cohort's frames behind this call:
        a DELETE awaited here held the next game's price behind the
        database (and one of the three stamp slots) on every publication.
        The next recovery opportunity settles the remembered revisions; a
        lost process leaves only intents whose recovery is price-free.

        Every publication is also a recovery opportunity, started here and
        awaited by nothing. A busy timed flush always has a price batch, so
        it never reaches `refresh_pending`; without this a failed game that
        went quiet waited for a fully empty flush.
        """
        expected = self._normal_revisions(frames)
        try:
            acknowledged = await self._publish(frames) or set()
        except BaseException as exc:
            self._release_normal(expected)
            self._note_normal_debt()
            self._note_confirm_published((), expected)
            if not isinstance(exc, Exception):
                raise
            logger.exception("live_blend_refresh[%s]: normal publication retained", self.source)
            self._start_normal_recovery()
            return set()
        if expected - acknowledged:
            self._note_normal_debt()
        self._note_confirm_published(expected & acknowledged, expected - acknowledged)
        # Resolved: acknowledged revisions are now in `_normal_acked`, the rest
        # are owed to the next opportunity.
        self._remember_normal_acks(acknowledged)
        self._release_normal(expected)
        self._start_normal_recovery()
        return acknowledged

    def _start_normal_recovery(self):
        task = self._normal_task
        if task is not None and not task.done():
            return
        if task is not None and not task.cancelled():
            task.exception()
        # Another owner may finish an already-started COMMIT after our empty
        # startup scan. Keep a bounded discovery opportunity on the existing
        # flush loop even when this instance has not recorded a failure.
        if self._normal_closed or _mono() < self._normal_retry_at:
            return
        self._normal_task = asyncio.create_task(self._recover_normal_prices())

    async def _recover_normal_prices(self):
        from sqlalchemy import text
        from app.tasks.base import get_task_session
        factory = self._session_factory or get_task_session
        try:
            # Recovery never queues for a stamp's slot: with all three taken,
            # this opportunity passes and the next one (after the cooldown)
            # tries again. Each of its three acquisitions checks this with no
            # await between the check and the acquisition.
            if self._session_slots.locked() or self._optional_db_busy():
                return
            acked, self._normal_acked = self._normal_acked, {}
            if acked:
                try:
                    await self._settle_normal_recovery(set(acked.items()))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Dropped, not restored: the durable rows remain, so the
                    # discovery below republishes their price-free control
                    # and its acknowledgement settles them.
                    logger.exception(
                        "live_blend_refresh[%s]: normal ACK settlement retained",
                        self.source,
                    )
            if self._session_slots.locked() or self._optional_db_busy():
                return
            epoch = self._normal_epoch
            # Freeze a finite sweep: new arrivals cannot indefinitely postpone
            # retrying an older failed event. Both reads use (source, id); bound
            # raw rows BEFORE coalescing so duplicate revisions cannot turn a
            # LIMIT32 result into an unbounded DISTINCT/sort over the backlog.
            gate = _CapacityReadGate()

            async def read_page():
                async with self._session_slot():
                    gate.reading = True
                    async with factory() as session:
                        if self._normal_horizon is None:
                            self._normal_horizon = (await session.execute(text(
                                "SELECT id FROM owed_chart_points WHERE source=:source "
                                "ORDER BY id DESC LIMIT 1"
                            ), {"source": self._normal_source})).scalar_one_or_none()
                            if self._normal_horizon is None:
                                if epoch == self._normal_epoch:
                                    self._normal_has_debt = False
                                return None
                        return (await session.execute(text(
                            "SELECT id, event_id, reading FROM owed_chart_points "
                            "WHERE source=:source AND id>:after AND id<=:horizon "
                            "ORDER BY id LIMIT 32"
                        ), {"source": self._normal_source, "after": self._normal_after,
                            "horizon": self._normal_horizon})).all()

            rows = await self._optional_db("normal_read", .25, read_page, gate=gate)
            if rows is None:
                return
            if not rows:
                self._normal_after = 0
                self._normal_horizon = None
                return
            self._normal_after = rows[-1].id
            if len(rows) < 32 or self._normal_after >= self._normal_horizon:
                self._normal_after = 0
                self._normal_horizon = None
            # These are price-free minimum-revision requests, not historical
            # prices. The reader fetches current authoritative state even when
            # a newer revision exists outside this bounded page. Keep the
            # highest revision per event within this page; never drop its debt
            # until publication is positively acknowledged.
            latest = {}
            for row in rows:
                prior = latest.get(row.event_id)
                if prior is None or row.reading["rev"] > prior.reading["rev"]:
                    latest[row.event_id] = row
            # A revision this process still owns belongs to its own publication:
            # in flight, or acknowledged after the swap above and settled by the
            # next opportunity. A control for it would cost every open reader
            # of a busy game a paired read. A lost process owns nothing, so a
            # fresh owner still republishes every intent.
            owned = dict(self._normal_acked)
            for eid, rev in self._normal_inflight:
                if rev > owned.get(eid, -1):
                    owned[eid] = rev
            rows = [
                row for row in latest.values()
                if row.reading["rev"] > owned.get(row.event_id, -1)
            ]
            frames = []
            for _cid, eid, reading in rows:
                rev = {str(eid): reading["rev"]}
                frames.append({
                    "event_id": eid, "p": None, "rev": rev,
                    "updated_at": reading["updated_at"], "reconcile_only": True,
                    "reconcile": {"event_id": eid,
                        "custody_id": f"normal-price:{eid}:{reading['rev']}",
                        "removal_rev": rev},
                })
            # No database session or event lock spans Redis publication.
            async with asyncio.timeout(.25):
                acknowledged = await self._publish(frames) if frames else set()
            await self._settle_normal_recovery(acknowledged)
        except Exception:
            logger.exception("live_blend_refresh[%s]: durable normal recovery retained", self.source)
        finally:
            self._normal_retry_at = _mono() + .5

    async def _close_normal_recovery(self):
        self._normal_closed = True
        task = self._normal_task
        if task is None:
            return
        if not task.done():
            task.cancel()
        interrupted = None
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError as exc:
                interrupted = exc
        if not task.cancelled():
            task.exception()
        self._normal_task = None
        if interrupted is not None:
            raise interrupted

    # ── #10090: optional reads abandoned at their deadline ───────────────────

    def _optional_db_busy(self) -> bool:
        """Abandoned optional work already holds its share of the slots; skip this turn."""
        held = sum(not task.done() for task in self._optional_db_running.values())
        if optional_db_abandons() or _optional_db_trial().state(OPTIONAL_DB_SWITCH).mode != "off":
            # The detached observation reads (#11700) share the same slots.
            held += sum(not task.done() for task in self._detached_reads)
        return held >= OPTIONAL_DB_HELD_MAX

    def _trial_attempt_failed(self, flush_started, error: BaseException) -> None:
        """An old stamp only a `pending_attempts` trial allowed has failed: that
        trial switches off in this process (automatic switch-back on error), and
        this flush attempts no more than the setting allows from here."""
        if (flush_started is not None and self._pending_fresh_flush
                and self._pending_attempts_limit != FRESH_FLUSH_PENDING_ATTEMPTS
                and self._pending_attempts > FRESH_FLUSH_PENDING_ATTEMPTS):
            self._pending_attempts_limit = FRESH_FLUSH_PENDING_ATTEMPTS
            _optional_db_trial().trip(PENDING_ATTEMPTS_SWITCH, error)

    @staticmethod
    def _optional_db_on(key: Optional[int]) -> bool:
        """The env switch, or the running trial's arm for the read keyed ``key``."""
        if optional_db_abandons():
            return True
        trial = _optional_db_trial()
        if trial.state(OPTIONAL_DB_SWITCH).mode == "alternate":
            return trial.arm(OPTIONAL_DB_SWITCH, 0)  # the period's arm, every read
        return key is not None and trial.arm(OPTIONAL_DB_SWITCH, key)

    async def _optional_db(self, kind: str, budget_s: float, body, key: Optional[int] = None,
                           gate=None):
        """Await ``body()`` for at most ``budget_s``; TimeoutError past it.

        Off (the default), exactly ``asyncio.timeout(budget_s)`` around the
        body. On (`OPTIONAL_DB_ABANDON_ENV`), the body runs on its own task and
        is never cancelled for the deadline: the caller is released with the
        same TimeoutError and the body finishes, keeping its connection. A
        cancellation of the CALLER still cancels the body and waits for it, as
        the timeout's own cancellation did. With a ``gate``, a body that has not
        set ``gate.reading`` (still queued for its session slot) is cancelled at
        the deadline, as with the switch off: it holds no connection to keep.
        """
        if not self._optional_db_on(key):
            async with asyncio.timeout(budget_s):
                return await body()
        if self._optional_db_busy():
            raise TimeoutError(f"optional {kind} read skipped: abandoned reads hold their share")
        task = asyncio.create_task(body(), name=f"optional-db:{kind}")
        try:
            # The same deadline scope as off; only the read behind it is shielded.
            async with asyncio.timeout(budget_s):
                return await asyncio.shield(task)
        except TimeoutError:
            if task.done():
                # The read's own TimeoutError, or one that ended at the deadline.
                if not task.cancelled():
                    task.exception()
                raise
            if self._optional_db_busy() or (gate is not None and not gate.reading):
                # Another read took the share meanwhile, or this one is still
                # queued for its slot: cancel, as with the switch off.
                await self._optional_db_cancel_and_join(task, TimeoutError())
                raise
            self._optional_db_abandon(kind, task, OPTIONAL_DB_ABANDON_LIMIT_S - budget_s)
            raise OptionalDbAbandoned(f"optional {kind} read abandoned after {budget_s}s")
        except BaseException as exc:
            await self._optional_db_cancel_and_join(task, exc)
            raise

    async def _optional_db_in_pass(self, kind: str, body, key: Optional[int] = None):
        """Await ``body(gate)`` under the enclosing pass's own deadline.

        For preview capacity maintenance, whose reads sit inside its 1 s pass
        timeout. Off, exactly ``await body(None)``. On, the body runs on its own
        task behind a shield: when the pass deadline cancels the caller while
        the body is inside its read (``gate.reading``), the caller ends exactly
        as before and the read is left to finish, then stop at
        ``gate.read_done()``. A cancellation anywhere else, or at shutdown,
        still cancels the body and waits for it.
        """
        if not self._optional_db_on(key):
            return await body(None)
        if self._optional_db_busy():
            raise TimeoutError(f"optional {kind} read skipped: abandoned reads hold their share")
        gate = _CapacityReadGate()
        task = asyncio.create_task(body(gate), name=f"optional-db:{kind}")
        try:
            return await asyncio.shield(task)
        except CancelledError as exc:
            if (gate.reading and not task.done() and not self._preview_maintenance_closed
                    and not self._optional_db_busy()):
                gate.abandoned = True
                self._optional_db_abandon(kind, task, OPTIONAL_DB_ABANDON_LIMIT_S)
                raise
            await self._optional_db_cancel_and_join(task, exc)
            raise

    @staticmethod
    async def _optional_db_cancel_and_join(task: asyncio.Task, exc: BaseException) -> None:
        """Cancel the body as the caller was cancelled, and wait for it.

        Every cancellation the caller receives while waiting (a shutdown, then
        the pass timeout) is forwarded with its message, so the body unwinds
        exactly as it did when it was the caller's own coroutine.
        """
        cancel = (lambda e: task.cancel(e.args[0] if e.args else None))
        if isinstance(exc, CancelledError):
            cancel(exc)
        else:
            task.cancel()
        while not task.done():
            try:
                await asyncio.wait({task})
            except CancelledError as again:
                cancel(again)
        if not task.cancelled():
            task.exception()

    def _optional_db_abandon(self, kind: str, task: asyncio.Task, limit_s: float) -> None:
        self._optional_db_running[kind] = task
        self.optional_db_abandoned += 1
        # A read that never finishes still ends: past the limit it is cancelled,
        # costing its connection as every read did before this switch.
        self._optional_db_limits[task] = asyncio.get_running_loop().call_later(
            max(0.0, limit_s), task.cancel,
        )
        task.add_done_callback(self._optional_db_finished)

    def _optional_db_finished(self, task: asyncio.Task) -> None:
        limit = self._optional_db_limits.pop(task, None)
        if limit is not None:
            limit.cancel()
        for kind, running in list(self._optional_db_running.items()):
            if running is task:
                del self._optional_db_running[kind]
        if not task.cancelled() and task.exception() is not None:
            error = task.exception()
            logger.warning(
                "live_blend_refresh[%s]: abandoned optional read failed",
                self.source, exc_info=(type(error), error, error.__traceback__),
            )
            if not optional_db_abandons():
                # A trial's switched path failed: off here for the rest of it.
                _optional_db_trial().trip(OPTIONAL_DB_SWITCH, error)

    async def _close_optional_db(self) -> None:
        """Cancel and join every abandoned read before the sessions close."""
        interrupted = None
        for task in list(self._optional_db_running.values()):
            if not task.done():
                task.cancel()
            while not task.done():
                try:
                    await asyncio.wait({task})
                except CancelledError as exc:
                    interrupted = exc
        self._optional_db_running.clear()
        if interrupted is not None:
            raise interrupted

    async def _publish(self, frames: list[dict]) -> set[tuple[int, int]]:
        """Fan the committed frames out to any SSE subscribers. Never raises.

        Bounded packed sends avoid one Redis round trip per event (#10659).
        Frame bytes and order stay unchanged; only committed inputs reach this
        method. A PUBLISH with no listeners is successful publication.

        Each command error is consumed and counted without costing siblings.
        An unanswered send may already have run: do not retry inside this attempt.
        Return positively acknowledged revisions to the withdrawal custodian;
        its durable replay may resend the exact committed invalidation later.
        Timeout, cancellation or transport failure disconnects the borrowed
        socket before it returns to the consumer's shared pool.
        """
        acknowledged: set[tuple[int, int]] = set()
        if not frames:
            return acknowledged
        sent = 0
        retention_answered = False
        accounted = 0
        exact_trace = getattr(self.receipts, "exact_trace", None)
        try:
            import asyncio
            from redis.exceptions import ResponseError

            from app.utils.live_push import frame_publish_command
            from app.utils.market_quote_push import _checkout

            async with asyncio.timeout(5):
                client = self._client()
                pool = client.connection_pool
                connection = await _checkout(pool)
                try:
                    for start in range(0, len(frames), 32):
                        commands: list[tuple] = []
                        event_ids: list[int] = []
                        event_revisions: list = []
                        for frame in frames[start : start + 32]:
                            try:
                                commands.append(frame_publish_command(frame, require_replay=True))
                                event_ids.append(frame["event_id"])
                                event_revisions.append(frame.get("rev"))
                            except Exception:
                                accounted += 1
                                self.stats["publish_errors"] += 1
                                logger.warning(
                                    "live_blend_refresh[%s]: frame failed for event %s",
                                    self.source,
                                    frame.get("event_id"),
                                    exc_info=True,
                                )
                        if not commands:
                            continue
                        # Same direct pool protocol as committed MARKET signals.
                        # Pipeline.execute can retry an ambiguous transport write.
                        await connection.send_packed_command(
                            connection.pack_commands(commands)
                        )
                        for event_id, revision in zip(event_ids, event_revisions):
                            try:
                                reply = await connection.read_response()
                            except ResponseError as exc:
                                if str(exc) == "normal price replay retention failed after PUBLISH":
                                    # Lua already published and Redis answered. Keep
                                    # the healthy connection, but do not pay the
                                    # durable intent without replay custody.
                                    retention_answered = True
                                if exact_trace is not None:
                                    with contextlib.suppress(Exception):
                                        exact_trace.publication(event_id, revision, "REDIS_ERROR")
                                accounted += 1
                                self.stats["publish_errors"] += 1
                                logger.warning(
                                    "live_blend_refresh[%s]: publish failed for event %s",
                                    self.source,
                                    event_id,
                                    exc_info=True,
                                )
                                continue
                            if type(reply) is not int or reply < 0:
                                raise ValueError("invalid Redis PUBLISH acknowledgment")
                            accounted += 1
                            sent += 1
                            if isinstance(revision, dict) and type(revision.get(str(event_id))) is int:
                                acknowledged.add((event_id, revision[str(event_id)]))
                            self.stats["published"] += 1
                            if exact_trace is not None:
                                with contextlib.suppress(Exception):
                                    exact_trace.publication(event_id, revision, "REDIS_ACK")
                except BaseException:
                    # Unknown acknowledgment state: unread replies must not be
                    # handed to another consumer, nor commands replayed here.
                    self._redis = None
                    await connection.disconnect()
                    raise
                finally:
                    await pool.release(connection)
                if sent == 0 and not retention_answered:
                    self._redis = None
        except Exception:
            self.stats["publish_errors"] += len(frames) - accounted
            self._redis = None
            logger.warning(
                "live_blend_refresh[%s]: publication incomplete: acknowledged=%s queued=%s",
                self.source,
                sent,
                len(frames),
                exc_info=True,
            )
        return acknowledged

    # ── #10090: provisional preview (off by default; canary events only) ──

    def _current_reading_proof(self, event_id, group, refused, *, park_refused=True):
        """Keep optional observation previews on the ordinary Kalshi proof path."""
        proof_kwargs = {}
        if (getattr(self, "require_current_book_proof", False)
                and any(getattr(entry.market, "source", None) == "kalshi"
                        and (getattr(entry.market, "external_id", None) or "").upper().startswith("KXATPCHALLENGERMATCH-")
                        for entry in group)):
            proof_kwargs = {
                "require_current_book_midpoint": True,
                "current_book_midpoint": getattr(self, "current_book_midpoint", None),
                "current_book_primary_price": getattr(self, "current_book_primary_price", None),
                "current_primary_input": (
                    lambda row: self.current_primary_input(
                        row, self.held_quotes,
                        overlaid=getattr(row, "_primary_quote_overlaid", False),
                    )
                ) if getattr(self, "current_primary_input", None) is not None else None,
                # Bound now: with a canary in the batch this
                # callback is stored in `preview_plans` and
                # called again by the stamp-time recheck.
                "current_book_refused": lambda refused=refused, event_id=event_id, group=group: (
                    refused.append(True)
                    or (self._park_book_refused(event_id, group) if park_refused else None)
                ),
            }
        return proof_kwargs

    async def preview_accepted_observations(self, observations, validate) -> bool | None:
        """Preview acknowledged unchanged venue observations without owning writes.

        The consumer excludes same-event price/stamp ownership and holds its
        scope guard until this work finishes. Graphs/sessions are call-local;
        False asks the caller to retain frozen inputs after capacity/read failure.
        The graph and copied input clocks are disposable. A separately selected
        DB clock may advance held_quotes only for inputs received AFTER this
        read scope completes; the frozen clocks in this batch never change.
        `validate` rechecks immutable input identity and the flush's ownership
        under its buffer lock, including at the final Redis send boundary.
        """
        if self.source not in ("polymarket", "kalshi") or not self.preview:
            return
        from app.tasks.base import get_task_session
        from app.utils.aggregation import _coerce_timestamp
        from app.utils.blend_preview import PREVIEW_STATUSES, registry
        from app.utils.settledness import market_assigned_settled
        from app.utils.live_blend import compute_source_home_probability, has_proven_home_orientation

        read_timing = None
        selections = None
        try:
            event_ids = {eid for eid in observations if eid in self.preview_events}
            event_ids.intersection_update(await validate(event_ids))
            if not event_ids:
                return
            factory = (self._observation_read_factory
                       or self._session_factory or get_task_session)
            # Optional display work must not queue the game loop behind a
            # contended pool/read. The caller may retain the SAME frozen input.
            if self._session_slots.locked():
                return False
            if (len(self._detached_reads) >= OBSERVATION_READ_DETACHED_MAX
                    or self._optional_db_busy()):
                # A read its caller left still holds a slot: no second read
                # starts beside it, so 2 of the 3 slots stay the stamps'. An
                # abandoned optional read (`OPTIONAL_DB_HELD_MAX`) is one.
                self.observation_read_stats["capped"] += 1
                return False
            read_timing = {"started_s": _mono()}
            clock_owner = self.held_quotes if self._observation_read_factory is not None else None
            clock = None
            if isinstance(clock_owner, HeldRowQuotes) and not clock_owner._closed:
                clock_owner._sample_started += 1
                clock_owner._sampling += 1
                clock_owner._last_sample_started = clock_owner._now()
                clock = (clock_owner, clock_owner._sample_started, {})
            read = _ObservationRead(read_timing)
            task = asyncio.create_task(
                self._observation_graph_read(read, factory, sorted(event_ids), clock),
                name=f"observation-read-{self.source}",
            )
            try:
                await asyncio.wait({task}, timeout=.25)
            except CancelledError:
                # External cancellation stops the read the old way, as the
                # scope it replaces did, and still ends with the caller.
                read.waiting = False
                task.cancel()
                self._track_observation_read(task, read, None)
                await asyncio.wait({task})
                raise
            if task.done():
                task.result()
                grouped = read.graph
            else:
                read.waiting = False
                read_timing["scope_ms"] = (_mono() - read_timing["started_s"]) * 1000
                await self._release_observation_read(task, read)
                # A completed autocommit SELECT needs no commit acknowledgement.
                # Its detached graph remains usable if only connection cleanup
                # exhausts our budget; that cleanup still finishes on its own.
                # Kalshi's ORM session has not committed: it does not qualify.
                # All input/freshness/send-boundary checks below remain.
                if self._observation_read_factory is None or read.graph is None:
                    raise _ObservationReadTimeout("observation read exceeded its preview budget")
                grouped = read.graph
                logger.warning(
                    "live_blend_refresh[%s]: observation read completed; cleanup exceeded budget read_timing=%s",
                    self.source, _observation_read_summary(read_timing),
                )
            plans = {}
            refusals = {}
            # #10090: selection receipts, only while a stage trace is attached.
            select_open = self._stage_hook("selection_open")
            selections = None if select_open is None else {}
            for eid, (event, group) in grouped.items():
                token = None if select_open is None else select_open(eid)
                if event.status not in PREVIEW_STATUSES or event.completed_at is not None:
                    refusals[eid] = "ineligible"
                    if token is not None:
                        self._trace_selection(None, eid, token, "refusal", route="observation",
                                              reason="ineligible")
                    continue
                rows = {row.id: (entry, row) for entry in group for row in entry.outcomes}
                snapshot = observations[eid]
                relevant = [entry for entry in group
                            if any(row.id in snapshot for row in entry.outcomes)]
                if any(entry.market.status != "open"
                       or market_assigned_settled(entry.market, entry.outcomes)
                       or any(row.resolution_source is not None for row in entry.outcomes)
                       for entry in relevant):
                    refusals[eid] = "settled"
                    if token is not None:
                        self._trace_selection(None, eid, token, "refusal", route="observation",
                                              reason="settled")
                    continue
                proof_kwargs = self._current_reading_proof(eid, group, [], park_refused=False)
                reading = compute_source_home_probability(
                    group, event.home_team_name, event.away_team_name, **proof_kwargs,
                )
                if reading is None or not has_proven_home_orientation(reading):
                    if token is not None:
                        self._trace_selection(
                            None, eid, token, "no_reading", route="observation", reading=reading,
                            reason=None if reading is None else "unproven_orientation",
                        )
                    continue  # optional path never invokes repairing inversion fallback
                contributors = getattr(reading, "contributing_outcomes", None) or (reading.outcome,)
                ids = {getattr(row, "id", None) for row in contributors}
                if not ids or not ids.issubset(snapshot):
                    if token is not None:
                        self._trace_selection(None, eid, token, "unobserved", route="observation",
                                              reading=reading, reason="contributor_not_observed")
                    continue
                if any(oid not in rows for oid in snapshot):
                    if token is not None:
                        self._trace_selection(None, eid, token, "unobserved", route="observation",
                                              reading=reading, reason="observation_not_read")
                    continue
                valid = True
                read_wall = datetime.now(timezone.utc).timestamp()
                for oid, (value, bound, mark) in snapshot.items():
                    entry, row = rows[oid]
                    stored_at = _coerce_timestamp(row.last_updated)
                    if (mark is None or getattr(mark, "probability", None) != value
                            or type(bound) not in (float, int) or not math.isfinite(bound)
                            or entry.market.status != "open" or row.resolution_source is not None
                            or row.is_winner is True or stored_at is None
                            or stored_at.timestamp() >= bound or bound > read_wall
                            or row.current_probability is None
                            or round(float(row.current_probability), 6) != round(float(value), 6)):
                        valid = False
                        break
                if not valid:
                    if token is not None:
                        self._trace_selection(None, eid, token, "unobserved", route="observation",
                                              reading=reading, reason="observation_invalid")
                    continue
                # Keep the immutable DB-clock bounds exactly; the generic
                # observation helper clamps future clocks to app-now. Such
                # clamping would manufacture newer observations on retries.
                basis = {str(row.id): float(snapshot[row.id][1]) for row in contributors}
                if basis:
                    plans[eid] = (event, reading, basis, group, proof_kwargs)
                    if token is not None:
                        self._trace_selection(
                            selections, eid, token, "preview_only", route="observation",
                            reading=reading, value=round(reading.home_probability, 4),
                            basis=basis, then="PROPOSE",
                        )
            if not plans and not refusals:
                return

            async def prepare_frames():
                allowed = await validate(set(plans) | set(refusals))
                if selections:
                    for eid in set(selections).difference(allowed or ()):
                        self._stage_trace("selection_unsent", selections[eid], "NOT_ALLOWED")
                if not allowed:
                    return []  # rejection/cancellation must not mutate the registry
                preview = registry()
                frames = preview.expire()
                for eid in allowed:
                    if eid in refusals:
                        frames.extend(preview.refused(eid, self.source, refusals[eid]))
                        continue
                    event, reading, basis, group, proof_kwargs = plans[eid]
                    if proof_kwargs:
                        # Current book/custody proof may change during Redis checkout.
                        current = compute_source_home_probability(
                            group, event.home_team_name, event.away_team_name, **proof_kwargs,
                        )
                        if (current is None or not has_proven_home_orientation(current)
                                or round(current.home_probability, 4) != round(reading.home_probability, 4)
                                or {str(row.id) for row in (getattr(current, "contributing_outcomes", None)
                                                            or (current.outcome,))} != set(basis)):
                            if selections and eid in selections:
                                self._stage_trace("selection_unsent", selections[eid], "RECHECK_CHANGED")
                            continue
                    ops = preview.propose(
                        eid, self.source, value=round(reading.home_probability, 4), event=event,
                        row_sources=event.preview_sources, row_rev=event.preview_rev,
                        eligibility=getattr(reading, "eligibility", None), observed_basis=basis,
                        observation_only=True,
                    )
                    frames.extend(ops)
                    if selections and eid in selections:
                        self._trace_proposal(selections[eid], ops, eid, preview.ledger)
                return frames

            await self._publish_previews([], prepare_frames=prepare_frames)
            if selections:
                self._stage_trace("selections_closed", selections.values())
        except Exception as exc:
            if selections:
                self._stage_trace("selections_closed", selections.values())
            # The read's own budget is not a publish failure; nothing was sent.
            key = ("observation_timeouts" if isinstance(exc, _ObservationReadTimeout)
                   else "publish_errors")
            self.preview_stats[key] = self.preview_stats.get(key, 0) + 1
            logger.warning(
                "live_blend_refresh[%s]: optional observation preview unavailable read_timing=%s "
                "detached_reads=%s",
                self.source, _observation_read_summary(read_timing),
                dict(self.observation_read_stats, running=len(self._detached_reads)),
                exc_info=True,
            )
            return False

    async def _observation_graph_read(self, read, factory, event_ids, clock) -> None:
        """The preview's graph read, in its own task so its caller can stop
        waiting without cancelling the statement (`OBSERVATION_READ_DETACHED_MAX`).

        The graph and copied input clocks are disposable. A separately selected
        DB clock may advance held_quotes only for inputs received AFTER this
        read scope completes, and only while its caller still waits.
        """
        token = _observation_read_timing.set(read.timing)
        try:
            async with self._session_slot(), factory() as session:
                read.graph = await self._read_groups(
                    session, event_ids, overlay_held=False,
                    stopped_waiting=lambda: not read.waiting,
                    **({"clock_sample": clock[2]} if clock is not None else {}),
                )
                read.timing["graph_ready_ms"] = (_mono() - read.timing["started_s"]) * 1000
            # Only normal context completion qualifies, never query or
            # cleanup timeout/cancellation, nor a read its caller left. A late
            # older read cannot replace a newer sample or clear its failure
            # episode.
            if clock is not None and read.waiting:
                clock_owner, clock_ordinal, clock_sample = clock
                if (clock_sample and self.held_quotes is clock_owner
                        and not clock_owner._closed
                        and clock_ordinal > clock_owner._sample_published):
                    clock_owner._database_bound = clock_sample["value"].timestamp()
                    clock_owner._sample_published = clock_ordinal
                    clock_owner._graph_sample_ordinal = clock_ordinal
                    # A graph read has a longer budget than the standalone
                    # clock probe. Its success supplies future input bounds,
                    # but cannot prove that shorter-budget path recovered.
                    # Only a standalone success clears its failure backoff.
                    clock_owner._last_sample_done = clock_owner._now()
        finally:
            if clock is not None:
                clock[0]._sampling -= 1  # counted until the read actually ends
            if read.waiting:
                read.timing["scope_ms"] = (_mono() - read.timing["started_s"]) * 1000
            _observation_read_timing.reset(token)

    async def _release_observation_read(self, task, read) -> None:
        """Its caller stopped waiting: leave the read to end by itself, or
        cancel it and wait out its cleanup as before.

        Cancelled: a retirement in flight (a Redis/row write never outlives its
        caller), or when `OBSERVATION_READ_DETACHED_MAX` reads already run.
        """
        if read.timing.get("retire_completed") is False:
            task.cancel()
        elif (len(self._detached_reads) >= OBSERVATION_READ_DETACHED_MAX
              or self._optional_db_busy()):
            self.observation_read_stats["capped"] += 1
            task.cancel()
        else:
            self.observation_read_stats["detached"] += 1
            ceiling = asyncio.get_running_loop().call_later(
                OBSERVATION_READ_DETACHED_S, self._cancel_detached_read, task, read,
            )
            self._track_observation_read(task, read, ceiling)
            return
        self._track_observation_read(task, read, None)
        await asyncio.wait({task})

    @staticmethod
    def _cancel_detached_read(task, read) -> None:
        if not task.done():
            read.ceiling = True
            task.cancel()

    def _track_observation_read(self, task, read, ceiling) -> None:
        """Count an unfinished read its caller left until it actually ends."""
        if task.done():
            self._observation_read_ended(read, ceiling, task)
            return
        self._detached_reads.add(task)
        task.add_done_callback(
            lambda done: self._observation_read_ended(read, ceiling, done)
        )

    def _observation_read_ended(self, read, ceiling, task) -> None:
        if ceiling is not None:
            ceiling.cancel()
        self._detached_reads.discard(task)
        if task.cancelled():
            if read.ceiling:
                self.observation_read_stats["ceiling_cancelled"] += 1
            return
        error = task.exception()
        if ceiling is not None:
            self.observation_read_stats["finished"] += 1
        if error is not None and not isinstance(error, _ObservationReadAbandoned):
            logger.warning(
                "live_blend_refresh[%s]: observation read failed after its caller stopped waiting",
                self.source, exc_info=(type(error), error, error.__traceback__),
            )

    # ── #10090 `preview_from_commit` ────────────────────────────────────────

    def _remember_preview_graphs(self, grouped, original_rows, read_started) -> None:
        """Keep each live preview event's graph exactly as this read returned it.

        Committed rows only: an event with a held-quote overlay (#11138) is not
        kept and drops any older graph, so nothing composed from the cache was
        never stored. A row this process committed while the read was in flight
        (`note_committed_rows`) is patched in, so a read that started before
        that COMMIT never puts the row's older value back. A read older than the
        kept one (a concurrent read that finished late) does not replace it.
        ``read_started`` is taken before the read's ticket: the graph's age.
        Never raises.
        """
        graphs = getattr(self, "_preview_graphs", None)
        receipt = _preview_at_receipt_possible(getattr(self, "source", None))
        if graphs is None or not (receipt or _preview_from_commit_possible()):
            return
        try:
            originals = None
            for event_id, (event, group) in grouped.items():
                if event_id not in self.preview_events:
                    continue
                kept = graphs.get(event_id)
                at = getattr(event, "preview_context_at", None)
                if kept is not None:
                    kept_at = getattr(kept[1], "preview_context_at", None)
                    if isinstance(kept_at, datetime) and (
                            not isinstance(at, datetime) or at < kept_at):
                        continue
                if (getattr(event, "status", None) != "live"
                        or getattr(event, "completed_at", None) is not None
                        or getattr(event, "preview_read_ticket", None) is None):
                    self._forget_preview_graph(event_id)
                    continue
                if any(id(row) not in original_rows
                       for entry in group for row in entry.outcomes):
                    # A held-quote overlay. `preview_at_receipt` keeps the rows
                    # as read (its own overlay carries the held quotes);
                    # `preview_from_commit` alone drops the graph, as before.
                    if originals is None and receipt:
                        values = getattr(original_rows, "values", None)
                        originals = ({row.id: row for row in values()}
                                     if callable(values) else {})
                    group = _unoverlaid_group(group, original_rows, originals) if receipt else None
                    if group is None:
                        self._forget_preview_graph(event_id)
                        continue
                forgotten = self._forgotten_outcomes
                if any(forgotten.get(row.id, -math.inf) >= read_started
                       for entry in group for row in entry.outcomes):
                    self._forget_preview_graph(event_id)
                    continue
                noted = self._noted_commits
                patched = _patched_group(group, {
                    row.id: noted[row.id][1]
                    for entry in group for row in entry.outcomes if row.id in noted
                })
                if patched is None:
                    self._forget_preview_graph(event_id)
                    continue
                self._install_preview_graph(event_id, (read_started, event, patched))
            while len(graphs) > PREVIEW_GRAPH_MAX_EVENTS:
                self._forget_preview_graph(min(graphs, key=lambda eid: graphs[eid][0]))
        except Exception:
            self.commit_preview_stats["errors"] += 1
            logger.warning("live_blend_refresh[%s]: preview graph not kept", self.source,
                           exc_info=True)

    def _install_preview_graph(self, event_id: int, entry: tuple) -> None:
        self._forget_preview_graph(event_id)
        self._preview_graphs[event_id] = entry
        for market in entry[2]:
            for row in market.outcomes:
                self._preview_graph_outcomes[row.id] = event_id

    def _forget_preview_graph(self, event_id: int) -> None:
        self._receipt_speaking.pop(event_id, None)
        entry = self._preview_graphs.pop(event_id, None)
        if entry is None:
            return
        for market in entry[2]:
            for row in market.outcomes:
                if self._preview_graph_outcomes.get(row.id) == event_id:
                    del self._preview_graph_outcomes[row.id]

    def note_committed_rows(self, rows) -> None:
        """A committed price write's RETURNING rows. Never raises.

        Called synchronously after the write's COMMIT, before its first await.
        Each row is noted for `PREVIEW_NOTE_RETENTION_S` (a read in flight
        patches it in); each cached graph holding a returned row gets a patched
        copy, and a live event whose `preview_from_commit` arm is on is queued
        for a preview composed from that copy (`_preview_from_commit_rows`).
        """
        note_rows = getattr(getattr(self, "receipts", None), "note_committed_rows", None)
        if note_rows is not None:
            # #10090: the delivery receipt's trail learns these inputs are
            # stored, whether or not any graph is cached for them.
            rows = rows if isinstance(rows, (list, tuple)) else list(rows)
            self._receipt_call(note_rows, rows)
        graphs = getattr(self, "_preview_graphs", None)
        if graphs is None or not _preview_from_commit_possible():
            return
        try:
            now = _mono()
            noted = self._noted_commits
            patches: dict[int, dict[int, dict]] = {}
            for row in rows:
                oid = getattr(row, "id", None)
                values = {name: getattr(row, name, _NOT_RETURNED) for name in COMMIT_PATCH_FIELDS}
                if (oid is None or any(value is _NOT_RETURNED for value in values.values())
                        or values["last_updated"] is None):
                    continue
                noted.pop(oid, None)
                noted[oid] = (now, values)
                event_id = self._preview_graph_outcomes.get(oid)
                if event_id is not None:
                    patches.setdefault(event_id, {})[oid] = values
            _prune_notes(noted, now, lambda note: note[0])
            for event_id, returned in patches.items():
                read_at, event, group = graphs[event_id]
                patched = _patched_group(group, returned)
                if patched is None:
                    # The write's re-rank moved a stored `rank` the resolver sorts by.
                    self._forget_preview_graph(event_id)
                    continue
                self._install_preview_graph(event_id, (read_at, event, patched))
                if _preview_from_commit(event_id):
                    self._commit_preview_due.setdefault(event_id, {}).update(
                        (oid, values["last_updated"]) for oid, values in returned.items()
                    )
            if self._commit_preview_due:
                task = self._commit_preview_task
                if task is None or task.done():
                    self._commit_preview_task = asyncio.create_task(
                        self._drain_commit_previews(), name=f"commit-preview-{self.source}",
                    )
        except Exception:
            self.commit_preview_stats["errors"] += 1
            logger.warning("live_blend_refresh[%s]: committed rows not noted", self.source,
                           exc_info=True)

    def forget_preview_outcomes(self, outcome_ids) -> None:
        """Rows this process changed OUTSIDE a price write (a settlement, a
        withdrawal): each cached graph holding one is dropped, and no read that
        started before now is kept for them. Called after that write's COMMIT,
        or when its outcome is unknown. Never raises."""
        graphs = getattr(self, "_preview_graphs", None)
        receipt = _preview_at_receipt_possible(getattr(self, "source", None))
        if graphs is None or not (receipt or _preview_from_commit_possible()):
            return
        try:
            now = _mono()
            forgotten = self._forgotten_outcomes
            outcome_ids = list(outcome_ids)
            events = []
            for oid in outcome_ids:
                forgotten.pop(oid, None)
                forgotten[oid] = now
                event_id = self._preview_graph_outcomes.get(oid)
                if event_id is not None:
                    events.append(event_id)
                    self._forget_preview_graph(event_id)
            _prune_notes(forgotten, now, lambda at: at)
            if receipt:
                self.note_receipt_withdrawn(outcome_ids, events)
        except Exception:
            self.commit_preview_stats["errors"] += 1
            logger.warning("live_blend_refresh[%s]: changed rows not forgotten", self.source,
                           exc_info=True)

    def _preview_graph_committed(self, event_id: int, sources, rev) -> None:
        """A stamp committed this event's bag at ``rev``: the cached graph's
        event carries it, so a later composition proposes on that revision and
        judges an unchanged reading against it. Never raises."""
        from copy import deepcopy
        from types import SimpleNamespace

        try:
            entry = getattr(self, "_preview_graphs", {}).get(event_id)
            if entry is None:
                return
            read_at, event, group = entry
            current = getattr(event, "preview_rev", None)
            if (type(rev) is not int or not isinstance(sources, dict)
                    or (type(current) is int and current >= rev)):
                return
            self._preview_graphs[event_id] = (read_at, SimpleNamespace(**{
                **vars(event),
                "preview_sources": deepcopy(sources),
                "preview_rev": rev,
                "win_probability_sources": {self.source: deepcopy(sources.get(self.source))},
            }), group)
        except Exception:
            self.commit_preview_stats["errors"] += 1
            logger.warning("live_blend_refresh[%s]: committed bag not cached", self.source,
                           exc_info=True)

    async def _drain_commit_previews(self) -> None:
        while self._commit_preview_due:
            due, self._commit_preview_due = self._commit_preview_due, {}
            try:
                await self._preview_from_commit_rows(due)
            except Exception:
                self.commit_preview_stats["errors"] += 1
                logger.warning("live_blend_refresh[%s]: preview from commit not sent",
                               self.source, exc_info=True)

    def _commit_preview_plan(self, event_id: int, written: dict, now: float):
        """``(event, reading, value, contributing)`` the re-read path would
        propose for this commit, from the cached graph; None to leave it there.

        Only a live event whose graph is young, needs no current-book proof,
        holds no held quote (the re-read would overlay it), is not held back
        from refreshing, still holds exactly the rows this process committed
        and resolves with a proven home orientation. Then the re-read path's
        own no-new-observation gate (#5661) against the stored entry. A value
        equal to the last written one is always left to the re-read path, even
        when `_should_write` would re-stamp it as due: stricter than
        `_should_write`, never looser.
        """
        from app.utils.aggregation import oldest_observation_time
        from app.utils.live_blend import (
            compute_source_home_probability, has_proven_home_orientation,
        )
        from app.utils.settledness import market_assigned_settled

        cached = self._preview_graphs.get(event_id)
        if cached is None:
            return None
        read_at, event, group = cached
        held = self.held_quotes
        if (now - read_at > PREVIEW_GRAPH_MAX_AGE_S
                or event.status != "live" or event.completed_at is not None
                or getattr(event, "preview_read_ticket", None) is None
                or type(getattr(event, "preview_rev", None)) is not int
                or event_id in self._lock_retry
                or self._failed_hold_until.get(event_id, now) > now
                or self._current_reading_proof(event_id, group, [], park_refused=False)
                or (held is not None and any(row.id in held
                                             for entry in group for row in entry.outcomes))):
            return None
        rows = {row.id: (entry, row) for entry in group for row in entry.outcomes}
        if any(oid not in rows or rows[oid][1].last_updated != at
               for oid, at in written.items()):
            return None  # a newer read or write replaced a row since
        reading = compute_source_home_probability(
            group, event.home_team_name, event.away_team_name,
        )
        if reading is None or not has_proven_home_orientation(reading):
            return None  # the stamp's own path owns the inversion fallback
        contributing = getattr(reading, "contributing_outcomes", None) or (reading.outcome,)
        ids = {getattr(row, "id", None) for row in contributing}
        if ids.isdisjoint(written) or not ids.issubset(rows):
            return None
        if any(entry.market.status != "open"
               or market_assigned_settled(entry.market, entry.outcomes)
               or any(row.resolution_source is not None or row.is_winner is True
                      for row in entry.outcomes)
               for entry in {id(rows[oid][0]): rows[oid][0] for oid in ids}.values()):
            return None
        value = round(reading.home_probability, 4)
        if (restamp_records_no_observation(
                value, oldest_observation_time(contributing),
                getattr(event, "win_probability_sources", None), self.source)
                or self._last_written_value.get(event_id) == value):
            return None
        return event, reading, value, contributing

    async def _preview_from_commit_rows(self, due: dict) -> None:
        """Propose each queued event's preview from its cached graph, no read.

        The proposal is the re-read path's (`_preview_before_stamp`) for the
        plan `_commit_preview_plan` admits, carrying the cached read's ticket,
        revision and base, so Redis refuses an open whose ticket is no longer
        current (`read_required`) or an older context that would change the
        event's class (`stale_context`), and the refused open is forgotten
        locally. The ordinary refresh of the same commit runs
        behind it whatever happens here.
        """
        from app.utils.aggregation import observation_basis
        from app.utils.blend_preview import registry

        now = _mono()
        plans = []
        for event_id, written in due.items():
            plan = self._commit_preview_plan(event_id, written, now)
            if plan is not None and observation_basis(plan[3]):
                plans.append((event_id, *plan))
        if not plans:
            return
        confirmed = getattr(self.receipts, "confirmed", None)
        if confirmed is not None:
            # #10090 decision J: no batch holds these events (`begin`), yet
            # readers may see this preview until a later batch's stamp.
            self._receipt_call(confirmed.previewed, [plan[0] for plan in plans])
        preview = registry()
        frames = preview.expire()
        for event_id, event, reading, value, contributing in plans:
            frames.extend(preview.propose(
                event_id, self.source, value=value, event=event,
                row_sources=event.preview_sources, row_rev=event.preview_rev,
                eligibility=getattr(reading, "eligibility", None),
                observed_basis=observation_basis(contributing),
            ))
            self.commit_preview_stats["proposed"] += 1
        await self._publish_previews(frames)

    async def _close_commit_preview(self) -> None:
        """Cancel and join the composition worker before the sessions close."""
        task, self._commit_preview_task = getattr(self, "_commit_preview_task", None), None
        if task is None:
            return
        if not task.done():
            task.cancel()
        interrupted = None
        while not task.done():
            try:
                await asyncio.wait({task})
            except CancelledError as exc:
                interrupted = exc
        if not task.cancelled():
            task.exception()
        if interrupted is not None:
            raise interrupted

    # ── #10090 `preview_at_receipt` ─────────────────────────────────────────

    def _note_receipt_input(self, mark, bound) -> None:
        """An accepted input (`HeldRowQuotes.note_input`, under the consumer's
        buffer lock, so in input-seq order): keep its price, queue its event.

        Receive-path cost only: a switch read and two dict writes. Composition
        runs on `_drain_receipt_previews`. An input with no frozen DB-clock
        ``bound`` cannot be ordered against the stored row and is not kept,
        nor one received while the routing is changing (`receipt_route`).
        Never raises (its caller swallows anyway).
        """
        event_id = getattr(mark, "event_id", None)
        oid = getattr(mark, "outcome_id", None)
        if (event_id is None or oid is None
                or not _preview_at_receipt(self.source, event_id)):
            return
        if bound is None:
            self.receipt_preview_stats["no_bound"] += 1
            return
        route = self.receipt_route
        token = route() if route is not None else 0
        if token is None:
            self.receipt_preview_stats["routing"] += 1
            return
        quotes = self._receipt_quotes
        prior = quotes.pop(oid, None)
        if prior is not None and getattr(prior[2], "seq", -1) >= getattr(mark, "seq", 0):
            quotes[oid] = prior  # an older input never replaces a newer one
            return
        now = _mono()
        quotes[oid] = (round(float(mark.probability), 6), float(bound), mark, event_id, token, now)
        self.receipt_preview_stats["noted"] += 1
        if self._preview_graph_outcomes.get(oid) != event_id:
            self.receipt_preview_stats["kept_no_graph"] += 1
            # Attribution: the event has a graph that lacks this leg (another
            # market) vs no graph for the event at all.
            self._note_receipt_class(
                "leg_not_in_graph" if event_id in self._preview_graphs else "event_no_graph",
                event_id)
            return  # kept for the overlay; no graph to compose it on yet
        speaking = self._receipt_speaking.get(event_id)
        if speaking is not None and oid not in speaking:
            self.receipt_preview_stats["not_speaking"] += 1
            self._note_receipt_class("not_speaking", event_id)
            return  # kept for the overlay; not a leg of the market that speaks
        if event_id not in self._hl_pending:
            self._hl_pending[event_id] = [getattr(mark, "recv_mono", now), "receipt"]
        self._receipt_due[event_id] = None
        last = self._receipt_last.get(event_id)
        self._wake_receipt(last is None or now - last[0] >= _receipt_interval())

    def note_receipt_withdrawn(self, outcome_ids, event_ids=()) -> None:
        """Legs a withdrawal (a book that prices them out) or a settlement took
        away: their received quotes are dropped and a receipt preview still
        pending for their events is revoked by the worker. Never raises."""
        if not _preview_at_receipt_possible(self.source):
            return
        try:
            events = dict.fromkeys(event_ids)
            for oid in outcome_ids:
                quote = self._receipt_quotes.pop(oid, None)
                if quote is not None:
                    events[quote[3]] = None
                event_id = self._preview_graph_outcomes.get(oid)
                if event_id is not None:
                    events[event_id] = None
            events.pop(None, None)
            if events:
                self._receipt_withdrawn.update(events)
                self._wake_receipt(True)
        except Exception:
            self.receipt_preview_stats["errors"] += 1

    def _wake_receipt(self, now: bool) -> None:
        task = self._receipt_task
        if task is None or task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            self._receipt_wake = asyncio.Event()
            self._receipt_task = loop.create_task(
                self._drain_receipt_previews(), name=f"receipt-preview-{self.source}",
            )
        elif now and self._receipt_wake is not None:
            self._receipt_wake.set()

    async def _drain_receipt_previews(self) -> None:
        """The one receipt-preview worker. Each pass composes every due event
        last composed at least `RECEIPT_PREVIEW_INTERVAL_S` ago (the rest wait
        for their interval, or a wake for an event that need not), and exits
        when nothing is left."""
        while self._receipt_due or self._receipt_withdrawn:
            now = _mono()
            interval = _receipt_interval()
            if now - self._receipt_stats_logged_at >= RECEIPT_STATS_LOG_INTERVAL_S:
                # Cumulative since this refresher started; readers diff lines.
                self._receipt_stats_logged_at = now
                logger.info(
                    "live_blend_refresh[%s]: receipt-preview stats %s compose_s=%.3f interval_s=%.2f "
                    "graph_max_age_s=%.0f events %s",
                    self.source,
                    " ".join(f"{k}={v}" for k, v in self.receipt_preview_stats.items()),
                    self.receipt_compose_s, interval, _receipt_graph_max_age(),
                    self._receipt_class_summary(),
                )
                logger.info("live_blend_refresh[%s]: headline-clock %s", self.source, self._hl_summary())
            due, deferred = [], {}
            for event_id in self._receipt_due:
                last = self._receipt_last.get(event_id)
                if last is not None and now - last[0] < interval:
                    deferred[event_id] = None
                else:
                    due.append(event_id)
            self._receipt_due = deferred
            withdrawn, self._receipt_withdrawn = list(self._receipt_withdrawn), {}
            if due or withdrawn:
                try:
                    await self._preview_at_receipt_rows(due, withdrawn)
                except Exception:
                    self.receipt_preview_stats["errors"] += 1
                    logger.warning("live_blend_refresh[%s]: receipt preview not sent",
                                   self.source, exc_info=True)
                continue
            wake = self._receipt_wake
            wait = min(self._receipt_last[eid][0] for eid in deferred) + interval - now
            if wake is None:
                await asyncio.sleep(max(0.0, wait))
                continue
            wake.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(wake.wait(), max(0.0, wait))

    def _hl_resolve(self, event_id, how: Optional[str] = None) -> None:
        """The headline clock stops: the page now shows this event's inputs."""
        entry = self._hl_pending.pop(event_id, None)
        if entry is None:
            return
        if len(self._hl_samples) < 20000:
            # A fallback keeps its reason (why it waited); else how it reached the screen.
            why = entry[1] if entry[1] != "receipt" else (how or "receipt")
            self._hl_samples.append((max(0.0, _mono() - entry[0]), event_id, why))

    def _hl_mark(self, event_id, how: str) -> None:
        """A headline input that will wait for the stamp path: say why."""
        entry = self._hl_pending.get(event_id)
        if entry is not None and entry[1] == "receipt":
            entry[1] = how
            self._hl_fallback[how] = self._hl_fallback.get(how, 0) + 1

    def _hl_published(self, frame, meta, reply) -> None:
        """Ledger observer: any published frame for an event puts its value on screen."""
        if reply and reply[0] == "published" and isinstance(frame, dict):
            event_id = frame.get("event_id")
            if event_id in self._hl_pending:
                self._hl_resolve(event_id)

    def _hl_summary(self) -> str:
        """The minute's headline clock: n, p50/p90/max, worst ids with how, fallbacks, late."""
        now = _mono()
        for event_id in [eid for eid, entry in self._hl_pending.items() if now - entry[0] > 60.0]:
            entry = self._hl_pending.pop(event_id)
            self._hl_late += 1
            self._hl_samples.append((now - entry[0], event_id, "late:" + entry[1]))
        samples, self._hl_samples = self._hl_samples, []
        late, self._hl_late = self._hl_late, 0
        fallback, self._hl_fallback = self._hl_fallback, {}
        if not samples:
            return "n=0 late=%d" % late
        ordered = sorted(x[0] for x in samples)
        pick = lambda q: int(round(ordered[min(len(ordered) - 1, int(q * len(ordered)))] * 1000))
        worst = sorted(samples, key=lambda x: -x[0])[:5]
        return "n=%d p50_ms=%d p90_ms=%d max_ms=%d worst=%s fallback=%s late=%d" % (
            len(samples), pick(0.5), pick(0.9), int(round(ordered[-1] * 1000)),
            ",".join("%s:%d:%s" % (eid, int(round(lat * 1000)), how) for lat, eid, how in worst),
            ",".join("%s:%d" % kv for kv in sorted(fallback.items())) or "-", late)

    def _note_receipt_class(self, kind: str, event_id) -> None:
        """Count one receipt composition outcome against its event (stats line)."""
        events = self._receipt_class_events.setdefault(kind, {})
        events[event_id] = events.get(event_id, 0) + 1

    def _receipt_class_summary(self) -> str:
        """``kind:event/count,...`` (top 6 per kind) since the last call; resets."""
        parts = []
        for kind, events in sorted(self._receipt_class_events.items()):
            top = sorted(events.items(), key=lambda kv: -kv[1])[:6]
            parts.append("%s:%s" % (kind, ",".join("%s/%d" % kv for kv in top)))
        self._receipt_class_events = {}
        return " ".join(parts) or "-"

    def _prune_receipt_quotes(self, now: float) -> None:
        quotes = self._receipt_quotes
        while quotes:
            oid = next(iter(quotes))
            if now - quotes[oid][5] <= RECEIPT_QUOTE_RETENTION_S:
                break
            del quotes[oid]
        last = self._receipt_last
        for event_id in [eid for eid, entry in last.items()
                         if now - entry[0] > RECEIPT_QUOTE_RETENTION_S]:
            del last[event_id]

    def _receipt_blend(self, event, source_value, eligibility, basis) -> Optional[int]:
        """The whole-percent blend ``event``'s committed bag composes to with
        this source at ``source_value`` (None: the committed value), as the
        preview composer does; None when there is none."""
        from types import SimpleNamespace

        from app.utils.aggregation import compute_aggregate_probability, stamp_source_reading

        bag = getattr(event, "preview_sources", None)
        if not isinstance(bag, dict):
            return None
        if source_value is not None:
            bag = stamp_source_reading(dict(bag), self.source, source_value,
                                       eligibility=eligibility, observed_basis=basis)
        probability = compute_aggregate_probability(SimpleNamespace(
            win_probability_sources=bag, status=event.status,
            espn_win_prob_home=getattr(event, "espn_win_prob_home", None),
            opening_home_probability=getattr(event, "opening_home_probability", None),
        ), event.status)
        return None if probability is None else round(float(probability) * 100)

    def _receipt_preview_plan(self, event_id: int, now: float, preview):
        """What a receipt composition does for this event: None (nothing),
        ``("returned",)`` (the reading is back at the stored value: retire a
        receipt preview) or ``("propose", event, reading, value, contributing,
        newest_mark)``.

        On the cached read graph (`_preview_graphs`), never older than
        `RECEIPT_GRAPH_MAX_AGE_S`, of a live event that needs no current-book
        proof: every row with a received quote strictly newer than the stored
        row (its frozen bound after the row's `last_updated`) is a copy at
        that price and bound, each changed market re-ranked as its write's
        re-rank will store it. A row stored at or after a quote's bound at a
        DIFFERENT price is ambiguous (the stored row may be newer): the whole
        event waits for its stamp, as `HeldRowQuotes.overlay_event` does.
        Then `_commit_preview_plan`'s checks: a proven orientation, every
        contributor read, an overlaid one among them, open unsettled markets.
        Skipped when the whole-percent blend is what the event already shows.
        """
        from types import SimpleNamespace

        from app.utils.aggregation import (
            _coerce_timestamp, observation_basis, oldest_observation_time,
        )
        from app.utils.live_blend import (
            compute_source_home_probability, has_proven_home_orientation,
        )
        from app.utils.settledness import market_assigned_settled

        stats = self.receipt_preview_stats
        cached = self._preview_graphs.get(event_id)
        if cached is None:
            stats["no_graph"] += 1
            self._note_receipt_class("no_graph", event_id)
            self._hl_mark(event_id, "no_graph")
            return None
        read_at, event, group = cached
        if now - read_at > _receipt_graph_max_age():
            stats["old_graph"] += 1
            self._note_receipt_class("old_graph", event_id)
            self._hl_mark(event_id, "old_graph")
            return None
        route = self.receipt_route
        token = route() if route is not None else 0
        gate = (token is None or event.status != "live" or event.completed_at is not None
                or getattr(event, "preview_read_ticket", None) is None
                or type(getattr(event, "preview_rev", None)) is not int
                or not _preview_at_receipt(self.source, event_id))
        if gate or self._current_reading_proof(event_id, group, [], park_refused=False):
            stats["not_admitted"] += 1
            self._note_receipt_class("not_admitted", event_id)
            self._hl_mark(event_id, "na_gate" if gate else "na_proof")
            return None
        quotes = self._receipt_quotes
        patched, overlaid, newest = [], set(), None
        for entry in group:
            outcomes, changed = [], False
            for row in entry.outcomes:
                quote = quotes.get(row.id)
                if quote is None or quote[3] != event_id or quote[4] != token:
                    outcomes.append(row)
                    continue
                price, bound, mark = quote[0], quote[1], quote[2]
                stored = _coerce_timestamp(getattr(row, "last_updated", None))
                if stored is not None and stored.timestamp() >= bound:
                    current = getattr(row, "current_probability", None)
                    if current is not None and round(float(current), 6) == price:
                        outcomes.append(row)  # the row already holds this quote
                        continue
                    stats["ambiguous"] += 1
                    self._note_receipt_class("ambiguous", event_id)
                    self._hl_mark(event_id, "ambiguous")
                    return None
                outcomes.append(SimpleNamespace(**{
                    **vars(row), "current_probability": price,
                    "last_updated": datetime.fromtimestamp(bound, timezone.utc),
                }))
                overlaid.add(row.id)
                changed = True
                if newest is None or mark.recv_mono > newest.recv_mono:
                    newest = mark
            if changed:
                ranks = _field_ranks([row.current_probability for row in outcomes])
                outcomes = [row if getattr(row, "rank", None) == rank
                            else SimpleNamespace(**{**vars(row), "rank": rank})
                            for row, rank in zip(outcomes, ranks)]
                patched.append(_replace(entry, outcomes=outcomes))
            else:
                patched.append(entry)
        if not overlaid:
            # Every received leg is already in the stored rows the graph read:
            # committed and stamped, so on screen (headline clock stops).
            self._hl_resolve(event_id, "in_graph")
            return None  # nothing received since the graph: the stamp's own path
        reading = compute_source_home_probability(
            patched, event.home_team_name, event.away_team_name,
        )
        if reading is None:
            self._receipt_speaking[event_id] = frozenset()
        if reading is None or not has_proven_home_orientation(reading):
            stats["not_admitted"] += 1
            self._note_receipt_class("not_admitted", event_id)
            self._hl_mark(event_id, "na_orientation")
            return None
        contributing = getattr(reading, "contributing_outcomes", None) or (reading.outcome,)
        rows = {row.id: (entry, row) for entry in patched for row in entry.outcomes}
        ids = {getattr(row, "id", None) for row in contributing}
        self._receipt_speaking[event_id] = frozenset(
            row.id for oid in ids if oid in rows for row in rows[oid][0].outcomes)
        if ids.isdisjoint(overlaid):
            # The received legs do not contribute to this reading: no headline effect.
            self._hl_resolve(event_id, "not_contributing")
            return None  # the received legs are not this reading's
        if not ids.issubset(rows):
            self._hl_mark(event_id, "incomplete")
            return None  # the received legs are not this reading's
        if any(entry.market.status != "open"
               or market_assigned_settled(entry.market, entry.outcomes)
               or any(row.resolution_source is not None or row.is_winner is True
                      for row in entry.outcomes)
               for entry in {id(rows[oid][0]): rows[oid][0] for oid in ids}.values()):
            stats["not_admitted"] += 1
            self._note_receipt_class("not_admitted", event_id)
            self._hl_mark(event_id, "na_settled")
            return None
        value = round(reading.home_probability, 4)
        if self._last_written_value.get(event_id) == value:
            # Back at the stored value: retire any receipt preview so the page
            # shows the committed one. Records nothing, so the #5661 restamp
            # gate below (which refuses re-dating an unchanged value) does not
            # apply; checked first so a stale receipt preview never outlives it.
            return ("returned",)
        basis = observation_basis(contributing)
        if not basis or restamp_records_no_observation(
                value, oldest_observation_time(contributing),
                getattr(event, "win_probability_sources", None), self.source):
            stats["not_admitted"] += 1
            self._note_receipt_class("not_admitted", event_id)
            self._hl_mark(event_id, "na_basis")
            return None
        pending = preview.pending_entry(event_id, self.source)
        eligibility = getattr(reading, "eligibility", None)
        shown = self._receipt_blend(event, None if pending is None else pending.value,
                                    getattr(pending, "eligibility", None),
                                    getattr(pending, "observed_basis", None))
        if shown is not None and shown == self._receipt_blend(event, value, eligibility, basis):
            stats["unchanged"] += 1
            self._note_receipt_class("unchanged", event_id)
            self._hl_resolve(event_id, "unchanged")
            return None
        return ("propose", event, reading, value, contributing, newest)

    async def _preview_at_receipt_rows(self, due: list, withdrawn: list) -> None:
        """Compose ``due`` events at receipt and revoke ``withdrawn`` ones'.

        Live events first and, among them, the ones a reader holds open
        (`reader_held`). Composition is local (no read, no await); the
        proposals and revokes are made under the publication's claim lock
        (`prepare_frames`), so they are ordered with every other publisher.
        A revoke or a return to the stored value retires only a pending value
        this path proposed (`at_receipt`): a stamp's own preview is the
        stamp's to settle.
        """
        from datetime import datetime as _dt

        from app.utils.blend_preview import registry

        started = time.perf_counter()
        now = _mono()
        preview = registry()
        self._prune_receipt_quotes(now)
        held = frozenset()
        if self.reader_held is not None:
            with contextlib.suppress(Exception):
                held = self.reader_held()
        due = sorted(due, key=lambda eid: eid not in held)
        plans = []
        for event_id in due:
            # The interval bounds compositions, not only proposals.
            self._receipt_last[event_id] = (now,)
            try:
                plan = self._receipt_preview_plan(event_id, now, preview)
            except Exception:
                self.receipt_preview_stats["errors"] += 1
                logger.warning("live_blend_refresh[%s]: receipt preview for event %s not composed",
                               self.source, event_id, exc_info=True)
                continue
            if plan is not None:
                plans.append((event_id, plan))
        self.receipt_compose_s += time.perf_counter() - started
        withdrawn = [eid for eid in withdrawn
                     if getattr(preview.pending_entry(eid, self.source), "at_receipt", False)]
        if not plans and not withdrawn:
            return
        proposals = [event_id for event_id, plan in plans if plan[0] == "propose"]
        confirmed = getattr(self.receipts, "confirmed", None)
        if confirmed is not None and proposals:
            # #10090 decision J, as `_preview_from_commit_rows`: readers may
            # see this preview before any batch holds these events.
            self._receipt_call(confirmed.previewed, proposals)

        async def prepare_frames():
            from app.utils.aggregation import observation_basis

            frames = preview.expire()
            stats = self.receipt_preview_stats
            for event_id in withdrawn:
                entry = preview.pending_entry(event_id, self.source)
                if entry is not None and entry.at_receipt:
                    frames.extend(preview.refused(event_id, self.source, "withdrawn"))
                    stats["withdrawn"] += 1
            for event_id, plan in plans:
                entry = preview.pending_entry(event_id, self.source)
                if plan[0] == "returned":
                    self._hl_resolve(event_id, "returned")
                    if entry is not None and entry.at_receipt:
                        frames.extend(preview.refused(event_id, self.source, "returned"))
                        stats["returned"] += 1
                    continue
                _kind, event, reading, value, contributing, newest = plan
                stamped_at = _dt.now(timezone.utc)
                frames.extend(preview.propose(
                    event_id, self.source, value=value, event=event,
                    row_sources=event.preview_sources, row_rev=event.preview_rev,
                    eligibility=getattr(reading, "eligibility", None),
                    observed_basis=observation_basis(contributing),
                    stamped_at=stamped_at, at_receipt=True,
                ))
                pending = preview.pending_entry(event_id, self.source)
                if pending is None or not pending.at_receipt or pending.value != value:
                    self._hl_mark(event_id, "refused_local")
                    continue  # refused locally (stale, expired value, capacity)
                stats["proposed"] += 1
                self._note_receipt_class("proposed", event_id)
                if self.preview_receipt is not None and newest is not None:
                    self._receipt_call(self.preview_receipt.carried, event_id,
                                       stamped_at.isoformat(), newest)
            return frames

        await self._publish_previews([], prepare_frames=prepare_frames)

    async def revoke_receipt_previews(self, outcome_ids) -> None:
        """Prices whose write will never happen (the final drain stranded
        them): every receipt preview still pending for their events is
        revoked now, on the caller's task (the worker may already be gone).
        A write that fails and stays buffered is retried, so its preview
        stands. Never raises."""
        if not _preview_at_receipt_possible(self.source):
            return
        try:
            from app.utils.blend_preview import registry

            events = set()
            for oid in outcome_ids:
                quote = self._receipt_quotes.pop(oid, None)
                if quote is not None:
                    events.add(quote[3])
                if oid in self._preview_graph_outcomes:
                    events.add(self._preview_graph_outcomes[oid])
            preview = registry()

            def ours():
                return [eid for eid in events
                        if getattr(preview.pending_entry(eid, self.source), "at_receipt", False)]

            if not ours():
                return

            async def prepare_frames():
                frames = []
                for event_id in ours():
                    frames.extend(preview.refused(event_id, self.source, "write_failed"))
                    self.receipt_preview_stats["withdrawn"] += 1
                return frames

            await self._publish_previews([], prepare_frames=prepare_frames)
        except Exception:
            self.receipt_preview_stats["errors"] += 1
            logger.warning("live_blend_refresh[%s]: receipt previews not revoked",
                           self.source, exc_info=True)

    async def _close_receipt_preview(self) -> None:
        """Cancel and join the receipt-preview worker before the sessions close."""
        task, self._receipt_task = getattr(self, "_receipt_task", None), None
        if task is None:
            return
        if not task.done():
            task.cancel()
        interrupted = None
        while not task.done():
            try:
                await asyncio.wait({task})
            except CancelledError as exc:
                interrupted = exc
        if not task.cancelled():
            task.exception()
        if interrupted is not None:
            raise interrupted

    async def _preview_before_stamp(self, grouped, plans, published_seq, *, observation_only=(),
                                    selections=None) -> None:
        """Publish every planned reading's preview, then let the UPDATEs run.

        Called once per attempt after all readings were computed and before
        any event's UPDATE, so no event's row-lock wait delays another event's
        preview. A failure here costs only the preview; the stamp proceeds.
        ``selections`` (#10090, only with a stage trace) maps a traced event to
        its SELECTED ``sel``; that proposal carries it into the ledger call.
        """
        from app.utils.aggregation import observation_basis
        from app.utils.blend_preview import registry

        preview = registry()
        frames = preview.expire()
        for event_id, (_refused, _proof, reading, value, contributing) in plans.items():
            event, _group = grouped[event_id]
            sel = selections.get(event_id) if selections else None
            try:
                ops = preview.propose(
                    event_id, self.source, value=value, event=event,
                    row_sources=getattr(event, "preview_sources", None),
                    row_rev=getattr(event, "preview_rev", None),
                    eligibility=getattr(reading, "eligibility", None),
                    observed_basis=observation_basis(contributing),
                    observation_only=event_id in observation_only,
                )
                frames.extend(ops)
            except Exception:
                self.preview_stats["publish_errors"] += 1
                logger.warning(
                    "live_blend_refresh[%s]: preview for event %s not composed",
                    self.source, event_id, exc_info=True,
                )
                if sel is not None:
                    self._stage_trace("selection_unsent", sel, "COMPOSE_ERROR")
                continue
            if sel is not None:
                self._trace_proposal(sel, ops, event_id, preview.ledger)
            seq = preview.pending_seq(event_id, self.source)
            if seq is not None:
                published_seq[event_id] = seq
        await self._publish_previews(frames)
        if selections:
            self._stage_trace("selections_closed", selections.values())

    def _preview_settlement(self, event_ids, grouped, published_seq, failed,
                            committed) -> list[dict]:
        """Settle this attempt's previews against what actually committed.

        Over every ATTEMPTED event, not only those the group read returned: an
        event this source no longer speaks for (unlinked, emptied, omitted by
        a prepared read) must not keep its pending value in the sibling's
        previews. Returns the frames; the caller orders their publication.
        """
        from app.utils.blend_preview import registry

        preview = registry()
        frames: list[dict] = []
        for event_id in dict.fromkeys(event_ids):
            if event_id not in self.preview_events:
                continue  # never proposed: nothing to settle
            try:
                if event_id not in grouped:
                    frames.extend(preview.refused(event_id, self.source, "no_group"))
                    continue
                if event_id in committed:
                    sources, rev, event = committed[event_id]
                    frames.extend(preview.committed(
                        event_id, self.source, seq=published_seq.get(event_id),
                        sources=sources, rev=rev, event=event,
                    ))
                    continue
                if event_id in failed:
                    reason = "error"
                else:
                    reason = (self._dispositions.get(event_id) or ("unknown",))[0]
                    if reason == "lock":
                        continue  # still owed; the retry republishes it
                    if reason in ("preview_only", "unobserved"):
                        # The optional proposal already judged this observation;
                        # absence of a newer durable row is not a withdrawal.
                        # The event restamp was deliberately throttled. Retain
                        # the bounded display chain, including its expiry fence,
                        # without pretending a failed write needs retrying.
                        continue
                # Also ends an expired chain with nothing pending (R4).
                frames.extend(preview.refused(event_id, self.source, reason))
            except Exception:
                self.preview_stats["publish_errors"] += 1
                logger.warning(
                    "live_blend_refresh[%s]: preview for event %s not settled",
                    self.source, event_id, exc_info=True,
                )
        return frames

    async def _claim_preview_epoch(self, connection, preview) -> None:
        """One atomic INCR + SET owner (`FENCE_CLAIM_SCRIPT`); caller holds the claim lock."""
        from app.utils.blend_preview import (
            FENCE_CLAIM_SCRIPT, FENCE_EPOCH_KEY, fence_owner_key,
        )

        if preview.ledger:
            bind_primary = getattr(preview, "bind_primary", None)
            if callable(bind_primary):
                from app.services.dnpl_authority import AuthorityStore
                from app.tasks.base import get_task_session

                await bind_primary(AuthorityStore(self._session_factory or get_task_session))
            # Owner claim remains atomic inside the exact ready namespace.
            await preview.claim(self._preview_call(connection), self.source)
        else:
            await connection.send_command(
                "EVAL", FENCE_CLAIM_SCRIPT, 2, FENCE_EPOCH_KEY, fence_owner_key(self.source),
            )
            preview.epoch = int(await connection.read_response())
        logger.info(
            "live_blend_refresh[%s]: preview display claimed epoch=%s",
            self.source, preview.claim_of(self.source),
        )

    @staticmethod
    @lru_cache(maxsize=2)
    def _preview_script_sha(script: str) -> str:
        from hashlib import sha1

        # Redis's program identity only; authority is checked inside the Lua.
        return sha1(script.encode(), usedforsecurity=False).hexdigest()

    @staticmethod
    def _preview_call(connection, *, send_before: Optional[float] = None):
        from redis.exceptions import NoScriptError
        from app.utils.blend_preview import LEDGER_SCRIPT
        from app.utils.dnpl_redis_authority import GUARDED_LEDGER_SCRIPT

        script_shas = {LEDGER_SCRIPT: LiveBlendRefresher._preview_script_sha(LEDGER_SCRIPT)}
        # Rollback changes transport only: DNPL still executes the complete guard.
        if os.getenv("DNPL_GUARDED_LEDGER_EVALSHA", "1") != "0":
            script_shas[GUARDED_LEDGER_SCRIPT] = LiveBlendRefresher._preview_script_sha(
                GUARDED_LEDGER_SCRIPT
            )

        async def send(*args):
            if send_before is not None and asyncio.get_running_loop().time() >= send_before:
                raise TimeoutError("idle retirement pass ended before transmission")
            await connection.send_command(*args)
            return await connection.read_response()

        async def call(*args):
            script_sha = (
                script_shas.get(args[1])
                if len(args) >= 3 and args[0] == "EVAL" and isinstance(args[1], str)
                else None
            )
            if script_sha is not None:
                try:
                    return await send("EVALSHA", script_sha, *args[2:])
                except NoScriptError:
                    # NOSCRIPT proves nothing ran. Load and execute the exact
                    # program once; never replay a timeout or ambiguous write.
                    # Recheck the retirement deadline before this second send.
                    pass
            return await send(*args)
        return call

    async def claim_preview_display(self) -> Optional[int]:
        """Claim this process's display epoch at startup, before any frame.

        Eager, so epoch order is process START order: a replacement started
        during a release overlap outranks the worker it replaces even if that
        worker has not previewed yet, instead of an old process's first frame
        in its final drain fencing the replacement for life. A no-op unless
        this arm previews, and when this process already holds an epoch.
        Never raises: a failed claim is retried by the first publication.
        """
        if not self.preview:
            return None
        try:
            from app.utils.blend_preview import registry
            from app.utils.market_quote_push import _checkout

            preview = registry()
            async with asyncio.timeout(1):
                if preview.claim_lock is None:
                    preview.claim_lock = asyncio.Lock()
                async with preview.claim_lock:
                    if preview.unclaimed(self.source):
                        pool = self._client().connection_pool
                        connection = await _checkout(pool)
                        try:
                            await self._claim_preview_epoch(connection, preview)
                        except BaseException:
                            self._redis = None
                            await connection.disconnect()
                            raise
                        finally:
                            await pool.release(connection)
            return preview.claim_of(self.source)
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning(
                "live_blend_refresh[%s]: preview display claim failed at startup",
                self.source, exc_info=True,
            )
            return None

    async def _preview_ticket(self, *, include_candidates=False):
        from app.utils.blend_preview import registry
        from app.utils.market_quote_push import _checkout

        preview = registry()
        if preview.claim_lock is None:
            preview.claim_lock = asyncio.Lock()
        pool = self._client().connection_pool
        # An established claim/authority is stable for this registry. Reading
        # its ticket uses a separate socket and Redis still checks the owner
        # and retirement barrier atomically. Do not spend the 250ms admission
        # budget waiting behind a publication batch. First claims and capacity
        # sampling (which updates local policy state) remain serialized.
        lock = (preview.claim_lock if include_candidates or preview.unclaimed(self.source)
                else contextlib.nullcontext())
        async with lock:
            connection = await _checkout(pool)
            try:
                if preview.unclaimed(self.source):
                    await self._claim_preview_epoch(connection, preview)
                if include_candidates:
                    return await preview.capacity_ticket(self._preview_call(connection), self.source,
                                                         maintenance_receipt=True)
                return await preview.read_ticket(self._preview_call(connection), self.source)
            except BaseException:
                self._redis = None
                await connection.disconnect()
                raise
            finally:
                await pool.release(connection)

    def _start_preview_maintenance(self):
        # One bounded pass per source per 30 seconds, independent of flush
        # cadence. No DB candidate scan or HKEYS on the admission path.
        if (not self._owns_preview_maintenance or self._preview_maintenance_closed or
                time.monotonic() < self._preview_maintenance_after or
                (self._preview_maintenance_task is not None and
                 not self._preview_maintenance_task.done()) or
                self._optional_db_busy()):
            return
        self._preview_maintenance_after = time.monotonic() + 30.0
        self._preview_maintenance_task = asyncio.create_task(self._maintain_preview_capacity())

    @staticmethod
    def _preview_retirable_row():
        from sqlalchemy import and_, or_, text
        from app.models.models import Event
        from app.tasks.ws_slate import SUSPENDED_SLATE_MAX_AGE_HOURS
        from app.utils.blend_preview import PREVIEW_STATUSES

        return or_(Event.status.not_in(PREVIEW_STATUSES), Event.completed_at.is_not(None),
                   and_(Event.status.in_(("scheduled", "suspended")),
                        Event.commence_time < text(
                            f"NOW() - INTERVAL '{int(SUSPENDED_SLATE_MAX_AGE_HOURS)} hours'")))

    @staticmethod
    def _preview_capacity_counts(candidates, rows, now: Optional[datetime], idle=()) -> dict:
        """Report-only split of the residents a full pass read (#10090)."""
        counts = {"candidates": len(candidates), "missing": 0, "retirable": 0,
                  "live": 0, "scheduled": 0, "suspended": 0, "other": 0,
                  "live_over_6h": 0, "oldest_live_h": "-",
                  "idle": sum(1 for eid in candidates if eid in idle)}
        present = {row[0] for row in rows}
        counts["missing"] = sum(1 for eid in candidates if eid not in present)
        oldest = None
        for row in rows:
            counts["retirable"] += bool(row[2])
            status = row[3] if row[3] in ("live", "scheduled", "suspended") else "other"
            counts[status] += 1
            if status == "live" and row[4] is not None:
                age = (now - row[4]).total_seconds() / 3600.0
                counts["live_over_6h"] += age > PREVIEW_CAPACITY_LIVE_OLD_HOURS
                oldest = age if oldest is None else max(oldest, age)
        if oldest is not None:
            counts["oldest_live_h"] = f"{oldest:.1f}"
        return counts

    async def _maintain_preview_capacity(self):
        from sqlalchemy import func, select
        from app.models.models import Event
        from app.tasks.base import get_task_session
        from app.utils.blend_preview import registry

        end, attempted, idle_attempted, policy_attempted = None, 0, 0, 0
        reclaimed_before = self.preview_stats.get("capacity_reclaimed", 0)
        counts = self._preview_capacity_counts((), (), None)
        try:
            async with asyncio.timeout(1) as budget:
                preview = registry()
                if preview.ledger:
                    # Local-only clean residue is absent from Redis's hints.
                    # Reconcile it before the receipt, even if no shared
                    # resident or network ticket is available this pass.
                    preview.maintain_local_capacity()
                ticket, candidates, idle, redis_now = await self._preview_ticket(include_candidates=True)
                when = budget.when()
                deadline_ms = (redis_now + int((when - asyncio.get_running_loop().time()) * 1000)
                               if redis_now is not None else None)
                if ticket is None or not candidates:
                    end = "no_ticket" if ticket is None else "no_candidates"
                    return
                if deadline_ms is None or deadline_ms <= redis_now:
                    end = "deadline"
                    counts["candidates"] = len(candidates)
                    counts["idle"] = sum(eid in idle for eid in candidates)
                    return
                # Account a bounded set without changing lifecycle or display
                # authority. Older/unclassified context is first in Redis's
                # persisted ordering, so restarts do not restart the migration.
                await self._classify_preview_residents(ticket, candidates[:32])
                ticket, candidates, idle, _ = await self._preview_ticket(include_candidates=True)
                if ticket is None:
                    end = "ticket_lost"
                    return
                policy = [eid for eid in candidates if eid in idle][:PREVIEW_CAPACITY_BATCH]
                if policy:
                    policy_attempted = len(policy)
                    await self._retire_policy_preview_events(policy, ticket, deadline_ms, when)
                # Policy retirement changed the barrier and resident hints.
                ticket, candidates, idle, _ = await self._preview_ticket(include_candidates=True)
                if ticket is None or not candidates:
                    end = "ticket_lost" if ticket is None else "no_candidates"
                    return
                factory = self._session_factory or get_task_session

                # Fetch existence and retirement eligibility together. This is
                # a fresh statement after the ticket, never cached slate data.
                async def read_candidates(gate):
                    async with self._session_slot():
                        if gate is not None:
                            gate.reading = True
                        async with factory() as session:
                            found = (await session.execute(select(
                                Event.id, Event.win_probability_sources_rev,
                                self._preview_retirable_row().label("retirable"),
                                Event.status, Event.commence_time, func.now().label("read_at"),
                            ).where(Event.id.in_(candidates)))).all()
                        if gate is not None:
                            gate.read_done()
                        return found

                rows = await self._optional_db_in_pass(
                    "preview_capacity", read_candidates, _optional_db_key(candidates))
                try:
                    counts = self._preview_capacity_counts(
                        candidates, rows, datetime.now(timezone.utc), idle)
                except Exception:
                    # Report only: a counting fault never stops reclamation.
                    logger.warning("live_blend_refresh[%s]: preview capacity receipt uncounted",
                                   self.source, exc_info=True)
                present = {row[0]: row for row in rows}
                def priority(eid):
                    row = present.get(eid)
                    if row is None or row[2]:
                        return (0, 0, eid)
                    # Only future scheduled rows reach this idle branch.
                    return (1, -row[4].timestamp(), eid)

                def idle_target(row):
                    return (not row[2] and row[3] == "scheduled"
                            and row[4] is not None and row[4] > row[5])

                targets = sorted((eid for eid in candidates
                                  if eid not in present or present[eid][2]
                                  or (eid in idle and idle_target(present[eid]))),
                                 key=priority)[:PREVIEW_CAPACITY_BATCH]
                idle_targets = [eid for eid in targets
                                if eid in present and not present[eid][2]]
                lifecycle = [eid for eid in targets if eid not in idle_targets]
                # Reclaim a bounded batch rather than allowing just one new
                # event per cadence. Every deletion advances the barrier;
                # each next lifecycle proof therefore needs a new ticket AND
                # DB read. Missing/retirable rows sort first.
                for index, eid in enumerate(lifecycle):
                    row = present.get(eid)
                    if index:
                        ticket, _ = await self._preview_ticket()
                        if ticket is None:
                            end = "ticket_lost"
                            return
                        async def read_target(gate, eid=eid):
                            async with self._session_slot():
                                if gate is not None:
                                    gate.reading = True
                                async with factory() as session:
                                    found = (await session.execute(select(
                                        Event.id, Event.win_probability_sources_rev,
                                        self._preview_retirable_row().label("retirable"),
                                        Event.status, Event.commence_time,
                                        func.now().label("read_at"),
                                    ).where(Event.id == eid))).first()
                                if gate is not None:
                                    gate.read_done()
                                return found

                        row = await self._optional_db_in_pass(
                            "preview_capacity", read_target, _optional_db_key([eid]))
                    if row is None:
                        attempted += 1
                        await self._publish_previews([registry().retire_missing(eid, self.source, ticket)])
                    elif row[2]:
                        attempted += 1
                        # The background UPDATE shares the same three DB
                        # slots as quote reads, stamps and chart custody.
                        # Inline terminal callers already own their slot.
                        async with self._session_slot():
                            await self._retire_preview_event(eid, row[1], ticket)
                    elif eid in idle and idle_target(row):
                        # A reread turned this row future-idle: the batch
                        # below proves it again under its own row lock.
                        idle_targets.append(eid)
                if idle_targets:
                    if attempted:
                        # Lifecycle retirements moved the barrier.
                        ticket, _ = await self._preview_ticket()
                        if ticket is None:
                            end = "ticket_lost"
                            return
                    idle_attempted = len(idle_targets)
                    await self._retire_idle_preview_events(idle_targets, ticket, deadline_ms, when)
                end = "done"
        except Exception:
            end = "error"
            self.preview_stats["publish_errors"] += 1
            logger.warning("live_blend_refresh[%s]: preview capacity maintenance incomplete",
                           self.source, exc_info=True)
        finally:
            # A cancelled pass (shutdown) leaves end unset and logs nothing.
            if end is not None:
                self._log_preview_capacity_receipt(
                    end, counts, attempted, idle_attempted, policy_attempted,
                    self.preview_stats.get("capacity_reclaimed", 0) - reclaimed_before)

    def _log_preview_capacity_receipt(self, end: str, c: dict, attempted: int,
                                      idle_attempted: int, policy_attempted: int = 0,
                                      reclaimed: int = 0) -> None:
        self._capacity_ends[end] = self._capacity_ends.get(end, 0) + 1
        logger.info(PREVIEW_CAPACITY_RECEIPT_FORMAT, self.source, end, c["candidates"],
                    c["missing"], c["retirable"], attempted, c["live"], c["scheduled"],
                    c["suspended"], c["other"], c["live_over_6h"], c["oldest_live_h"],
                    c["idle"], idle_attempted, policy_attempted, reclaimed)

    @staticmethod
    def _reservation_context_query(event_ids):
        from sqlalchemy import func, select
        from app.models.models import Event, Sport

        # Lock event context, not the nullable side of the sport lookup. The
        # canonical key comes from Event.sport_id -> Sport.key, never a market
        # hint or a competing tier table. SKIP LOCKED is absence of proof.
        return (select(Event.id, Event.status, Event.commence_time, Event.completed_at,
                       Event.win_probability_sources_rev.label("preview_rev"),
                       Sport.key.label("sport_key"),
                       func.statement_timestamp().label("preview_context_at"))
                .outerjoin(Sport, Sport.id == Event.sport_id)
                .where(Event.id.in_(event_ids))
                .with_for_update(of=Event, read=True, skip_locked=True))

    async def _classify_preview_residents(self, ticket: int, event_ids: list[int]) -> None:
        from types import SimpleNamespace
        from app.tasks.base import get_task_session
        from app.utils.blend_preview import registry

        factory = self._session_factory or get_task_session

        async def classify(gate):
            async with self._session_slot():
                if gate is not None:
                    gate.reading = True
                async with factory() as session:
                    rows = (await session.execute(
                        self._reservation_context_query(event_ids[:32]))).all()
                    if gate is not None and gate.read_done():
                        return
                    ops = []
                    for row in rows:
                        context = SimpleNamespace(**dict(row._mapping))
                        op = registry().classify(context.id, self.source, context,
                                                 context.preview_rev, ticket)
                        if op is not None:
                            ops.append(op)
                    # Keep fresh context locked until Redis has acknowledged accounting.
                    await self._prepare_ledger_previews(ops)

        await self._optional_db_in_pass("preview_capacity", classify,
                                        _optional_db_key(event_ids[:32]))

    async def _retire_policy_preview_event(
        self, event_id: int, ticket: int, deadline_ms: int, when: float,
    ) -> None:
        await self._retire_policy_preview_events([event_id], ticket, deadline_ms, when)

    async def _retire_policy_preview_events(
        self, event_ids: list[int], ticket: int, deadline_ms: int, when: float,
    ) -> None:
        """Fresh locked policy proof, separate from future-idle lifecycle proof.

        Redis checks every contributor's owner/deadline atomically and only
        reclaims a charged full/debt bucket. No valid preview is evicted.
        An uncertain reply keeps the proof locked through the pass deadline;
        Redis refuses retirement at/after its paired cutoff. Clock changes and
        involuntary lock loss retain the same residuals as idle retirement.
        The whole batch is one locked statement after ``ticket`` and one
        Redis connection (`LedgerRegistry.prepare_retirements`).
        """
        from types import SimpleNamespace
        from app.tasks.base import get_task_session
        from app.utils.blend_preview import registry

        factory = self._session_factory or get_task_session
        order = {eid: index for index, eid in enumerate(event_ids)}

        async def retire(gate):
            async with self._session_slot():
                if gate is not None:
                    gate.reading = True
                async with factory() as session:
                    rows = (await session.execute(
                        self._reservation_context_query(event_ids))).all()
                    # A read the pass deadline outlived proves nothing now.
                    if gate is not None and gate.read_done() or not rows:
                        return None
                    ops = []
                    for row in sorted(rows, key=lambda row: order[row.id]):
                        context = SimpleNamespace(**dict(row._mapping))
                        op = registry().retire_policy(context.id, self.source, context,
                                                     context.preview_rev, ticket, deadline_ms)
                        if op is not None:
                            op["send_before"] = when
                            ops.append(op)
                    if not ops:
                        return []
                    try:
                        return await self._prepare_ledger_previews(ops)
                    except BaseException as exc:
                        await self._hold_idle_proof_until(when, exc)

        frames = await self._optional_db_in_pass("preview_capacity", retire,
                                                 _optional_db_key(event_ids))
        if frames is not None:
            await self._publish_previews(frames)

    async def _retire_idle_preview_event(
        self, event_id: int, ticket: int, deadline_ms: int, when: float,
    ) -> None:
        await self._retire_idle_preview_events([event_id], ticket, deadline_ms, when)

    async def _retire_idle_preview_events(
        self, event_ids: list[int], ticket: int, deadline_ms: int, when: float,
    ) -> None:
        """Skip busy rows; hold fresh future-scheduled proof through mutation.

        An absent locked result means protected, missing or locked; none authorizes
        missing-row retirement. Publication happens after releasing the rows.
        An uncertain outcome keeps the locks until the pass deadline; Redis
        refuses execution at/after its paired cutoff. Redis clock rollback,
        rate drift/failover and involuntary DB lock loss remain residuals:
        this is not distributed atomicity across the two stores. The whole
        batch is one locked statement after ``ticket`` and one Redis
        connection (`LedgerRegistry.prepare_retirements`).
        """
        from sqlalchemy import func, select
        from app.models.models import Event
        from app.tasks.base import get_task_session
        from app.utils.blend_preview import registry

        factory = self._session_factory or get_task_session
        order = {eid: index for index, eid in enumerate(event_ids)}

        async def retire(gate):
            async with self._session_slot():
                if gate is not None:
                    gate.reading = True
                async with factory() as session:
                    rows = (await session.execute(select(
                        Event.id, Event.win_probability_sources_rev,
                    ).where(
                        Event.id.in_(event_ids), Event.status == "scheduled",
                        Event.commence_time.is_not(None), Event.commence_time > func.now(),
                        Event.completed_at.is_(None),
                    ).with_for_update(read=True, skip_locked=True))).all()
                    # A read the pass deadline outlived proves nothing now.
                    if gate is not None and gate.read_done() or not rows:
                        return None
                    operations = []
                    for event_id, rev in sorted(rows, key=lambda row: order[row[0]]):
                        operation = registry().retire_idle(event_id, self.source, rev, ticket,
                                                           deadline_ms)
                        # The authority registry refuses a ticket of another
                        # owner or domain: no operation, as for policy.
                        if operation is not None:
                            operation["send_before"] = when
                            operations.append(operation)
                    if not operations:
                        return []
                    try:
                        return await self._prepare_ledger_previews(operations)
                    except BaseException as exc:
                        # Before session rollback releases FOR SHARE, including on
                        # shutdown, transport errors and repeated cancellation from
                        # the outer timeout.
                        await self._hold_idle_proof_until(when, exc)

        frames = await self._optional_db_in_pass("preview_capacity", retire,
                                                 _optional_db_key(event_ids))
        if frames is not None:
            await self._publish_previews(frames)

    @staticmethod
    async def _hold_idle_proof_until(when: float, error: BaseException) -> None:
        first_cancel = error if isinstance(error, asyncio.CancelledError) else None
        loop = asyncio.get_running_loop()
        while loop.time() < when:
            try:
                await asyncio.sleep(max(0.0, when - loop.time()))
            except asyncio.CancelledError as exc:
                if first_cancel is None:
                    first_cancel = exc
        # Never uncancel: the outer timeout must see a prior shutdown cancellation.
        if first_cancel is not None:
            raise first_cancel
        raise error

    async def _close_preview_maintenance(self):
        self._preview_maintenance_closed = True
        task = self._preview_maintenance_task
        if task is None:
            return
        if not task.done():
            task.cancel()
        interrupted = None
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError as exc:
                interrupted = exc
        if not task.cancelled():
            task.exception()
        if interrupted is not None:
            raise interrupted

    async def _preview_admission_read(self) -> Optional[int]:
        """Read-before-admit ticket, without capacity scans on the flush path."""
        from app.utils.blend_preview import registry
        if not registry().ledger:
            return None
        self._start_preview_maintenance()
        try:
            async with asyncio.timeout(.25):
                before, _ = await self._preview_ticket()
                return before
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning("live_blend_refresh[%s]: preview admission read unavailable", self.source,
                           exc_info=True)
            return None

    async def _retire_terminal_preview_read(self, grouped, ticket: int) -> None:
        from app.utils.blend_preview import PREVIEW_STATUSES, registry

        preview = registry()
        for event_id, (event, _group) in grouped.items():
            if event_id not in self.preview_events:
                continue
            if event.status not in PREVIEW_STATUSES or event.completed_at is not None:
                rev = getattr(event, "preview_rev", None)
                if type(rev) is int and rev >= 0:
                    # One retirement per statement ticket. A racing retirement
                    # refuses this one; it must wait for another real read.
                    await self._retire_preview_event(event_id, rev, ticket)
                    return

    async def _retire_preview_event(self, event_id: int, read_rev: int, ticket: int) -> None:
        """Preserve an ineligible row's floor before forgetting Redis state.

        A fresh read alone is insufficient: source revisions do not change on
        status-only updates. Under the event row lock, this conditional SQL
        increment leaves every future read strictly above the retired floor.
        It changes neither source values nor observation timestamps. A failed
        or timed-out transaction leaves the existing Redis guard in place.
        """
        from sqlalchemy import update
        from app.models.models import Event
        from app.tasks.base import get_task_session
        from app.utils.blend_preview import registry

        preview = registry()
        try:
            async with asyncio.timeout(.25):
                # Close the preview first, including if the durable advance
                # cannot acquire its row. Later duplicate terminal operations
                # carry the old ticket and cannot recreate retired state.
                await self._publish_previews([
                    preview.terminal_read(event_id, self.source, read_rev, ticket),
                ])
                factory = self._session_factory or get_task_session
                async with factory() as session:
                    durable = (await session.execute(update(Event).where(
                        Event.id == event_id,
                        self._preview_retirable_row(),
                        Event.win_probability_sources_rev >= read_rev,
                        Event.win_probability_sources_rev < 9007199254740991,
                    ).values(win_probability_sources_rev=Event.win_probability_sources_rev + 1)
                      .returning(Event.win_probability_sources_rev))).scalar_one_or_none()
                    if durable is None:
                        return
                    await session.commit()
                # Only a successful COMMIT can authorize deletion. Redis
                # still checks ticket, owners, and all event-local floors.
                await self._publish_previews([
                    preview.retire_read(event_id, self.source, durable - 1, ticket,
                                        committed_rev=durable),
                ])
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning("live_blend_refresh[%s]: preview retirement incomplete", self.source,
                           exc_info=True)

    async def _prepare_ledger_previews(self, items: list) -> list[dict]:
        """TSP-1: run settlement operations now, so their frames can be ordered.

        Single-source registries already return frames: unchanged. A failure
        costs only the preview (the frames are dropped), never the commit.
        """
        if not items or not any("ledger_op" in item for item in items):
            return items
        idle = [item for item in items if item.get("ledger_op") in ("retire_idle", "retire_policy")]
        send_before = min((item["send_before"] for item in idle), default=None)
        try:
            from app.utils.blend_preview import registry
            from app.utils.market_quote_push import _checkout

            preview = registry()
            async with asyncio.timeout(1):
                if preview.claim_lock is None:
                    preview.claim_lock = asyncio.Lock()
                pool = self._client().connection_pool
                async with preview.claim_lock:
                    connection = await _checkout(pool)
                    first_error = None
                    try:
                        if preview.unclaimed(self.source):
                            await self._claim_preview_epoch(connection, preview)
                        call = (self._preview_call(connection, send_before=send_before)
                                if idle else self._preview_call(connection))
                        if idle and len(idle) == len(items):
                            # One capacity batch, proved by one locked read.
                            return await preview.prepare_retirements(items, call,
                                                                     self.preview_stats)
                        return await preview.prepare(items, call, self.preview_stats)
                    except BaseException as exc:
                        first_error = exc
                        self._redis = None
                        try:
                            await connection.disconnect()
                        except BaseException as cleanup_error:
                            # A shutdown may arrive while cleaning up an ordinary
                            # transport failure. Preserve the first cancellation.
                            if (isinstance(cleanup_error, asyncio.CancelledError)
                                    and not isinstance(first_error, asyncio.CancelledError)):
                                first_error = cleanup_error
                        raise first_error
                    finally:
                        try:
                            await pool.release(connection)
                        except BaseException as cleanup_error:
                            if (isinstance(cleanup_error, asyncio.CancelledError)
                                    and not isinstance(first_error, asyncio.CancelledError)):
                                first_error = cleanup_error
                            if first_error is not None:
                                raise first_error
                            raise
        except Exception as exc:
            self.preview_stats["publish_errors"] += 1
            logger.warning(
                "live_blend_refresh[%s]: ledger preview settlement incomplete (%s operations)",
                self.source, len(items), exc_info=True,
            )
            if idle:
                raise PreviewSettlementUncertain("idle retirement reply unavailable") from exc
            return []

    async def _publish_previews(self, frames: list[dict], *, prepare_frames=None) -> None:
        """Fenced PUBLISH of provisional frames. Never raises; never retained.

        Not `_publish`: a preview has no revision, owes no recovery intent and
        must never be counted, acknowledged or replayed as a committed frame.
        Same direct pool protocol, so a borrowed socket left in an unknown
        state is disconnected rather than returned.

        The process normally claimed its epoch at startup
        (`claim_preview_display`); if that claim failed, the first call here
        claims it. Every batch then goes through `FENCE_PUBLISH_SCRIPT`, which
        drops the blends of a process another worker has superseded. No
        epoch, no blend.
        """
        if not frames and prepare_frames is None:
            return
        try:
            import json

            from app.utils.blend_preview import (
                FENCE_PUBLISH_SCRIPT, fence_owner_key, registry,
            )
            from app.utils.live_push import event_channel
            from app.utils.market_quote_push import _checkout

            preview = registry()
            owner_key = fence_owner_key(self.source)
            async with asyncio.timeout(1):
                if preview.claim_lock is None:
                    preview.claim_lock = asyncio.Lock()
                pool = self._client().connection_pool
                async with preview.claim_lock:
                    connection = await _checkout(pool)
                    try:
                        if preview.unclaimed(self.source):
                            await self._claim_preview_epoch(connection, preview)
                        if prepare_frames is not None:
                            frames = await prepare_frames()
                            if not frames:
                                return
                        if preview.ledger:
                            # TSP-1: operations and prepared frames run through
                            # the ledger CAS; nothing is relabeled here.
                            # #10090: the stage trace and the preview receipt
                            # see each send, after it; neither changes it.
                            observe = self._preview_observer()
                            await preview.execute(
                                frames, self._preview_call(connection), event_channel,
                                self.preview_stats,
                                **({} if observe is None else {"observe": observe}),
                            )
                            return
                        # A blend composed before this lock may be older than a
                        # revoke another batch sent while it waited (#10090).
                        kept = [f for f in frames if not preview.withdrawn(f)]
                        if len(kept) < len(frames):
                            self.preview_stats["withdrawn"] = (
                                self.preview_stats.get("withdrawn", 0) + len(frames) - len(kept)
                            )
                            frames = kept
                            if not frames:
                                return
                        argv: list = [preview.epoch]
                        for frame in frames:
                            preview.sending(frame)
                            frame["preview"]["epoch"] = preview.epoch
                            argv.extend((
                                frame["preview"]["kind"],
                                event_channel(frame["event_id"]),
                                json.dumps(frame),
                            ))
                        await connection.send_command(
                            "EVAL", FENCE_PUBLISH_SCRIPT, 1, owner_key, *argv,
                        )
                        published, fenced, owner = await connection.read_response()
                    except BaseException:
                        self._redis = None
                        await connection.disconnect()
                        raise
                    finally:
                        await pool.release(connection)
            revokes = sum(1 for f in frames if f["preview"]["kind"] == "revoke")
            self.preview_stats["revoked"] += revokes
            self.preview_stats["published"] += int(published) - revokes
            if int(fenced):
                self.preview_stats["fenced"] += int(fenced)
                if isinstance(owner, bytes):
                    owner = owner.decode()
                logger.warning(
                    "live_blend_refresh[%s]: %s preview frame(s) fenced: epoch=%s owner=%s",
                    self.source, fenced, preview.epoch, owner or "missing",
                )
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning(
                "live_blend_refresh[%s]: preview publication incomplete (%s frames)",
                self.source, len(frames), exc_info=True,
            )

    async def _maybe_snapshot(
        self, session, event_id: int, value: float, reading, now: float,
    ) -> None:
        """Append this reading to the chart series, on the snapshot clock.

        Called only after a blend stamp actually happened, which on a FLAT
        market is the `unchanged_restamp_interval_s` beat (45s) rather than the
        2s blend beat. `_create_or_update_win_prob_snapshot` is the same helper
        the 120s poll uses — it appends a row on a value CHANGE and, since
        live/035, also once `max_gap_seconds` of silence have passed, so a
        motionless market still draws a breathing line instead of one straight
        segment between its endpoints.

        Failures are swallowed and counted like everything else in this module:
        the chart is downstream of the number, and a snapshot that cannot be
        written must not cost the blend stamp that already succeeded.
        """
        # #11181: an owned point was spaced by the reservation that admitted
        # it, and its custody row is settled with it, so it is never skipped
        # here. A point loaded from custody has no clock of this process.
        owned = getattr(reading, "owned_history", False)
        if now is not None:
            last = self._last_snapshot_at.get(event_id)
            if not owned and last is not None and (now - last) < self.snapshot_interval_s:
                return
            self._last_snapshot_at[event_id] = now

        try:
            from app.tasks.snapshots import _create_or_update_win_prob_snapshot
            from app.tasks.prediction_market_matching import _second_slot

            # #6277 — THE SAME SECOND SLOT THE 15-MINUTE MATCHER WRITES, from the
            # same helper. This lane recomputes the number every few seconds from
            # the same rows, so a partition published by the matcher and
            # complemented here would be overwritten with the fabricated value
            # within one tick — during the match, which is the window the
            # photographed card was taken in. The two writers disagreeing is the
            # one thing this module exists to prevent, and it applies to the away
            # slot exactly as it applies to the home one.
            away_value, draw_value = _second_slot(reading, value)

            snapshot, is_new = await _create_or_update_win_prob_snapshot(
                session,
                event_id=event_id,
                source=self.source,
                home_win_probability=value,
                away_win_probability=round(away_value, 4),
                draw_probability=None if draw_value is None else round(draw_value, 4),
                game_state={
                    "market_name": getattr(reading.market, "name", None),
                    "market_id": getattr(reading.market, "id", None),
                    "outcome_name": getattr(reading.outcome, "name", None),
                    "yes_probability": reading.yes_probability,
                    # Distinguishable from the poll's "live_fast" in the audit
                    # trail, so "which writer produced this point" stays a
                    # question the data can answer.
                    "poll_type": "ws_fast_lane",
                },
                max_gap_seconds=heartbeat_deadline(
                    self.snapshot_max_gap_s, self.snapshot_interval_s
                ),
                observed_at=getattr(reading, "snapshot_observed_at", None),
            )
            if is_new:
                session.add(snapshot)
                self.stats["snapshots_written"] += 1
            else:
                self.stats["snapshots_deduped"] += 1
        except Exception:
            if getattr(reading, "owned_history", False):
                raise
            self.stats["errors"] += 1
            logger.exception(
                "live_blend_refresh[%s]: snapshot failed for event %s",
                self.source, event_id,
            )

    def _should_write(self, event_id: int, value: float, now: float) -> bool:
        """Write on any real move; on no move, re-stamp only occasionally.

        The re-stamp is not cosmetic. `updated_at` feeds the hero's RELATIVE
        recency decay, so a source that keeps quoting the same price must keep
        saying so or it slowly loses weight against noisier siblings and the
        blend drifts toward whichever source moves most.
        """
        previous = self._last_written_value.get(event_id)
        if previous is None or previous != value:
            return True
        last_write = self._last_write_at.get(event_id, 0.0)
        return (now - last_write) >= self.unchanged_restamp_interval_s


def event_ids_for_outcomes(
    outcome_to_event: dict[int, Optional[int]], outcome_ids: Iterable[int]
) -> set[int]:
    """The distinct linked event ids behind a batch of flushed outcomes."""
    seen: set[int] = set()
    for outcome_id in outcome_ids:
        event_id = outcome_to_event.get(outcome_id)
        if event_id is not None:
            seen.add(event_id)
    return seen


# ── #9462 review: owed stamps survive a recycle ──────────────────────────────
#
# Each consumer run builds a NEW refresher, and the final drain stops as soon as
# the price buffer is empty. A price committed inside the 2 s throttle (or behind
# a row lock) is held in `_throttle_deferred` / `_lock_retry` and stamped by a
# LATER flush — but at a recycle there is no later flush in this run, and the
# next run's refresher started empty. The outcome price stayed in the database;
# the number on the card waited for another venue tick or the 120 s poll. #9418's
# admission recycle made that end-of-run far more frequent.
#
# So the ending run hands its owed events to the next run of the same source,
# which adopts them before its first flush. Process-local on purpose: the two
# consumers of a dyno run in one process, and a restart takes the owed stamps
# with it exactly as it takes the socket. A hand-off older than
# `PENDING_HANDOFF_TTL_S` is dropped — by then the poll has restamped the event.

#: The oldest hand-off a new run adopts. The 120 s poll restamps every live
#: event on its own; carrying a stamp past that would only re-date its work.
PENDING_HANDOFF_TTL_S = 120.0

_pending_handoff: dict[str, tuple[float, frozenset]] = {}
_history_handoff: dict[str, tuple] = {}


def hand_off_pending(refresher) -> int:
    """Leave `refresher`'s owed stamps for the next run of its source.

    Returns how many blend events were handed off. Committed history scalars
    travel separately, without the blend handoff's age cutoff. Its owner must
    already be joined; a legacy/test refresher without that owner is supported.
    Both consumers call this in their teardown `finally`, so it also closes the
    run's idle bound sampler; their `reap_stopped_loops` then joins it.
    """
    held = getattr(refresher, "held_quotes", None)
    if isinstance(held, HeldRowQuotes):
        _park_closing_sampler(getattr(refresher, "source", None), held.close())
    try:
        if refresher._history_task is not None and not refresher._history_task.done():
            raise RuntimeError("history owner must join before handing off its debt")
        debt = tuple((eid, value, reading, at) for eid, value, reading, at, _ in refresher._history)
        if debt:
            _history_handoff[refresher.source] = debt
            refresher._history.clear()
            refresher._history_count = 0
            refresher._history_reserved.clear()
        else:
            _history_handoff.pop(refresher.source, None)
    except AttributeError:
        pass  # legacy/test refresher without a chart owner
    try:
        pending = frozenset(refresher.pending_event_ids())
        # #11317 P2: a parked refused pair is owed too; the next run's book
        # decides it again (`adopt_pending` makes it due once).
        pending |= frozenset(getattr(refresher, "_book_refused", ()))
    except Exception:
        return 0
    if pending:
        _pending_handoff[refresher.source] = (_mono(), pending)
    else:
        _pending_handoff.pop(refresher.source, None)
    return len(pending)


def adopt_handed_off(refresher) -> int:
    """Give `refresher` the stamps the previous run of its source still owed.

    Returns how many blend events were adopted (0 when none, too old, or the
    refresher cannot adopt). History is separate committed observation debt and
    keeps its original times through a recycle, even after a later poll point.
    """
    try:
        debt = _history_handoff.pop(refresher.source, ())
        for eid, value, reading, at in debt:
            ready = asyncio.Event()
            ready.set()
            refresher._history.append((eid, value, reading, at, ready))
            refresher._history_count += 1
            if at is not None:  # a point loaded from custody carries no clock
                refresher._history_reserved[eid] = at
    except AttributeError:
        pass
    try:
        handed = _pending_handoff.pop(refresher.source, None)
    except Exception:
        return 0
    if handed is None:
        return 0
    at, pending = handed
    if _mono() - at > PENDING_HANDOFF_TTL_S:
        return 0
    try:
        refresher.adopt_pending(pending)
    except Exception:
        return 0
    return len(pending)
