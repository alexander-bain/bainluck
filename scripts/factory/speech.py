"""Build and check lane speech from structured observations of the floor."""

from datetime import timedelta
from hashlib import sha256
import json

from model import BUILDERS, PACIFIC, instant
from notes import LABELS, PLACES, chat_request_kwargs, model_request
from signals import on_floor

LANES = tuple(BUILDERS.values())
FRESH = timedelta(minutes=15)
MAX_CHARACTERS = 140
PROMPT = """Write a short speech bubble and choose a pose for each lane given.
For each lane, use one sentence verbatim from its own sentence groups, or combine
two sentences from different groups with a space. Choose playful phrasing when
it fits. Use at most 140 characters. Plain English for all ages. Use only that
lane's facts. Add no claims, numbers, change numbers, names or advice.
Choose a mood from that lane's moods.
Return a single JSON object keyed by the given lane codes, with a "text" string
and a "mood" string for each lane. If unsure, return null for that lane."""


def lane_facts(snapshot):
    now = instant(snapshot["generated_at"])
    day = now.astimezone(PACIFIC).date()
    changes = snapshot["changes"]
    facts = {}

    def recent(value):
        return value and timedelta(0) <= now - instant(value) <= FRESH

    def latest(rows, time):
        return max(rows, key=lambda c: (instant(c[time]), c["number"]), default=None)

    for lane in LANES:
        rows = [c for c in changes if c["builder"] == lane]
        active = [c for c in rows if on_floor(c)]
        numbers = {(c["number"], c["line"]) for c in rows}
        merged = latest(
            (c for c in rows if c.get("merged_at")
             and instant(c["merged_at"]) <= now
             and instant(c["merged_at"]).astimezone(PACIFIC).date() == day),
            "merged_at",
        )
        live = latest(
            (c for c in rows if c["station"] == "Live" and recent(c.get("live_at"))),
            "live_at",
        )
        testing = latest(
            (c for c in active if c["station"] == "Test" and c.get("last_activity")),
            "last_activity",
        )
        bench = latest(
            (c for c in active if c["station"] == "Write" and recent(c.get("last_activity"))),
            "last_activity",
        )
        waiting = min(
            (c for c in active if c["station"] in {"Review", "Merge line"}
             and c.get("station_since") and instant(c["station_since"]) <= now),
            key=lambda c: (instant(c["station_since"]), c["number"]),
            default=None,
        )
        held = next(
            (c for c in active if c["station"] == "Merge line"
             and any(stop["kind"] == "hold" and stop.get("source") and stop["line"] == c["line"]
                     for stop in snapshot.get("stops", []))),
            None,
        )
        carried = max(
            (t for t in snapshot.get("transitions", [])
             if (t["number"], t["line"]) in numbers and t["from"] != t["to"]
             and recent(t.get("observed_at") or t["at"])),
            key=lambda t: (instant(t.get("observed_at") or t["at"]), instant(t["at"]), t["number"]),
            default=None,
        )
        lane_read = {}
        if held:
            lane_read["held"] = held["number"]
        if live:
            lane_read["live"] = live["number"]
        if carried:
            lane_read["carried"] = {"number": carried["number"], "station": carried["to"]}
        if testing:
            checks = {"number": testing["number"], "running": bool(testing.get("checks_running"))}
            progress = testing.get("check_progress")
            if progress:
                checks.update(done=progress["done"], total=progress["total"])
            lane_read["checks"] = checks
        if waiting:
            lane_read["waiting"] = {
                "number": waiting["number"],
                "station": waiting["station"],
                "minutes": (now - instant(waiting["station_since"])) // timedelta(minutes=1),
            }
        if merged:
            lane_read["merged"] = {"number": merged["number"], "recent": bool(recent(merged["merged_at"]))}
        if bench:
            lane_read["bench"] = bench["number"]
        lane_read["recent_activity"] = any(recent(c.get("last_activity")) for c in rows)
        facts[lane] = lane_read
    return facts


def speech_options(facts):
    groups, moods = [], []
    if number := facts.get("held"):
        groups.append([f"#{number} is held at the loading dock.", f"The dock has #{number} on hold."])
        moods.append("stuck")
    if number := facts.get("live"):
        groups.append([f"#{number} is live.", f"Out the door goes #{number}."])
        moods.append("celebrating")
    if move := facts.get("carried"):
        number, station = move["number"], move["station"]
        place = PLACES[list(LABELS).index(station)]
        groups.append([f"#{number} moved and is now {place}.", f"Fresh off the belt, #{number} is {place}."])
        moods.append("carrying")
    if checks := facts.get("checks"):
        number = checks["number"]
        group = [f"#{number} is in checks.", f"The check desk has #{number}."]
        if "done" in checks:
            group.insert(0, f"{checks['done']} of {checks['total']} checks finished on #{number}.")
        elif checks["running"]:
            group.insert(0, f"Checks are running on #{number}.")
        groups.append(group)
        if checks["running"]:
            moods.append("working")
    if wait := facts.get("waiting"):
        number, minutes = wait["number"], wait["minutes"]
        unit = "minute" if minutes == 1 else "minutes"
        where = "for review" if wait["station"] == "Review" else "for a merge"
        groups.append([
            f"#{number} has waited {minutes} {unit} {where}.",
            f"Still in line, #{number} has waited {minutes} {unit} {where}.",
        ])
        moods.append("waiting")
    if merged := facts.get("merged"):
        number = merged["number"]
        groups.append([f"#{number} merged today.", f"The ink is dry on today's merge of #{number}."])
        if merged["recent"]:
            moods.append("celebrating")
    if number := facts.get("bench"):
        groups.append([f"#{number} is at the bench.", f"The workbench has #{number}."])
    if facts["recent_activity"]:
        moods.append("working")
    if not groups:
        groups.append(["This lane was active in the last 15 minutes."] if facts["recent_activity"]
                      else ["There is no recent activity for this lane.", "It's quiet on this stretch of belt."])
    return {"groups": groups, "moods": list(dict.fromkeys(moods)) or ["asleep"]}


def valid_line(answer, options):
    if not isinstance(answer, dict) or set(answer) != {"text", "mood"}:
        return False
    text = answer["text"]
    if (
        not isinstance(text, str) or not 0 < len(text) <= MAX_CHARACTERS
        or answer["mood"] not in options["moods"]
    ):
        return False
    groups = options["groups"]
    return any(
        text == first or any(
            text == f"{first} {second}"
            for other, group in enumerate(groups) if other != index
            for second in group
        )
        for index, group in enumerate(groups) for first in group
    )


def make_speech(snapshot, previous, budget, key, *, request=model_request):
    lines, changed = {}, {}
    for lane, facts in lane_facts(snapshot).items():
        digest = sha256(json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        options = speech_options(facts)
        old = previous.get(lane) or {}
        old_line = {field: old.get(field) for field in ("text", "mood")}
        lines[lane] = {
            "facts_hash": digest,
            "source": "facts",
            "text": options["groups"][0][0],
            "mood": options["moods"][0],
        }
        if old.get("facts_hash") != digest:
            changed[lane] = options
        elif key and old.get("source") == "model" and valid_line(old_line, options):
            lines[lane].update(old_line, source="model")
    stats = budget.stats()
    if key and changed:
        try:
            kwargs = chat_request_kwargs("factory_notes", max_output_tokens=640, temperature=0.4)
        except (ValueError, RuntimeError):
            return lines, stats
        answers, stats = budget.call({
            **kwargs,
            "messages": [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": json.dumps(changed, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }, key, request)
        if isinstance(answers, dict):
            for lane, options in changed.items():
                answer = answers.get(lane)
                if valid_line(answer, options):
                    lines[lane].update(answer, source="model")
    return lines, stats
