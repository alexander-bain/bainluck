#!/usr/bin/env python3
"""#12528: the reader walk. Ask the live site what a reader would ask, and sort every answer.

Stdlib only, GET only, public pages only. It never signs in and reads no secret.

    python3 tools/reader_walk/walk.py                        # run the search walk, print the summary
    python3 tools/reader_walk/walk.py --out /tmp/walk.json   # also keep the whole run
    python3 tools/reader_walk/walk.py --min-pass 34          # exit 1 below 34 field-proved passes

Every answer lands in exactly one of four states:

  pass      a clean answer that holds the thing the reader asked for
  fail      a clean answer that does not
  degraded  the API said part of the answer is missing (its ``degraded`` list) and still
            said so on one retry
  error     no HTTP 200 after one retry

A degraded or failed read is never an empty answer and never a speed sample (#12290).

A fifth state is about the check, not the site: ``expired`` means the check named a week
or a market that has passed its ``valid_until`` date, so it says nothing until refreshed.

A check proves its pass one of two ways, and a run reports them apart:

  fields    the answer carries the requested object itself: a team's slug, a collection's
            slug, a market's id, or a game in the asked-for sport starting in the
            asked-for window
  words     only the item's name was matched. This is a heuristic, not proof, and it is
            never counted toward an acceptance number.

Neither reading says where on the page the thing lands. Order is the browser walk's job.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, NamedTuple, Sequence

REPO = Path(__file__).resolve().parents[2]
DEFAULT_QUERIES = REPO / "evals" / "reader-walk" / "queries" / "search-v1.json"
DEFAULT_API = "https://api.bainluck.com"
USER_AGENT = "bainluck-reader-walk/1 (+https://github.com/alexander-bain/bainluck/issues/12528)"

#: The lists a search answer can carry.
LISTS = (
    "event_concepts",
    "collections",
    "teams",
    "futures",
    "futures_families",
    "results",
    "sports",
)
PER_LIST = 6
RETRY_PAUSE_S = 2.0
RAW_LIMIT_CHARS = 40_000
#: A game that began up to this long ago still counts as "tonight".
STARTED_HOURS_AGO = 6
STATES = ("pass", "fail", "degraded", "error", "expired")
PROOFS = ("fields", "words")
CLASSES = ("entity", "alias", "entity+market", "set", "other topics", "honesty")
#: A ``where`` on one of these names the object itself; on any other field it only narrows.
IDENTITY_FIELDS = ("id", "slug", "key")
SPEC_KEYS = {
    "empty",
    "any_of",
    "all_of",
    "kinds",
    "where",
    "name_has_all",
    "name_has_any",
    "name_has_none",
    "outcome_has_any",
    "starts_within_hours",
    "rank_in_list_max",
}
_WORD_KEYS = ("name_has_all", "name_has_any", "name_has_none", "outcome_has_any")
_NAME_KEYS = ("name", "title", "text", "display_name", "label", "full_name")

Fetch = Callable[[str, str], tuple[int, int, Any]]


class Item(NamedTuple):
    kind: str
    name: str
    rank: int  # 1-based position inside its own list
    raw: Mapping[str, Any]


def name_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in _NAME_KEYS:
            if value.get(key):
                return str(value[key])
    return ""


def first_screen(payload: Any) -> list[Item]:
    """What an answer holds: at most ``PER_LIST`` rows from each list, each with its rank."""
    if not isinstance(payload, Mapping):
        return []
    items: list[Item] = []
    for kind in LISTS:
        rows = payload.get(kind) or []
        if not isinstance(rows, list):
            continue
        for rank, row in enumerate(rows[:PER_LIST], 1):
            if kind == "results" and isinstance(row, Mapping):
                home, away = name_of(row.get("home_team")), name_of(row.get("away_team"))
                label = f"{away} at {home}" if (home or away) else name_of(row)
            else:
                label = name_of(row)
            items.append(Item(kind, label, rank, row if isinstance(row, Mapping) else {}))
    return items


def is_degraded(payload: Any) -> bool:
    return bool(isinstance(payload, Mapping) and payload.get("degraded"))


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def validate_spec(spec: Any) -> list[str]:
    """Every problem with one check; an empty list means it can be run."""
    if not isinstance(spec, Mapping):
        return ["the check is not an object"]
    problems = [f"unknown key {key!r}" for key in spec if key not in SPEC_KEYS]
    if "empty" in spec:
        if spec.get("empty") is not True:
            problems.append("'empty' may only be true")
        if set(spec) != {"empty"}:
            problems.append("an 'empty' check takes no other key")
        return problems
    for joiner in ("any_of", "all_of"):
        if joiner in spec:
            options = spec.get(joiner)
            if set(spec) != {joiner}:
                problems.append(f"an {joiner!r} check takes no other key")
            if not isinstance(options, list) or len(options) < 2:
                problems.append(f"{joiner!r} needs at least two checks")
            else:
                for option in options:
                    problems.extend(validate_spec(option))
            return problems
    kinds = spec.get("kinds")
    if kinds is not None and (not isinstance(kinds, list) or not kinds or any(k not in LISTS for k in kinds)):
        problems.append("'kinds' must be a non-empty list of known lists")
    where = spec.get("where")
    if where is not None:
        if not isinstance(where, Mapping) or not where:
            problems.append("'where' must name at least one field")
        else:
            for field, allowed in where.items():
                if not isinstance(allowed, list) or not allowed or any(
                    isinstance(v, bool) or not isinstance(v, (str, int)) or str(v).strip() in ("", "*") for v in allowed
                ):
                    problems.append(f"'where' field {field!r} needs a non-empty list of values")
    for key in _WORD_KEYS:
        words = spec.get(key)
        if words is not None and (
            not isinstance(words, list) or not words or any(not isinstance(w, str) or not w.strip() for w in words)
        ):
            problems.append(f"{key!r} must be a non-empty list of words")
    for key in ("rank_in_list_max", "starts_within_hours"):
        if spec.get(key) is not None and not _is_count(spec[key]):
            problems.append(f"{key!r} must be a whole number of at least 1")
    if spec.get("starts_within_hours") is not None and kinds != ["results"]:
        problems.append("'starts_within_hours' only reads games, so 'kinds' must be [\"results\"]")
    selects = bool(where) or bool(spec.get("name_has_all")) or bool(spec.get("name_has_any"))
    selects = selects or spec.get("starts_within_hours") is not None or bool(spec.get("outcome_has_any"))
    if not selects:
        problems.append("the check names no object, word or window, so an unrelated answer would pass")
    return problems


def proof_of(spec: Mapping[str, Any]) -> str:
    """How a pass on this check is proved: by ``fields`` or by ``words`` only."""
    if spec.get("empty") is True:
        return "fields"
    for joiner in ("any_of", "all_of"):
        if joiner in spec:
            return "fields" if all(proof_of(option) == "fields" for option in spec[joiner]) else "words"
    where = spec.get("where") or {}
    if any(field in IDENTITY_FIELDS for field in where):
        return "fields"
    if spec.get("starts_within_hours") is not None:
        return "fields"
    return "words"


def _field_matches(raw: Mapping[str, Any], field: str, allowed: Sequence[Any]) -> bool:
    value = raw.get(field)
    if value is None or isinstance(value, (dict, list)):
        return False
    text = str(value).strip().lower()
    for want in allowed:
        wanted = str(want).strip().lower()
        if wanted.endswith("*"):
            if text.startswith(wanted[:-1]):
                return True
        elif text == wanted:
            return True
    return False


def _outcome_has(raw: Mapping[str, Any], words: Sequence[str]) -> bool:
    outcomes = raw.get("top_outcomes") or raw.get("outcomes") or []
    names = [name_of(o).lower() for o in outcomes] if isinstance(outcomes, list) else []
    return any(word in name for word in words for name in names)


def _starts_within(raw: Mapping[str, Any], hours: int, now: datetime) -> bool:
    stamp = raw.get("commence_time")
    if not isinstance(stamp, str) or not stamp:
        return False
    try:
        start = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return now - timedelta(hours=STARTED_HOURS_AGO) <= start <= now + timedelta(hours=hours)


def check(spec: Mapping[str, Any], items: Sequence[Item], now: datetime) -> bool:
    """True when the answer holds the thing the reader asked for. ``now`` is passed in, never read."""
    if spec.get("empty") is True:
        return len(items) == 0
    if "any_of" in spec:
        return any(check(option, items, now) for option in spec["any_of"])
    if "all_of" in spec:
        return all(check(option, items, now) for option in spec["all_of"])
    kinds = spec.get("kinds")
    where = spec.get("where") or {}
    has_all = [w.lower() for w in spec.get("name_has_all") or ()]
    has_any = [w.lower() for w in spec.get("name_has_any") or ()]
    has_none = [w.lower() for w in spec.get("name_has_none") or ()]
    outcome_any = [w.lower() for w in spec.get("outcome_has_any") or ()]
    rank_max = spec.get("rank_in_list_max")
    hours = spec.get("starts_within_hours")
    for item in items:
        text = item.name.lower()
        if kinds and item.kind not in kinds:
            continue
        if rank_max is not None and item.rank > rank_max:
            continue
        if not all(_field_matches(item.raw, field, allowed) for field, allowed in where.items()):
            continue
        if any(word not in text for word in has_all):
            continue
        if has_any and not any(word in text for word in has_any):
            continue
        if any(word in text for word in has_none):
            continue
        if outcome_any and not _outcome_has(item.raw, outcome_any):
            continue
        if hours is not None and not _starts_within(item.raw, hours, now):
            continue
        return True
    return False


def classify(status: int, payload: Any, spec: Mapping[str, Any], now: datetime) -> str:
    """One of ``STATES``. Only a clean HTTP 200 can pass or fail."""
    if status != 200 or not isinstance(payload, Mapping):
        return "error"
    if is_degraded(payload):
        return "degraded"
    return "pass" if check(spec, first_screen(payload), now) else "fail"


def valid_until(query: Mapping[str, Any]) -> datetime | None:
    """The end of the last day a calendar-bound check still means what it says, in UTC."""
    stamp = query.get("valid_until")
    if stamp is None:
        return None
    day = datetime.strptime(str(stamp), "%Y-%m-%d")
    return day.replace(tzinfo=timezone.utc) + timedelta(days=1)


def is_expired(query: Mapping[str, Any], now: datetime) -> bool:
    end = valid_until(query)
    return end is not None and now >= end


def load_queries(path: Path = DEFAULT_QUERIES) -> list[dict[str, Any]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    queries = doc.get("queries") if isinstance(doc, Mapping) else None
    if not isinstance(queries, list) or not queries:
        raise ValueError(f"{path}: no queries")
    seen: set[str] = set()
    for row in queries:
        text = row.get("q") if isinstance(row, Mapping) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{path}: a query has no text")
        if text in seen:
            raise ValueError(f"{path}: {text!r} appears twice")
        seen.add(text)
        if row.get("class") not in CLASSES:
            raise ValueError(f"{path}: {text!r} has an unknown class {row.get('class')!r}")
        if not str(row.get("expect") or "").strip():
            raise ValueError(f"{path}: {text!r} does not say what the reader expects")
        problems = validate_spec(row.get("check"))
        if problems:
            raise ValueError(f"{path}: {text!r}: {'; '.join(problems)}")
        try:
            valid_until(row)
        except ValueError:
            raise ValueError(f"{path}: {text!r}: 'valid_until' must be a date like 2026-11-16") from None
    return queries


def percentile(values: Sequence[int], fraction: float) -> int | None:
    """Nearest-rank percentile; ``None`` when there is nothing to rank."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def _speed(values: Sequence[int]) -> dict[str, Any]:
    return {
        "n": len(values),
        "p50_ms": percentile(values, 0.5),
        "p90_ms": percentile(values, 0.9),
        "p95_ms": percentile(values, 0.95),
        "max_ms": max(values) if values else None,
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    states = {state: sum(1 for r in rows if r["state"] == state) for state in STATES}
    by_class: dict[str, dict[str, int]] = {}
    for row in rows:
        counts = by_class.setdefault(row["class"], {state: 0 for state in STATES})
        counts[row["state"]] += 1
    return {
        "queries": len(rows),
        "states": states,
        "checks_by_proof": {p: sum(1 for r in rows if r["proof"] == p) for p in PROOFS},
        "pass_by_proof": {p: sum(1 for r in rows if r["state"] == "pass" and r["proof"] == p) for p in PROOFS},
        "by_class": by_class,
        "first_call_degraded": sum(1 for r in rows if r.get("first_call_degraded")),
        "first_call_not_200": sum(1 for r in rows if r.get("first_call_status") != 200),
        "cold": _speed([r["ms_cold"] for r in rows if r.get("ms_cold") is not None]),
        "repeat": _speed([r["ms_repeat"] for r in rows if r.get("ms_repeat") is not None]),
    }


def fetch(api: str, path: str, timeout: float = 35.0) -> tuple[int, int, Any]:
    """GET one public path. Returns (status, milliseconds, payload); status 0 means no answer."""
    started = time.time()
    request = urllib.request.Request(api + path, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
        return status, round((time.time() - started) * 1000), json.loads(body)
    except Exception as exc:  # a refused, timed-out or unreadable answer is an error, never empty
        return 0, round((time.time() - started) * 1000), {"_error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _raw(payload: Any) -> Any:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return payload if len(text) <= RAW_LIMIT_CHARS else text[:RAW_LIMIT_CHARS] + " …(cut)"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def walk(
    queries: Sequence[Mapping[str, Any]],
    api: str = DEFAULT_API,
    *,
    fetch_fn: Fetch = fetch,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = _utc_now,
    pause_s: float = 0.15,
) -> list[dict[str, Any]]:
    """Ask every query: a first (cold) call, one retry if it wasn't clean, and a repeat."""
    rows: list[dict[str, Any]] = []
    for query in queries:
        path = "/api/events/search?q=" + urllib.parse.quote(query["q"])
        status, ms_first, payload = fetch_fn(api, path)
        sleep(pause_s)
        clean_first = status == 200 and not is_degraded(payload)
        judged_status, judged_payload, retried = status, payload, False
        if not clean_first:
            sleep(RETRY_PAUSE_S)
            retried = True
            judged_status, _ms, judged_payload = fetch_fn(api, path)
            sleep(pause_s)
        repeat_status, ms_repeat, repeat_payload = fetch_fn(api, path)
        sleep(pause_s)
        now = clock()
        # A check past its date says nothing about the site, so it is never a pass or a fail.
        state = "expired" if is_expired(query, now) else classify(judged_status, judged_payload, query["check"], now)
        row: dict[str, Any] = {
            "class": query["class"],
            "q": query["q"],
            "expect": query["expect"],
            "state": state,
            "proof": proof_of(query["check"]),
            "valid_until": query.get("valid_until"),
            "first_call_status": status,
            "first_call_degraded": bool(status == 200 and is_degraded(payload)),
            "degraded_lists": payload.get("degraded") if isinstance(payload, Mapping) else None,
            "retried": retried,
            # Only a clean first call is a cold speed sample; only a clean repeat is a repeat sample.
            "ms_cold": ms_first if clean_first else None,
            "ms_first_raw": ms_first,
            "ms_repeat": ms_repeat if (repeat_status == 200 and not is_degraded(repeat_payload)) else None,
            "holds": [[i.kind, i.name] for i in first_screen(judged_payload)[:4]] if judged_status == 200 else [],
        }
        if state not in ("pass", "expired"):
            row["raw"] = _raw(judged_payload)  # keep the answer itself for anything that isn't a pass
        rows.append(row)
    return rows


def _print(summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
    states, proved, asked = summary["states"], summary["pass_by_proof"], summary["checks_by_proof"]
    print(
        f"{states['pass']} pass, {states['fail']} fail, {states['degraded']} degraded, "
        f"{states['error']} error of {summary['queries']} searches"
        + (f" ({states['expired']} more had a check past its date and were not judged)" if states["expired"] else "")
    )
    print(
        f"passes proved by fields: {proved['fields']} of {asked['fields']} | "
        f"by words only (a heuristic, not proof): {proved['words']} of {asked['words']}"
    )
    cold, repeat = summary["cold"], summary["repeat"]
    print(
        f"cold (clean first calls, n={cold['n']}): p50 {cold['p50_ms']} ms, p95 {cold['p95_ms']} ms, "
        f"max {cold['max_ms']} ms | repeat (n={repeat['n']}): p50 {repeat['p50_ms']} ms"
    )
    for name, counts in summary["by_class"].items():
        print(f"  {name}: " + ", ".join(f"{counts[s]} {s}" for s in STATES if counts[s]))
    for row in rows:
        if row["state"] == "expired":
            print(f"  EXPIRED  | {row['class']} | {row['q']} | refresh this check: it was valid until {row['valid_until']}")
        elif row["state"] != "pass":
            got = f"{row['holds'][0][0]}: {row['holds'][0][1]}" if row["holds"] else "(nothing)"
            print(f"  {row['state'].upper():8} | {row['class']} | {row['q']} | wanted {row['expect']} | first row {got}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The reader walk (#12528): searches, sorted into four states.")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--out", type=Path, help="write the whole run here as JSON")
    parser.add_argument("--min-pass", type=int, help="exit 1 when fewer searches pass with field proof")
    args = parser.parse_args(argv)
    queries = load_queries(args.queries)
    rows = walk(queries, args.api)
    summary = summarize(rows)
    _print(summary, rows)
    if args.out:
        run = {
            "walk_version": 2,
            "ran_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "api": args.api,
            "summary": summary,
            "rows": rows,
        }
        args.out.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.min_pass is not None and summary["pass_by_proof"]["fields"] < args.min_pass:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
