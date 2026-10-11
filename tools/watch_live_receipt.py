"""Verify real Watch selection and post-relaunch refresh, without fixture fallback."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib
import re


def verify(log: str, exit_code: int, preferences: dict) -> dict:
    if exit_code != 0 or not re.search(
        r"^\*\* TEST SUCCEEDED \*\*\s*$", log, re.MULTILINE
    ):
        raise ValueError("Live test process did not finish successfully")
    totals = re.findall(
        r"^Test Suite '(?:Selected tests|All tests)' (passed|failed)[^\n]*\n"
        r"[ \t]*Executed (\d+) tests?, with (\d+) failures?[^\n]*",
        log,
        re.MULTILINE,
    )
    if len(totals) != 1 or totals[0] != ("passed", "1", "0"):
        raise ValueError(
            "Expected exactly one completed root summary with one test and zero failures"
        )
    count = 1
    if (
        len(
            re.findall(
                r"^Test Case '-\[BainLuckWatchUITests\.LiveSelectedGameJourneyTests "
                r"testProductionPickerSelectionSurvivesRelaunchAndRefreshes\]' passed",
                log,
                re.MULTILINE,
            )
        )
        != 1
    ):
        raise ValueError("Expected the production picker/relaunch test to pass")
    packets = re.findall(r"^WATCH_LIVE_EVIDENCE=(.+)$", log, re.MULTILINE)
    if len(packets) != 1:
        raise ValueError("Expected exactly one completed live evidence packet")
    e = json.loads(packets[0])
    if (
        e.get("schema_version") != 1
        or e.get("configuration") != "Release"
        or e.get("fixture") is not False
        or e.get("refreshed_after_relaunch") is not True
    ):
        raise ValueError("Release real-data refresh evidence missing")
    for key in ("picker_id", "canonical_id"):
        if type(e.get(key)) is not int or e[key] <= 0:
            raise ValueError(f"Invalid {key}")
    detail = e["production_detail"]
    if detail["id"] != e["canonical_id"]:
        raise ValueError("Production canonical identity differs")
    for key in ("home_team", "away_team"):
        if (
            not isinstance(e.get(key), str)
            or not e[key].strip()
            or e[key] != detail[key]
        ):
            raise ValueError("Production named sides differ")
    for phase in ("first", "reopened"):
        state = e[f"{phase}_state"]
        if (
            not isinstance(state, str)
            or not state.strip()
            or any(
                text in state.lower()
                for text in (
                    "saved reading",
                    "offline",
                    "couldn't",
                    "try again",
                    "timed out",
                    "temporarily busy",
                )
            )
        ):
            raise ValueError("Reading was not successfully refreshed")
        probability = e[f"{phase}_probability"]
        closed = "Closed · result unverified" in state
        final = state == "Final"
        if final or closed:
            if probability != f"No forecast: {state}":
                raise ValueError("Final or closed state retained a forecast")
        elif probability not in (
            "Win probability unavailable",
            e["home_team"] + " win chance unavailable",
        ):
            match = re.fullmatch(
                re.escape(e["home_team"]) + r" win probability, (\d+)%", probability
            )
            if not match or not 0 <= int(match[1]) <= 100:
                raise ValueError(
                    "Missing valid named probability or unavailable explanation"
                )
    selected = preferences["bainluck_watch_selected_event_id"]
    snapshot = json.loads(preferences["bainluck_watch_selected_game_snapshot_v1"])
    if type(selected) is not int or selected != e["canonical_id"]:
        raise ValueError("Persisted selection differs from canonical identity")
    if snapshot["version"] != 1 or snapshot["game"]["id"] != selected:
        raise ValueError("Persisted snapshot identity/version differs")
    for key in ("home_team", "away_team"):
        if snapshot["game"][key] != e[key]:
            raise ValueError("Persisted named sides differ")
    requested = datetime.fromisoformat(e["requested_at"].replace("Z", "+00:00"))
    relaunched = datetime.fromisoformat(e["relaunched_at"].replace("Z", "+00:00"))
    if requested.tzinfo is None or relaunched.tzinfo is None or requested > relaunched:
        raise ValueError("Invalid request/relaunch timestamps")
    # JSONEncoder's default Date encoding is seconds since 2001-01-01 UTC.
    fetched = snapshot["fetchedAt"]
    if type(fetched) not in (int, float):
        raise ValueError("Invalid persisted fetch time")
    fetched_unix = fetched + datetime(2001, 1, 1, tzinfo=timezone.utc).timestamp()
    if (
        not relaunched.timestamp()
        <= fetched_unix
        <= datetime.now(timezone.utc).timestamp() + 5
    ):
        raise ValueError("Persisted reading did not refresh after relaunch")
    return {"tests": count, "evidence": e, "snapshot_fetched_at": fetched_unix}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--log", required=True, type=Path)
    p.add_argument("--exit-code", required=True, type=int)
    p.add_argument("--sha", required=True)
    p.add_argument("--preferences", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    receipt = {"sha": a.sha, "verdict": "UNPAID", "exit_code": a.exit_code}
    try:
        verified = verify(
            a.log.read_text(), a.exit_code, plistlib.loads(a.preferences.read_bytes())
        )
        receipt.update(verified, verdict="PASS")
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        receipt["reason"] = str(error)
    a.output.write_text(json.dumps(receipt, indent=2) + "\n")
    if receipt["verdict"] != "PASS":
        raise SystemExit(f"Watch live journey UNPAID: {receipt['reason']}")
    print(
        f"Watch live journey PASS at {a.sha}: canonical event {verified['evidence']['canonical_id']}"
    )


if __name__ == "__main__":
    main()
