#!/usr/bin/env python3
"""Census markets settled against a wrong-scored or absorbed event (339T item 3, #1779/#1798).

CENSUS ONLY. This script never writes, and it must never learn to. Its output is a
list Alex adjudicates by MC; the standing hazard is gotcha #21 -- a bulk ``is_winner``
reset has burned this project before, and the class of damage is unrecoverable because
the prior grade is not stored anywhere once overwritten.

WHAT MAKES A GRADE CONTAMINATED, precisely
------------------------------------------
Not every market hanging off a defective event is mis-graded, and saying so would be
the same crying-wolf failure the Grid Sentinel was built to end. The question is
whether the grade was DERIVED FROM the thing that is wrong:

  * ``api_settlement`` / ``clob_*`` -- the VENUE settled its own market. Our score
    was never an input, so a wrong score cannot have corrupted the grade. These are
    reported as ATTRIBUTION-only exposure when the event is absorbed (the grade is
    right, the event it is attached to is the wrong game), and as CLEAN otherwise.
  * ``game_score`` / ``poly_total_score`` -- computed from ``events.home_score`` /
    ``events.away_score``. A wrong score is a wrong grade, directly.
  * ``box_score`` / ``box_score_bound`` / ``scoring_plays`` -- computed from
    ``events.box_score_data``. Not corrupted by a wrong SCORE, but wholly corrupted
    by ABSORPTION, because then the box score belongs to a different game.

So the defect class and the resolution source have to be crossed. A single blended
"contaminated markets" number would be wrong in both directions at once.

TWO DEFECTS, TWO LEFT EDGES (Alex ruling 2, 2026-08-12)
-------------------------------------------------------
Absorption (MISDATED / REKEY) is governed by the 2026-05-22 ``_MATCH_WINDOW`` widening
(``49da8ceb``). The March-April binding damage belongs to #1798 and is older. This
script reports per defect class and never sums them into one figure.

Usage:
    python3 scripts/census_settlement_contamination.py --findings /tmp/q339t --out report.md

``--findings`` is a directory of ``chunk*.json`` emitted by
``reconcile_mlb_schedule.py --json``. Requires BAINLUCK_API and ADMIN_TOKEN
(``source ~/.claude/.env``).
"""

from __future__ import annotations

import argparse
import ast
import glob
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# Sources computed from events.home_score / events.away_score. A wrong score is a
# wrong grade for these, full stop.
SCORE_DERIVED = ("game_score", "poly_total_score")

# Sources computed from events.box_score_data. Immune to a wrong final score;
# fully corrupted when the row is a different game than it claims.
BOXSCORE_DERIVED = ("box_score", "box_score_bound", "scoring_plays")

# The venue's own settlement. Never reads our event data -- the GRADE is sound even
# on a defective row. Listed so it is explicitly excluded rather than forgotten.
VENUE_SETTLED = (
    "api_settlement", "clob_authoritative", "clob_field_repair",
    "clob_never_graded", "clob_ordinal", "datagolf_settlement", "settlement_sync",
)


def db_query(sql: str, limit: int = 1000) -> list:
    api, token = os.environ.get("BAINLUCK_API"), os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        sys.exit("BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env)")
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = urllib.request.Request(
        f"{api}/api/admin/db-query", data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
    # gotcha #40: JSONB comes back as a Python repr, so json.loads alone reads {}.
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = ast.literal_eval(raw)
    rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
    if len(rows) >= limit:
        # gotcha: db-query silently truncates at the cap. A truncated census
        # UNDERSTATES contamination, which is the direction that gets someone hurt.
        sys.exit(f"REFUSING TO REPORT: {len(rows)} rows at the {limit} cap -- narrow the query.")
    return rows


from app.utils.market_identity import (  # ONE implementation — see that module
    eastern_game_date as _eastern_date,
    market_identity_disputed,
    ticker_game_date,
)


def _split_label(label: str) -> tuple[str, str]:
    """'Away Team @ Home Team 2026-08-11 23:07Z' -> ('Away Team', 'Home Team').

    Returns ('', '') when the label is not that shape, which makes the spread
    recomputer refuse the row rather than match a team token against an empty string.
    """
    if " @ " not in (label or ""):
        return "", ""
    away, rest = label.split(" @ ", 1)
    # Trim the trailing ' YYYY-MM-DD HH:MMZ' the reconcile script appends.
    home = re.sub(r"\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}Z$", "", rest)
    return away.strip(), home.strip()


def load_findings(directory: str) -> dict:
    """Fold the per-chunk reconcile output into one per-event defect map."""
    events: dict[int, dict] = {}
    for path in sorted(glob.glob(os.path.join(directory, "chunk*.json"))):
        chunk = json.load(open(path))
        for row in chunk["wrong_score"]:
            events.setdefault(row["event_id"], {"classes": set()}).update(
                {"label": row["label"], "ours": row["ours"], "truth": row["truth"],
                 "status_ours": row["status_ours"], "espn_id": row["espn_id"]}
            )
            events[row["event_id"]]["classes"].add("WRONG_SCORE")
        for row in chunk["stuck_live"]:
            e = events.setdefault(row["event_id"], {"classes": set()})
            e.setdefault("label", row["label"])
            e.setdefault("ours", row["ours"])
            e.setdefault("truth", row["truth"])
            e["classes"].add("STUCK_LIVE")
        for row in chunk["misdated"]:
            e = events.setdefault(row["event_id"], {"classes": set()})
            e["drift_hours"] = row["drift_hours"]
            e.setdefault("label", f"espn={row['espn_id']}")
            e["classes"].add("MISDATED")
        for row in chunk["missing_rekey"]:
            e = events.setdefault(row["impostor_event_id"], {"classes": set()})
            e["wears_id_of"] = row["label"]
            e["holds_espn_id"] = row["impostor_holds_espn_id"]
            e.setdefault("label", row["label"])
            e["classes"].add("REKEY_IMPOSTOR")
    return events


def score_verdict(ours, truth) -> str:
    """What the wrong score actually breaks -- winner, total, or nothing.

    The distinction is the whole point of the census. A 6-2 recorded as 9-2 grades
    every moneyline correctly and every total wrongly; recorded as 2-6 it grades the
    moneyline BACKWARDS. Those need different adjudications, so they get different
    labels rather than one 'wrong score' bucket.
    """
    if not ours or not truth or None in ours or None in truth:
        return "UNSCORABLE"
    (oa, oh), (ta, th) = ours, truth
    if (oa, oh) == (0, 0) and (ta, th) != (0, 0):
        # We never captured a score at all. Anything graded off this did not grade
        # against a WRONG result; it graded against NO result.
        return "NEVER_SCORED"
    ow = "away" if oa > oh else ("home" if oh > oa else "tie")
    tw = "away" if ta > th else ("home" if th > ta else "tie")
    if ow != tw:
        return "WINNER_FLIP"
    if (oa + oh) != (ta + th):
        return "TOTAL_WRONG"
    return "MARGIN_ONLY"


_LINE_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _norm(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def recompute(market_name: str, outcome_name: str, away: int, home: int,
              away_team: str, home_team: str) -> bool | None:
    """Re-grade one outcome from a score pair. ``None`` means 'cannot decide'.

    Fail-closed on purpose. This function's output goes on a list a human uses to
    change ``is_winner`` on real settled markets, so a confident wrong answer is far
    worse than an admission. Anything whose shape is not recognised, or whose team
    token cannot be tied to exactly one side, returns None and is reported as
    UNRESOLVED rather than folded into either verdict.
    """
    total = away + home
    mname, oname = market_name or "", outcome_name or ""

    # Polymarket totals: "... : O/U 11.5" with Over/Under outcomes.
    if "o/u" in mname.lower():
        line_match = _LINE_RE.search(mname.lower().split("o/u", 1)[1])
        if not line_match:
            return None
        line = float(line_match.group(1))
        if _norm(oname) == "over":
            return total > line
        if _norm(oname) == "under":
            return total < line
        return None

    # Kalshi totals: outcome "Over 8.5 runs scored".
    if oname.lower().startswith("over ") and "run" in oname.lower():
        line_match = _LINE_RE.search(oname)
        if not line_match:
            return None
        return total > float(line_match.group(1))

    # Kalshi spreads: outcome "<Team> wins by over 2.5 runs".
    if "wins by over" in oname.lower():
        line_match = _LINE_RE.search(oname.lower().split("wins by over", 1)[1])
        if not line_match:
            return None
        line = float(line_match.group(1))
        token = _norm(oname.lower().split("wins by over", 1)[0])
        if not token:
            return None
        # Tie the token to exactly ONE side, or refuse. Kalshi abbreviates
        # inconsistently ("Los Angeles D", "Mariners"), so match on containment in
        # either direction -- but an ambiguous or absent hit must not be guessed.
        na, nh = _norm(away_team), _norm(home_team)
        hit_away = token in na or na in token
        hit_home = token in nh or nh in token
        if hit_away == hit_home:  # both or neither -> ambiguous
            return None
        margin = (away - home) if hit_away else (home - away)
        return margin > line

    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--findings", required=True, help="dir of chunk*.json from reconcile --json")
    ap.add_argument("--out", help="write the markdown evidence report here")
    args = ap.parse_args()

    events = load_findings(args.findings)
    for ev in events.values():
        ev["verdict"] = score_verdict(ev.get("ours"), ev.get("truth")) \
            if "WRONG_SCORE" in ev["classes"] or "STUCK_LIVE" in ev["classes"] else "N/A"
        ev["away_team"], ev["home_team"] = _split_label(ev.get("label", ""))
    print(f"suspect events: {len(events)}")

    srcs = ",".join(f"'{s}'" for s in SCORE_DERIVED + BOXSCORE_DERIVED)

    def fetch(event_ids: list[int]) -> list:
        """Fetch detail rows, splitting the batch rather than truncating it.

        db-query caps at 1000 rows and truncates SILENTLY; the whole population here
        is ~5.5K, so a single query cannot see it. Bisecting on the event list keeps
        the refuse-on-cap guard intact -- a batch that still hits the cap at one
        event is a real error and is allowed to raise, because at that point the
        truncation is not something a smaller batch can fix.
        """
        inlist = ",".join(str(i) for i in event_ids)
        sql = (
            # NB: the outcome's label column is futures_outcomes.name, NOT outcome_name.
            # fm.external_id (col 9) is the MARKET's own identity claim, added queue 362.
            # Without it this census could only ask whether the EVENT was disputed, and
            # an accurately-identified event carrying a NEIGHBOURING game's market read
            # as "identity certain" -- see `market_identity_disputed`.
            "SELECT fm.event_id, fm.id, fm.name, fo.id, fo.name, fo.is_winner, "
            "fo.resolution_source, fo.calibration_probability, fm.source, "
            "fm.external_id, ev.commence_time "
            "FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id = fm.id "
            "JOIN events ev ON ev.id = fm.event_id "
            f"WHERE fm.event_id IN ({inlist}) AND fo.resolution_source IN ({srcs}) "
            "ORDER BY fm.event_id, fm.id, fo.id"
        )
        if len(event_ids) == 1:
            return db_query(sql)
        try:
            return db_query(sql)
        except SystemExit:
            mid = len(event_ids) // 2
            return fetch(event_ids[:mid]) + fetch(event_ids[mid:])

    rows = fetch(sorted(events))
    print(f"detail rows fetched: {len(rows)}")

    by_event = defaultdict(list)
    for r in rows:
        by_event[r[0]].append(r)

    # Cross defect class x verdict x source. Never one blended number (ruling 2).
    matrix: dict[tuple, dict] = defaultdict(lambda: {"outcomes": 0, "markets": set(), "events": set()})
    for ev_id, recs in by_event.items():
        ev = events[ev_id]
        for cl in sorted(ev["classes"]):
            for r in recs:
                key = (cl, ev["verdict"], r[6])
                matrix[key]["outcomes"] += 1
                matrix[key]["markets"].add(r[1])
                matrix[key]["events"].add(ev_id)

    lines = []
    def out(s=""):
        print(s)
        lines.append(s)

    out()
    out(f"{'defect':16}{'verdict':14}{'source':20}{'outcomes':>9}{'markets':>9}{'events':>8}")
    out("-" * 76)
    for key in sorted(matrix):
        cl, verdict, src = key
        m = matrix[key]
        out(f"{cl:16}{verdict:14}{src:20}{m['outcomes']:>9}{len(m['markets']):>9}{len(m['events']):>8}")

    out()
    out(f"UNION, no double count: {len(rows)} outcomes on "
        f"{len({r[1] for r in rows})} markets across {len(by_event)} events")

    # ── The re-grade shortlist ──────────────────────────────────────
    # Every score-derived grade on an event whose own score is wrong is SUSPECT.
    # Only the subset that actually re-grades differently is WRONG. Conflating the
    # two would hand Alex a 400-row adjudication where the real list is far shorter,
    # and every no-op re-grade on that list is pure downside: gotcha #21 damage risk
    # bought for a value that does not change.
    candidates = [
        (ev_id, r) for ev_id, recs in by_event.items() for r in recs
        if r[6] in SCORE_DERIVED
        and events[ev_id]["verdict"] in ("WINNER_FLIP", "TOTAL_WRONG", "MARGIN_ONLY")
    ]
    confirmed, agrees, unresolved = [], [], []
    for ev_id, r in candidates:
        ev = events[ev_id]
        away_team, home_team = ev.get("away_team", ""), ev.get("home_team", "")
        should = recompute(r[2], r[4], ev["truth"][0], ev["truth"][1], away_team, home_team)
        if should is None:
            unresolved.append((ev_id, r))
        elif bool(r[5]) != should:
            confirmed.append((ev_id, r, should))
        else:
            agrees.append((ev_id, r))

    out()
    out("### Re-grade triage — recomputed against truth, per row")
    out()
    out(f"- **CONFIRMED WRONG** — {len(confirmed)} outcomes on "
        f"{len({r[1] for _, r, _ in confirmed})} markets, "
        f"{len({e for e, _, _ in confirmed})} events. Recomputing the grade from the "
        "TRUE score yields a different `is_winner`.")
    out(f"- **AGREES ANYWAY** — {len(agrees)} outcomes. Derived from a wrong score but "
        "the grade is still correct (the error did not cross the line). "
        "**Do not re-grade these** — the write would be a no-op carrying real risk.")
    out(f"- **UNRESOLVED** — {len(unresolved)} outcomes on "
        f"{len({r[1] for _, r in unresolved})} markets. The recomputer could not tie the "
        "outcome to a line or a side and refuses to guess. **These need a human read.**")
    out()
    out("The recomputer handles Polymarket `O/U N.5`, Kalshi `Over N.5 runs scored`, and "
        "Kalshi `<Team> wins by over N.5 runs`. Anything else returns UNRESOLVED by design.")

    # ── Identity-certain vs identity-disputed ───────────────────────
    # A row that is ALSO a REKEY_IMPOSTOR or MISDATED has a contested identity: it
    # carries game X's provider id while being named and timed like game Y. The
    # "truth" this census pairs it with is game X's -- the game whose id it wears --
    # which is not necessarily the game its markets are about.
    #
    # So a re-grade computed here would be authoritative about the WRONG GAME. The
    # grade cannot be decided before the identity is, which is why this split exists
    # rather than one confirmed list: shipping the blended list would invite exactly
    # the unattended bulk re-grade gotcha #21 warns about, with a truth source that
    # looks impeccable and is pointed at the wrong row.
    def disputed(ev_id: int) -> bool:
        return bool({"REKEY_IMPOSTOR", "MISDATED"} & events[ev_id]["classes"])

    # QUEUE 362 — the second half of the same question. `disputed` asks whether the
    # EVENT's identity is contested; this asks whether the MARKET's is. Both must be
    # certain before a grade is adjudicable, because a grade is a claim about one
    # specific game and either one of them being wrong points it at another.
    # ``commence_time`` travels on the DETAIL ROW (col 10), not in the findings dict —
    # the findings come from the reconcile output, which never carried it, so reading
    # it from there would have made this whole check a silent no-op that reports zero
    # disputes forever and looks exactly like good news.
    def market_disputed(rec) -> bool:
        return market_identity_disputed(rec[9], rec[10])

    tier_a = [c for c in confirmed if not disputed(c[0]) and not market_disputed(c[1])]
    tier_b = [c for c in confirmed if disputed(c[0]) and not market_disputed(c[1])]
    tier_m = [c for c in confirmed if market_disputed(c[1])]

    # The same test applied to the "AGREES ANYWAY" exclusion, which is where the
    # specimen's four silently-wrong rows were hiding. A row agreeing with a grade
    # recomputed from the WRONG GAME's truth is not agreement; it is a coincidence
    # that the exclusion then reads as a reason to leave it alone.
    agrees_market_disputed = [(e, r) for e, r in agrees if market_disputed(r)]

    out()
    out("#### ⚠️ The re-grade list splits on IDENTITY, and that changes what is actionable")
    out()
    out(f"- **Tier A — identity certain, grade provably wrong: {len(tier_a)} outcomes on "
        f"{len({r[1] for _, r, _ in tier_a})} markets, {len({e for e, _, _ in tier_a})} events.** "
        "The row carries the right game's id; only its score is wrong. Truth is decidable "
        "today, so these are adjudicable now.")
    out(f"- **Tier B — identity DISPUTED: {len(tier_b)} outcomes on "
        f"{len({r[1] for _, r, _ in tier_b})} markets, {len({e for e, _, _ in tier_b})} events.** "
        "The event is also a re-key impostor or misdated, so the truth game paired with it "
        "here is the game whose id it *wears*. **Not adjudicable until the re-key lands** — "
        "a re-grade now would be confidently wrong about a different game.")
    out(f"- **Tier M — MARKET identity disputed: {len(tier_m)} outcomes on "
        f"{len({r[1] for _, r, _ in tier_m})} markets, {len({e for e, _, _ in tier_m})} events.** "
        "The event may be perfectly sound; the MARKET's own ticker names a different "
        "game-date than the event it is linked to, so the grade would be computed for "
        "one game from another game's truth. **Not adjudicable until the market→event "
        "link is repaired.**")
    if agrees_market_disputed:
        out(f"- ⚠️ **{len(agrees_market_disputed)} rows inside the AGREES ANYWAY exclusion "
            f"({len({r[1] for _, r in agrees_market_disputed})} markets) sit on a "
            "market-identity dispute.** Their 'agreement' was measured against the wrong "
            "game's truth, so the exclusion is not evidence they are correct. They are "
            "unknown, not fine.")
    out()
    out("**This is the ordering ruling arriving a FOURTH time, and market identity is "
        "identity too.** 339S's gate caught CREATE-vs-REKEY before a backfill could "
        "duplicate rows; Tier B caught event identity before a grade; Tier M catches the "
        "case where the event is right and the MARKET is on a different game. **Identity "
        "must be repaired before a grade can even be computed**, let alone written. The "
        "re-grade is downstream of the repair, not parallel to it.")

    out()
    out("#### Tier A — CONFIRMED WRONG, identity certain (adjudicable now)")
    out()
    if not tier_a:
        out("_(none)_")
    for ev_id in sorted({e for e, _, _ in tier_a}):
        ev = events[ev_id]
        out(f"- **event {ev_id}** — {ev['label']}  ours=`{ev['ours']}` truth=`{ev['truth']}` "
            f"[{ev.get('status_ours')}]  verdict={ev['verdict']}")
        for e2, r, should in tier_a:
            if e2 != ev_id:
                continue
            out(f"    - market {r[1]} ({r[8]}) `{r[2]}` / outcome {r[3]} `{r[4]}` — "
                f"held `is_winner={r[5]}`, truth says `{should}` "
                f"(src={r[6]}, cal_prob={r[7]})")

    out()
    out("#### Tier B — recomputes differently, but identity is disputed (HOLD)")
    out()
    for ev_id in sorted({e for e, _, _ in tier_b}):
        ev = events[ev_id]
        wears = ev.get("wears_id_of", "?")
        out(f"- **event {ev_id}** — {ev['label']}  ours=`{ev['ours']}` truth=`{ev['truth']}` "
            f"[{ev.get('status_ours')}]  verdict={ev['verdict']}  classes={sorted(ev['classes'])}")
        if "REKEY_IMPOSTOR" in ev["classes"]:
            out(f"    - ⚠️ also the impostor row for: {wears} "
                f"(it holds espn_id `{ev.get('holds_espn_id')}`)")
        for e2, r, should in tier_b:
            if e2 != ev_id:
                continue
            out(f"    - market {r[1]} ({r[8]}) `{r[2]}` / outcome {r[3]} `{r[4]}` — "
                f"held `is_winner={r[5]}`, this truth says `{should}` "
                f"(src={r[6]}, cal_prob={r[7]})")

    out()
    out("#### UNRESOLVED — needs a human read")
    out()
    for ev_id in sorted({e for e, _ in unresolved}):
        ev = events[ev_id]
        out(f"- **event {ev_id}** — {ev['label']} ours=`{ev['ours']}` truth=`{ev['truth']}`")
        for e2, r in unresolved:
            if e2 != ev_id:
                continue
            out(f"    - market {r[1]} ({r[8]}) `{r[2]}` / outcome {r[3]} `{r[4]}` "
                f"is_winner={r[5]} src={r[6]}")

    if args.out:
        with open(args.out, "w") as fh:
            fh.write("\n".join(lines))
        print(f"\n[wrote {args.out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
