#!/usr/bin/env python3
"""Manus-powered health audit suite for Bain Luck.

Submits audit prompts to Manus in parallel, polls for completion,
and collects results into a dated directory.

Usage:
    MANUS_API_KEY=... python3 scripts/manus_health_suite.py

    # Run specific modules only:
    MANUS_API_KEY=... python3 scripts/manus_health_suite.py --modules event_detail feed

    # List available modules:
    python3 scripts/manus_health_suite.py --list

    # Check status of a running suite:
    MANUS_API_KEY=... python3 scripts/manus_health_suite.py --status 2026-04-22
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

API_KEY = os.getenv("MANUS_API_KEY", "")
BASE = "https://api.manus.ai/v2"
PROMPTS_DIR = Path(__file__).parent / ".." / ".." / "Manus" / "prompts"
RESULTS_DIR = Path(__file__).parent / ".." / ".." / "Manus" / "audit_results"

MODULES = {
    "event_detail": {
        "file": "event_detail_audit.md",
        "name": "Event Detail Deep Audit",
        "priority": 1,
        "timeout": 1800,
    },
    "feed": {
        "file": "feed_audit.md",
        "name": "Feed & Discovery Audit",
        "priority": 1,
    },
    "league_page": {
        "file": "league_page_audit.md",
        "name": "Sport & League Page Audit",
        "priority": 2,
    },
    "market_completeness": {
        "file": "market_completeness.md",
        "name": "Market Completeness Audit",
        "priority": 2,
    },
    "visual_review": {
        "file": "visual_review.md",
        "name": "Visual Design Review",
        "priority": 3,
    },
    "chart_timing": {
        "file": "chart_timing_audit.md",
        "name": "Chart Timing & Boundary Audit",
        "priority": 2,
    },
    "grid": {
        "file": "grid_audit.md",
        "name": "Championship Grid Deep Audit",
        "priority": 2,
    },
    "grid_ground_truth": {
        "file": "grid_ground_truth.md",
        "name": "Grid Ground Truth Capture",
        "priority": 3,
        "timeout": 1200,
    },
    "event_matching": {
        "file": "event_matching_ground_truth.md",
        "name": "Event Matching Ground Truth Sweep",
        "priority": 1,
        "timeout": 1800,
    },
    "market_accuracy": {
        "file": "market_accuracy_ground_truth.md",
        "name": "Market Accuracy & Monotonicity Audit",
        "priority": 1,
        "timeout": 1800,
    },
    "category_page": {
        "file": "category_page_audit.md",
        "name": "Category Page Audit (Politics, Entertainment, Economics, Weather)",
        "priority": 1,
        "timeout": 2400,
    },
}


def submit_task(prompt_text: str, module_name: str, display_name: str) -> str | None:
    """Submit a prompt to the Manus API. Returns task_id."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    resp = httpx.post(
        f"{BASE}/task.create",
        json={
            "message": {"content": prompt_text},
            "title": f"BainLuck Health: {display_name} ({date_str})",
            "hide_in_task_list": True,
            "agent_profile": "manus-1.6-max",
        },
        headers={"x-manus-api-key": API_KEY},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  ERROR submitting {module_name}: {resp.status_code} {resp.text[:200]}")
        return None
    data = resp.json()
    task_id = data.get("task_id")
    task_url = data.get("task_url", f"https://manus.im/app/{task_id}")
    if task_id:
        print(f"  Submitted {module_name}: {task_id}")
        print(f"    View: {task_url}")
    return task_id


def get_task_status(task_id: str) -> dict | None:
    """Quick status check via task.detail."""
    try:
        resp = httpx.get(
            f"{BASE}/task.detail",
            params={"task_id": task_id},
            headers={"x-manus-api-key": API_KEY},
            timeout=15,
        )
        data = resp.json()
        return data.get("task", {})
    except Exception:
        return None


def _ts() -> str:
    """Return a compact timestamp for log lines."""
    return datetime.now().strftime("%H:%M:%S")


def _collect_messages(task_id: str) -> dict:
    """Fetch final messages from a completed task. Raises on failure."""
    resp = httpx.get(
        f"{BASE}/task.listMessages",
        params={"task_id": task_id, "order": "asc", "limit": 100},
        headers={"x-manus-api-key": API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def poll_task(task_id: str, timeout_seconds: int = 900) -> dict | None:
    """Poll a Manus task until completion. Returns final messages.

    Collection phase retries up to 3 times with 30s delay if the task
    completed but message retrieval fails.
    """
    max_polls = timeout_seconds // 15
    for i in range(max_polls):
        try:
            task = get_task_status(task_id)
            if task:
                status = task.get("status", "running")
                credits = task.get("credit_usage", 0)

                if status == "stopped":
                    # Task completed — collect messages with retry
                    for attempt in range(1, 4):
                        try:
                            print(f"    [{_ts()}] Task stopped — collecting results (attempt {attempt}/3)...")
                            full = _collect_messages(task_id)
                            full["_credit_usage"] = credits
                            return full
                        except Exception as collect_err:
                            print(f"    [{_ts()}] Collection attempt {attempt}/3 failed: {collect_err}")
                            if attempt < 3:
                                print(f"    [{_ts()}] Retrying in 30s...")
                                time.sleep(30)
                    # All 3 collection attempts failed
                    print(f"    [{_ts()}] All collection attempts failed for {task_id}")
                    return {"error": True, "collection_failed": True, "_credit_usage": credits}
                elif status == "error":
                    print(f"    [{_ts()}] Task errored (credits: {credits})")
                    return {"error": True, "_credit_usage": credits}
                elif status == "waiting":
                    detail = httpx.get(
                        f"{BASE}/task.listMessages",
                        params={"task_id": task_id, "order": "desc", "limit": 3},
                        headers={"x-manus-api-key": API_KEY},
                        timeout=30,
                    ).json()
                    for msg in detail.get("messages", []):
                        su = msg.get("status_update", {})
                        sd = su.get("status_detail", {})
                        evt_type = sd.get("waiting_for_event_type", "")
                        evt_id = sd.get("waiting_for_event_id", "")
                        if evt_type and evt_type != "messageAskUser" and evt_id:
                            print(f"    [{_ts()}] Auto-confirming {evt_type}...")
                            httpx.post(
                                f"{BASE}/task.confirmAction",
                                json={"task_id": task_id, "event_id": evt_id, "input": {"accept": True}},
                                headers={"x-manus-api-key": API_KEY},
                                timeout=15,
                            )
                            break
                    else:
                        print(f"    [{_ts()}] [{i+1}/{max_polls}] waiting (may need manual input)")
                else:
                    print(f"    [{_ts()}] [{i+1}/{max_polls}] running... ({credits} credits)")
            else:
                print(f"    [{_ts()}] [{i+1}/{max_polls}] status check returned None — retrying...")

        except Exception as e:
            print(f"    [{_ts()}] Poll error: {e}")

        time.sleep(15)

    print(f"    [{_ts()}] Timed out after {timeout_seconds}s for task {task_id}")
    return None


def extract_report(messages: dict) -> str:
    """Extract the final report text from Manus messages."""
    parts = []
    for msg in messages.get("messages", []):
        if msg.get("type") == "assistant_message":
            content = msg.get("assistant_message", {}).get("content", "")
            if content:
                parts.append(content)
            for att in msg.get("assistant_message", {}).get("attachments", []):
                parts.append(f"\n**Attachment:** {att.get('file_name')} — {att.get('url')}")
    return "\n\n".join(parts)


GROUND_TRUTH_MODULES = {"grid_ground_truth", "event_matching"}

# Keywords that signal critical findings in a report
CRITICAL_KEYWORDS = ["critical", "broken", "crash", "0/100", "0%", "fail", "error", "bug"]


def extract_json_from_report(report_text: str) -> dict | None:
    """Extract a JSON code block from a Manus report.

    Ground truth modules output structured JSON inside ```json ... ``` blocks.
    """
    import re
    pattern = re.compile(r"```json\s*\n(.*?)\n\s*```", re.DOTALL)
    match = pattern.search(report_text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _count_critical_keywords(report_text: str) -> dict[str, int]:
    """Count occurrences of each critical keyword in a report (case-insensitive)."""
    text_lower = report_text.lower()
    counts: dict[str, int] = {}
    for kw in CRITICAL_KEYWORDS:
        n = text_lower.count(kw)
        if n > 0:
            counts[kw] = n
    return counts


def _load_previous_manifest() -> dict | None:
    """Load the manifest from the current 'latest' symlink, if it exists."""
    latest = RESULTS_DIR / "latest"
    if not latest.is_symlink() and not latest.exists():
        return None
    manifest_path = latest / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def run_regression_detection(manifest: dict, results: dict[str, str]):
    """Phase 4: Compare current sweep against previous sweep for regressions.

    Modifies manifest in-place to add ``diagnostics`` key with keyword counts.
    Prints a summary of regressions, improvements, and new critical findings.
    """
    prev_manifest = _load_previous_manifest()

    # --- Keyword diagnostics for current sweep ---
    diagnostics: dict[str, dict[str, int]] = {}
    for module_name, report_text in results.items():
        diagnostics[module_name] = _count_critical_keywords(report_text)
    manifest["diagnostics"] = diagnostics

    if prev_manifest is None:
        print("  No previous sweep found — skipping regression comparison.")
        # Still print keyword summary for the current sweep
        total_kw = sum(sum(c.values()) for c in diagnostics.values())
        print(f"  Current sweep: {total_kw} critical keyword occurrences across {len(diagnostics)} modules.")
        return

    prev_date = prev_manifest.get("date", "unknown")
    prev_tasks = prev_manifest.get("tasks", {})
    prev_diagnostics = prev_manifest.get("diagnostics", {})

    regressions: list[str] = []
    improvements: list[str] = []

    # --- Status comparison ---
    all_modules = set(manifest["tasks"].keys()) | set(prev_tasks.keys())
    for module in sorted(all_modules):
        cur_status = manifest["tasks"].get(module, {}).get("status")
        prev_status = prev_tasks.get(module, {}).get("status")

        if prev_status is None or cur_status is None:
            continue  # Module only exists in one sweep — not a regression

        if prev_status == "complete" and cur_status in ("timeout", "error", "collection_failed"):
            regressions.append(f"  - {module}: was complete, now {cur_status}")
        elif prev_status in ("timeout", "error", "collection_failed") and cur_status == "complete":
            improvements.append(f"  - {module}: was {prev_status}, now complete")

    # --- Keyword count comparison ---
    new_critical_findings: list[str] = []
    for module_name, cur_counts in diagnostics.items():
        prev_counts = prev_diagnostics.get(module_name, {})
        cur_total = sum(cur_counts.values())
        prev_total = sum(prev_counts.values())
        delta = cur_total - prev_total
        if delta > 0:
            new_critical_findings.append(
                f"  - {module_name}: {cur_total} keywords (was {prev_total}, +{delta})"
            )

    # --- Summary ---
    n_regressions = len(regressions)
    n_improvements = len(improvements)
    n_new_findings = len(new_critical_findings)

    print(f"\n  Compared against previous sweep ({prev_date}):")
    print(f"  {n_regressions} regression(s), {n_improvements} improvement(s), "
          f"{n_new_findings} new critical finding(s)")

    if regressions:
        print("\n  REGRESSIONS (status downgrade):")
        for line in regressions:
            print(line)

    if improvements:
        print("\n  IMPROVEMENTS (status upgrade):")
        for line in improvements:
            print(line)

    if new_critical_findings:
        print("\n  NEW CRITICAL FINDINGS (keyword count increase):")
        for line in new_critical_findings:
            print(line)

    if not regressions and not improvements and not new_critical_findings:
        print("  No changes detected.")


def run_suite(module_names: list[str]):
    """Run the full audit suite."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = RESULTS_DIR / date_str
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Manus Health Audit Suite — {date_str}")
    print(f"Output: {output_dir}")
    print(f"Modules: {', '.join(module_names)}")
    print()

    # Phase 1: Submit all tasks
    print("Phase 1: Submitting tasks...")
    tasks = {}
    for name in module_names:
        module = MODULES[name]
        prompt_path = PROMPTS_DIR / module["file"]
        if not prompt_path.exists():
            print(f"  SKIP {name}: prompt file not found at {prompt_path}")
            continue
        prompt_text = prompt_path.read_text()
        task_id = submit_task(prompt_text, name, module["name"])
        if task_id:
            tasks[name] = task_id

    if not tasks:
        print("\nNo tasks submitted. Check your MANUS_API_KEY and prompt files.")
        sys.exit(1)

    # Save task manifest
    manifest = {
        "date": date_str,
        "mode": sweep_mode if "sweep_mode" in dir() else os.getenv("MANUS_SWEEP_MODE", "deep"),
        "new_findings_count": None,
        "tasks": {
            name: {
                "task_id": tid,
                "status": "running",
                "task_url": f"https://manus.im/app/{tid}",
                "credits": 0,
            }
            for name, tid in tasks.items()
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest saved: {manifest_path}")

    # Phase 2: Poll all tasks in parallel
    # Each task gets its own per-module timeout. Tasks are already running
    # concurrently on Manus, so we poll them concurrently too.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    phase_start = time.monotonic()
    print(f"\nPhase 2: Polling {len(tasks)} tasks in parallel...")
    print(f"  [{_ts()}] Phase 2 started")
    results = {}

    def _poll_one(name: str, task_id: str) -> tuple[str, dict | None]:
        module_timeout = MODULES.get(name, {}).get("timeout", 900)
        print(f"  [{_ts()}] Polling {name} ({task_id}, timeout={module_timeout}s)...")
        result = poll_task(task_id, timeout_seconds=module_timeout)
        return name, result

    with ThreadPoolExecutor(max_workers=min(len(tasks), 5)) as pool:
        futures = {pool.submit(_poll_one, name, tid): name for name, tid in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            task_id = tasks[name]
            try:
                _, result = future.result()
            except Exception as e:
                print(f"  [{_ts()}] EXCEPTION: {name} — {e}")
                manifest["tasks"][name]["status"] = "error"
                continue

            credits = result.get("_credit_usage", 0) if result else 0
            if result is None:
                print(f"  [{_ts()}] TIMEOUT: {name}")
                manifest["tasks"][name]["status"] = "timeout"
            elif result.get("collection_failed"):
                print(f"  [{_ts()}] COLLECTION_FAILED: {name}")
                manifest["tasks"][name]["status"] = "collection_failed"
            elif result.get("error"):
                print(f"  [{_ts()}] ERROR: {name}")
                manifest["tasks"][name]["status"] = "error"
            else:
                print(f"  [{_ts()}] COMPLETE: {name} ({credits} credits)")
                manifest["tasks"][name]["status"] = "complete"
                report = extract_report(result)
                results[name] = report

                report_path = output_dir / f"{name}.md"
                report_path.write_text(report)
                print(f"    Report: {report_path}")

                if name in GROUND_TRUTH_MODULES:
                    gt_data = extract_json_from_report(report)
                    if gt_data:
                        gt_filename = {
                            "grid_ground_truth": "grid_ground_truth.json",
                            "event_matching": "event_matching_ground_truth.json",
                        }.get(name, f"{name}_ground_truth.json")
                        gt_path = output_dir / gt_filename
                        gt_path.write_text(json.dumps(gt_data, indent=2))
                        print(f"    Ground truth JSON: {gt_path}")
                    else:
                        print(f"    No JSON block found in {name} report")
        manifest["tasks"][name]["credits"] = credits

    phase_elapsed = time.monotonic() - phase_start
    print(f"\n  [{_ts()}] Phase 2 finished in {phase_elapsed:.0f}s")

    # Phase 3: Generate combined report
    print(f"\n[{_ts()}] Phase 3: Generating combined report...")
    n_complete = sum(1 for t in manifest["tasks"].values() if t["status"] == "complete")
    n_failed = sum(1 for t in manifest["tasks"].values() if t["status"] != "complete")
    combined = [f"# Manus Health Audit — {date_str}\n"]
    combined.append(f"**Modules run:** {len(tasks)}")
    combined.append(f"**Completed:** {n_complete}")
    combined.append(f"**Failed/Timeout:** {n_failed}")
    # List failures with reason for quick diagnosis
    for tname, tinfo in manifest["tasks"].items():
        if tinfo["status"] != "complete":
            combined.append(f"- {tname}: {tinfo['status']}")
    combined.append("")

    for name in module_names:
        if name in results:
            combined.append(f"---\n\n## {MODULES[name]['name']}\n")
            combined.append(results[name])
            combined.append("")

    combined_path = output_dir / "combined_report.md"
    combined_path.write_text("\n".join(combined))

    # Phase 4: Regression detection (runs BEFORE updating latest symlink
    # so _load_previous_manifest reads the prior sweep)
    print(f"\n[{_ts()}] Phase 4: Regression detection...")
    run_regression_detection(manifest, results)

    # Update manifest (now includes diagnostics from Phase 4)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Symlink latest
    latest = RESULTS_DIR / "latest"
    if latest.is_symlink():
        latest.unlink()
    latest.symlink_to(date_str)

    print(f"\nCombined report: {combined_path}")
    print(f"Latest symlink: {latest} -> {date_str}")
    print("\nDone.")


def check_status(date_str: str):
    """Check status of a running suite."""
    manifest_path = RESULTS_DIR / date_str / "manifest.json"
    if not manifest_path.exists():
        print(f"No manifest found for {date_str}")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    print(f"Suite: {manifest['date']}")
    for name, info in manifest["tasks"].items():
        status = info["status"]
        icon = {"running": "...", "complete": "OK", "error": "ERR", "timeout": "T/O", "collection_failed": "CFail"}.get(status, "?")
        print(f"  [{icon:3s}] {name:25s} {info['task_id']}")
        if status == "running":
            print(f"        View: https://manus.im/app/{info['task_id']}")


def main():
    parser = argparse.ArgumentParser(description="Manus Health Audit Suite")
    parser.add_argument(
        "--modules",
        nargs="+",
        choices=list(MODULES.keys()),
        help="Run specific modules (default: all)",
    )
    parser.add_argument("--list", action="store_true", help="List available modules")
    parser.add_argument("--status", metavar="DATE", help="Check status of a running suite (YYYY-MM-DD)")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run smoke test modules only (event_detail + feed)",
    )
    args = parser.parse_args()

    if args.list:
        print("Available modules:")
        for name, info in sorted(MODULES.items(), key=lambda x: x[1]["priority"]):
            print(f"  P{info['priority']} {name:25s} {info['name']}")
        sys.exit(0)

    if args.status:
        check_status(args.status)
        sys.exit(0)

    if not API_KEY:
        print("Set MANUS_API_KEY environment variable")
        sys.exit(1)

    sweep_mode = os.getenv("MANUS_SWEEP_MODE", "deep")

    if args.smoke:
        module_names = ["event_detail", "feed"]
    elif args.modules:
        module_names = args.modules
    elif sweep_mode == "light":
        # Light sweep: feed + event_detail + one rotating module
        _ROTATION = [
            "market_accuracy", "category_page", "event_matching",
            "league_page", "market_completeness", "grid",
            "chart_timing", "visual_review",
        ]
        from datetime import datetime
        _day_idx = datetime.now().timetuple().tm_yday % len(_ROTATION)
        rotating = _ROTATION[_day_idx]
        module_names = ["feed", "event_detail", rotating]
        print(f"Light sweep: feed + event_detail + {rotating} (day-of-year rotation)")
    else:
        module_names = sorted(MODULES.keys(), key=lambda k: MODULES[k]["priority"])

    run_suite(module_names)


if __name__ == "__main__":
    main()
