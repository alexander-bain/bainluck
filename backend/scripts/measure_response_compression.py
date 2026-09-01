#!/usr/bin/env python3
"""Measure what the API actually puts on the wire, before and after compression.

LAT-P185. The API has never sent a `Content-Encoding` on any response: every
JSON body — including a 449 KB `/api/calibration` — crosses the network raw.
This script is the instrument for that claim and for the fix, and it is
deliberately ONE instrument used at both ends so the before/after numbers are
comparable by construction rather than by assertion.

What it records per endpoint, per repeat:

  * ``wire_bytes``   — bytes actually received. This is the number that changes.
  * ``total_ms``     — full request wall time, client side.
  * ``ttfb_ms``      — time to first byte, so transfer time can be separated
                       from server think time. Compression trades a little
                       server time for a lot of transfer time; a single
                       total-time number cannot show that trade and would let a
                       CPU regression hide inside a transfer win.
  * ``content_encoding`` / ``x-response-time`` / ``x-feed-cache`` — the server's
                       own account of what it did.

Two things this script does NOT do, on purpose:

  * It does not decompress and re-measure to prove the bodies match. That is a
    correctness question and it belongs to the guard suite
    (``tests/test_response_compression_1636.py``, which ships with CERT-630),
    asserted against the real ASGI app instead of against production traffic.
  * It does not average away the cache dimension. `/api/feed` is bimodal (cold
    miss vs warm hit) and a mean over both is a number describing no request
    anyone ever made. Every repeat is printed.

The `--offline-levels` mode answers the sizing question the deploy needs
BEFORE the deploy: given the body that is on the wire right now, what would
each gzip level cost in CPU and buy in bytes? That is how `COMPRESS_LEVEL` gets
chosen rather than inherited.

Usage:
    python3 scripts/measure_response_compression.py --repeats 3
    python3 scripts/measure_response_compression.py --offline-levels
    python3 scripts/measure_response_compression.py --json out.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict

DEFAULT_BASE = os.getenv("BAINLUCK_API", "https://api.bainluck.com")

# The five heaviest public JSON endpoints, by measured uncompressed body size
# on 2026-09-01. Ordered heaviest first so a truncated run still covers the
# endpoints where compression is worth the most.
ENDPOINTS: list[tuple[str, str]] = [
    ("calibration", "/api/calibration"),
    ("golf-tournament", "/api/golf/tournaments/us-open"),
    ("feed", "/api/feed?limit=20"),
    ("search", "/api/events/search?q=lakers"),
    ("futures", "/api/futures/1"),
]

# Levels worth pricing. 9 is Starlette's default and is NOT assumed to be the
# right answer — DEFLATE's ratio curve flattens hard above ~6 while its CPU cost
# keeps climbing, and this runs on every request of a 449 KB response.
GZIP_LEVELS = (1, 4, 5, 6, 9)


@dataclass
class Sample:
    label: str
    path: str
    status: int
    wire_bytes: int
    ttfb_ms: float
    total_ms: float
    content_encoding: str
    vary: str
    server_time: str
    cache: str
    error: str = ""


@dataclass
class LevelCost:
    level: int
    compressed_bytes: int
    ratio: float
    compress_ms: float


@dataclass
class OfflineSizing:
    label: str
    path: str
    raw_bytes: int
    levels: list[LevelCost] = field(default_factory=list)


def _opener() -> urllib.request.OpenerDirector:
    # The sandbox occasionally presents a proxy CA. Verification is not what
    # this script is measuring, and a TLS failure here would read as a latency
    # result, which is worse than an unverified byte count.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def fetch(base: str, label: str, path: str, accept_encoding: str) -> Sample:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept-Encoding", accept_encoding)
    req.add_header("Accept", "application/json")
    # A real browser principal. The anonymous shared key is the one a brand-new
    # install routes to, so no session header is sent.
    req.add_header("User-Agent", "bainluck-compression-probe/1")

    start = time.perf_counter()
    try:
        with _opener().open(req, timeout=60) as resp:
            ttfb_ms = (time.perf_counter() - start) * 1000
            body = resp.read()
            total_ms = (time.perf_counter() - start) * 1000
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return Sample(
                label=label,
                path=path,
                status=resp.status,
                wire_bytes=len(body),
                ttfb_ms=ttfb_ms,
                total_ms=total_ms,
                content_encoding=headers.get("content-encoding", "(none)"),
                vary=headers.get("vary", "(none)"),
                server_time=headers.get("x-response-time", ""),
                cache=headers.get("x-feed-cache", headers.get("x-cache", "")),
            )
    except urllib.error.HTTPError as exc:
        return Sample(label, path, exc.code, 0, 0.0, 0.0, "", "", "", "", str(exc))
    except Exception as exc:  # noqa: BLE001 — a probe must report, never raise
        return Sample(label, path, 0, 0, 0.0, 0.0, "", "", "", "", repr(exc))


def _read_raw(base: str, path: str) -> bytes:
    """Fetch a body with compression explicitly refused, for offline sizing."""
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept-Encoding", "identity")
    req.add_header("Accept", "application/json")
    with _opener().open(req, timeout=60) as resp:
        raw = resp.read()
        # If the server compressed anyway (a future proxy, say), decode so the
        # sizing prices the real payload and not a doubly-compressed one.
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return raw


def price_levels(raw: bytes) -> list[LevelCost]:
    costs: list[LevelCost] = []
    for level in GZIP_LEVELS:
        # Three passes, keep the fastest: this is a CPU measurement on a shared
        # laptop and the minimum is the least noisy estimator of the cost the
        # dyno would pay.
        best = None
        out = b""
        for _ in range(3):
            t0 = time.perf_counter()
            out = gzip.compress(raw, compresslevel=level)
            dt = (time.perf_counter() - t0) * 1000
            best = dt if best is None else min(best, dt)
        costs.append(
            LevelCost(
                level=level,
                compressed_bytes=len(out),
                ratio=len(out) / len(raw) if raw else 1.0,
                compress_ms=round(best or 0.0, 2),
            )
        )
    return costs


def run_wire(base: str, repeats: int, accept_encoding: str) -> list[Sample]:
    samples: list[Sample] = []
    for label, path in ENDPOINTS:
        for _ in range(repeats):
            samples.append(fetch(base, label, path, accept_encoding))
    return samples


def run_offline(base: str) -> list[OfflineSizing]:
    out: list[OfflineSizing] = []
    for label, path in ENDPOINTS:
        try:
            raw = _read_raw(base, path)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {label}: {exc!r}", file=sys.stderr)
            continue
        out.append(OfflineSizing(label, path, len(raw), price_levels(raw)))
    return out


def print_wire(samples: list[Sample]) -> None:
    print()
    print(
        f"{'endpoint':<18} {'bytes':>9} {'enc':<10} {'ttfb_ms':>8} {'total_ms':>9} {'srv':>8} {'cache':<10}"
    )
    print("-" * 80)
    for s in samples:
        if s.error:
            print(f"{s.label:<18} ERROR {s.error[:60]}")
            continue
        print(
            f"{s.label:<18} {s.wire_bytes:>9,} {s.content_encoding:<10} "
            f"{s.ttfb_ms:>8.0f} {s.total_ms:>9.0f} {s.server_time:>8} {s.cache:<10}"
        )
    total = sum(s.wire_bytes for s in samples if not s.error)
    n = len([s for s in samples if not s.error])
    print("-" * 80)
    print(f"{'TOTAL':<18} {total:>9,} bytes over {n} responses")


def print_offline(sizings: list[OfflineSizing]) -> None:
    print()
    for sz in sizings:
        print(f"{sz.label}  ({sz.path})  raw {sz.raw_bytes:,} bytes")
        for c in sz.levels:
            saved = sz.raw_bytes - c.compressed_bytes
            print(
                f"    gzip -{c.level}: {c.compressed_bytes:>9,} bytes "
                f"({c.ratio * 100:5.1f}% of raw, -{saved:,})  cpu {c.compress_ms:>6.2f} ms"
            )
        print()
    print("Totals across all endpoints:")
    raw_total = sum(s.raw_bytes for s in sizings)
    for level in GZIP_LEVELS:
        comp = sum(
            c.compressed_bytes for s in sizings for c in s.levels if c.level == level
        )
        cpu = sum(c.compress_ms for s in sizings for c in s.levels if c.level == level)
        print(
            f"    gzip -{level}: {comp:>9,} / {raw_total:,} bytes "
            f"({comp / raw_total * 100:5.1f}%)  total cpu {cpu:6.2f} ms"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument(
        "--accept-encoding",
        default="gzip, br",
        help="what the client claims to accept (use 'identity' for a raw baseline)",
    )
    ap.add_argument(
        "--offline-levels",
        action="store_true",
        help="price gzip levels on the current bodies",
    )
    ap.add_argument("--json", dest="json_out", help="write the full record here")
    args = ap.parse_args()

    print(f"base: {args.base}")
    print(f"accept-encoding: {args.accept_encoding}")

    record: dict = {"base": args.base, "accept_encoding": args.accept_encoding}

    if args.offline_levels:
        sizings = run_offline(args.base)
        print_offline(sizings)
        record["offline_levels"] = [asdict(s) for s in sizings]
    else:
        samples = run_wire(args.base, args.repeats, args.accept_encoding)
        print_wire(samples)
        record["samples"] = [asdict(s) for s in samples]

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(record, fh, indent=2)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
