#!/usr/bin/env python3
"""Q477 — does the per-fixture series table classify PRODUCTION tickers right,
and how many duplicate event rows would it stop?

Two questions, one script, because they share a population.

**Question 1, classification.** `KALSHI_MATCH_SERIES_TO_SPORT_KEY` is a cross
product of league stems and market-type suffixes, so most of what it generates
matches nothing and the entries that matter are the ones sitting next to a
near-miss. Every production series under the declared stems is run through the
real `kalshi_anchor_key()` — not a re-implementation — and printed with its
verdict, so a promotion nobody intended is visible rather than inferred. The
REJECTED `kxucl` stem is censused too: a rejection that leaves no evidence is
indistinguishable from an oversight.

**Question 2, the replay.** Ordering every Kalshi market for these leagues by
`created_at` and stepping the anchor channel forward answers "how many event
rows would exist" on both trees, against the rows production actually holds.
The counterfactual is not a guess about the matcher's name comparison: a market
whose event is `commence_time_source='kalshi_ticker'` MINTED that row, and any
other provenance means the matcher LINKED it to a row that already existed.

Usage:
    python3 scripts/census_kalshi_match_series.py --fetch   # needs ADMIN_TOKEN
    python3 scripts/census_kalshi_match_series.py           # replay the artifact
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.prediction_market_matching import kalshi_game_id  # noqa: E402
from app.utils.provider_anchor_keys import kalshi_anchor_key  # noqa: E402
from app.utils.sport_keys import (  # noqa: E402
    _KALSHI_MATCH_SERIES_LEAGUE_STEMS,
    KALSHI_MATCH_SERIES_TO_SPORT_KEY,
)

#: Outside the repo on purpose. A 1,785-row pull is evidence, not source, and a
#: census that drops an untracked directory into the working tree is how four
#: unrelated artifact dirs rode into a commit on CERT-526. `--fetch` regenerates
#: it; the numbers it produced are in the report.
ARTIFACT = Path(
    os.environ.get("Q477_ARTIFACT", "/tmp/q477_kalshi_match_series.json")
)

#: Censused alongside the declared stems precisely because it is NOT declared.
#: See the block comment on `KALSHI_MATCH_SERIES_TO_SPORT_KEY`.
REJECTED_STEMS = ("kxucl",)

#: The provenance string `_create_event_from_prediction_market` stamps on a row
#: it minted from a ticker. Read from the task module rather than spelled here:
#: a literal copy of a constant is how a census answers 0 for the wrong reason.
from app.tasks.prediction_market_matching import (  # noqa: E402
    _TICKER_DERIVED_COMMENCE_SOURCE as TICKER_DERIVED,
)

CHUNKS = 4


def _db_query(sql: str, limit: int = 1000) -> list[list]:
    base = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not base or not token:
        raise SystemExit("BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env)")
    req = urllib.request.Request(
        f"{base}/api/admin/db-query",
        data=json.dumps({"sql": sql, "limit": limit}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"db-query failed: {exc.read()[:400]!r}\nSQL: {sql}"
        ) from exc
    if payload.get("truncated"):
        raise SystemExit(
            "db-query TRUNCATED — a silent 1000-row cap would make every count "
            "below a floor rather than a measurement. Raise CHUNKS."
        )
    return payload["rows"]


def _stem_predicate(stems, column: str = "external_id") -> str:
    # The column is QUALIFIED by the caller when the statement joins `events`:
    # that table has an `external_id` too, and a bare one reads as ambiguous —
    # which the read guard reports as `invalid_statement`, not as an ambiguity.
    return " OR ".join(f"lower({column}) LIKE '{s}%'" for s in stems)


def fetch() -> dict:
    all_stems = tuple(_KALSHI_MATCH_SERIES_LEAGUE_STEMS) + REJECTED_STEMS
    where = _stem_predicate(all_stems)

    series = _db_query(
        "SELECT split_part(external_id, '-', 1) AS series, count(*) AS n, "
        "min(external_id) AS sample, min(name) AS sample_name "
        f"FROM futures_markets WHERE source = 'kalshi' AND ({where}) "
        "GROUP BY 1 ORDER BY 1"
    )

    # Chunked on a hash of the FIXTURE TOKEN so a fixture's markets can never
    # split across chunks and be counted as two.
    declared = _stem_predicate(
        tuple(_KALSHI_MATCH_SERIES_LEAGUE_STEMS), "fm.external_id"
    )
    markets: list[list] = []
    for chunk in range(CHUNKS):
        markets += _db_query(
            "SELECT fm.external_id, fm.event_id, fm.created_at::text, "
            "e.commence_time_source, e.commence_time::text, "
            "e.home_team_name, e.away_team_name "
            "FROM futures_markets fm "
            "LEFT JOIN events e ON e.id = fm.event_id "
            f"WHERE fm.source = 'kalshi' AND ({declared}) "
            "AND fm.created_at > now() - interval '45 days' "
            "AND mod(abs(hashtext(split_part(fm.external_id, '-', 2))), "
            f"{CHUNKS}) = {chunk} "
            "ORDER BY fm.created_at"
        )

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"series": series, "markets": markets}
    ARTIFACT.write_text(json.dumps(payload, indent=1))
    print(f"wrote {ARTIFACT} — {len(series)} series, {len(markets)} markets")
    return payload


def classify(series_rows) -> int:
    print("=" * 78)
    print("CLASSIFICATION — every production series under the declared stems")
    print("=" * 78)
    promoted, refused, bad = [], [], []
    for name, n, sample, sample_name in series_rows:
        key = kalshi_anchor_key(sample)
        row = (name, n, sample, key.id_kind, key.source_id, sample_name)
        if key.id_kind == "game":
            promoted.append(row)
        else:
            refused.append(row)
        # A promoted series under a stem we did NOT declare is the failure this
        # census exists to catch.
        if key.id_kind == "game" and not any(
            sample.lower().startswith(p) for p in KALSHI_MATCH_SERIES_TO_SPORT_KEY
        ):
            continue  # promoted by the pre-existing game map, not by this table
    for name, n, sample, _kind, source_id, _nm in promoted:
        if any(name.lower().startswith(s) for s in REJECTED_STEMS):
            bad.append((name, source_id))
    print(f"\n  game-level (would anchor a fixture): {len(promoted)}")
    for row in promoted:
        print(f"    {row[0]:<26} n={row[1]:<5} {row[4]}")
    print(f"\n  market-level (unchanged): {len(refused)}")
    for row in refused:
        print(f"    {row[0]:<26} n={row[1]:<5} {row[2]}")
    if bad:
        print("\n  *** A REJECTED STEM WAS PROMOTED ANYWAY ***")
        for name, source_id in bad:
            print(f"    {name} -> {source_id}")
    return len(bad)


def replay(market_rows, *, label: str = "real arrival order", verbose: bool = True) -> int:
    """Step the anchor channel forward over one arrival order.

    **The answer depends on the order and that is not a flaw in the replay, it
    is the mechanism.** `record_anchor` never repoints an incumbent, so within a
    fixture whichever market is processed FIRST decides which row owns the
    anchor. When that is a market the matcher can name-match, the real
    schedule-derived row wins and every sibling joins it; when it is one the
    matcher cannot, a minted twin owns the key and the real row cannot take it
    back. The caller therefore runs this twice — the real `created_at` order and
    its exact reverse — and the pair is a measured BAND, not a point estimate.
    """
    if verbose:
        print()
        print("=" * 78)
        print(f"REPLAY ({label}) — event rows per fixture, before vs after")
        print("=" * 78)

    token_mismatch = 0
    before: dict[str, set] = defaultdict(set)
    after: dict[str, set] = defaultdict(set)
    anchors: dict[str, object] = {}
    minted = 0

    for external_id, event_id, _created, commence_source, _ct, _h, _a in market_rows:
        if event_id is None:
            continue
        token = kalshi_game_id(external_id)
        if token is None:
            continue
        # The SQL chunk key re-implemented the token; check it against the real
        # helper rather than trusting two spellings of one idea to agree.
        if external_id.split("-")[1].upper() != token:
            token_mismatch += 1

        key = kalshi_anchor_key(external_id)
        fixture = f"{key.source_id if key.id_kind == 'game' else token}"

        before[fixture].add(event_id)

        if commence_source != TICKER_DERIVED:
            # The matcher LINKED this market to a row that already existed.
            # Half B writes the anchor, and only when it is unclaimed.
            after[fixture].add(event_id)
            if key.id_kind == "game":
                anchors.setdefault(key.source_id, event_id)
            continue

        # This market's row was MINTED from its ticker. On the repaired tree the
        # registry consults the channel first (Step 2).
        if key.id_kind == "game" and key.source_id in anchors:
            after[fixture].add(anchors[key.source_id])
            continue
        after[fixture].add(event_id)
        if key.id_kind == "game":
            anchors[key.source_id] = event_id
        minted += 1

    n_fixtures = len(before)
    rows_before = sum(len(v) for v in before.values())
    rows_after = sum(len(v) for v in after.values())
    regressed = [f for f in before if len(after[f]) > len(before[f])]
    if not verbose:
        print(
            f"  {label:<24} rows {rows_before} -> {rows_after}   "
            f"excess {rows_before - n_fixtures} -> {rows_after - n_fixtures}   "
            f"made worse {len(regressed)}"
        )
        return token_mismatch + len(regressed)
    print(f"\n  fixtures                     {n_fixtures}")
    print(f"  event rows BEFORE            {rows_before}")
    print(f"  event rows AFTER             {rows_after}")
    print(f"  excess rows BEFORE           {rows_before - n_fixtures}")
    print(f"  excess rows AFTER            {rows_after - n_fixtures}")
    print(f"  SQL-vs-helper token mismatch {token_mismatch}")

    worst = sorted(before.items(), key=lambda kv: -len(kv[1]))[:12]
    print("\n  worst fixtures (before -> after):")
    for fixture, rows in worst:
        print(f"    {fixture:<44} {len(rows)} -> {len(after[fixture])}")

    # A repair that adds a row anywhere is not a repair. Asserted rather than
    # eyeballed off the totals, which can net a regression against a win.
    print(f"\n  fixtures made WORSE          {len(regressed)}")
    for fixture in regressed:
        print(f"    *** {fixture} {len(before[fixture])} -> {len(after[fixture])}")

    residual = sorted(f for f in after if len(after[f]) > 1)
    print(f"\n  fixtures still >1 row after  {len(residual)}")
    for fixture in residual:
        print(f"    {fixture:<44} {len(before[fixture])} -> {len(after[fixture])}")
        for external_id, event_id, created, src, _ct, home, away in market_rows:
            if event_id is None or kalshi_game_id(external_id) is None:
                continue
            key = kalshi_anchor_key(external_id)
            name = key.source_id if key.id_kind == "game" else kalshi_game_id(external_id)
            if name == fixture:
                print(
                    f"        {created[:16]}  {external_id:<34} ev={event_id} "
                    f"src={src} {home} v {away}"
                )
    return token_mismatch + len(regressed)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="re-pull from production")
    args = ap.parse_args()

    payload = fetch() if args.fetch else json.loads(ARTIFACT.read_text())
    bad = classify(payload["series"])
    rows = payload["markets"]
    mismatch = replay(sorted(rows, key=lambda r: r[2]))
    print("\n  ORDER BAND — the same population, both extremes:")
    mismatch += replay(
        sorted(rows, key=lambda r: r[2]), label="real created_at order",
        verbose=False,
    )
    mismatch += replay(
        sorted(rows, key=lambda r: r[2], reverse=True),
        label="reversed (adversarial)", verbose=False,
    )
    if bad or mismatch:
        print("\nFAILED: see the starred lines above")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
