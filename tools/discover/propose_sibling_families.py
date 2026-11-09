#!/usr/bin/env python3
"""Offline CLI for the ``sibling_family`` proposer (#12372, Epic #12288, Decide 61-A).

PILLAR: DISCOVER / MATCHING / TRUTH · SHIP: discovers candidate ``sibling_family``
groups from live open markets on ``https://api.bainluck.com``, prints the
estimated model spend before running ($5 cap/run, $30 cap/Nov), verifies rule
quotes and headings, judges every proposal through ``select_sibling_family``,
and writes ``docs/discover/grouping-candidates-2026-11.{json,md}``.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.utils.sibling_family_proposer import (  # noqa: E402
    DEFAULT_JSON_OUT,
    DEFAULT_MD_OUT,
    DEFAULT_PROPOSER_MODEL,
     format_grouping_candidates_markdown,
    nominate_sibling_families,
    propose_sibling_families,
)

DEFAULT_API_BASE = "https://api.bainluck.com"

BROWSE_CATEGORIES: tuple[str, ...] = (
    "politics",
    "economics",
    "entertainment",
    "weather",
    "football",
    "basketball",
    "baseball",
    "hockey",
    "soccer",
    "motorsports",
    "mma",
    "golf",
    "tennis",
    "other",
)

SEARCH_TERMS: tuple[str, ...] = (
    "Will",
    "win",
    "Division",
    "Conference",
    "Playoff",
    " playoffs",
    "Senate",
    "Governor",
    "House",
    "Presidential",
    "Nominee",
    "Rotten Tomatoes",
    "Opening Weekend",
    "Box Office",
    "Oscar",
    "Grammy",
    "Golden Globe",
    "snow",
    "rain",
    "temperature",
    "degrees",
    "high temperature",
    "inch",
    "hurricane",
    "Fed",
    "inflation",
    "rate",
    "recession",
    "tariff",
    "AI",
    "OpenAI",
    "SpaceX",
    "Championship",
    "MVP",
    "Coach",
    "Rookie",
)


def _http_get_json(url: str, *, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "bainluck-sibling-proposer/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_open_markets(
    api_base: str = DEFAULT_API_BASE,
    *,
    categories: Sequence[str] = BROWSE_CATEGORIES,
    terms: Sequence[str] = SEARCH_TERMS,
    pages_per_category: int = 3,
    http_get: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch open futures markets across categories and search terms from ``/api/futures/browse``."""
    getter = http_get or _http_get_json
    base = api_base.rstrip("/")
    by_id: dict[int, dict[str, Any]] = {}

    urls: list[str] = []
    for cat in categories:
        c = urllib.parse.quote(cat)
        for page in range(pages_per_category):
            offset = page * 200
            urls.append(f"{base}/api/futures/browse?category={c}&limit=200&offset={offset}")
    for term in terms:
        q = urllib.parse.quote(term)
        urls.append(f"{base}/api/futures/browse?q={q}&limit=100")

    def _fetch_one(url: str) -> list[dict[str, Any]]:
        try:
            payload = getter(url)
            items = payload.get("items") if isinstance(payload, Mapping) else None
            return [dict(x) for x in items if isinstance(x, Mapping)] if isinstance(items, list) else []
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        for items in pool.map(_fetch_one, urls):
            for item in items:
                mid = item.get("id")
                if isinstance(mid, int) and not isinstance(mid, bool) and mid not in by_id:
                    by_id[mid] = item

    return [by_id[k] for k in sorted(by_id)]


def enrich_nominated_family_markets(
    markets: list[dict[str, Any]],
    *,
    api_base: str = DEFAULT_API_BASE,
    max_families: int = 25,
    min_members: int = 3,
    http_get: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch ``/api/futures/{id}`` for members of top nominated families so full outcomes and rule descriptions are present."""
    getter = http_get or _http_get_json
    base = api_base.rstrip("/")
    preliminary = nominate_sibling_families(markets, min_members=min_members)[:max_families]
    target_ids = sorted(
        {
            int(m["id"])
            for fam in preliminary
            for m in fam["members"]
        }
    )
    if not target_ids:
        return markets

    details: dict[int, dict[str, Any]] = {}

    def _fetch_detail(mid: int) -> tuple[int, dict[str, Any] | None]:
        try:
            data = getter(f"{base}/api/futures/{mid}")
            return (mid, dict(data)) if isinstance(data, Mapping) else (mid, None)
        except Exception:
            return (mid, None)

    with ThreadPoolExecutor(max_workers=6) as pool:
        for mid, detail in pool.map(_fetch_detail, target_ids):
            if detail is not None:
                details[mid] = detail

    enriched: list[dict[str, Any]] = []
    for m in markets:
        mid = int(m["id"])
        if mid in details:
            merged = {**m, **details[mid]}
            # Preserve outcomes from detail if non-empty, else keep browse top_outcomes.
            if not merged.get("outcomes") and m.get("top_outcomes"):
                merged["outcomes"] = m["top_outcomes"]
            enriched.append(merged)
        else:
            enriched.append(m)
    return enriched


def _load_openai_key_from_dotenv() -> str:
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key
    for candidate in (REPO_ROOT / "backend" / ".env", Path("/Users/bain/bainluck/backend/.env")):
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s.startswith("OPENAI_API_KEY="):
                    return s.split("=", 1)[1].strip().strip("\"'")
    return ""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--max-families", type=int, default=22)
    parser.add_argument("--min-members", type=int, default=3)
    parser.add_argument("--model", default=DEFAULT_PROPOSER_MODEL)
    parser.add_argument("--no-llm", action="store_true", help="Run rules-only ($0.00) without calling OpenAI")
    parser.add_argument("--november-spent-prior-usd", type=float, default=0.0)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_OUT)
    args = parser.parse_args(argv)

    api_key = "" if args.no_llm else _load_openai_key_from_dotenv()
    use_llm = (not args.no_llm) and bool(api_key)

    markets = fetch_open_markets(args.api_base)
    markets = enrich_nominated_family_markets(
        markets,
        api_base=args.api_base,
        max_families=args.max_families,
        min_members=args.min_members,
    )

    now_utc = datetime.now(timezone.utc)
    report = propose_sibling_families(
        markets,
        max_families=args.max_families,
        min_members=args.min_members,
        use_llm=use_llm,
        model=args.model,
        api_key=api_key or None,
        november_spent_prior_usd=args.november_spent_prior_usd,
        now=now_utc,
    )
    md_text = format_grouping_candidates_markdown(report)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.md_out.write_text(md_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
