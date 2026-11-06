"""#12108 PR 2: freeze per-event replay inputs; never write a database.

Extends calibration_population_integrity (ruling 002).

Offline: python -m scripts.evals.blend_replay_export --input packets.json \
  --recording-start 2026-11-06T05:00:00Z --output replay.json

Packets contain event metadata, odds_snapshots, win_prob_snapshots and
publications from an independent read. Historical values are reconstructions,
not receipts of a served probability. In particular, valid_until is the last
confirmation, not proof of the complete book population or a source removal.
The recorded sources/status/blend_inputs remain verbatim on served rows.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from app.utils.aggregation import SOURCE_WEIGHTS
from app.utils.book_consensus import median_invents_its_answer
from app.utils.publication_reader import HORIZONS, select_horizon_rows

SCHEMA = "blend-replay/1"
MAX_ROWS_PER_EVENT_TABLE = 20_000
MAX_STATEMENT_SECONDS = 30 * 60


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return instant(value).isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


async def read_packets(
    manifest: list[dict], *, seconds_used: float
) -> tuple[list, dict]:
    """Explicit event ids, index-bounded reads, readonly transactions and 10s caps.

    The measurement owner supplies the already-spent nightly statement time;
    the returned receipt carries it forward. A run needs the entire off-peak
    slot clear of attended folds/applies. There is no scheduled collector.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.utils.busy_db_defer import in_busy_window

    if not math.isfinite(seconds_used) or not 0 <= seconds_used < MAX_STATEMENT_SECONDS:
        raise ValueError("nightly statement budget is exhausted or unknown")
    if not manifest or len(manifest) > 1000:
        raise ValueError("manifest must name 1..1000 explicit events")
    ids = [int(e["event_id"]) for e in manifest]
    if len(set(ids)) != len(ids) or any(i <= 0 for i in ids):
        raise ValueError("manifest event ids must be unique and positive")
    if any(
        not isinstance(e.get("cluster_id"), str) or not e["cluster_id"]
        for e in manifest
    ):
        raise ValueError("manifest must preserve series/doubleheader groups")
    if in_busy_window():
        raise ValueError("off-peak read window is closed")
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("PostgreSQL DATABASE_URL required")
    engine = create_async_engine(
        url,
        connect_args={
            "server_settings": {
                "default_transaction_read_only": "on",
                "statement_timeout": "10000",
            }
        },
    )
    packets, spent, statements = [], seconds_used, 0

    async def read(conn, sql, params):
        nonlocal spent, statements
        if in_busy_window():
            raise ValueError("read window closed during export")
        remaining_ms = math.floor((MAX_STATEMENT_SECONDS - spent) * 1000)
        if remaining_ms < 1:
            raise ValueError("nightly statement budget exhausted")
        timeout = min(10_000, remaining_ms)
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout / 1000):
                await conn.execute(text(f"SET LOCAL statement_timeout = {timeout}"))
                result = await conn.execute(text(sql), params)
                rows = [dict(r) for r in result.mappings()]
            if len(rows) > MAX_ROWS_PER_EVENT_TABLE:
                raise ValueError("per-event row cap exceeded; no truncated packet")
            return json_value(rows)
        finally:
            spent += time.monotonic() - started
            statements += 1

    try:
        async with engine.connect() as conn:
            for entry in manifest:
                async with conn.begin():
                    await conn.execute(text("SET TRANSACTION READ ONLY"))
                    # Event primary key and its sport primary key, no population scan.
                    events = await read(
                        conn,
                        """
                        SELECT e.id, e.commence_time AS start, e.status,
                               e.home_score, e.away_score, s.key AS league
                          FROM events e JOIN sports s ON s.id = e.sport_id
                         WHERE e.id = :event_id
                    """,
                        {"event_id": entry["event_id"]},
                    )
                    if not events:
                        raise ValueError("manifest event does not exist")
                    event = events[0]
                    event["cluster_id"] = entry["cluster_id"]
                    home, away = event.pop("home_score"), event.pop("away_score")
                    event["outcome"] = (
                        int(home > away)
                        if event["status"] in {"completed", "closed"}
                        and home is not None
                        and away is not None
                        else None
                    )
                    params = {
                        "event_id": entry["event_id"],
                        "start": instant(event["start"]),
                        "limit": MAX_ROWS_PER_EVENT_TABLE + 1,
                    }
                    packet = {"event": event}
                    for table, columns, tail in (
                        (
                            "odds_snapshots",
                            "id, bookmaker, captured_at, valid_until, home_win_probability",
                            "captured_at, id",
                        ),
                        (
                            "win_prob_snapshots",
                            "id, source, captured_at, valid_until, home_win_probability",
                            "captured_at, id",
                        ),
                        (
                            "probability_publications",
                            "rev, recorded_at, sources, event_status, blend_inputs, source_clocks, blend_probability, blend_tier, blend_method, payload_sha256",
                            "rev",
                        ),
                    ):
                        # Identifiers are fixed literals above; event ids are binds.
                        clock = (
                            "recorded_at"
                            if table == "probability_publications"
                            else "captured_at"
                        )
                        rows = await read(
                            conn,
                            f"SELECT {columns} FROM {table} "
                            f"WHERE event_id = :event_id AND {clock} <= :start "
                            f"ORDER BY {tail} LIMIT :limit",
                            params,
                        )
                        packet[
                            (
                                "publications"
                                if table == "probability_publications"
                                else table
                            )
                        ] = rows
                    packets.append(packet)
                    await conn.rollback()
    except (SQLAlchemyError, ValueError, TimeoutError) as exc:
        # Preserve a failed read in the export and its consumed budget. Never
        # print a driver exception/URL which could contain connection details.
        packets.append({"read_failure": type(exc).__name__})
    finally:
        await engine.dispose()
    return packets, {
        "statements": statements,
        "statement_seconds_before": seconds_used,
        "statement_seconds_after": spent,
        "nightly_limit_seconds": MAX_STATEMENT_SECONDS,
        "statement_timeout_ms": 10_000,
        "read_only": True,
    }


def instant(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("an explicit UTC offset is required")
    return parsed.astimezone(timezone.utc)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def probability(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("a probability must be numeric, not boolean")
    p = float(value)
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("probability outside [0,1]")
    return p


def rebuild_betting(books: list[dict]) -> dict:
    """The producer's median, rounding, floor and split decision, unchanged.

    Caller supplies a reconstructed population. This does not establish that
    the population equals the producer's original listing.
    """
    from app.tasks.odds_polling import BETTING_BOOK_FLOOR

    values = [
        probability(row["home_win_probability"])
        for row in books
        if row.get("home_win_probability")  # producer deliberately skips zero
    ]
    middle = median(values) if values else None
    split = median_invents_its_answer(values)
    reason = (
        "no_readings"
        if not values
        else (
            "split"
            if split is not None
            else "below_floor" if len(values) < BETTING_BOOK_FLOOR else None
        )
    )
    return {
        "value": round(middle, 4) if reason is None else None,
        "median": middle,
        "book_count": len(values),
        "floor": BETTING_BOOK_FLOOR,
        "split": list(split) if split else None,
        "refusal": reason,
    }


def confirmed_readings(rows: list[dict], at: datetime, key: str) -> list[dict]:
    """Latest observed value per key, only within its confirmation bounds.

    No forward fill beyond the last confirmed timestamp. Ties without a unique
    row id fail instead of letting input order choose the reconstructed value.
    """
    selected: dict[str, tuple[tuple[datetime, int], dict]] = {}
    for row in rows:
        captured = instant(row["captured_at"])
        end = instant(row.get("valid_until") or row["captured_at"])
        if end < captured:
            raise ValueError("confirmation precedes capture")
        if not captured <= at <= end:
            continue
        identity = str(row[key])
        order = (captured, int(row["id"]))
        if identity in selected and order == selected[identity][0]:
            raise ValueError("duplicate snapshot identity")
        if identity not in selected or order > selected[identity][0]:
            selected[identity] = (order, row)
    return [selected[k][1] for k in sorted(selected)]


def reconstruction(packet: dict, at: datetime) -> dict:
    books = confirmed_readings(packet["odds_snapshots"], at, "bookmaker")
    betting = rebuild_betting(books)
    snapshots = confirmed_readings(packet["win_prob_snapshots"], at, "source")
    sources: dict[str, Any] = {}
    for row in snapshots:
        source = row["source"]
        if source in SOURCE_WEIGHTS and source != "betting":
            if row.get("home_win_probability") is not None:
                sources[source] = {
                    "value": probability(row["home_win_probability"]),
                    "updated_at": instant(row["captured_at"]).isoformat(),
                }
    if betting["value"] is not None:
        stamp = max(instant(b["captured_at"]) for b in books)
        sources["betting"] = {
            "value": betting["value"],
            "updated_at": stamp.isoformat(),
        }
    sources["betting_book_count"] = betting["book_count"]
    return {
        "kind": "reconstruction",
        "sources": sources,
        "source_clocks": {
            name: entry["updated_at"]
            for name, entry in sources.items()
            if name in SOURCE_WEIGHTS
        },
        "event_status": "scheduled",
        # A mutable current event fallback cannot be passed off as historical.
        "blend_inputs": {
            "espn_win_prob_home": None,
            "opening_home_probability": None,
        },
        "reconstruction_evidence": {
            "betting": betting,
            "books": books,
            "book_snapshot_ids": [b["id"] for b in books],
            "source_snapshot_ids": [s["id"] for s in snapshots],
            "clock_basis": "capture_not_original_writer_stamp",
            "population_basis": "within_last_confirmation_bounds",
            "historical_fallbacks": "unestablished",
        },
    }


def time_split(start: datetime, recording_start: datetime, league: str) -> str:
    lower = datetime(2026, 9, 1, tzinfo=timezone.utc)
    if league.startswith("soccer_"):
        lower = datetime(2026, 9, 16, tzinfo=timezone.utc)
    if start < lower:
        return "excluded_before_window"
    if start < datetime(2026, 10, 16, tzinfo=timezone.utc):
        return "train"
    if start < recording_start:
        return "tune"
    if start < recording_start + timedelta(weeks=4):
        return "held_out"
    return "excluded_after_window"


def build_export(packets: list[dict], recording_start: datetime) -> dict:
    rows, failures, coverage = [], [], []
    events_seen: set[int] = set()
    clusters: dict[str, str] = {}
    for packet_index, packet in enumerate(packets):
        try:
            event = packet["event"]
            event_id = int(event["id"])
            if event_id in events_seen:
                raise ValueError("duplicate event packet")
            events_seen.add(event_id)
            start = instant(event["start"])
            league, cluster = event["league"], event["cluster_id"]
            if not isinstance(cluster, str) or not cluster:
                raise ValueError("explicit series/doubleheader cluster_id required")
            split = time_split(start, recording_start, league)
            if cluster in clusters and clusters[cluster] != split:
                raise ValueError("series/doubleheader crosses time splits")
            clusters[cluster] = split
            outcome = event["outcome"]
            if outcome not in (0, 1) or isinstance(outcome, bool):
                raise ValueError("binary home-win outcome must be known")
            publications = packet["publications"]
            if split == "held_out":
                publications = [
                    p
                    for p in publications
                    if instant(p["recorded_at"]) >= recording_start
                ]
            selected = select_horizon_rows(
                [
                    (p["rev"], instant(p["recorded_at"]), p["blend_probability"])
                    for p in publications
                ],
                start,
            )
            by_rev = {int(p["rev"]): p for p in publications}
            if len(by_rev) != len(publications):
                raise ValueError("duplicate publication revision")
            event_rows = []
            for horizon, offset in HORIZONS:
                at = start - offset
                base = {
                    "event_id": event_id,
                    "cluster_id": cluster,
                    "league": league,
                    "start": start.isoformat(),
                    "at": at.isoformat(),
                    "horizon": horizon,
                    "split": split,
                    "outcome": outcome,
                    "target": "home_win",
                }
                publication = (
                    by_rev[selected[horizon]["rev"]]
                    if selected[horizon] is not None
                    else None
                )
                reconstructed_at = (
                    instant(publication["recorded_at"]) if publication else at
                )
                reconstructed = reconstruction(packet, reconstructed_at)
                reconstructed["reconstructed_at"] = reconstructed_at.isoformat()
                if publication:
                    # Known inputs from this exact stored instant; never take
                    # the mutable event's present-day fallback or status.
                    reconstructed["event_status"] = publication["event_status"]
                    reconstructed["blend_inputs"] = publication["blend_inputs"]
                    reconstructed["reconstruction_evidence"][
                        "historical_fallbacks"
                    ] = "recorded_overlap"
                event_rows.append({**base, **reconstructed})
                coverage.append(
                    {
                        "event_id": event_id,
                        "league": league,
                        "horizon": horizon,
                        "split": split,
                        "recorded": publication is not None,
                        "recorded_probability": publication is not None
                        and publication["blend_probability"] is not None,
                    }
                )
                # Held-out rows are prospective recorded values only.
                if selected[horizon] is not None:
                    event_rows.append(
                        {
                            **base,
                            "kind": "served",
                            **{
                                k: publication[k]
                                for k in (
                                    "sources",
                                    "event_status",
                                    "blend_inputs",
                                    "source_clocks",
                                    "blend_probability",
                                    "blend_tier",
                                    "blend_method",
                                    "rev",
                                    "recorded_at",
                                    "payload_sha256",
                                )
                            },
                        }
                    )
            rows.extend(event_rows)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            failures.append({"packet_index": packet_index, "reason": str(exc)})
    return {
        "schema": SCHEMA,
        "recording_start": recording_start.isoformat(),
        "source_packets_sha256": digest(packets),
        "rows": rows,
        "coverage": coverage,
        "failures": failures,
        "result": "FAIL" if failures or not rows else "EXPORTED_NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input", type=Path)
    mode.add_argument("--database", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--read-window-clear",
        action="store_true",
        help="Owner attests the whole off-peak slot is free of attended folds/applies",
    )
    parser.add_argument(
        "--statement-seconds-used",
        type=float,
        help="Statement seconds already spent in this night's 30-minute budget",
    )
    parser.add_argument("--recording-start", type=instant, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.database:
        if (
            not args.manifest
            or not args.read_window_clear
            or args.statement_seconds_used is None
        ):
            parser.error(
                "database mode needs manifest, clear read window, and prior nightly statement time"
            )
    # Reserve the immutable destination before any database work, so an
    # existing receipt cannot cause us to spend the same read budget again.
    with args.output.open("xb") as output:
        read_receipt = None
        if args.database:
            packets, read_receipt = asyncio.run(
                read_packets(
                    json.loads(args.manifest.read_bytes()),
                    seconds_used=args.statement_seconds_used,
                )
            )
        else:
            packets = json.loads(args.input.read_bytes())
        if not isinstance(packets, list):
            parser.error("input must be a list of per-event packets")
        export = build_export(packets, args.recording_start)
        export["database_reads"] = read_receipt
        output.write(canonical(export) + b"\n")
    print(
        json.dumps(
            {
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "rows": len(export["rows"]),
                "failures": len(export["failures"]),
                "result": export["result"],
            }
        )
    )
    return 1 if export["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
