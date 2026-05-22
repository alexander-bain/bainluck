"""LLM-powered system diagnosis for the admin dashboard."""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

router = APIRouter(prefix="/admin", tags=["admin-llm"])
logger = logging.getLogger(__name__)


def _check_admin_secret(secret: str) -> bool:
    import os
    expected = os.getenv("ADMIN_SECRET", "")
    return bool(expected) and secret == expected


@router.get("/llm-diagnosis")
@router.post("/llm-diagnosis")
async def llm_diagnosis(
    secret: str = Query(...),
    force: bool = Query(False),
):
    """Generate an LLM-powered diagnosis of current system health.

    GET returns cached result if available.
    POST with force=true regenerates.
    """
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    from app.tasks.redis_state import get_redis_client

    cache_key = "bainluck:admin:llm_diagnosis"
    r = get_redis_client()

    if not force and r:
        cached = r.get(cache_key)
        if cached:
            result = json.loads(cached)
            result["cached"] = True
            return result

    # Gather metrics from existing functions
    metrics = await _gather_metrics(secret)

    # Call LLM
    diagnosis = _run_diagnosis(metrics)

    # Cache for 15 min
    if r and diagnosis:
        r.setex(cache_key, 900, json.dumps(diagnosis))

    return diagnosis


async def _gather_metrics(secret: str) -> dict:
    """Collect key metrics from existing dashboard functions."""
    from app.utils.admin_dashboard import build_worker_section
    from app.tasks.redis_state import get_redis_client

    now = datetime.now(timezone.utc)
    metrics = {}

    # Worker health
    try:
        worker = build_worker_section(now)
        metrics["workers"] = {
            "status": worker["overall_health"],
            "critical": worker["critical_tasks"],
            "degraded": worker["degraded_tasks"],
        }
    except Exception as e:
        metrics["workers"] = {"error": str(e)}

    # Quota
    try:
        r = get_redis_client()
        remaining = r.get("odds_api:remaining")
        if remaining:
            metrics["quota"] = {
                "remaining": int(remaining),
                "health": "ok" if int(remaining) > 50000 else "low" if int(remaining) > 20000 else "critical",
            }
    except Exception:
        metrics["quota"] = {"error": "redis unavailable"}

    # Celery queue lengths
    try:
        r = get_redis_client()
        bg = r.llen("celery_background") if r else 0
        rt = r.llen("celery_realtime") if r else 0
        metrics["queues"] = {"background": bg, "realtime": rt}
    except Exception:
        metrics["queues"] = {"error": "redis unavailable"}

    return metrics


def _run_diagnosis(metrics: dict) -> dict:
    """Run GPT-4o-mini diagnosis on collected metrics."""
    from app.services.llm import _get_client

    client = _get_client()
    if not client:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cached": False,
            "issues": [{
                "severity": "info",
                "title": "LLM unavailable",
                "explanation": "OpenAI API key not configured — diagnosis requires GPT-4o-mini.",
                "claude_prompt": "",
                "admin_page": "/admin",
            }],
        }

    prompt = f"""You are an ops diagnostician for Bain Luck, a prediction market aggregation platform.

Given these current system metrics, identify the top 3 issues or anomalies. For each:
1. Severity: critical, warning, or info
2. Title: short description (under 10 words)
3. Explanation: 1-2 sentences in plain English
4. Claude prompt: a ready-to-paste prompt for Claude Code to investigate/fix this issue
5. Admin page: which admin page to check (/admin, /admin/discover-quality, /admin/matching, /admin/source-intelligence, /admin/taxonomy, /admin/eval, /admin/bug-reports)

Current metrics:
{json.dumps(metrics, indent=2)}

What "good" looks like:
- Workers: all essential tasks healthy, zero critical/degraded
- Quota: >50K remaining is healthy, <20K is critical
- Queues: background <10 is normal, >50 means backed up

Respond ONLY with a JSON array of 3 objects. No other text.
Example: [{{"severity":"warning","title":"Background queue backed up","explanation":"...","claude_prompt":"...","admin_page":"/admin"}}]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
        )
        raw = response.choices[0].message.content.strip()
        # Parse JSON from response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        issues = json.loads(raw)
    except Exception as e:
        logger.warning(f"LLM diagnosis failed: {e}")
        issues = [{
            "severity": "info",
            "title": "Diagnosis failed",
            "explanation": f"LLM call failed: {e}",
            "claude_prompt": "",
            "admin_page": "/admin",
        }]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "issues": issues[:3],
    }
