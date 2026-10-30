"""#10090 — fold the receipts' ``first_new_recv`` into per-event trailing seconds.

Speed's metric (2026-10-30 04:18Z), server half: the server TRAILS from our
receipt of the oldest eligible input readers lack until the first publication
that carries it to readers. TOTAL is the union of those intervals per event,
each second counted once; WORST is the longest single interval.

Reads log lines — a Platform API log session of worker-ws, and of any dyno
running a sportsbook/model writer — raw (``<ts> app[dyno]: <payload>``) or
bare; a structured-JSON payload is unwrapped to its ``"message"``. Folds:

* ``delivery-receipt`` ``stamps=`` items
  ``rev@stamped_at@newest_recv@oldest_recv@covered@first_new_recv``: one
  interval ``[first_new_recv, stamped_at]`` per item carrying one;
* its ``previews=`` items ``base_rev:seq@published_at@first_new_recv``:
  ``[first_new_recv, published_at]``;
* ``writer-receipt`` ``stamps=`` items (another writer's revision), as stamps.

Items written before the receipt fields existed (five-part stamps) carry no
claim and are counted as ``legacy_items``. ``first_new_recv`` of ``?`` (a writer
that could not say) is counted as ``unknown_recv``, never timed.

Clocks: recv and ``published_at`` are the dyno's wall clock; ``stamped_at`` is
the database write clock. A stamp interval that comes out negative (database
clock behind the dyno's) is clamped to 0 and counted as ``negative_clamped``.

HEADLINE ONLY. Every publication timed here carries the headline blend. The
chart's served line has no server-side publication of its own (pages read it
from stored history on request), so there is no chart interval to report.

``since``/``until`` keep intervals whose PUBLICATION falls in [since, until);
the total clips each to start no earlier than ``since``, the worst does not.

Stdlib only, so it can be copied into a readout unchanged.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from typing import Iterable, Optional

_DELIVERY = re.compile(r"live_blend_refresh\[(\w+)\]: delivery-receipt (.*)$")
_WRITER = re.compile(r"(\w+)\[([\w+]+)\]: writer-receipt (.*)$")

HEADLINE_ONLY = (
    "headline only: every interval ends at a publication of the headline blend "
    "(DNPL preview, stamp, or another writer's revision). The chart's served line "
    "has no server-side publication of its own, so no chart interval exists here."
)
BOUNDARY = (
    "server segment only: our receipt of the oldest eligible input readers lacked "
    "(dyno clock) -> the first publication carrying it (preview: dyno clock; stamp/"
    "revision: database write clock). Not the network, not the phone's paint. Each "
    "process judges against its own last publication, so a value another process "
    "already showed can be claimed again; the union counts each second once."
)


def _ts(value: Optional[str]) -> Optional[dt.datetime]:
    if not value or value in ("-", "?", "None"):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def message_of(line: str) -> str:
    """The log payload: a structured-JSON line's ``"message"``, else the line."""
    line = line.replace("\x00", "").rstrip("\n")
    brace = line.find("{")
    if brace >= 0:
        try:
            payload = json.loads(line[brace:])
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("message"), str):
            return payload["message"]
    return line


def _kv(text: str) -> dict:
    out = {}
    for token in text.split():
        key, sep, value = token.partition("=")
        if sep and key not in out:
            out[key] = value
    return out


def receipt_items(lines: Iterable[str]):
    """Yield one dict per receipt item: ``kind`` (stamp|preview|writer),
    ``writer``, ``event``, ``published``, ``first`` (datetime / None / ``"?"``),
    ``legacy`` (a pre-field item). Exact repeated messages are read once (a
    capture's back-to-back log sessions replay each other's tail)."""
    seen = set()
    for line in lines:
        message = message_of(line)
        if "-receipt " not in message or message in seen:
            continue
        seen.add(message)
        match = _DELIVERY.search(message)
        if match:
            kv = _kv(match.group(2))
            writer, event = kv.get("writer") or match.group(1), kv.get("event")
            for item in (kv.get("stamps") or "-").split(";"):
                parts = item.split("@")
                if len(parts) < 5:
                    continue
                yield _item("stamp", writer, event, parts[1], parts[5] if len(parts) > 5 else None)
            for item in (kv.get("previews") or "-").split(";"):
                parts = item.split("@")
                if len(parts) != 3:
                    continue
                yield _item("preview", writer, event, parts[1], parts[2])
            continue
        match = _WRITER.search(message)
        if match:
            kv = _kv(match.group(3))
            for item in (kv.get("stamps") or "-").split(";"):
                parts = item.split("@")
                if len(parts) < 6:
                    continue
                yield _item("writer", kv.get("writer") or match.group(2), kv.get("event"),
                            parts[1], parts[5])


def _item(kind, writer, event, published, first):
    return {
        "kind": kind, "writer": writer, "event": event, "published": _ts(published),
        "first": "?" if first == "?" else _ts(first), "legacy": first is None,
    }


def _union_seconds(intervals: list) -> float:
    total, end = 0.0, None
    for lo, hi in sorted(intervals):
        if end is None or lo > end:
            total += (hi - lo).total_seconds()
            end = hi
        elif hi > end:
            total += (hi - end).total_seconds()
            end = hi
    return total


def trailing(lines: Iterable[str], since: Optional[dt.datetime] = None,
             until: Optional[dt.datetime] = None) -> dict:
    """Per-event and overall trailing total / worst / over-1 s (module doc)."""
    per: dict[str, dict] = {}
    counts = {"items": 0, "carrying_items": 0, "legacy_items": 0, "unknown_recv": 0,
              "negative_clamped": 0, "by_kind": {}}
    for item in receipt_items(lines):
        published = item["published"]
        if published is None:
            continue
        if (since and published < since) or (until and published >= until):
            continue
        counts["items"] += 1
        if item["legacy"]:
            counts["legacy_items"] += 1
            continue
        first = item["first"]
        if first == "?":
            counts["unknown_recv"] += 1
            continue
        if first is None:
            continue
        seconds = (published - first).total_seconds()
        if seconds < 0:
            counts["negative_clamped"] += 1
            first, seconds = published, 0.0
        counts["carrying_items"] += 1
        counts["by_kind"][item["kind"]] = counts["by_kind"].get(item["kind"], 0) + 1
        event = per.setdefault(item["event"], {"intervals": [], "worst": None})
        event["intervals"].append((max(first, since) if since else first, published))
        if event["worst"] is None or seconds > event["worst"]["seconds"]:
            event["worst"] = {"seconds": round(seconds, 3), "kind": item["kind"],
                              "writer": item["writer"], "recv": first.isoformat(),
                              "published": published.isoformat()}
        event.setdefault("durations", []).append(seconds)
    events = {}
    for event_id, data in sorted(per.items()):
        durations = data["durations"]
        events[event_id] = {
            "total_s": round(_union_seconds(data["intervals"]), 3),
            "worst_s": data["worst"]["seconds"],
            "worst": data["worst"],
            "over_1s": sum(1 for d in durations if d >= 1.0),
            "intervals": len(durations),
        }
    worst = max((e["worst"] | {"event": k} for k, e in events.items()),
                key=lambda w: w["seconds"], default=None)
    return {
        "boundary": BOUNDARY,
        "chart": HEADLINE_ONLY,
        "total_s": round(sum(e["total_s"] for e in events.values()), 3),
        "worst": worst,
        "over_1s": sum(e["over_1s"] for e in events.values()),
        **counts,
        "events": events,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: trailing_readout.py LOGFILE [LOGFILE ...]")
    def _lines():
        for path in sys.argv[1:]:
            with open(path, errors="replace") as handle:
                yield from handle
    print(json.dumps(trailing(_lines()), indent=2, default=str))
