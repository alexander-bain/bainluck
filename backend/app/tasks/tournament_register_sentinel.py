"""Daily tournament-register drift sentinel (UX-P134, US Open program Day 4).

`/tournaments/us-open` renders a **committed** register: 211 players, 66
matchups and 4 curated props, each pinned to an exact `(source, market_id,
outcome_id)`. That pinning is what makes the page immune to the
`llm_sport_category` contamination — and it is also what makes it go stale
silently. A fuzzy matcher that drifts renders a wrong row; a pinned register
that drifts renders *nothing*, or worse, renders a name against a market that
is no longer that player's. Neither has a symptom the page can show.

So this runs daily, from the day the boards go live, and compares every
registered identity against current source inventory.

**What it does NOT do, deliberately.** The grid sentinel can publish an
auto-versioned register because it writes to a data directory. This one cannot
and must not: the tournament register is a file committed to git, reviewed as
code, and the only correct response to drift during a live tournament is a
human deciding in minutes, not a task rewriting the page's source of truth at
07:45 UTC. So this sentinel **detects and files**. `publish` is computed and
reported, never acted on.

Safety properties, inherited from the grid register sentinel because the
failure modes are identical:

* One poison tournament cannot starve its siblings — each is isolated.
* A malformed candidate set is never read as "no drift found": it raises the
  `CANDIDATES_WRONG_SHAPE` / `POISON_CANDIDATE` findings the core already has,
  which classify `needs_ruling` and go to a human. Note the distinction — the
  register is not invalid, the OBSERVATION is unusable, and the one thing
  neither may do is read as clean (gotcha #53 — an empty answer is a response
  shape, not an absence).
* Identity only. Reads no probabilities and writes no market data (gotcha #21).
* Enrolled in `ENFORCED_TASKS` with a real terminal from birth (#1884), because
  a sentinel that reports success having compared nothing is the exact
  false-green class it exists to catch.
"""

from __future__ import annotations

import hashlib
import logging
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.tournament_register import (
    TournamentRegister,
    classify,
    diff_against_inventory,
    load_register,
    us_open_2026_contract,
    validate_register,
)

logger = logging.getLogger(__name__)

#: The tournaments this sentinel watches. One entry per committed register.
#: A tournament is added here the day its page goes live and removed when the
#: page comes down — an unwatched live register is the whole failure class.
WATCHED: tuple[tuple[str, str], ...] = (("us-open", "2026"),)

#: Inner deadline, comfortably under the task's soft limit so the run always
#: reaches its own terminal rather than being SIGKILLed untracked (#966).
DEADLINE_SECONDS = 180.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def register_age_hours(register: dict[str, Any], now: datetime | None = None) -> float | None:
    """Hours since the register's data was observed, or None if unreadable."""
    raw = register.get("generated_at")
    if not isinstance(raw, str):
        return None
    try:
        generated = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return ((now or _now()) - generated).total_seconds() / 3600.0


def drift_fingerprint(tournament: str, season: str) -> str:
    """Stable id for "this tournament's register has drift".

    Keyed on the SUBJECT (tournament + season) and deliberately **not** on the
    finding set. Two reasons, and the second is the load-bearing one:

    1. The same drift seen on three consecutive mornings is one problem, and
       three issues about it is how a sentinel teaches people to ignore it.
    2. The fingerprint has to survive the RED->GREEN transition. A fingerprint
       computed from findings changes the moment the findings clear — which is
       exactly when the close is attempted — so the green pass would look for
       an issue id that never existed and silently close nothing. The alert
       would stay open forever while the sentinel reported it resolved.

    The cost is that two unrelated drift shapes on one tournament share an
    issue. That is the right trade: the body is refreshed to the current
    findings on every red pass, so the issue always describes what is wrong
    now, and one open alert per broken tournament is what a human wants.
    """
    payload = f"{tournament}:{season}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


async def build_candidates(session, register: dict[str, Any]) -> list[dict[str, Any]]:
    """Observe current source state for exactly the registered identities.

    Deliberately keyed on the register rather than on a query for "US Open
    markets": the register is the question being asked, and asking the database
    what it thinks the tournament contains is the fuzzy matching this whole
    design refuses. An identity the register pins and the source no longer
    carries comes back absent, which is `REGISTERED_IDENTITY_NOT_OBSERVED` —
    the finding that matters most, and one a discovery query would hide.
    """
    from sqlalchemy import select

    from app.models.models import FuturesMarket, FuturesOutcome

    view = TournamentRegister(register)
    wanted: set[int] = set()
    for player in view.data.get("players", []) or []:
        if not isinstance(player, dict):
            continue
        for block in player.get("sources") or []:
            if isinstance(block, dict) and block.get("outcome_id") is not None:
                wanted.add(block["outcome_id"])

    if not wanted:
        return []

    rows = (
        await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesOutcome.market_id,
                FuturesOutcome.is_winner,
                FuturesMarket.source,
                FuturesMarket.status,
            )
            .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
            .where(FuturesOutcome.id.in_(wanted))
        )
    ).all()

    season = register.get("season")
    candidates: list[dict[str, Any]] = []
    for outcome_id, name, market_id, is_winner, source, status in rows:
        # `status` here is the MARKET's. A settled market with an unresolved
        # winner is `SETTLEMENT_WITHOUT_RESULT` in the core, which is exactly
        # right: gotcha #33 means a Kalshi market can read `open` long after it
        # settled, so "settled" is a claim we only make when there is a result
        # to point at.
        settled = status in ("settled", "closed", "resolved")
        candidates.append({
            "source": source,
            "market_id": market_id,
            "outcome_id": outcome_id,
            "outcome_name": name,
            "status": "settled" if settled else "live",
            "terminal_result": ("won" if is_winner else "lost") if settled and is_winner is not None else None,
            "season": season,
        })
    return candidates


def build_drift_issue_body(result: dict[str, Any]) -> str:
    """The evidence a human needs to answer this in one tap."""
    lines = [
        f"**Tournament register drift — {result['tournament']} {result['season']}**",
        "",
        f"- register version: `{result.get('version')}`",
        f"- register age: `{result.get('age_hours')}h`",
        f"- registered identities compared: `{result.get('registered_count')}`",
        f"- observed in source inventory: `{result.get('candidate_count')}`",
        f"- classification: **{result.get('classification')}**",
        f"- action: `{result.get('action')}`",
        "",
        "**Findings**",
    ]
    for finding in sorted(set(result.get("findings") or [])):
        lines.append(f"- `{finding}`")
    lines += [
        "",
        "This sentinel never republishes the register — it is a committed file, "
        "reviewed as code. The fix is a register regeneration pass reviewed by a "
        "human, not an automated version bump during a live tournament.",
        "",
        f"<!-- sentinel-fingerprint: tournament_register_sentinel:{result.get('fingerprint')} -->",
    ]
    return "\n".join(lines)


async def _run_tournament(session, tournament: str, season: str, *, directory: Path | None) -> dict[str, Any]:
    """Audit one tournament's register. Isolated so one poison cannot spread."""
    result: dict[str, Any] = {"tournament": tournament, "season": season, "status": "ok"}

    register = load_register(tournament, season, directory=directory)
    if register is None:
        # Meaningful and safe: no register means the page has no rows. It is
        # reported, never treated as clean.
        return {"tournament": tournament, "season": season, "status": "no_register"}

    contract = us_open_2026_contract()
    base_findings = validate_register(register, contract)
    view = TournamentRegister(register)
    result.update({
        "version": view.version,
        "age_hours": register_age_hours(register),
        "registered_count": len(register.get("players") or []),
    })

    if base_findings:
        # A committed register that no longer validates is a hard stop: we do
        # not diff from it, because every finding downstream would be noise
        # about a file that is already wrong.
        result.update({
            "status": "invalid_register",
            "findings": base_findings,
            **classify(base_findings),
        })
        result["fingerprint"] = drift_fingerprint(tournament, season)
        return result

    candidates = await build_candidates(session, register)
    findings = diff_against_inventory(register, candidates)
    result["candidate_count"] = len(candidates)
    result["findings"] = findings
    result.update(classify(findings))

    # `publish` is reported and never acted on — see the module docstring.
    if result.get("publish"):
        result["publish"] = False
        result["publish_suppressed"] = "committed_file_human_reviews"

    if findings:
        result["fingerprint"] = drift_fingerprint(tournament, season)
    return result


async def _run_tournament_register_sentinel(
    *,
    file_issues: bool = True,
    deadline_seconds: float = DEADLINE_SECONDS,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Run the drift sentinel across every watched tournament."""
    from app.services.database import async_session_maker

    start = _time.monotonic()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    async with async_session_maker() as session:
        for tournament, season in WATCHED:
            if _time.monotonic() - start > deadline_seconds:
                errors.append({"tournament": tournament, "error": "deadline_exceeded"})
                continue
            try:
                results.append(await _run_tournament(session, tournament, season, directory=directory))
            except Exception as exc:  # one poison tournament cannot spread
                logger.exception("tournament register sentinel failed for %s", tournament)
                errors.append({"tournament": tournament, "error": str(exc)[:300]})

    needs_ruling = [r for r in results if r.get("action") == "file_p2_needs_triage"]
    invalid = [r for r in results if r.get("classification") == "invalid"]

    filed: list[dict[str, Any]] = []
    if file_issues and results:
        try:
            from app.tasks.sentinel_filing import list_open_alert_issues, reconcile_issue

            # ONE read of the open-issue set for the whole run. Re-reading per
            # tournament would let two calls disagree about what is already
            # filed, which is how a "deduped" sentinel files twice.
            open_issues = list_open_alert_issues()

            red_results = needs_ruling + invalid
            for result in red_results:
                filed.append(reconcile_issue(
                    red=True,
                    marker_key="tournament_register_sentinel",
                    fingerprint=result.get("fingerprint", ""),
                    title=(
                        f"Tournament register drift: {result['tournament']} "
                        f"{result['season']} ({result.get('classification')})"
                    ),
                    body=build_drift_issue_body(result),
                    red_body=build_drift_issue_body(result),
                    labels=["needs-triage", "area:data-quality", "priority:p2"],
                    open_issues=open_issues,
                ))

            # GREEN: a tournament that came back clean resolves its own prior
            # drift issue. Without this the sentinel only ever accumulates —
            # and an alert lane that never closes anything gets muted, which
            # costs more than the alert was ever worth.
            for result in results:
                if result in red_results or result.get("classification") != "clean":
                    continue
                filed.append(reconcile_issue(
                    red=False,
                    marker_key="tournament_register_sentinel",
                    fingerprint=drift_fingerprint(result["tournament"], result["season"]),
                    green_comment=(
                        f"Tournament register drift cleared: {result['tournament']} "
                        f"{result['season']} v{result.get('version')} compared "
                        f"{result.get('registered_count')} registered identities "
                        f"against {result.get('candidate_count')} observed, no findings."
                    ),
                    open_issues=open_issues,
                ))
        except Exception as exc:
            logger.exception("tournament register sentinel filing failed")
            errors.append({"tournament": "filing", "error": str(exc)[:300]})

    stats: dict[str, Any] = {
        "tournaments": len(results),
        "clean": sum(1 for r in results if r.get("classification") == "clean"),
        "needs_ruling": len(needs_ruling),
        "invalid": len(invalid),
        "no_register": sum(1 for r in results if r.get("status") == "no_register"),
        "errors": errors,
        "filed": filed,
        "results": results,
        "duration_s": round(_time.monotonic() - start, 2),
    }
    stats["terminal"] = _terminal(stats)
    return stats


def _terminal(stats: dict[str, Any]) -> str:
    """The honest terminal (#1884: enrolled from birth, so this is the contract).

    A run that compared NO tournaments is `no_work`, never `complete`. A run
    where every watched tournament errored is `failed`, not a success with a
    long error list — "it returned" is not "it worked" (gotcha #53). Finding
    drift is a `complete` run: the sentinel's job is to notice, and noticing
    successfully is success.
    """
    if stats["tournaments"] == 0 and not stats["errors"]:
        return "no_work"
    if stats["tournaments"] == 0:
        return "failed"
    if stats["errors"]:
        return "partial"
    return "complete"
