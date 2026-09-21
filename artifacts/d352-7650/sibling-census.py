"""#7650 step (b) — what does teaching the shared grammar DATES do to each consumer?

Run:  BL_RUN=before python3 artifacts-discover/d352/d352_sibling_census.py

THE QUESTION THIS ANSWERS, AND WHY IT HAS TO BE ASKED BEFORE ANY WIRING.

`cumulative_outcome_ladder` is one predicate read by four reader-visible sites:

  1. `feed._outcomes_are_cumulative_ladder` -> `_feed_display_scale`  — THE DIVISOR (the ship)
  2. `outcome_display.drop_incoherent_ladder_outcomes`                — which bars a card draws
  3. `outcome_display.ladder_treatment_collapsed`                     — whether the field draws AT ALL
  4. `futures_highlights.leader_is_ladder_rung` / `feed._leader_is_ladder_rung` — the leader COPY

Widening the grammar lands on the POPULATION PREDICATE, so all four move together
and three of them are NOT the ship. `#7641`'s abandoned first build (`690ea46cb`)
is the same mistake with a different gate: a widening whose blast radius was
assumed rather than measured. So every flipped field is priced at all four sites
here, before `dates=True` is wired into any of them.

═══ TWO THINGS THIS INSTRUMENT DOES DELIBERATELY ═══

**THE OUTCOME TEXT COMES FROM THE DATABASE, NOT THE PAGE PAYLOAD.** `futures_outcomes.name`
is the exact string the feed's ORM path hands the predicate. `top_outcomes[].name`
on the API is HUMANIZED and `distribution_outcomes[].label` is a third rendering;
asking a grammar question of a re-rendered string measures the renderer.

**A FETCH FAILURE IS NEVER AN ABSENCE.** The feed is fetched with the status code
read and 429 backed off (d349's lesson: 57 of 91 cards once vanished from a census
that still printed a confident "0 regressed"). The db-query is chunked and its row
count reconciled against the ids asked for, so a truncated answer is LOUD.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from app.utils.ladder_monotonicity import cumulative_outcome_ladder  # noqa: E402
# Imported as a MODULE, not flat: `_verdict_with_dates` below has to rebind
# `cumulative_outcome_ladder` on the module object `outcome_display` actually
# reads, and a flat `from ... import` would bind a local name that function's
# callees never consult.
from app.utils import outcome_display  # noqa: E402

incoherent_ladder_verdict = outcome_display.incoherent_ladder_verdict
LADDER_MIN_DRAWN_RUNGS = outcome_display.LADDER_MIN_DRAWN_RUNGS

API = os.environ["BAINLUCK_API"]
TOK = os.environ["ADMIN_TOKEN"]
RUN = os.environ.get("BL_RUN", "before")
STAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

RATE_LIMITED = object()


def curl(url, *extra):
    delay = 2.0
    for _ in range(6):
        r = subprocess.run(
            ["curl", "-s", "--max-time", "30", "-w", "\n%{http_code}", *extra, url],
            capture_output=True, text=True,
        )
        body, _, code = r.stdout.rpartition("\n")
        if code.strip() == "429":
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
            continue
        if code.strip() != "200":
            time.sleep(1.0)
            continue
        try:
            return json.loads(body)
        except Exception:
            time.sleep(1.0)
    return RATE_LIMITED


def dbq(sql):
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", "-H", f"Authorization: Bearer {TOK}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"sql": sql, "limit": 5000}),
         f"{API}/api/admin/db-query"],
        capture_output=True, text=True,
    )
    try:
        return json.loads(r.stdout)["rows"]
    except Exception:
        sys.exit(f"db-query unreadable — no run. Body: {r.stdout[:300]}")


# ── the feed, always fresh ────────────────────────────────────────────────────
feed = curl(f"{API}/api/feed?limit=200")
if feed is RATE_LIMITED or not feed or "items" not in feed:
    sys.exit("feed fetch FAILED — no run. An empty feed is not a clean census.")

#: The copy a card derives from its LEADER, which is what site 4 suppresses.
#: `leader_is_ladder_rung` turning True does not by itself change a reader's
#: screen — it only withholds copy the card was going to write. So the card's
#: CURRENT copy is captured here and the site-4 count is taken against it,
#: rather than reported as "5 cards stop naming a favorite" on the strength of
#: the predicate alone. A predicate flip is not a reader-visible change.
_LEADER_REASONS = {"leader_change", "rank_shakeup", "major_movement_24h", "major_surprise"}

cards = {}
copy = {}
for item in feed["items"]:
    if item.get("type") != "futures":
        continue
    data = item.get("data") or {}
    if not data.get("id"):
        continue
    cards[data["id"]] = str(data.get("name") or "")[:52]
    card = data.get("discover_card") or {}
    reasons = [r.get("code") if isinstance(r, dict) else r
               for r in (data.get("reasons") or card.get("reasons") or [])]
    copy[data["id"]] = {
        "headline": card.get("headline"),
        "caption": card.get("caption"),
        "context_line": card.get("context_line"),
        "reasons": reasons,
        "leader_derived": bool(set(reasons) & _LEADER_REASONS) or bool(card.get("headline")),
    }

if not cards:
    sys.exit("no futures cards on the feed — no run.")

# ── the outcome text, from the DB, chunked and RECONCILED ─────────────────────
ids = sorted(cards)
legs: dict[int, list[tuple[str, float | None]]] = {i: [] for i in ids}
for start in range(0, len(ids), 40):
    chunk = ids[start:start + 40]
    rows = dbq(
        "SELECT market_id, name, current_probability FROM futures_outcomes "
        f"WHERE market_id IN ({','.join(str(i) for i in chunk)}) ORDER BY market_id, id"
    )
    for market_id, name, probability in rows:
        legs[market_id].append(
            (name, None if probability is None else float(probability))
        )

unread = [i for i in ids if not legs[i]]

print(f"=== #7650 SIBLING CENSUS · {RUN} · fetched {STAMP} ===")
print(f"futures cards on feed: {len(cards)} · with outcome rows: {len(ids) - len(unread)}")
if unread:
    print(f"!! {len(unread)} cards returned NO outcome rows — every count below is "
          f"blind to them: {unread[:20]}")


def gate(field, *, dates):
    return cumulative_outcome_ladder(
        [{"name": n} for n, _ in field], name_key="name", dates=dates
    ) is not None


def divisor(field, *, dates):
    """`_feed_display_scale` reproduced on (name, probability) pairs.

    Reproduced rather than imported because the shipped function reads ORM
    attributes off objects this census does not have; the arithmetic below is
    the same arithmetic, and `test_the_census_divisor_matches_the_shipped_one`
    in the guard file pins the two together on the specimens.
    """
    if gate(field, dates=dates):
        return 1.0
    displayed = [p for _, p in field[:3] if p]
    if not displayed:
        return 1.0
    threshold = 1.01 if len(displayed) == 2 else 1.05
    total = sum(p for _, p in field if p)
    return 1.0 if (total <= threshold or total > 2.0) else total


def drop_verdict(field, *, dates):
    """`(rungs dropped, field collapses)` — sites 2 and 3, on one read.

    `incoherent_ladder_verdict` is imported, not restated: it is the function
    both `drop_incoherent_ladder_outcomes` and `ladder_treatment_collapsed`
    call, so measuring it measures exactly what those two will do.
    """
    incoherent, priced = _verdict_with_dates(list(field), dates)
    collapses = bool(incoherent) and (priced - len(incoherent) < LADDER_MIN_DRAWN_RUNGS)
    return len(incoherent), collapses


def _verdict_with_dates(items, dates):
    """`incoherent_ladder_verdict` under a CHOSEN grammar width.

    The flag is injected by overriding the ONE symbol `outcome_display` imported,
    and restored in a `finally` so a raising field cannot leave the module
    widened for the rest of the run. The override wins over whatever the shipped
    call site passes, which is what lets this script take BOTH sides of the
    before/after on a tree that has already been wired — re-run it after the
    merge and it still reproduces (it did, 03:00Z, same 5 fields).
    """
    real = outcome_display.cumulative_outcome_ladder
    outcome_display.cumulative_outcome_ladder = (
        lambda rows, **kw: real(rows, **{**kw, "dates": dates})
    )
    try:
        return incoherent_ladder_verdict(
            items, lambda item: item[0], lambda item: item[1]
        )
    finally:
        outcome_display.cumulative_outcome_ladder = real


flipped, unchanged_gate = [], 0
for market_id in ids:
    field = legs[market_id]
    if len(field) < 2:
        continue
    off, on = gate(field, dates=False), gate(field, dates=True)
    if off == on:
        unchanged_gate += 1
        # THE CONTROL. A field the widening does not flip must be identical at
        # every site; if this ever prints, the date grammar is not additive.
        if (divisor(field, dates=False) != divisor(field, dates=True)
                or drop_verdict(field, dates=False) != drop_verdict(field, dates=True)):
            print(f"!! CONTROL BROKEN id={market_id}: gate unchanged but a consumer moved")
        continue
    if off and not on:
        print(f"!! id={market_id} was a ladder and the widening UN-made it — impossible, read the grammar")
    d_off, d_on = divisor(field, dates=False), divisor(field, dates=True)
    drop_off, drop_on = drop_verdict(field, dates=False), drop_verdict(field, dates=True)
    leader = max((p, n) for n, p in field if p is not None)[1] if any(
        p is not None for _, p in field) else None
    raw = dict((n, p) for n, p in field).get(leader)
    flipped.append({
        "id": market_id, "name": cards[market_id], "legs": len(field),
        "divisor_before": round(d_off, 4), "divisor_after": round(d_on, 4),
        "leader": leader, "raw": raw,
        "shown_before": None if raw is None else round(raw / d_off, 4),
        "shown_after": None if raw is None else round(raw / d_on, 4),
        "pts": None if raw is None else round((raw / d_on - raw / d_off) * 100, 1),
        "rungs_dropped_before": drop_off[0], "rungs_dropped_after": drop_on[0],
        "collapses_before": drop_off[1], "collapses_after": drop_on[1],
        "copy": copy.get(market_id, {}),
        "names": [n for n, _ in field],
    })

print(f"\nfields whose LADDER VERDICT the widening flips: {len(flipped)} "
      f"(unchanged: {unchanged_gate})")

print("\n--- SITE 1 · THE DIVISOR (the ship) ---")
for row in sorted(flipped, key=lambda r: -abs(r["pts"] or 0)):
    print(f"  {row['pts'] if row['pts'] is not None else 0:6.1f}pt  id={row['id']:9} "
          f"divisor {row['divisor_before']:.3f} -> {row['divisor_after']:.3f}  "
          f"'{str(row['leader'])[:26]}' {row['shown_before']} -> {row['shown_after']}  "
          f"{row['name']}")

print("\n--- SITES 2+3 · THE INCOHERENT-RUNG DROP (NOT the ship) ---")
moved = [r for r in flipped
         if r["rungs_dropped_before"] != r["rungs_dropped_after"]
         or r["collapses_before"] != r["collapses_after"]]
print(f"  fields whose drawn bars change: {len(moved)} of {len(flipped)}")
for row in moved:
    print(f"    id={row['id']:9} rungs dropped {row['rungs_dropped_before']} -> "
          f"{row['rungs_dropped_after']} · collapses {row['collapses_before']} -> "
          f"{row['collapses_after']}  {row['name']}")
collapsing = [r for r in flipped if r["collapses_after"]]
print(f"  fields the widening would COLLAPSE (heatmap deleted): {len(collapsing)} "
      f"{[r['id'] for r in collapsing]}")

print("\n--- SITE 4 · THE LEADER COPY (NOT the ship) ---")
print(f"  fields whose `leader_is_ladder_rung` flips False -> True: {len(flipped)}")
with_copy = [r for r in flipped if r["copy"].get("leader_derived")]
print(f"  ...of which carry leader-derived copy TODAY (so a reader sees the "
      f"suppression): {len(with_copy)} {[r['id'] for r in with_copy]}")
for row in flipped:
    print(f"    id={row['id']:9} headline={row['copy'].get('headline')!r} "
          f"reasons={row['copy'].get('reasons')}")

out = os.path.join(os.path.dirname(__file__), f"{RUN}-sibling-census-{STAMP[11:16].replace(':', '')}Z.json")
with open(out, "w") as handle:
    json.dump({"run": RUN, "fetched": STAMP, "cards": len(cards),
               "unread": unread, "flipped": flipped,
               "gate_unchanged": unchanged_gate}, handle, indent=1)
print(f"\nbanked -> {out}")

if unread:
    sys.exit(f"\nVERDICT: PARTIAL — {len(unread)} cards had no outcome rows. "
             f"The flip counts are a FLOOR, not a count.")
print("\nVERDICT: COMPLETE — every futures card on the feed was read.")
