#!/usr/bin/env python3
"""
Scan Kalshi + Polymarket for every US Open (men's golf) market and rank by
TRUE 12-hour trading volume (summed from trade-level data, not the 24h field).

Why a standalone stdlib script: it can run anywhere with outbound network
(including a Claude Code web session once the egress allowlist includes the
hosts below) without needing httpx/requests installed.

Hosts contacted:
  - api.elections.kalshi.com   (Kalshi markets + trades)
  - gamma-api.polymarket.com   (Polymarket market discovery)
  - data-api.polymarket.com    (Polymarket trade history)

Auth:
  - Kalshi public market/trade reads work without a key. If you have one,
    set KALSHI_API_KEY and it will be sent as a Bearer token.
  - Polymarket read APIs are fully public.

Usage:
    python3 scripts/us_open_golf_markets.py
    python3 scripts/us_open_golf_markets.py --hours 12 --out us_open.csv

Output:
  - A markdown table ranked desc by 12h USD-notional volume (printed to stdout)
  - A CSV with every column (--out, default scripts/us_open_golf_markets.csv)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# --------------------------------------------------------------------------- #
# HTTP helpers (stdlib only, with 429 backoff)
# --------------------------------------------------------------------------- #

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"
PM_DATA_BASE = "https://data-api.polymarket.com"

_KALSHI_KEY = os.getenv("KALSHI_API_KEY")


def _get(url: str, params: dict | None = None, headers: dict | None = None,
         retries: int = 5) -> object:
    """GET JSON with simple 429/5xx exponential backoff. Returns parsed JSON
    or None on 404."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    hdrs = {"Accept": "application/json", "User-Agent": "bainluck-usopen-scan/1.0"}
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 422:
                # Gamma's offset pagination caps (~2000) and returns 422
                # ("offset too large, use /events/keyset"). Treat as end-of-data
                # so the sweep loop stops gracefully instead of crashing; the
                # tag-slug discovery already covers the golf events directly.
                return None
            if e.code in (403, 429, 500, 502, 503, 504):
                # 403 from Kalshi/Polymarket here is almost always a transient
                # rate-limit guard, not a real auth failure — back off and retry.
                last_err = e
                time.sleep(min(2 ** attempt, 16))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(min(2 ** attempt, 16))
            continue
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last_err})")


def _kalshi_get(path: str, params: dict | None = None) -> object:
    headers = {}
    if _KALSHI_KEY:
        headers["Authorization"] = f"Bearer {_KALSHI_KEY}"
    return _get(f"{KALSHI_BASE}{path}", params=params, headers=headers)


# --------------------------------------------------------------------------- #
# US Open matching
# --------------------------------------------------------------------------- #

# Matches "U.S. Open", "US Open", "USOpen", "U S Open" (case-insensitive).
_US_OPEN_RE = re.compile(r"\bu\.?\s*s\.?\s*open\b", re.IGNORECASE)


def _is_us_open_text(*texts: str) -> bool:
    blob = " ".join(t for t in texts if t)
    return bool(_US_OPEN_RE.search(blob))


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Kalshi
# --------------------------------------------------------------------------- #

def kalshi_golf_series() -> list[str]:
    """Discover all men's golf series tickers.

    Strategy: pull Sports/Golf series via the series endpoint AND keep any
    series ticker starting with KXPGA (every kxpga* series is men's golf per
    sport_keys.py). Excludes LPGA (women's). Adds known major/US-Open prop
    prefixes explicitly so nothing is missed if the tag listing is incomplete.
    """
    found: set[str] = set()
    cursor = None
    for _ in range(15):
        params = {"category": "Sports", "tags": "Golf", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = _kalshi_get("/series", params=params) or {}
        for s in data.get("series", []) or []:
            t = (s.get("ticker") or "").upper()
            if t:
                found.add(t)
        cursor = data.get("cursor")
        if not cursor:
            break
        time.sleep(0.3)

    # Keep only men's golf series: kxpga* / kxlivgolf, drop LPGA.
    mens = {
        t for t in found
        if (t.startswith("KXPGA") or t.startswith("KXLIVGOLF"))
        and not t.startswith("KXLPGA")
    }
    # Explicit safety net of known men's golf prop/futures prefixes.
    mens.update({
        "KXPGATOUR", "KXPGAMAKECUT", "KXPGATOP5", "KXPGATOP10", "KXPGATOP20",
        "KXPGAR1LEAD", "KXPGAR2LEAD", "KXPGAR3LEAD", "KXPGAH2H",
        "KXPGAHOLEINONE", "KXPGAMAJORWIN", "KXPGAWINNINGSCORE", "KXPGACUTLINE",
        "KXPGAWINMARGIN", "KXPGAUSO",
    })
    return sorted(mens)


def kalshi_scan(include_settled: bool = False) -> list[dict]:
    """Return raw US-Open men's golf markets from Kalshi (one row per market).

    By default only currently-tradeable markets are returned. Pass
    include_settled=True to also surface resolved per-round/per-hole prop
    markets (eagle, birdie, round score, round lead, etc.) — these settle as
    the tournament progresses, so late in an event most of the granular prop
    scene is finalized and would otherwise be invisible.
    """
    series = kalshi_golf_series()
    print(f"[kalshi] scanning {len(series)} men's golf series...", file=sys.stderr)
    markets: dict[str, dict] = {}  # ticker -> market dict (dedup)

    for st in series:
        # Fetch open + unsettled events for this series. Status=open covers
        # today's live markets; we also sweep without status to catch any
        # neg-risk event whose status is null.
        for status in ("open", None):
            cursor = None
            for _ in range(8):
                params = {"series_ticker": st, "with_nested_markets": "true",
                          "limit": 200}
                if status:
                    params["status"] = status
                if cursor:
                    params["cursor"] = cursor
                data = _kalshi_get("/events", params=params) or {}
                events = data.get("events", []) or []
                for ev in events:
                    ev_title = ev.get("title") or ""
                    ev_sub = ev.get("sub_title") or ""
                    ev_tkr = ev.get("event_ticker") or ""
                    nested = ev.get("markets", []) or []
                    # Event-level US Open match, OR any nested market mentions it.
                    ev_match = _is_us_open_text(ev_title, ev_sub, ev_tkr)
                    for m in nested:
                        mt = m.get("title") or ""
                        msub = m.get("subtitle") or m.get("yes_sub_title") or ""
                        mtkr = m.get("ticker") or ""
                        if not (ev_match or _is_us_open_text(mt, msub, mtkr)):
                            continue
                        if not include_settled and m.get("status") not in ("active", "open", None, "initialized"):
                            # keep only tradeable markets for "today" view
                            if m.get("status") in ("settled", "finalized"):
                                continue
                        tkr = m.get("ticker")
                        if not tkr or tkr in markets:
                            continue
                        markets[tkr] = {
                            "event_ticker": ev_tkr,
                            "event_title": ev_title,
                            "series": st,
                            "ticker": tkr,
                            "market_title": mt,
                            "yes_sub": m.get("yes_sub_title") or msub,
                            "status": m.get("status"),
                            "yes_ask": _price(m, "yes_ask"),
                            "last_price": _price(m, "last_price"),
                            "volume_24h": _intish(m.get("volume_24h_fp"), m.get("volume_24h")),
                            "volume_total": _intish(m.get("volume_fp"), m.get("volume")),
                            "open_interest": _intish(m.get("open_interest_fp"), m.get("open_interest")),
                        }
                cursor = data.get("cursor")
                if not cursor:
                    break
                time.sleep(0.25)
    print(f"[kalshi] matched {len(markets)} US Open markets", file=sys.stderr)
    return list(markets.values())


def _price(m: dict, base: str):
    v = m.get(f"{base}_dollars")
    if v not in (None, ""):
        try:
            return float(v)
        except Exception:
            pass
    v = m.get(base)
    if v is None:
        return None
    try:
        v = float(v)
        return v if v <= 1 else v / 100.0
    except Exception:
        return None


def _intish(*vals):
    for v in vals:
        if v in (None, ""):
            continue
        try:
            return int(float(v))
        except Exception:
            continue
    return None


def kalshi_12h_volume(ticker: str, cutoff_ts: int) -> tuple[int, float]:
    """Sum (contracts, USD notional) of trades on a Kalshi market since cutoff.

    Trades are returned newest-first; stop paginating once we pass the cutoff.
    """
    contracts = 0
    notional = 0.0
    cursor = None
    for _ in range(60):  # up to 60 pages * 100 = 6000 trades
        params = {"ticker": ticker, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        data = _kalshi_get("/markets/trades", params=params) or {}
        trades = data.get("trades", []) or []
        if not trades:
            break
        stop = False
        for tr in trades:
            ct = tr.get("created_time")
            tdt = _parse_iso(ct) if isinstance(ct, str) else None
            tts = int(tdt.timestamp()) if tdt else tr.get("created_time_ts") or tr.get("ts")
            if tts is None:
                continue
            if tts < cutoff_ts:
                stop = True
                break
            cnt = _intish(tr.get("count_fp"), tr.get("count")) or 0
            price = None
            for k in ("yes_price_dollars", "yes_price"):
                if tr.get(k) not in (None, ""):
                    try:
                        price = float(tr[k])
                        price = price if price <= 1 else price / 100.0
                        break
                    except Exception:
                        pass
            contracts += cnt
            if price is not None:
                notional += cnt * price
        cursor = data.get("cursor")
        if stop or not cursor:
            break
        time.sleep(0.1)
    return contracts, round(notional, 2)


# --------------------------------------------------------------------------- #
# Polymarket
# --------------------------------------------------------------------------- #

def polymarket_scan() -> list[dict]:
    """Return raw US-Open golf sub-markets from Polymarket (one row per market)."""
    rows: dict[str, dict] = {}  # condition_id -> row

    # 1) Golf-tagged events (slug-based).
    golf_events: list[dict] = []
    for slug in ("golf", "pga-tour", "us-open-golf"):
        offset = 0
        for _ in range(10):
            data = _get(f"{GAMMA_BASE}/events", params={
                "active": "true", "closed": "false",
                "tag_slug": slug, "limit": 100, "offset": offset,
            }) or []
            if not data:
                break
            golf_events.extend(data)
            if len(data) < 100:
                break
            offset += 100
            time.sleep(0.2)

    # 2) Full active-event sweep, filtering titles for "U.S. Open" + golf.
    offset = 0
    for _ in range(120):  # up to 12,000 events
        data = _get(f"{GAMMA_BASE}/events", params={
            "active": "true", "closed": "false", "limit": 100, "offset": offset,
        }) or []
        if not data:
            break
        for ev in data:
            title = ev.get("title") or ""
            slug = ev.get("slug") or ""
            tags = [
                (t.get("label") or t.get("slug") or "") if isinstance(t, dict) else str(t)
                for t in (ev.get("tags") or [])
            ]
            tagblob = " ".join(tags).lower()
            if _is_us_open_text(title, slug) and ("golf" in tagblob or "golf" in slug.lower()):
                golf_events.append(ev)
        if len(data) < 100:
            break
        offset += 100
        time.sleep(0.2)

    print(f"[polymarket] {len(golf_events)} candidate golf events", file=sys.stderr)

    for ev in golf_events:
        title = ev.get("title") or ""
        slug = ev.get("slug") or ""
        ev_id = str(ev.get("id") or "")
        tags = [
            (t.get("label") or t.get("slug") or "") if isinstance(t, dict) else str(t)
            for t in (ev.get("tags") or [])
        ]
        is_golf = "golf" in " ".join(tags).lower() or "golf" in slug.lower()
        if not (_is_us_open_text(title, slug) and is_golf):
            # Some golf-tagged events list the tournament only in sub-markets.
            if not is_golf:
                continue
        for m in ev.get("markets", []) or []:
            q = m.get("question") or ""
            git = m.get("groupItemTitle") or ""
            if not (_is_us_open_text(title, slug) or _is_us_open_text(q, git)):
                continue
            cid = m.get("conditionId") or m.get("condition_id") or ""
            if not cid or cid in rows:
                continue
            prices = _json_arr(m.get("outcomePrices"))
            outcomes = _json_arr(m.get("outcomes"))
            tokens = _json_arr(m.get("clobTokenIds"))
            yes_price = None
            if prices:
                try:
                    yes_price = float(prices[0])
                except Exception:
                    yes_price = None
            rows[cid] = {
                "event_title": title,
                "event_id": ev_id,
                "condition_id": cid,
                "market_title": q,
                "group_item_title": git,
                "outcomes": outcomes,
                "yes_price": yes_price,
                "last_trade_price": _safe_float(m.get("lastTradePrice")),
                "volume_24h": _safe_float(m.get("volume24hr")),
                "volume_total": _safe_float(m.get("volume")),
                "liquidity": _safe_float(m.get("liquidity")),
                "clob_token_ids": tokens,
                "slug": m.get("slug"),
            }
    print(f"[polymarket] matched {len(rows)} US Open markets", file=sys.stderr)
    return list(rows.values())


def polymarket_12h_volume(condition_id: str, cutoff_ts: int) -> tuple[float, float]:
    """Sum (shares, USD notional) of trades on a Polymarket market since cutoff.

    Uses data-api /trades (market filter = condition_id). Notional = size*price.
    """
    shares = 0.0
    notional = 0.0
    offset = 0
    for _ in range(40):  # up to 40 pages
        try:
            data = _get(f"{PM_DATA_BASE}/trades", params={
                "market": condition_id, "limit": 500, "offset": offset,
                "takerOnly": "true",
            }) or []
        except Exception:
            break
        if not data:
            break
        page_all_old = True
        for tr in data:
            ts = tr.get("timestamp") or tr.get("matchtime") or tr.get("time")
            try:
                ts = int(ts)
            except Exception:
                continue
            if ts < cutoff_ts:
                continue
            page_all_old = False
            size = _safe_float(tr.get("size")) or 0.0
            price = _safe_float(tr.get("price")) or 0.0
            shares += size
            notional += size * price
        if len(data) < 500:
            break
        # data-api returns newest first; if an entire page is older than cutoff, stop.
        if page_all_old and offset > 0:
            break
        offset += 500
        time.sleep(0.15)
    return round(shares, 2), round(notional, 2)


def _json_arr(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            p = json.loads(value)
            return p if isinstance(p, list) else []
        except Exception:
            return []
    return []


def _safe_float(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=12.0,
                    help="Trade-volume window in hours (default 12)")
    ap.add_argument("--out", default="scripts/us_open_golf_markets.csv")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--include-settled", action="store_true",
                    help="Also include resolved per-round/per-hole prop markets "
                         "(eagle, birdie, round score/lead). Surfaces the full "
                         "extended prop scene once an event is underway.")
    ap.add_argument("--top", type=int, default=0,
                    help="Limit the printed markdown table to the top N rows "
                         "(0 = print all). The CSV always contains every row.")
    ap.add_argument("--storylines", action="store_true",
                    help="Print a final-round viewing guide (winner race, "
                         "tightest head-to-head pairings, top-5 bubble, winning "
                         "score line) instead of the full market table. The CSV "
                         "is still written.")
    args = ap.parse_args()

    now = int(time.time())
    cutoff = now - int(args.hours * 3600)
    window_lbl = f"{args.hours:g}h"

    # --- Scan both venues ---
    k_rows = kalshi_scan(include_settled=args.include_settled)
    p_rows = polymarket_scan()

    # --- Compute true Nh volume via trades (parallel) ---
    print(f"[trades] summing {window_lbl} volume for "
          f"{len(k_rows)} Kalshi + {len(p_rows)} Polymarket markets...",
          file=sys.stderr)

    def fill_kalshi(r):
        c, n = kalshi_12h_volume(r["ticker"], cutoff)
        r["vol12_contracts"] = c
        r["vol12_usd"] = n
        return r

    def fill_pm(r):
        s, n = polymarket_12h_volume(r["condition_id"], cutoff)
        r["vol12_shares"] = s
        r["vol12_usd"] = n
        return r

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(fill_kalshi, k_rows))
        list(ex.map(fill_pm, p_rows))

    # --- Unify ---
    unified = []
    for r in k_rows:
        prob = r.get("yes_ask") or r.get("last_price")
        unified.append({
            "source": "Kalshi",
            "market": _kalshi_label(r),
            "type": _classify_kalshi(r),
            "implied_prob": prob,
            "vol12_usd": r.get("vol12_usd") or 0.0,
            "vol12_native": f"{r.get('vol12_contracts') or 0} contracts",
            "vol24h_native": r.get("volume_24h"),
            "ticker_or_id": r["ticker"],
        })
    for r in p_rows:
        prob = r.get("yes_price") or r.get("last_trade_price")
        unified.append({
            "source": "Polymarket",
            "market": _pm_label(r),
            "type": _classify_pm(r),
            "implied_prob": prob,
            "vol12_usd": r.get("vol12_usd") or 0.0,
            "vol12_native": f"{r.get('vol12_shares') or 0:.0f} shares",
            "vol24h_native": r.get("volume_24h"),
            "ticker_or_id": r["condition_id"][:18],
        })

    unified.sort(key=lambda x: x["vol12_usd"], reverse=True)

    # --- Output: header + category summary ---
    print()
    print(f"# US Open (men's golf) markets — ranked by {window_lbl} trade volume")
    print(f"# Generated {datetime.now(timezone.utc).isoformat()}  "
          f"(cutoff = last {window_lbl})")
    settled_note = " (incl. settled props)" if args.include_settled else ""
    print(f"# {len(unified)} markets total{settled_note}: "
          f"{len(k_rows)} Kalshi + {len(p_rows)} Polymarket")
    print()

    if args.storylines:
        _print_storylines(unified, window_lbl)
    else:
        import collections as _c
        by_type = _c.Counter((x["source"], x["type"]) for x in unified)
        type_usd = _c.defaultdict(float)
        for x in unified:
            type_usd[(x["source"], x["type"])] += x["vol12_usd"] or 0.0
        print("## Prop-type breakdown")
        print(f"| Source | Type | Markets | {window_lbl} vol (USD) |")
        print("|--------|------|---------|------------|")
        for (s, t), n in sorted(by_type.items(), key=lambda kv: -type_usd[kv[0]]):
            print(f"| {s} | {t} | {n} | ${type_usd[(s, t)]:,.0f} |")
        print()

        # --- Output: markdown table ---
        shown = unified if args.top <= 0 else unified[:args.top]
        title_cap = "" if args.top <= 0 else f" (top {len(shown)} of {len(unified)})"
        print(f"## Markets ranked by {window_lbl} trade volume{title_cap}")
        hdr = ("| # | Source | Market | Type | Implied % | "
               f"{window_lbl} vol (USD) | {window_lbl} native | 24h vol |")
        print(hdr)
        print("|---|--------|--------|------|-----------|------------|-----------|---------|")
        for i, x in enumerate(shown, 1):
            prob = f"{x['implied_prob']*100:.1f}%" if x["implied_prob"] is not None else "—"
            v24 = f"{x['vol24h_native']:,.0f}" if x["vol24h_native"] else "—"
            print(f"| {i} | {x['source']} | {x['market'][:60]} | {x['type']} | "
                  f"{prob} | ${x['vol12_usd']:,.0f} | {x['vol12_native']} | {v24} |")

    # --- Output: CSV ---
    import csv
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "source", "market", "type", "implied_prob",
                    f"vol{window_lbl}_usd", f"vol{window_lbl}_native",
                    "vol24h_native", "ticker_or_id"])
        for i, x in enumerate(unified, 1):
            w.writerow([i, x["source"], x["market"], x["type"],
                        x["implied_prob"], x["vol12_usd"], x["vol12_native"],
                        x["vol24h_native"], x["ticker_or_id"]])
    print(f"\n[done] wrote {len(unified)} rows to {args.out}", file=sys.stderr)


def _print_storylines(unified: list[dict], window_lbl: str) -> None:
    """Render a final-round viewing guide from the live unified board.

    Pulls four narrative slices from the (live) markets: the winner race, the
    tightest final-round head-to-head pairings, the top-5 bubble, and the
    winning-score line. Designed to be re-run through the round for updates.
    """
    def pct(x):
        p = x.get("implied_prob")
        return p * 100 if p is not None else None

    def usd(x):
        return x.get("vol12_usd") or 0.0

    # --- Winner race (Kalshi per-player winner markets) ---
    win = [x for x in unified if x["type"] == "winner"
           and x["source"] == "Kalshi" and pct(x) is not None]
    win.sort(key=lambda x: -pct(x))
    print("## 🏆 Winner race")
    for x in win[:8]:
        name = re.sub(r"Will (.+?) win.*", r"\1", x["market"])
        print(f"- **{pct(x):.0f}%** {name}  · {window_lbl} ${usd(x):,.0f}")

    # --- Tightest final-round head-to-head pairings ---
    h2h = [x for x in unified if x["type"] == "head-to-head"
           and pct(x) is not None and usd(x) > 500]
    # Dedup mirror pairings (A vs B / B vs A) by keeping the higher-volume side.
    seen, uniq = {}, []
    for x in sorted(h2h, key=lambda x: -usd(x)):
        m = re.sub(r"Will (.+?) beat (.+?) in the 4th round.*", r"\1|\2", x["market"])
        key = frozenset(m.split("|"))
        if key in seen:
            continue
        seen[key] = True
        uniq.append(x)
    uniq.sort(key=lambda x: abs(pct(x) - 50))
    print("\n## ⚔️ Tightest final-round pairings (coin-flips)")
    for x in uniq[:6]:
        m = re.sub(r"Will (.+?) beat (.+?) in the 4th round.*", r"\1 vs \2", x["market"])
        print(f"- **{pct(x):.0f}/{100 - pct(x):.0f}** {m}  · {window_lbl} ${usd(x):,.0f}")

    # --- Top-5 bubble (on the cusp) ---
    bub = [x for x in unified if x["type"] == "top 5"
           and pct(x) is not None and 20 <= pct(x) <= 85]
    bub.sort(key=lambda x: -usd(x))
    print("\n## 📊 Top-5 bubble (the chase behind the leaders)")
    for x in bub[:8]:
        name = re.sub(r".*Will (.+?) finish top 5.*", r"\1", x["market"])
        print(f"- **{pct(x):.0f}%** {name}  · {window_lbl} ${usd(x):,.0f}")

    # --- Winning score line ---
    ws = [x for x in unified if x["type"] == "winning score" and pct(x) is not None]
    ws.sort(key=lambda x: -pct(x))
    if ws:
        print("\n## 🎯 Winning score line")
        for x in ws:
            lab = x["market"].split("—")[0].strip()
            print(f"- **{pct(x):.0f}%** {lab}")


def _kalshi_label(r):
    sub = r.get("yes_sub") or ""
    title = r.get("market_title") or ""
    if sub and sub.lower() not in title.lower():
        return f"{title} — {sub}".strip(" —")
    return title or r["ticker"]


def _pm_label(r):
    git = r.get("group_item_title") or ""
    q = r.get("market_title") or ""
    if git and git.lower() not in q.lower():
        return f"{q} — {git}".strip(" —")
    return q or r["condition_id"]


def _classify_kalshi(r):
    s = (r.get("series") or "").upper()
    table = {
        "KXPGAMAKECUT": "make cut", "KXPGATOP5": "top 5", "KXPGATOP10": "top 10",
        "KXPGATOP20": "top 20", "KXPGAH2H": "head-to-head", "KXPGAR1LEAD": "R1 lead",
        "KXPGAR2LEAD": "R2 lead", "KXPGAR3LEAD": "R3 lead",
        "KXPGAHOLEINONE": "hole-in-one", "KXPGAMAJORWIN": "winner",
        "KXPGAWINNINGSCORE": "winning score", "KXPGACUTLINE": "cut line",
        "KXPGAWINMARGIN": "win margin", "KXPGATOUR": "winner", "KXPGAUSO": "winner",
    }
    for k, v in table.items():
        if s.startswith(k):
            return v
    return "prop"


def _classify_pm(r):
    q = (r.get("market_title") or "").lower()
    if "win" in q:
        return "winner"
    if "cut" in q:
        return "make cut"
    if "top" in q:
        return "top finish"
    return "prop"


if __name__ == "__main__":
    main()
