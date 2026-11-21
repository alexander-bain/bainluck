"""Keep the stations the collector actually saw each crate visit."""

from datetime import timedelta

from model import instant
from signals import on_floor

READ_GAP = timedelta(minutes=15)
MAX_VISITS = 18


def at_station(change):
    return change and (on_floor(change) or change["station"] == "Live")


def add_journeys(floor, previous):
    observed = floor["generated_at"]
    before = previous.get("generated_at")
    if before and instant(before) > instant(observed):
        before = None
    earlier = {
        (change["number"], change["line"]): change
        for change in previous.get("changes", [])
    } if before else {}
    gap = before and instant(observed) - instant(before) > READ_GAP

    for change in floor["changes"]:
        old = earlier.get((change["number"], change["line"]))
        visits = [dict(visit) for visit in (old or {}).get("journey", [])]
        was_on_floor = at_station(old)
        still_here = at_station(change)
        if was_on_floor and not visits:
            visits.append({"station": old["station"], "first_seen_at": before})
        same_visit = (
            was_on_floor and still_here and old["station"] == change["station"]
            and (not gap or change["station"] == "Live")
        )
        if was_on_floor and not same_visit:
            visits[-1]["last_seen_at"] = before
        if still_here and not same_visit:
            visits.append({"station": change["station"], "first_seen_at": observed})
        if visits:
            change["journey"] = visits[-MAX_VISITS:]
