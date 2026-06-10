#!/usr/bin/env python3
"""Manus verify: launch a single targeted Manus task to verify a shipped fix.

Usage:
    python3 scripts/manus_verify.py --brief "On bainluck.com, click 10 See more buttons..."
    python3 scripts/manus_verify.py --brief "..." --timeout 300
"""

import argparse
import json
import os
import sys
import time

import httpx

API_KEY = os.getenv("MANUS_API_KEY", "")
BASE_URL = "https://api.manus.ai/v2"


def launch_task(brief: str, timeout_seconds: int = 600) -> dict:
    """Launch a Manus task, poll until complete, return result."""
    if not API_KEY:
        return {"status": "error", "detail": "MANUS_API_KEY not set"}

    headers = {"x-manus-api-key": API_KEY, "Content-Type": "application/json"}

    # Launch
    try:
        resp = httpx.post(
            f"{BASE_URL}/tasks",
            headers=headers,
            json={"prompt": brief},
            timeout=30,
        )
        resp.raise_for_status()
        task = resp.json()
        task_id = task.get("id") or task.get("task_id")
        if not task_id:
            return {"status": "error", "detail": f"No task_id in response: {task}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200]}

    print(f"Launched Manus task: {task_id}")
    print(f"URL: https://manus.im/app/{task_id}")

    # Poll
    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        time.sleep(15)
        try:
            status_resp = httpx.get(
                f"{BASE_URL}/tasks/{task_id}",
                headers=headers,
                timeout=15,
            )
            status_resp.raise_for_status()
            status = status_resp.json()
            state = status.get("status", "unknown")
            print(f"  [{int(time.monotonic() - start)}s] {state}")

            if state in ("complete", "completed", "done"):
                return {
                    "status": "pass",
                    "task_id": task_id,
                    "url": f"https://manus.im/app/{task_id}",
                    "result": status.get("result", status.get("output", "")),
                    "credits": status.get("credits", 0),
                }
            elif state in ("failed", "error", "cancelled"):
                return {
                    "status": "fail",
                    "task_id": task_id,
                    "url": f"https://manus.im/app/{task_id}",
                    "detail": status.get("error", state),
                }
        except Exception as e:
            print(f"  Poll error: {e}")

    return {
        "status": "timeout",
        "task_id": task_id,
        "url": f"https://manus.im/app/{task_id}",
        "detail": f"Timed out after {timeout_seconds}s",
    }


def main():
    parser = argparse.ArgumentParser(description="Run a targeted Manus verification task")
    parser.add_argument("--brief", required=True, help="The verification brief to send to Manus")
    parser.add_argument("--timeout", type=int, default=600, help="Polling timeout in seconds")
    parser.add_argument("--json-output", action="store_true", help="Print result as JSON")
    args = parser.parse_args()

    result = launch_task(args.brief, args.timeout)

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        status = result["status"]
        icon = "✅" if status == "pass" else "❌" if status == "fail" else "⏱️"
        print(f"\n{icon} VERIFY: {status}")
        if result.get("url"):
            print(f"   Task: {result['url']}")
        if result.get("detail"):
            print(f"   Detail: {result['detail']}")
        if result.get("result"):
            output = str(result["result"])[:500]
            print(f"   Result: {output}")


if __name__ == "__main__":
    main()
