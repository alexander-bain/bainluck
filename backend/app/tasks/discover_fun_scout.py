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
import re
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


SCOUT_GITHUB_COMMENT_MAX_CHARS = 65_000
_BACKTICK_RUN_RE = re.compile(r"`+")


def _md_code_span(value: Any, *, table: bool = False) -> str:
    """Wrap untrusted venue/model text in a safe CommonMark code span.

    Code spans suppress GitHub @mentions and #123 issue links. Newlines are
    collapsed to spaces so rows stay single-line, pipes are escaped when placed
    inside a Markdown table cell (GFM splits table cells before parsing code
    spans), and the backtick fence is always longer than any run in the text.
    """
    text = " ".join(str("" if value is None else value).split())
    if not text:
        return "`—`"
    if table:
        text = text.replace("|", r"\|")
    runs = _BACKTICK_RUN_RE.findall(text)
    fence = "`" * (max((len(r) for r in runs), default=0) + 1)
    if text.startswith("`") or text.endswith("`") or (text.startswith(" ") and text.endswith(" ")):
        return f"{fence} {text} {fence}"
    return f"{fence}{text}{fence}"


def _md_code_fence(text: str, lang: str = "json") -> list[str]:
    """Emit a fenced code block whose fence cannot be closed by ``text``."""
    runs = _BACKTICK_RUN_RE.findall(text)
    fence = "`" * max(3, max((len(r) for r in runs), default=0) + 1)
    return [f"{fence}{lang}", text, fence]


def format_scout_nightly_comment_markdown(
    artifact: dict[str, Any],
    *,
    max_chars: int = SCOUT_GITHUB_COMMENT_MAX_CHARS,
) -> str:
    """Format the nightly scout output (sets, singles, spend) for #13102.

    Escapes every venue/model string into an inert code span/fence and caps the
    comment strictly under GitHub's 65,536-character limit (keeping the header,
    spend line, and staged sets whole and trimming the verified-singles table
    with an explicit "first N of M" line when needed).
    """
    run_date = str(artifact.get("run_date") or "")
    day_key = f"{_RUN_ARTIFACT_REDIS_PREFIX}:{run_date}"

    header_lines: list[str] = [
        f"## Nightly Fun Scout Report — {_md_code_span(run_date)}",
        "",
        f"- **Run time (UTC):** {_md_code_span(artifact.get('run_at'))}",
        f"- **Model:** {_md_code_span(artifact.get('set_model'))}",
        f"- **Spend:** {_md_code_span(artifact.get('spend_line'))} "
        f"(actual: `${float(artifact.get('actual_total_cost_usd') or 0.0):.4f}`)",
        f"- **Licence:** {_md_code_span(json.dumps(artifact.get('licence_state') or {}, sort_keys=True))}",
    ]
    if not artifact.get("monthly_ledger_recorded", True):
        header_lines.append(
            f"- **WARNING — MONTHLY LEDGER WRITE FAILED:** "
            f"{_md_code_span(artifact.get('monthly_ledger_error'))} "
            "(month marked unknown / fail-closed for next run)"
        )

    staged = artifact.get("staged_sets") or []
    sets_lines: list[str] = ["", f"### Staged Sets ({len(staged)})"]
    if not staged:
        sets_lines.append("_None tonight._")
    for idx, s in enumerate(staged, 1):
        sets_lines.append(
            f"#### {idx}. {_md_code_span(s.get('name'))} "
            f"({_md_code_span(s.get('slug'))} · {_md_code_span(s.get('category'))} "
            f"· look={_md_code_span(s.get('look'))})"
        )
        sets_lines.append(f"- **Kicker:** {_md_code_span(s.get('kicker'))}")
        sets_lines.append(
            f"- **Why better together:** {_md_code_span(s.get('why_better_together'))}"
        )
        sets_lines.append("- **Members:**")
        for m in s.get("members") or []:
            vol = f"{int(m['volume']):,}" if m.get("volume") is not None else "n/a"
            sets_lines.append(
                f"  - {_md_code_span(m.get('market_id'))} "
                f"({_md_code_span(m.get('source'))}, vol `{vol}`): "
                f"{_md_code_span(m.get('title'))}"
            )
        sets_lines.append("<details><summary>Rule definition JSON</summary>\n")
        rule_json = json.dumps(s.get("rule_definition") or {}, indent=2)
        sets_lines.extend(_md_code_fence(rule_json, "json"))
        sets_lines.append("</details>")
        sets_lines.append("")

    rejected = artifact.get("rejected_sets") or []
    rejected_prefix: list[str] = ["", f"### Rejected Proposals ({len(rejected)})"] if rejected else []
    rejected_rows: list[str] = [
        f"- {_md_code_span(json.dumps(rej, sort_keys=True))}" for rej in rejected
    ]

    singles = artifact.get("verified_singles") or []
    singles_header: list[str] = ["", f"### Verified Fun Singles ({len(singles)})"]
    if not singles:
        singles_header.append("_None tonight._")
        singles_rows: list[str] = []
    else:
        singles_header.extend(
            [
                "| Market ID | Fun Group | Title | Reason |",
                "|---:|---|---|---|",
            ]
        )
        singles_rows = [
            f"| {_md_code_span(item.get('market_id'), table=True)} "
            f"| {_md_code_span(item.get('fun_group') or '', table=True)} "
            f"| {_md_code_span(item.get('title') or '', table=True)} "
            f"| {_md_code_span(item.get('reason') or '', table=True)} |"
            for item in singles
        ]

    # Header + staged sets always stay whole unless they alone exceed max_chars.
    base_lines = header_lines + sets_lines
    base_text = "\n".join(base_lines)

    # Reserve a small slice for rejected proposals (kept compact if large).
    rejected_lines: list[str] = []
    if rejected_rows:
        rejected_budget = min(4_000, max(0, max_chars - len(base_text) - 512))
        acc: list[str] = list(rejected_prefix)
        used = sum(len(line) + 1 for line in acc)
        shown_rej = 0
        for row in rejected_rows:
            note_reserve = 120
            if used + len(row) + 1 + note_reserve > rejected_budget:
                break
            acc.append(row)
            used += len(row) + 1
            shown_rej += 1
        if shown_rej < len(rejected_rows):
            acc.append(
                f"_Showing first {shown_rej} of {len(rejected_rows)} rejected proposals "
                f"(full list in Redis {_md_code_span(day_key)})._"
            )
        if shown_rej > 0 or len(rejected_rows) > 0:
            rejected_lines = acc

    rejected_text = ("\n" + "\n".join(rejected_lines)) if rejected_lines else ""

    # Fit as many verified singles rows as possible inside the remaining budget.
    singles_section_lines: list[str] = list(singles_header)
    if singles_rows:
        # Leave space for trailing newline + possible truncation note.
        trunc_template = (
            f"\n_Showing first {len(singles_rows)} of {len(singles_rows)} verified singles "
            f"(capped under GitHub's 65,536-char limit; full list in Redis {_md_code_span(day_key)})._"
        )
        prefix_len = len(base_text) + 1 + len("\n".join(singles_section_lines)) + len(rejected_text) + 2
        available_for_rows = max_chars - prefix_len
        all_rows_len = sum(len(r) + 1 for r in singles_rows)
        if all_rows_len <= available_for_rows:
            singles_section_lines.extend(singles_rows)
        else:
            row_budget = max(0, available_for_rows - len(trunc_template) - 1)
            used_rows = 0
            shown_singles = 0
            for row in singles_rows:
                if used_rows + len(row) + 1 > row_budget:
                    break
                singles_section_lines.append(row)
                used_rows += len(row) + 1
                shown_singles += 1
            singles_section_lines.append(
                f"_Showing first {shown_singles} of {len(singles_rows)} verified singles "
                f"(capped under GitHub's 65,536-char limit; full list in Redis {_md_code_span(day_key)})._"
            )

    body = "\n".join(base_lines + singles_section_lines + rejected_lines).strip() + "\n"
    if len(body) > max_chars:
        suffix = f"\n\n_Report truncated to fit GitHub's comment limit; full artifact in Redis {_md_code_span(day_key)}._\n"
        keep = max(0, max_chars - len(suffix))
        body = body[:keep].rstrip() + suffix
    return body


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
