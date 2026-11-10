#!/usr/bin/env python3
"""#12528: the reader walk. Ask the live site what a reader would ask, and sort every answer.

Stdlib only, GET only, public pages only. It never signs in and reads no secret.

    python3 tools/reader_walk/walk.py                        # run the search walk, print the summary
    python3 tools/reader_walk/walk.py --out /tmp/walk.json   # also keep the whole run
    python3 tools/reader_walk/walk.py --min-pass 34          # exit 1 below 34 passes

Every answer lands in exactly one of four states:

  pass      a clean answer whose first screen holds what the reader meant
  fail      a clean answer that does not
  degraded  the API said part of the answer is missing (its ``degraded`` list) and still
            said so on one retry
  error     no HTTP 200 after one retry

A degraded or failed read is never an empty answer and never a speed sample (#12290).
The checks in ``evals/reader-walk/queries/search-v1.json`` are the lenient reading: the
expected thing is somewhere on the first screen. The README says what the strict reading
still needs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
DEFAULT_QUERIES = REPO / "evals" / "reader-walk" / "queries" / "search-v1.json"
DEFAULT_API = "https://api.bainluck.com"
USER_AGENT = "bainluck-reader-walk/1 (+https://github.com/alexander-bain/bainluck/issues/12528)"

#: The lists a search answer can carry, in the order this walk reads them as one screen.
FIRST_SCREEN_LISTS = (
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
STATES = ("pass", "fail", "degraded", "error")
CLASSES = ("entity", "alias", "entity+market", "set", "other topics", "honesty")
SPEC_KEYS = {"empty", "kinds", "name_has_all", "name_has_any", "top", "min_count"}
_NAME_KEYS = ("name", "title", "text", "display_name", "label", "full_name")

Item = tuple[str, str]
Fetch = Callable[[str, str], tuple[int, int, Any]]


def name_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in _NAME_KEYS:
            if value.get(key):
                return str(value[key])
    return ""


def first_screen(payload: Any) -> list[Item]:
    """The (list, name) pairs a reader gets first, at most ``PER_LIST`` from each list."""
    if not isinstance(payload, Mapping):
        return []
    items: list[Item] = []
    for kind in FIRST_SCREEN_LISTS:
        rows = payload.get(kind) or []
        if not isinstance(rows, list):
            continue
        for row in rows[:PER_LIST]:
            if kind == "results" and isinstance(row, Mapping):
                home, away = name_of(row.get("home_team")), name_of(row.get("away_team"))
                label = f"{away} at {home}" if (home or away) else name_of(row)
            else:
                label = name_of(row)
            items.append((kind, label))
    return items


def is_degraded(payload: Any) -> bool:
    return bool(isinstance(payload, Mapping) and payload.get("degraded"))


def validate_spec(spec: Any) -> list[str]:
    """Every problem with one query's check; an empty list means it can be run."""
    if not isinstance(spec, Mapping):
        return ["the check is not an object"]
    problems = [f"unknown key {key!r}" for key in spec if key not in SPEC_KEYS]
    if spec.get("empty") is True:
        if set(spec) != {"empty"}:
            problems.append("an 'empty' check takes no other key")
        return problems
    if "empty" in spec:
        problems.append("'empty' may only be true")
    kinds = spec.get("kinds")
    if kinds is not None and (
        not isinstance(kinds, list) or not kinds or any(k not in FIRST_SCREEN_LISTS for k in kinds)
    ):
        problems.append("'kinds' must be a non-empty list of known lists")
    for key in ("name_has_all", "name_has_any"):
        words = spec.get(key)
        if words is not None and (
            not isinstance(words, list) or not words or any(not isinstance(w, str) or not w.strip() for w in words)
        ):
            problems.append(f"{key!r} must be a non-empty list of words")
    for key in ("top", "min_count"):
        number = spec.get(key)
        if number is not None and (not isinstance(number, int) or isinstance(number, bool) or number < 1):
            problems.append(f"{key!r} must be a whole number of at least 1")
    if not (kinds or spec.get("name_has_all") or spec.get("name_has_any")):
        problems.append("the check names neither a list nor a word, so anything would pass")
    return problems


def check(spec: Mapping[str, Any], items: Sequence[Item]) -> bool:
    """True when the first screen holds what the reader meant, by the lenient reading."""
    if spec.get("empty") is True:
        return len(items) == 0
    pool = items if spec.get("top") is None else items[: int(spec["top"])]
    kinds = spec.get("kinds")
    has_all = [w.lower() for w in spec.get("name_has_all") or ()]
    has_any = [w.lower() for w in spec.get("name_has_any") or ()]
    hits = 0
    for kind, name in pool:
        text = name.lower()
        if kinds and kind not in kinds:
            continue
        if any(word not in text for word in has_all):
            continue
        if has_any and not any(word in text for word in has_any):
            continue
        hits += 1
    return hits >= int(spec.get("min_count") or 1)


def classify(status: int, payload: Any, spec: Mapping[str, Any]) -> str:
    """One of ``STATES``. Only a clean HTTP 200 can pass or fail."""
    if status != 200 or not isinstance(payload, Mapping):
        return "error"
    if is_degraded(payload):
        return "degraded"
    return "pass" if check(spec, first_screen(payload)) else "fail"


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


def walk(
    queries: Sequence[Mapping[str, Any]],
    api: str = DEFAULT_API,
    *,
    fetch_fn: Fetch = fetch,
    sleep: Callable[[float], None] = time.sleep,
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
        state = classify(judged_status, judged_payload, query["check"])
        row: dict[str, Any] = {
            "class": query["class"],
            "q": query["q"],
            "expect": query["expect"],
            "state": state,
            "first_call_status": status,
            "first_call_degraded": bool(status == 200 and is_degraded(payload)),
            "degraded_lists": payload.get("degraded") if isinstance(payload, Mapping) else None,
            "retried": retried,
            # Only a clean first call is a cold speed sample; only a clean repeat is a repeat sample.
            "ms_cold": ms_first if clean_first else None,
            "ms_first_raw": ms_first,
            "ms_repeat": ms_repeat if (repeat_status == 200 and not is_degraded(repeat_payload)) else None,
            "top": first_screen(judged_payload)[:4] if judged_status == 200 else [],
        }
        if state != "pass":
            row["raw"] = _raw(judged_payload)  # keep the answer itself for anything that isn't a pass
        rows.append(row)
    return rows


def _print(summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
    states = summary["states"]
    print(
        f"{states['pass']} pass, {states['fail']} fail, {states['degraded']} degraded, "
        f"{states['error']} error of {summary['queries']} searches"
    )
    cold, repeat = summary["cold"], summary["repeat"]
    print(
        f"cold (clean first calls, n={cold['n']}): p50 {cold['p50_ms']} ms, p95 {cold['p95_ms']} ms, "
        f"max {cold['max_ms']} ms | repeat (n={repeat['n']}): p50 {repeat['p50_ms']} ms"
    )
    for name, counts in summary["by_class"].items():
        print(f"  {name}: " + ", ".join(f"{counts[s]} {s}" for s in STATES if counts[s]))
    for row in rows:
        if row["state"] != "pass":
            top = f"{row['top'][0][0]}: {row['top'][0][1]}" if row["top"] else "(nothing)"
            print(f"  {row['state'].upper():8} | {row['class']} | {row['q']} | wanted {row['expect']} | got {top}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The reader walk (#12528): searches, sorted into four states.")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--out", type=Path, help="write the whole run here as JSON")
    parser.add_argument("--min-pass", type=int, help="exit 1 when fewer searches pass")
    args = parser.parse_args(argv)
    queries = load_queries(args.queries)
    rows = walk(queries, args.api)
    summary = summarize(rows)
    _print(summary, rows)
    if args.out:
        run = {
            "walk_version": 1,
            "ran_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "api": args.api,
            "summary": summary,
            "rows": rows,
        }
        args.out.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.min_pass is not None and summary["states"]["pass"] < args.min_pass:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
