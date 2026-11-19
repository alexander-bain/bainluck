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


# A live line with no explicit slot uses the builder's standing merge lane.
LIVE_LINES = {
    "Speed": ("Server",),
    "Builder B": ("Server",),
    "Builder C": ("Apps",),
    "Atlas": ("Server", "Website"),
    "Builder E": ("Server",),
    "Apple": ("Apps",),
}
AUTHORS = (*LIVE_LINES, "Fable", "Alex", "Wee-Bey")
AUTHOR = "|".join(map(re.escape, AUTHORS))
BYLINE = re.compile(
    rf"^\**({AUTHOR})\**(?: \([^)]{{1,35}}\))?\s*:\s*|^\**(Fable|Alex)\b\**(?=[ ,—–])"
)
SIGNED = re.compile(rf"^[^—–]{{0,100}}[—–]\s*\**({AUTHOR})\b")
HOLD_OVER = re.compile(
    r"\bhold\b\s+(?:(?:is|was|has been)\s+)?(?:cleared|lifted|over)\b"
    r"|\b(?:clears?|cleared|clearing|lifts?|lifted|lifting)\b.{0,60}\bhold\b",
    re.I,
)
TEST_NAME = re.compile(r"\btest_[A-Za-z0-9_]{1,90}\b", re.ASCII)


def named_lines(text):
    return [line for line in LINES if re.search(rf"\b{line}\b", text, re.I)]


def commands_from(comments):
    commands = []
    for comment in comments:
        if comment.get("author_association") not in TRUSTED:
            continue
        for raw in comment.get("body", "").splitlines():
            line = raw.strip()
            byline = BYLINE.match(line)
            signed = SIGNED.match(line)
            author = (
                (byline[1] or byline[2]) if byline else (signed[1] if signed else None)
            )
            status = line[byline.end() :] if byline and byline[1] else line
            status = status.lstrip("* ")
            at = comment["created_at"]
            clearing = HOLD_OVER.search(line)
            slots = named_lines(line)

            if (
                re.match(r"^stuck\b", line.lstrip("* "), re.I)
                and re.search(r"\bHOLD\b", line)
                and not clearing
            ):
                # Prefer the slot named next to HOLD over incidental references.
                named = re.search(
                    r"\bHOLD\s*\(([^)]+)\)|\b(server|website|apps)\s+HOLD\b",
                    line,
                    re.I,
                )
                targets = (
                    named_lines(named[1] or named[2])
                    if named
                    else slots if len(slots) == 1 else []
                )
                origin = author or (
                    "Repository owner"
                    if comment.get("author_association") == "OWNER"
                    else None
                )
                identifier = comment.get("id")
                if origin and type(identifier) is int and identifier > 0:
                    for target in targets:
                        hold = {
                            "kind": "hold",
                            "line": target,
                            "at": at,
                            "source": {"id": identifier, "author": origin},
                        }
                        tests = TEST_NAME.findall(line)
                        if tests:
                            hold["test"] = tests[-1]
                        commands.append(hold)
                continue

            if clearing and author in {"Fable", "Alex"}:
                for target in slots or [None]:
                    commands.append({"kind": "resume", "line": target, "at": at})

            live = re.match(r"^live\b[\s:]*", status, re.I)
            if live:
                prefix, _, suffix = status[live.end() :].partition("(")
                delivery, _, _ = suffix.partition(")")
                explicit = re.fullmatch(
                    r"(?:server|website|apps)(?:\s*[+,/]\s*(?:server|website|apps))*",
                    delivery.strip(),
                    re.I,
                )
                targets = (
                    named_lines(delivery) if explicit else LIVE_LINES.get(author, ())
                )
                numbers = re.split(r"[\s,+]+", prefix.strip())
                ids = (
                    [int(n[1:]) for n in numbers]
                    if all(re.fullmatch(r"#[1-9][0-9]{0,9}", n) for n in numbers)
                    else []
                )
                for target in targets:
                    commands.append(
                        {"kind": "live", "line": target, "at": at, "numbers": ids}
                    )

            merging = re.search(r"\bmerging\b", line, re.I)
            if merging:
                numbers, separator, target = line[merging.end() :].partition("(")
                tokens = numbers.replace(",", " ").split()
                delivery = re.match(r"(server|website|apps)\)", target, re.I)
                if (
                    separator
                    and delivery
                    and tokens
                    and all(re.fullmatch(r"#[0-9]{1,10}", token) for token in tokens)
                ):
                    commands.append(
                        {
                            "kind": "merging",
                            "line": delivery[1].title(),
                            "numbers": [int(token[1:]) for token in tokens],
                            "at": at,
                        }
                    )
    return sorted(commands, key=lambda command: moment(command["at"]))


def resolve_holds(commands, changes, master, now, previous=None):
    """Keep the original NOW line and the earliest evidence that released it."""
    previous = previous or {}
    events = sorted([*commands, *previous.values()], key=lambda c: moment(c["at"]))
    holds = {}
    for event in events:
        at = moment(event["at"])
        if at > now:
            continue
        slot = event["line"]
        if event["kind"] == "resume" and slot is None:
            active = [
                h
                for h in holds.values()
                if moment(h["at"]) < at
                and (not h["ended_at"] or moment(h["ended_at"]) > at)
            ]
            if len(active) == 1:
                active[0]["ended_at"] = event["at"]
            continue
        if event["kind"] != "hold" or not event.get("source"):
            continue
        last = holds.get(slot)
        if last and (not last["ended_at"] or moment(last["ended_at"]) > at):
            continue  # Repeating the warning does not move the start time.

        releases = [
            c["at"]
            for c in events
            if c["kind"] in {"live", "resume"} and c["line"] == slot
        ]
        releases.extend(
            c["live_at"]
            for c in changes
            if c["line"] == slot
            and c["station"] == "Live"
            and c.get("merged_at")
            and c.get("live_at")
        )
        releases.extend(
            run["finished_at"]
            for run in master.get("successful_runs", [])
            if moment(run["started_at"]) > at
        )
        saved = previous.get(slot)
        if (
            saved
            and saved["source"] == event["source"]
            and saved["at"] == event["at"]
            and saved["ended_at"]
        ):
            releases.append(saved["ended_at"])
        holds[slot] = {
            **event,
            "ended_at": min(
                (value for value in releases if at < moment(value) <= now),
                default=None,
                key=moment,
            ),
        }
    return holds


def reader_behind(published_at, now):
    return now - moment(published_at) > timedelta(minutes=15)


def stopped_rules(
    changes, commands, master, last_merges, observed_since, now, holds=None
):
    if holds is None:
        holds = resolve_holds(commands, changes, master, now)
    commands = sorted(commands, key=lambda command: command["at"])
    stops = []
    merged = {c["number"]: c.get("merged_at") for c in changes}
    for line in LINES:
        waiting = [
            c
            for c in changes
            if c["line"] == line
            and c["station"] == "Merge line"
            and not c.get("bot_update")
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
                    "level": "amber",
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
                        "level": "amber",
                    }
                )
        hold = holds.get(line)
        if hold and not hold["ended_at"]:
            stops.append(
                {
                    "kind": "hold",
                    "line": line,
                    "station": "Merge line",
                    "since": hold["at"],
                    "count": len(waiting),
                    "level": "red",
                    "source": hold["source"],
                    **({"test": hold["test"]} if hold.get("test") else {}),
                }
            )
        reviewing = [
            c["station_since"]
            for c in changes
            if c["line"] == line
            and c["station"] == "Review"
            and not c.get("bot_update")
            and c.get("station_since")
            and timedelta(0) <= now - moment(c["last_activity"]) <= timedelta(hours=48)
            and now - moment(c["station_since"]) > timedelta(hours=2)
        ]
        if reviewing:
            stops.append(
                {
                    "kind": "review-waiting",
                    "line": line,
                    "station": "Review",
                    "since": min(reviewing, key=moment),
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
                "level": "amber",
            }
        )
    return stops
