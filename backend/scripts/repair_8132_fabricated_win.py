"""#8132 — retract the Kalshi WINS the venue never declared.

THE SHIP: a settled Kalshi board stops printing **"Won"** on a leg the venue
itself finalized as a loser. 56 legs across 49 boards, 46 of them rendering at
95-99%, so today a reader opening ``/futures/59319183`` is told:

    San Diego wins by over 3.5 runs   [WON]
    Markets gave this just 0%.

…and the Final Results panel prints THREE legs as ``Won / 100% / Settled`` on a
board whose venue finalized all six ``no`` (a one-run game). After this repair
those boards render the way ``/futures/61461824`` already does today — a neutral
``RESOLVED`` chip, the caption "Settled.", every leg ``Lost / 0%``. The
presentation is already shipped; nothing new is drawn.

THIS IS #1852'S MIRROR. That rail (``repair_kalshi_fabricated_loss.py``) retracts
fabricated LOSSES and its population predicate requires ``fo.is_winner = false``,
so it is structurally blind to this half. The defect here is the opposite
direction and the worse one to read: a fabricated loss quietly removes a row from
the accuracy curve; a fabricated WIN puts a green tick on a leg that lost.

------------------------------------------------------------------------------
WHY THE VENUE CAN STILL BE QUOTED, AND WHY THIS IS #2077 PAYING OUT
------------------------------------------------------------------------------

Kalshi has PURGED the per-leg results for most of these boards. Measured at the
venue 2026-09-23 00:55Z (notice 26/27 — the venue's own API, not our mirror):

    KXMLBSPREAD-26JUL201915SDATL       ~64d   6 markets, all result='no'
    KXITFDOUBLES-26JUL09KIMROHRIFLEE   ~75d   0 markets  (purged)
    KXARTISTSTREAMSU-GAGA26JUL02       ~82d   0 markets  (purged)
    KXWTASETWINNER-26JUN26MARKEY-2     ~88d   0 markets  (purged)

``GET /events/{ticker}`` answers **200 with an empty ``markets`` array** — gotcha
#53's exact shape, an empty 200 that is a response shape and not an absence.
So the venue can no longer be re-asked, and our ``settlement_captures`` rows are
the last surviving record of what it said. That is the insurance policy #2077 was
built to buy, and this is the first thing it pays for. It is also the reason this
repair reads a BANKED payload rather than re-probing: re-probing would return
nothing and the honest reading of nothing is "we no longer know", which would
lose the answer we already hold.

A banked read is legitimate here for the reason already on #8126: a consumer
applies the CURRENT vocabulary to whatever it reads regardless of a capture's
stored ``protocol_version``, and a ``finalized`` leg is TERMINAL — it cannot have
moved since capture, so a banked read of one is as good as a fresh one. Every
verdict below requires ``status='finalized'`` for exactly that reason.

------------------------------------------------------------------------------
THE EVIDENCE, AND THE CONTROL THAT PROVES THE INSTRUMENT ALIVE
------------------------------------------------------------------------------

Venue vocabulary, censused over a 1/7 sample of Kalshi captures (production
2026-09-23 00:50Z). ``result`` is NEVER absent, and the unsettled case is ``''``,
which pairs ONLY with ``status='closed'`` — never with ``finalized``:

    no      / finalized   18,237
    scalar  / finalized    3,078
    yes     / finalized      289
    ''      / closed          47

So the ``finalized`` gate alone already excludes the unsettled legs; requiring
both is belt and braces, and it makes the refusal explicit rather than lucky.

Joined to our verdicts on ``futures_outcomes.external_id = leg->>'ticker'``:

    venue      ours     legs
    no         False   12,824   agree
    scalar     False    1,652   agree
    yes        True       121   agree
    yes        False        0   <- we never call a venue winner a loser
    no         True        21   DEFECT
    scalar     True         6   DEFECT

🔴 THE ZERO IS THE POINT. 14,597 agreeing rows and no ``yes``/False at all is the
known-good control: the join key, the nesting path and the vocabulary are all
alive, so the 27 contradictions are a signal and not an instrument artifact. A
uniform answer across a population where variation is due would have indicted the
instrument first (this table was read wrong twice already on this lane — once
testing ``raw_response ? 'markets'`` at the TOP level, which returns a clean
``false`` on 400/400 because the payload is nested one level down under
``kalshi_event``; and once reading ``protocol_version`` as a JSON key when it is a
COLUMN).

Driven over ALL captures in seven ``mod(id,7)`` slices — the unsliced join exceeds
the 25s admin ceiling — the population is :data:`EXPECTED`: **56 legs / 49
boards**, and no leg's captures ever disagree with each other.

------------------------------------------------------------------------------
TWO ARMS, TWO STAMPS, AND THE SECOND ONE IS NOT THE OBVIOUS ONE
------------------------------------------------------------------------------

    venue     prior source        tier  legs   write                      tier
    no        clean_resolution      1     29   false / api_settlement       3
    no        game_score            2     10   false / api_settlement       3
    scalar    clean_resolution      1     17   false / ungradeable_result   1

``result='no'`` — the venue DID declare this leg lost, so ``api_settlement`` is
the truth and it is an UPGRADE over both priors (``is_downgrade`` is False).

``result='scalar'`` — the board settled on a NUMBER and no side was declared.
Stamping ``api_settlement`` here would assert a loss the venue never stated,
which is precisely the #1852 defect this file is the mirror of. The correct stamp
is ``ungradeable_result``, the retraction TERMINAL_SOURCES already defines for "a
Kalshi ``result`` of ``scalar`` or ``''``". It is calibration-truth INELIGIBLE, so
the scalar legs leave the published curve instead of entering it as fake losses.

The specimen that settles the argument — ``KXWTASETWINNER-26JUN26MARKEY-2-MAR``,
"Will Petra Marcinko win set 2": ``result='scalar'``, ``status='finalized'``,
``settlement_value_dollars='0.1500'``, and the venue's own ``rules_secondary``
says a retirement settles to Fair Market Price. Nobody won that set. We print
Madison Keys as the winner at 0.98.

NO DOWNGRADE ANYWHERE IN THE POPULATION, and that was checked rather than hoped:
all 17 ``scalar`` legs carry ``clean_resolution`` (tier 1), NONE carries
``game_score`` (tier 2), so the tier-1 retraction never writes over tier 2.
:func:`is_downgrade` permits a same-tier rewrite by name. The script re-checks
this per leg anyway and refuses ``WOULD_DOWNGRADE`` rather than trusting the
table.

------------------------------------------------------------------------------
THE REPAIR IS A NO-OP WITHOUT THE PRODUCER GUARD THAT SHIPS BESIDE IT
------------------------------------------------------------------------------

``backfill_winners`` holds three price-derived crowners, and none of them guarded
the rows its UPDATE wrote — the CTE vets the MARKET, then the UPDATE rewrites
every leg of it without asking what that leg's grade already says:

    ~1340   clean_resolution (t1)   fires when the venue returns NO markets
    ~7358   clean_resolution (t1)   fires when every leg is near-certain
    ~10579  settlement_sync  (t3)   golf, when is_winner != (prob >= 0.95)

The first is the ORIGIN of the 46 ``clean_resolution`` rows: the venue purged,
``nested`` came back empty, and ``is_winner = current_probability >= 0.95`` became
"won". Re-run against repaired rows it would undo every one of them within 6h,
and the golf crowner would re-crown with TIER 3, which nothing may then overwrite.

So ``PRICE_CROWN_PROTECTED_SOURCES`` (``resolution_authority``) ships in the same
change and all three now refuse to overwrite a venue-licensed grade or a
retraction. **That guard must be live before this script is applied.** It is what
makes this a repair rather than a race, and :func:`guard_is_live` refuses to run
without it.

It also closes a hole that predates this issue: TERMINAL_SOURCES claims the
HAVING guards stop a price crowner superseding ``ungradeable_result``, but those
guards count only rows where ``is_winner`` is TRUE, and a retraction is
``is_winner=false`` — invisible to its own stated defence.

------------------------------------------------------------------------------
HOW TO RUN IT (D51(b): backup first, one-command restore)
------------------------------------------------------------------------------

    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_8132_fabricated_win.py
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_8132_fabricated_win.py --apply

Dry-run by default; ``--apply`` writes. The undo is
``restore_8132_fabricated_win.py --apply`` and it is one command.

Refuses to run anywhere but ``bainluck-heavy`` (notice 47(c): the runtime DDL
below is attended-invocation-only, which is what keeps it out of migration
class). Idempotent: a second run finds every row already at its target and
reports ``ALREADY_REPAIRED``.

BY DEFAULT IT REPAIRS ONLY THE PINNED :data:`EXPECTED` LEGS, and that is
deliberate. ``run_settlement_sweep`` banks ~3,000 boards a night, so the derived
population GROWS; a script that silently widened its own blast radius between the
dry-run somebody read and the apply would be unreviewable. Legs the derivation
finds beyond EXPECTED are counted and listed as ``NEW`` and left alone unless
``--include-new`` is passed. Legs in EXPECTED that no longer match their recorded
prior state are ``DIVERGED`` and are never written.

The backup table is NOT Alembic-managed; ``alembic revision --autogenerate`` will
propose DROPping it, which is expected and to be deleted from the generated
migration rather than accepted.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# …and this script's OWN directory, so the restore's sibling import resolves
# however the file is loaded. `python3 scripts/repair_….py` puts `scripts/` on the
# path for free; importing the file by its path (the guard test does) does not,
# and the difference is an ImportError nobody sees until CI.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402
from app.utils.resolution_authority import (  # noqa: E402
    authority_tier,
    is_downgrade,
)

#: Only this app may run it. The repair writes production rows, and notice 47(c)
#: makes the attended invocation itself the gate that keeps the runtime DDL below
#: out of migration class.
PRODUCER_APP = "bainluck-heavy"

#: Pre-image lives here. Plain `backup_*`, created on demand under `--apply`.
BACKUP_TABLE = "backup_8132_fabricated_win"

#: The venue's per-leg payload, nested one level down. Reading it at the TOP
#: level returns a clean `false` on every row and convicts nothing (this lane did
#: exactly that, twice, on this table).
LEGS_PATH = "raw_response -> 'kalshi_event' -> 'markets'"

#: Venue `result` values that mean "this leg is NOT a winner", each with the
#: stamp it earns. A `no` is the venue declaring a loss, so it is that venue's own
#: settlement. A `scalar` is the venue declining to declare any side, so asserting
#: a loss would fabricate one — it gets the #1852 retraction instead.
RETRACTION_FOR: dict[str, str] = {
    "no": "api_settlement",
    "scalar": "ungradeable_result",
}

#: The only venue status a verdict may be read from. `''`/`closed` legs are
#: unsettled and `yes` legs are not this defect; both fall through to REFUSED.
TERMINAL_STATUS = "finalized"

#: Verdicts.
REPAIR = "REPAIR"
ALREADY_REPAIRED = "ALREADY_REPAIRED"
DIVERGED = "DIVERGED"
NEW = "NEW"
WOULD_DOWNGRADE = "WOULD_DOWNGRADE"

#: (outcome_id, market_id, ticker, venue_result, prior_resolution_source).
#: Measured on production 2026-09-23 00:50-01:05Z; every row `is_winner = TRUE`.
#: Re-derived on every run and compared row by row — the table cannot notice the
#: world moved, and a derivation cannot notice it was pointed at the wrong rows,
#: so neither is trusted alone.
EXPECTED: tuple[tuple[int, int, str, str, str], ...] = (
    (198727974, 52793841, "KXKBORFI-26JUL080530NCDHAN-Y", "scalar", "clean_resolution"),
    (198738690, 52795334, "KXWNBA2HTOTAL-26JUL06GSWSH-80", "no", "clean_resolution"),
    (198742260, 52795824, "KXARTISTSTREAMSU-OCEAN26JUL02-83.2M", "no", "clean_resolution"),
    (198742261, 52795827, "KXARTISTSTREAMSU-GAGA26JUL02-201.5M", "no", "clean_resolution"),
    (198742262, 52795828, "KXARTISTSTREAMSU-EMINEM26JUL02-182.7M", "no", "clean_resolution"),
    (198742263, 52795835, "KXARTISTSTREAMSU-BIGGIE26JUL02-41.4M", "no", "clean_resolution"),
    (198742265, 52795838, "KXARTISTSTREAMSU-BEILISH26JUL02-196.3M", "no", "clean_resolution"),
    (198742266, 52795839, "KXARTISTSTREAMSU-BEATLES26JUL02-113.5M", "no", "clean_resolution"),
    (198742267, 52795840, "KXARTISTSTREAMSU-2PAC26JUL02-70.4M", "no", "clean_resolution"),
    (198742302, 52795904, "KXALBUMSTREAMSU-LEMONBEY26JUL02-8.8M", "no", "clean_resolution"),
    (198833279, 52832249, "KXKBORFI-26JUL050500NCDKIA-Y", "scalar", "clean_resolution"),
    (198833281, 52832251, "KXKBORFI-26JUL050500HANLG-Y", "scalar", "clean_resolution"),
    (198837759, 52832698, "KXNBASUMMERTOTAL-26JUL04BKNSAC-169", "no", "game_score"),
    (198837760, 52832698, "KXNBASUMMERTOTAL-26JUL04BKNSAC-172", "no", "game_score"),
    (198837761, 52832698, "KXNBASUMMERTOTAL-26JUL04BKNSAC-175", "no", "game_score"),
    (198837762, 52832698, "KXNBASUMMERTOTAL-26JUL04BKNSAC-178", "no", "game_score"),
    (198837763, 52832698, "KXNBASUMMERTOTAL-26JUL04BKNSAC-181", "no", "game_score"),
    (198928840, 52866232, "KXLMBGAME-26JUL022110CDJCAL-CDJ", "scalar", "clean_resolution"),
    (199070799, 52921626, "KXMLBF3-26JUN302140LAASEA-SEA", "no", "clean_resolution"),
    (199075315, 52922081, "KXINXHUD-26JUN301600-T0.00", "no", "clean_resolution"),
    (199076442, 52922376, "KXATPACES-26JUN30FRILAJ-19", "no", "clean_resolution"),
    (199167101, 52956112, "KXARTISTSTREAMSU-SWIFT26JUN25-516.7M", "no", "clean_resolution"),
    (199167109, 52956164, "KXALBUMSTREAMSU-X100PBUNNY26JUN25-24.3M", "no", "clean_resolution"),
    (199168427, 52956754, "KXATPEXACTMATCH-26JUN29BONDIA-DIA32", "scalar", "clean_resolution"),
    (199170447, 52957038, "KXWNBA3QTOTAL-26JUN28PDXWSH-36", "no", "clean_resolution"),
    (199170448, 52957038, "KXWNBA3QTOTAL-26JUN28PDXWSH-51", "no", "clean_resolution"),
    (199247728, 52985347, "KXWNBA3QSPREAD-26JUN26ATLGS-ATL2", "no", "clean_resolution"),
    (199255006, 52986112, "KXWTASETWINNER-26JUN26MARKEY-2-KEY", "scalar", "clean_resolution"),
    (199257459, 52986498, "KXWNBA4QSPREAD-26JUN25LATOR-TOR10", "no", "clean_resolution"),
    (199416744, 53049975, "KXMLBOUTS-26JUN232140ATLSD-ATLJRITCHIE60-16", "no", "clean_resolution"),
    (199419440, 53050183, "KXMLBSB-26JUN231840NYYDET-NYYCBELLINGER35-1", "no", "clean_resolution"),
    (199420131, 53050259, "KXITFMATCH-26JUN23LOUPET-LOU", "scalar", "clean_resolution"),
    (201189077, 53732402, "KXCS2TOTALMAPS-26JUL100100THEKAL-3", "no", "clean_resolution"),
    (201641857, 53910048, "KXDXYDUD-26JUL07-T101.0780", "no", "clean_resolution"),
    (204486258, 55053111, "KXCS2TOTALMAPS-26JUL101130TRIPURE-3", "no", "clean_resolution"),
    (206186995, 55538757, "KXLMBGAME-26JUL092130TDTRDA-RDA", "scalar", "clean_resolution"),
    (206830281, 55688586, "KXPGA3BALL-THOC26R1DBRFLAOSIM-DBR", "scalar", "clean_resolution"),
    (207018257, 55743327, "KXPPLMATCH-26JUL10MEWTPB-MEW", "no", "clean_resolution"),
    (207022213, 55744096, "KXITFWDOUBLES-26JUL09HAVPODFERYOU-HAVPOD", "no", "clean_resolution"),
    (207070706, 55758199, "KXITFDOUBLES-26JUL09KIMROHRIFLEE-KIMROH", "no", "clean_resolution"),
    (207070854, 55758241, "KXITFWDOUBLES-26JUL09MATZARAVATAH-MATZAR", "no", "clean_resolution"),
    (207071017, 55758285, "KXITFDOUBLES-26JUL09DOMCATIGNRAZ-DOMCAT", "no", "clean_resolution"),
    (207071170, 55758332, "KXITFWDOUBLES-26JUL09RICSACBRENIC-RICSAC", "no", "clean_resolution"),
    (209797633, 56510750, "KXWTASETWINNER-26JUL19MONPIE-2-PIE", "scalar", "clean_resolution"),
    (211090553, 56847666, "KXATPSETWINNER-26JUL19GASDZU-1-GAS", "scalar", "clean_resolution"),
    (211097722, 56848716, "KXATPSETWINNER-26JUL18LUZTSE-2-LUZ", "scalar", "clean_resolution"),
    (211098147, 56848889, "KXCS2MAP-26JUL180630EXMANAMIS-1-EXMANA", "scalar", "clean_resolution"),
    (211145278, 56862505, "KXATPEXACTMATCH-26JUL15PRIMOL-MOL21", "scalar", "clean_resolution"),
    (212867753, 57365941, "KXCS2MAP-26JUL251000JUSBLA-1-JUS", "scalar", "clean_resolution"),
    (216033383, 58211974, "KXITFDOUBLES-26JUL16FANVOARYMREH-FANVOA", "scalar", "clean_resolution"),
    (217995391, 58724041, "KXPGA3BALL-MO26R1MROZJKANAEWA-MROZ", "scalar", "clean_resolution"),
    (220355165, 59287261, "KXMLBSPREAD-26JUL282138HOULAA-HOU2", "no", "game_score"),
    (220395090, 59293859, "KXMLBSPREAD-26JUL271845TORWSH-WSH2", "no", "game_score"),
    (220538443, 59319183, "KXMLBSPREAD-26JUL201915SDATL-SD2", "no", "game_score"),
    (220538444, 59319183, "KXMLBSPREAD-26JUL201915SDATL-SD3", "no", "game_score"),
    (220538445, 59319183, "KXMLBSPREAD-26JUL201915SDATL-SD4", "no", "game_score"),
)

EXPECTED_BY_ID = {row[0]: row for row in EXPECTED}


def wrong_app_refusal() -> str | None:
    """Return a refusal string when not running on :data:`PRODUCER_APP`."""
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def classify_leg(venue_result: str | None, venue_status: str | None) -> str | None:
    """The stamp a leg earns from the venue's own answer, or None to refuse.

    PURE, and per-leg by construction: it is handed one leg's answer and nothing
    about the board's shape. That is what makes the rule safe on a ladder — a
    spread board legitimately settles several legs `no` (gotcha #23), and the
    venue states each one separately, so no exclusivity is ever inferred here.
    """
    if venue_status != TERMINAL_STATUS:
        return None
    return RETRACTION_FOR.get((venue_result or "").strip())


def _population_sql(slice_mod: int) -> str:
    """One slice of the contradiction population.

    Sliced because the unsliced join exceeds the admin read ceiling — the third
    formulation of this count to time out. `jsonb_typeof(...) = 'array'` skips the
    ~7.5% of captures the writer `_head`-clipped: an unreadable payload is
    skipped, never guessed.
    """
    return f"""
        SELECT DISTINCT fo.id, fo.market_id, fo.external_id,
               leg->>'result' AS venue_result,
               fo.is_winner, COALESCE(fo.resolution_source, '') AS prior_source
        FROM settlement_captures sc
        CROSS JOIN LATERAL jsonb_array_elements(sc.{LEGS_PATH}) leg
        JOIN futures_outcomes fo
          ON fo.external_id = leg->>'ticker' AND fo.market_id = sc.market_id
        WHERE sc.source = 'kalshi'
          AND jsonb_typeof(sc.{LEGS_PATH}) = 'array'
          AND leg->>'status' = '{TERMINAL_STATUS}'
          AND leg->>'result' IN ('no', 'scalar')
          AND fo.is_winner IS TRUE
          AND mod(sc.id, 7) = {slice_mod}
    """


def guard_is_live() -> bool:
    """True when the price-crowner guard is in the code this dyno imported.

    Applying the repair under a binary whose crowners still overwrite any leg
    hands the rows straight back within 6h — and the golf crowner hands them back
    stamped TIER 3, which nothing may then overwrite. So this is a refusal, not a
    warning.

    It asks the IMPORTED module, not the checkout: a repair run on a dyno is run
    against whatever that dyno released, and "the fix is on master" has never
    been the same claim as "the fix is in the process doing the writing"
    (notice 48). Reading the interpolated SQL is the strongest available proof
    short of a write — the constant appears in the statement only if the guard
    clause is there.

    🪤 `from app.tasks import backfill_winners` binds the Celery TASK of that
    name, not the module that defines it — `inspect.getsource` then returns 427
    characters of decorator, the constant is absent from it, and this function
    returns False for ever. The refusal would read exactly like "the guard is not
    deployed", which is the shape of failure that is hardest to tell from the
    thing it is looking for. `import_module` cannot be shadowed.
    """
    import importlib
    import inspect

    body = inspect.getsource(importlib.import_module("app.tasks.backfill_winners"))
    return (
        "PRICE_CROWN_PROTECTED_SOURCES_SQL" in body
        and "price_crown_protected_sql" in body
    )


async def derive(session) -> list[dict]:
    """Re-derive the population and grade every row against :data:`EXPECTED`."""
    found: dict[int, dict] = {}
    for slice_mod in range(7):
        rows = (await session.execute(text(_population_sql(slice_mod)))).all()
        for oid, market_id, ticker, venue_result, is_winner, prior_source in rows:
            prior = found.get(oid)
            if prior and prior["venue_result"] != venue_result:
                # Two captures of one leg disagreeing would make the venue's
                # answer unusable for that leg. Measured zero today; if it ever
                # fires, refuse rather than pick one.
                prior["verdict"] = DIVERGED
                prior["why"] = (
                    f"captures disagree: {prior['venue_result']} vs {venue_result}"
                )
                continue
            found[oid] = {
                "outcome_id": oid,
                "market_id": market_id,
                "ticker": ticker,
                "venue_result": venue_result,
                "is_winner": is_winner,
                "prior_source": prior_source,
                "verdict": None,
                "why": "",
            }

    plan: list[dict] = []
    for oid, row in sorted(found.items()):
        if row["verdict"] == DIVERGED:
            plan.append(row)
            continue

        stamp = classify_leg(row["venue_result"], TERMINAL_STATUS)
        if stamp is None:
            continue
        row["target_source"] = stamp

        expected = EXPECTED_BY_ID.get(oid)
        if expected is None:
            row["verdict"] = NEW
            row["why"] = "evidenced but not in the pinned table"
        else:
            _, exp_market, exp_ticker, exp_result, exp_source = expected
            if (exp_market, exp_ticker, exp_result) != (
                row["market_id"],
                row["ticker"],
                row["venue_result"],
            ):
                row["verdict"] = DIVERGED
                row["why"] = "row no longer matches its pinned identity"
                plan.append(row)
                continue
            if row["prior_source"] != exp_source:
                row["verdict"] = DIVERGED
                row["why"] = (
                    f"prior source moved: pinned {exp_source!r}, "
                    f"found {row['prior_source']!r}"
                )
                plan.append(row)
                continue

        if is_downgrade(row["prior_source"] or None, stamp):
            row["verdict"] = WOULD_DOWNGRADE
            row["why"] = (
                f"{row['prior_source']} (tier "
                f"{authority_tier(row['prior_source'])}) -> {stamp} (tier "
                f"{authority_tier(stamp)})"
            )
        elif row["is_winner"] is False and row["prior_source"] == stamp:
            row["verdict"] = ALREADY_REPAIRED
        elif row["verdict"] != NEW:
            row["verdict"] = REPAIR
        plan.append(row)

    return plan


async def bank_pre_image(session, writable: list[dict]) -> None:
    """Write the pre-image BEFORE the first UPDATE, or write nothing at all."""
    await session.execute(
        text(f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
                outcome_id      BIGINT PRIMARY KEY,
                market_id       BIGINT NOT NULL,
                ticker          TEXT   NOT NULL,
                prior_is_winner BOOLEAN NOT NULL,
                prior_source    TEXT   NOT NULL,
                target_source   TEXT   NOT NULL,
                banked_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    )
    for row in writable:
        # ON CONFLICT DO NOTHING: the FIRST pre-image is the true one. A second
        # run must never overwrite it with the state the first run produced —
        # that would quietly make the undo a no-op.
        await session.execute(
            text(f"""
                INSERT INTO {BACKUP_TABLE}
                    (outcome_id, market_id, ticker, prior_is_winner,
                     prior_source, target_source)
                VALUES (:oid, :mid, :ticker, :winner, :prior, :target)
                ON CONFLICT (outcome_id) DO NOTHING
            """),
            {
                "oid": row["outcome_id"],
                "mid": row["market_id"],
                "ticker": row["ticker"],
                "winner": row["is_winner"],
                "prior": row["prior_source"],
                "target": row["target_source"],
            },
        )


async def apply_plan(session, writable: list[dict]) -> dict[str, int]:
    """Compare-and-set each leg on its EXACT prior state."""
    stats = {"written": 0, "concurrent_drift": 0}
    for row in writable:
        result = await session.execute(
            text("""
                UPDATE futures_outcomes
                SET is_winner = false,
                    resolution_source = :target,
                    last_updated = NOW()
                WHERE id = :oid
                  AND is_winner IS TRUE
                  AND COALESCE(resolution_source, '') = :prior
            """),
            {
                "oid": row["outcome_id"],
                "target": row["target_source"],
                "prior": row["prior_source"],
            },
        )
        if result.rowcount == 1:
            stats["written"] += 1
        else:
            # A grader moved the row between the read and the write. Report it
            # by name; never a silent overwrite and never a silent success.
            stats["concurrent_drift"] += 1
            row["verdict"] = DIVERGED
            row["why"] = "concurrent_drift: prior state gone at write time"
    return stats


def writable_rows(plan: list[dict], include_new: bool) -> list[dict]:
    """The rows `--apply` will actually write.

    Kept OUT of :func:`derive` deliberately. `include_new` used to be a
    parameter there, and it changed nothing the plan could show: a NEW row came
    back identically either way, so a mutation that made the flag inert survived
    the whole suite. The switch belongs where it acts, which is here, where a
    test can drive both of its branches against one plan.
    """
    allowed = {REPAIR} | ({NEW} if include_new else set())
    return [row for row in plan if row["verdict"] in allowed]


def _summarise(plan: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in plan:
        out[row["verdict"]] = out.get(row["verdict"], 0) + 1
    return out


async def run(apply: bool, include_new: bool) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2

    async with get_task_session() as session:
        if apply and not guard_is_live():
            print(
                "REFUSED: the #8132 price-crowner guard is not in this build. "
                "Applying without it hands every repaired row back within 6h — "
                "and the golf crowner hands it back at tier 3. Deploy the guard "
                "first."
            )
            return 2

        plan = await derive(session)
        summary = _summarise(plan)
        writable = writable_rows(plan, include_new)

        print(f"#8132 fabricated-win retraction — {'APPLY' if apply else 'DRY RUN'}")
        print(f"  pinned EXPECTED legs : {len(EXPECTED)}")
        print(f"  derived legs         : {len(plan)}")
        for verdict in (REPAIR, ALREADY_REPAIRED, NEW, DIVERGED, WOULD_DOWNGRADE):
            print(f"  {verdict:<18} : {summary.get(verdict, 0)}")
        print(f"  writable             : {len(writable)}")

        for row in plan:
            if row["verdict"] in (DIVERGED, WOULD_DOWNGRADE, NEW):
                print(
                    f"    {row['verdict']} {row['outcome_id']} {row['ticker']} "
                    f"{row['why']}"
                )

        missing = sorted(set(EXPECTED_BY_ID) - {r["outcome_id"] for r in plan})
        if missing:
            print(f"  MISSING from derivation: {len(missing)} -> {missing[:10]}")

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply.")
            return 0

        if not writable:
            print("\nnothing writable — no rows touched.")
            return 0

        await bank_pre_image(session, writable)
        stats = await apply_plan(session, writable)
        await session.commit()

        print(f"\n  pre-image banked in : {BACKUP_TABLE}")
        print(f"  rows written        : {stats['written']}")
        print(f"  concurrent_drift    : {stats['concurrent_drift']}")
        print("\nundo: python3 scripts/restore_8132_fabricated_win.py --apply")
        return 0 if stats["concurrent_drift"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument(
        "--include-new",
        action="store_true",
        help="also repair evidenced legs beyond the pinned EXPECTED table",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.apply, args.include_new))


if __name__ == "__main__":
    raise SystemExit(main())
