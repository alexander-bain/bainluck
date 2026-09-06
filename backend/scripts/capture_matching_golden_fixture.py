#!/usr/bin/env python3
"""Capture the inputs behind MATCHING-GOLDEN-2026-09-02.json into a CI fixture (#2706).

WHY A FIXTURE AND NOT A LIVE CHECK. The golden set is 709 adjudicated pairs
(``ARTIFACT-M-20260902-A``): 159 say *"this market belongs on this event"* and
550 say *"this market belongs on no event"*. Both were adjudicated against the
production database, and CI has no production database. So a CI test can only be
honest if it carries the INPUTS the matcher would have seen — the market row AND
the candidate events its own search would have surfaced. Without the candidates
the test is vacuous twice over: a positive pair with one event on offer proves
nothing about a chooser, and a negative pair with no events on offer proves
nothing about restraint.

HOW THE CANDIDATE SET IS BUILT. Not by hand and not by "the correct event plus
some decoys". This script runs the matcher's OWN parse
(``extract_matchup_with_ticker_fallback``) and its OWN search-term expansion
(``_expand_team_search_terms``) for each market, then asks production for the
events those terms select inside the matcher's own time window. What comes back
is the candidate set the matcher really faced. If the matcher's parser or its
expansion changes, this file must be re-captured — which is a feature: the
fixture is only valid against the parser that built it, and the CI test asserts
that provenance.

WHAT IT WRITES: ``backend/tests/fixtures/matching_golden_inputs.json``.

    python3 scripts/capture_matching_golden_fixture.py \\
        --golden ~/bainluck/.claude/handoff/MATCHING-GOLDEN-2026-09-02.json

Needs ``BAINLUCK_API`` + ``ADMIN_TOKEN`` (``source ~/.claude/.env``). The output
is checked in, so CI never touches the network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "matching_golden_inputs.json"

MARKET_CHUNK = 120
#: Markets per UNION ALL request. Each contributes its own ILIKE block, so this
#: trades request count against per-request cost; 6 keeps every page under the
#: db-query row path's hard 10s bound.
CANDIDATE_BATCH = 6
#: Candidates kept per market, and it MUST equal the matcher's own limit —
#: `test_golden_capture_cap_matches_production_3564.py` fails if the two drift.
#:
#: This was 10 while the matcher took 20 (#3564). The old note beside it said so
#: out loud and treated it as harmless truncation "of the rows it would have
#: scored last". It is not harmless, because the cap does not just shorten the
#: candidate list — it changes the QUESTION the fixture asks. 327 of 709 pairs
#: sit exactly at the cap, so for 46% of the corpus the matcher is handed a
#: different population than production hands it, and which rows survive depends
#: on what production had ingested at capture time. Measured across two captures
#: four days apart: of the 207 pairs at the cap in both, the candidate id set
#: changed in 141 (68%), and of 69 regressions, 40 were at the cap in both with
#: not one keeping its candidate set. A ratchet whose question moves is not a
#: ratchet.
#:
#: NOTE for whoever re-captures (this ship does not): doubling the rows per
#: block also doubles what each UNION ALL page returns, 6*10+10=70 -> 6*20+10=130.
#: Both are far under db-query's 1,000-row page cap, and the cost here is the
#: per-block ILIKE scan rather than the rows returned, so `CANDIDATE_BATCH` is
#: deliberately left at 6 rather than halved on a guess. Watch the 10s row-path
#: bound on the first real run and lower the batch if a page times out.
MAX_CANDIDATES = 20


def db_query(sql: str, limit: int = 1000) -> list[list]:
    # No timeout_ms: db-query only accepts it with explain:true, and the row
    # path is hard-bounded at 10s regardless. Batches are sized to fit under it.
    api = os.environ["BAINLUCK_API"].rstrip("/")
    token = os.environ["ADMIN_TOKEN"]
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = urllib.request.Request(
        f"{api}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read())
            if "rows" not in payload:
                raise RuntimeError(f"db-query refused: {payload}")
            if payload.get("truncated"):
                raise RuntimeError(f"truncated at {limit} rows — chunk smaller")
            return payload["rows"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            last = f"{exc} :: {detail}"
            print(f"  retry {attempt + 1} after {last}", file=sys.stderr)
            time.sleep(4)
        except Exception as exc:
            last = exc
            print(f"  retry {attempt + 1} after {exc}", file=sys.stderr)
            time.sleep(4)
    raise RuntimeError(f"db-query failed after 3 attempts: {last}")


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def market_search_plan(market: dict):
    """The matcher's own parse + expansion + window, for one market.

    Imported from the task module deliberately: a second copy of the window
    arithmetic here is how ``match-trace`` drifted out of agreement with the
    matcher it claims to explain.
    """
    from app.tasks.prediction_market_matching import (
        _escape_like, _expand_team_search_terms,
    )
    from app.utils.prediction_market_matching import (
        MAX_TIME_DELTA, extract_game_date_from_ticker,
        extract_matchup_with_ticker_fallback,
    )
    from app.tasks.prediction_market_matching import ticker_start_utc

    matchup = extract_matchup_with_ticker_fallback(
        market["name"], external_id=market["external_id"]
    )
    if not matchup:
        return None, [], None, None

    game_date = (
        extract_game_date_from_ticker(market["external_id"])
        if market["source"] == "kalshi" else None
    )
    ticker_start = (
        ticker_start_utc(game_date)
        if game_date and market["source"] == "kalshi" else None
    )
    commence = market.get("commence_time")
    if isinstance(commence, str):
        commence = datetime.fromisoformat(commence.replace("Z", "+00:00"))
    reference = ticker_start or game_date or commence
    if reference is None:
        return matchup, [], None, None
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    if game_date:
        if ticker_start is not None or game_date.hour or game_date.minute:
            start, end = reference - timedelta(hours=3), reference + timedelta(hours=3)
        else:
            start, end = reference - timedelta(hours=6), reference + timedelta(hours=30)
    elif market["source"] == "kalshi":
        start, end = reference - timedelta(days=7), reference + timedelta(days=7)
    else:
        start, end = reference - MAX_TIME_DELTA, reference + MAX_TIME_DELTA

    # The adjudicated answer can sit outside the matcher's window (that IS
    # failure class c). Widen the CAPTURE so the fixture holds the event the
    # golden set names; the matcher's real window is recorded separately and the
    # test re-derives it. Capturing only what the current window admits would
    # bake today's bug into tomorrow's baseline.
    cap_start, cap_end = start - timedelta(days=4), end + timedelta(days=4)

    terms = []
    for team in [matchup.team_a] + ([matchup.team_b] if matchup.team_b else []):
        for t in _expand_team_search_terms(team):
            if t and t not in terms:
                terms.append(t)
    patterns = [f"%{_escape_like(t)}%" for t in terms]
    return matchup, patterns, cap_start, cap_end


#: Corrections to the dated artifact's adjudications. See the file's own
#: ``why_this_file_exists`` — the short version is that
#: ``MATCHING-GOLDEN-2026-09-02.json`` is never rewritten, and hand-editing the
#: captured fixture instead would survive exactly until the next re-capture,
#: which re-derives ``correct_event_id`` from the artifact.
AMENDMENTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests" / "fixtures" / "matching_golden_adjudication_amendments.json"
)


def apply_adjudication_amendments(golden: list[dict]) -> list[int]:
    """Rewrite adjudicated answers in place, BEFORE any pair is built.

    Before, not after, because two of the fixture's own guarantees are derived
    from ``correct_event_id``: the adjudicated event is fetched even when the
    matcher's search would not surface it, and ``search_surfaced_the_answer`` is
    computed against the candidate list. An amendment applied afterwards would
    leave both describing the OLD answer, which is the quiet kind of wrong.

    ``was`` is checked, not assumed. If the artifact no longer says what the
    amendment claims it said, this raises: an amendment is a correction to a
    specific recorded answer, and applying it blind to a pair that has moved
    underneath it would be laundering, not correcting.
    """
    if not AMENDMENTS_PATH.exists():
        return []
    doc = json.loads(AMENDMENTS_PATH.read_text())
    by_market = {int(p["market_id"]): p for p in golden}
    applied: list[int] = []
    for a in doc.get("amendments", []):
        mid = int(a["market_id"])
        pair = by_market.get(mid)
        if pair is None:
            # Not an error: --limit truncates the set, and a market can leave
            # the artifact. Silence would be, so it says so.
            print(f"  amendment for market {mid}: not in this golden set, skipped")
            continue
        current = pair.get("correct_event_id")
        current = int(current) if current is not None else None
        was = a["was"]
        was = int(was) if was is not None else None
        if current != was:
            raise SystemExit(
                f"amendment for market {mid} says the artifact adjudicated "
                f"{was!r}, but it adjudicates {current!r}. The pair moved under "
                f"the amendment — re-check the evidence before re-capturing."
            )
        pair["correct_event_id"] = a["now"]
        applied.append(mid)
    return applied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=0, help="debug: first N pairs")
    args = ap.parse_args()

    golden = json.loads(Path(args.golden).expanduser().read_text())
    if args.limit:
        golden = golden[:args.limit]
    print(f"golden pairs: {len(golden)}")

    amended = apply_adjudication_amendments(golden)
    print(f"adjudication amendments applied: {len(amended)}")

    market_ids = sorted({int(p["market_id"]) for p in golden})
    markets: dict[int, dict] = {}
    for i in range(0, len(market_ids), MARKET_CHUNK):
        ids = ",".join(str(x) for x in market_ids[i:i + MARKET_CHUNK])
        for r in db_query(
            "SELECT id, source, external_id, name, category, llm_sport_category, "
            "commence_time, group_type, group_id, status, event_id "
            f"FROM futures_markets WHERE id IN ({ids})",
            limit=MARKET_CHUNK + 10,
        ):
            markets[int(r[0])] = {
                "id": int(r[0]), "source": r[1], "external_id": r[2],
                "name": r[3], "category": r[4], "llm_sport_category": r[5],
                "commence_time": r[6], "group_type": r[7], "group_id": r[8],
                "status": r[9],
                "event_id_at_capture": int(r[10]) if r[10] is not None else None,
            }
        print(f"  markets {len(markets)}/{len(market_ids)}")

    # ── Candidates, via the matcher's own terms and window ──────────────
    plans: dict[int, tuple] = {}
    for mid, market in markets.items():
        matchup, patterns, start, end = market_search_plan(market)
        plans[mid] = (matchup, patterns, start, end)

    events: dict[int, dict] = {}
    candidates_of: dict[int, list[int]] = {}

    searchable = [
        mid for mid, (mu, pats, s, e) in plans.items() if mu and pats and s and e
    ]
    print(f"  parseable markets with a window: {len(searchable)}/{len(markets)}")

    for i in range(0, len(searchable), CANDIDATE_BATCH):
        batch = searchable[i:i + CANDIDATE_BATCH]
        blocks = []
        for mid in batch:
            _mu, pats, start, end = plans[mid]
            ors = " OR ".join(
                f"e.home_team_name ILIKE {sql_str(p)} OR "
                f"e.away_team_name ILIKE {sql_str(p)}"
                for p in pats
            )
            blocks.append(
                f"(SELECT {mid} AS mid, e.id, e.home_team_name, e.away_team_name, "
                f"e.commence_time, e.status, e.external_id, e.sport_id, s.key "
                "FROM events e LEFT JOIN sports s ON s.id = e.sport_id "
                f"WHERE ({ors}) AND e.commence_time BETWEEN "
                f"{sql_str(start.isoformat())}::timestamptz AND "
                f"{sql_str(end.isoformat())}::timestamptz "
                f"ORDER BY e.commence_time LIMIT {MAX_CANDIDATES})"
            )
        # Wrapped in an outer SELECT: the read guard requires the statement to
        # START with SELECT or WITH, and a UNION ALL of parenthesised blocks
        # starts with "(".
        rows = db_query(
            "SELECT * FROM (" + " UNION ALL ".join(blocks) + ") u",
            limit=CANDIDATE_BATCH * MAX_CANDIDATES + 10,
        )
        for r in rows:
            mid = int(r[0])
            eid = int(r[1])
            events[eid] = {
                "id": eid, "home_team_name": r[2], "away_team_name": r[3],
                "commence_time": r[4], "status": r[5], "external_id": r[6],
                "sport_id": int(r[7]) if r[7] is not None else None,
                # The field is "sport", not "sport_key". gitleaks' generic-api-key
                # rule fires on a JSON key ending in _key whose value is a long
                # token, and every Odds API sport key looks like one
                # ("cricket_international_t20"). They are public league
                # identifiers, not credentials — renaming the FIELD keeps the
                # secret scanner honest without a repo-wide allowlist or a
                # SHA-pinned .gitleaksignore entry that a rebase would break.
                "sport": r[8],
            }
            candidates_of.setdefault(mid, []).append(eid)
        print(f"  candidates {min(i + CANDIDATE_BATCH, len(searchable))}/{len(searchable)}")

    # The adjudicated event must always be IN the fixture, even when the
    # matcher's own search would not surface it — that gap is the finding, and
    # a fixture that omitted it could never record the pair going green.
    wanted = {
        int(p["correct_event_id"]) for p in golden
        if p.get("correct_event_id") is not None
    } - set(events)
    for i in range(0, len(sorted(wanted)), MARKET_CHUNK):
        ids = ",".join(str(x) for x in sorted(wanted)[i:i + MARKET_CHUNK])
        for r in db_query(
            "SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time, "
            "e.status, e.external_id, e.sport_id, s.key "
            "FROM events e LEFT JOIN sports s ON s.id = e.sport_id "
            f"WHERE e.id IN ({ids})",
            limit=MARKET_CHUNK + 10,
        ):
            events[int(r[0])] = {
                "id": int(r[0]), "home_team_name": r[1], "away_team_name": r[2],
                "commence_time": r[3], "status": r[4], "external_id": r[5],
                "sport_id": int(r[6]) if r[6] is not None else None,
                "sport": r[7],
            }
    print(f"  adjudicated events not surfaced by search: {len(wanted)}")

    pairs, dropped = [], {"market_gone": 0, "event_gone": 0}
    for p in golden:
        mid = int(p["market_id"])
        raw_eid = p.get("correct_event_id")
        eid = int(raw_eid) if raw_eid is not None else None
        market = markets.get(mid)
        if market is None:
            dropped["market_gone"] += 1
            continue
        if eid is not None and eid not in events:
            dropped["event_gone"] += 1
            continue

        cand = list(dict.fromkeys(candidates_of.get(mid, [])))
        if eid is not None and eid not in cand:
            cand.append(eid)
        pairs.append({
            "market_id": mid,
            "correct_event_id": eid,
            "failure_class": p.get("failure_class"),
            "title": p.get("title"),
            "venue": p.get("venue"),
            "note": p.get("note"),
            "market": market,
            "events": [events[c] for c in cand],
            "search_surfaced_the_answer": eid is None or eid in candidates_of.get(mid, []),
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "source_file": Path(args.golden).name,
        # Recorded in the header so a reader of the fixture can see that its
        # adjudications are not verbatim the artifact's, and which ones are not.
        "amended_market_ids": sorted(amended),
        "golden_pairs": len(golden),
        "captured_pairs": len(pairs),
        "positive_pairs": sum(1 for p in pairs if p["correct_event_id"] is not None),
        "negative_pairs": sum(1 for p in pairs if p["correct_event_id"] is None),
        "dropped": dropped,
        "pairs": pairs,
    }, indent=1, sort_keys=True) + "\n")
    print(f"wrote {out} — {len(pairs)} pairs, dropped {dropped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
