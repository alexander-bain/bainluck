#!/usr/bin/env python3
"""Poll a Manus task for completion and download results.

Usage:
    MANUS_API_KEY=... python3 scripts/manus_poll.py TASK_ID

    # Or use the last created task:
    MANUS_API_KEY=... python3 scripts/manus_poll.py mHDPR637zfZiCanujUchov
"""

import json
import os
import sys
import time

import httpx

API_KEY = os.getenv("MANUS_API_KEY", "")
BASE = "https://api.manus.ai/v2"


def poll_task(task_id: str, interval: int = 15, max_polls: int = 40):
    """Poll a Manus task until completion."""
    print(f"Polling task {task_id}...")
    print(f"View in browser: https://manus.im/app/{task_id}")
    print()

    for i in range(max_polls):
        resp = httpx.get(
            f"{BASE}/task.listMessages",
            params={"task_id": task_id, "order": "desc", "limit": 5},
            headers={"x-manus-api-key": API_KEY},
            timeout=30,
        )
        data = resp.json()
        messages = data.get("messages", [])

        for msg in messages:
            if msg.get("type") == "status_update":
                status = msg.get("status_update", {}).get("agent_status", "?")
                if status == "stopped":
                    print(f"\n✅ TASK COMPLETE")
                    # Get the full message history
                    full = httpx.get(
                        f"{BASE}/task.listMessages",
                        params={"task_id": task_id, "order": "asc", "limit": 100},
                        headers={"x-manus-api-key": API_KEY},
                        timeout=30,
                    ).json()
                    for m in full.get("messages", []):
                        if m.get("type") == "assistant_message":
                            am = m.get("assistant_message", {})
                            print(f"\n{am.get('content', '')}")
                            for a in am.get("attachments", []):
                                print(f"\n📎 {a.get('file_name')} → {a.get('url')}")
                    return True
                elif status == "error":
                    print(f"\n❌ TASK FAILED")
                    for m in messages:
                        if m.get("type") == "assistant_message":
                            print(m.get("assistant_message", {}).get("content", ""))
                    return False

        # Show latest message
        for msg in messages:
            if msg.get("type") == "assistant_message":
                content = msg.get("assistant_message", {}).get("content", "")[:100]
                print(f"  [{i+1}/{max_polls}] {content}")
                break
        else:
            print(f"  [{i+1}/{max_polls}] waiting...")

        time.sleep(interval)

    print(f"\n⏰ Timed out after {max_polls * interval}s. Task may still be running.")
    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/manus_poll.py TASK_ID")
        sys.exit(1)
    if not API_KEY:
        print("Set MANUS_API_KEY environment variable")
        sys.exit(1)
    poll_task(sys.argv[1])
