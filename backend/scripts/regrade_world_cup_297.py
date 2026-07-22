"""#1203 / #237 Item 2 — correct the wrongly-graded 2026 World Cup winner field.

The Kalshi-sourced WC winner market (futures market 297,
``2026 Men's World Cup Winner``) has ALL 66 outcomes graded ``is_winner=false``
with ``resolution_source='api_settlement'`` — including Spain, the actual champion.
Kalshi's OWN finalized settlement API says otherwise:

    GET markets/KXMENWORLDCUP-26-ES -> result="yes", status="finalized"

So our DB scores the real champion as a LOSER — the #1203 symptom (``futures/297``:
Spain, zero ``is_winner``) and an active poisoner of Kalshi calibration (a settled
YES scored as a loss). This is exactly gotcha #21's ALLOWED case: a targeted
correction backed by a confirmed authoritative source (Kalshi's finalized result),
NOT a probability guess and NOT a bulk reset. ``api_settlement`` → ``api_settlement``
is a same-tier authoritative rewrite (resolution_authority.is_downgrade permits it).

Safety:
  * Re-verifies Kalshi's LIVE finalized result for the Spain ticker before writing —
    if Kalshi does not confirm result="yes"/finalized, the script SKIPS (never a
    blind write).
  * Targets exactly market 297's Spain outcome (is_winner false -> true); every
    other outcome stays false (Kalshi confirms AR/FR/... = "no"). Also flips the
    market status open -> resolved (gotcha #33: settled Kalshi markets linger as
    'open', blocking calibration inclusion).
  * Idempotent: no-op if Spain is already is_winner=true.

    python3 scripts/regrade_world_cup_297.py            # dry-run (ledger only)
    python3 scripts/regrade_world_cup_297.py --apply    # commit the correction
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MARKET_ID = 297
SPAIN_TICKER = "KXMENWORLDCUP-26-ES"
KALSHI_MARKET_URL = "https://api.elections.kalshi.com/trade-api/v2/markets/"


async def _kalshi_confirms_spain() -> bool:
    """True only when Kalshi's live API reports the Spain WC market finalized YES."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{KALSHI_MARKET_URL}{SPAIN_TICKER}")
            resp.raise_for_status()
            m = resp.json().get("market", {})
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Kalshi verify failed ({exc}) — SKIP (never a blind write)")
        return False
    result, status = m.get("result"), m.get("status")
    print(f"  Kalshi {SPAIN_TICKER}: result={result!r} status={status!r}")
    return result == "yes" and status == "finalized"


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    print(f"#1203 WC winner-field correction — market {MARKET_ID}, {SPAIN_TICKER}")
    if not await _kalshi_confirms_spain():
        print("Kalshi did not confirm Spain as finalized YES — aborting, no writes.")
        return

    async with get_task_session() as s:
        spain = (await s.execute(text(
            "SELECT fo.id, fo.is_winner, fo.resolution_source, fm.status "
            "FROM futures_outcomes fo JOIN futures_markets fm ON fo.market_id = fm.id "
            "WHERE fo.market_id = :mid AND fo.external_id = :tk"
        ), {"mid": MARKET_ID, "tk": SPAIN_TICKER})).first()

        if not spain:
            print(f"  ! No outcome {SPAIN_TICKER} in market {MARKET_ID} — aborting.")
            return

        oid, is_winner, res_src, mkt_status = spain
        winners = (await s.execute(text(
            "SELECT count(*) FILTER (WHERE is_winner) FROM futures_outcomes WHERE market_id = :mid"
        ), {"mid": MARKET_ID})).scalar()
        print(f"  before: Spain(id={oid}) is_winner={is_winner} resolution_source={res_src!r}; "
              f"market status={mkt_status!r}; winners in field={winners}")

        if is_winner and mkt_status == "resolved":
            print("  already corrected (Spain winner + market resolved) — no-op.")
            return

        if not apply:
            print("\nDRY-RUN — would set Spain is_winner=true (source stays api_settlement) "
                  f"and market {MARKET_ID} status=resolved. Pass --apply to commit.")
            return

        # Same-tier authoritative correction — do NOT lower authority, keep api_settlement.
        await s.execute(text(
            "UPDATE futures_outcomes SET is_winner = true "
            "WHERE id = :oid AND market_id = :mid"
        ), {"oid": oid, "mid": MARKET_ID})
        await s.execute(text(
            "UPDATE futures_markets SET status = 'resolved' WHERE id = :mid"
        ), {"mid": MARKET_ID})
        await s.commit()

        winners_after = (await s.execute(text(
            "SELECT count(*) FILTER (WHERE is_winner) FROM futures_outcomes WHERE market_id = :mid"
        ), {"mid": MARKET_ID})).scalar()
        print(f"\nAPPLIED: Spain graded winner; market {MARKET_ID} resolved. "
              f"winners in field now = {winners_after} (expect 1). "
              "Other outcomes untouched (Kalshi confirms they are 'no').")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
