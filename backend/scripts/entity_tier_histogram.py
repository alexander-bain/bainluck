#!/usr/bin/env python3
"""entity_tier_histogram — how many entities land in each tier, per class.

Epic #1741 step 0 (#1742), spec `docs/entity-page-templates.md` §9.

## Why this script is an acceptance item and not a nice-to-have

Spec §11 leaves exactly one decision open: the threshold taste-check (12 / 4 /
3-per-section). It is deliberately gated on this output, so Alex's pass is "an
evidenced choice instead of a vibe". Every later step is also *sized* by it —
"leagues are 30 entities, 4 of them T0" is a plan; "leagues are probably mostly
fine" is not.

So the output has one job: for each entity class, how many entities land in each
tier, and — when a tier is surprising — WHY, in counts.

## What it reads

Public production endpoints by default. It deliberately does NOT need the admin
token or a DB connection: the point is to measure what a PAGE would be handed,
and the page is handed an API response. Reading the DB directly would measure a
different thing and silently diverge from the resolver's real inputs.

    python3 scripts/entity_tier_histogram.py                    # all classes
    python3 scripts/entity_tier_histogram.py --class competition
    python3 scripts/entity_tier_histogram.py --json out.json    # machine-readable

The resolver is imported, never reimplemented — a histogram that counts
differently from the page it predicts is worse than no histogram (ruling 021's
argument, one level out: two graders, one input).

## Honest limits, stated because a histogram invites over-reading

* **Rate limits are real.** The public API is 60/min and a throttled response
  parses as an error, not as an empty entity (memory:
  `reference_api_rate_limit_false_null`). Requests are spaced, and any entity
  whose fetch fails is reported in a separate `errors` bucket — NEVER counted as
  T0. An outage must not look like an off-season.
* **This is a snapshot.** Tiers are season-aware and expected to move (spec §2);
  a February run and an August run should disagree. Stamp the date on any
  conclusion drawn from it.
* **Leagues/teams/players are not wired yet.** Their classes are declared here and
  report `not_wired` until steps 1/3/4 land, so the shape of the report does not
  change under those steps — only its numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.entity_page_tiers import (  # noqa: E402
    TIERS,
    resolve_entity_tier,
)

DEFAULT_API = "https://api.bainluck.com"

#: Space requests so a sweep cannot rate-limit itself into false zeros. The public
#: limit is 60/min; this keeps a wide margin because the cost of a false T0 in
#: this report is a wrong threshold decision.
REQUEST_SPACING_SECONDS = 1.5

#: Competition slugs come from the hub registry itself rather than a second list
#: here — a hand-maintained copy would drift the first time a hub is added.
try:
    from app.routes.hub import HUB_CONFIGS  # noqa: E402

    COMPETITION_SLUGS = sorted(HUB_CONFIGS.keys())
except Exception:  # pragma: no cover - the script must still run standalone
    COMPETITION_SLUGS = []

#: Leagues come from `SPORT_HIERARCHY` for the same reason competitions come from
#: `HUB_CONFIGS`: it is the register the product already navigates by, so a second
#: list here would drift the first time a league is added. Step 1 (#1743).
try:
    from app.utils.sport_keys import SPORT_HIERARCHY  # noqa: E402

    _LEAGUE_ROWS = [
        {
            "sport_slug": sport_slug,
            "league_slug": lg.get("slug"),
            "name": lg.get("name"),
            "sport_key": (lg.get("sport_keys") or [None])[0],
        }
        for sport_slug, sport in SPORT_HIERARCHY.items()
        for lg in (sport.get("leagues") or [])
    ]
except Exception:  # pragma: no cover - the script must still run standalone
    _LEAGUE_ROWS = []

#: Measurable = has a sport key to query with.
LEAGUE_ROWS = [r for r in _LEAGUE_ROWS if r["sport_key"]]

#: NOT a tier, and deliberately not an error either. A league in the register with
#: no `sport_keys` (golf's DP World / LIV / Korn Ferry today) cannot be queried at
#: all, so we have no measurement of it. Gotcha #53 is the whole point: an absence
#: of measurement is not a measurement of absence, and filing these as T0 would
#: report "three empty leagues" when the truth is "three unasked questions".
LEAGUE_UNMEASURABLE = [r for r in _LEAGUE_ROWS if not r["sport_key"]]

LEAGUE_LABELS = {r["sport_key"]: f"{r['sport_slug']}/{r['league_slug']}" for r in LEAGUE_ROWS}


def _get(url: str, timeout: float = 30.0):
    req = urllib.request.Request(url, headers={"User-Agent": "bainluck-tier-histogram"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


def measure_competition(api: str, slug: str, *, now: datetime) -> dict:
    """One hub → its resolved tier plus the counts that explain it."""
    payload = _get(f"{api}/api/hub/{slug}")
    sections = payload.get("sections") or {}
    upcoming = payload.get("upcoming") or []

    out = resolve_entity_tier(
        sections,
        now=now,
        entity_is_real=True,
        record_n=0,  # wired at step 2, when the record strip lands on competitions
        next_event_count=len(upcoming),
        season_known=False,
    )
    return {
        "key": slug,
        "tier": out["tier"],
        "answers": out["answers"],
        "sections_populated": out["sections_populated"],
        "rows": sum(len(v or []) for v in sections.values()),
        "upcoming": len(upcoming),
        "dropped": out["pool_counts"]["dropped"],
        "settled": out["pool_counts"]["settled"],
        "unpriced": out["unpriced"],
        "duplicates": out["duplicates"],
        "per_section": {
            k: v["answers"] for k, v in sorted(out["per_section"].items())
        },
    }


def measure_league(api: str, sport_key: str, *, now: datetime) -> dict:
    """One league → its resolved tier plus the counts that explain it.

    Reads `/api/leagues/{sport_key}` — the same payload the league page is handed,
    for the reason stated in the module docstring: measuring the DB instead would
    measure a different thing and silently diverge from the resolver's real inputs.
    """
    payload = _get(f"{api}/api/leagues/{sport_key}")
    sections = payload.get("sections") or {}

    out = resolve_entity_tier(
        sections,
        now=now,
        entity_is_real=True,  # it is in SPORT_HIERARCHY; that IS league identity
        record_n=payload.get("record_n") or 0,
        next_event_count=payload.get("next_event_count") or 0,
        season_known=bool((payload.get("season") or {}).get("state")),
    )

    # Ruling 021, made mechanical. Once the route declares a tier, the histogram
    # must not quietly compute a second opinion: two graders over one input is
    # exactly the parity bug the typed field exists to prevent, and it is
    # unfindable precisely because both sides believe they are correct.
    declared = payload.get("tier", "__absent__")
    return {
        "key": LEAGUE_LABELS.get(sport_key, sport_key),
        "sport_key": sport_key,
        "tier": out["tier"],
        "declared_tier": declared,
        "tier_agrees": declared == "__absent__" or declared == out["tier"],
        "answers": out["answers"],
        "sections_populated": out["sections_populated"],
        "rows": sum(len(v or []) for v in sections.values()),
        "upcoming": payload.get("next_event_count") or 0,
        "dropped": out["pool_counts"]["dropped"],
        "settled": out["pool_counts"]["settled"],
        "unpriced": out["unpriced"],
        "duplicates": out["duplicates"],
        "per_section": {
            k: v["answers"] for k, v in sorted(out["per_section"].items())
        },
    }


CLASS_MEASURERS = {
    "competition": {
        "keys": lambda: COMPETITION_SLUGS,
        "measure": measure_competition,
        "unmeasurable": lambda: [],
        "step": 0,
    },
    "league": {
        "keys": lambda: [r["sport_key"] for r in LEAGUE_ROWS],
        "measure": measure_league,
        "unmeasurable": lambda: [
            {
                "key": f"{r['sport_slug']}/{r['league_slug']}",
                "reason": "no sport_keys in SPORT_HIERARCHY — not queryable",
            }
            for r in LEAGUE_UNMEASURABLE
        ],
        "step": 1,
    },
    # Declared now so the report's SHAPE is stable across the epic; the numbers
    # arrive with their steps.
    "team": {"keys": lambda: [], "measure": None, "unmeasurable": lambda: [], "step": 3},
    "player": {"keys": lambda: [], "measure": None, "unmeasurable": lambda: [], "step": 4},
}


def run(api: str, classes: list[str], *, now: datetime) -> dict:
    report: dict = {
        "generated_at_utc": now.isoformat(),
        "api": api,
        "classes": {},
    }

    for cls in classes:
        spec = CLASS_MEASURERS[cls]
        measurer = spec["measure"]
        if measurer is None:
            report["classes"][cls] = {"status": "not_wired", "entities": []}
            continue

        keys = spec["keys"]()
        entities: list[dict] = []
        errors: list[dict] = []
        for i, key in enumerate(keys):
            if i:
                time.sleep(REQUEST_SPACING_SECONDS)
            try:
                entities.append(measurer(api, key, now=now))
            except (urllib.error.URLError, RuntimeError, ValueError, TimeoutError) as e:
                # NEVER counted as a tier. A fetch failure is a gap in the
                # measurement, not a thin entity — the whole point of gotcha #53.
                errors.append({"key": key, "error": f"{type(e).__name__}: {e}"})

        hist = Counter(e["tier"] for e in entities)
        report["classes"][cls] = {
            "status": "measured",
            "measured": len(entities),
            "errors": errors,
            # Neither a tier nor an error: entities we could not ask about at all.
            "unmeasurable": spec["unmeasurable"](),
            # Ruling 021: where the route declares a tier, it must match ours.
            "tier_disagreements": [
                {
                    "key": e["key"],
                    "declared": e.get("declared_tier"),
                    "recomputed": e["tier"],
                }
                for e in entities
                if not e.get("tier_agrees", True)
            ],
            "histogram": {
                **{t: hist.get(t, 0) for t in TIERS},
                "no_page": hist.get(None, 0),
            },
            "entities": sorted(entities, key=lambda e: -e["answers"]),
        }

    return report


def render(report: dict) -> str:
    lines = [
        "ENTITY TIER HISTOGRAM",
        f"generated {report['generated_at_utc']}  ·  {report['api']}",
        "",
        "Tiers are season-aware and expected to move (spec §2). This is a snapshot;",
        "date any conclusion drawn from it.",
        "",
    ]
    for cls, data in report["classes"].items():
        lines.append(f"── {cls.upper()} ──")
        if data["status"] == "not_wired":
            step = CLASS_MEASURERS.get(cls, {}).get("step", "?")
            lines.append(f"   not wired yet — arrives with step {step}")
            lines.append("")
            continue

        h = data["histogram"]
        total = data["measured"]
        lines.append(
            f"   measured {total}"
            + (f"  ·  {len(data['errors'])} ERRORS (not counted as a tier)" if data["errors"] else "")
        )
        for tier in TIERS:
            n = h[tier]
            bar = "█" * n
            lines.append(f"   {tier:<9} {n:>3}  {bar}")
        if h["no_page"]:
            lines.append(f"   {'no_page':<9} {h['no_page']:>3}")
        lines.append("")
        # Width is computed, not guessed: league keys are "motorsports/nascar",
        # which silently ran into the tier column at a hardcoded 12.
        kw = max(
            [12]
            + [len(e["key"]) for e in data["entities"]]
            + [len(x["key"]) for x in data["errors"]]
            + [len(x["key"]) for x in (data.get("unmeasurable") or [])]
        ) + 2
        lines.append(f"   {'entity':<{kw}}{'tier':<10}{'ans':>4}{'secs':>6}{'rows':>6}{'drop':>6}  sections")
        for e in data["entities"]:
            secs = " ".join(f"{k}={v}" for k, v in e["per_section"].items() if v)
            lines.append(
                f"   {e['key']:<{kw}}{str(e['tier']):<10}{e['answers']:>4}"
                f"{e['sections_populated']:>6}{e['rows']:>6}{e['dropped']:>6}  {secs}"
            )
        for err in data["errors"]:
            lines.append(f"   {err['key']:<{kw}}ERROR     {err['error'][:60]}")
        for un in data.get("unmeasurable") or []:
            lines.append(f"   {un['key']:<{kw}}—         unmeasurable: {un['reason']}")

        # Loud on purpose. A silent disagreement here is the ruling-021 parity bug
        # arriving through the instrument that exists to catch it.
        for d in data.get("tier_disagreements") or []:
            lines.append(
                f"   !! TIER DISAGREEMENT {d['key']}: route declared "
                f"{d['declared']!r}, resolver says {d['recomputed']!r}"
            )
        lines.append("")

    lines.append("READ THIS BEFORE TUNING (spec §11):")
    lines.append("  `ans` is ANSWERS (deduped, priced, live) — `rows` is raw markets.")
    lines.append("  A big rows-vs-ans gap is the answers-not-rows case working, not a bug.")
    lines.append("  `drop` = unpriced + duplicate. A high drop with low ans means the")
    lines.append("  entity's markets are unpriced, which is a DIFFERENT problem from")
    lines.append("  thinness and has a different owner.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument(
        "--class",
        dest="classes",
        action="append",
        choices=sorted(CLASS_MEASURERS),
        help="Limit to one class (repeatable). Default: all.",
    )
    ap.add_argument("--json", dest="json_out", help="Write the raw report to this path.")
    args = ap.parse_args()

    classes = args.classes or sorted(CLASS_MEASURERS)
    now = datetime.now(timezone.utc)
    report = run(args.api, classes, now=now)

    print(render(report))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
