"""Observed movement and stoppages. No discussion text leaves this module."""

import re
from datetime import datetime, timedelta

LINES = ("Server", "Website", "Apps")
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}


def moment(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_file(path):
    parts = path.split("/")
    return any(
        p in {"tests", "__tests__", "__snapshots__"} or p.endswith("Tests")
        for p in parts[:-1]
    ) or bool(re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", parts[-1]))


def commands_from(comments):
    commands = []
    for comment in comments:
        if comment.get("author_association") not in TRUSTED:
            continue
        for line in comment.get("body", "").splitlines():
            merging = re.search(
                r"\bmerging\s+(#[\d]+(?:\s*,?\s*#\d+)*)\s*\((server|website|apps)\)",
                line,
                re.I,
            )
            if merging:
                commands.append(
                    {
                        "kind": "merging",
                        "line": merging[2].title(),
                        "numbers": [int(n) for n in re.findall(r"#(\d+)", merging[1])],
                        "at": comment["created_at"],
                    }
                )
            for name in LINES:
                if re.search(r"\bHOLD\b", line) and re.search(
                    rf"\b{name}\b", line, re.I
                ):
                    commands.append(
                        {"kind": "hold", "line": name, "at": comment["created_at"]}
                    )
                live = re.search(
                    rf"\blive\s+#\d+\s*\({name}\)", line, re.I
                ) or re.search(rf"^\s*live\b[^\n]*\b{name}\b", line, re.I)
                if live:
                    commands.append(
                        {"kind": "live", "line": name, "at": comment["created_at"]}
                    )
    return sorted(commands, key=lambda command: command["at"])


def reader_behind(published_at, now):
    return now - moment(published_at) > timedelta(minutes=15)


def stopped_rules(changes, commands, master, last_merges, observed_since, now):
    commands = sorted(commands, key=lambda command: command["at"])
    stops = []
    merged = {c["number"]: c.get("merged_at") for c in changes}
    for line in LINES:
        waiting = [
            c for c in changes if c["line"] == line and c["station"] == "Merge line"
        ]
        since = last_merges.get(line) or observed_since
        if waiting and now - moment(since) >= timedelta(minutes=30):
            stops.append(
                {
                    "kind": "line-stalled",
                    "line": line,
                    "station": "Merge line",
                    "since": since,
                    "count": len(waiting),
                    "level": "red",
                }
            )
        announcements = [
            c
            for c in commands
            if c["line"] == line and c["kind"] == "merging" and moment(c["at"]) <= now
        ]
        if announcements:
            latest = announcements[-1]
            any_merged = latest.get("resolved", False) or any(
                merged.get(n) and moment(merged[n]) >= moment(latest["at"])
                for n in latest["numbers"]
            )
            if not any_merged and now - moment(latest["at"]) >= timedelta(minutes=15):
                stops.append(
                    {
                        "kind": "announced",
                        "line": line,
                        "station": "Merge line",
                        "since": latest["at"],
                        "count": len(latest["numbers"]),
                        "level": "red",
                    }
                )
        holds = [
            c
            for c in commands
            if c["line"] == line
            and c["kind"] in {"hold", "live"}
            and moment(c["at"]) <= now
        ]
        if holds and holds[-1]["kind"] == "hold":
            stops.append(
                {
                    "kind": "hold",
                    "line": line,
                    "station": "Merge line",
                    "since": holds[-1]["at"],
                    "count": len(waiting),
                    "level": "red",
                }
            )
        reviewing = [
            c for c in changes if c["line"] == line and c["station"] == "Review"
        ]
        if reviewing:
            oldest = min(c["station_since"] for c in reviewing)
            if now - moment(oldest) > timedelta(hours=2):
                stops.append(
                    {
                        "kind": "review-waiting",
                        "line": line,
                        "station": "Review",
                        "since": oldest,
                        "count": len(reviewing),
                        "level": "amber",
                    }
                )
    if master.get("tests") == "failing":
        stops.append(
            {
                "kind": "master",
                "line": None,
                "station": "Test",
                "since": master.get("tests_at") or observed_since,
                "count": sum(c["station"] == "Test" for c in changes),
                "level": "red",
            }
        )
    return stops
