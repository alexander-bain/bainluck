#!/usr/bin/env python3
"""Discover cross-venue (Kalshi ↔ Polymarket) twin-register candidates via the Anthropic Message Batches API.

PILLAR: MATCHING / TRUTH · SHIP: an auditable candidate table
(``docs/matching/twin-candidates-2026-11.md`` + ``.json``) of cross-venue futures
market pairs evaluated on proposition, deadline, resolution rule, and outcome
aliases so verified pairs can be promoted into explicit twin registers.

Nothing in this script writes to a live code register; verification and
promotion into ``MIDTERMS_TWIN_REGISTER`` / ``NFL_DIVISION_REGISTER``-style code
remains a separate Tier-B change.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API_BASE = "https://api.bainluck.com"
ANTHROPIC_BATCHES_URL = "https://api.anthropic.com/v1/messages/batches"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"
FALLBACK_MODELS = ("claude-sonnet-4-6", "claude-sonnet-4-5-20250929")
HARD_COST_CAP_USD = 60.0
MAX_OUTPUT_TOKENS = 900

# Conservative worst-case pricing ($/million tokens) used for the $60 pre-flight guard.
INPUT_COST_PER_MTOK_USD = 3.00
OUTPUT_COST_PER_MTOK_USD = 15.00

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MD_OUT = REPO_ROOT / "docs" / "matching" / "twin-candidates-2026-11.md"
DEFAULT_JSON_OUT = REPO_ROOT / "docs" / "matching" / "twin-candidates-2026-11.json"

# Catalog P6 search terms + high-value cross-venue subjects.
CATALOG_P6_TERMS: tuple[str, ...] = (
    "Fed",
    "FOMC",
    "interest rate",
    "inflation",
    "CPI",
    "GDP",
    "recession",
    "unemployment",
    "payrolls",
    "tariff",
    "shutdown",
    "debt",
    "Super Bowl",
    "Pro Football",
    "NFL",
    "AFC",
    "NFC",
    "Coach of the Year",
    "MVP",
    "Offensive Player",
    "Defensive Player",
    "Rookie of the Year",
    "Playoff",
    "Heisman",
    "College Football",
    "NBA",
    "Pro Basketball",
    "World Series",
    "MLB",
    "Stanley Cup",
    "NHL",
    "Premier League",
    "Champions League",
    "World Cup",
    "La Liga",
    "Serie A",
    "Bundesliga",
    "Formula 1",
    "F1",
    "Drivers",
    "Constructors",
    "UFC",
    "Masters",
    "PGA",
    "Australian Open",
    "Wimbledon",
    "US Open",
    "Oscars",
    "Best Picture",
    "Best Director",
    "Best Actor",
    "Best Actress",
    "Grammy",
    "Emmy",
    "Golden Globes",
    "Rotten Tomatoes",
    "Box Office",
    "Opening Weekend",
    "Hunger Games",
    "GTA",
    "Supreme Court",
    "Senate",
    "House",
    "Governor",
    "Presidential",
    "2028",
    "Nominee",
    "Democratic",
    "Republican",
    "Prime Minister",
    "Mayor",
    "Cabinet",
    "AI",
    "OpenAI",
    "GPT",
    "Claude",
    "Gemini",
    "SpaceX",
    "Starship",
    "Snow",
    "Temperature",
    "Hurricane",
)

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

# Already-registered market IDs (E2 Midterms + E4 NFL Divisions) excluded from candidate discovery.
REGISTERED_MARKET_IDS: frozenset[int] = frozenset(
    {
        # NFL Division Register (E4)
        53671,
        53672,
        53673,
        53674,
        53675,
        53676,
        53677,
        53678,
        55104215,
        55104216,
        55104217,
        55104218,
        55104219,
        55104220,
        55104221,
        55104222,
        # Midterms 2026 Register (E2)
        345,
        346,
        1512,
        11898,
        11899,
        11900,
        11901,
        11902,
        11904,
        11905,
        11906,
        11909,
        11912,
        58017257,
        55099506,
        55099505,
        57543616,
        56933349,
        56933339,
        56933344,
        56933341,
        56933350,
        56933348,
        56933346,
        57395704,
    }
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "before",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "which",
        "who",
        "will",
        "win",
        "winner",
        "winners",
        "with",
        "market",
        "annual",
        "next",
        "end",
        "during",
        "after",
        "than",
        "more",
        "least",
        "above",
        "below",
    }
)

_PHRASE_SYNONYMS: tuple[tuple[str, str], ...] = (
    ("pro football", "nfl"),
    ("professional football", "nfl"),
    ("pro basketball", "nba"),
    ("professional basketball", "nba"),
    ("pro baseball", "mlb"),
    ("major league baseball", "mlb"),
    ("pro hockey", "nhl"),
    ("national hockey league", "nhl"),
    ("college football", "ncaaf"),
    ("college basketball", "ncaab"),
    ("english premier league", "epl premier league"),
    ("uefa champions league", "ucl champions league"),
    ("federal reserve", "fed fomc"),
    ("interest rates", "fed rate fomc"),
    ("interest rate", "fed rate fomc"),
    ("fed decision", "fed rate fomc decision"),
    ("academy awards", "oscars"),
    ("academy award", "oscars"),
    ("rotten tomatoes", "rt rottentomatoes"),
)

_TOKEN_SYNONYMS: Mapping[str, str] = {
    "jan": "january",
    "feb": "february",
    "mar": "march",
    "apr": "april",
    "jun": "june",
    "jul": "july",
    "aug": "august",
    "sep": "september",
    "sept": "september",
    "oct": "october",
    "nov": "november",
    "dec": "december",
    "championship": "champion",
    "champions": "champion",
    "fomc": "fed",
    "oscars": "oscar",
    "grammys": "grammy",
    "emmys": "emmy",
}

_NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bup or down\b", re.IGNORECASE),
    re.compile(r"\bwhat will .+ say\b", re.IGNORECASE),
    re.compile(r"\bhow many (tweets|posts|truths)\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}:\d{2}\s*(am|pm)\s*-\s*\d{1,2}:\d{2}\s*(am|pm)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class CandidatePair:
    kalshi: dict[str, Any]
    polymarket: dict[str, Any]
    lexical_score: float
    shared_tokens: tuple[str, ...]
    shared_outcomes: tuple[str, ...]

    @property
    def custom_id(self) -> str:
        return f"pair-{self.kalshi['id']}-{self.polymarket['id']}"


def is_noise_market(name: str) -> bool:
    """Exclude intraday up/down ladders and transcript-mention markets (catalog §5)."""
    text = str(name or "").strip()
    if not text:
        return True
    return any(pat.search(text) for pat in _NOISE_PATTERNS)


def normalize_tokens(text: str) -> set[str]:
    """Normalize a market title or outcome string into canonical lexical tokens."""
    lowered = str(text or "").lower()
    for src, dst in _PHRASE_SYNONYMS:
        if src in lowered:
            lowered = lowered.replace(src, f" {dst} ")
    raw_tokens = re.findall(r"[a-z0-9]+", lowered)
    out: set[str] = set()
    for tok in raw_tokens:
        mapped = _TOKEN_SYNONYMS.get(tok, tok)
        if len(mapped) <= 1 and not mapped.isdigit():
            continue
        if mapped in _STOPWORDS:
            continue
        out.add(mapped)
    return out


def _outcome_names(market: Mapping[str, Any]) -> list[str]:
    outcomes = market.get("outcomes") or market.get("top_outcomes") or []
    names: list[str] = []
    for o in outcomes:
        if isinstance(o, Mapping):
            n = str(o.get("name") or "").strip()
            if n and n.lower() not in {"yes", "no", "other"}:
                names.append(n)
    return names


def _parse_iso_date(val: Any) -> datetime | None:
    if not val or not isinstance(val, str):
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def score_candidate_pair(
    kalshi: Mapping[str, Any],
    polymarket: Mapping[str, Any],
) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    """Compute a lexical similarity score in ``[0, 1]`` for a Kalshi ↔ Polymarket pair."""
    k_name = str(kalshi.get("name") or "")
    p_name = str(polymarket.get("name") or "")
    if is_noise_market(k_name) or is_noise_market(p_name):
        return 0.0, (), ()

    k_tokens = normalize_tokens(k_name)
    p_tokens = normalize_tokens(p_name)
    if not k_tokens or not p_tokens:
        return 0.0, (), ()

    shared = sorted(k_tokens & p_tokens)
    if not shared:
        return 0.0, (), ()

    # Reject if both titles state explicit 4-digit years and have zero year in common.
    k_years = {t for t in k_tokens if len(t) == 4 and t.isdigit()}
    p_years = {t for t in p_tokens if len(t) == 4 and t.isdigit()}
    if k_years and p_years and not (k_years & p_years):
        return 0.0, (), ()

    union_size = len(k_tokens | p_tokens)
    min_size = min(len(k_tokens), len(p_tokens))
    jaccard = len(shared) / union_size if union_size else 0.0
    containment = len(shared) / min_size if min_size else 0.0
    title_sim = 0.55 * jaccard + 0.45 * containment

    k_outcomes = {n.lower(): n for n in _outcome_names(kalshi)}
    p_outcomes = {n.lower(): n for n in _outcome_names(polymarket)}
    exact_outcomes = sorted(set(k_outcomes) & set(p_outcomes))

    # Also check token overlap across outcome names (e.g. "Hike 25bps" vs "25 bps increase").
    k_out_tokens = set()
    for n in k_outcomes.values():
        k_out_tokens |= normalize_tokens(n)
    p_out_tokens = set()
    for n in p_outcomes.values():
        p_out_tokens |= normalize_tokens(n)
    shared_out_tokens = k_out_tokens & p_out_tokens

    outcome_bonus = 0.0
    if exact_outcomes:
        outcome_bonus = min(0.25, 0.08 * len(exact_outcomes))
    elif shared_out_tokens:
        outcome_bonus = min(0.15, 0.04 * len(shared_out_tokens))

    k_cat = str(kalshi.get("llm_sport_category") or "").strip().lower()
    p_cat = str(polymarket.get("llm_sport_category") or "").strip().lower()
    cat_bonus = 0.06 if (k_cat and p_cat and k_cat == p_cat) else 0.0

    # Resolution date proximity bonus / penalty.
    date_adj = 0.0
    k_dt = _parse_iso_date(kalshi.get("resolution_date"))
    p_dt = _parse_iso_date(polymarket.get("resolution_date"))
    if k_dt is not None and p_dt is not None:
        days_apart = abs((k_dt - p_dt).total_seconds()) / 86400.0
        if days_apart <= 3:
            date_adj = 0.08
        elif days_apart <= 14:
            date_adj = 0.04
        elif days_apart > 120:
            date_adj = -0.15

    # Require at least 2 shared non-trivial tokens (or 1 shared token + shared outcome).
    if len(shared) < 2 and not exact_outcomes:
        return 0.0, (), ()

    total = max(0.0, min(1.0, title_sim + outcome_bonus + cat_bonus + date_adj))
    shared_outcome_labels = tuple(exact_outcomes[:6]) or tuple(sorted(shared_out_tokens)[:6])
    return round(total, 4), tuple(shared), shared_outcome_labels


def prefilter_pairs(
    markets: Sequence[Mapping[str, Any]],
    *,
    min_score: float = 0.34,
    max_per_market: int = 2,
    max_pairs: int = 120,
) -> list[CandidatePair]:
    """Lexically prefilter open Kalshi ↔ Polymarket markets into a ranked shortlist."""
    kalshi_markets: list[dict[str, Any]] = []
    poly_markets: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for m in markets:
        if not isinstance(m, Mapping):
            continue
        mid = m.get("id")
        if not isinstance(mid, int) or isinstance(mid, bool) or mid <= 0:
            continue
        if mid in seen_ids or mid in REGISTERED_MARKET_IDS:
            continue
        src = str(m.get("source") or "").strip().lower()
        if src not in ("kalshi", "polymarket"):
            continue
        name = str(m.get("name") or "").strip()
        if is_noise_market(name):
            continue
        seen_ids.add(mid)
        item = dict(m)
        if src == "kalshi":
            kalshi_markets.append(item)
        else:
            poly_markets.append(item)

    raw_candidates: list[CandidatePair] = []
    for km in kalshi_markets:
        per_kalshi: list[CandidatePair] = []
        for pm in poly_markets:
            score, shared_toks, shared_outs = score_candidate_pair(km, pm)
            if score >= min_score:
                per_kalshi.append(
                    CandidatePair(
                        kalshi=km,
                        polymarket=pm,
                        lexical_score=score,
                        shared_tokens=shared_toks,
                        shared_outcomes=shared_outs,
                    )
                )
        per_kalshi.sort(
            key=lambda c: (-c.lexical_score, c.kalshi["id"], c.polymarket["id"])
        )
        raw_candidates.extend(per_kalshi[:max_per_market])

    raw_candidates.sort(
        key=lambda c: (-c.lexical_score, c.kalshi["id"], c.polymarket["id"])
    )

    # Cap how many times a single Polymarket market can appear so one broad market
    # does not crowd out the rest of the shortlist.
    poly_counts: dict[int, int] = {}
    shortlist: list[CandidatePair] = []
    for cand in raw_candidates:
        pid = int(cand.polymarket["id"])
        if poly_counts.get(pid, 0) >= max_per_market:
            continue
        poly_counts[pid] = poly_counts.get(pid, 0) + 1
        shortlist.append(cand)
        if len(shortlist) >= max_pairs:
            break

    return shortlist


def _http_get_json(url: str, *, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "bainluck-twin-candidates/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_open_futures_markets(
    api_base: str = DEFAULT_API_BASE,
    *,
    terms: Sequence[str] = CATALOG_P6_TERMS,
    categories: Sequence[str] = BROWSE_CATEGORIES,
    pages_per_category: int = 2,
    http_get: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch open futures markets from ``/api/futures/browse`` across P6 terms and categories."""
    getter = http_get or _http_get_json
    base = api_base.rstrip("/")
    by_id: dict[int, dict[str, Any]] = {}

    urls: list[str] = []
    for term in terms:
        q = urllib.parse.quote(term)
        urls.append(f"{base}/api/futures/browse?q={q}&limit=100")
    for cat in categories:
        c = urllib.parse.quote(cat)
        for page in range(pages_per_category):
            offset = page * 200
            urls.append(f"{base}/api/futures/browse?category={c}&limit=200&offset={offset}")

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
                if isinstance(mid, int) and mid not in by_id:
                    by_id[mid] = item

    return [by_id[k] for k in sorted(by_id)]


def enrich_shortlist_markets(
    pairs: Sequence[CandidatePair],
    *,
    api_base: str = DEFAULT_API_BASE,
    http_get: Callable[[str], Any] | None = None,
) -> list[CandidatePair]:
    """Fetch ``/api/futures/{id}`` for unique markets in ``pairs`` so rules and full outcomes are present."""
    getter = http_get or _http_get_json
    base = api_base.rstrip("/")
    unique_ids = sorted(
        {int(p.kalshi["id"]) for p in pairs} | {int(p.polymarket["id"]) for p in pairs}
    )
    details: dict[int, dict[str, Any]] = {}

    def _fetch_detail(mid: int) -> tuple[int, dict[str, Any] | None]:
        try:
            data = getter(f"{base}/api/futures/{mid}")
            return (mid, dict(data)) if isinstance(data, Mapping) else (mid, None)
        except Exception:
            return (mid, None)

    with ThreadPoolExecutor(max_workers=6) as pool:
        for mid, detail in pool.map(_fetch_detail, unique_ids):
            if detail is not None:
                details[mid] = detail

    enriched: list[CandidatePair] = []
    for p in pairs:
        k_full = {**p.kalshi, **details.get(int(p.kalshi["id"]), {})}
        p_full = {**p.polymarket, **details.get(int(p.polymarket["id"]), {})}
        enriched.append(
            CandidatePair(
                kalshi=k_full,
                polymarket=p_full,
                lexical_score=p.lexical_score,
                shared_tokens=p.shared_tokens,
                shared_outcomes=p.shared_outcomes,
            )
        )
    return enriched


def _format_market_for_prompt(market: Mapping[str, Any]) -> dict[str, Any]:
    outcomes_raw = market.get("outcomes") or market.get("top_outcomes") or []
    outcomes = []
    for o in outcomes_raw[:35]:
        if isinstance(o, Mapping):
            outcomes.append(
                {
                    "name": o.get("name"),
                    "probability": o.get("probability"),
                }
            )
    return {
        "id": market.get("id"),
        "source": market.get("source"),
        "external_id": market.get("external_id"),
        "name": market.get("name"),
        "category": market.get("llm_sport_category") or market.get("category"),
        "resolution_date": market.get("resolution_date"),
        "description": str(market.get("description") or "")[:600] or None,
        "outcome_count": market.get("outcome_count") or len(outcomes_raw),
        "outcomes": outcomes,
    }


def build_pair_prompt(pair: CandidatePair) -> str:
    """Build the single structured evaluation prompt for one Kalshi ↔ Polymarket pair."""
    k_info = _format_market_for_prompt(pair.kalshi)
    p_info = _format_market_for_prompt(pair.polymarket)
    return (
        "Evaluate whether these two open prediction markets from Kalshi and Polymarket are true cross-venue twins "
        "that can be blended in an explicit twin register.\n\n"
        f"Kalshi market:\n{json.dumps(k_info, indent=2, sort_keys=True)}\n\n"
        f"Polymarket market:\n{json.dumps(p_info, indent=2, sort_keys=True)}\n\n"
        "Check four things and return ONLY a single JSON object (no markdown fences, no prose outside JSON) with this exact schema:\n"
        "{\n"
        '  "same_proposition": {"pass": true|false, "reason": "one concise sentence"},\n'
        '  "same_deadline": {"pass": true|false, "reason": "one concise sentence comparing settlement/cutoff windows"},\n'
        '  "same_resolution_rule": {"pass": true|false, "reason": "one concise sentence comparing how winners/rungs settle"},\n'
        '  "outcome_aliases": [{"kalshi": "Outcome A", "polymarket": "Outcome A alias"}],\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "evidence": "one concise summary sentence suitable for an audit table (say market, never question)"\n'
        "}\n\n"
        "Strict rules:\n"
        "- Set confidence='high' ONLY when same_proposition.pass, same_deadline.pass, and same_resolution_rule.pass are all true.\n"
        "- If rungs/thresholds differ (e.g. strict 'Above 45' vs inclusive '50+'), or one market is a path combination while the other is a single meeting, same_resolution_rule.pass MUST be false.\n"
        "- In all reason and evidence strings, use the word 'market' (never 'question')."
    )


def build_batch_requests(
    pairs: Sequence[CandidatePair],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> list[dict[str, Any]]:
    """Build the ``requests`` list for ``POST /v1/messages/batches``."""
    requests: list[dict[str, Any]] = []
    for pair in pairs:
        requests.append(
            {
                "custom_id": pair.custom_id,
                "params": {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {
                            "role": "user",
                            "content": build_pair_prompt(pair),
                        }
                    ],
                },
            }
        )
    return requests


def estimate_batch_cost_usd(
    requests: Sequence[Mapping[str, Any]],
    *,
    input_cost_per_mtok: float = INPUT_COST_PER_MTOK_USD,
    output_cost_per_mtok: float = OUTPUT_COST_PER_MTOK_USD,
) -> float:
    """Estimate worst-case USD cost for a batch of requests."""
    total_input_tokens = 0
    total_output_tokens = 0
    for req in requests:
        params = req.get("params") if isinstance(req.get("params"), Mapping) else {}
        msgs = params.get("messages") if isinstance(params.get("messages"), list) else []
        chars = sum(len(str(m.get("content") or "")) for m in msgs if isinstance(m, Mapping))
        total_input_tokens += max(1, int(math.ceil(chars / 3.5)))
        total_output_tokens += int(params.get("max_tokens", MAX_OUTPUT_TOKENS))

    cost = (
        (total_input_tokens / 1_000_000.0) * input_cost_per_mtok
        + (total_output_tokens / 1_000_000.0) * output_cost_per_mtok
    )
    return round(cost, 4)


def enforce_cost_cap(
    requests: Sequence[dict[str, Any]],
    *,
    max_cost_usd: float = HARD_COST_CAP_USD,
) -> tuple[list[dict[str, Any]], float]:
    """Ensure the batch never exceeds ``max_cost_usd`` (nor the $60 hard ceiling)."""
    effective_cap = min(float(max_cost_usd), HARD_COST_CAP_USD)
    if effective_cap <= 0:
        raise ValueError(f"max_cost_usd must be positive; got {max_cost_usd}")

    kept: list[dict[str, Any]] = []
    for req in requests:
        candidate = kept + [req]
        if estimate_batch_cost_usd(candidate) > effective_cap:
            break
        kept.append(req)

    return kept, estimate_batch_cost_usd(kept)


def _anthropic_request(
    url: str,
    api_key: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    timeout: float = 60.0,
) -> bytes:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Accept": "application/json",
        "User-Agent": "bainluck-twin-candidates/1.0",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def submit_and_poll_batch(
    requests: Sequence[dict[str, Any]],
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    poll_interval_seconds: float = 10.0,
    timeout_seconds: float = 1800.0,
) -> tuple[str, str, dict[str, dict[str, Any]]]:
    """Submit a Message Batch to Anthropic, poll until ``ended``, and return ``(batch_id, model_used, results_by_custom_id)``."""
    if not requests:
        return "empty-batch", model, {}

    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]
    batch_obj: dict[str, Any] | None = None
    model_used = model
    last_err: Exception | None = None

    for candidate_model in models_to_try:
        model_requests = [
            {
                **r,
                "params": {**r["params"], "model": candidate_model},
            }
            for r in requests
        ]
        try:
            raw = _anthropic_request(
                ANTHROPIC_BATCHES_URL,
                api_key,
                method="POST",
                payload={"requests": model_requests},
            )
            batch_obj = json.loads(raw.decode("utf-8"))
            model_used = candidate_model
            break
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"Anthropic Batch POST HTTP {err.code}: {body}")
            if err.code in (400, 404) and ("model" in body.lower() or "not_found" in body.lower()):
                continue
            raise last_err from err

    if batch_obj is None:
        raise last_err or RuntimeError("Failed to submit Anthropic Message Batch")

    batch_id = str(batch_obj["id"])
    deadline = time.monotonic() + timeout_seconds
    while batch_obj.get("processing_status") != "ended":
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Batch {batch_id} did not finish within {timeout_seconds}s")
        time.sleep(poll_interval_seconds)
        raw_status = _anthropic_request(f"{ANTHROPIC_BATCHES_URL}/{batch_id}", api_key)
        batch_obj = json.loads(raw_status.decode("utf-8"))

    results_url = batch_obj.get("results_url") or f"{ANTHROPIC_BATCHES_URL}/{batch_id}/results"
    raw_results = _anthropic_request(str(results_url), api_key, timeout=120.0).decode("utf-8")

    by_custom_id: dict[str, dict[str, Any]] = {}
    for line in raw_results.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        cid = str(row.get("custom_id") or "")
        if cid:
            by_custom_id[cid] = parse_batch_result_row(row)

    return batch_id, model_used, by_custom_id


def _sanitize_reader_copy(text: str) -> str:
    """Ensure reader/audit text never uses 'question' as a synonym for 'market'."""
    cleaned = re.sub(r"\bquestions\b", "markets", str(text or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"\bquestion\b", "market", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def parse_batch_result_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Extract and normalize the structured JSON verdict from a single batch result line."""
    result = row.get("result") if isinstance(row.get("result"), Mapping) else {}
    if result.get("type") != "succeeded":
        err_msg = str(result.get("type") or "error")
        return {
            "confidence": "low",
            "same_proposition": {"pass": False, "reason": f"Batch item status: {err_msg}"},
            "same_deadline": {"pass": False, "reason": f"Batch item status: {err_msg}"},
            "same_resolution_rule": {"pass": False, "reason": f"Batch item status: {err_msg}"},
            "outcome_aliases": [],
            "evidence": f"Batch item did not succeed ({err_msg}).",
        }

    msg = result.get("message") if isinstance(result.get("message"), Mapping) else {}
    content = msg.get("content") if isinstance(msg.get("content"), list) else []
    text_blocks = [
        str(block.get("text") or "")
        for block in content
        if isinstance(block, Mapping) and block.get("type") == "text"
    ]
    raw_text = "\n".join(text_blocks).strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = {}

    def _norm_check(key: str) -> dict[str, Any]:
        val = parsed.get(key)
        if isinstance(val, Mapping):
            passed = bool(val.get("pass") if "pass" in val else val.get("verdict"))
            reason = _sanitize_reader_copy(str(val.get("reason") or ""))
            return {"pass": passed, "reason": reason}
        return {"pass": bool(val), "reason": ""}

    prop = _norm_check("same_proposition")
    deadline = _norm_check("same_deadline")
    rule = _norm_check("same_resolution_rule")

    raw_conf = str(parsed.get("confidence") or "low").strip().lower()
    if raw_conf not in ("high", "medium", "low"):
        raw_conf = "low"
    # Enforce strict high-confidence gate: all three checks must pass.
    if raw_conf == "high" and not (prop["pass"] and deadline["pass"] and rule["pass"]):
        raw_conf = "medium" if (prop["pass"] and (deadline["pass"] or rule["pass"])) else "low"

    aliases_raw = parsed.get("outcome_aliases")
    aliases: list[dict[str, str]] = []
    if isinstance(aliases_raw, list):
        for item in aliases_raw[:16]:
            if isinstance(item, Mapping):
                k_out = str(item.get("kalshi") or "").strip()
                p_out = str(item.get("polymarket") or "").strip()
                if k_out and p_out:
                    aliases.append({"kalshi": k_out, "polymarket": p_out})

    evidence = _sanitize_reader_copy(str(parsed.get("evidence") or ""))
    if not evidence:
        evidence = _sanitize_reader_copy(
            "; ".join(r for r in (prop["reason"], deadline["reason"], rule["reason"]) if r)
        )

    return {
        "confidence": raw_conf,
        "same_proposition": prop,
        "same_deadline": deadline,
        "same_resolution_rule": rule,
        "outcome_aliases": aliases,
        "evidence": evidence,
    }


def _md_cell(text: str) -> str:
    return _sanitize_reader_copy(text).replace("|", "\\|").replace("\n", " ").strip()


def format_candidates_report(
    pairs: Sequence[CandidatePair],
    verdicts_by_id: Mapping[str, Mapping[str, Any]],
    *,
    batch_id: str,
    model_used: str,
    estimated_cost_usd: float,
    generated_at: str,
) -> tuple[dict[str, Any], str]:
    """Build the JSON payload and Markdown table for ``docs/matching/twin-candidates-2026-11.{json,md}``."""
    conf_rank = {"high": 0, "medium": 1, "low": 2}
    rows: list[dict[str, Any]] = []

    for pair in pairs:
        v = verdicts_by_id.get(pair.custom_id) or parse_batch_result_row({})
        rows.append(
            {
                "custom_id": pair.custom_id,
                "lexical_score": pair.lexical_score,
                "shared_tokens": list(pair.shared_tokens),
                "kalshi": {
                    "id": pair.kalshi.get("id"),
                    "external_id": pair.kalshi.get("external_id"),
                    "name": _sanitize_reader_copy(str(pair.kalshi.get("name") or "")),
                    "category": pair.kalshi.get("llm_sport_category"),
                    "resolution_date": pair.kalshi.get("resolution_date"),
                },
                "polymarket": {
                    "id": pair.polymarket.get("id"),
                    "external_id": pair.polymarket.get("external_id"),
                    "name": _sanitize_reader_copy(str(pair.polymarket.get("name") or "")),
                    "category": pair.polymarket.get("llm_sport_category"),
                    "resolution_date": pair.polymarket.get("resolution_date"),
                },
                "confidence": v["confidence"],
                "same_proposition": v["same_proposition"],
                "same_deadline": v["same_deadline"],
                "same_resolution_rule": v["same_resolution_rule"],
                "outcome_aliases": v["outcome_aliases"],
                "evidence": v["evidence"],
            }
        )

    rows.sort(
        key=lambda r: (
            conf_rank.get(r["confidence"], 3),
            -float(r["lexical_score"]),
            int(r["kalshi"]["id"] or 0),
            int(r["polymarket"]["id"] or 0),
        )
    )

    high_count = sum(1 for r in rows if r["confidence"] == "high")
    med_count = sum(1 for r in rows if r["confidence"] == "medium")
    low_count = sum(1 for r in rows if r["confidence"] == "low")

    json_payload: dict[str, Any] = {
        "generated_at": generated_at,
        "batch_id": batch_id,
        "model": model_used,
        "max_cost_usd": HARD_COST_CAP_USD,
        "estimated_cost_usd": estimated_cost_usd,
        "pairs_sent": len(rows),
        "high_confidence_candidates": high_count,
        "medium_confidence_candidates": med_count,
        "low_confidence_candidates": low_count,
        "candidates": rows,
    }

    md_lines = [
        "# Twin-Register Candidates — November 2026",
        "",
        "**PILLAR:** MATCHING / TRUTH · **SHIP:** candidate table of Kalshi ↔ Polymarket open futures market pairs evaluated by the Anthropic Message Batches API for promotion into explicit twin registers (`MIDTERMS_TWIN_REGISTER` / `NFL_DIVISION_REGISTER` pattern).",
        "",
        f"- **Generated at:** `{generated_at}`",
        f"- **Batch ID:** `{batch_id}`",
        f"- **Model:** `{model_used}`",
        f"- **Estimated batch cost:** `${estimated_cost_usd:.4f}` (hard cap `${HARD_COST_CAP_USD:.2f}`)",
        f"- **Pairs sent:** **{len(rows)}**",
        f"- **High-confidence candidates:** **{high_count}** (medium: {med_count}, low: {low_count})",
        "",
        "| Pair (Kalshi ↔ Polymarket) | Confidence | Three Checks (Proposition / Deadline / Rule) | Outcome Aliases | Evidence |",
        "|---|---|---|---|---|",
    ]

    for r in rows:
        k = r["kalshi"]
        p = r["polymarket"]
        pair_cell = _md_cell(
            f"**Kalshi `{k['id']}`** ({k['name']}, closes `{k.get('resolution_date') or 'undated'}`) ↔ "
            f"**Polymarket `{p['id']}`** ({p['name']}, closes `{p.get('resolution_date') or 'undated'}`)"
        )
        conf_cell = f"**{str(r['confidence']).upper()}**"

        c_prop = r["same_proposition"]
        c_dead = r["same_deadline"]
        c_rule = r["same_resolution_rule"]
        checks_cell = _md_cell(
            f"Proposition: {'PASS' if c_prop['pass'] else 'FAIL'} ({c_prop['reason']}) · "
            f"Deadline: {'PASS' if c_dead['pass'] else 'FAIL'} ({c_dead['reason']}) · "
            f"Rule: {'PASS' if c_rule['pass'] else 'FAIL'} ({c_rule['reason']})"
        )

        aliases = r.get("outcome_aliases") or []
        if aliases:
            alias_str = "; ".join(
                f"`{a['kalshi']}` = `{a['polymarket']}`" for a in aliases[:8]
            )
            if len(aliases) > 8:
                alias_str += f" (+{len(aliases) - 8} more)"
        else:
            alias_str = "—"
        alias_cell = _md_cell(alias_str)
        evidence_cell = _md_cell(
            f"{r['evidence']} (lexical={r['lexical_score']:.2f})"
        )
        md_lines.append(
            f"| {pair_cell} | {conf_cell} | {checks_cell} | {alias_cell} | {evidence_cell} |"
        )

    md_lines.append("")
    return json_payload, "\n".join(md_lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-pairs", type=int, default=120)
    parser.add_argument("--min-score", type=float, default=0.34)
    parser.add_argument("--max-cost-usd", type=float, default=HARD_COST_CAP_USD)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_OUT)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--dry-run", action="store_true", help="Prefilter and estimate cost without calling Anthropic")
    args = parser.parse_args(argv)

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY is required unless --dry-run is set", file=sys.stderr)
        return 1

    markets = fetch_open_futures_markets(args.api_base)
    shortlist = prefilter_pairs(
        markets,
        min_score=args.min_score,
        max_pairs=args.max_pairs,
    )
    shortlist = enrich_shortlist_markets(shortlist, api_base=args.api_base)

    requests = build_batch_requests(shortlist, model=args.model)
    capped_requests, est_cost = enforce_cost_cap(requests, max_cost_usd=args.max_cost_usd)
    kept_ids = {r["custom_id"] for r in capped_requests}
    kept_pairs = [p for p in shortlist if p.custom_id in kept_ids]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.dry_run:
        batch_id, model_used, verdicts = "dry-run", args.model, {}
    else:
        batch_id, model_used, verdicts = submit_and_poll_batch(
            capped_requests,
            api_key=api_key,
            model=args.model,
        )

    json_payload, md_text = format_candidates_report(
        kept_pairs,
        verdicts,
        batch_id=batch_id,
        model_used=model_used,
        estimated_cost_usd=est_cost,
        generated_at=generated_at,
    )

    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.write_text(md_text, encoding="utf-8")
    args.json_out.write_text(json.dumps(json_payload, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "model": model_used,
                "markets_scanned": len(markets),
                "pairs_sent": json_payload["pairs_sent"],
                "high_confidence_candidates": json_payload["high_confidence_candidates"],
                "medium_confidence_candidates": json_payload["medium_confidence_candidates"],
                "low_confidence_candidates": json_payload["low_confidence_candidates"],
                "estimated_cost_usd": est_cost,
                "md_out": str(args.md_out),
                "json_out": str(args.json_out),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
