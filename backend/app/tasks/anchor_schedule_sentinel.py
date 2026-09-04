"""Nightly, read-only driver for the anchor-schedule rail. #2853.

WHAT THIS IS FOR
════════════════

``app/tasks/reconcile_anchor_schedule`` can already ask the authority what game
each anchor names, and it has been able to since #2697. It just never ran unless
a person opened an admin endpoint and asked. That is the whole defect #2853
reports, and it is not a small one: the rail's entire reason to exist is the
December anchor on a September row — the row no scoreboard pass visits — and a
rail that waits to be asked catches that row when somebody happens to wonder.
For #2804 nobody wondered until days after the wrong kickoff was already on a
team page.

**SHIP: a schedule error like #2804's stops reaching a fan's screen, because the
system catches it the night it appears instead of a human catching it days
before kickoff.** (Pillar: TRUTH.)

WHAT IT WILL NOT DO
═══════════════════

**It never writes.** ``apply`` is not a parameter of this module and
:func:`reconcile` is called with ``apply=False`` at the one call site. The
attended apply stays a human's, for the reason the rail's own docstring gives:
the moves are large and a reviewer should see the plan. This driver's product is
a *report* — the plan, and an issue on the board naming it.

The one thing it writes is a GitHub issue, through the shared sentinel filing
rail, which is what every other sentinel does and is not a data write.

WHAT IT CANNOT SEE — SAY IT IN THE ISSUE, NOT JUST HERE
═══════════════════════════════════════════════════════

The population is ``espn_id IS NOT NULL``. So this sentinel reports **schedule
drift on anchored rows** and nothing else. It is blind to:

  * **id-less twins** — #2857's Towson ghost carries no ``espn_id`` at all;
  * **the preseason twins** — #2866's 47 NFL pairs, whose entire sport key is
    ``espn_id IS NULL`` (50/50 rows);
  * **tennis**, which is excluded on purpose (see ``EXCLUDED_SPORT_KEYS``).

Those are real duplicates that this rail will report a clean night on. The
issue body says so in as many words, because a sentinel whose silence is read
as "the event graph is fine" is worse than no sentinel.

THE BUDGET, AND WHY IT IS WALL-CLOCK AND NOT A ROW COUNT
════════════════════════════════════════════════════════

One ``summary?event=`` call per row, **~0.59s re-measured against production on
2026-09-04** (#2953 — the ~0.2s this paragraph used to claim was wrong by 3x,
and the endpoint's row bound was built on it). The window held 685 anchored rows
the day the rail was written (239 NFL alone), so a full sweep is ~400s of
upstream time on a good night — more than one night's deadline, which is exactly
why the continuation below is load-bearing rather than a nicety. And good nights
are not the ones to size for. The sibling endpoint one door over (``authority-id-collisions``,
#2864) went to a 30s H12 on exactly this shape, and lane1/082 measured its
*3-group* call at 19.3s and 2.0s minutes apart: the per-row cost has a heavy
tail that lives upstream, outside our control.

So the bound is a deadline plus a page cap, and a run that hits either stops and
says ``partial`` — it does not keep going and it does not call a short sweep
clean.

**And a bounded run that stops must hand on WHERE it stopped, or the bound turns
into a blind spot (CERT-843).** A budget alone, with every night starting at the
oldest row, means a window bigger than one night's budget has a tail that is
never examined at all: the rail rescans the same front slice forever, reports a
clean census of it every morning, and a bad anchor sitting behind the cutoff
stays on a team page indefinitely. That is strictly worse than not paging,
because the report looks finished. So the continuation is persisted between runs
(``CURSOR_STATE_KEY``) and cleared when a sweep actually reaches the end.

Two consequences that are easy to get wrong and are guarded:

  * a **resumed** run that reaches the end of the window has seen only the tail,
    so that RUN is not complete and may not close the issue on its own; and
  * a saved cursor points into a **moving** window, so it can age out entirely —
    an exhausted resume restarts from the oldest row inside the same run rather
    than stalling silently on zero rows every night.

THE UNION IS THE THING THAT CLOSES — NOT ANY ONE RUN (#2983)
════════════════════════════════════════════════════════════

Those two consequences, taken together, produced a sentinel that could file and
could never close. The close was gated on one run having reached the end of the
window *without resuming*, and no such night exists at this population: a fresh
run cannot cover 685 rows in a 300s deadline (night one measured 600 of 685,
``stopped_by: deadline``), and the night that does reach the end gets there by
resuming. An alert that can never go green is one people stop reading.

Coverage was never the problem — nights one and two together see the whole
window, which is what the continuation is for. What was missing was anything
that recorded the UNION. So a **window pass** is tracked beside the position:

  * a run that starts at the oldest row **begins** a pass;
  * a run that resumes **continues** the pass its predecessor began;
  * a chain that reaches the end of the window with its pass intact has seen
    the window, and *that* is what may close.

Three things can void a pass, and each fails toward "cannot close" rather than
toward a wrong green:

  * **A broken chain.** Resuming with no marker to continue (the marker was lost,
    or it predates this mechanism) still sweeps — the position is good — but
    cannot claim the union. One extra cycle, then a clean pass.
  * **An expired pass** (:data:`MAX_PASS_AGE_SECONDS`). A close asserts the
    window is clean *now*; the oldest observation in a chain is as old as the
    pass. Note the deliberate asymmetry: expiry voids the CLAIM and never the
    POSITION, because clearing the continuation here would restart the sweep at
    the oldest row every cycle and hand CERT-843's blind spot straight back. A
    window that has outgrown its budget therefore stops closing — *visibly*,
    via ``PASS-EXPIRED`` on the operator line, which is the loud version of the
    failure #2983 reported as a silent one.
  * **Drift seen anywhere in the chain.** The trap this mechanism creates if
    built naively: night one files 5 drifting rows, night two sweeps a clean
    tail and reaches the end — and closes an issue whose 5 rows are still
    wrong. GREEN is the pass's verdict, not the last run's.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.tasks.reconcile_anchor_schedule import (
    DEFAULT_HORIZON,
    DEFAULT_LOOKBACK,
    EXCLUDED_SPORT_KEYS,
    reconcile,
)
from app.utils.anchor_schedule import SCHEDULE_VERDICTS

logger = logging.getLogger(__name__)

#: Stop paging after this much wall clock. 300s sits well inside the 840s soft
#: limit the Celery wrapper carries, leaving the filing round-trip room even on
#: a night when the last page is the slow one.
DEFAULT_DEADLINE_SECONDS = 300.0

#: And stop after this many pages regardless. The deadline alone would be enough
#: if every page were slow; the page cap is what bounds a night when every page
#: is FAST, because then the deadline buys thousands of upstream calls nobody
#: asked for. Two bounds, two different runaway shapes.
DEFAULT_MAX_PAGES = 12

#: This sweep's OWN page size, and the reason it is not ``reconcile``'s.
#:
#: `reconcile.DEFAULT_LIMIT` is a **router** bound — it exists because the admin
#: endpoint has 30 seconds before Heroku kills it. This task has no router: it
#: runs in a Celery worker under :data:`DEFAULT_DEADLINE_SECONDS`. When #2953
#: cut the shared default from 100 to 25 for the endpoint's sake, this sweep
#: would have inherited it and gone from ~500 rows a night (300s ÷ ~59s a page)
#: to 300 (:data:`DEFAULT_MAX_PAGES` × 25), because the page cap binds first at
#: the smaller size — a 40% cut in nightly reach, bought for a constraint this
#: caller does not have.
#:
#: 100 rows at the measured ~0.59s/row is ~59s, so ~5 pages fit the deadline and
#: the page cap stays slack. Stated here, in the caller that owns the budget.
SWEEP_PAGE_LIMIT = 100

#: The per-page wall clock, matched to :data:`SWEEP_PAGE_LIMIT` above.
#:
#: `reconcile` cuts a page at its own ``budget_seconds``, whose default is the
#: endpoint's 18s. Left alone that would truncate every page of this sweep at
#: ~30 rows and hand back a cursor, quietly turning the page cap into the real
#: bound again. 70s clears a full 100-row page (~59s) with headroom for a slow
#: night, and still lands ~4 pages inside the 300s deadline.
SWEEP_PAGE_BUDGET_SECONDS = 70.0

#: The dedupe marker. One canonical issue for this sentinel, re-pointed at the
#: current observation on each RED night and closed on a clean COMPLETE sweep.
MARKER_KEY = "anchor-schedule-sentinel-fingerprint"

#: What the issue is called. The filing rail matches on the declaration first and
#: falls back to this prefix, so it must stay stable across nights.
TITLE_PREFIX = "Anchor-schedule drift"


#: Where the continuation between nights lives (CERT-843). Redis, not a column:
#: it is scheduling scratch, it is worthless the moment the window moves past
#: it, and a migration for it would outlive its usefulness by years.
CURSOR_STATE_KEY = "anchor_schedule_sentinel:continuation"

#: Long enough to survive a few missed nights, short enough that a cursor from a
#: dead era expires instead of being resumed into a window that no longer holds
#: it. The exhausted-resume restart handles the case anyway; this is the belt.
CURSOR_STATE_TTL_SECONDS = 7 * 24 * 3600

#: Where the WINDOW-PASS marker lives (#2983) — beside the continuation, not
#: inside it.
#:
#: A second key on purpose. The continuation is a POSITION; the pass is a CLAIM
#: about a chain of runs, and the two fail in opposite directions. Losing the
#: position costs coverage, so it is worth protecting; losing the claim costs
#: one cycle's close, which is the harmless direction. Folding both into one
#: blob would let a marker write failure take the position with it, and would
#: change the format of a key that is live in production right now — a legacy
#: bare cursor with no marker beside it reads as a broken chain, which is
#: exactly the safe way for this to arrive.
#:
#: **The marker names the cursor it was written beside, and a mismatch is a
#: broken chain** (CERT-896). Two keys cannot be written atomically, and both
#: writes swallow their exceptions, so the pairing can come apart: the night
#: that finds drift advances the cursor, its ``drift_seen: true`` write fails,
#: and the store is left holding an ADVANCED position beside a STALE CLEAN
#: claim. The next clean tail would then reach the end of the window with
#: ``pass_drift_seen`` false and close an issue whose rows are still wrong —
#: the exact failure the drift-seen rule exists to prevent, walked in through
#: the persistence layer. Binding detects the divergence instead of trying to
#: prevent it, which is the only option available across two keys; the writes
#: are additionally ordered marker-first so the likely crack falls the
#: conservative way.
PASS_STATE_KEY = "anchor_schedule_sentinel:window_pass"

#: How long a pass may stay open before it stops being evidence about tonight.
#:
#: Closing asserts "no anchored row in the window disagrees with its authority"
#: — now, not last week. The oldest observation in a chain is as old as the pass
#: itself, so past this bound the window floor has moved days beyond where the
#: pass began and rows have been re-anchored since. Three nights covers the
#: two-night steady state plus a missed run, and sits well inside
#: :data:`CURSOR_STATE_TTL_SECONDS` so the position always outlives the claim
#: rather than the other way round.
MAX_PASS_AGE_SECONDS = 3 * 24 * 3600


def _load_continuation() -> Optional[str]:
    """Last night's position, or ``None`` to start at the oldest row.

    A Redis fault degrades to ``None`` — a full restart from the front, which is
    exactly the pre-CERT-843 behaviour. That is the right way to fail: the rail
    still runs and still reports, it just loses its place. Raising here would
    trade a partial sweep for no sweep at all.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(CURSOR_STATE_KEY)
    except Exception:  # pragma: no cover - defensive, exercised by the fault test
        logger.warning(
            "anchor-schedule sentinel: could not read the saved continuation; "
            "starting from the oldest row",
            exc_info=True,
        )
        return None
    if not raw:
        return None
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)


def _save_continuation(cursor: Optional[str]) -> None:
    """Hand tonight's position to tomorrow, or clear it on a finished sweep.

    ``None`` DELETES rather than writing an empty string: a stale key that reads
    as falsy-but-present is the kind of state that survives a fix and confuses
    the next reader.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        if cursor:
            client.setex(CURSOR_STATE_KEY, CURSOR_STATE_TTL_SECONDS, cursor)
        else:
            client.delete(CURSOR_STATE_KEY)
    except Exception:  # pragma: no cover - defensive
        logger.warning(
            "anchor-schedule sentinel: could not persist the continuation; "
            "tomorrow's run will restart from the oldest row",
            exc_info=True,
        )


def _load_pass() -> Optional[tuple[datetime, bool, Optional[str]]]:
    """The open window pass as ``(started_at, drift_seen, cursor)``, or ``None``.

    ``cursor`` is the continuation this marker was written beside; the caller
    refuses the marker unless it matches the position actually being resumed
    from (CERT-896).

    ``None`` means "there is no chain here I can continue", and EVERY failure
    resolves to it: no key, a Redis fault, unparseable JSON, a shape this
    version does not recognise, a timestamp that will not parse. That is the
    safe direction for all of them without having to reason about each — a lost
    marker costs one extra cycle before the rail can go green, where a marker
    trusted wrongly closes a live drift issue.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(PASS_STATE_KEY)
    except Exception:  # pragma: no cover - defensive, exercised by the fault test
        logger.warning(
            "anchor-schedule sentinel: could not read the window-pass marker; "
            "this run cannot close the issue",
            exc_info=True,
        )
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        started_at = datetime.fromisoformat(data["started_at"])
    except Exception:
        logger.warning(
            "anchor-schedule sentinel: window-pass marker is unreadable (%r); "
            "treating the chain as broken",
            raw,
        )
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    cursor = data.get("cursor")
    return started_at, bool(data.get("drift_seen")), cursor if cursor else None


def _save_pass(started_at: datetime, drift_seen: bool, cursor: Optional[str]) -> None:
    """Carry the open pass to the next night, bound to the position beside it.

    ``cursor`` is not decoration: it is what lets the next run detect that these
    two keys came apart (CERT-896). It must be the SAME continuation this run is
    handing on, which is why this is called with ``state["continuation"]`` and
    before the continuation is written.

    Shares :data:`CURSOR_STATE_TTL_SECONDS` with the continuation so the two
    cannot outlive each other in the dangerous order (a marker older than the
    position it describes would claim a chain that no longer exists).
    """
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(
            PASS_STATE_KEY,
            CURSOR_STATE_TTL_SECONDS,
            json.dumps(
                {
                    "started_at": started_at.isoformat(),
                    "drift_seen": bool(drift_seen),
                    "cursor": cursor,
                }
            ),
        )
    except Exception:  # pragma: no cover - defensive
        logger.warning(
            "anchor-schedule sentinel: could not persist the window-pass marker; "
            "tomorrow's run will treat the chain as broken",
            exc_info=True,
        )


def _clear_pass() -> None:
    """End the pass — it finished, it expired, or there was never one."""
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().delete(PASS_STATE_KEY)
    except Exception:  # pragma: no cover - defensive
        logger.warning(
            "anchor-schedule sentinel: could not clear the window-pass marker",
            exc_info=True,
        )


def _blind_spots_note() -> str:
    """The paragraph that keeps a green night from being read as a clean graph."""
    return (
        "**What a clean run here does NOT mean.** This sentinel's population is "
        "`espn_id IS NOT NULL`, so it reports schedule drift on *anchored* rows "
        "only. It is structurally blind to id-less duplicates (#2857's Towson "
        "ghost has no `espn_id`) and to the NFL preseason twins (#2866 — all 50 "
        "rows are `espn_id IS NULL`), and it excludes tennis on purpose (#2852 — "
        "ESPN answers for no tennis anchor, 20/20 `no_answer` measured). A green "
        "night from this rail is not a statement about the event graph."
    )


def _summarize(state: dict[str, Any]) -> str:
    """One operator line for the log and the issue body."""
    counts = " ".join(
        f"{name}={state['by_verdict'].get(name, 0)}" for name in SCHEDULE_VERDICTS
    )
    # Whether this run continued another one changes what its counts MEAN, so it
    # belongs on the line a reviewer reads, not only in the payload.
    where = " RESUMED" if state.get("resumed_from") else ""
    if state.get("continuation"):
        where += " CONTINUES-TOMORROW"
    # The three pass states an operator has to be able to tell apart when the
    # rail is not closing. Silent versions of these are what #2983 was.
    if state.get("pass_expired"):
        where += " PASS-EXPIRED"
    elif state.get("pass_open") is False:
        where += " CHAIN-BROKEN"
    if state.get("pass_drift_seen") and not state.get("moves"):
        where += " PASS-SAW-DRIFT-EARLIER"
    return (
        f"{state['terminal']}:{where} examined={state['examined']}/{state['eligible']} "
        f"pages={state['pages']} drift={len(state['moves'])} · {counts}"
    )


async def _sweep(
    session,
    *,
    limit: int,
    sport: Optional[str],
    lookback: timedelta,
    horizon: timedelta,
    deadline_seconds: float,
    max_pages: int,
    resume_from: Optional[str] = None,
) -> dict[str, Any]:
    """Page the rail read-only until the window ends or a bound is hit.

    ``reached_window_end`` is this SWEEP's word, not any one page's. The rail is
    explicit that whether a sweep finished is the driver's finding to report
    (see ``reconcile``'s paging docstring), so the per-page ``partial`` is
    expected and is not propagated — what matters is whether we reached the end
    of the window before a bound stopped us. Turning that into ``complete`` and
    a ``terminal`` is the caller's job, because it needs the window-pass marker
    this function does not hold (#2983).

    ═══ RESUMING, AND THE STALL IT MUST NOT CAUSE (CERT-843) ═══

    ``resume_from`` is last night's continuation. Without it a bounded run
    restarts at the oldest slice every night, so a window bigger than one
    night's budget means the TAIL IS NEVER EXAMINED — the rail rescans the same
    front rows forever while a bad anchor behind them stays on a team page. That
    is the defect this parameter exists to close, and it is worse than not
    paging at all, because the census each night looks clean and complete.

    But a saved cursor is a position in a MOVING window: the floor advances with
    ``now``, so a continuation can end up past the last row (every row it named
    aged out). ``reconcile`` answers that with zero rows, and a driver that
    simply stopped there would stall permanently — a *silent* stall, reporting
    ``partial`` every night having examined nothing. So an exhausted resume
    restarts from the oldest row inside the same run rather than ending it.
    """
    start = _time.monotonic()
    by_verdict: dict[str, int] = {name: 0 for name in SCHEDULE_VERDICTS}
    moves: list[dict] = []
    examined = 0
    eligible = 0
    pages = 0
    cursor: Optional[str] = resume_from
    stopped_by: Optional[str] = None
    dark_pages = 0
    resumed = resume_from is not None
    restarted_from_exhausted_cursor = False
    # The continuation to hand to tomorrow. Only meaningful when this run stops
    # early; a run that reached the end of the window has nothing to continue.
    continuation: Optional[str] = None

    while True:
        if pages >= max_pages:
            stopped_by = "max_pages"
            break
        if _time.monotonic() - start > deadline_seconds:
            stopped_by = "deadline"
            break

        page = await reconcile(
            session,
            # Not a default being relied on — the one call site states it.
            # This driver has no `apply` parameter to thread through, so there
            # is no path by which a caller can turn this into a write.
            apply=False,
            limit=limit,
            sport=sport,
            lookback=lookback,
            horizon=horizon,
            cursor=cursor,
            exclude_sports=EXCLUDED_SPORT_KEYS,
            # Stated for the same reason `apply` is: this caller is not behind
            # the router `reconcile`'s default is sized for, and inheriting it
            # would truncate every page here at ~30 rows (#2953).
            budget_seconds=SWEEP_PAGE_BUDGET_SECONDS,
        )
        pages += 1

        # A resume that named a position the window has moved past. Restart at
        # the oldest row now rather than ending the run: the alternative is a
        # sentinel that reports `partial` every night having examined nothing,
        # and nothing about that failure is loud.
        if (
            cursor is not None
            and page.get("examined", 0) == 0
            and not restarted_from_exhausted_cursor
        ):
            logger.info(
                "anchor-schedule sentinel: saved cursor is past the window; "
                "restarting from the oldest row"
            )
            restarted_from_exhausted_cursor = True
            resumed = False
            cursor = None
            continue

        # `eligible` is the whole window and is recounted per page against a
        # moving `now`; the LAST reading is the freshest, so take it rather than
        # summing (summing would multiply the window by the page count).
        eligible = page.get("eligible", 0)
        examined += page.get("examined", 0)
        for name, n in (page.get("by_verdict") or {}).items():
            by_verdict[name] = by_verdict.get(name, 0) + n
        moves.extend(page.get("moves") or [])

        if page.get("terminal") == "authority_dark":
            # A page where the authority answered for nothing tells us nothing
            # about those rows. Keep going once — a single dark page can be one
            # bad slice — but two in a row is an outage, and grinding through
            # ten more pages of it just spends the budget to learn the same
            # thing (and would file a "no drift" green on an unread window).
            dark_pages += 1
            if dark_pages >= 2:
                stopped_by = "authority_dark"
                break
        else:
            dark_pages = 0

        if not page.get("has_more"):
            break
        cursor = page.get("next_cursor")
        if not cursor:
            # has_more with no cursor would loop forever on the same page.
            stopped_by = "no_cursor"
            break
        # Where tomorrow starts if a bound stops us before the window ends. Held
        # per page rather than read off the last one, because the loop can exit
        # from the top (deadline/page cap) with `cursor` already advanced.
        continuation = cursor

    # A run that stopped early hands its position on. A run that reached the end
    # clears it, so the next night starts at the oldest row again — the window
    # is a moving front and yesterday's tail is not a useful place to begin a
    # fresh pass.
    if stopped_by is None:
        continuation = None

    # This sweep reports what IT did; whether the WINDOW has been seen is a
    # question about the chain this run belongs to, and only the caller holds
    # the pass marker that answers it (#2983). Reaching the end while resumed
    # means this run saw the TAIL — that is a fact about the run, and it is a
    # necessary but not sufficient condition for the close.
    return {
        "measured": True,
        "reached_window_end": stopped_by is None,
        "resumed": resumed,
        "stopped_by": stopped_by,
        "resumed_from": resume_from,
        "restarted_from_exhausted_cursor": restarted_from_exhausted_cursor,
        "continuation": continuation,
        "applied": False,
        "pages": pages,
        "examined": examined,
        "eligible": eligible,
        "by_verdict": by_verdict,
        "moves": moves,
        "elapsed_seconds": round(_time.monotonic() - start, 1),
    }


def _issue_body(state: dict[str, Any], *, now: datetime) -> str:
    """The evidence pack: what drifted, by how much, and what to do about it."""
    lines = [
        f"The nightly anchor-schedule sweep found **{len(state['moves'])} row(s)** whose "
        "kickoff disagrees with the game their own ESPN anchor names.",
        "",
        f"`{_summarize(state)}`",
        "",
        "| event | anchor | ours | authority says | drift (days) |",
        "|---|---|---|---|---|",
    ]
    for m in state["moves"][:50]:
        lines.append(
            f"| {m['event_id']} | `{m['espn_id']}` | {m['ours']} | {m['theirs']} | "
            f"{m['delta_days']} |"
        )
    if len(state["moves"]) > 50:
        lines.append(f"| … | *{len(state['moves']) - 50} more* | | | |")

    lines += [
        "",
        "**Nothing was written.** This rail reports; the correction is attended. "
        "To see the plan and then apply it, use the admin endpoint "
        "(`/api/admin/events/reconcile-anchor-schedule`) with `apply=false` first.",
        "",
        _blind_spots_note(),
        "",
        f"<sub>anchor-schedule sentinel · {now.isoformat()} · "
        f"`{MARKER_KEY}:{state['fingerprint']}`  (dedupe key — do not remove)</sub>",
    ]
    return "\n".join(lines)


async def _run_anchor_schedule_sentinel(
    file_issues: bool = True,
    *,
    limit: int = SWEEP_PAGE_LIMIT,
    sport: Optional[str] = None,
    lookback: timedelta = DEFAULT_LOOKBACK,
    horizon: timedelta = DEFAULT_HORIZON,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    max_pages: int = DEFAULT_MAX_PAGES,
    now: Optional[datetime] = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Sweep the anchored near-future window read-only and report what drifted.

    RED (file) when the sweep found drift. GREEN (close) **only from a COMPLETE
    window pass that found none, on any night of it** — a truncated,
    chain-broken, expired or authority-dark state has not earned the word, and
    closing on one would resolve a real issue because the budget ran out. That
    is the same discipline ``reconcile`` applies per page, held one level up
    (gotcha #53: a partial answer read as an all-clear).

    Consecutive nights CONTINUE each other (CERT-843): a run stopped by its
    budget saves where it got to, and the next one starts after it, so a window
    bigger than one night's budget is still covered end to end instead of the
    front slice being rescanned forever. ``resume=False`` forces a run to start
    at the oldest row — for an operator who wants a front-of-window read now.

    And the close is the CHAIN's, not any one run's (#2983). The run that
    reaches the end of the window is, by construction, a resumed one; gating
    GREEN on a single unresumed run reaching the end made the close unreachable
    at this population. So ``complete`` is now "an intact window pass reached
    the end", and GREEN additionally requires that no night in that pass saw
    drift. The three ways a pass fails to earn it — broken chain, expiry,
    drift-seen-earlier — are each on the operator line.
    """
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    resume_from = _load_continuation() if resume else None
    open_pass = _load_pass() if resume_from else None

    # Which window pass this run belongs to, decided before the sweep because it
    # is decided by WHERE the run starts (#2983). Starting at the oldest row
    # begins a pass; resuming continues the one the predecessor began; resuming
    # with nothing to continue is a broken chain, which still sweeps — the
    # position is good — but cannot claim to have seen the window.
    if resume_from is None:
        pass_open, pass_started_at, pass_drift_seen = True, now, False
    elif open_pass is not None and open_pass[2] == resume_from:
        pass_open = True
        pass_started_at, pass_drift_seen, _ = open_pass
    else:
        # No marker, or one that names a DIFFERENT position than the one being
        # resumed from. The second case is the one that matters (CERT-896): the
        # two keys came apart, so the claim does not describe this chain and
        # cannot be carried by it. Both read as a broken chain — the sweep runs
        # normally on a position that is still good, and only the close is
        # withheld.
        if open_pass is not None:
            logger.warning(
                "anchor-schedule sentinel: the window-pass marker names cursor "
                "%r but this run resumes from %r — the two keys came apart, so "
                "the chain cannot claim the window",
                open_pass[2],
                resume_from,
            )
        pass_open, pass_started_at, pass_drift_seen = False, None, False

    async with get_task_session() as session:
        state = await _sweep(
            session,
            limit=limit,
            sport=sport,
            lookback=lookback,
            horizon=horizon,
            deadline_seconds=deadline_seconds,
            max_pages=max_pages,
            resume_from=resume_from,
        )

    # An exhausted resume restarted this run at the oldest row (see `_sweep`),
    # so a NEW pass began mid-run: the rows the dead cursor named are out of the
    # window and the chain that examined them is not continuable. Anything the
    # run found before the restart is still counted below — the restart can only
    # fire on a page that examined nothing, so there is nothing to lose.
    if state["restarted_from_exhausted_cursor"]:
        pass_open, pass_started_at, pass_drift_seen = True, now, False

    pass_drift_seen = pass_drift_seen or bool(state["moves"])
    pass_age_seconds = (
        (now - pass_started_at).total_seconds() if pass_started_at else None
    )
    pass_expired = pass_open and pass_age_seconds > MAX_PASS_AGE_SECONDS

    # `complete` still gates the GREEN close and still means "the whole window
    # has been seen" — the change is that it is now the CHAIN's property rather
    # than one run's, which is the only reading under which it is ever true at
    # this population (#2983).
    complete = bool(state["reached_window_end"] and pass_open and not pass_expired)

    if state["stopped_by"] == "authority_dark":
        terminal = "authority_dark"
    elif not complete:
        terminal = "partial"
    elif pass_drift_seen:
        terminal = "plan_only"
    else:
        terminal = "no_work"

    state["complete"] = complete
    state["terminal"] = terminal
    state["pass_open"] = pass_open
    state["pass_drift_seen"] = pass_drift_seen
    state["pass_started_at"] = pass_started_at.isoformat() if pass_started_at else None
    state["pass_age_seconds"] = (
        round(pass_age_seconds, 1) if pass_age_seconds is not None else None
    )
    state["pass_expired"] = bool(pass_expired)

    # THE MARKER IS WRITTEN FIRST, ALWAYS (CERT-896). Neither write can be made
    # atomic with the other and both swallow their exceptions, so one landing
    # without the other is a state this has to survive rather than exclude.
    # Marker-first makes the likely crack the conservative one — a claim that
    # names a position the store no longer holds is refused on sight, where the
    # reverse (an advanced position beside a stale claim) is the one that could
    # close a live issue. The binding below is what actually catches it; the
    # ordering just makes the catch rarer.
    #
    # The pass ends when the chain reaches the end of the window, and also when
    # it has nothing left to claim — expired, or broken from the start. Note
    # what is NOT cleared on expiry: the continuation. Restarting the sweep at
    # the oldest row every time a pass ages out would mean a window that has
    # outgrown three nights of budget never has its tail examined at all, which
    # is CERT-843's blind spot with extra steps. Expiry costs the close, never
    # the coverage.
    if state["reached_window_end"] or not pass_open or pass_expired:
        _clear_pass()
    else:
        # Bound to the very position being handed on, so tomorrow can tell
        # whether both writes landed.
        _save_pass(pass_started_at, pass_drift_seen, state["continuation"])

    # Hand the position on (or clear it on a finished sweep) BEFORE filing, so a
    # GitHub fault cannot cost us the place we got to.
    _save_continuation(state["continuation"])

    # One canonical issue for this rail. The fingerprint deliberately does NOT
    # hash the drifting ids: if it did, every night with a different set of bad
    # rows would open a NEW issue and the board would grow one row per night for
    # one recurring defect. The body is re-pointed at tonight's observation
    # instead, which is what `reconcile_issue`'s red_body is for.
    state["fingerprint"] = "anchor-schedule-drift"

    red = bool(state["moves"])
    line = _summarize(state)
    if red:
        logger.warning("anchor-schedule sentinel: %s", line)
    else:
        logger.info("anchor-schedule sentinel: %s", line)

    state["filing"] = None
    # GREEN is the PASS's verdict, not tonight's. A chain whose first night
    # filed five drifting rows must not be closed by a later night that swept a
    # clean tail and reached the end — those five rows are still wrong. Without
    # this clause the #2983 repair would resolve live drift, which is a worse
    # failure than the one it fixes.
    green = complete and not pass_drift_seen
    # A sweep that did not finish may neither file a clean bill nor close one.
    # It MAY still file drift it actually saw — a real finding does not become
    # unreal because the budget stopped the sweep after it.
    if file_issues and (red or green):
        from app.tasks.sentinel_filing import reconcile_issue

        state["filing"] = reconcile_issue(
            red=red,
            fingerprint=state["fingerprint"],
            marker_key=MARKER_KEY,
            title=f"{TITLE_PREFIX} — {len(state['moves'])} anchored row(s) disagree with ESPN",
            title_prefix=TITLE_PREFIX,
            body=_issue_body(state, now=now),
            red_body=_issue_body(state, now=now),
            red_comment=f"Still drifting as of {now.isoformat()} — `{line}`",
            green_comment=(
                f"Resolved: a COMPLETE sweep at {now.isoformat()} found no anchored "
                f"row whose kickoff disagrees with its authority — `{line}`"
            ),
            labels=["type:bug", "priority:p1", "area:backend", "matching-symptom"],
        )
    elif file_issues and complete and pass_drift_seen:
        logger.warning(
            "anchor-schedule sentinel: the window pass is complete but an earlier "
            "night in it found drift — not closing; the pass ends RED — %s",
            line,
        )
    elif file_issues:
        logger.warning(
            "anchor-schedule sentinel: window pass incomplete (stopped_by=%s "
            "pass_open=%s expired=%s) and no drift found — neither filing nor "
            "closing; an unfinished window is not an all-clear",
            state["stopped_by"],
            pass_open,
            pass_expired,
        )

    return state
