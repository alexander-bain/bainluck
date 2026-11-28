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
    SCOUT_AUTO_PROMOTE_TO_PUBLIC,
    SCOUT_LICENCE_STATE_PATH,
    SCOUT_MAX_NEW_SETS_PER_DAY,
    SCOUT_PUBLIC_PROMOTION_GATE,
    SCOUT_RETIRED_SETS_PATH,
    SCOUT_STAGED_SETS_DIR,
    ScoutKnownSet,
    ScoutLicenceState,
    ScoutMarketRow,
    ScoutUncoveredFamily,
    build_scout_anthropic_client,
    build_scout_openai_client,
    build_scout_rule_file_definition,
    is_fun_scout_enabled,
    load_db_graded_scout_sets,
    load_graded_scout_sets,
    load_known_sets_for_scout,
    load_public_scout_sets,
    load_reader_dismissed_sets,
    load_retired_scout_sets,
    normalize_retired_scout_sets,
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
) -> list[dict[str, Any]]:
    """Load retired sets from checked-in file UNION durable Redis as normalized dicts.

    Fails closed (raises) if Redis is unreadable so a retired set can never be
    silently re-proposed after a dyno restart.
    """
    file_entries: list[dict[str, Any]] = load_retired_scout_sets(path)
    from app.tasks.redis_state import get_redis_client

    raw = get_redis_client().get(_RETIRED_SETS_REDIS_KEY)
    redis_entries: list[Any] = []
    if raw is not None:
        parsed = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    redis_entries.append(item)
                else:
                    cleaned = str(item or "").strip().lower()
                    if cleaned:
                        redis_entries.append(
                            {"slug": cleaned, "name": cleaned, "reason": "retired"}
                        )
        elif isinstance(parsed, dict):
            for item in parsed.get("retired_sets") or []:
                if isinstance(item, dict):
                    redis_entries.append(item)
            for slug in parsed.get("retired_slugs") or []:
                cleaned = str(slug or "").strip().lower()
                if cleaned:
                    redis_entries.append(
                        {"slug": cleaned, "name": cleaned, "reason": "retired"}
                    )
    normalized = normalize_retired_scout_sets([*file_entries, *redis_entries])
    normalized.sort(key=lambda r: (str(r.get("slug") or ""), str(r.get("name") or "")))
    return normalized


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
    max_new_per_day: int = SCOUT_MAX_NEW_SETS_PER_DAY,
) -> dict[str, Any]:
    """Build the complete, durable JSON artifact for one Nightly Fun Scout run."""
    licence_dict = result.get("licence_state") or {}
    licence_status = str(licence_dict.get("status") or LICENCE_AWAITING_LOOK)
    set_model = str(result.get("set_model") or "")
    cap = max(0, int(max_new_per_day))

    staged_sets: list[dict[str, Any]] = []
    for vset in (result.get("validated_sets") or [])[:cap]:
        rule_def = build_scout_rule_file_definition(
            vset,
            model_used=set_model,
            created_at=run_now,
            licence_state=licence_status,
        )
        scout_meta = rule_def.get("scout") or {}
        row_answers_map = dict(vset.row_answers)
        staged_entry: dict[str, Any] = {
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
                    **(
                        {"row_answer": row_answers_map[m.market_id]}
                        if m.market_id in row_answers_map
                        else {}
                    ),
                }
                for m in vset.members
            ],
            "trimmed_members": list(scout_meta.get("trimmed_members") or []),
            "added_members": list(scout_meta.get("added_members") or []),
            "rule_definition": rule_def,
        }
        if row_answers_map:
            staged_entry["row_answers"] = {
                str(mid): ans for mid, ans in sorted(row_answers_map.items())
            }
        staged_sets.append(staged_entry)

    verified_singles = list(result.get("verified_singles") or [])
    rejected_sets = list(result.get("rejected_sets") or [])
    carried_grades = list(result.get("carried_grades") or [])
    return {
        "run_date": run_now.strftime("%Y-%m-%d"),
        "run_at": run_now.isoformat(),
        "spend_line": str(result.get("spend_line") or ""),
        "actual_total_cost_usd": float(result.get("actual_total_cost_usd") or 0.0),
        "set_model": set_model,
        "tagged_count": int(result.get("tagged_count") or 0),
        "max_new_sets_per_day": cap,
        "auto_promote_to_public": SCOUT_AUTO_PROMOTE_TO_PUBLIC,
        "public_promotion_gate": SCOUT_PUBLIC_PROMOTION_GATE,
        "licence_state": licence_dict,
        "monthly_ledger_recorded": bool(monthly_ledger_recorded),
        "monthly_ledger_error": monthly_ledger_error,
        "staged_sets": staged_sets,
        "verified_singles": verified_singles,
        "rejected_sets": rejected_sets,
        "carried_grades": carried_grades,
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
        kicker_raw = s.get("kicker")
        kicker_display = "`(omitted)`" if kicker_raw == "" else _md_code_span(kicker_raw)
        sets_lines.append(f"- **Kicker:** {kicker_display}")
        sets_lines.append(
            f"- **Why better together:** {_md_code_span(s.get('why_better_together'))}"
        )
        sets_lines.append("- **Members:**")
        for m in s.get("members") or []:
            vol = f"{int(m['volume']):,}" if m.get("volume") is not None else "n/a"
            ans_suffix = (
                f" · answer: {_md_code_span(m.get('row_answer'))}"
                if m.get("row_answer")
                else ""
            )
            sets_lines.append(
                f"  - {_md_code_span(m.get('market_id'))} "
                f"({_md_code_span(m.get('source'))}, vol `{vol}`): "
                f"{_md_code_span(m.get('title'))}{ans_suffix}"
            )
        trimmed_rows = (
            s.get("trimmed_members")
            or ((s.get("rule_definition") or {}).get("scout") or {}).get("trimmed_members")
            or []
        )
        if trimmed_rows:
            sets_lines.append("- **Split-set gate trimmed:**")
            for tm in trimmed_rows:
                sets_lines.append(
                    f"  - {_md_code_span(tm.get('market_id'))} "
                    f"({_md_code_span(tm.get('reason'))}): "
                    f"{_md_code_span(tm.get('title'))}"
                )
        added_rows = (
            s.get("added_members")
            or ((s.get("rule_definition") or {}).get("scout") or {}).get("added_members")
            or []
        )
        if added_rows:
            sets_lines.append("- **Missing-member fill added:**")
            for am in added_rows:
                sets_lines.append(
                    f"  - {_md_code_span(am.get('market_id'))} "
                    f"({_md_code_span(am.get('reason'))}): "
                    f"{_md_code_span(am.get('title'))}"
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

    carried_raw = artifact.get("carried_grades") or []
    carried_lines: list[str] = []
    if carried_raw:
        carried_lines.append("")
        carried_lines.append(f"### Carried Grades ({len(carried_raw)})")
        for cg in carried_raw[:20]:
            if not isinstance(cg, dict):
                continue
            prop_span = _md_code_span(cg.get("proposed_name") or cg.get("proposed_slug"))
            known_span = _md_code_span(
                cg.get("matched_set") or cg.get("matched_slug") or cg.get("known_name")
            )
            grade_span = _md_code_span(cg.get("grade"))
            shared_n = cg.get("shared_members")
            cand_n = cg.get("candidate_count")
            overlap_txt = (
                f"{shared_n}/{cand_n} shared"
                if shared_n is not None and cand_n
                else "name/slug"
            )
            carried_lines.append(
                f"- {prop_span} → carried {grade_span} from {known_span} "
                f"({overlap_txt}; not asked again)"
            )
    carried_text = ("\n" + "\n".join(carried_lines)) if carried_lines else ""

    # Fit as many verified singles rows as possible inside the remaining budget.
    singles_section_lines: list[str] = list(singles_header)
    if singles_rows:
        # Leave space for trailing newline + possible truncation note.
        trunc_template = (
            f"\n_Showing first {len(singles_rows)} of {len(singles_rows)} verified singles "
            f"(capped under GitHub's 65,536-char limit; full list in Redis {_md_code_span(day_key)})._"
        )
        prefix_len = (
            len(base_text)
            + 1
            + len("\n".join(singles_section_lines))
            + len(carried_text)
            + len(rejected_text)
            + 2
        )
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

    body = (
        "\n".join(base_lines + singles_section_lines + carried_lines + rejected_lines).strip()
        + "\n"
    )
    if len(body) > max_chars:
        suffix = f"\n\n_Report truncated to fit GitHub's comment limit; full artifact in Redis {_md_code_span(day_key)}._\n"
        keep = max(0, max_chars - len(suffix))
        body = body[:keep].rstrip() + suffix
    return body


async def _load_known_sets_durable(
    catalog_by_id: dict[int, ScoutMarketRow],
) -> list[ScoutKnownSet]:
    """Load graded sets (DB + committed) and public sets (live machinery + Redis + seed)."""
    from app.tasks.redis_state import get_redis_client

    try:
        redis_client = get_redis_client()
    except Exception:
        redis_client = None

    try:
        async with async_session_maker() as db:
            graded_sets = await load_db_graded_scout_sets(db, redis_client=redis_client)
    except Exception as exc:
        logger.warning(
            "Fun scout continuing with committed graded sets (%s: %s)",
            type(exc).__name__,
            exc,
        )
        graded_sets = load_graded_scout_sets()

    try:
        public_sets = load_public_scout_sets(
            catalog_by_id=catalog_by_id,
            redis_client=redis_client,
        )
    except Exception as exc:
        logger.warning(
            "Fun scout continuing with file public sets (%s: %s)",
            type(exc).__name__,
            exc,
        )
        public_sets = load_public_scout_sets(catalog_by_id=catalog_by_id)

    return load_known_sets_for_scout(
        catalog_by_id=catalog_by_id,
        graded_sets=graded_sets,
        public_sets=public_sets,
        redis_client=redis_client,
    )


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


async def fetch_reader_dismissed_sets_for_scout(
    *, lookback_days: int = 30, now: Optional[datetime] = None
) -> dict[str, int]:
    """Read grouped-card ('not for me') dismissals by set for the Fun Scout (#13644)."""
    async with async_session_maker() as db:
        return await load_reader_dismissed_sets(
            db, lookback_days=lookback_days, now=now
        )


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
    catalog_by_id = {m.market_id: m for m in markets}
    try:
        known_sets: Optional[list[ScoutKnownSet]] = await _load_known_sets_durable(catalog_by_id)
    except Exception as exc:
        logger.warning(
            "Fun scout continuing with committed/file known sets (%s: %s)",
            type(exc).__name__,
            exc,
        )
        known_sets = None
    try:
        reader_dismissed = await fetch_reader_dismissed_sets_for_scout(now=run_now)
    except Exception as exc:
        logger.warning(
            "Fun scout continuing without reader dismissed sets (%s: %s)",
            type(exc).__name__,
            exc,
        )
        reader_dismissed = {}
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
        reader_dismissed_sets=reader_dismissed,
        known_sets=known_sets,
        licence_state=licence,
        prior_monthly_spend_usd=prior_spend,
        max_new_per_day=SCOUT_MAX_NEW_SETS_PER_DAY,
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
        max_new_per_day=SCOUT_MAX_NEW_SETS_PER_DAY,
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
