"""Pure, conservative rules for The Factory. All clocks are supplied by the caller."""

from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo
from signals import resolve_holds, stopped_rules

LINES = ("Server", "Website", "Apps")
STATIONS = ("Write", "Test", "Review", "Merge line", "Ship", "Live")
BUILDERS = {
    "speed/": "S",
    "codex/": "B",
    "ios/": "C",
    "atlas/": "D",
    "builder-e/": "E",
    "apple/": "F",
    "weebey/": "W",
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


def latest_checks(pull):
    # Last attempt wins, including a re-run which is still in progress.
    latest = {}
    for check in sorted(
        pull.get("checks", []), key=lambda c: c.get("started_at") or ""
    ):
        latest[(check.get("app"), check["name"])] = check
    return latest.values()


def checks_green(pull):
    if not pull.get("checks_complete") or not pull.get("checks"):
        return False, True
    green = all(
        check["state"] == "completed"
        and check.get("conclusion") in {"success", "neutral", "skipped"}
        for check in latest_checks(pull)
    )
    return green, False


def review_ready_at(pull):
    # Called once the current head has passed its checks. A draft may finish
    # checks before being marked ready, or a branch may pass before it is opened.
    completions = [
        check.get("finished_at")
        or (check.get("started_at") if check.get("app") == "commit-status" else None)
        for check in latest_checks(pull)
    ]
    if not completions or not all(completions):
        return None
    intake = pull.get("review_resumed_at") or pull.get("created_at")
    return max(completions + ([intake] if intake else []), key=instant)


def unchanged_after(pull, commit_id):
    if commit_id == pull["head_sha"]:
        return True
    if not pull.get("commits_complete"):
        return False
    commits = pull.get("commits", [])
    index = next((i for i, c in enumerate(commits) if c.get("sha") == commit_id), None)
    return index is not None and all(
        c.get("merge_from_master") or c.get("test_only") for c in commits[index + 1 :]
    )


def classify(pull, deployments, now):
    line, uncertain_line = line_for(pull)
    reasons = ["Changed files could not be confirmed."] if uncertain_line else []
    builder = next(
        (value for key, value in BUILDERS.items() if pull["branch"].startswith(key)),
        "Other",
    )
    activity = [pull["updated_at"]]
    if pull.get("review_resumed_at"):
        activity.append(pull["review_resumed_at"])
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
    if pull["branch"].startswith("dependabot/"):
        change["bot_update"] = True
    fable = max(
        (
            c
            for c in pull.get("comments", [])
            if c.get("association") in TRUSTED
            and (c.get("fable_changes") or c.get("fable_accept"))
        ),
        key=lambda c: (instant(c["created_at"]), bool(c.get("fable_changes"))),
        default={},
    )
    if fable.get("fable_changes"):
        change["sent_back"] = True
        return change
    if pull.get("draft"):
        return change
    change["station"] = "Test"
    green, unknown = checks_green(pull)
    if not green:
        if pull.get("checks_complete") and any(
            c.get("ci") and c["state"] == "in_progress" for c in latest_checks(pull)
        ):
            change["checks_running"] = True
        change["unsure"] |= unknown
        if unknown:
            change["reasons"].append("Checks on this version could not be confirmed.")
        return change
    change["station"] = "Review"
    if not change.get("bot_update") and now - instant(last_activity) >= timedelta(
        hours=48
    ):
        change["parked"] = True
    if not pull.get("reviews_complete"):
        change["unsure"] = True
        change["reasons"].append("Review evidence could not be confirmed.")
        return change
    bot_reviews = [
        r
        for r in pull.get("reviews", [])
        if r.get("login") == "claude[bot]" and unchanged_after(pull, r.get("commit_id"))
    ]
    latest_review = max(
        bot_reviews, key=lambda r: r.get("submitted_at") or "", default={}
    )
    if latest_review.get("state") != "APPROVED":
        return change
    if pull.get("fable_needed") and not pull.get("fable_not_needed"):
        non_merge = [
            c
            for c in pull.get("commits", [])
            if not c.get("merge_from_master") and not c.get("test_only")
        ]
        if (
            not pull.get("commits_complete")
            or not pull.get("comments_complete")
            or not non_merge
        ):
            change["unsure"] = True
            change["reasons"].append("The final review could not be confirmed.")
            return change
        # The API returns commits in topological order. Merge-only syncs do not
        # invalidate an acceptance of the last authored (non-merge) change.
        last_commit = non_merge[-1]["at"]
        accepted = fable.get("fable_accept") and instant(
            fable["created_at"]
        ) >= instant(last_commit)
        if not accepted:
            return change
    if not uncertain_line:
        change["station"] = "Merge line"
    return change


def advance_jams(changes, master, previous, now, stops=(), holds=None):
    # Earlier review jams used the old wait rule and cannot be carried forward.
    previous = [
        jam
        for jam in previous
        if jam["key"] != f"review-waiting:{jam['line']}"
        and (jam["kind"] != "hold" or jam.get("source"))
    ]
    conditions = {}
    starts = {}
    origins = {}
    previous_keys = {j["key"] for j in previous if j.get("ended_at") is None}
    active = [
        c
        for c in changes
        if c["station"] != "Live"
        and not any(c.get(flag) for flag in ("side_track", "bot_update", "parked"))
    ]
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
    for stop in stops:
        kind = stop["kind"]
        prefix = "review-ready" if kind == "review-waiting" else kind
        key = "master" if kind == "master" else f"{prefix}:{stop['line']}"
        if kind == "hold":
            key += f":{stop['source']['id']}"
            origins[key] = stop["source"]
        threshold = {
            "line-stalled": 1800,
            "announced": 900,
            "review-waiting": 7200,
        }.get(stop["kind"], 0)
        conditions[key] = (
            stop["kind"],
            stop["station"],
            stop["line"],
            threshold,
            stop["count"],
        )
        starts[key] = instant(stop["since"])
    old = {j["key"]: j for j in previous if j.get("ended_at") is None}
    jams = [j.copy() for j in previous if j.get("ended_at") is not None]
    for key, (kind, station, line, threshold, count) in conditions.items():
        jam = old.pop(key, None) or {
            "key": key,
            "kind": kind,
            "station": station,
            "line": line,
            "started_at": iso(starts.get(key, now)),
            "qualifies_at": iso(starts.get(key, now) + timedelta(seconds=threshold)),
            "ended_at": None,
        }
        jam["count"] = count
        if key in origins:
            jam["source"] = origins[key]
        jams.append(jam)
    for jam in old.values():
        if now >= instant(jam["qualifies_at"]):
            hold = (holds or {}).get(jam["line"], {})
            ended = (
                hold.get("ended_at")
                if jam["kind"] == "hold" and hold.get("source") == jam.get("source")
                else None
            )
            jams.append({**jam, "ended_at": ended or iso(now)})
    midnight = now.astimezone(PACIFIC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return [
        j
        for j in jams
        if j["ended_at"] is None
        or instant(j["ended_at"]) >= midnight - timedelta(days=7)
    ]


def delivery_posts(commands, now):
    batches, live, build_post = {}, {}, None
    for post in sorted(commands, key=lambda c: instant(c["at"])):
        if instant(post["at"]) > now:
            continue
        line = post["line"]
        if post["kind"] == "merging":
            batches[line] = {number: post["at"] for number in post["numbers"]}
        elif post["kind"] == "hold" or (
            post["kind"] == "live" and not post.get("numbers")
        ):
            batches.pop(line, None)
        elif post["kind"] == "live":
            for number in post["numbers"]:
                live[(line, number)] = post
                batches.get(line, {}).pop(number, None)
        if post.get("build"):
            build_post = {"build": post["build"], "at": post["at"]}
    return batches, live, build_post


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
    commands = snapshot.get("commands", previous.get("signals", {}).get("commands", []))
    history = snapshot.get("hold_commands", commands)
    batches, live_posts, posted_build = delivery_posts(history, now)
    holds = resolve_holds(
        history,
        changes,
        snapshot["master"],
        now,
        previous.get("signals", {}).get("holds"),
    )
    pulls = {p["number"]: p for p in snapshot["pulls"]}
    transitions = [
        t
        for t in previous.get("transitions", [])
        if now - instant(t.get("observed_at", t["at"])) <= timedelta(minutes=15)
    ]
    for change in changes:
        old = old_changes.get(change["number"], {})
        pull = pulls[change["number"]]
        authored = [
            c["at"]
            for c in pull.get("commits", [])
            if not c.get("merge_from_master") and not c.get("test_only")
        ]
        revision = max(
            authored, default=pull.get("created_at", snapshot["captured_at"])
        )
        change["revision_at"] = revision
        arrivals = [revision]
        if change["station"] == "Merge line":
            arrivals += [
                c["finished_at"] for c in pull.get("checks", []) if c.get("finished_at")
            ]
            arrivals += [
                r["submitted_at"]
                for r in pull.get("reviews", [])
                if r.get("submitted_at")
                and r.get("state") == "APPROVED"
                and unchanged_after(pull, r.get("commit_id"))
            ]
            if pull.get("fable_needed") and not pull.get("fable_not_needed"):
                arrivals += [
                    c["created_at"]
                    for c in pull.get("comments", [])
                    if c.get("fable_accept")
                    and c.get("association") in TRUSTED
                    and c["created_at"] >= revision
                ]
        arrived = min(max(arrivals), snapshot["captured_at"])
        announced = batches.get(change["line"], {}).get(change["number"])
        hold = holds.get(change["line"])
        if (
            change["station"] == "Merge line"
            and announced
            and instant(announced) >= instant(revision)
            and not any(
                change.get(flag) for flag in ("parked", "bot_update", "side_track")
            )
            and not (hold and not hold["ended_at"])
        ):
            change.update(station="Ship", merge_announced_at=announced)
            arrived = announced
        same_station = (
            old.get("station") == change["station"]
            and old.get("line") == change["line"]
        )
        if change["station"] == "Review":
            ready_at = review_ready_at(pull)
            if ready_at:
                change["station_since"] = ready_at
            arrived = ready_at or snapshot["captured_at"]
        else:
            change["station_since"] = (
                old.get("station_since", arrived)
                if same_station and old.get("revision_at", revision) == revision
                else arrived
            )
        if old and not same_station:
            transitions.append(
                {
                    "number": change["number"],
                    "line": change["line"],
                    "from": old["station"],
                    "to": change["station"],
                    "at": change.get("live_at") or change.get("merged_at") or arrived,
                    "observed_at": snapshot["captured_at"],
                }
            )
        if change["merged_at"] and (
            change["station"] == "Live" or change["line"] == "Apps"
        ):
            post = live_posts.get((change["line"], change["number"]))
            if post and instant(post["at"]) >= instant(change["merged_at"]):
                if change["station"] == "Live":
                    change["live_posted_at"] = post["at"]
                if post.get("build"):
                    change["testflight_build"] = post["build"]
            if old.get("line") == change["line"]:
                if change["station"] == "Live" and old.get("live_posted_at"):
                    change.setdefault("live_posted_at", old["live_posted_at"])
                if old.get("testflight_build"):
                    change.setdefault("testflight_build", old["testflight_build"])
            if change.get("live_posted_at"):
                change["live_post_observed_at"] = (
                    old.get("live_post_observed_at", old["live_posted_at"])
                    if old.get("live_posted_at") == change["live_posted_at"]
                    else snapshot["captured_at"]
                )
        observed_since = previous.get("observed_since", snapshot["captured_at"])
        change["merge_to_live_seconds"] = None
        if (
            change["merged_at"]
            and change["live_at"]
            and instant(change["merged_at"]) >= instant(observed_since)
        ):
            change["merge_to_live_seconds"] = (
                instant(change["live_at"]) - instant(change["merged_at"])
            ).total_seconds()
    observed_since = previous.get("observed_since", snapshot["captured_at"])
    last_merges = dict(previous.get("signals", {}).get("last_merged_at", {}))
    for change in changes:
        if change["merged_at"]:
            line = change["line"]
            last_merges[line] = max(
                last_merges.get(line, change["merged_at"]), change["merged_at"]
            )
    stops = stopped_rules(
        changes, commands, snapshot["master"], last_merges, observed_since, now, holds
    )
    return {
        "schema_version": 1,
        "generated_at": snapshot["captured_at"],
        "observed_since": previous.get("observed_since", snapshot["captured_at"]),
        "read_expires_at": iso(now + timedelta(minutes=15)),
        "changes": changes,
        "transitions": transitions,
        "stops": stops,
        "jams": advance_jams(
            changes, snapshot["master"], previous.get("jams", []), now, stops, holds
        ),
        "signals": {
            **snapshot["master"],
            "last_merged_at": last_merges,
            "commands": commands,
            "holds": holds,
            **({"testflight_post": posted_build} if posted_build else {}),
        },
        "coverage": snapshot.get("coverage", []),
    }
