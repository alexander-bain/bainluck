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
clean. The cursor makes tomorrow's run resume rather than restart, so a window
too big for one night is still covered; nothing is silently skipped.
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
    return (
        f"{state['terminal']}: examined={state['examined']}/{state['eligible']} "
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
) -> dict[str, Any]:
    """Page the rail read-only until the window ends or a bound is hit.

    ``terminal`` is this SWEEP's word, not any one page's. The rail is explicit
    that whether a sweep finished is the driver's finding to report (see
    ``reconcile``'s paging docstring), so the per-page ``partial`` is expected
    and is not propagated — what matters is whether we reached the end of the
    window before a bound stopped us.
    """
    start = _time.monotonic()
    by_verdict: dict[str, int] = {name: 0 for name in SCHEDULE_VERDICTS}
    moves: list[dict] = []
    examined = 0
    eligible = 0
    pages = 0
    cursor: Optional[str] = None
    stopped_by: Optional[str] = None
    dark_pages = 0

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

    complete = stopped_by is None
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
) -> dict[str, Any]:
    """Sweep the anchored near-future window read-only and report what drifted.

    RED (file) when the sweep found drift. GREEN (close) **only from a COMPLETE
    sweep that found none** — a truncated or authority-dark run has not earned
    the word, and closing on one would resolve a real issue because the budget
    ran out. That is the same discipline ``reconcile`` applies per page, held one
    level up (gotcha #53: a partial answer read as an all-clear).
    """
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)

    async with get_task_session() as session:
        state = await _sweep(
            session,
            limit=limit,
            sport=sport,
            lookback=lookback,
            horizon=horizon,
            deadline_seconds=deadline_seconds,
            max_pages=max_pages,
        )

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
