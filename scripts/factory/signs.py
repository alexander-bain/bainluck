"""Records for the injury sign and the engineer's clipboard."""

import re

from model import instant
from signals import BYLINE, TRUSTED, on_floor


def switched_off(comments, since):
    found = []
    for comment in comments:
        if comment.get("author_association") not in TRUSTED:
            continue
        if instant(comment["created_at"]) < instant(since):
            continue
        for raw in comment.get("body", "").splitlines():
            line = raw.strip()
            byline = BYLINE.match(line)
            if byline and byline[1]:
                line = line[byline.end() :]
            if re.match(r"^switched off\b", line.lstrip("* "), re.I):
                found.append(
                    {
                        "kind": "switched-off",
                        "number": comment["id"],
                        "at": comment["created_at"],
                    }
                )
                break
    return found


def wrong_numbers(report_page, since):
    if not report_page or report_page["pageInfo"]["hasNextPage"]:
        return None
    issues = report_page["nodes"]
    if report_page["issueCount"] != len(issues) or not all(issues):
        return None
    return [
        {"kind": "wrong-number", "number": issue["number"], "at": issue["createdAt"]}
        for issue in issues
        if issue.get("title", "").startswith("Wrong number")
        and instant(issue["createdAt"]) >= instant(since)
    ]


def add_signs(floor, snapshot, previous):
    if source := snapshot.get("injury_source"):
        prior = previous.get("injury_clock") or {}
        reports = source["wrong_numbers"]
        events = {
            (event["kind"], event["number"]): event
            for event in [
                *prior.get("events", []),
                *source["switches"],
                *(reports or []),
            ]
            if instant(event["at"]) <= instant(floor["generated_at"])
        }
        floor["injury_clock"] = {
            "from": source["from"],
            "available": reports is not None,
            "events": sorted(
                events.values(),
                key=lambda event: (
                    instant(event["at"]),
                    event["kind"],
                    event["number"],
                ),
            ),
        }
    prior_changes = {(c["number"], c["line"]): c for c in previous.get("changes", [])}
    for change in floor["changes"]:
        old = prior_changes.get((change["number"], change["line"]), {})
        first = old.get("bench_seen_at")
        if not first and old.get("station") == "Write" and on_floor(old):
            first = previous["generated_at"]
        if not first and change["station"] == "Write" and on_floor(change):
            first = floor["generated_at"]
        if first:
            change["bench_seen_at"] = first
