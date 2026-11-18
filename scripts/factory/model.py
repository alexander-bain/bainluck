"""Pure, conservative rules for The Factory. All clocks are supplied by the caller."""

from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

LINES = ("Server", "Website", "Apps")
STATIONS = ("Write", "Test", "Review", "Merge line", "Ship", "Live")
BUILDERS = {
    "speed/": "S",
    "codex/": "B",
    "ios/": "C",
    "atlas/": "D",
    "builder-e/": "E",
    "apple/": "F",
}
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
PACIFIC = ZoneInfo("America/Los_Angeles")


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def public_title(title):
    # Titles are the only free text that leaves the collector. Never publish
    # discussion bodies, author identities, URLs from comments, or email addresses.
    title = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", title)
    title = re.sub(r"(?<!\w)@[\w-]+(?:\[bot\])?", "[account removed]", title)
    title = re.sub(r"\bAlex(?:ander)?(?: Bain)?\b", "the founder", title, flags=re.I)
    return title


def line_for(pull):
    files = pull.get("files", [])
    if not pull.get("files_complete") or not files:
        return "Server", True
    if all(path.startswith("ios/") for path in files):
        return "Apps", False
    if all(path.startswith("frontend/") for path in files):
        return "Website", False
    return "Server", False


def checks_green(pull):
    if not pull.get("checks_complete") or not pull.get("checks"):
        return False, True
    # Last attempt wins, including a re-run which is still in progress.
    latest = {}
    for check in sorted(pull["checks"], key=lambda c: c.get("started_at") or ""):
        latest[(check.get("app"), check["name"])] = check
    green = all(
        check["state"] == "completed"
        and check.get("conclusion") in {"success", "neutral", "skipped"}
        for check in latest.values()
    )
    return green, False


def classify(pull, deployments, now):
    line, uncertain_line = line_for(pull)
    reasons = ["Changed files could not be confirmed."] if uncertain_line else []
    builder = next(
        (value for key, value in BUILDERS.items() if pull["branch"].startswith(key)),
        "Other",
    )
    activity = [pull["updated_at"]]
    activity += [
        review["submitted_at"]
        for review in pull.get("reviews", [])
        if review.get("submitted_at")
    ]
    activity += [
        comment["updated_at"]
        for comment in pull.get("comments", [])
        if comment.get("updated_at")
    ]
    activity += [
        check["finished_at"]
        for check in pull.get("checks", [])
        if check.get("finished_at")
    ]
    last_activity = max(activity, key=instant)
    change = {
        "number": pull["number"],
        "title": public_title(pull["title"]),
        "builder": builder,
        "line": line,
        "station": "Write",
        "unsure": uncertain_line,
        "reasons": reasons,
        "side_track": pull["state"] == "open"
        and now - instant(last_activity) >= timedelta(days=3),
        "last_activity": last_activity,
        "merged_at": pull.get("merged_at"),
        "live_at": None,
        "timing": None,
    }
    if pull.get("merged_at"):
        receipts = [
            d
            for d in deployments
            if d["line"] == line
            and pull["merge_commit_sha"] in d["contains"]
            and instant(d["at"]) >= instant(pull["merged_at"])
        ]
        change["station"] = "Ship"
        if receipts and not uncertain_line:
            receipt = min(receipts, key=lambda d: instant(d["at"]))
            change.update(station="Live", live_at=receipt["at"], timing=receipt["kind"])
        else:
            change["unsure"] = True
            change["reasons"].append("Waiting for deployment evidence on this line.")
        return change
    if pull.get("draft"):
        return change
    change["station"] = "Test"
    green, unknown = checks_green(pull)
    if not green:
        change["unsure"] |= unknown
        if unknown:
            change["reasons"].append("Checks on this version could not be confirmed.")
        return change
    change["station"] = "Review"
    if not pull.get("reviews_complete") or not pull.get("commits_complete"):
        change["unsure"] = True
        change["reasons"].append("Review evidence could not be confirmed.")
        return change
    bot_reviews = [
        r
        for r in pull.get("reviews", [])
        if r.get("login") == "claude[bot]" and r.get("commit_id") == pull["head_sha"]
    ]
    latest_review = max(
        bot_reviews, key=lambda r: r.get("submitted_at") or "", default={}
    )
    if latest_review.get("state") != "APPROVED":
        return change
    if pull.get("fable_needed"):
        non_merge = [c for c in pull.get("commits", []) if c["parents"] == 1]
        if not pull.get("comments_complete") or not non_merge:
            change["unsure"] = True
            change["reasons"].append("The final review could not be confirmed.")
            return change
        # The API returns commits in topological order. Merge-only syncs do not
        # invalidate an acceptance of the last authored (non-merge) change.
        last_commit = non_merge[-1]["at"]
        accepted = any(
            c.get("fable_accept")
            and c.get("association") in TRUSTED
            and instant(c["created_at"]) >= instant(last_commit)
            for c in pull.get("comments", [])
        )
        if not accepted:
            return change
    if not uncertain_line:
        change["station"] = "Merge line"
    return change


def advance_jams(changes, master, previous, now):
    conditions = {}
    previous_keys = {j["key"] for j in previous if j.get("ended_at") is None}
    active = [c for c in changes if c["station"] != "Live" and not c["side_track"]]
    for station in STATIONS[:-1]:
        count = sum(c["station"] == station for c in active)
        if count >= 10:
            conditions[f"crowd:{station}"] = ("crowd", station, None, 1800, count)
    if master.get("tests") == "failing" or (
        "master" in previous_keys and master.get("tests") != "passing"
    ):
        conditions["master"] = ("master", "Test", "Server", 0, None)
    if master.get("testflight") in {"failure", "cancelled", "timed_out", "error"} or (
        "testflight" in previous_keys and master.get("testflight") != "success"
    ):
        conditions["testflight"] = ("testflight", "Ship", "Apps", 0, None)
    for line in LINES:
        waiting = any(
            c["line"] == line and c["station"] in STATIONS[:3] for c in active
        )
        ready = any(c["line"] == line and c["station"] == "Merge line" for c in active)
        if waiting and not ready:
            conditions[f"empty:{line}"] = ("empty", "Merge line", line, 900, None)
    old = {j["key"]: j for j in previous if j.get("ended_at") is None}
    jams = [j.copy() for j in previous if j.get("ended_at") is not None]
    for key, (kind, station, line, threshold, count) in conditions.items():
        jam = old.pop(key, None) or {
            "key": key,
            "kind": kind,
            "station": station,
            "line": line,
            "started_at": iso(now),
            "qualifies_at": iso(now + timedelta(seconds=threshold)),
            "ended_at": None,
        }
        jam["count"] = count
        jams.append(jam)
    for jam in old.values():
        if now >= instant(jam["qualifies_at"]):
            jams.append({**jam, "ended_at": iso(now)})
    midnight = now.astimezone(PACIFIC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return [
        j
        for j in jams
        if j["ended_at"] is None
        or instant(j["ended_at"]) >= midnight - timedelta(days=7)
    ]


def build(snapshot, previous=None):
    previous = previous or {}
    now = instant(snapshot["captured_at"])
    changes = [
        classify(p, snapshot["deployments"], now)
        for p in snapshot["pulls"]
        if p["state"] == "open" or p.get("merged_at")
    ]
    # Keep the first observed receipt across updates. Refreshes do not increase
    # merge-to-live time. A source whose evidence disappears stays in Ship.
    old_changes = {c["number"]: c for c in previous.get("changes", [])}
    for change in changes:
        old = old_changes.get(change["number"], {})
        if change["station"] == "Live" and old.get("live_at"):
            change["live_at"] = min(old["live_at"], change["live_at"], key=instant)
            if old["live_at"] == change["live_at"]:
                change["timing"] = old["timing"]
    return {
        "schema_version": 1,
        "generated_at": snapshot["captured_at"],
        "observed_since": previous.get("observed_since", snapshot["captured_at"]),
        "changes": changes,
        "jams": advance_jams(
            changes, snapshot["master"], previous.get("jams", []), now
        ),
        "signals": snapshot["master"],
        "coverage": snapshot.get("coverage", []),
    }
