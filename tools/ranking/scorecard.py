#!/usr/bin/env python3
"""#12095 Decide 37-B: score one ranking slate against the family's grades.

    python3 tools/ranking/scorecard.py --slate evals/ranking/slates/<file>.json
        [--previous <yesterday's slate>.json | --slates-dir evals/ranking/slates]
        [--grades-dir evals/ranking/grades] [--replay movement | --replay pkg.mod:fn]

A slate is the JSON ``GET /api/admin/ranking/slates/{ref}`` returns (fetch it
with ``tools/ranking/grades.py fetch``). Grades are the files under
``evals/ranking/grades/`` whose ``slate_id`` matches.

Metrics, all over the top ten:

* **NDCG@10** against founder grades (shareable=2, interesting=1, neither=0;
  several founders average). No grades → UNKNOWN, never 0. A card with no grade
  counts 0 and the line says how many of the ten were graded, so a partly
  graded ranking reads as a lower bound. Non-expert (kid) grades get their own
  line and never mix into the founder number.
* **category entropy** (bits; the ceiling for ten cards is log2(10) ≈ 3.32).
* **max entity repeats** — the most cards sharing one team/person/outcome.
* **sameness** — how many of today's ten were in the previous day's served ten
  for the same surface. No previous slate → UNKNOWN.
* **freshness** — median age of the latest price, and the share that moved at
  least one point in 24h (over the cards where each is known).
* **truth-gate failures** — settled / stale / blend-missing cards shown
  (target 0). Only a recorded ``True`` counts; an unknown flag is reported as
  unknown, never as a pass.

``--replay`` re-ranks the slate's stored candidate pool with another ranker and
prints its scorecard beside the served one, so a new ranking is scored against
last week's grades before it ships. A ranker is a function
``rank(candidates: list[dict]) -> list`` returning candidates (or their
``item_key``s) best first; built-ins: ``served``, ``movement``, ``closest``.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

TOP = 10
GAINS = {"shareable": 2, "interesting": 1, "neither": 0}
#: A card "moved" in 24h at a change of at least one probability point.
MOVED_24H_MIN = 0.01
UNKNOWN = "UNKNOWN"
REPO = Path(__file__).resolve().parents[2]
DEFAULT_GRADES_DIR = REPO / "evals" / "ranking" / "grades"


# ── inputs ──────────────────────────────────────────────────────────────────


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text())


def _stamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def load_grades(grades_dir: Path, slate_id: str) -> list[dict]:
    """Every grade file under ``grades_dir`` for this slate."""
    out = []
    if not grades_dir or not Path(grades_dir).is_dir():
        return out
    for path in sorted(Path(grades_dir).glob("*.json")):
        try:
            doc = load_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and doc.get("slate_id") == slate_id:
            out.append(doc)
    return out


def find_previous(slates_dir: Path, slate: dict) -> Optional[dict]:
    """The latest slate for the same surface captured 12–36 h before this one."""
    at = _stamp(slate.get("captured_at"))
    if at is None or not slates_dir or not Path(slates_dir).is_dir():
        return None
    best = None
    for path in Path(slates_dir).glob("*.json"):
        try:
            doc = load_json(path)
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or doc.get("surface") != slate.get("surface"):
            continue
        other = _stamp(doc.get("captured_at"))
        if other is None or not (at - timedelta(hours=36) <= other <= at - timedelta(hours=12)):
            continue
        if best is None or other > _stamp(best["captured_at"]):
            best = doc
    return best


def item_gains(grade_docs: Iterable[dict], *, expert: bool) -> dict[str, float]:
    """item_key → mean gain across the graders of one kind (founder or kid)."""
    per_item: dict[str, list[int]] = {}
    for doc in grade_docs:
        if bool(doc.get("expert", True)) is not expert:
            continue
        for item in doc.get("items") or ():
            grade = item.get("grade")
            if item.get("item_key") and grade in GAINS:
                per_item.setdefault(item["item_key"], []).append(GAINS[grade])
    return {key: sum(v) / len(v) for key, v in per_item.items()}


# ── metrics ─────────────────────────────────────────────────────────────────


def ndcg_at(ranking: list[str], gains: dict[str, float], k: int = TOP) -> dict:
    """``{"value", "graded", "reason"}``; value is None (UNKNOWN) when nothing in
    the top k is graded or the ideal gain is 0."""
    top = ranking[:k]
    graded = sum(1 for key in top if key in gains)
    if not gains:
        return {"value": None, "graded": 0, "reason": "no grades"}
    if graded == 0:
        return {"value": None, "graded": 0, "reason": "no graded card in the top ten"}
    dcg = sum(gains.get(key, 0.0) / math.log2(i + 2) for i, key in enumerate(top))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    if idcg == 0:
        return {"value": None, "graded": graded, "reason": "every graded card is 'neither'"}
    return {"value": dcg / idcg, "graded": graded, "reason": None}


def category_entropy(cards: list[dict]) -> Optional[float]:
    if not cards:
        return None
    counts = Counter(c.get("category") or "(none)" for c in cards)
    n = sum(counts.values())
    return -sum((m / n) * math.log2(m / n) for m in counts.values())


def max_entity_repeats(cards: list[dict]) -> tuple[Optional[int], list[str]]:
    counts: Counter = Counter()
    for card in cards:
        counts.update({str(e) for e in card.get("entities") or () if e})
    if not counts:
        return None, []
    top = max(counts.values())
    return top, sorted(e for e, m in counts.items() if m == top)


def sameness(ranking: list[str], previous: Optional[dict]) -> Optional[int]:
    if not previous:
        return None
    return len(set(ranking[:TOP]) & set((previous.get("served_order") or [])[:TOP]))


def freshness(cards: list[dict]) -> dict:
    ages = [c["price_age_s"] for c in cards if isinstance(c.get("price_age_s"), (int, float))]
    moves = [c["movement_24h"] for c in cards if isinstance(c.get("movement_24h"), (int, float))]
    return {
        "median_age_s": statistics.median(ages) if ages else None,
        "ages_known": len(ages),
        "moved_share": (sum(1 for m in moves if abs(m) >= MOVED_24H_MIN) / len(moves)) if moves else None,
        "moved_count": sum(1 for m in moves if abs(m) >= MOVED_24H_MIN),
        "moves_known": len(moves),
    }


def truth_gate(cards: list[dict]) -> dict:
    out = {}
    for flag in ("settled", "stale", "blend_missing"):
        out[flag] = sum(1 for c in cards if c.get(flag) is True)
        out[f"{flag}_unknown"] = sum(1 for c in cards if c.get(flag) is None)
    out["failures"] = sum(
        1 for c in cards if any(c.get(f) is True for f in ("settled", "stale", "blend_missing"))
    )
    return out


def score_ranking(ranking: list[str], slate: dict, grades: list[dict], previous: Optional[dict]) -> dict:
    by_key = {c.get("item_key"): c for c in slate.get("candidates") or ()}
    cards = [by_key.get(key, {"item_key": key}) for key in ranking[:TOP]]
    repeats, entities = max_entity_repeats(cards)
    return {
        "top": [key for key in ranking[:TOP]],
        "ndcg_founder": ndcg_at(ranking, item_gains(grades, expert=True)),
        "ndcg_kid": ndcg_at(ranking, item_gains(grades, expert=False)),
        "entropy": category_entropy(cards),
        "max_entity_repeats": repeats,
        "repeated_entities": entities,
        "sameness": sameness(ranking, previous),
        "freshness": freshness(cards),
        "truth_gate": truth_gate(cards),
    }


# ── replay ──────────────────────────────────────────────────────────────────


def _served_pos(c: dict) -> float:
    pos = c.get("served_position")
    return pos if isinstance(pos, (int, float)) else math.inf


def rank_served(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=_served_pos)


def rank_movement(candidates: list[dict]) -> list[dict]:
    """Largest 24h move first; unknown movement last; ties keep served order."""
    def key(c):
        m = c.get("movement_24h")
        return (0 if isinstance(m, (int, float)) else 1, -abs(m) if isinstance(m, (int, float)) else 0, _served_pos(c))
    return sorted(candidates, key=key)


def rank_closest(candidates: list[dict]) -> list[dict]:
    """Probability closest to 50% first; unknown probability last."""
    def key(c):
        p = c.get("probability")
        return (0 if isinstance(p, (int, float)) else 1, abs(p - 0.5) if isinstance(p, (int, float)) else 0, _served_pos(c))
    return sorted(candidates, key=key)


BUILTIN_RANKERS: dict[str, Callable[[list[dict]], list]] = {
    "served": rank_served,
    "movement": rank_movement,
    "closest": rank_closest,
}


def resolve_ranker(spec: str) -> Callable[[list[dict]], list]:
    if spec in BUILTIN_RANKERS:
        return BUILTIN_RANKERS[spec]
    module, _, name = spec.partition(":")
    if not name:
        raise SystemExit(f"--replay {spec!r}: not a built-in ({', '.join(BUILTIN_RANKERS)}) or module:function")
    return getattr(importlib.import_module(module), name)


def replay(slate: dict, ranker: Callable[[list[dict]], list]) -> list[str]:
    """The ranker's order over the slate's stored candidates, as item keys."""
    out = []
    for entry in ranker([dict(c) for c in slate.get("candidates") or ()]):
        key = entry.get("item_key") if isinstance(entry, dict) else entry
        if key and key not in out:
            out.append(key)
    return out


# ── output ──────────────────────────────────────────────────────────────────


def _fmt_ndcg(n: dict) -> str:
    if n["value"] is None:
        return f"{UNKNOWN} ({n['reason']})"
    note = "" if n["graded"] == TOP else f"; {n['graded']}/{TOP} graded, ungraded count 0 (lower bound)"
    return f"{n['value']:.3f}{note}"


def _fmt_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return UNKNOWN
    return f"{seconds / 60:.0f} min" if seconds < 7200 else f"{seconds / 3600:.1f} h"


def _cells(s: dict) -> dict[str, str]:
    f, t = s["freshness"], s["truth_gate"]
    ent = s["entropy"]
    rep = s["max_entity_repeats"]
    return {
        "NDCG@10 (founder)": _fmt_ndcg(s["ndcg_founder"]),
        "NDCG@10 (kids, separate)": _fmt_ndcg(s["ndcg_kid"]),
        "Category entropy (bits, max 3.32)": UNKNOWN if ent is None else f"{ent:.2f}",
        "Max entity repeats": UNKNOWN if rep is None else f"{rep} ({', '.join(s['repeated_entities'][:3])})",
        "Sameness vs previous day": UNKNOWN if s["sameness"] is None else f"{s['sameness']} of {TOP}",
        "Median price age": _fmt_age(f["median_age_s"]) + (f" ({f['ages_known']}/{TOP} known)" if f["median_age_s"] is not None else ""),
        "Moved ≥1 pt in 24h": UNKNOWN if f["moved_share"] is None else f"{f['moved_count']} of {f['moves_known']} known ({f['moved_share']:.0%})",
        "Truth-gate failures (target 0)": (
            f"{t['failures']} — settled {t['settled']}, stale {t['stale']}, blend missing {t['blend_missing']}"
            + (
                f" (unknown: settled {t['settled_unknown']}, stale {t['stale_unknown']}, blend {t['blend_missing_unknown']})"
                if any(t[f'{k}_unknown'] for k in ('settled', 'stale', 'blend_missing'))
                else ""
            )
        ),
    }


def render(slate: dict, columns: list[tuple[str, dict]], grades: list[dict], previous: Optional[dict]) -> str:
    founders = sorted({d.get("grader", "?") for d in grades if d.get("expert", True)})
    kids = sorted({d.get("grader", "?") for d in grades if not d.get("expert", True)})
    lines = [
        f"### Ranking scorecard — {slate.get('surface')} slate `{slate.get('slate_id')}`",
        "",
        f"Captured {slate.get('captured_at')} · ranker `{slate.get('ranker_version')}` · "
        f"{len(slate.get('served_order') or [])} served · {len(slate.get('candidates') or [])} candidates · "
        f"founder graders: {', '.join(founders) or 'none'} · kid graders: {', '.join(kids) or 'none'} · "
        f"previous slate: {('`' + str(previous.get('slate_id')) + '` ' + str(previous.get('captured_at'))) if previous else 'none'}",
        "",
        "| Metric | " + " | ".join(name for name, _ in columns) + " |",
        "|---|" + "---|" * len(columns),
    ]
    cells = [_cells(s) for _, s in columns]
    for metric in cells[0]:
        lines.append(f"| {metric} | " + " | ".join(c[metric] for c in cells) + " |")
    by_key = {c.get("item_key"): c for c in slate.get("candidates") or ()}
    for name, s in columns:
        lines += ["", f"**Top ten — {name}:** " + " · ".join(
            f"{i}. {(by_key.get(k) or {}).get('title') or k}" for i, k in enumerate(s["top"], start=1)
        )]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--slate", required=True, type=Path)
    ap.add_argument("--previous", type=Path)
    ap.add_argument("--slates-dir", type=Path)
    ap.add_argument("--grades-dir", type=Path, default=DEFAULT_GRADES_DIR)
    ap.add_argument("--replay", action="append", default=[], help="built-in name or module:function; repeatable")
    args = ap.parse_args(argv)

    slate = load_json(args.slate)
    previous = load_json(args.previous) if args.previous else (
        find_previous(args.slates_dir, slate) if args.slates_dir else None
    )
    grades = load_grades(args.grades_dir, slate.get("slate_id"))
    columns = [("served", score_ranking(list(slate.get("served_order") or []), slate, grades, previous))]
    for spec in args.replay:
        columns.append((f"replay: {spec}", score_ranking(replay(slate, resolve_ranker(spec)), slate, grades, previous)))
    sys.stdout.write(render(slate, columns, grades, previous))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
