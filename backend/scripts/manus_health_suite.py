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


def poll_task(task_id: str, timeout_seconds: int = 900) -> dict | None:
    """Poll a Manus task until completion. Returns final messages."""
    max_polls = timeout_seconds // 15
    for i in range(max_polls):
        try:
            task = get_task_status(task_id)
            if task:
                status = task.get("status", "running")
                credits = task.get("credit_usage", 0)

                if status == "stopped":
                    full = httpx.get(
                        f"{BASE}/task.listMessages",
                        params={"task_id": task_id, "order": "asc", "limit": 100},
                        headers={"x-manus-api-key": API_KEY},
                        timeout=30,
                    ).json()
                    full["_credit_usage"] = credits
                    return full
                elif status == "error":
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
                            print(f"    Auto-confirming {evt_type}...")
                            httpx.post(
                                f"{BASE}/task.confirmAction",
                                json={"task_id": task_id, "event_id": evt_id, "input": {"accept": True}},
                                headers={"x-manus-api-key": API_KEY},
                                timeout=15,
                            )
                            break
                    else:
                        print(f"    [{i+1}/{max_polls}] waiting (may need manual input)")
                else:
                    print(f"    [{i+1}/{max_polls}] running... ({credits} credits)")
            else:
                print(f"    [{i+1}/{max_polls}] polling...")

        except Exception as e:
            print(f"    Poll error: {e}")

        time.sleep(15)

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

    # Phase 2: Poll all tasks
    print(f"\nPhase 2: Polling {len(tasks)} tasks (15min timeout each)...")
    results = {}
    for name, task_id in tasks.items():
        print(f"\n  Waiting for {name} ({task_id})...")
        result = poll_task(task_id)
        credits = result.get("_credit_usage", 0) if result else 0
        if result is None:
            print(f"  TIMEOUT: {name}")
            manifest["tasks"][name]["status"] = "timeout"
        elif result.get("error"):
            print(f"  ERROR: {name}")
            manifest["tasks"][name]["status"] = "error"
        else:
            print(f"  COMPLETE: {name} ({credits} credits)")
            manifest["tasks"][name]["status"] = "complete"
            report = extract_report(result)
            results[name] = report

            report_path = output_dir / f"{name}.md"
            report_path.write_text(report)
            print(f"    Report: {report_path}")
        manifest["tasks"][name]["credits"] = credits

    # Phase 3: Generate combined report
    print("\nPhase 3: Generating combined report...")
    combined = [f"# Manus Health Audit — {date_str}\n"]
    combined.append(f"**Modules run:** {len(tasks)}")
    combined.append(f"**Completed:** {sum(1 for t in manifest['tasks'].values() if t['status'] == 'complete')}")
    combined.append(f"**Failed/Timeout:** {sum(1 for t in manifest['tasks'].values() if t['status'] != 'complete')}")
    combined.append("")

    for name in module_names:
        if name in results:
            combined.append(f"---\n\n## {MODULES[name]['name']}\n")
            combined.append(results[name])
            combined.append("")

    combined_path = output_dir / "combined_report.md"
    combined_path.write_text("\n".join(combined))

    # Update manifest
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
        icon = {"running": "...", "complete": "OK", "error": "ERR", "timeout": "T/O"}.get(status, "?")
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

    if args.smoke:
        module_names = ["event_detail", "feed"]
    elif args.modules:
        module_names = args.modules
    else:
        module_names = sorted(MODULES.keys(), key=lambda k: MODULES[k]["priority"])

    run_suite(module_names)


if __name__ == "__main__":
    main()
