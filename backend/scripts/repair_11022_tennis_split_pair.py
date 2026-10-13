"""#11022 — one Santa Cruz 2 match, one page carrying both venues.

THE SHIP: the reader opens one Justo–Huertas Del Pino Cordova page and gets
both Kalshi's and Polymarket's probability on it.

WHY (production read 2026-10-13 22:4xZ)
---------------------------------------

The match lives on two live rows, one venue each, both id-less:

* 15329605 "Guido Justo" v "Arklon Del Pino", ``tennis_other``, minted at
  07:37Z by Polymarket group ``polymarket:1181127``. Its winner market 65624229
  is condition ``0xad76c3f9…``, the one on the user-supplied page
  ``polymarket.com/sports/atp/atp-justo-pin-2026-10-13``, titled "Santa Cruz 2:
  Guido Justo vs Arklon Del Pino".
* 15329612 "Justo" v "Huertas Del Pino Cordova", ``tennis_atp``, minted at
  08:19Z by Kalshi market 65633052 ``KXATPCHALLENGERMATCH-26OCT13JUSHUE``
  (competition "ATP Challenger Santa Cruz 2"; contracts "Guido Ivan Justo" /
  "Arklon Huertas Del Pino Cordova").

The Kalshi market's receipt (11275879, pass1_ticker) shows it retrieved
15329605 inside its window and refused it ``name_mismatch``: Kalshi's title
surname "Huertas Del Pino Cordova" and Polymarket's "Arklon Del Pino" share no
name the gate accepts. The forward fix (same change) retries on the contracts'
own full names; this script repairs the one row already minted.

THE RULE: one reviewed pair, and every witness must still hold
--------------------------------------------------------------

The market moves only when ALL of these read true at run time:

1. the market is Kalshi, a tennis match ticker, and still on 15329612;
2. 15329612 is market-born and id-less (no ``external_id``, ``espn_id``,
   ``statpal_fixture_id``), carries no score or ``completed_at``, is not
   retired, and holds no market but this one;
3. 15329605 is a tennis row, not retired (a finished match still takes the
   move: the settled page then carries both results), and holds the user's
   Polymarket condition;
4. THE FORWARD GATE ACCEPTS IT: the contracts' names rebuild the matchup
   (``kalshi_contract_name_matchup``, one contract per title side) and the
   unchanged ``_score_candidates`` picks 15329605 — both sides, opposite sides,
   pair shape, tennis family — and records which side is home;
5. the ticker's date does not conflict with 15329605's start
   (``_ticker_date_conflicts_with_event``, the matcher's own rule);
6. THE TOURNAMENT IS NAMED BY BOTH VENUES: a Polymarket market on 15329605 is
   titled "<label>: …" and Kalshi's competition ends with that same label.

WHAT IS WRITTEN, AND WHAT IS NOT
--------------------------------

``futures_markets.event_id`` of 65633052 only, compare-and-swap on 15329612,
then one ``market_link_changes`` row (actor ``admin_repair``, phase
``repair_11022``). No event row is written, tagged, merged or deleted. 15329612
then reads as 15329605 through the existing market-born drain verdict
(``anchor_channel.resolve_market_born_duplicate``): its only anchor is the
Kalshi ticker, and that market now sits on 15329605. The verdict is recomputed
on every read, so moving the market back un-drains the row. The run reports the
verdict after the commit; ``drain_verdict`` must be 15329605.

The reviewer's question: the drain verdict's docstring assumes the market's
current row was chosen from a provider id. This move is chosen from the two
venues' own contracts and tournament label, reviewed by a person; it is not an
id-anchored correspondence.

THE REVIEWED PLAN IS THE ONLY PLAN APPLIED
------------------------------------------

The dry run prints ``plan_digest`` (sha256 over the move and every witness
above). ``--apply`` requires ``--plan-digest`` and refuses, before the backup,
unless the plan it builds now hashes to exactly that.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` banks ``(market_id, event_id_before, event_id_after)`` in
``bak_11022_split_pair`` and refuses to write if the bank is short.
``--restore`` moves the banked market back if it is still on
``event_id_after``. ``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a
person's invocation on a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_11022_tennis_split_pair.py                        # dry run; prints plan_digest
    heroku run:detached -a bainluck -- python3 scripts/repair_11022_tennis_split_pair.py --apply --plan-digest <sha256>
    heroku run:detached -a bainluck -- python3 scripts/repair_11022_tennis_split_pair.py --restore              # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_TABLE = "bak_11022_split_pair"
PHASE = "repair_11022"

MARKET_ID = 65633052
TICKER = "KXATPCHALLENGERMATCH-26OCT13JUSHUE"
FROM_EVENT_ID = 15329612
TO_EVENT_ID = 15329605
#: The user-supplied Polymarket page's condition (atp-justo-pin-2026-10-13).
PM_CONDITION = "0xad76c3f95ad3a76f6aaa78f49fc1e82f617cba0261005effde12ba09dd9c33ea"

RETIRED = frozenset({"merged", "voided"})

DRY_RUN = "DRY_RUN"
APPLIED = "APPLIED"
ROLLED_BACK_CHANGED_UNDER_RUN = "ROLLED_BACK_CHANGED_UNDER_RUN"
ROLLED_BACK_ERROR = "ROLLED_BACK_ERROR"
COMMIT_UNCERTAIN = "COMMIT_UNCERTAIN"
APPLIED_POSTCOMMIT_UNVERIFIED = "APPLIED_POSTCOMMIT_UNVERIFIED"
APPLIED_NOT_DRAINED = "APPLIED_NOT_DRAINED"
RESTORED = "RESTORED"
NOTHING_TO_RESTORE = "NOTHING_TO_RESTORE"
RESTORE_SHORT = "RESTORE_SHORT"
CLEAN_OUTCOMES = frozenset({DRY_RUN, APPLIED, RESTORED, NOTHING_TO_RESTORE})

UNDO_LINE = (
    "heroku run:detached -a bainluck -- "
    "python3 scripts/repair_11022_tennis_split_pair.py --restore"
)


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def _tournament_label(pm_names: list[str], competition: Optional[str]) -> Optional[str]:
    """The "<label>: …" prefix of a Polymarket title that Kalshi's competition ends with."""
    comp = " ".join((competition or "").lower().split())
    if not comp:
        return None
    for name in pm_names:
        label, colon, rest = (name or "").partition(":")
        label = " ".join(label.lower().split())
        if colon and label and rest.strip() and (comp == label or comp.endswith(" " + label)):
            return label
    return None


def decide(*, market: dict, outcomes: list[str], from_row: Optional[dict],
           to_row: Optional[dict], from_market_ids: list[int],
           to_markets: list[dict], now: datetime) -> dict:
    """Every refusal and the witness for the one reviewed move. Pure."""
    from app.tasks.prediction_market_matching import (
        _kalshi_prefix,
        _score_candidates,
        _ticker_date_conflicts_with_event,
    )
    from app.utils.prediction_market_matching import (
        extract_game_date_from_ticker,
        extract_matchup_with_ticker_fallback,
        is_kalshi_tennis_match_ticker,
        kalshi_contract_name_matchup,
    )

    refusals: list[str] = []
    witness: dict = {}

    if market.get("source") != "kalshi" or market.get("external_id") != TICKER:
        refusals.append("market_is_not_the_reviewed_kalshi_ticker")
    if not is_kalshi_tennis_match_ticker(market.get("external_id")):
        refusals.append("not_a_kalshi_tennis_match_ticker")
    if market.get("event_id") != FROM_EVENT_ID:
        refusals.append("market_not_on_from_event")

    if from_row is None:
        refusals.append("from_event_missing")
    else:
        if from_row.get("status") in RETIRED:
            refusals.append("from_event_retired")
        if any(from_row.get(k) for k in ("external_id", "espn_id", "statpal_fixture_id")):
            refusals.append("from_event_carries_a_provider_id")
        if (from_row.get("home_score") is not None or from_row.get("away_score") is not None
                or from_row.get("completed_at") is not None):
            refusals.append("from_event_carries_a_result")
        if from_row.get("commence_time_source") != "kalshi":
            refusals.append("from_event_not_kalshi_born")
    if sorted(from_market_ids) != [MARKET_ID]:
        refusals.append("from_event_holds_other_markets")

    if to_row is None:
        refusals.append("to_event_missing")
        return {"refusals": refusals, "witness": witness}
    if to_row.get("status") in RETIRED:
        refusals.append("to_event_retired")
    if not str(to_row.get("sport_key") or "").startswith("tennis"):
        refusals.append("to_event_not_tennis")
    if not any(m.get("external_id") == PM_CONDITION for m in to_markets):
        refusals.append("to_event_lacks_the_user_polymarket_condition")

    title = extract_matchup_with_ticker_fallback(market.get("name") or "", external_id=TICKER)
    contract = kalshi_contract_name_matchup(title, outcomes)
    witness["title"] = [title.team_a, title.team_b] if title else None
    witness["contracts"] = [contract.team_a, contract.team_b] if contract else None
    game_date = extract_game_date_from_ticker(TICKER)
    to_ns = SimpleNamespace(
        id=to_row["id"], sport=SimpleNamespace(key=to_row.get("sport_key")),
        home_team_name=to_row.get("home_team_name"),
        away_team_name=to_row.get("away_team_name"),
        commence_time=to_row.get("commence_time"), status=to_row.get("status"),
        external_id=to_row.get("external_id"), sport_id=to_row.get("sport_id"),
    )
    market_ns = SimpleNamespace(
        id=MARKET_ID, external_id=TICKER, name=market.get("name"), source="kalshi",
        llm_sport_category=market.get("llm_sport_category"), commence_time=None,
    )
    witness["to_event"] = [to_row.get("home_team_name"), to_row.get("away_team_name")]
    if contract is None:
        refusals.append("contracts_do_not_rename_both_title_sides")
    else:
        chosen = _score_candidates([to_ns], contract, market_ns, now, game_date)
        if not chosen or chosen.get("event_id") != TO_EVENT_ID:
            refusals.append("forward_gate_refuses_the_target")
        else:
            witness["yes_is_home"] = bool(chosen["yes_is_home"])
    if _ticker_date_conflicts_with_event(
        game_date, to_row.get("commence_time"), _kalshi_prefix(TICKER),
    ):
        refusals.append("ticker_date_conflicts_with_target_start")
    witness["ticker_date"] = game_date.isoformat() if game_date else None
    witness["to_commence"] = (
        to_row["commence_time"].isoformat() if to_row.get("commence_time") else None
    )

    label = _tournament_label(
        [m.get("name") or "" for m in to_markets if m.get("source") == "polymarket"],
        market.get("competition"),
    )
    witness["competition"] = market.get("competition")
    witness["tournament_label"] = label
    if label is None:
        refusals.append("venues_do_not_name_one_tournament")
    return {"refusals": refusals, "witness": witness}


def plan_digest(witness: dict) -> str:
    body = {
        "market_id": MARKET_ID, "external_id": TICKER,
        "from_event_id": FROM_EVENT_ID, "to_event_id": TO_EVENT_ID,
        "witness": witness,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()
    ).hexdigest()


async def read_state(session) -> dict:
    m = (await session.execute(text(
        "SELECT id, source, external_id, name, event_id, llm_sport_category, "
        "market_metadata->>'competition' AS competition "
        "FROM futures_markets WHERE id = :id"), {"id": MARKET_ID})).mappings().first()
    outcomes = [r[0] for r in await session.execute(text(
        "SELECT name FROM futures_outcomes WHERE market_id = :id ORDER BY id"),
        {"id": MARKET_ID})]
    rows = {int(r["id"]): dict(r) for r in (await session.execute(text(
        "SELECT e.id, e.status, e.external_id, e.espn_id, e.statpal_fixture_id, "
        "e.home_score, e.away_score, e.completed_at, e.commence_time, "
        "e.commence_time_source, e.home_team_name, e.away_team_name, e.sport_id, "
        "s.key AS sport_key FROM events e LEFT JOIN sports s ON s.id = e.sport_id "
        "WHERE e.id IN (:a, :b)"), {"a": FROM_EVENT_ID, "b": TO_EVENT_ID})).mappings()}
    from_market_ids = [int(r[0]) for r in await session.execute(text(
        "SELECT id FROM futures_markets WHERE event_id = :e"), {"e": FROM_EVENT_ID})]
    to_markets = [dict(r) for r in (await session.execute(text(
        "SELECT id, source, external_id, name FROM futures_markets WHERE event_id = :e"),
        {"e": TO_EVENT_ID})).mappings()]
    return {
        "market": dict(m) if m else {}, "outcomes": outcomes,
        "from_row": rows.get(FROM_EVENT_ID), "to_row": rows.get(TO_EVENT_ID),
        "from_market_ids": from_market_ids, "to_markets": to_markets,
    }


async def _backup(session) -> bool:
    await session.execute(text(
        f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
        " market_id bigint PRIMARY KEY,"
        " event_id_before integer NOT NULL,"
        " event_id_after integer NOT NULL,"
        " taken_at timestamptz NOT NULL DEFAULT now(),"
        " applied_at timestamptz)"))
    await session.execute(text(
        f"INSERT INTO {BACKUP_TABLE} (market_id, event_id_before, event_id_after) "
        "VALUES (:m, :b, :a) ON CONFLICT (market_id) DO NOTHING"),
        {"m": MARKET_ID, "b": FROM_EVENT_ID, "a": TO_EVENT_ID})
    await session.commit()
    row = (await session.execute(text(
        f"SELECT event_id_before, event_id_after FROM {BACKUP_TABLE} WHERE market_id = :m"),
        {"m": MARKET_ID})).first()
    return row is not None and (int(row[0]), int(row[1])) == (FROM_EVENT_ID, TO_EVENT_ID)


async def _cas(session, old: int, new: int) -> bool:
    result = await session.execute(text(
        "UPDATE futures_markets SET event_id = :new "
        "WHERE id = :id AND event_id = :old "
        "AND EXISTS (SELECT 1 FROM events WHERE id = :new "
        "AND status NOT IN ('merged', 'voided'))"),
        {"id": MARKET_ID, "old": old, "new": new})
    return result.rowcount == 1


async def _quiet_rollback(session) -> None:
    try:
        await session.rollback()
    except Exception:
        pass


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


async def _receipt(market: dict, old: int, new: int) -> int:
    from app.utils.match_receipts import ACTOR_ADMIN_REPAIR, record_link_change_receipts

    return await record_link_change_receipts(
        [{"id": MARKET_ID, "source": "kalshi", "external_id": TICKER,
          "name": market.get("name")}],
        previous_event_id=old, new_event_id=new,
        actor=ACTOR_ADMIN_REPAIR, phase=PHASE,
    )


async def _postcommit(session, market: dict, old: int, new: int, out: dict) -> dict:
    """Receipt, read-back and drain verdict. Never raises: the write has landed."""
    errors = {}
    try:
        out["receipts"] = await _receipt(market, old, new)
    except Exception as exc:
        errors["receipts"] = _err(exc)
    try:
        row = (await session.execute(text(
            "SELECT event_id FROM futures_markets WHERE id = :id"), {"id": MARKET_ID})).first()
        out["readback_event_id"] = int(row[0]) if row and row[0] is not None else None
    except Exception as exc:
        await _quiet_rollback(session)
        errors["readback"] = _err(exc)
    if errors:
        out["postcommit_errors"] = errors
    return out


async def run(session, *, apply: bool, expected_digest: Optional[str] = None,
              now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    state = await read_state(session)
    verdict = decide(now=now, **state)
    digest = plan_digest(verdict["witness"])
    out = {
        "mode": "apply" if apply else "dry-run",
        "outcome": DRY_RUN,
        "move": {"market_id": MARKET_ID, "external_id": TICKER,
                 "from_event_id": FROM_EVENT_ID, "to_event_id": TO_EVENT_ID},
        "refusals": verdict["refusals"],
        "witness": verdict["witness"],
        "plan_digest": digest,
    }
    if not apply:
        return out
    if verdict["refusals"]:
        raise Refused(f"witness refused: {verdict['refusals']}")
    if not expected_digest:
        raise Refused("--apply needs --plan-digest from the reviewed dry run")
    if expected_digest.strip().lower() != digest:
        raise Refused(
            f"the plan built now hashes to {digest}, not the reviewed {expected_digest}; "
            "read a fresh dry run"
        )
    if not await _backup(session):
        raise Refused("backup does not bank this move; refusing to write")
    try:
        if not await _cas(session, FROM_EVENT_ID, TO_EVENT_ID):
            await session.rollback()
            out.update(outcome=ROLLED_BACK_CHANGED_UNDER_RUN, committed=False,
                       undo="nothing moved; no restore needed")
            return out
        marked = await session.execute(text(
            f"UPDATE {BACKUP_TABLE} SET applied_at = now() WHERE market_id = :m "
            "AND event_id_before = :b AND event_id_after = :a"),
            {"m": MARKET_ID, "b": FROM_EVENT_ID, "a": TO_EVENT_ID})
        if marked.rowcount != 1:
            await session.rollback()
            out.update(outcome=ROLLED_BACK_ERROR, committed=False,
                       error="bank row not marked applied")
            return out
    except Exception as exc:
        await session.rollback()
        out.update(outcome=ROLLED_BACK_ERROR, committed=False, error=_err(exc))
        return out
    try:
        await session.commit()
    except Exception as exc:
        await _quiet_rollback(session)
        out.update(outcome=COMMIT_UNCERTAIN, committed="unknown", error=_err(exc),
                   undo=UNDO_LINE)
        return out
    out.update(outcome=APPLIED, committed=True, undo=UNDO_LINE)
    await _postcommit(session, state["market"], FROM_EVENT_ID, TO_EVENT_ID, out)
    try:
        from app.services.anchor_channel import resolve_market_born_duplicate

        out["drain_verdict"] = await resolve_market_born_duplicate(session, FROM_EVENT_ID)
    except Exception as exc:
        out.setdefault("postcommit_errors", {})["drain_verdict"] = _err(exc)
    if out.get("postcommit_errors") or out.get("readback_event_id") != TO_EVENT_ID:
        out["outcome"] = APPLIED_POSTCOMMIT_UNVERIFIED
    elif out.get("drain_verdict") != TO_EVENT_ID:
        out["outcome"] = APPLIED_NOT_DRAINED
    return out


async def restore(session) -> dict:
    exists = await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP_TABLE})
    if exists.scalar() is None:
        raise Refused(f"{BACKUP_TABLE} does not exist; nothing to restore")
    row = (await session.execute(text(
        f"SELECT event_id_before, event_id_after, applied_at FROM {BACKUP_TABLE} "
        "WHERE market_id = :m"), {"m": MARKET_ID})).first()
    out = {"mode": "restore", "market_id": MARKET_ID}
    if row is None or row[2] is None:
        out["outcome"] = NOTHING_TO_RESTORE
        return out
    before, after = int(row[0]), int(row[1])
    m = (await session.execute(text(
        "SELECT name FROM futures_markets WHERE id = :id"), {"id": MARKET_ID})).first()
    if not await _cas(session, after, before):
        await session.rollback()
        out.update(outcome=RESTORE_SHORT, committed=False,
                   note="market is no longer on event_id_after; left alone")
        return out
    try:
        await session.commit()
    except Exception as exc:
        await _quiet_rollback(session)
        out.update(outcome=COMMIT_UNCERTAIN, committed="unknown", error=_err(exc))
        return out
    out.update(outcome=RESTORED, committed=True)
    await _postcommit(session, {"name": m[0] if m else None}, after, before, out)
    if out.get("postcommit_errors") or out.get("readback_event_id") != before:
        out["outcome"] = RESTORE_SHORT
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--restore", action="store_true")
    ap.add_argument("--plan-digest", default=None,
                    help="with --apply: the plan_digest the reviewed dry run printed")
    args = ap.parse_args()
    if args.apply and not args.plan_digest:
        print("REFUSED: --apply needs --plan-digest (the plan_digest of the dry run you read)")
        return 2
    try:
        refuse_unless_production(dict(os.environ))
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        try:
            out = await (restore(session) if args.restore else run(
                session, apply=args.apply, expected_digest=args.plan_digest))
        except Refused as exc:
            await session.rollback()
            print(f"REFUSED: {exc}")
            return 2
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        if out["mode"] == "dry-run" and not out["refusals"]:
            print(
                "APPLY THIS PLAN: heroku run:detached -a bainluck -- python3 "
                "scripts/repair_11022_tennis_split_pair.py --apply "
                f"--plan-digest {out['plan_digest']}"
            )
        if out.get("undo") == UNDO_LINE:
            print(f"UNDO: {UNDO_LINE}")
        sys.stdout.flush()
        return 0 if out.get("outcome") in CLEAN_OUTCOMES else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
