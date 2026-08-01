"""Daily grid-register drift sentinel (Queue 295, Item 2).

The register pins each grid cell to an exact market identity. Sources do not
hold still: they rename tickers mid-season, settle markets when a team clinches
or is eliminated, and publish next season's set under new tickers while the
current one is still trading. A pinned register that nobody checks goes stale
just as silently as fuzzy matching went wrong — so this runs daily, compares
every registered identity against current source inventory, and splits what it
finds into exactly two buckets:

* **Unambiguous** — the identity is unchanged and only its ticker was renamed,
  or the market settled with an authoritative result. A deterministic rule can
  version that forward, so the sentinel proposes a validated next version.
* **Ambiguous** — a *different* market now backs the cell, two markets compete
  for it, a registered identity has vanished, or a next-season set appeared.
  These are never applied. One deduped P2 ``needs-triage`` issue is filed per
  league with the evidence needed to answer it in one tap.

Safety properties this module is written to hold:

* One poison league cannot starve its siblings or publish a partial mixed
  version — every league is isolated in its own try/except and publishes
  independently, all-or-nothing.
* A malformed generation never replaces a good register: the proposed version is
  validated as a transition BEFORE anything is written, and writes go through
  temp + atomic rename.
* Publication is opt-in (``apply=False`` by default) so the first runs are
  dry-run/diff only.
* Closure follows the ratified 24h continuous-GREEN rule via the shared filing
  rail; this sentinel does not own closure and does not hand it to Board
  Sentinel either.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.league_configs import get_league_config
from app.utils.grid_register import (
    GridRegister,
    REGISTER_DIR,
    build_contract,
    classify,
    diff_against_inventory,
    load_register,
    register_filename,
    validate_register,
    validate_transition,
)

logger = logging.getLogger(__name__)

#: Leagues the sentinel will look for registers for. A league with no committed
#: register is reported as ``no_register`` and skipped — not an error.
REGISTER_LEAGUES = ("nba", "nhl", "mlb", "nfl", "golf")

#: Per-run wall-clock bound. A sentinel that can run long is a sentinel that
#: gets SIGKILLed mid-write (gotcha #51 class), so it stops cleanly instead.
DEADLINE_SECONDS = 240.0

REDIS_KEY = "bainluck:grid_register_sentinel:last"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def register_age_hours(register: dict[str, Any], now: datetime | None = None) -> float | None:
    """Hours since the register was generated, or ``None`` if unparseable."""
    stamp = register.get("generated_at")
    if not isinstance(stamp, str):
        return None
    try:
        generated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return round(((now or _now()) - generated).total_seconds() / 3600.0, 2)


def drift_fingerprint(league: str, findings: list[str]) -> str:
    """Stable dedup key: same league + same drift shape == same issue.

    Deliberately keyed on the finding SET, not on counts, so a drift that grows
    from three cells to five updates the existing issue instead of filing a new
    one every night.
    """
    payload = f"grid-register-drift:{league}:{','.join(sorted(set(findings)))}"
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def propose_transition(
    register: dict[str, Any],
    candidates: list[dict],
    findings: list[str],
    *,
    observed_at: str | None = None,
) -> dict[str, Any] | None:
    """Build the next register version for UNAMBIGUOUS drift only.

    The deterministic rule, and nothing beyond it:
      * a renamed ticker on the same pinned identity updates ``external_id``;
      * an authoritative settlement on the same pinned identity flips the entry
        to ``settled`` with its terminal result and drops the live identity's
        claim to a probability.

    Returns ``None`` when there is nothing safely applicable. Any ambiguity in
    ``findings`` disqualifies the whole league — a partially-applied register is
    a mixed-version register, which is exactly what must never publish.
    """
    verdict = classify(findings, transition_ok=True)
    if verdict["classification"] != "unambiguous_drift":
        return None

    by_cell = {
        (row.get("stage"), row.get("entity_key"), row.get("source")): row
        for row in candidates
    }
    observed = observed_at or _now().isoformat()

    entries: list[dict[str, Any]] = []
    changed = False
    for entry in register.get("entries", []):
        if not isinstance(entry, dict):
            return None
        new_entry = dict(entry)
        row = by_cell.get((entry.get("stage"), entry.get("entity_key"), entry.get("source")))
        same_identity = row is not None and (
            row.get("market_id") == entry.get("market_id")
            and row.get("outcome_id") == entry.get("outcome_id")
        )
        if same_identity:
            if (
                row.get("status") == "settled"
                and entry.get("status") == "live"
                and row.get("terminal_result") in ("won", "eliminated")
            ):
                new_entry["status"] = "settled"
                new_entry["terminal_result"] = row["terminal_result"]
                new_entry["evidence"] = {
                    "kind": "authoritative_settlement",
                    "observed_at": observed,
                    "market_name": row.get("market_name"),
                }
                changed = True
            elif row.get("external_id") != entry.get("external_id"):
                new_entry["external_id"] = row.get("external_id")
                new_entry["evidence"] = {
                    "kind": "exact_identity_rename",
                    "observed_at": observed,
                    "previous_external_id": entry.get("external_id"),
                    "market_name": row.get("market_name"),
                }
                changed = True
        entries.append(new_entry)

    if not changed:
        return None

    proposed = dict(register)
    proposed["entries"] = entries
    proposed["version"] = register.get("version", 0) + 1
    proposed["supersedes_version"] = register.get("version")
    proposed["generated_at"] = observed
    return proposed


def publish_register(
    proposed: dict[str, Any],
    directory: Path | None = None,
) -> dict[str, Any]:
    """Atomically publish a validated register version.

    Temp file + rename, so a crash mid-write leaves the previous last-good
    register fully intact rather than a truncated one the serving path would
    read as a wrong number.
    """
    target_dir = directory or REGISTER_DIR
    path = target_dir / register_filename(proposed["league"], proposed["season"])
    tmp = path.with_suffix(".json.tmp")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(proposed, indent=2, sort_keys=True) + "\n")
        tmp.replace(path)
    except OSError as exc:
        # Ephemeral/read-only filesystems are expected in some deploys. The
        # proposal still travels in the run payload; the last-good register on
        # disk is untouched.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        logger.warning("Grid register publish failed for %s: %s", proposed["league"], exc)
        return {"published": False, "reason": f"write_failed: {exc}", "path": str(path)}
    return {"published": True, "path": str(path), "version": proposed["version"]}


def build_drift_issue_body(result: dict[str, Any]) -> str:
    """MC-ready evidence: what changed, what we refuse to guess, and the options."""
    league = result["league"]
    lines = [
        f"**Grid register drift — {league.upper()}** (register v{result.get('version')}, "
        f"season {result.get('season')})",
        "",
        f"The daily register sentinel found drift it will NOT resolve on its own. "
        f"The register is unchanged and the grid keeps serving v{result.get('version')} "
        f"until this is answered.",
        "",
        f"- findings: `{', '.join(result.get('findings', [])) or 'none'}`",
        f"- registered cells: {result.get('counters', {})}",
        f"- observed candidates: {result.get('candidate_count')}",
        f"- register age: {result.get('age_hours')}h",
        "",
        "**Question for Alex**",
        "",
    ]
    for row in result.get("ambiguities", [])[:10]:
        reason = row.get("reason", "?")
        if reason == "multiple_candidates":
            lines.append(
                f"- `{row.get('stage')}` / `{row.get('entity_key')}` / `{row.get('source')}`: "
                f"{len(row.get('candidates', []))} markets claim this cell — "
                + "; ".join(
                    f"#{c.get('market_id')} {c.get('market_name')!r} ({c.get('external_id')})"
                    for c in row.get("candidates", [])[:3]
                )
            )
        else:
            lines.append(
                f"- `{reason}`: `{row.get('stage')}` / `{row.get('outcome_name') or row.get('entity_key')}` "
                f"({row.get('source')}, market #{row.get('market_id')})"
            )
    if not result.get("ambiguities"):
        lines.append("- see `findings` above; no per-cell detail was captured.")
    lines += [
        "",
        "**Options**",
        "1. Point the cell at one of the listed markets (I will pin it and version the register).",
        "2. Mark the cell `missing` (renders an honest empty cell, no number).",
        "3. Tell me the rule and I will make the generator deterministic for this class.",
        "",
        f"<!-- fingerprint: {result.get('fingerprint')} -->",
    ]
    return "\n".join(lines)


async def _run_league(session, league: str, *, apply: bool, directory: Path | None) -> dict[str, Any]:
    """Audit one league's register. Isolated so a poison league cannot spread."""
    from app.services.grid_register_source import build_candidates

    config = get_league_config(league)
    result: dict[str, Any] = {"league": league, "status": "ok"}
    if not config:
        return {"league": league, "status": "unknown_league"}

    register_data = load_register(config.slug, config.season_pattern, directory=directory)
    if register_data is None:
        return {
            "league": league,
            "status": "no_register",
            "season": config.season_pattern,
        }

    contract = build_contract({
        config.slug: {
            "season": config.season_pattern,
            "stages": [c.key for c in config.columns],
        },
    })

    # A committed register that no longer validates is a hard stop for this
    # league: we neither serve a transition from it nor try to repair it.
    base_findings = validate_register(register_data, contract)
    view = GridRegister(register_data)
    result.update({
        "season": config.season_pattern,
        "version": view.version,
        "age_hours": register_age_hours(register_data),
        "counters": view.counters(),
    })
    if base_findings:
        result.update({
            "status": "invalid_register",
            "findings": base_findings,
            "classification": "invalid",
            "action": "reject_register",
            "published": False,
        })
        return result

    candidates, unresolved = await build_candidates(session, config)
    findings = diff_against_inventory(register_data, candidates)
    result["candidate_count"] = len(candidates)
    result["ambiguities"] = unresolved
    result["findings"] = findings

    proposed = propose_transition(register_data, candidates, findings)
    transition_findings = validate_transition(register_data, proposed, contract) if proposed else []
    verdict = classify(
        findings,
        transition_ok=(not transition_findings) if proposed is not None else None,
    )
    result.update(verdict)
    result["transition_findings"] = transition_findings

    published = False
    if verdict["publish"] and proposed is not None and not transition_findings:
        if apply:
            outcome = publish_register(proposed, directory)
            published = outcome["published"]
            result["publish_result"] = outcome
        else:
            result["publish_result"] = {"published": False, "reason": "dry_run"}
        result["proposed_version"] = proposed["version"]
    result["published"] = published

    if verdict["action"] == "file_p2_needs_triage":
        result["fingerprint"] = drift_fingerprint(league, findings)

    return result


async def _run_grid_register_sentinel(
    *,
    apply: bool = False,
    file_issues: bool = True,
    deadline_seconds: float = DEADLINE_SECONDS,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Run the drift sentinel across every league that has a register."""
    from app.services.database import async_session_maker

    start = _time.monotonic()
    stats: dict[str, Any] = {
        "mode": "apply" if apply else "dry_run",
        "leagues": [],
        "filed": [],
        "errors": [],
    }

    async with async_session_maker() as session:
        for league in REGISTER_LEAGUES:
            if _time.monotonic() - start > deadline_seconds:
                stats["errors"].append({"deadline": f"stopped before {league}"})
                break
            try:
                stats["leagues"].append(
                    await _run_league(session, league, apply=apply, directory=directory)
                )
            except Exception as exc:
                # One league's failure must never starve the rest, and must
                # never be mistaken for "clean".
                logger.error("Grid register sentinel: %s crashed: %s", league, exc)
                stats["errors"].append({"league": league, "error": str(exc)[:200]})
                stats["leagues"].append({
                    "league": league,
                    "status": "crashed",
                    "classification": "invalid",
                    "action": "reject_register",
                    "published": False,
                    "failure_cause": str(exc)[:200],
                })

    active = [lg for lg in stats["leagues"] if lg.get("status") not in ("no_register", "unknown_league")]
    needs_ruling = [lg for lg in active if lg.get("action") == "file_p2_needs_triage"]

    stats["scorecard"] = {
        "leagues_total": len(stats["leagues"]),
        "leagues_with_register": len(active),
        "leagues_clean": len([lg for lg in active if lg.get("classification") == "clean"]),
        "leagues_needs_ruling": len(needs_ruling),
        "leagues_published": len([lg for lg in active if lg.get("published")]),
        "per_league": [
            {
                "league": lg["league"],
                "status": lg.get("status"),
                "version": lg.get("version"),
                "age_hours": lg.get("age_hours"),
                "classification": lg.get("classification"),
                "action": lg.get("action"),
                "published": lg.get("published", False),
                "missing": (lg.get("counters") or {}).get("missing", 0),
                "settled": (lg.get("counters") or {}).get("settled", 0),
                "live": (lg.get("counters") or {}).get("live", 0),
                "drift": len(lg.get("findings") or []),
                "ambiguous": len(lg.get("ambiguities") or []),
                "failure_cause": lg.get("failure_cause"),
            }
            for lg in stats["leagues"]
        ],
    }

    if file_issues and needs_ruling:
        try:
            from app.tasks.sentinel_filing import list_open_alert_issues, reconcile_issue

            open_issues = list_open_alert_issues()
            for lg in needs_ruling:
                stats["filed"].append(reconcile_issue(
                    red=True,
                    fingerprint=lg["fingerprint"],
                    marker_key=f"grid_register_drift:{lg['league']}",
                    title=(
                        f"[Grid Register] {lg['league'].upper()}: "
                        "ambiguous identity drift needs a ruling"
                    ),
                    title_prefix=f"[Grid Register] {lg['league'].upper()}:",
                    body=build_drift_issue_body(lg),
                    labels=["alert-intake", "type:bug", "priority:p2",
                            "needs-triage", "area:grids"],
                    open_issues=open_issues,
                ))
        except Exception as exc:
            logger.error("Grid register sentinel: filing failed: %s", exc)
            stats["errors"].append({"filing": str(exc)[:200]})

    stats["duration_seconds"] = round(_time.monotonic() - start, 1)
    stats["generated_at"] = _now().isoformat()

    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(REDIS_KEY, 14 * 86400, json.dumps(stats, default=str))
    except Exception as exc:
        logger.warning("Grid register sentinel cache write failed: %s", exc)

    logger.info(
        "Grid register sentinel (%s): %d/%d registers clean, %d need a ruling, "
        "%d published in %.1fs",
        stats["mode"],
        stats["scorecard"]["leagues_clean"],
        stats["scorecard"]["leagues_with_register"],
        stats["scorecard"]["leagues_needs_ruling"],
        stats["scorecard"]["leagues_published"],
        stats["duration_seconds"],
    )
    return stats
