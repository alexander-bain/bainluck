"""#10009 — a Polymarket chart stops drawing the other side's price as this team's line.

THE SHIP. ``/events/15322407`` (Phillies at Braves, Wild Card Game 3, first pitch
2026-10-02 00:00Z), phone width, seen 2026-10-01 05:20Z: the Win Probability
chart is a solid block between ~45% and ~55% for two days ("Odds flipped (171)")
while the hero reads Braves 49 / Phillies 51.

------------------------------------------------------------------------------
WHY THESE ROWS ARE PROVABLY THE WRONG TOKEN'S PRICE
------------------------------------------------------------------------------

The chart backfill (``event_chart_backfill._polymarket_token_id``) picked a
leg's CLOB token as ``token_ids[rank - 1]``. ``rank`` is PRICE order, not token
order, so a ``…_no`` / ``…_side1`` leg ranked first, or a ``…_yes`` / bare leg
ranked second, fetched the OTHER side's book and stored it as its own YES price.
#10009's code half makes the leg's suffix pick the token (the socket's
``_token_index``); it cannot see a row already stored, and the rail's minute
dedup means it will never overwrite one.

Nothing here is inferred from rank, from names or from the shape of a curve.
Each row is asked of the VENUE: both tokens of the leg's condition are read from
CLOB ``/markets/{condition}`` and their ``prices-history`` is fetched with the
same calls the rail made, so a stored row's minute lands on a venue minute. A
row is flipped only when its stored YES price equals the WRONG token's price at
that minute, differs from the RIGHT token's, and the two tokens are complements
there (sum 1 within :data:`COMPLEMENT_TOLERANCE`). Measured on the specimen
2026-10-01 05:5xZ: the two tokens summed to exactly 1.000 at all 388 minutes,
and 324 of 347 stored rows equalled the Phillies token (22 sat at 0.50, where
both tokens agree, 1 had no venue minute).

The flip is ``p -> 1 - p`` on home, away and ``yes_probability``. Because the
tokens are complements, that is the right token's price exactly — no refetch,
and the minute stays occupied so a rail still on old code cannot re-add it.

------------------------------------------------------------------------------
HOW TO RUN IT (D51(b): backup first, one-command restore)
------------------------------------------------------------------------------

Dry run (default, writes nothing, prints the plan):

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_10009_polymarket_wrong_token_chart_rows.py

Apply:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_10009_polymarket_wrong_token_chart_rows.py --apply

The undo is one command:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_10009_polymarket_wrong_token_chart_rows.py --apply

Re-running is safe: a flipped row now equals the right token and is left, and
the UPDATE refuses any row already stamped ``token_repair``.

Runtime DDL (``CREATE TABLE IF NOT EXISTS backup_*``), attended invocation only,
refuses to run anywhere but ``bainluck-heavy`` — notice 47(c), not migration
class. Nothing here runs on merge or on release.

Gotcha #48: use ``run:detached`` and verify the side effect afterwards with the
verify query this script prints.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

#: Only this app may run it — notice 47(c).
PRODUCER_APP = "bainluck-heavy"

BACKUP_TABLE = "backup_10009_polymarket_wrong_token_chart_rows"

#: The stamp written into ``game_state`` of every flipped row.
REPAIR_STAMP = "10009"

#: How close a stored YES price must sit to a venue price to be that token's
#: reading (``yes_probability`` is rounded to 4 places at write).
MATCH_TOLERANCE = 0.0006

#: The two tokens must be complements at the row's minute for ``1 - p`` to BE
#: the right token's price.
COMPLEMENT_TOLERANCE = 0.0015

#: The always-included specimen.
SPECIMEN_EVENT_ID = 15322407

#: Row verdicts.
FLIP = "flip"
RIGHT = "right_token"
AMBIGUOUS = "both_tokens_agree"
UNMATCHED = "no_venue_minute"
NOT_COMPLEMENT = "tokens_not_complements"
NEITHER = "matches_neither_token"


def wrong_app_refusal() -> str | None:
    """Return a refusal string when not running on :data:`PRODUCER_APP`."""
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def venue_minutes(history: list[dict]) -> dict[datetime, float]:
    """``prices-history`` points keyed by the minute the rail would store them at."""
    from app.tasks.event_chart_backfill import minute_key

    out: dict[datetime, float] = {}
    for point in history or []:
        try:
            ts = minute_key(datetime.fromtimestamp(float(point["t"]), tz=timezone.utc))
            out.setdefault(ts, float(point["p"]))
        except (KeyError, TypeError, ValueError, OSError, OverflowError):
            continue
    return out


def classify_row(
    yes: float | None,
    right_price: float | None,
    wrong_price: float | None,
) -> str:
    """PURE. One stored row against the two venue tokens at its minute."""
    if yes is None or right_price is None or wrong_price is None:
        return UNMATCHED
    if abs(right_price + wrong_price - 1.0) > COMPLEMENT_TOLERANCE:
        return NOT_COMPLEMENT
    on_right = abs(yes - right_price) <= MATCH_TOLERANCE
    on_wrong = abs(yes - wrong_price) <= MATCH_TOLERANCE
    if on_right and on_wrong:
        return AMBIGUOUS
    if on_wrong:
        return FLIP
    if on_right:
        return RIGHT
    return NEITHER


def right_token_index(outcome_external_id: str | None) -> int | None:
    """The token this leg IS — the socket's own rule, the code half's rule."""
    from app.tasks.polymarket_ws import _token_index

    return _token_index(outcome_external_id or "")


async def _groups(session, days_back: int, days_ahead: int) -> list[dict]:
    """Every (event, market, leg) the rail wrote on events in the window."""
    result = await session.execute(
        text("""
            WITH ev AS (
                SELECT id, home_team_name, away_team_name, commence_time, status
                  FROM events
                 WHERE id = :specimen
                    OR commence_time BETWEEN now() - make_interval(days => :back)
                                         AND now() + make_interval(days => :ahead)
            )
            SELECT w.event_id,
                   (w.game_state->>'market_id')::bigint AS market_id,
                   w.game_state->>'outcome_name' AS leg,
                   count(*) AS rows,
                   min(ev.home_team_name) AS home, min(ev.away_team_name) AS away,
                   min(ev.commence_time) AS commence_time
              FROM win_prob_snapshots w
              JOIN ev ON ev.id = w.event_id
             WHERE w.source = 'polymarket'
               AND w.game_state->>'poll_type' = 'history_backfill'
             GROUP BY 1, 2, 3
             ORDER BY min(ev.commence_time), 1, 2, 3
        """),
        {"specimen": SPECIMEN_EVENT_ID, "back": days_back, "ahead": days_ahead},
    )
    return [dict(r) for r in result.mappings()]


async def _leg_external_id(session, market_id: int, leg: str) -> str | None:
    rows = (
        await session.execute(
            text(
                "SELECT external_id FROM futures_outcomes "
                "WHERE market_id = :mid AND name = :leg"
            ),
            {"mid": market_id, "leg": leg},
        )
    ).scalars().all()
    return rows[0] if len(rows) == 1 else None


async def _token_history(service, token_id: str) -> dict[datetime, float]:
    """Both fidelities the rail asks for, merged — so every stored minute can land."""
    merged: dict[datetime, float] = {}
    for fidelity in (1, 60):
        history = await service.get_prices_history(
            token_id=token_id, interval="max", fidelity=fidelity
        )
        for minute, price in venue_minutes(history).items():
            merged.setdefault(minute, price)
    return merged


async def _plan_group(session, service, group: dict) -> tuple[str | None, list[dict]]:
    """(skip reason or None, classified rows) for one group."""
    from app.tasks.event_chart_backfill import strip_leg_suffix

    ext = await _leg_external_id(session, group["market_id"], group["leg"])
    if ext is None:
        return "market no longer carries exactly one leg of that name", []
    right = right_token_index(ext)
    if right is None:
        return f"leg id {ext!r} names no token by suffix", []
    clob = await service.get_clob_market_by_condition(strip_leg_suffix(ext))
    tokens = [str(t.get("token_id") or "") for t in (clob or {}).get("tokens") or []]
    if len(tokens) != 2 or not all(tokens):
        return f"CLOB lists {len(tokens)} tokens for the condition, not 2", []
    stored = (
        await session.execute(
            text(
                # As text[] in SQL, so the driver's JSONB decoding never matters.
                "SELECT CASE WHEN jsonb_typeof(market_metadata->'clob_token_ids') = 'array' "
                "THEN ARRAY(SELECT jsonb_array_elements_text(market_metadata->'clob_token_ids')) "
                "END FROM futures_markets WHERE id = :mid"
            ),
            {"mid": group["market_id"]},
        )
    ).scalar()
    stored = [str(t) for t in (stored or [])]
    if set(stored) == set(tokens) and stored != tokens:
        # Same condition, different order: the token the leg IS is in doubt.
        return "stored clob_token_ids disagree with CLOB's token order", []
    right_prices = await _token_history(service, tokens[right])
    wrong_prices = await _token_history(service, tokens[1 - right])

    snaps = await session.execute(
        text("""
            SELECT id, captured_at, (game_state->>'yes_probability')::float AS yes,
                   game_state ? 'token_repair' AS stamped
              FROM win_prob_snapshots
             WHERE source = 'polymarket'
               AND event_id = :eid
               AND game_state->>'poll_type' = 'history_backfill'
               AND game_state->>'market_id' = :mid
               AND game_state->>'outcome_name' = :leg
        """),
        {"eid": group["event_id"], "mid": str(group["market_id"]), "leg": group["leg"]},
    )
    from app.tasks.event_chart_backfill import minute_key

    rows = []
    for r in snaps.mappings():
        minute = minute_key(r["captured_at"])
        verdict = classify_row(r["yes"], right_prices.get(minute), wrong_prices.get(minute))
        if r["stamped"] and verdict == FLIP:
            # Already flipped once; a second flip would undo it. Never.
            verdict = NEITHER
        rows.append({"id": r["id"], "verdict": verdict})
    return None, rows


async def bank_pre_image(session, ids: list[int]) -> None:
    """Bank whole rows before the first UPDATE. The FIRST pre-image is the true one."""
    await session.execute(
        text(f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
                snapshot_id          BIGINT PRIMARY KEY,
                event_id             BIGINT NOT NULL,
                home_win_probability NUMERIC(5, 4),
                away_win_probability NUMERIC(5, 4),
                game_state           JSONB,
                banked_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    )
    await session.execute(
        text(f"""
            INSERT INTO {BACKUP_TABLE}
                (snapshot_id, event_id, home_win_probability, away_win_probability,
                 game_state)
            SELECT id, event_id, home_win_probability, away_win_probability, game_state
              FROM win_prob_snapshots WHERE id = ANY(:ids)
            ON CONFLICT (snapshot_id) DO NOTHING
        """),
        {"ids": ids},
    )


#: The write. Re-asserts source, poll type and the absent stamp in the WHERE,
#: so a row changed between the read and here is not flipped on a stale read.
FLIP_SQL = """
    UPDATE win_prob_snapshots
       SET home_win_probability = 1 - home_win_probability,
           away_win_probability = 1 - away_win_probability,
           game_state = game_state || jsonb_build_object(
               'yes_probability',
               round((1 - (game_state->>'yes_probability')::numeric), 4),
               'token_repair', CAST(:stamp AS text)
           )
     WHERE id = ANY(:ids)
       AND source = 'polymarket'
       AND game_state->>'poll_type' = 'history_backfill'
       AND NOT (game_state ? 'token_repair')
"""


async def run(apply: bool, days_back: int, days_ahead: int) -> int:
    if apply:
        refusal = wrong_app_refusal()
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2

    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.base import get_task_session

    service = PolymarketAPIService()
    try:
        async with get_task_session() as session:
            groups = await _groups(session, days_back, days_ahead)
            print(f"#10009 — {'APPLY' if apply else 'DRY RUN'}")
            print(f"  window              : -{days_back}d .. +{days_ahead}d (+ event {SPECIMEN_EVENT_ID})")
            print(f"  groups              : {len(groups)}")

            flip_ids: list[int] = []
            for group in groups:
                label = (
                    f"{group['event_id']}  {group['commence_time']:%Y-%m-%d %H:%M}Z  "
                    f"{group['home']} v {group['away']}  leg={group['leg']!r} "
                    f"market={group['market_id']}"
                )
                try:
                    why, rows = await _plan_group(session, service, group)
                except Exception as exc:  # noqa: BLE001 — one group, not the run
                    print(f"    SKIP {label}: venue read failed: {str(exc)[:120]}")
                    continue
                if why:
                    print(f"    SKIP {label}: {why}")
                    continue
                tally: dict[str, int] = {}
                for r in rows:
                    tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
                ids = [r["id"] for r in rows if r["verdict"] == FLIP]
                flip_ids.extend(ids)
                if ids or tally.get(NEITHER) or tally.get(NOT_COMPLEMENT):
                    print(f"    {label}  {len(rows)} rows {tally}")

            flip_ids = sorted(set(flip_ids))
            print(f"  rows to flip        : {len(flip_ids)}")
            if not apply:
                print("\ndry run — nothing written. Re-run with --apply.")
                return 0
            if not flip_ids:
                print("\nnothing to write.")
                return 0

            await bank_pre_image(session, flip_ids)
            banked = (
                await session.execute(
                    text(f"SELECT count(*) FROM {BACKUP_TABLE} WHERE snapshot_id = ANY(:ids)"),
                    {"ids": flip_ids},
                )
            ).scalar()
            if banked != len(flip_ids):
                await session.rollback()
                print(f"REFUSED: banked {banked} of {len(flip_ids)} rows — nothing written")
                return 1

            result = await session.execute(
                text(FLIP_SQL), {"ids": flip_ids, "stamp": REPAIR_STAMP}
            )
            flipped = result.rowcount or 0
            await session.commit()

            drift = len(flip_ids) - flipped
            print(f"\n  pre-image banked in : {BACKUP_TABLE} ({banked} rows)")
            print(f"  rows flipped        : {flipped}")
            print(f"  concurrent_drift    : {drift}")
            print(
                "\nverify: SELECT count(*) FROM win_prob_snapshots "
                f"WHERE game_state->>'token_repair' = '{REPAIR_STAMP}';  -- expect {flipped}+"
            )
            print(
                "undo: python3 scripts/restore_10009_polymarket_wrong_token_chart_rows.py --apply"
            )
            return 0 if drift == 0 else 1
    finally:
        await service.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--days-back", type=int, default=14)
    parser.add_argument("--days-ahead", type=int, default=14)
    args = parser.parse_args()
    return asyncio.run(run(args.apply, args.days_back, args.days_ahead))


if __name__ == "__main__":
    raise SystemExit(main())
