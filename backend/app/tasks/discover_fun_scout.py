"""Celery worker entry point for the Nightly Fun Scout (#13102, Ruling 276: B).

Runs on ``bainluck``'s ``worker-background`` (queue ``background``, same app
and worker as ``grouping_sentinel``) so only ``bainluck`` needs
``ANTHROPIC_API_KEY_SCOUT``. Never called during a page load.

Durability (Fable #13124 pre-flip items):
1. Staged sets in full, verified fun singles, rejected sets, and the spend line
   are persisted to Redis (``bainluck:fun_scout:run:<date>`` + ``:latest``) AND
   posted as a structured nightly comment on GitHub issue #13102 so nothing is
   lost on ephemeral Heroku worker restarts.
2. Licence state and retired sets live in durable Redis keys (unioned with the
   checked-in files), failing closed if retired sets cannot be read and never
   unlocking auto-publish if licence state cannot be read.
3. A failed monthly spend ledger write is returned in the task result AND marks
   the month unknown (closed at cap) so the next run fails closed rather than
   undercounting spend.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from sqlalchemy import select

from app.models.models import FuturesMarket
from app.services.database import async_session_maker
from app.utils.discover_fun_scout import (
    LICENCE_AWAITING_LOOK,
    SCOUT_LICENCE_STATE_PATH,
    SCOUT_RETIRED_SETS_PATH,
    SCOUT_STAGED_SETS_DIR,
    ScoutLicenceState,
    ScoutMarketRow,
    ScoutUncoveredFamily,
    build_scout_anthropic_client,
    build_scout_openai_client,
    build_scout_rule_file_definition,
    is_fun_scout_enabled,
    load_retired_scout_sets,
    run_nightly_fun_scout,
)

logger = logging.getLogger(__name__)

_NON_SPORTS_CATEGORIES: frozenset[str] = frozenset(
    {
        "politics",
        "economics",
        "tech",
        "entertainment",
        "culture",
        "weather",
        "geopolitics",
        "health",
        "science",
        "climate",
        "finance",
        "crypto",
    }
)

_MONTHLY_SPEND_REDIS_PREFIX = "bainluck:fun_scout:monthly_spend"
_MONTHLY_SPEND_UNKNOWN_PREFIX = "bainluck:fun_scout:monthly_spend_unknown"
_MONTHLY_SPEND_TTL_S = 45 * 24 * 3600

_RUN_ARTIFACT_REDIS_PREFIX = "bainluck:fun_scout:run"
_RUN_ARTIFACT_LATEST_KEY = "bainluck:fun_scout:latest"
_RUN_ARTIFACT_TTL_S = 30 * 24 * 3600

_LICENCE_STATE_REDIS_KEY = "bainluck:fun_scout:licence_state"
_RETIRED_SETS_REDIS_KEY = "bainluck:fun_scout:retired_sets"

SCOUT_REPORT_ISSUE_NUMBER = 13102

# In-process fallback so a worker whose Redis write failed cannot undercount on
# a subsequent invocation in the same process even if marking Redis also failed.
_UNRECORDED_SPEND_MONTHS: set[str] = set()


def _read_monthly_spend_usd(month_key: str) -> float:
    """Read month-to-date scout spend; fail closed (``inf``) if unknown or unreadable."""
    if month_key in _UNRECORDED_SPEND_MONTHS:
        logger.warning(
            "Fun scout monthly spend for %s marked unknown in process; failing closed",
            month_key,
        )
        return float("inf")
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        unknown_flag = client.get(f"{_MONTHLY_SPEND_UNKNOWN_PREFIX}:{month_key}")
        if unknown_flag is not None:
            logger.warning(
                "Fun scout monthly spend for %s marked unknown after prior ledger write failure; failing closed",
                month_key,
            )
            return float("inf")
        raw = client.get(f"{_MONTHLY_SPEND_REDIS_PREFIX}:{month_key}")
        if raw is None:
            return 0.0
        return max(0.0, float(raw.decode() if isinstance(raw, bytes) else raw))
    except Exception:
        logger.warning("Fun scout monthly spend ledger unavailable; failing closed at cap")
        return float("inf")


def _record_monthly_spend_usd(
    month_key: str, delta_usd: float
) -> tuple[bool, Optional[str]]:
    """Record actual run spend; on failure mark the month unknown (closed) and return error."""
    if delta_usd <= 0:
        return True, None
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        key = f"{_MONTHLY_SPEND_REDIS_PREFIX}:{month_key}"
        client.incrbyfloat(key, float(delta_usd))
        client.expire(key, _MONTHLY_SPEND_TTL_S)
        return True, None
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logger.error("Failed to record fun scout monthly spend for %s: %s", month_key, err)
        _UNRECORDED_SPEND_MONTHS.add(month_key)
        try:
            from app.tasks.redis_state import get_redis_client

            client = get_redis_client()
            client.set(
                f"{_MONTHLY_SPEND_UNKNOWN_PREFIX}:{month_key}",
                "1",
                ex=_MONTHLY_SPEND_TTL_S,
            )
        except Exception:
            logger.error(
                "Also failed to persist monthly_spend_unknown sentinel for %s", month_key
            )
        return False, err


def _load_licence_state(
    path: Path = SCOUT_LICENCE_STATE_PATH,
) -> ScoutLicenceState:
    """Load licence state from durable Redis, falling back to checkout file.

    If Redis raises, fails safely to ``awaiting_look`` (``clean_days=0``) so
    auto-publish can never unlock on an unreadable store.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(_LICENCE_STATE_REDIS_KEY)
        if raw is not None:
            parsed = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            if isinstance(parsed, dict):
                return ScoutLicenceState.from_dict(parsed)
    except Exception as exc:
        logger.warning(
            "Fun scout durable licence state unreadable (%s); defaulting to awaiting_look",
            exc,
        )
        return ScoutLicenceState(status=LICENCE_AWAITING_LOOK, clean_days=0)

    if not path.exists():
        return ScoutLicenceState()
    raw_file = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw_file, dict):
        return ScoutLicenceState.from_dict(raw_file)
    return ScoutLicenceState()


def save_licence_state_durable(state: ScoutLicenceState) -> tuple[bool, Optional[str]]:
    """Persist Decide 61-A licence state to durable Redis across dyno restarts."""
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().set(
            _LICENCE_STATE_REDIS_KEY,
            json.dumps(state.to_dict(), sort_keys=True),
        )
        return True, None
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logger.error("Failed to save fun scout durable licence state: %s", err)
        return False, err


def _load_retired_sets_durable(
    path: Path = SCOUT_RETIRED_SETS_PATH,
) -> set[str]:
    """Load retired set slugs from checked-in file UNION durable Redis.

    Fails closed (raises) if Redis is unreadable so a retired set can never be
    silently re-proposed after a dyno restart.
    """
    retired = set(load_retired_scout_sets(path))
    from app.tasks.redis_state import get_redis_client

    raw = get_redis_client().get(_RETIRED_SETS_REDIS_KEY)
    if raw is not None:
        parsed = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        if isinstance(parsed, list):
            for slug in parsed:
                cleaned = str(slug or "").strip().lower()
                if cleaned:
                    retired.add(cleaned)
        elif isinstance(parsed, dict):
            for slug in parsed.get("retired_slugs") or []:
                cleaned = str(slug or "").strip().lower()
                if cleaned:
                    retired.add(cleaned)
    return retired


def retire_scout_set_durable(slug: str) -> tuple[bool, Optional[str]]:
    """Record a retired scout set slug in durable Redis across dyno restarts."""
    cleaned = (slug or "").strip().lower()
    if not cleaned:
        return False, "empty slug"
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        existing = set()
        raw = client.get(_RETIRED_SETS_REDIS_KEY)
        if raw is not None:
            parsed = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            if isinstance(parsed, list):
                existing.update(str(s).strip().lower() for s in parsed if s)
            elif isinstance(parsed, dict):
                existing.update(
                    str(s).strip().lower()
                    for s in (parsed.get("retired_slugs") or [])
                    if s
                )
        existing.add(cleaned)
        client.set(_RETIRED_SETS_REDIS_KEY, json.dumps(sorted(existing)))
        return True, None
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logger.error("Failed to persist retired scout set '%s': %s", cleaned, err)
        return False, err


def build_scout_nightly_artifact(
    result: dict[str, Any],
    *,
    run_now: datetime,
    monthly_ledger_recorded: bool = True,
    monthly_ledger_error: Optional[str] = None,
) -> dict[str, Any]:
    """Build the complete, durable JSON artifact for one Nightly Fun Scout run."""
    licence_dict = result.get("licence_state") or {}
    licence_status = str(licence_dict.get("status") or LICENCE_AWAITING_LOOK)
    set_model = str(result.get("set_model") or "")

    staged_sets: list[dict[str, Any]] = []
    for vset in result.get("validated_sets") or []:
        rule_def = build_scout_rule_file_definition(
            vset,
            model_used=set_model,
            created_at=run_now,
            licence_state=licence_status,
        )
        staged_sets.append(
            {
                "slug": vset.slug,
                "name": vset.name,
                "kicker": vset.kicker,
                "category": vset.category,
                "why_better_together": vset.why_better_together,
                "look": vset.look,
                "members": [
                    {
                        "market_id": m.market_id,
                        "source": m.source,
                        "title": m.title,
                        "volume": m.volume,
                        "category": m.category,
                    }
                    for m in vset.members
                ],
                "rule_definition": rule_def,
            }
        )

    verified_singles = list(result.get("verified_singles") or [])
    rejected_sets = list(result.get("rejected_sets") or [])
    return {
        "run_date": run_now.strftime("%Y-%m-%d"),
        "run_at": run_now.isoformat(),
        "spend_line": str(result.get("spend_line") or ""),
        "actual_total_cost_usd": float(result.get("actual_total_cost_usd") or 0.0),
        "set_model": set_model,
        "tagged_count": int(result.get("tagged_count") or 0),
        "licence_state": licence_dict,
        "monthly_ledger_recorded": bool(monthly_ledger_recorded),
        "monthly_ledger_error": monthly_ledger_error,
        "staged_sets": staged_sets,
        "verified_singles": verified_singles,
        "rejected_sets": rejected_sets,
    }


def _persist_run_artifact_redis(
    artifact: dict[str, Any],
) -> tuple[bool, Optional[str]]:
    """Save the full nightly scout artifact to durable Redis (30-day TTL)."""
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        serialized = json.dumps(artifact, sort_keys=True)
        day_key = f"{_RUN_ARTIFACT_REDIS_PREFIX}:{artifact['run_date']}"
        client.set(day_key, serialized, ex=_RUN_ARTIFACT_TTL_S)
        client.set(_RUN_ARTIFACT_LATEST_KEY, serialized, ex=_RUN_ARTIFACT_TTL_S)
        return True, None
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logger.error("Failed to persist fun scout run artifact to Redis: %s", err)
        return False, err


def format_scout_nightly_comment_markdown(artifact: dict[str, Any]) -> str:
    """Format the full nightly scout output (sets, singles, spend) for #13102."""
    lines: list[str] = [
        f"## Nightly Fun Scout Report — {artifact['run_date']}",
        "",
        f"- **Run time (UTC):** `{artifact['run_at']}`",
        f"- **Model:** `{artifact['set_model']}`",
        f"- **Spend:** `{artifact['spend_line']}` (actual: `${artifact['actual_total_cost_usd']:.4f}`)",
        f"- **Licence:** `{json.dumps(artifact.get('licence_state') or {}, sort_keys=True)}`",
    ]
    if not artifact.get("monthly_ledger_recorded", True):
        lines.append(
            f"- **WARNING — MONTHLY LEDGER WRITE FAILED:** `{artifact.get('monthly_ledger_error')}` "
            "(month marked unknown / fail-closed for next run)"
        )

    staged = artifact.get("staged_sets") or []
    lines.extend(["", f"### Staged Sets ({len(staged)})"])
    if not staged:
        lines.append("_None tonight._")
    for idx, s in enumerate(staged, 1):
        lines.append(
            f"#### {idx}. {s['name']} (`{s['slug']}` · `{s['category']}` · look=`{s['look']}`)"
        )
        lines.append(f"- **Kicker:** {s['kicker']}")
        lines.append(f"- **Why better together:** {s['why_better_together']}")
        lines.append("- **Members:**")
        for m in s.get("members") or []:
            vol = f"{int(m['volume']):,}" if m.get("volume") is not None else "n/a"
            lines.append(
                f"  - `{m['market_id']}` ({m['source']}, vol `{vol}`): {m['title']}"
            )
        lines.append("<details><summary>Rule definition JSON</summary>\n")
        lines.append("```json")
        lines.append(json.dumps(s.get("rule_definition") or {}, indent=2))
        lines.append("```")
        lines.append("</details>")
        lines.append("")

    singles = artifact.get("verified_singles") or []
    lines.extend(["", f"### Verified Fun Singles ({len(singles)})"])
    if not singles:
        lines.append("_None tonight._")
    else:
        lines.append("| Market ID | Fun Group | Title | Reason |")
        lines.append("|---:|---|---|---|")
        for item in singles:
            lines.append(
                f"| `{item.get('market_id')}` | `{item.get('fun_group') or ''}` | "
                f"{item.get('title') or ''} | {item.get('reason') or ''} |"
            )

    rejected = artifact.get("rejected_sets") or []
    if rejected:
        lines.extend(["", f"### Rejected Proposals ({len(rejected)})"])
        for rej in rejected:
            lines.append(f"- `{json.dumps(rej, sort_keys=True)}`")

    return "\n".join(lines).strip() + "\n"


def _post_scout_report_to_github(
    artifact: dict[str, Any],
    *,
    issue_number: int = SCOUT_REPORT_ISSUE_NUMBER,
) -> tuple[Optional[str], Optional[str]]:
    """Post the nightly scout report as a comment on #13102 so Fable can open it."""
    from app.tasks.bug_report_github import REPO

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return None, "GITHUB_TOKEN not set"

    body = format_scout_nightly_comment_markdown(artifact)
    url = f"https://api.github.com/repos/{REPO}/issues/{int(issue_number)}/comments"
    try:
        resp = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"body": body},
            timeout=20.0,
        )
        if resp.status_code not in (200, 201):
            return None, f"GitHub API HTTP {resp.status_code}"
        payload = resp.json()
        return str(payload.get("html_url") or ""), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


async def fetch_open_non_sports_markets_for_scout(
    *, limit: int = 6000
) -> list[ScoutMarketRow]:
    """Read today's open non-sports titles from both venues (Kalshi + Polymarket)."""
    async with async_session_maker() as db:
        stmt = (
            select(
                FuturesMarket.id,
                FuturesMarket.source,
                FuturesMarket.name,
                FuturesMarket.status,
                FuturesMarket.llm_sport_category,
                FuturesMarket.resolution_date,
                FuturesMarket.volume,
                FuturesMarket.volume_24h,
                FuturesMarket.canonical_market_key,
                FuturesMarket.group_id,
                FuturesMarket.market_metadata,
            )
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.source.in_(("kalshi", "polymarket")),
                FuturesMarket.llm_sport_category.in_(tuple(_NON_SPORTS_CATEGORIES)),
            )
            .order_by(FuturesMarket.volume.desc().nullslast(), FuturesMarket.id.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()

    return [
        ScoutMarketRow(
            market_id=int(r.id),
            source=str(r.source or ""),
            title=str(r.name or ""),
            status=str(r.status or "open"),
            category=r.llm_sport_category,
            resolution_date=r.resolution_date,
            volume=float(r.volume) if r.volume is not None else None,
            volume_24h=float(r.volume_24h) if r.volume_24h is not None else None,
            canonical_market_key=r.canonical_market_key,
            group_id=r.group_id,
            market_metadata=r.market_metadata if isinstance(r.market_metadata, dict) else None,
        )
        for r in rows
    ]


async def _run_discover_fun_scout(
    *,
    force: bool = False,
    output_dir: Optional[Path] = SCOUT_STAGED_SETS_DIR,
    uncovered_families: Optional[list[ScoutUncoveredFamily]] = None,
    now: Optional[datetime] = None,
    publish_to_github: bool = True,
    report_issue_number: int = SCOUT_REPORT_ISSUE_NUMBER,
) -> dict[str, Any]:
    """Execute one scheduled or attended Nightly Fun Scout run."""
    if not force and not is_fun_scout_enabled():
        logger.info("Nightly fun scout skipped: DISCOVER_FUN_SCOUT_ENABLED is off")
        return {"status": "disabled"}

    run_now = now or datetime.now(timezone.utc)
    month_key = run_now.strftime("%Y-%m")
    prior_spend = _read_monthly_spend_usd(month_key)

    try:
        retired = _load_retired_sets_durable(SCOUT_RETIRED_SETS_PATH)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logger.error("Fun scout aborted: retired sets store unreadable (%s)", err)
        return {
            "status": "aborted_retired_sets_unreadable",
            "error": err,
        }

    markets = await fetch_open_non_sports_markets_for_scout()
    licence = _load_licence_state(SCOUT_LICENCE_STATE_PATH)

    openai_client = build_scout_openai_client()
    anthropic_client = build_scout_anthropic_client()

    result = run_nightly_fun_scout(
        markets,
        uncovered_families or [],
        openai_client=openai_client,
        anthropic_client=anthropic_client,
        output_dir=output_dir,
        retired_sets=retired,
        licence_state=licence,
        prior_monthly_spend_usd=prior_spend,
        now=run_now,
    )
    monthly_ledger_recorded, monthly_ledger_error = _record_monthly_spend_usd(
        month_key, float(result.get("actual_total_cost_usd") or 0.0)
    )
    artifact = build_scout_nightly_artifact(
        result,
        run_now=run_now,
        monthly_ledger_recorded=monthly_ledger_recorded,
        monthly_ledger_error=monthly_ledger_error,
    )
    redis_saved, redis_error = _persist_run_artifact_redis(artifact)
    github_url: Optional[str] = None
    github_error: Optional[str] = None
    if publish_to_github:
        github_url, github_error = _post_scout_report_to_github(
            artifact, issue_number=report_issue_number
        )

    status = (
        "completed"
        if monthly_ledger_recorded
        else "completed_ledger_write_failed"
    )
    return {
        "status": status,
        "spend_line": result["spend_line"],
        "actual_total_cost_usd": result["actual_total_cost_usd"],
        "set_model": result["set_model"],
        "tagged_count": result["tagged_count"],
        "validated_set_count": len(result["validated_sets"]),
        "rejected_set_count": len(result["rejected_sets"]),
        "verified_single_count": len(artifact["verified_singles"]),
        "staged_sets": artifact["staged_sets"],
        "verified_singles": artifact["verified_singles"],
        "written_rule_files": result["written_rule_files"],
        "monthly_ledger_recorded": monthly_ledger_recorded,
        "monthly_ledger_error": monthly_ledger_error,
        "redis_artifact_saved": redis_saved,
        "redis_artifact_error": redis_error,
        "github_comment_url": github_url,
        "github_comment_error": github_error,
    }
