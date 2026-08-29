"""Re-pull the US Open ladder books that `market_liquidity` is graded against.

WHY THIS IS A FILE AND NOT A PASTED ONE-LINER.  UX-P157 banked
`docs/mocks/us-open/ladder-books-2026-08-28.json` from an ad-hoc pull, and the
next queue that needed one more field (Gamma's lifetime ``volume``) had to
re-derive the whole pull from the fixture's shape.  The rule in
``app/utils/market_liquidity.py`` is defensible only because every ingredient in
it was measured, so the pull that produces those measurements is part of the
rule and lives beside it.

Live half: Gamma ``/markets?condition_ids=...``, batched.  Stored half: the
read-only admin ``db-query`` endpoint, which needs ``ADMIN_TOKEN`` and
``BAINLUCK_API`` from ``~/.claude/.env`` — pass ``--no-stored`` to skip it and
pull the live half alone.

    python3 backend/scripts/pull_ladder_books.py \
        --condition-ids-from docs/mocks/us-open/ladder-books-2026-08-28.json \
        --out docs/mocks/us-open/ladder-books-2026-08-29.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Optional

GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"

#: The TRADE TAPE — a different endpoint measuring a different thing. Gamma's
#: volume fields are computed aggregates it may omit; this is the list of trades
#: that actually happened. It is the second signal gotcha #53 asks for before
#: reading an absence as a zero, and banking it beside the books is what lets a
#: test re-check that reading without a network call.
DATA_API_TRADES = "https://data-api.polymarket.com/trades"

#: How many trades to ask for per market. Only two questions are asked of the
#: answer — "any at all?" and "any in the last day?" — and 100 is far above the
#: busiest of these markets, so the sample is never the binding constraint.
#: A market that hit the cap is recorded as having hit it rather than silently
#: summarised (no silent caps).
TRADES_LIMIT = 100

#: Gamma's page limit is generous but the URL is not — 25 ids per request keeps
#: the query string well inside anything a proxy might truncate.
BATCH = 25

#: Every live field the liquidity rule reads or might read, and nothing else.
#: A wholesale dump of Gamma's ~60 keys would bank a fixture nobody can diff.
LIVE_FIELDS = (
    "bestBid",
    "bestAsk",
    "volume24hr",
    "volume",
    "volumeClob",
    "liquidity",
    "oneDayPriceChange",
    "spread",
    "outcomePrices",
    "closed",
    "question",
)


#: Gamma 403s urllib's default ``Python-urllib/3.x`` agent while serving the
#: identical URL to curl. Measured 2026-08-28: same query string, 403 vs 200.
#: This is a header, not a workaround for a rate limit — do not add sleeps to
#: "fix" a 403.
USER_AGENT = "bainluck-ladder-book-pull/1.0 (+https://bainluck.com)"


def _get_json(url: str, timeout: int = 30) -> Any:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict, token: str, timeout: int = 40) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _batched(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def fetch_live(condition_ids: list[str]) -> dict[str, dict[str, Any]]:
    """condition_id → the LIVE_FIELDS Gamma serves for it, right now.

    A field Gamma omits is omitted here too.  Defaulting an absent
    ``volume24hr`` to ``0`` is the exact mistake gotcha #53 names, and the
    fixture is the last place it should be made — a fixture that has already
    decided is not evidence.
    """
    out: dict[str, dict[str, Any]] = {}
    for batch in _batched(condition_ids, BATCH):
        query = "&".join(f"condition_ids={urllib.parse.quote(c)}" for c in batch)
        query += f"&limit={len(batch)}"
        try:
            markets = _get_json(f"{GAMMA_MARKETS}?{query}")
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover
            print(f"  batch failed ({exc}) — retrying one at a time", file=sys.stderr)
            markets = []
            for one in batch:
                try:
                    markets.extend(
                        _get_json(
                            f"{GAMMA_MARKETS}?condition_ids={urllib.parse.quote(one)}"
                        )
                    )
                except (urllib.error.URLError, TimeoutError) as inner:
                    print(f"  {one[:12]}… failed: {inner}", file=sys.stderr)
        for market in markets or []:
            condition_id = market.get("conditionId")
            if not condition_id:
                continue
            out[condition_id] = {
                field: market[field] for field in LIVE_FIELDS if field in market
            }
        print(f"  live {len(out)}/{len(condition_ids)}", file=sys.stderr)
    return out


def fetch_tape(condition_ids: list[str], *, now: float) -> dict[str, dict[str, Any]]:
    """condition_id → what the trade tape says, independent of Gamma's volume.

    ``now`` is passed in rather than read here so the whole pull is stamped
    against one instant and a re-run is reproducible from the fixture.
    """
    out: dict[str, dict[str, Any]] = {}
    for index, condition_id in enumerate(condition_ids, 1):
        url = f"{DATA_API_TRADES}?market={urllib.parse.quote(condition_id)}&limit={TRADES_LIMIT}"
        try:
            trades = _get_json(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  tape {condition_id[:12]}… failed: {exc}", file=sys.stderr)
            continue
        if not isinstance(trades, list):
            continue
        stamps = sorted(float(t.get("timestamp") or 0) for t in trades)
        out[condition_id] = {
            "trades_sampled": len(trades),
            "trades_sample_hit_cap": len(trades) >= TRADES_LIMIT,
            "trades_in_24h": sum(1 for s in stamps if now - s <= 86400),
            "newest_trade_age_h": (now - stamps[-1]) / 3600.0 if stamps else None,
        }
        if index % 50 == 0:
            print(f"  tape {index}/{len(condition_ids)}", file=sys.stderr)
    return out


def fetch_stored(condition_ids: list[str]) -> dict[str, dict[str, Any]]:
    """condition_id → what our own Postgres holds for the same markets.

    Chunked on the id list because the db-query row path has a hard 10s timeout
    and a 1000-row cap, and a truncated read is indistinguishable from a short
    one in the response body.
    """
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        raise SystemExit(
            "BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env), "
            "or pass --no-stored"
        )
    out: dict[str, dict[str, Any]] = {}
    for batch in _batched(condition_ids, 60):
        quoted = ", ".join("'" + c.replace("'", "''") + "'" for c in batch)
        # The BOOK the route reads is the YES outcome's, not the market's —
        # `_load_prices` selects `FuturesOutcome.current_yes_bid/ask`. The
        # VOLUME it reads is the market's, because both venues report volume
        # per market. A fixture that pulled the book from the wrong table would
        # grade a book the page never sees.
        sql = (
            "SELECT fm.external_id AS condition_id, "
            "MAX(fo.current_yes_bid) AS best_bid, MAX(fo.current_yes_ask) AS best_ask, "
            "MAX(fm.volume_24h) AS volume_24h, MAX(fm.volume) AS volume, "
            "MAX(fm.volume_updated_at)::text AS volume_updated_at, "
            "MAX(fo.last_updated)::text AS price_updated_at "
            "FROM futures_markets fm "
            "JOIN futures_outcomes fo ON fo.market_id = fm.id "
            "AND LOWER(TRIM(fo.name)) = 'yes' "
            f"WHERE fm.external_id IN ({quoted}) "
            "GROUP BY fm.external_id"
        )
        payload = _post_json(
            f"{api}/api/admin/db-query", {"sql": sql, "limit": 500}, token
        )
        columns = payload.get("columns") or []
        for row in payload.get("rows") or []:
            record = dict(zip(columns, row))
            condition_id = record.pop("condition_id", None)
            if condition_id:
                out[condition_id] = record
        print(f"  stored {len(out)}/{len(condition_ids)}", file=sys.stderr)
    return out


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--condition-ids-from",
        required=True,
        help="a previously banked ladder-books fixture; its keys are the ids to pull",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-stored", action="store_true")
    parser.add_argument("--no-tape", action="store_true")
    args = parser.parse_args()

    with open(args.condition_ids_from, encoding="utf-8") as handle:
        raw = json.load(handle)
    condition_ids = sorted(k for k in raw if k != "_meta")
    print(f"{len(condition_ids)} condition ids", file=sys.stderr)

    pulled_at = time.time()
    live = fetch_live(condition_ids)
    tape = {} if args.no_tape else fetch_tape(condition_ids, now=pulled_at)
    stored = {} if args.no_stored else fetch_stored(condition_ids)

    banked: dict[str, dict[str, Any]] = {}
    for condition_id in condition_ids:
        live_row = live.get(condition_id, {})
        stored_row = stored.get(condition_id, {})
        entry: dict[str, Any] = {
            "live_bid": _as_float(live_row.get("bestBid")),
            "live_ask": _as_float(live_row.get("bestAsk")),
            # ABSENT and null are different facts. `live_volume_24h_present`
            # carries the distinction the grade turns on; a reader of the
            # fixture must not have to infer it from a null.
            "live_volume_24h": _as_float(live_row.get("volume24hr")),
            "live_volume_24h_present": "volume24hr" in live_row,
            "live_volume_lifetime": _as_float(live_row.get("volume")),
            "live_volume_clob": _as_float(live_row.get("volumeClob")),
            "live_liquidity": _as_float(live_row.get("liquidity")),
            "live_one_day_price_change": _as_float(live_row.get("oneDayPriceChange")),
            "live_present": bool(live_row),
        }
        if stored_row:
            entry["stored_bid"] = _as_float(stored_row.get("best_bid"))
            entry["stored_ask"] = _as_float(stored_row.get("best_ask"))
            entry["stored_volume_24h"] = _as_float(stored_row.get("volume_24h"))
            entry["stored_volume_lifetime"] = _as_float(stored_row.get("volume"))
            entry["stored_volume_updated_at"] = stored_row.get("volume_updated_at")
            entry["stored_price_updated_at"] = stored_row.get("price_updated_at")
        entry.update(tape.get(condition_id, {}))
        banked[condition_id] = entry

    banked["_meta"] = {
        "pulled_at_epoch": pulled_at,
        "pulled_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(pulled_at)),
        "condition_ids": len(condition_ids),
        "live_served": sum(1 for v in banked.values() if v.get("live_present")),
        "trades_limit": TRADES_LIMIT,
        "note": (
            "Live half: Gamma /markets. Tape half: data-api /trades, the "
            "independent instrument that makes an absent volume field readable. "
            "Stored half: production Postgres via admin db-query. Produced by "
            "backend/scripts/pull_ladder_books.py."
        ),
    }

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(banked, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
