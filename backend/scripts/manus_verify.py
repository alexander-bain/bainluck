#!/usr/bin/env python3
"""Manus verify: launch a single targeted Manus task to verify a shipped fix.

Usage:
    python3 scripts/manus_verify.py --brief "On bainluck.com, click 10 See more buttons..."
    python3 scripts/manus_verify.py --brief "..." --timeout 300
    python3 scripts/manus_verify.py --poll <task_id>   # re-poll an existing task

The poller speaks the Manus v2 API the same way the health suite does:
`task.detail` returns ``{"task": {"status": ..., "credit_usage": ...}}`` where the
terminal status is ``"stopped"`` (NOT "complete"/"done") and the human-readable
verdict lives in the ``assistant_message`` content returned by ``task.listMessages``.
The previous implementation read a non-existent top-level ``status``/``result``
field, so it never detected completion and always timed out.
"""

import argparse
import json
import os
import sys
import time

import httpx

API_KEY = os.getenv("MANUS_API_KEY", "")
BASE_URL = "https://api.manus.ai/v2"


def _headers() -> dict:
    return {"x-manus-api-key": API_KEY, "Content-Type": "application/json"}


def create_task(brief: str) -> dict:
    """Create a Manus task. Returns {'task_id': ...} or {'error': ...}."""
    if not API_KEY:
        return {"error": "MANUS_API_KEY not set"}
    try:
        resp = httpx.post(
            f"{BASE_URL}/task.create",
            headers=_headers(),
            json={
                "message": {"content": brief},
                "title": f"BainLuck Verify: {brief[:60]}",
                "hide_in_task_list": True,
                "agent_profile": "manus-1.6-max",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("task_id") or data.get("id")
        if not task_id:
            return {"error": f"No task_id in response: {data}"}
        return {"task_id": task_id}
    except Exception as e:  # noqa: BLE001 - surface any launch failure to the caller
        return {"error": str(e)[:200]}


def get_task_status(task_id: str) -> dict | None:
    """Quick status check via task.detail. Returns the inner ``task`` dict."""
    try:
        resp = httpx.get(
            f"{BASE_URL}/task.detail",
            params={"task_id": task_id},
            headers=_headers(),
            timeout=15,
        )
        return resp.json().get("task", {})
    except Exception:  # noqa: BLE001
        return None


def collect_messages(task_id: str) -> dict:
    """Fetch the full message history for a task. Raises on transport failure."""
    resp = httpx.get(
        f"{BASE_URL}/task.listMessages",
        params={"task_id": task_id, "order": "asc", "limit": 100},
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def extract_verdict(messages: dict) -> str:
    """Pull the assistant verdict text (and attachment links) from messages."""
    parts: list[str] = []
    for msg in messages.get("messages", []):
        if msg.get("type") != "assistant_message":
            continue
        am = msg.get("assistant_message", {})
        content = am.get("content", "")
        if content:
            parts.append(content)
        for att in am.get("attachments", []):
            parts.append(f"\n📎 {att.get('file_name')} — {att.get('url')}")
    return "\n\n".join(parts).strip()


def poll_task(
    task_id: str,
    timeout_seconds: int = 600,
    interval: int = 15,
    sleep=time.sleep,
) -> dict:
    """Poll a Manus task until it stops, errors, or times out.

    Returns a dict with ``status`` in {"complete", "error", "timeout"}.
    On completion the verdict text is under ``verdict``.
    """
    url = f"https://manus.im/app/{task_id}"
    max_polls = max(1, timeout_seconds // interval)
    last_credits = 0
    for i in range(max_polls):
        task = get_task_status(task_id)
        if task:
            status = task.get("status", "running")
            last_credits = task.get("credit_usage", last_credits)

            if status == "stopped":
                try:
                    messages = collect_messages(task_id)
                    verdict = extract_verdict(messages)
                except Exception as e:  # noqa: BLE001
                    return {
                        "status": "complete",
                        "task_id": task_id,
                        "url": url,
                        "verdict": "",
                        "credits": last_credits,
                        "detail": f"collection failed: {str(e)[:120]}",
                    }
                return {
                    "status": "complete",
                    "task_id": task_id,
                    "url": url,
                    "verdict": verdict,
                    "credits": last_credits,
                }
            if status == "error":
                return {
                    "status": "error",
                    "task_id": task_id,
                    "url": url,
                    "detail": "task reported error",
                    "credits": last_credits,
                }
            print(f"  [{(i + 1) * interval}s] {status} ({last_credits} credits)")
        else:
            print(f"  [{(i + 1) * interval}s] status check returned None — retrying")

        sleep(interval)

    return {
        "status": "timeout",
        "task_id": task_id,
        "url": url,
        "detail": f"Timed out after {timeout_seconds}s",
        "credits": last_credits,
    }


def launch_task(brief: str, timeout_seconds: int = 600) -> dict:
    """Create a task and poll it to completion."""
    created = create_task(brief)
    if "error" in created:
        return {"status": "error", "detail": created["error"]}
    task_id = created["task_id"]
    print(f"Launched Manus task: {task_id}")
    print(f"URL: https://manus.im/app/{task_id}")
    return poll_task(task_id, timeout_seconds=timeout_seconds)


def _print_result(result: dict) -> None:
    status = result["status"]
    icon = "✅" if status == "complete" else "❌" if status == "error" else "⏱️"
    print(f"\n{icon} VERIFY: {status}")
    if result.get("url"):
        print(f"   Task: {result['url']}")
    if result.get("credits"):
        print(f"   Credits: {result['credits']}")
    if result.get("detail"):
        print(f"   Detail: {result['detail']}")
    if result.get("verdict"):
        print(f"\n   Verdict:\n{result['verdict']}")


def main():
    parser = argparse.ArgumentParser(description="Run a targeted Manus verification task")
    parser.add_argument("--brief", help="The verification brief to send to Manus")
    parser.add_argument("--poll", help="Re-poll an existing task_id instead of launching")
    parser.add_argument("--timeout", type=int, default=600, help="Polling timeout in seconds")
    parser.add_argument("--json-output", action="store_true", help="Print result as JSON")
    args = parser.parse_args()

    if not API_KEY:
        print("Set MANUS_API_KEY environment variable")
        sys.exit(1)

    if args.poll:
        result = poll_task(args.poll, timeout_seconds=args.timeout)
    elif args.brief:
        result = launch_task(args.brief, args.timeout)
    else:
        parser.error("provide --brief to launch or --poll TASK_ID to re-poll")

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        _print_result(result)


if __name__ == "__main__":
    main()
