"""One-command Dec 4 held-out scoring kit for Decide 44 (#12108, protocol-pinned).

Reads ZERO production tables before Fri Dec 4, 2026 00:00:00 PT (08:00:00Z) — strictly
after the Nov 6–Dec 4 four-week held-out window closes at 2026-12-04T05:52:44Z.
Executes Fable's single held-out score once against committed blend_replay_protocol.json
(SHA-256 73b302ff91058e29fe13d6dc315462f7fcdc3b50903c9cdce45610931d83b746), writing
immutable exclusive-create artifacts (`manifest`, `replay`, `score_receipt`).

Modes:
  --run         Execute the one-shot read-only production score on or after Dec 4 00:00 PT.
  --print-sql   Print the exact manifest and per-event read-only SQL queries (no DB access).
  --rehearsal   Prove current-clock refusal AND rehearse end-to-end on made-up games in a
                disposable local Postgres DB (ZERO production reads, ZERO real held-out games).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROTOCOL_REL_PATH = Path("backend/scripts/evals/blend_replay_protocol.json")
PROTOCOL_SHA256 = "73b302ff91058e29fe13d6dc315462f7fcdc3b50903c9cdce45610931d83b746"
RECORDING_START_ISO = "2026-11-06T05:52:44+00:00"
HOLDOUT_END_ISO = "2026-12-04T05:52:44+00:00"
# Dec 4 00:00:00 PST (2026-12-04T08:00:00Z): strictly past HOLDOUT_END_ISO and inside off-peak (05-15Z).
EARLIEST_RUN_UTC = datetime(2026, 12, 4, 8, 0, 0, tzinfo=timezone.utc)
_PT = ZoneInfo("America/Los_Angeles")
_SERIES_MAX_GAP = timedelta(days=4)
_MANIFEST_TIMEOUT_MS = 10_000
_BATCH_SIZE = 1000

MANIFEST_SQL = f"""
SELECT e.id AS event_id,
       e.commence_time AS start,
       e.home_team_name AS home_team_name,
       e.away_team_name AS away_team_name,
       s.key AS league
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE e.status = 'completed'
   AND e.commence_time >= TIMESTAMPTZ '{RECORDING_START_ISO}'
   AND e.commence_time < TIMESTAMPTZ '{HOLDOUT_END_ISO}'
   AND e.home_score IS NOT NULL
   AND e.away_score IS NOT NULL
   AND EXISTS (
       SELECT 1
         FROM probability_publications pp
        WHERE pp.event_id = e.id
          AND pp.recorded_at >= TIMESTAMPTZ '{RECORDING_START_ISO}'
          AND pp.recorded_at <= e.commence_time
   )
 ORDER BY e.commence_time, e.id
""".strip()

PER_EVENT_SQLS = [
    (
        "event",
        """
SELECT e.id, e.commence_time AS start, e.status,
       e.home_score, e.away_score, s.key AS league
  FROM events e JOIN sports s ON s.id = e.sport_id
 WHERE e.id = :event_id
""".strip(),
    ),
    (
        "odds_snapshots",
        """
SELECT id, bookmaker, captured_at, valid_until, home_win_probability
  FROM odds_snapshots
 WHERE event_id = :event_id AND captured_at <= :start
 ORDER BY captured_at, id
 LIMIT 20001
""".strip(),
    ),
    (
        "win_prob_snapshots",
        """
SELECT id, source, captured_at, valid_until, home_win_probability
  FROM win_prob_snapshots
 WHERE event_id = :event_id AND captured_at <= :start
 ORDER BY captured_at, id
 LIMIT 20001
""".strip(),
    ),
    (
        "probability_publications",
        """
SELECT rev, recorded_at, sources, event_status, blend_inputs, source_clocks,
       blend_probability, blend_tier, blend_method, payload_sha256
  FROM probability_publications
 WHERE event_id = :event_id AND recorded_at <= :start
 ORDER BY rev
 LIMIT 20001
""".strip(),
    ),
]


def _setup_sys_path(repo: Path) -> None:
    backend = str(repo.resolve() / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)


def enforce_dec4_gate(*, now_utc: datetime | None = None) -> datetime:
    """Refuse execution strictly before Fri Dec 4, 2026 00:00:00 PT (08:00:00Z)."""
    now_dt = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if now_dt < EARLIEST_RUN_UTC:
        now_pt = now_dt.astimezone(_PT).isoformat()
        earliest_pt = EARLIEST_RUN_UTC.astimezone(_PT).isoformat()
        raise ValueError(
            f"REFUSED: held-out window ({RECORDING_START_ISO} to {HOLDOUT_END_ISO}) "
            f"may not be scored before Fri Dec 4 00:00 PT ({EARLIEST_RUN_UTC.isoformat()} / "
            f"{earliest_pt}). Current time: {now_dt.isoformat()} ({now_pt})."
        )
    return now_dt


def assign_series_clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group consecutive matchups between the same teams within 4 days into one cluster_id."""
    grouped: dict[tuple[str, tuple[str, str]], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        team_a = str(r["home_team_name"]).strip().lower()
        team_b = str(r["away_team_name"]).strip().lower()
        pair = tuple(sorted((team_a, team_b)))
        grouped[(str(r["league"]), pair)].append(r)

    cluster_by_eid: dict[int, str] = {}
    for (league, pair), games in grouped.items():
        games_sorted = sorted(games, key=lambda g: (g["start"], int(g["event_id"])))
        series_start = games_sorted[0]["start"]
        prev_start = games_sorted[0]["start"]
        for g in games_sorted:
            if g["start"] - prev_start > _SERIES_MAX_GAP:
                series_start = g["start"]
            cid = f"{league}:{pair[0]}_vs_{pair[1]}:{series_start.date().isoformat()}"
            cluster_by_eid[int(g["event_id"])] = cid
            prev_start = g["start"]

    manifest = []
    for r in sorted(rows, key=lambda g: (g["start"], int(g["event_id"]))):
        eid = int(r["event_id"])
        manifest.append(
            {
                "event_id": eid,
                "cluster_id": cluster_by_eid[eid],
                "league": str(r["league"]),
                "start": r["start"].astimezone(timezone.utc).isoformat(),
            }
        )
    return manifest


def _async_db_url(raw_url: str) -> str:
    url = raw_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("PostgreSQL DATABASE_URL required")
    return url


async def _fetch_manifest_rows(raw_db_url: str) -> tuple[list[dict[str, Any]], float]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        _async_db_url(raw_db_url),
        connect_args={
            "server_settings": {
                "default_transaction_read_only": "on",
                "statement_timeout": str(_MANIFEST_TIMEOUT_MS),
            }
        },
    )
    started = time.monotonic()
    try:
        async with engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                await conn.execute(text(f"SET LOCAL statement_timeout = {_MANIFEST_TIMEOUT_MS}"))
                res = await conn.execute(text(MANIFEST_SQL))
                rows = [dict(r) for r in res.mappings()]
                await conn.rollback()
    finally:
        await engine.dispose()
    elapsed = time.monotonic() - started
    return rows, elapsed


def run_heldout_pipeline(
    *,
    repo: Path,
    output_dir: Path,
    read_window_clear: bool,
    now_utc: datetime | None = None,
    rehearsal_clock_bypass: bool = False,
) -> dict[str, Any]:
    """Execute the full manifest -> export -> score pipeline once, writing immutable receipts."""
    if not rehearsal_clock_bypass:
        now_dt = enforce_dec4_gate(now_utc=now_utc)
    else:
        now_dt = (now_utc or EARLIEST_RUN_UTC).astimezone(timezone.utc)
        if now_dt < EARLIEST_RUN_UTC:
            raise ValueError("Rehearsal clock must simulate >= EARLIEST_RUN_UTC")

    if not read_window_clear:
        raise ValueError("--read-window-clear is required")

    _setup_sys_path(repo)
    from app.utils.busy_db_defer import in_busy_window
    from scripts.evals import blend_replay_export, blend_scorer

    if in_busy_window(now_dt):
        raise ValueError(
            f"Off-peak read window closed at {now_dt.isoformat()} "
            "(allowed window: 05:00–15:00 UTC / 9:00 PM–7:00 AM PT)"
        )

    protocol_path = repo.resolve() / PROTOCOL_REL_PATH
    protocol = blend_scorer.committed_protocol(
        protocol_path, PROTOCOL_SHA256, repository=repo.resolve()
    )
    recording_start = blend_replay_export.instant(protocol["recording_start"])

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest_dec4_heldout.json"
    replay_path = output_dir / "replay_dec4_heldout.json"
    receipt_path = output_dir / "score_receipt_dec4_heldout.json"
    for p in (manifest_path, replay_path, receipt_path):
        if p.exists():
            raise FileExistsError(f"Refusing to overwrite existing immutable artifact: {p}")

    db_url = os.environ["DATABASE_URL"]
    raw_rows, manifest_s = asyncio.run(_fetch_manifest_rows(db_url))
    manifest = assign_series_clusters(raw_rows)
    if not manifest:
        raise ValueError("No qualifying completed held-out events found in manifest query")

    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with manifest_path.open("xb") as f:
        f.write(manifest_bytes)

    all_packets: list[dict[str, Any]] = []
    spent = float(manifest_s)
    statements_total = 3
    for i in range(0, len(manifest), _BATCH_SIZE):
        batch = manifest[i : i + _BATCH_SIZE]
        packets, read_receipt = asyncio.run(
            blend_replay_export.read_packets(batch, seconds_used=spent)
        )
        spent = float(read_receipt["statement_seconds_after"])
        statements_total += int(read_receipt["statements"])
        for pkt in packets:
            if "read_failure" in pkt:
                raise RuntimeError(f"Packet read failure during export: {pkt['read_failure']}")
        all_packets.extend(packets)

    export = blend_replay_export.build_export(all_packets, recording_start)
    export["database_reads"] = {
        "manifest_events": len(manifest),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "statements": statements_total,
        "statement_seconds_total": round(spent, 3),
        "nightly_limit_seconds": blend_replay_export.MAX_STATEMENT_SECONDS,
        "statement_timeout_ms": 10_000,
        "read_only": True,
    }
    if export["result"] == "FAIL":
        raise RuntimeError(f"Export failed validation: {export['failures']}")

    replay_bytes = blend_replay_export.canonical(export) + b"\n"
    with replay_path.open("xb") as f:
        f.write(replay_bytes)
    export_sha256 = hashlib.sha256(replay_bytes).hexdigest()

    report = blend_scorer.score_export(export)
    report["baseline_result"] = report["result"]
    full_receipt = {
        "input_sha256": export_sha256,
        "protocol_sha256": PROTOCOL_SHA256,
        "candidate_sha256": None,
        "implementation_sha256": blend_scorer.implementation_hashes(),
        "manifest_events": len(manifest),
        "manifest_clusters": len({m["cluster_id"] for m in manifest}),
        "database_reads": export["database_reads"],
        **report,
    }
    receipt_bytes = (
        json.dumps(full_receipt, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    with receipt_path.open("xb") as f:
        f.write(receipt_bytes)

    return {
        "manifest_path": str(manifest_path),
        "replay_path": str(replay_path),
        "receipt_path": str(receipt_path),
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "export_sha256": export_sha256,
        "protocol_sha256": PROTOCOL_SHA256,
        "manifest_events": len(manifest),
        "manifest_clusters": len({m["cluster_id"] for m in manifest}),
        "database_reads": export["database_reads"],
        "receipt": full_receipt,
    }


def run_local_rehearsal(repo: Path) -> dict[str, Any]:
    """Prove pre-Dec-4 clock refusal AND rehearse full pipeline on synthetic local PG data."""
    # 1. Prove actual wall-clock date is strictly refused BEFORE any DB connection.
    real_clock_refusal = None
    try:
        enforce_dec4_gate()
    except ValueError as exc:
        real_clock_refusal = str(exc)
    if real_clock_refusal is None:
        raise AssertionError("Expected pre-Dec-4 clock gate to refuse today's wall clock!")

    _setup_sys_path(repo)
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models.models import Base
    from app.utils import busy_db_defer
    from app.utils.aggregation import compute_aggregate_probability_tiered
    from app.utils.probability_publication import BLEND_METHOD
    from scripts.evals import blend_replay_export

    db_name = "bl_dec4_kit_rehearsal_tmp"
    rehearsal_out = Path("/tmp/bl_dec4_rehearsal_out")
    shutil.rmtree(rehearsal_out, ignore_errors=True)
    subprocess.run(["dropdb", "-h", "/tmp", "--if-exists", db_name], check=True)
    subprocess.run(["createdb", "-h", "/tmp", db_name], check=True)

    sync_url = f"postgresql://bain@localhost:5432/{db_name}"
    async_url = f"postgresql+asyncpg://bain@localhost:5432/{db_name}"
    pg14_safe_tables = [
        t for t in Base.metadata.sorted_tables if t.name != "container_provider_anchors"
    ]
    old_db_url = os.environ.get("DATABASE_URL")
    orig_in_busy = busy_db_defer.in_busy_window
    try:
        async def _seed():
            engine = create_async_engine(async_url)
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=pg14_safe_tables))
                Session = async_sessionmaker(engine, expire_on_commit=False)
                async with Session() as s:
                    await s.execute(
                        text(
                            'INSERT INTO sports (id, key, name, "group", active) VALUES '
                            "(1, 'basketball_nba', 'NBA', 'Basketball', true), "
                            "(2, 'soccer_epl', 'EPL', 'Soccer', true)"
                        )
                    )
                    # 4 synthetic held-out games (including 1 two-game series) + 2 out-of-window controls
                    synthetic_events = [
                        # Out-of-window BEFORE Nov 6 recording_start (MUST be excluded)
                        (880001, 1, "syn-before", "Madeup PreA", "Madeup PreB",
                         datetime(2026, 11, 5, 18, 0, tzinfo=timezone.utc), "completed", 104, 98),
                        # Two-game series inside holdout (MUST share 1 cluster_id)
                        (880002, 1, "syn-s1", "Madeup Lions", "Madeup Bears",
                         datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc), "completed", 112, 105),
                        (880003, 1, "syn-s2", "Madeup Bears", "Madeup Lions",
                         datetime(2026, 11, 14, 20, 0, tzinfo=timezone.utc), "completed", 99, 108),
                        # Standalone NBA + EPL held-out games
                        (880004, 1, "syn-nba", "Madeup Hawks", "Madeup Owls",
                         datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc), "completed", 95, 102),
                        (880005, 2, "syn-epl", "Madeup Rovers", "Madeup United",
                         datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc), "completed", 2, 1),
                        # Out-of-window AFTER Dec 4 holdout_end (MUST be excluded)
                        (880006, 2, "syn-after", "Madeup PostA", "Madeup PostB",
                         datetime(2026, 12, 5, 18, 0, tzinfo=timezone.utc), "completed", 1, 0),
                    ]
                    for eid, sid, ext, hm, aw, ct, st, hs, as_ in synthetic_events:
                        await s.execute(
                            text(
                                "INSERT INTO events (id, sport_id, external_id, home_team_name, away_team_name, "
                                "commence_time, status, home_score, away_score) VALUES "
                                "(:eid, :sid, :ext, :hm, :aw, :ct, :st, :hs, :as)"
                            ),
                            {"eid": eid, "sid": sid, "ext": ext, "hm": hm, "aw": aw,
                             "ct": ct, "st": st, "hs": hs, "as": as_},
                        )

                    pub_cols = (
                        "(event_id, rev, schema_version, recorded_at, txn_started_at, sources, "
                        "event_status, blend_inputs, source_clocks, blend_probability, blend_tier, "
                        "blend_method, observations, coverage, removed_sources, uncovered_keys, "
                        "unobserved_bumps, queued_frame_matches, payload_sha256) "
                    )
                    oid = 1000
                    wid = 5000
                    from types import SimpleNamespace

                    for eid, sid, ext, hm, aw, ct, st, hs, as_ in synthetic_events:
                        base_books = [0.64, 0.66, 0.65] if hs > as_ else [0.40, 0.42, 0.41]
                        espn_p = 0.60 if hs > as_ else 0.45
                        kalshi_p = 0.62 if hs > as_ else 0.44
                        for rev_idx, hrs_before in enumerate([25, 7, 2, 0], start=1):
                            ts = ct - timedelta(hours=hrs_before, minutes=10)
                            vu = ct + timedelta(minutes=1)
                            delta = (rev_idx - 1) * 0.01 * (1 if hs > as_ else -1)
                            books = [round(p + delta, 4) for p in base_books]
                            for b_idx, b_name in enumerate(["book_alpha", "book_beta", "book_gamma"]):
                                oid += 1
                                await s.execute(
                                    text(
                                        "INSERT INTO odds_snapshots (id, event_id, bookmaker, captured_at, valid_until, reading_count, home_win_probability) "
                                        "VALUES (:id, :eid, :bm, :cap, :vu, 1, :p)"
                                    ),
                                    {"id": oid, "eid": eid, "bm": b_name, "cap": ts, "vu": vu, "p": books[b_idx]},
                                )
                            for s_name, s_p in [("espn", round(espn_p + delta, 4)), ("kalshi", round(kalshi_p + delta, 4))]:
                                wid += 1
                                await s.execute(
                                    text(
                                        "INSERT INTO win_prob_snapshots (id, event_id, source, captured_at, valid_until, reading_count, home_win_probability) "
                                        "VALUES (:id, :eid, :src, :cap, :vu, 1, :p)"
                                    ),
                                    {"id": wid, "eid": eid, "src": s_name, "cap": ts, "vu": vu, "p": s_p},
                                )
                            bet_med = sorted(books)[1]
                            sources_obj = {
                                "betting": {"value": bet_med, "updated_at": ts.isoformat()},
                                "espn": {"value": round(espn_p + delta, 4), "updated_at": ts.isoformat()},
                                "kalshi": {"value": round(kalshi_p + delta, 4), "updated_at": ts.isoformat()},
                            }
                            inputs = {"espn_win_prob_home": None, "opening_home_probability": None}
                            bp, btier = compute_aggregate_probability_tiered(
                                SimpleNamespace(win_probability_sources=sources_obj, status="scheduled", **inputs),
                                "scheduled",
                            )
                            clocks = {k: v["updated_at"] for k, v in sources_obj.items()}
                            await s.execute(
                                text(
                                    f"INSERT INTO probability_publications {pub_cols} VALUES "
                                    "(:eid, :rev, 1, :rec_at, :rec_at, CAST(:sources AS jsonb), 'scheduled', "
                                    "CAST(:inputs AS jsonb), CAST(:clocks AS jsonb), :bp, :btier, :bmethod, "
                                    "CAST('[]' AS jsonb), 'nonvenue_complete', CAST('[]' AS jsonb), "
                                    "CAST('[]' AS jsonb), 0, true, :sha)"
                                ),
                                {
                                    "eid": eid, "rev": rev_idx, "rec_at": ts,
                                    "sources": json.dumps(sources_obj),
                                    "inputs": json.dumps(inputs),
                                    "clocks": json.dumps(clocks),
                                    "bp": bp, "btier": btier, "bmethod": BLEND_METHOD,
                                    "sha": f"syn-{eid}-{rev_idx}",
                                },
                            )
                    await s.commit()
            finally:
                await engine.dispose()

        asyncio.run(_seed())
        os.environ["DATABASE_URL"] = sync_url
        # Rehearsal-only in-process simulation of Dec 4 off-peak clock (never active in --run).
        busy_db_defer.in_busy_window = lambda now=None: False
        res = run_heldout_pipeline(
            repo=repo,
            output_dir=rehearsal_out,
            read_window_clear=True,
            now_utc=datetime(2026, 12, 4, 9, 0, 0, tzinfo=timezone.utc),
            rehearsal_clock_bypass=True,
        )
        rec = res["receipt"]
        assert res["manifest_events"] == 4, res
        assert res["manifest_clusters"] == 3, res
        assert rec["result"] == "BASELINE_REPLAY_ONLY", rec
        assert rec["activation"] == "NONE", rec
        assert rec["recorded_reproduction"] == {"n": 16, "mismatches": 0}, rec
        assert rec["reconstruction_agreement"]["result"] == "PASS", rec
        assert all(c["split"] == "held_out" for c in rec["cohorts"]), rec["cohorts"]

        return {
            "rehearsal_status": "PASSED",
            "database": "disposable local postgres (0 production reads, 0 real games)",
            "pre_dec4_clock_refusal_check": real_clock_refusal,
            "simulated_rehearsal_clock_utc": "2026-12-04T09:00:00+00:00",
            "protocol_sha256": res["protocol_sha256"],
            "manifest_events": res["manifest_events"],
            "out_of_window_synthetic_events_excluded": 2,
            "manifest_clusters": res["manifest_clusters"],
            "export_sha256": res["export_sha256"],
            "receipt_sha256": res["receipt_sha256"],
            "database_reads": res["database_reads"],
            "score_receipt_summary": {
                "result": rec["result"],
                "activation": rec["activation"],
                "method": rec["method"],
                "failures": rec["failures"],
                "input_rows": rec["input_rows"],
                "recorded_reproduction": rec["recorded_reproduction"],
                "reconstruction_agreement": rec["reconstruction_agreement"],
                "coverage": rec["coverage"],
                "cohorts": rec["cohorts"],
                "blend_vs_sources": rec["blend_vs_sources"],
            },
        }
    finally:
        busy_db_defer.in_busy_window = orig_in_busy
        if old_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_db_url
        shutil.rmtree(rehearsal_out, ignore_errors=True)
        subprocess.run(["dropdb", "-h", "/tmp", "--if-exists", db_name], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--rehearsal", action="store_true")
    mode.add_argument("--print-sql", action="store_true")
    parser.add_argument("--repo", type=Path, default=Path("/Users/bain/bainluck"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--read-window-clear", action="store_true")
    args = parser.parse_args()

    if args.print_sql:
        print("=== 1. MANIFEST SQL (Dec 4 held-out events) ===")
        print(MANIFEST_SQL)
        for name, sql in PER_EVENT_SQLS:
            print(f"\n=== 2.{name.upper()} PER-EVENT SQL (inside blend_replay_export.read_packets) ===")
            print(sql)
        return 0

    if args.run:
        try:
            enforce_dec4_gate()
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if not args.output_dir or not args.read_window_clear:
            parser.error("--run requires --read-window-clear and --output-dir")
        out = run_heldout_pipeline(
            repo=args.repo,
            output_dir=args.output_dir,
            read_window_clear=args.read_window_clear,
        )
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    print(json.dumps(run_local_rehearsal(args.repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
