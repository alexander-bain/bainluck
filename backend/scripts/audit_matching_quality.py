#!/usr/bin/env python3
"""
Comprehensive page health audit for BainLuck.

Hits the production API and evaluates data quality across event detail pages
and championship grids. Uses a mix of deterministic checks (arithmetic,
completeness, consistency) and LLM-based semantic checks (label clarity,
team-market matching).

Usage:
    cd backend
    OPENAI_API_KEY=... python3 scripts/audit_matching_quality.py

Optional flags:
    --event-id 12345     Audit a specific event (default: random live/recent)
    --grid mlb           Audit a specific grid (default: mlb)
    --max-items 50       Max items to audit per category (default: 50)
    --verbose            Print each judgment
    --skip-event         Skip event detail audit
    --skip-grid          Skip championship grid audit
    --skip-llm           Skip LLM-based checks (deterministic only)
    --json               Output JSON report (for programmatic consumption)
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

API_BASE = "https://api.bainluck.com"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
RESULTS_DIR = Path(__file__).parent / "audit_results"

# Severity levels and their score penalties
SEVERITY_CRITICAL = "critical"   # Broken/misleading data shown to users
SEVERITY_WARNING = "warning"     # Data quality concern, possibly confusing
SEVERITY_INFO = "info"           # Minor improvement opportunity

SEVERITY_PENALTY = {
    SEVERITY_CRITICAL: 10,
    SEVERITY_WARNING: 3,
    SEVERITY_INFO: 1,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AuditFinding:
    check: str              # e.g., "hero_probability_sanity", "grid_fill_rate"
    severity: str           # critical / warning / info
    category: str           # "event_detail", "related_futures", "grid"
    description: str        # Human-readable description
    details: dict = field(default_factory=dict)

    def __str__(self):
        icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        return f"{icon.get(self.severity, '?')} [{self.check}] {self.description}"


@dataclass
class AuditReport:
    event_id: Optional[int] = None
    event_name: str = ""
    grid_league: str = ""
    findings: list = field(default_factory=list)

    def add(self, finding: AuditFinding):
        self.findings.append(finding)

    @property
    def critical_count(self):
        return sum(1 for f in self.findings if f.severity == SEVERITY_CRITICAL)

    @property
    def warning_count(self):
        return sum(1 for f in self.findings if f.severity == SEVERITY_WARNING)

    @property
    def info_count(self):
        return sum(1 for f in self.findings if f.severity == SEVERITY_INFO)

    @property
    def health_score(self) -> int:
        """0-100 health score. Starts at 100, penalized by findings."""
        penalty = sum(SEVERITY_PENALTY.get(f.severity, 0) for f in self.findings)
        return max(0, 100 - penalty)

    @property
    def finding_fingerprints(self) -> set[str]:
        """Stable fingerprints for each finding (for diff across runs)."""
        return {_fingerprint(f) for f in self.findings}

    def summary(self, baseline: Optional[dict] = None) -> str:
        lines = [
            "",
            "=" * 70,
            "PAGE HEALTH AUDIT REPORT",
            "=" * 70,
        ]
        if self.event_id:
            lines.append(f"Event: {self.event_name} (ID: {self.event_id})")
        if self.grid_league:
            lines.append(f"Grid: {self.grid_league}")

        # Health score with delta
        score = self.health_score
        score_line = f"Health Score: {score}/100"
        if baseline:
            prev_score = baseline.get("health_score", 100)
            delta = score - prev_score
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            score_line += f"  {arrow} {abs(delta):+d} from last run ({prev_score}/100)"
        lines.append(score_line)
        lines.append("")

        lines.append(f"Findings: {len(self.findings)}")
        lines.append(f"  🔴 Critical: {self.critical_count}  (−{self.critical_count * SEVERITY_PENALTY[SEVERITY_CRITICAL]} pts)")
        lines.append(f"  🟡 Warning:  {self.warning_count}  (−{self.warning_count * SEVERITY_PENALTY[SEVERITY_WARNING]} pts)")
        lines.append(f"  🔵 Info:     {self.info_count}  (−{self.info_count * SEVERITY_PENALTY[SEVERITY_INFO]} pts)")
        lines.append("")

        # Diff against baseline
        if baseline:
            prev_fps = set(baseline.get("fingerprints", []))
            curr_fps = self.finding_fingerprints
            fixed = prev_fps - curr_fps
            new = curr_fps - prev_fps
            persistent = prev_fps & curr_fps

            if fixed:
                lines.append(f"✅ FIXED since last run: {len(fixed)}")
                # Match fingerprints to previous findings for descriptions
                prev_findings_by_fp = {}
                for pf in baseline.get("findings", []):
                    fp = _fingerprint_from_dict(pf)
                    prev_findings_by_fp[fp] = pf
                for fp in sorted(fixed):
                    pf = prev_findings_by_fp.get(fp, {})
                    lines.append(f"  ✅ [{pf.get('check', '?')}] {pf.get('description', fp)[:80]}")
                lines.append("")

            if new:
                lines.append(f"🆕 NEW findings: {len(new)}")
                curr_findings_by_fp = {_fingerprint(f): f for f in self.findings}
                for fp in sorted(new):
                    cf = curr_findings_by_fp.get(fp)
                    if cf:
                        lines.append(f"  🆕 {cf}")
                lines.append("")

            if persistent:
                lines.append(f"⏳ Persistent: {len(persistent)} (unchanged from last run)")
                lines.append("")

        # Group by category
        categories = {}
        for f in self.findings:
            categories.setdefault(f.category, []).append(f)

        for cat, cat_findings in sorted(categories.items()):
            lines.append(f"── {cat.upper().replace('_', ' ')} ({len(cat_findings)} findings) ──")
            order = {SEVERITY_CRITICAL: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
            for f in sorted(cat_findings, key=lambda x: order.get(x.severity, 9)):
                lines.append(f"  {f}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {
            "timestamp": datetime.now(tz=None).isoformat(),
            "event_id": self.event_id,
            "event_name": self.event_name,
            "grid_league": self.grid_league,
            "health_score": self.health_score,
            "summary": {
                "total": len(self.findings),
                "critical": self.critical_count,
                "warning": self.warning_count,
                "info": self.info_count,
            },
            "fingerprints": sorted(self.finding_fingerprints),
            "findings": [
                {
                    "check": f.check,
                    "severity": f.severity,
                    "category": f.category,
                    "description": f.description,
                    "details": f.details,
                }
                for f in self.findings
            ],
        }


def _fingerprint(finding: AuditFinding) -> str:
    """Stable fingerprint for a finding — same issue produces same hash across runs."""
    # Use check + category + key details (not description, which may vary with LLM)
    key_parts = [finding.check, finding.category]
    # Add stable identifying details
    d = finding.details
    for k in ("team", "column", "label", "merge_group", "source", "market", "side"):
        if k in d:
            key_parts.append(f"{k}={d[k]}")
    raw = "|".join(str(p) for p in key_parts)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _fingerprint_from_dict(finding_dict: dict) -> str:
    """Fingerprint from a serialized finding dict (for baseline comparison)."""
    key_parts = [finding_dict.get("check", ""), finding_dict.get("category", "")]
    d = finding_dict.get("details", {})
    for k in ("team", "column", "label", "merge_group", "source", "market", "side"):
        if k in d:
            key_parts.append(f"{k}={d[k]}")
    raw = "|".join(str(p) for p in key_parts)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def save_baseline(report: AuditReport) -> Path:
    """Save audit results as a timestamped baseline."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=None).strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"audit_{ts}.json"
    path.write_text(json.dumps(report.to_json(), indent=2))

    # Also update the "latest" symlink
    latest = RESULTS_DIR / "latest.json"
    latest.write_text(json.dumps(report.to_json(), indent=2))

    return path


def load_baseline() -> Optional[dict]:
    """Load the most recent baseline for comparison."""
    latest = RESULTS_DIR / "latest.json"
    if latest.exists():
        return json.loads(latest.read_text())
    return None


# ---------------------------------------------------------------------------
# OpenAI helper
# ---------------------------------------------------------------------------

def ask_llm_judge(prompt: str) -> Optional[dict]:
    """Send an audit prompt to GPT-4o-mini and get a structured JSON verdict."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key, timeout=30.0)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  LLM error: {e}")
        return None


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict = None) -> dict:
    """GET from the production API."""
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_audit_event(event_id: Optional[int] = None) -> dict:
    """Find a good event to audit — either specific or random recent."""
    if event_id:
        return api_get(f"/api/events/{event_id}")

    feed = api_get("/api/feed", {"limit": "50"})
    items = feed.get("items", [])
    events = []
    for item in items:
        data = item.get("data", {})
        if data and data.get("id"):
            events.append(data)

    sports_with_futures = {"basketball_nba", "americanfootball_nfl", "baseball_mlb", "icehockey_nhl"}

    def _get_sport_key(e):
        sport = e.get("sport", "")
        if isinstance(sport, dict):
            return sport.get("key", "")
        return sport or ""

    candidates = [e for e in events if _get_sport_key(e) in sports_with_futures]
    if not candidates:
        candidates = events[:20]
    if not candidates:
        print("ERROR: No events found in feed")
        sys.exit(1)

    chosen = random.choice(candidates)
    eid = chosen["id"]
    print(f"Selected event: {chosen.get('home_team', '?')} vs {chosen.get('away_team', '?')} (ID: {eid})")
    return api_get(f"/api/events/{eid}")


# ---------------------------------------------------------------------------
# EVENT DETAIL: Deterministic checks
# ---------------------------------------------------------------------------

def check_hero_probability_sanity(event_data: dict, report: AuditReport):
    """Check that hero card probabilities sum to ~100% and are present."""
    co = event_data.get("current_odds") or {}
    hp = co.get("home_probability")
    ap = co.get("away_probability")

    if hp is None and ap is None:
        # Check opening odds fallback
        oo = event_data.get("opening_odds") or {}
        ohp = oo.get("home_probability")
        oap = oo.get("away_probability")
        if ohp is None and oap is None:
            report.add(AuditFinding(
                check="hero_probability_missing",
                severity=SEVERITY_CRITICAL,
                category="event_detail",
                description="No probabilities available for hero card (current_odds and opening_odds both null)",
            ))
            return
        hp, ap = ohp, oap

    if hp is not None and ap is not None:
        total = hp + ap
        if abs(total - 1.0) > 0.05:
            report.add(AuditFinding(
                check="hero_probability_sum",
                severity=SEVERITY_CRITICAL,
                category="event_detail",
                description=f"Hero probabilities sum to {total*100:.1f}% (expected ~100%): home={hp*100:.1f}%, away={ap*100:.1f}%",
                details={"home": hp, "away": ap, "sum": total},
            ))


def check_feed_vs_detail_consistency(event_data: dict, report: AuditReport):
    """Compare feed probability with detail page probability for same event."""
    event_id = event_data.get("id")
    if not event_id:
        return

    # Get this event from the feed
    try:
        feed = api_get("/api/feed", {"limit": "100"})
    except Exception:
        return

    feed_event = None
    for item in feed.get("items", []):
        data = item.get("data", {})
        if data.get("id") == event_id:
            feed_event = data
            break

    if not feed_event:
        return  # Event not in current feed, can't compare

    feed_odds = feed_event.get("current_odds") or {}
    detail_odds = event_data.get("current_odds") or {}

    feed_hp = feed_odds.get("home_probability")
    detail_hp = detail_odds.get("home_probability")

    if feed_hp is not None and detail_hp is not None:
        diff = abs(feed_hp - detail_hp)
        if diff > 0.05:  # >5pp difference
            report.add(AuditFinding(
                check="feed_detail_mismatch",
                severity=SEVERITY_CRITICAL,
                category="event_detail",
                description=f"Feed shows {feed_hp*100:.0f}% but detail shows {detail_hp*100:.0f}% for home team ({diff*100:.1f}pp difference)",
                details={"feed_home": feed_hp, "detail_home": detail_hp, "diff_pp": diff * 100},
            ))


def check_missing_team_data(event_data: dict, report: AuditReport):
    """Check for missing logos, colors, abbreviations in event data."""
    for side in ["home", "away"]:
        team_data = event_data.get(f"{side}_team_data") or {}
        team_name = event_data.get(f"{side}_team", "Unknown")

        if not team_data.get("logo_small") and not team_data.get("logo_large"):
            report.add(AuditFinding(
                check="missing_team_logo",
                severity=SEVERITY_WARNING,
                category="event_detail",
                description=f"{team_name} ({side}) has no logo",
                details={"team": team_name, "side": side},
            ))

        if not team_data.get("primary_color"):
            report.add(AuditFinding(
                check="missing_team_color",
                severity=SEVERITY_INFO,
                category="event_detail",
                description=f"{team_name} ({side}) has no primary color",
                details={"team": team_name, "side": side},
            ))


# ---------------------------------------------------------------------------
# RELATED FUTURES: Deterministic checks
# ---------------------------------------------------------------------------

def check_matchup_probability_sums(futures: list, report: AuditReport):
    """Check that matchup market outcomes from a single market don't have inflated probabilities."""
    # Group by market_id (single underlying multi-outcome market)
    groups: dict[int, list] = {}
    for f in futures:
        mg = f.get("merge_group") or ""
        if "matchup" not in mg:
            continue
        mid = f.get("market_id")
        if mid is not None:
            groups.setdefault(mid, []).append(f)

    for mid, items in groups.items():
        probs = [f.get("probability", 0) for f in items if f.get("probability")]
        if len(probs) < 2:
            continue
        total = sum(probs)
        source = items[0].get("source", "?")
        mg = items[0].get("merge_group", "?")
        label = items[0].get("clean_label") or items[0].get("market_name", "?")

        # These outcomes are from a SINGLE multi-outcome market (NegRisk).
        # The FULL market should sum to ~100% across ALL outcomes.
        # We only see a subset (filtered to this event's teams), so the sum
        # should be well under 100%. If the filtered subset already exceeds 150%,
        # the individual outcome probabilities are likely inflated/stale.
        if total > 1.5:
            report.add(AuditFinding(
                check="matchup_prob_sum",
                severity=SEVERITY_WARNING if total < 4.0 else SEVERITY_CRITICAL,
                category="related_futures",
                description=f"'{label}' ({source}): {len(probs)} filtered outcomes sum to {total*100:.0f}% — prices likely inflated (full market should sum to ~100%)",
                details={"merge_group": mg, "source": source, "market_id": mid, "count": len(probs), "sum_pct": total * 100},
            ))


def check_duplicate_display_labels(futures: list, team_name: str, report: AuditReport):
    """Check for same clean_label appearing multiple times from same source for same team."""
    # Group by (clean_label, source)
    groups: dict[tuple, list] = {}
    for f in futures:
        label = f.get("clean_label") or f.get("market_name", "?")
        source = f.get("source", "?")
        mg = f.get("merge_group") or ""

        # Skip win_total (expected: multiple thresholds), matchups (expected: multiple opponents)
        if mg in ("win_total",) or "matchup" in mg:
            continue

        groups.setdefault((label, source), []).append(f)

    for (label, source), items in groups.items():
        if len(items) > 1:
            outcomes = [f.get("outcome_name", "?") for f in items]
            report.add(AuditFinding(
                check="duplicate_label",
                severity=SEVERITY_WARNING,
                category="related_futures",
                description=f"{team_name}: '{label}' appears {len(items)}x from {source} (outcomes: {', '.join(outcomes[:3])})",
                details={"label": label, "source": source, "count": len(items), "team": team_name},
            ))


def check_win_total_noise(futures: list, team_name: str, report: AuditReport):
    """Flag win total thresholds that are effectively resolved (>99% or <1%)."""
    win_totals = [f for f in futures if (f.get("merge_group") or "") == "win_total"]
    if not win_totals:
        return

    resolved = [f for f in win_totals if f.get("probability", 0.5) > 0.99 or f.get("probability", 0.5) < 0.01]
    if len(resolved) > 0:
        total = len(win_totals)
        report.add(AuditFinding(
            check="win_total_resolved",
            severity=SEVERITY_INFO,
            category="related_futures",
            description=f"{team_name}: {len(resolved)}/{total} win total thresholds are effectively resolved (>99% or <1%)",
            details={"team": team_name, "resolved": len(resolved), "total": total},
        ))


def check_cross_source_display_dupes(all_futures: list, team_name: str, report: AuditReport):
    """
    Check for markets that appear as separate rows but look like the same thing
    from different sources (e.g., 'AL East Winner' from Kalshi + Polymarket).
    These aren't data errors but create visual clutter.
    """
    # Group by clean_label (ignoring source)
    label_groups: dict[str, list] = {}
    for f in all_futures:
        label = f.get("clean_label") or f.get("market_name", "?")
        mg = f.get("merge_group") or ""
        # Skip expected multi-row items
        if mg in ("win_total",) or "matchup" in mg:
            continue
        label_groups.setdefault(label, []).append(f)

    for label, items in label_groups.items():
        sources = set(f.get("source", "?") for f in items)
        if len(sources) > 1 and len(items) > 1:
            probs = [f.get("probability", 0) for f in items]
            prob_range = max(probs) - min(probs) if probs else 0
            source_list = sorted(sources)
            report.add(AuditFinding(
                check="cross_source_visual_dupe",
                severity=SEVERITY_INFO,
                category="related_futures",
                description=f"{team_name}: '{label}' shown {len(items)}x across {', '.join(source_list)} (prob spread: {prob_range*100:.1f}pp)",
                details={"label": label, "sources": source_list, "count": len(items), "team": team_name},
            ))


# ---------------------------------------------------------------------------
# RELATED FUTURES: LLM checks
# ---------------------------------------------------------------------------

def check_label_clarity_llm(futures: list, sport_key: str, report: AuditReport, verbose: bool):
    """Ask LLM to evaluate whether market labels are clear to a casual fan."""
    # Collect unique clean_labels
    seen = set()
    labels = []
    for f in futures:
        label = f.get("clean_label") or f.get("market_name", "?")
        if label not in seen:
            seen.add(label)
            labels.append({
                "label": label,
                "market_name": f.get("market_name", "?"),
                "display_category": f.get("display_category", "?"),
                "outcome_sample": f.get("outcome_name", "?"),
            })

    if not labels:
        return

    # Batch into groups of 10
    batch_size = 10
    for i in range(0, len(labels), batch_size):
        batch = labels[i:i + batch_size]

        items_text = []
        for idx, item in enumerate(batch):
            items_text.append(
                f"  {idx + 1}. Label: \"{item['label']}\"\n"
                f"     Raw market name: \"{item['market_name']}\"\n"
                f"     Category: {item['display_category']}\n"
                f"     Sample outcome: {item['outcome_sample']}"
            )

        prompt = f"""You are evaluating label clarity for a sports odds app aimed at CASUAL fans.
Sport: {sport_key}

For each label below, evaluate:
1. Would a casual fan understand what this market is about from the label alone?
2. Is the label misleading or ambiguous?
3. Could the label be clearer?

Mark as "clear", "unclear", or "misleading". Flag labels that:
- Use jargon or abbreviations without context (e.g., "Pro Baseball Champion" instead of "World Series Winner")
- Don't specify which team/player they refer to
- Could be confused with a different market type
- Have inconsistent naming (e.g., "Longest winning Streak" vs "Longest Winning Streak")

ITEMS:
{chr(10).join(items_text)}

Return a JSON object with key "judgments" — an array of objects, one per item:
  "item_number": int,
  "verdict": "clear" | "unclear" | "misleading",
  "suggestion": string (improved label, or null if already clear),
  "reason": string (1 sentence)
"""

        result = ask_llm_judge(prompt)
        if not result:
            continue

        for j in result.get("judgments", []):
            item_num = j.get("item_number", 0)
            if 1 <= item_num <= len(batch):
                item = batch[item_num - 1]
                verdict = j.get("verdict", "clear")
                if verdict in ("unclear", "misleading"):
                    severity = SEVERITY_WARNING if verdict == "misleading" else SEVERITY_INFO
                    suggestion = j.get("suggestion", "")
                    report.add(AuditFinding(
                        check="label_clarity",
                        severity=severity,
                        category="related_futures",
                        description=f"Label '{item['label']}' is {verdict}: {j.get('reason', '')}",
                        details={
                            "label": item["label"],
                            "raw_market_name": item["market_name"],
                            "verdict": verdict,
                            "suggestion": suggestion,
                        },
                    ))
                    if verbose:
                        sug = f" → suggestion: '{suggestion}'" if suggestion else ""
                        print(f"    [{verdict}] '{item['label']}': {j.get('reason', '')}{sug}")

        time.sleep(0.5)


def check_team_matching_llm(futures: list, home_team: str, away_team: str,
                             sport_key: str, report: AuditReport, verbose: bool):
    """LLM-based check for team-market association correctness (existing logic)."""
    # Build roster context
    home_futures = [f for f in futures if f.get("_side") == "home"]
    away_futures = [f for f in futures if f.get("_side") == "away"]

    home_players = set()
    away_players = set()
    team_name_words = {w.lower() for w in (home_team + " " + away_team).split()}
    for f in home_futures:
        outcome = f.get("outcome_name", "")
        if outcome and outcome.lower() not in team_name_words and outcome not in ("Yes", "No", home_team, away_team) and not outcome.endswith("wins"):
            home_players.add(outcome)
    for f in away_futures:
        outcome = f.get("outcome_name", "")
        if outcome and outcome.lower() not in team_name_words and outcome not in ("Yes", "No", home_team, away_team) and not outcome.endswith("wins"):
            away_players.add(outcome)

    roster_context = ""
    if home_players:
        roster_context += f"\n  {home_team} players (from app's roster): {', '.join(sorted(home_players)[:20])}"
    if away_players:
        roster_context += f"\n  {away_team} players (from app's roster): {', '.join(sorted(away_players)[:20])}"

    # Filter to non-trivial items (skip matchups and win totals which are obviously correct)
    items_to_check = [f for f in futures if (f.get("merge_group") or "") not in ("win_total",) and "matchup" not in (f.get("merge_group") or "")]

    if not items_to_check:
        return

    batch_size = 5
    for i in range(0, min(len(items_to_check), 50), batch_size):
        batch = items_to_check[i:i + batch_size]

        items_text = []
        for idx, f in enumerate(batch):
            items_text.append(
                f"  {idx + 1}. Team: {f.get('_team', '?')} ({f.get('_side', '?')})\n"
                f"     Market: {f.get('market_name', '?')}\n"
                f"     Outcome: {f.get('outcome_name', '?')}\n"
                f"     Category: {f.get('display_category', '?')}\n"
                f"     Source: {f.get('source', '?')}"
            )

        prompt = f"""You are auditing data quality for a sports odds app. Date: April 2026.

EVENT CONTEXT:
  Sport: {sport_key}
  Home team: {home_team}
  Away team: {away_team}
{roster_context}

CRITICAL: The app uses live ESPN roster data. Your training data is from May 2025.
Trust the roster data listed above as ground truth.

Check each item: is it correctly associated with the listed team?
- Matchup markets mentioning a team ARE correctly associated
- Player awards are correct if the player is on the team's roster
- Conference/division markets are correct if the team is in that conference/division
- Season stat markets (best/worst record, win totals, streaks) where the team
  appears in the market/outcome ARE correctly associated — the market is asking
  "will THIS team achieve X?", not predicting they will. A "Worst Record" market
  for the Dodgers at 1% is CORRECTLY associated even though they're unlikely to
  finish last. NEVER flag season stat markets as incorrect based on likelihood.

ITEMS:
{chr(10).join(items_text)}

Return JSON with key "judgments" — array of objects:
  "item_number": int,
  "verdict": "correct" | "incorrect" | "uncertain",
  "issue": null | "wrong_team" | "wrong_category" | "wrong_sport" | "no_connection",
  "reason": string (1 sentence)
"""

        result = ask_llm_judge(prompt)
        if not result:
            continue

        for j in result.get("judgments", []):
            item_num = j.get("item_number", 0)
            if 1 <= item_num <= len(batch):
                f = batch[item_num - 1]
                verdict = j.get("verdict", "uncertain")
                if verdict == "incorrect":
                    issue = j.get("issue", "unknown")
                    desc = f"{f.get('_team', '?')}: '{f.get('market_name', '?')}' = {f.get('outcome_name', '?')} ({f.get('source', '?')})"
                    report.add(AuditFinding(
                        check="team_matching",
                        severity=SEVERITY_CRITICAL,
                        category="related_futures",
                        description=f"{desc} — {j.get('reason', '')}",
                        details={"issue": issue, "team": f.get("_team"), "market": f.get("market_name"), "outcome": f.get("outcome_name")},
                    ))
                    if verbose:
                        print(f"    ✗ {desc}: {j.get('reason', '')}")

        time.sleep(0.5)


# ---------------------------------------------------------------------------
# CHAMPIONSHIP GRID: Deterministic checks
# ---------------------------------------------------------------------------

def check_grid_column_fill_rate(grid_data: dict, report: AuditReport):
    """Flag columns where many teams are missing data."""
    teams = grid_data.get("teams", [])
    columns = grid_data.get("columns", [])

    if not teams or not columns:
        return

    for col in columns:
        col_key = col.get("key", "")
        col_label = col.get("label", col_key)
        filled = sum(
            1 for t in teams
            if t.get("cells", {}).get(col_key) and
            t["cells"][col_key].get("merged_probability") is not None
        )
        fill_pct = filled / len(teams) if teams else 0

        if fill_pct < 0.80:
            severity = SEVERITY_CRITICAL if fill_pct < 0.50 else SEVERITY_WARNING
            report.add(AuditFinding(
                check="grid_fill_rate",
                severity=severity,
                category="grid",
                description=f"'{col_label}' column: only {filled}/{len(teams)} teams have data ({fill_pct*100:.0f}%)",
                details={"column": col_label, "filled": filled, "total": len(teams), "fill_pct": fill_pct},
            ))


def check_grid_source_coverage(grid_data: dict, report: AuditReport):
    """Check if columns are single-source when multiple sources should be available."""
    teams = grid_data.get("teams", [])
    columns = grid_data.get("columns", [])
    available_sources = set(grid_data.get("sources_available", []))

    for col in columns:
        col_key = col.get("key", "")
        col_label = col.get("label", col_key)

        # Collect all sources used for this column
        col_sources = set()
        single_source_count = 0
        multi_source_count = 0
        for t in teams:
            cell = t.get("cells", {}).get(col_key)
            if cell and cell.get("sources"):
                sources = [s.get("source") for s in cell["sources"]]
                col_sources.update(sources)
                if len(sources) == 1:
                    single_source_count += 1
                else:
                    multi_source_count += 1

        # Flag if column uses only 1 source but other sources also have
        # data for this column (not just grid-wide). If only one source
        # offers this market type at all, it's expected, not a warning.
        if len(col_sources) == 1 and len(available_sources) > 1:
            the_source = list(col_sources)[0]
            # Check if other sources actually have data for ANY team in this column
            other_sources_have_data = False
            for t in teams:
                cell = t.get("cells", {}).get(col_key)
                if cell and cell.get("sources"):
                    for s in cell["sources"]:
                        if s.get("source") != the_source:
                            other_sources_have_data = True
                            break
                if other_sources_have_data:
                    break
            if other_sources_have_data:
                report.add(AuditFinding(
                    check="grid_single_source",
                    severity=SEVERITY_WARNING,
                    category="grid",
                    description=f"'{col_label}' column uses only {the_source} — {', '.join(available_sources - col_sources)} not contributing",
                    details={"column": col_label, "sole_source": the_source, "missing_sources": list(available_sources - col_sources)},
                ))


def check_grid_missing_columns(grid_data: dict, league: str, report: AuditReport):
    """Check if expected columns are missing from the grid configuration."""
    columns = grid_data.get("columns", [])
    col_keys = {c.get("key", "") for c in columns}

    # Expected columns per league
    expected = {
        "mlb": {"make_playoffs", "pennant", "championship"},
        "nba": {"make_playoffs", "conference", "championship"},
        "nhl": {"make_playoffs", "conference", "championship"},
    }

    if league in expected:
        missing = expected[league] - col_keys
        # Only flag columns that could still have data. Seasonal columns
        # (e.g., make_playoffs after playoffs start) may have zero fill and
        # are legitimately absent from the grid response.
        teams = grid_data.get("teams", [])
        for m in list(missing):
            has_any_data = any(
                t.get("cells", {}).get(m, {}).get("merged_probability") is not None
                for t in teams
            )
            if not has_any_data:
                missing.discard(m)
        if missing:
            report.add(AuditFinding(
                check="grid_missing_column",
                severity=SEVERITY_WARNING,
                category="grid",
                description=f"Expected columns not found: {', '.join(sorted(missing))}",
                details={"missing": list(missing), "present": list(col_keys)},
            ))

    # Check for columns that COULD exist based on known Kalshi tickers
    # MLB: kxmlbal (AL Champion), kxmlbnl (NL Champion) → should map to "pennant"
    # If "pennant" exists but has very few data points, flag it
    # This is now covered by fill_rate and source_coverage checks


def check_grid_team_identity(grid_data: dict, league: str, report: AuditReport):
    """Check for teams with missing identity data (logo, team_id, name issues)."""
    teams = grid_data.get("teams", [])

    # Individual sports (golf) don't have team_id/logo/record — skip those checks
    individual_sports = {"golf", "tennis", "mma", "boxing"}
    is_individual = league in individual_sports

    for t in teams:
        name = t.get("name", "?")
        team_id = t.get("team_id")
        logo = t.get("logo_url")
        short_name = t.get("short_name", "")

        if is_individual:
            continue  # Individual athletes aren't expected to have team data

        issues = []
        if not team_id:
            issues.append("no team_id (can't link to ESPN data)")
        if not logo:
            issues.append("no logo")
        if not t.get("record"):
            issues.append("no record")

        if issues:
            report.add(AuditFinding(
                check="grid_team_identity",
                severity=SEVERITY_CRITICAL if not team_id else SEVERITY_WARNING,
                category="grid",
                description=f"'{name}' ({short_name}): {'; '.join(issues)}",
                details={"team": name, "issues": issues, "team_id": team_id},
            ))

    # Check for duplicate team entries (e.g., "Athletics" + "A's")
    names_lower = [t.get("name", "").lower() for t in teams]
    seen_ids = set()
    for t in teams:
        tid = t.get("team_id")
        if tid and tid in seen_ids:
            report.add(AuditFinding(
                check="grid_duplicate_team",
                severity=SEVERITY_CRITICAL,
                category="grid",
                description=f"Team ID {tid} appears multiple times in grid",
                details={"team_id": tid, "name": t.get("name")},
            ))
        if tid:
            seen_ids.add(tid)


def check_grid_source_disagreement(grid_data: dict, report: AuditReport):
    """Flag cells with large source disagreements (>15pp)."""
    teams = grid_data.get("teams", [])
    columns = grid_data.get("columns", [])

    for t in teams:
        name = t.get("name", "?")
        cells = t.get("cells", {})
        for col in columns:
            col_key = col.get("key", "")
            col_label = col.get("label", col_key)
            cell = cells.get(col_key)
            if not cell or not cell.get("sources"):
                continue
            sources = cell["sources"]

            # Filter out noise-floor sources: Kalshi/Polymarket at exactly 0.50 (±0.02)
            # are illiquid binary market defaults, not real prices
            meaningful_sources = []
            for s in sources:
                prob = s.get("probability")
                if not isinstance(prob, (int, float)):
                    continue
                source_name = s.get("source", "")
                if source_name in ("kalshi", "polymarket") and abs(prob - 0.50) <= 0.02:
                    continue  # Noise floor — skip
                meaningful_sources.append(s)

            probs = [s.get("probability", 0) for s in meaningful_sources]
            if len(probs) >= 2:
                max_diff = max(probs) - min(probs)
                if max_diff > 0.15:
                    source_detail = ", ".join(f"{s.get('source', '?')}: {s.get('probability', 0)*100:.1f}%" for s in meaningful_sources)
                    report.add(AuditFinding(
                        check="grid_source_disagreement",
                        severity=SEVERITY_CRITICAL,
                        category="grid",
                        description=f"{name} → {col_label}: {max_diff*100:.1f}pp disagreement ({source_detail})",
                        details={"team": name, "column": col_label, "diff_pp": max_diff * 100},
                    ))


def check_grid_monotonicity(grid_data: dict, report: AuditReport):
    """Check that P(earlier round) >= P(later round) for each team."""
    teams = grid_data.get("teams", [])
    columns = grid_data.get("columns", [])
    col_keys = [c.get("key", "") for c in columns]
    col_labels = [c.get("label", c.get("key", "?")) for c in columns]

    for t in teams:
        name = t.get("name", "?")
        cells = t.get("cells", {})
        for i in range(len(col_keys) - 1):
            left_key = col_keys[i]
            right_key = col_keys[i + 1]
            left_prob = (cells.get(left_key) or {}).get("merged_probability")
            right_prob = (cells.get(right_key) or {}).get("merged_probability")
            if left_prob is not None and right_prob is not None:
                if right_prob > left_prob + 0.02:  # >2pp violation
                    report.add(AuditFinding(
                        check="grid_monotonicity",
                        severity=SEVERITY_CRITICAL,
                        category="grid",
                        description=f"{name}: {col_labels[i+1]} ({right_prob*100:.1f}%) > {col_labels[i]} ({left_prob*100:.1f}%)",
                        details={"team": name, "later_round": col_labels[i + 1], "earlier_round": col_labels[i]},
                    ))


def check_grid_universal_trend(grid_data: dict, report: AuditReport):
    """Detect if nearly all teams are trending in the same direction (stale/broken data signal)."""
    teams = grid_data.get("teams", [])
    columns = grid_data.get("columns", [])

    for col in columns:
        col_key = col.get("key", "")
        col_label = col.get("label", col_key)

        positive = 0
        negative = 0
        flat = 0
        for t in teams:
            cell = t.get("cells", {}).get(col_key)
            if not cell:
                continue
            trend = cell.get("trend_24h") or 0
            if trend > 0.001:
                positive += 1
            elif trend < -0.001:
                negative += 1
            else:
                flat += 1

        total_with_data = positive + negative + flat
        if total_with_data < 5:
            continue

        # If >75% of teams trend the same way, flag it
        if negative > total_with_data * 0.75:
            report.add(AuditFinding(
                check="grid_universal_decline",
                severity=SEVERITY_WARNING,
                category="grid",
                description=f"'{col_label}': {negative}/{total_with_data} teams declining in 24h — possible data quality issue",
                details={"column": col_label, "declining": negative, "rising": positive, "flat": flat},
            ))
        elif positive > total_with_data * 0.75:
            report.add(AuditFinding(
                check="grid_universal_rise",
                severity=SEVERITY_INFO,
                category="grid",
                description=f"'{col_label}': {positive}/{total_with_data} teams rising in 24h — unusual but possibly real",
                details={"column": col_label, "declining": negative, "rising": positive, "flat": flat},
            ))


def check_grid_probability_sum(grid_data: dict, report: AuditReport):
    """Check that championship probabilities across all teams sum to ~100%."""
    teams = grid_data.get("teams", [])
    columns = grid_data.get("columns", [])

    for col in columns:
        col_key = col.get("key", "")
        col_label = col.get("label", col_key)

        total = 0.0
        count = 0
        for t in teams:
            cell = t.get("cells", {}).get(col_key)
            if cell and cell.get("merged_probability") is not None:
                total += cell["merged_probability"]
                count += 1

        if count > 0:
            # Championship probs should sum to ~100%
            # Make playoffs probs can sum to any total (12 teams make playoffs → sum ≈ 12*avg)
            if col_key == "championship":
                if abs(total - 1.0) > 0.15:
                    report.add(AuditFinding(
                        check="grid_prob_sum",
                        severity=SEVERITY_WARNING if abs(total - 1.0) < 0.30 else SEVERITY_CRITICAL,
                        category="grid",
                        description=f"'{col_label}' probabilities sum to {total*100:.1f}% across {count} teams (expected ~100%)",
                        details={"column": col_label, "sum_pct": total * 100, "team_count": count},
                    ))


# ---------------------------------------------------------------------------
# GAME STATE: Chart period boundary coverage
# ---------------------------------------------------------------------------

def check_game_state_coverage(event_data: dict, report: AuditReport):
    """Check that a live/completed event has period markers for chart annotations.

    Period boundaries (Q1, HT, Q3, Top 5th, etc.) are critical chart context.
    Every live or completed game should have them from at least one source:
    ScoringPlay table, win_prob_history game_state, ESPN history, or scoring plays.
    """
    event_id = event_data.get("id")
    status = event_data.get("status", "")
    if status not in ("live", "completed", "closed"):
        return  # Scheduled games don't have game state yet

    home = event_data.get("home_team", "?")
    away = event_data.get("away_team", "?")

    try:
        history = api_get(f"/api/events/{event_id}/history")
    except Exception:
        report.add(AuditFinding(
            check="game_state_history_unavailable",
            severity=SEVERITY_WARNING,
            category="event_detail",
            description=f"Could not fetch history for {away} @ {home} (ID: {event_id})",
            details={"event_id": event_id},
        ))
        return

    # Check all period data sources
    period_markers = history.get("period_markers") or []
    espn_history = history.get("espn_history") or []
    win_prob_history = history.get("win_prob_history") or {}
    scoring_plays = history.get("scoring_plays") or []

    # Count periods from each source
    espn_periods = set()
    for pt in espn_history:
        if pt.get("period"):
            espn_periods.add(pt["period"])

    wp_periods = set()
    for source_points in win_prob_history.values():
        for pt in source_points:
            gs = pt.get("game_state") or {}
            if gs.get("period"):
                wp_periods.add(gs["period"])
            elif isinstance(gs.get("inning"), int) and gs["inning"] > 0:
                wp_periods.add(f"inning_{gs['inning']}")

    sp_periods = set()
    for play in scoring_plays:
        if play.get("period"):
            sp_periods.add(play["period"])

    has_period_markers = len(period_markers) > 0
    has_espn_periods = len(espn_periods) > 0
    has_wp_periods = len(wp_periods) > 0
    has_sp_periods = len(sp_periods) > 0

    any_game_state = has_period_markers or has_espn_periods or has_wp_periods or has_sp_periods

    if not any_game_state:
        report.add(AuditFinding(
            check="game_state_missing",
            severity=SEVERITY_CRITICAL,
            category="event_detail",
            description=f"No game state data for {away} @ {home} (ID: {event_id}, status: {status}). Charts have no period boundaries.",
            details={
                "event_id": event_id,
                "status": status,
                "period_markers": len(period_markers),
                "espn_periods": len(espn_periods),
                "wp_periods": len(wp_periods),
                "sp_periods": len(sp_periods),
            },
        ))
    elif not has_period_markers and not has_wp_periods:
        # Period markers missing from primary sources but available in fallbacks
        sources = []
        if has_espn_periods:
            sources.append(f"espn({len(espn_periods)})")
        if has_sp_periods:
            sources.append(f"scoring_plays({len(sp_periods)})")
        report.add(AuditFinding(
            check="game_state_weak_source",
            severity=SEVERITY_INFO,
            category="event_detail",
            description=f"{away} @ {home}: period data only from fallback sources: {', '.join(sources)}",
            details={
                "event_id": event_id,
                "sources": sources,
            },
        ))


def audit_game_state_bulk(verbose: bool = False):
    """Scan all live/completed events from the feed for game state coverage.

    Returns (total_checked, missing_count, findings_list).
    """
    print("\n" + "=" * 70)
    print("GAME STATE COVERAGE AUDIT")
    print("=" * 70)

    feed = api_get("/api/feed", {"limit": "100"})
    items = feed.get("items", [])

    # Collect live + completed events
    events = []
    for item in items:
        data = item.get("data", {})
        status = data.get("status", "")
        if data.get("id") and status in ("live", "completed", "closed"):
            events.append(data)

    print(f"Found {len(events)} live/completed events in feed")

    report = AuditReport()
    results = []

    for ev in events:
        eid = ev["id"]
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        status = ev.get("status", "?")

        try:
            history = api_get(f"/api/events/{eid}/history")
        except Exception:
            results.append({"id": eid, "name": f"{away} @ {home}", "status": status, "game_state": False, "sources": []})
            continue

        period_markers = history.get("period_markers") or []
        espn_history = history.get("espn_history") or []
        win_prob_history = history.get("win_prob_history") or {}
        scoring_plays = history.get("scoring_plays") or []

        sources = []
        if period_markers:
            sources.append(f"period_markers({len(period_markers)})")
        espn_periods = sum(1 for pt in espn_history if pt.get("period"))
        if espn_periods:
            sources.append(f"espn({espn_periods})")
        wp_count = 0
        for pts in win_prob_history.values():
            for pt in pts:
                gs = pt.get("game_state") or {}
                if gs.get("period") or (isinstance(gs.get("inning"), int) and gs["inning"] > 0):
                    wp_count += 1
        if wp_count:
            sources.append(f"win_prob({wp_count})")
        sp_periods = sum(1 for p in scoring_plays if p.get("period"))
        if sp_periods:
            sources.append(f"scoring_plays({sp_periods})")

        has_any = len(sources) > 0
        results.append({
            "id": eid,
            "name": f"{away} @ {home}",
            "status": status,
            "game_state": has_any,
            "sources": sources,
        })

        if not has_any:
            report.add(AuditFinding(
                check="game_state_missing",
                severity=SEVERITY_CRITICAL,
                category="event_detail",
                description=f"No game state: {away} @ {home} (ID: {eid}, {status})",
                details={"event_id": eid, "status": status},
            ))

        if verbose or not has_any:
            icon = "✅" if has_any else "❌"
            src_str = ", ".join(sources) if sources else "NONE"
            print(f"  {icon} [{status:9s}] {away:25s} @ {home:25s}  sources: {src_str}")

    # Summary
    total = len(results)
    missing = sum(1 for r in results if not r["game_state"])
    covered = total - missing
    pct = (covered / total * 100) if total > 0 else 0

    print(f"\n{'─' * 50}")
    print(f"Game state coverage: {covered}/{total} ({pct:.0f}%)")
    if missing > 0:
        print(f"❌ Missing game state: {missing} events")
        for r in results:
            if not r["game_state"]:
                print(f"   - {r['name']} (ID: {r['id']}, {r['status']})")
    else:
        print("✅ All live/completed events have game state data")
    print()

    return total, missing, report.findings


# ---------------------------------------------------------------------------
# Main audit functions
# ---------------------------------------------------------------------------

def audit_event_detail(event_data: dict, report: AuditReport, verbose: bool, skip_llm: bool):
    """Run all event detail page checks."""
    event_id = event_data.get("id")
    home_team = event_data.get("home_team", "Unknown")
    away_team = event_data.get("away_team", "Unknown")
    sport = event_data.get("sport", "unknown")
    sport_key = sport.get("key") if isinstance(sport, dict) else (sport or "unknown")

    print(f"\n1. EVENT DETAIL CHECKS")
    print("-" * 40)
    print(f"   Event: {away_team} at {home_team} (ID: {event_id})")

    # Deterministic checks on the event itself
    check_hero_probability_sanity(event_data, report)
    check_feed_vs_detail_consistency(event_data, report)
    check_missing_team_data(event_data, report)
    check_game_state_coverage(event_data, report)

    # Fetch related futures
    try:
        rf_data = api_get(f"/api/events/{event_id}/related-futures")
    except Exception as e:
        print(f"  Could not fetch related futures: {e}")
        return

    home_futures = rf_data.get("home_team_futures", [])
    away_futures = rf_data.get("away_team_futures", [])

    # Tag futures with side info for downstream checks
    for f in home_futures:
        f["_side"] = "home"
        f["_team"] = home_team
    for f in away_futures:
        f["_side"] = "away"
        f["_team"] = away_team

    all_futures = home_futures + away_futures

    print(f"   Related futures: {len(home_futures)} home, {len(away_futures)} away")

    # Deterministic checks on related futures
    check_matchup_probability_sums(all_futures, report)
    check_duplicate_display_labels(home_futures, home_team, report)
    check_duplicate_display_labels(away_futures, away_team, report)
    check_win_total_noise(home_futures, home_team, report)
    check_win_total_noise(away_futures, away_team, report)
    check_cross_source_display_dupes(home_futures, home_team, report)
    check_cross_source_display_dupes(away_futures, away_team, report)

    # LLM checks
    if not skip_llm:
        print("   Running LLM label clarity check...")
        check_label_clarity_llm(all_futures, sport_key, report, verbose)
        print("   Running LLM team matching check...")
        check_team_matching_llm(all_futures, home_team, away_team, sport_key, report, verbose)


def audit_championship_grid(league: str, report: AuditReport, verbose: bool):
    """Run all championship grid checks."""
    print(f"\n2. CHAMPIONSHIP GRID CHECKS ({league.upper()})")
    print("-" * 40)

    try:
        grid_data = api_get(f"/api/playoffs/{league}")
    except Exception as e:
        print(f"  Could not fetch grid for {league}: {e}")
        return

    teams = grid_data.get("teams", [])
    columns = grid_data.get("columns", [])
    col_labels = [c.get("label", c.get("key")) for c in columns]

    print(f"   {len(teams)} teams × {len(columns)} columns ({', '.join(col_labels)})")
    print(f"   Sources available: {', '.join(grid_data.get('sources_available', []))}")

    # Run all deterministic checks
    check_grid_column_fill_rate(grid_data, report)
    check_grid_source_coverage(grid_data, report)
    check_grid_missing_columns(grid_data, league, report)
    check_grid_team_identity(grid_data, league, report)
    check_grid_source_disagreement(grid_data, report)
    check_grid_monotonicity(grid_data, report)
    check_grid_universal_trend(grid_data, report)
    check_grid_probability_sum(grid_data, report)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive page health audit for BainLuck",
        epilog="""
Examples:
  # Quick deterministic scan (free, instant):
  python3 scripts/audit_matching_quality.py --skip-llm

  # Full audit with LLM, save baseline:
  OPENAI_API_KEY=... python3 scripts/audit_matching_quality.py --save

  # Compare against last baseline (shows what's fixed/new):
  python3 scripts/audit_matching_quality.py --skip-llm --compare --save

  # Grid-only audit:
  python3 scripts/audit_matching_quality.py --skip-event --grid nba --skip-llm

  # Game state coverage scan (all live/completed events):
  python3 scripts/audit_matching_quality.py --game-state

  # Verbose game state scan (shows all events, not just missing):
  python3 scripts/audit_matching_quality.py --game-state --verbose
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--event-id", type=int, help="Specific event ID to audit")
    parser.add_argument("--grid", default="mlb", help="Championship grid to audit (default: mlb)")
    parser.add_argument("--max-items", type=int, default=50, help="Max items per LLM batch (default: 50)")
    parser.add_argument("--verbose", action="store_true", help="Print each judgment")
    parser.add_argument("--skip-event", action="store_true", help="Skip event audit")
    parser.add_argument("--skip-grid", action="store_true", help="Skip grid audit")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM checks (deterministic only)")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--save", action="store_true", help="Save results as new baseline")
    parser.add_argument("--compare", action="store_true", help="Compare against last baseline")
    parser.add_argument("--game-state", action="store_true", help="Bulk game state coverage scan across all live/completed feed events")
    args = parser.parse_args()

    # --- Standalone game state audit ---
    if args.game_state:
        total, missing, findings = audit_game_state_bulk(verbose=args.verbose)
        sys.exit(1 if missing > 0 else 0)

    if not args.skip_llm and not os.getenv("OPENAI_API_KEY"):
        print("ERROR: Set OPENAI_API_KEY or use --skip-llm for deterministic-only mode")
        sys.exit(1)

    report = AuditReport(grid_league=args.grid)

    # --- Event audit ---
    if not args.skip_event:
        event_data = find_audit_event(args.event_id)
        report.event_id = event_data.get("id")
        report.event_name = f"{event_data.get('away_team', '?')} at {event_data.get('home_team', '?')}"
        audit_event_detail(event_data, report, args.verbose, args.skip_llm)

    # --- Grid audit ---
    if not args.skip_grid:
        audit_championship_grid(args.grid, report, args.verbose)

    # --- Load baseline for comparison ---
    baseline = None
    if args.compare:
        baseline = load_baseline()
        if not baseline:
            print("  (no previous baseline found — this will be the first)")

    # --- Output ---
    if args.json:
        print(json.dumps(report.to_json(), indent=2))
    else:
        print(report.summary(baseline=baseline))

    # --- Save baseline ---
    if args.save:
        path = save_baseline(report)
        print(f"Baseline saved: {path}")

    # Estimate OpenAI cost if LLM was used
    if not args.skip_llm:
        llm_findings = [f for f in report.findings if f.check in ("label_clarity", "team_matching")]
        print(f"LLM checks contributed {len(llm_findings)} findings")
        print(f"Estimated OpenAI cost: ~$0.01-0.03")


if __name__ == "__main__":
    main()
