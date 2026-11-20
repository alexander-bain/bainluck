"""Project the work already read by the collector into public floor events."""

from collections import defaultdict
from datetime import timedelta
from hashlib import sha256

from model import bot_review, fable_decision, instant, last_authored, latest_checks
from signals import on_floor

WINDOW = timedelta(minutes=5)


def authored(pull):
    return [c for c in pull.get("commits", []) if not c.get("merge_from_master")]


def approvals(pull):
    bot = bot_review(pull)
    cleared = {}
    if (
        pull.get("reviews_complete")
        and bot.get("state") == "APPROVED"
        and bot.get("submitted_at")
    ):
        cleared["bot"] = bot["submitted_at"]
    if pull.get("comments_complete") and pull.get("commits_complete"):
        look = fable_decision(pull)
        revised = last_authored(pull)
        if (
            look.get("fable_accept")
            and not look.get("fable_changes")
            and revised
            and instant(look["created_at"]) >= instant(revised["at"])
        ):
            cleared["fable"] = look["created_at"]
    return cleared


def check_identity(check):
    return (check.get("app"), check["name"], check.get("finished_at"))


def add_events(floor, snapshot, previous, cache):
    observed = floor["generated_at"]
    now = instant(observed)
    since = previous.get("generated_at")
    events = {
        e["id"]: e
        for e in previous.get("events", [])
        if timedelta(0) <= now - instant(e["observed_at"]) < WINDOW
    }
    changes = {(c["number"], c["line"]): c for c in floor["changes"]}
    pulls = {p["number"]: p for p in snapshot.get("pulls", [])}
    old_changes = {(c["number"], c["line"]): c for c in previous.get("changes", [])}
    visible = defaultdict(list)
    for change in floor["changes"]:
        if on_floor(change) or change["station"] == "Live":
            visible[change["number"]].append(change)

    def record(kind, change, station, at, *evidence, **detail):
        if not since or not at or instant(at) > now:
            return
        key = (kind, change["number"], change["line"], at, *evidence)
        event_id = sha256(repr(key).encode()).hexdigest()[:20]
        events.setdefault(
            event_id,
            {
                "id": event_id,
                "kind": kind,
                "number": change["number"],
                "line": change["line"],
                "builder": change["builder"],
                "station": station,
                "at": at,
                "observed_at": observed,
                **detail,
            },
        )

    for number, rows in visible.items():
        pull = pulls[number]
        if pull.get("merged_at"):
            continue
        change = rows[0]
        prior = cache.get(str(number), {})
        just_opened = since and pull.get("created_at", "") >= since and not prior
        if pull.get("commits_complete") and (
            prior.get("commits_complete") or just_opened
        ):
            seen = {c["sha"] for c in prior.get("commits", []) if c.get("sha")}
            for commit in authored(pull):
                if commit.get("sha") and commit["sha"] not in seen:
                    # A new member of the observed commit list proves a push.
                    # Keep GitHub's commit time and the observation separately.
                    record("commit", change, "Write", commit["at"], commit["sha"])

        checked = list(latest_checks(pull)) if pull.get("checks_complete") else []
        finished = [c for c in checked if c["state"] == "completed"]
        cleared = approvals(pull)
        for row in rows:
            if checked:
                row["check_progress"] = {"done": len(finished), "total": len(checked)}
            if cleared:
                row["approvals"] = cleared

        ordered = sorted(
            (c for c in finished if c.get("finished_at")),
            key=lambda c: c["finished_at"],
        )
        old_checks = {check_identity(c) for c in prior.get("checks", [])}
        for done, check in enumerate(ordered, start=1):
            at = check["finished_at"]
            conclusion = check.get("conclusion")
            if check_identity(check) not in old_checks and (
                prior.get("checks_complete") or just_opened or since and at >= since
            ):
                record(
                    "check",
                    change,
                    "Test",
                    at,
                    check_identity(check),
                    done=done,
                    total=len(checked),
                    outcome={
                        "success": "passed",
                        "failure": "failed",
                        "timed_out": "failed",
                    }.get(conclusion, "finished"),
                )

        old = old_changes.get((number, change["line"]), {})
        old_approvals = approvals(prior)
        for reviewer, at in cleared.items():
            if at != old.get("approvals", {}).get(reviewer) and (
                prior and at != old_approvals.get(reviewer) or since and at >= since
            ):
                record(reviewer, change, "Review", at)

    merged_here = set()
    for key, change in changes.items():
        merged = change.get("merged_at")
        if not merged or not since:
            continue
        old = old_changes.get(key, {})
        if not old.get("merged_at") and (old or merged >= since):
            lift = {"from": "Merge line"} if old.get("station") == "Merge line" else {}
            record("merge", change, "Ship", merged, **lift)
            merged_here.add(key)
        started = old.get("deploy_started_at")
        if not started and old.get("station") != "Live":
            merge_sha = pulls.get(change["number"], {}).get("merge_commit_sha")
            candidates = [
                s["at"]
                for s in snapshot.get("deploy_starts", [])
                if s["line"] == change["line"]
                and merged <= s["at"] <= observed
                and (not change["live_at"] or s["at"] <= change["live_at"])
                and merge_sha in s["contains"]
            ]
            if candidates:
                started = min(candidates)
                if old or started >= since:
                    record("deploy", change, "Ship", started)
        if started:
            change["deploy_started_at"] = started
        live = change.get("live_at")
        if live and not old.get("live_at") and (old or live >= since):
            record("live", change, "Live", live)

    for transfer in floor.get("transitions", []):
        key = (transfer["number"], transfer["line"])
        change = changes.get(key)
        if (
            not change
            or not on_floor(change)
            or transfer.get("observed_at") != observed
            or transfer["to"] == "Ship"
            and key in merged_here
        ):
            continue
        kind = (
            "returned"
            if transfer["to"] == "Write" and change.get("sent_back")
            else "move"
        )
        at = (
            fable_decision(pulls[change["number"]]).get("created_at")
            if kind == "returned"
            else transfer["at"]
        )
        record(
            kind,
            change,
            transfer["to"],
            at,
            transfer["from"],
            **{"from": transfer["from"]},
        )
    floor["events"] = sorted(
        events.values(), key=lambda e: (instant(e["at"]), instant(e["observed_at"]))
    )
