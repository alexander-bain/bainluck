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

One ``summary?event=`` call per row, ~0.2s measured. The window held 685
anchored rows the day the rail was written (239 NFL alone), so a full sweep is
~140s of upstream time on a good night — and good nights are not the ones to
size for. The sibling endpoint one door over (``authority-id-collisions``,
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
    so it is not ``complete`` and may not close the issue; and
  * a saved cursor points into a **moving** window, so it can age out entirely —
    an exhausted resume restarts from the oldest row inside the same run rather
    than stalling silently on zero rows every night.
"""

from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.tasks.reconcile_anchor_schedule import (
    DEFAULT_HORIZON,
    DEFAULT_LIMIT,
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

    ``terminal`` is this SWEEP's word, not any one page's. The rail is explicit
    that whether a sweep finished is the driver's finding to report (see
    ``reconcile``'s paging docstring), so the per-page ``partial`` is expected
    and is not propagated — what matters is whether we reached the end of the
    window before a bound stopped us.

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

    # `complete` gates the GREEN close, so it has to mean "this run saw the
    # whole window" — not merely "this run was not interrupted". A resumed run
    # that reaches the end has seen only the TAIL; everything before its cursor
    # went unexamined tonight, and closing the issue on that would resolve a
    # defect nobody looked for.
    complete = stopped_by is None and not resumed
    if stopped_by == "authority_dark":
        terminal = "authority_dark"
    elif not complete:
        terminal = "partial"
    elif moves:
        terminal = "plan_only"
    else:
        terminal = "no_work"

    return {
        "measured": True,
        "terminal": terminal,
        "complete": complete,
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
    limit: int = DEFAULT_LIMIT,
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
    sweep that found none** — a truncated, resumed or authority-dark run has not
    earned the word, and closing on one would resolve a real issue because the
    budget ran out. That is the same discipline ``reconcile`` applies per page,
    held one level up (gotcha #53: a partial answer read as an all-clear).

    Consecutive nights CONTINUE each other (CERT-843): a run stopped by its
    budget saves where it got to, and the next one starts after it, so a window
    bigger than one night's budget is still covered end to end instead of the
    front slice being rescanned forever. ``resume=False`` forces a run to start
    at the oldest row — for an operator who wants a front-of-window read now.
    """
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    resume_from = _load_continuation() if resume else None

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
    # A sweep that did not finish may neither file a clean bill nor close one.
    # It MAY still file drift it actually saw — a real finding does not become
    # unreal because the budget stopped the sweep after it.
    if file_issues and (red or state["complete"]):
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
    elif file_issues:
        logger.warning(
            "anchor-schedule sentinel: sweep incomplete (%s) and no drift found — "
            "neither filing nor closing; an unfinished window is not an all-clear",
            state["stopped_by"],
        )

    return state
