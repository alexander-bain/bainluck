"""Keep the crew's recorded week and the station moves seen today."""

from collections import Counter, defaultdict
from datetime import timedelta

from model import BUILDERS, PACIFIC, STATIONS, instant, iso
from signals import on_floor

CREW = (*dict.fromkeys(BUILDERS.values()), "Fable")


def add_day_replay(floor, previous):
    now = instant(floor["generated_at"])
    day = now.astimezone(PACIFIC).date().isoformat()
    earlier = previous.get("day_replay") or {}
    events = {event["id"]: event for event in earlier.get("events", [])}
    if earlier.get("date") != day:
        events.clear()
    builders = {change["number"]: change["builder"] for change in floor["changes"]}
    returns = {
        (e["number"], e["line"], instant(e["observed_at"]))
        for e in floor.get("events", []) if e["kind"] == "returned"
    }

    def milliseconds(at):
        return int(at.timestamp()) * 1000 + at.microsecond // 1000

    for move in floor.get("transitions", []):
        at = instant(move["at"])
        observed = instant(move.get("observed_at") or move["at"])
        if (
            at.astimezone(PACIFIC).date().isoformat() != day
            or not at <= observed <= now
            or move["from"] == move["to"]
        ):
            continue
        number, line = move["number"], move["line"]
        start, end = move["from"], move["to"]
        key = f"transfer:{line}:{number}:{start}:{end}:{milliseconds(at)}:{milliseconds(observed)}"
        old = events.get(key, {})
        event = {
            "id": key,
            "kind": "returned" if (number, line, observed) in returns else old.get("kind", "move"),
            "number": number,
            "line": line,
            "from": start,
            "station": end,
            "at": move["at"],
            "observed_at": move.get("observed_at") or move["at"],
        }
        builder = builders.get(number) or old.get("builder")
        if builder:
            event["builder"] = builder
        events[key] = event

    if events:
        floor["day_replay"] = {
            "date": day,
            "through": max((e["observed_at"] for e in events.values()), key=instant),
            "events": sorted(
                events.values(), key=lambda e: (instant(e["at"]), instant(e["observed_at"]), e["id"])
            ),
        }


def station_totals(visits):
    intervals = defaultdict(list)
    for builder, number, station, start, end in visits:
        intervals[builder, number, station].append((instant(start), instant(end)))
    totals = defaultdict(Counter)
    for (builder, _, station), spans in intervals.items():
        counted_through = min(start for start, _ in spans)
        for start, end in sorted(spans):
            # A crate on two lines can spend the same minute at a station only once.
            totals[builder][station] += max(0, (end - max(counted_through, start)).total_seconds())
            counted_through = max(end, counted_through)
    return totals


def add_crew_week(floor, pulls, saved=None):
    now = instant(floor["generated_at"])
    local = now.astimezone(PACIFIC)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week = monday.date().isoformat()
    saved = saved if saved and saved.get("week") == week else {}
    shipped = dict(saved.get("shipped", {}))
    work = dict(saved.get("work", {}))
    visits = dict(saved.get("visits", {}))
    first_read = saved.get("first_read", floor["generated_at"])
    started = {pull["number"]: pull.get("created_at") for pull in pulls}
    running = {}

    def record(builder, number, kind, at):
        if builder in CREW and at and monday <= instant(at) <= now:
            work[f"{builder}/{number}/{kind}/{iso(instant(at))}"] = (builder, at)

    def oldest(builder, number, since):
        if not since or instant(since) > now:
            return
        prior = running.get(builder)
        if prior is None or (instant(since), number) < (instant(prior["since"]), prior["number"]):
            running[builder] = {"number": number, "since": since}

    for change in floor["changes"]:
        builder, number = change["builder"], change["number"]
        live = change.get("live_at")
        if builder in CREW and live and monday <= instant(live) <= now:
            shipped[str(number)] = builder
            record(builder, number, "live", live)
        if on_floor(change) and not change.get("merged_at"):
            if builder in CREW:
                oldest(builder, number, started.get(number))
            if change["station"] == "Review":
                oldest("Fable", number, change.get("station_since"))
        cleared = change.get("approvals", {}).get("fable")
        record("Fable", number, "accept", cleared)

        for visit in change.get("journey", []):
            # Only closed, observed visits provide a settled duration.
            before = visit.get("last_seen_at")
            if not before:
                continue
            end = instant(before)
            start = max(monday, instant(visit["first_seen_at"]))
            if not start < end <= now:
                continue
            station = visit["station"]
            participants = [builder] if builder in CREW else []
            if station == "Review" and cleared and start <= instant(cleared) <= end:
                participants.append("Fable")
            for participant in participants:
                key = f"{participant}/{number}/{station}/{iso(start)}/{iso(end)}"
                visits[key] = (participant, number, station, iso(start), iso(end))

    for event in floor.get("events", []):
        if event["kind"] == "commit":
            record(event.get("builder"), event["number"], "commit", event["at"])
        if event["kind"] == "returned":
            record("Fable", event["number"], "return", event["at"])

    station_time = station_totals(visits.values())
    hours = defaultdict(Counter)
    fable_looks = 0
    for builder, at in work.values():
        hours[builder][instant(at).astimezone(PACIFIC).hour] += 1
        fable_looks += builder == "Fable"
    deliveries = Counter(shipped.values())
    floor["crew_week"] = {
        "since": max((iso(monday), first_read), key=instant),
        "builders": {
            builder: {
                "changes": fable_looks if builder == "Fable" else deliveries[builder],
                "stations": [
                    station for station in STATIONS if station_time[builder][station] > 0
                    and station_time[builder][station] == max(station_time[builder].values())
                ],
                "hours": sorted(hour for hour, count in hours[builder].items()
                                if count == max(hours[builder].values())),
                **({"longest": running[builder]} if builder in running else {}),
            }
            for builder in CREW
        },
    }
    return {"week": week, "first_read": first_read, "shipped": shipped, "work": work, "visits": visits}
