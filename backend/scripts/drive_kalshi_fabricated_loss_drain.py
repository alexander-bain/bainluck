#!/usr/bin/env python3
"""Drive the Kalshi fabricated-loss drain page by page, under D51 + D70 stop rules.

The repair rail itself (``app/tasks/repair_kalshi_fabricated_loss.py``) is
ATTENDED-ONLY and deliberately does one page per call. This is the attendant:
it dry-runs a page, banks that page's plan artifact as the backup BEFORE
anything else can overwrite the single durable plan slot, checks the stop
rules, applies, and carries the keyset cursor forward.

    python3 backend/scripts/drive_kalshi_fabricated_loss_drain.py \
        --band 47-67 --limit 10 --out ~/…/drain-CAL-P1026

Stop rules (D70, Fable-5 2026-09-05). The job HALTS — it never widens, never
retries blind — when:

* any call is non-200, or returns ``success: false``;
* an apply did not write exactly the legs its plan named
  (``attempted_leg_ids_equal_plan``), or banked no undo receipt before
  mutating, or left its invalidation obligation undischarged;
* a proposed write cannot be tied to a venue record — structurally
  ``markets_would_write`` may never exceed the markets the venue ANSWERED, so
  a violation means the rail's own exclusion has drifted;
* the batch's concurrent drift exceeds ``--max-drift-pct`` of its legs
  (something else is writing these rows);
* the batch proposes ``restore_winner`` legs and neither ``--check-restores``
  nor ``--allow-restore`` was given. The retraction arm removes a fabricated
  claim and is declared curve-neutral; the restore arm CROWNS a winner, so it
  is the arm D70's "2% disagreement with a second source" is about;
* with ``--check-restores``, the cumulative share of proposed changes whose
  restored winner DISAGREES with our own capture at settlement exceeds 2%
  over a denominator of at least ``--rate-floor`` proposed changes.

The second source, and why it is that one. D70 names "Polymarket / ESPN final
/ our own capture at settlement". Most of this population is not sports — the
first restore this rail proposed was a MrBeast-mention market — so ESPN and
Polymarket have no record of it at all, and the only second source that spans
the whole population is the price WE captured when it settled. A restored
winner disagrees when our captured price for it was under
``--disagree-below`` while a sibling leg in the same market was at least
``--disagree-margin`` higher: our own book was confidently pointing somewhere
else. A genuine upset trips that test too, which is why it is a RATE with a
floor and not a per-item veto — an upset is rare, a broken repair is not.
Every restore verdict, disagreeing or not, is written to
``restore-second-source.jsonl`` whether or not the rate halts the job.

A market whose legs price to more than ``_MUTUALLY_EXCLUSIVE_BOOK_SUM`` is
UNCOMPARABLE rather than concordant: its legs are independent binaries and the
test cannot speak about it either way (gotcha #53 — an absence of evidence is
not evidence of agreement).

Every page writes ``batch-NNN-dryrun.json`` (which contains the plan artifact —
that IS the backup) and ``batch-NNN-apply.json`` (which contains the
one-command undo), plus a line in ``progress.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RAIL = "kalshi-fabricated-loss"


def _curl(url: str, token: str, timeout: int = 180) -> tuple[int, Any]:
    """POST and return (http_status, parsed_body_or_text)."""
    proc = subprocess.run(
        [
            "curl", "-s", "-m", str(timeout), "-X", "POST",
            "-H", f"Authorization: Bearer {token}",
            "-w", "\n%{http_code}", url,
        ],
        capture_output=True, text=True,
    )
    raw = proc.stdout
    body, _, code = raw.rpartition("\n")
    try:
        return int(code.strip() or 0), json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return int(code.strip() or 0), body


def _q(params: dict[str, Any]) -> str:
    from urllib.parse import urlencode
    return urlencode({k: v for k, v in params.items() if v is not None})


class Halt(Exception):
    pass


_RESTORE_PRICE_SQL = (
    "SELECT fo.id, fo.market_id, fo.name, "
    "COALESCE(fo.calibration_probability, fo.opening_probability) AS price, "
    "(SELECT MAX(COALESCE(s.calibration_probability, s.opening_probability)) "
    " FROM futures_outcomes s WHERE s.market_id = fo.market_id AND s.id <> fo.id) "
    "AS sibling_max, "
    "(SELECT SUM(COALESCE(s.calibration_probability, s.opening_probability)) "
    " FROM futures_outcomes s WHERE s.market_id = fo.market_id) AS book_sum "
    "FROM futures_outcomes fo WHERE fo.id IN ({ids})"
)

# Above this, the market's legs cannot all be alternatives to each other, so a
# high-priced sibling is not evidence against a low-priced winner. Measured on
# the first 107 restores this rail proposed: every one of the 10 the naive
# sibling test flagged was a nested threshold ladder ("Above 148 million",
# "Above 3%") or an AP-top-25 set, where the lowest rung sits at 0.94-0.99 by
# construction and several rungs settle yes together (gotcha #23).
_MUTUALLY_EXCLUSIVE_BOOK_SUM = 1.25


def _db_query(api: str, token: str, sql: str, limit: int = 200) -> dict:
    proc = subprocess.run(
        [
            "curl", "-s", "-m", "40", "-X", "POST",
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: application/json",
            f"{api}/api/admin/db-query",
            "-d", json.dumps({"sql": sql, "limit": limit}),
        ],
        capture_output=True, text=True,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise Halt(f"db-query returned non-JSON: {proc.stdout[:200]}")


def _num(v) -> float | None:
    return None if v is None else float(v)


def second_source_verdicts(
    api: str, token: str, legs: list[dict], below: float, margin: float
) -> list[dict]:
    """Judge each restore_winner leg against the price WE captured at settlement.

    A restored winner is CONCORDANT when our own book was not confidently
    pointing at a different leg. It DISAGREES when its captured price was
    under `below` while a sibling in the same market was at least `margin`
    higher. A leg we captured no price for is UNCHECKABLE — reported, never
    silently counted as agreement (gotcha #53).
    """
    if not legs:
        return []
    ids = ",".join(str(int(leg["leg_id"])) for leg in legs)
    res = _db_query(api, token, _RESTORE_PRICE_SQL.format(ids=ids), limit=len(legs) + 10)
    if "rows" not in res:
        raise Halt(f"second-source query failed: {str(res)[:300]}")
    cols = res["columns"]
    by_id = {}
    for row in res["rows"]:
        r = dict(zip(cols, row))
        by_id[int(r["id"])] = r

    out = []
    for leg in legs:
        r = by_id.get(int(leg["leg_id"]))
        if r is None:
            out.append({**leg, "second_source": "UNCHECKABLE", "why": "leg not found"})
            continue
        price, sib = _num(r.get("price")), _num(r.get("sibling_max"))
        book = _num(r.get("book_sum"))
        rec = {
            **leg, "name": r.get("name"), "price": price, "sibling_max": sib,
            "book_sum": book,
        }
        if price is None:
            rec.update(second_source="UNCHECKABLE", why="no captured price at settlement")
        elif book is not None and book > _MUTUALLY_EXCLUSIVE_BOOK_SUM:
            rec.update(
                second_source="UNCOMPARABLE",
                why=(f"the market's legs price to {book:.2f}, so they are independent "
                     "binaries, not alternatives — a high sibling is not evidence "
                     "against this winner"),
            )
        elif price < below and sib is not None and sib - price >= margin:
            rec.update(
                second_source="DISAGREES",
                why=(f"our capture had it at {price:.3f} while a sibling was at "
                     f"{sib:.3f} — the book pointed elsewhere"),
            )
        else:
            rec.update(
                second_source="CONCORDANT",
                why=(f"our capture had it at {price:.3f}"
                     + (f" vs sibling max {sib:.3f}" if sib is not None else "")),
            )
        out.append(rec)
    return out


def check_dryrun(res: dict, allow_restore: bool) -> None:
    if not res.get("success", False):
        raise Halt(f"dry-run success=false: {res.get('refused') or res.get('reason')}")

    answered = (res.get("market_verdicts") or {}).get("answered", 0)
    would_write = res.get("markets_would_write", 0)
    if would_write > answered:
        raise Halt(
            f"D70: {would_write} markets would be written but the venue only ANSWERED "
            f"{answered} — a write not tied to a venue record"
        )

    if res.get("winners_would_restore", 0) and not allow_restore:
        raise Halt(
            f"D70: batch proposes {res['winners_would_restore']} restore_winner legs; "
            "the winner-crowning arm needs the second-source check before it goes in "
            "(re-run with --check-restores, or --allow-restore to skip the check)"
        )


def check_apply(res: dict, plan_legs: int, max_drift_pct: float) -> None:
    if not res.get("success", False):
        raise Halt(f"apply success=false: {res.get('success_note') or res.get('reason')}")
    if res.get("attempted_leg_ids_equal_plan") is not True:
        raise Halt("apply wrote legs the plan did not name")
    undo = res.get("undo") or {}
    if not undo.get("receipt_banked_before_mutation") or not undo.get("reversible"):
        raise Halt(f"apply is not reversible: {undo}")
    ob = res.get("invalidation_obligation") or {}
    if ob.get("state") != "discharged":
        raise Halt(f"invalidation obligation not discharged: {ob.get('state')}")
    drift = res.get("concurrent_drift_count", 0)
    if plan_legs and (drift / plan_legs) * 100 > max_drift_pct:
        raise Halt(f"concurrent drift {drift}/{plan_legs} legs exceeds {max_drift_pct}%")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", default=None, help="age slice to page first, e.g. 47-67")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-batches", type=int, default=1000)
    ap.add_argument("--max-drift-pct", type=float, default=20.0)
    ap.add_argument("--allow-restore", action="store_true",
                    help="apply restore_winner legs WITHOUT the second-source check")
    ap.add_argument("--check-restores", action="store_true",
                    help="apply restore_winner legs after judging each against our "
                         "own capture at settlement, halting on the D70 2% rate")
    ap.add_argument("--disagree-below", type=float, default=0.50)
    ap.add_argument("--disagree-margin", type=float, default=0.20)
    ap.add_argument("--rate-floor", type=int, default=50,
                    help="minimum proposed changes before the 2% rate can halt")
    ap.add_argument("--start-batch", type=int, default=1)
    ap.add_argument("--after-id", type=int, default=None)
    ap.add_argument("--after-date", default=None)
    ap.add_argument("--band-as-of", default=None)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("BAINLUCK_API / ADMIN_TOKEN must be set (source ~/.claude/.env)")
        return 2

    out = Path(os.path.expanduser(args.out))
    out.mkdir(parents=True, exist_ok=True)
    progress = out / "progress.jsonl"

    cursor = {
        "after_id": args.after_id,
        "after_date": args.after_date,
        "band_as_of": args.band_as_of,
    }
    limit = args.limit
    n = args.start_batch
    totals = {
        "batches": 0, "examined": 0, "answered": 0, "unexplained_absence": 0,
        "markets_written": 0, "legs_written": 0,
        "winners_restored": 0, "losses_retracted": 0, "drift": 0,
        "restores_checked": 0, "restores_disagree": 0, "restores_uncheckable": 0,
    }
    halt_reason = None
    t0 = time.time()

    try:
        while totals["batches"] < args.max_batches:
            params = {
                "limit": limit, "band": args.band,
                "after_id": cursor.get("after_id"),
                "after_date": cursor.get("after_date"),
                "band_as_of": cursor.get("band_as_of"),
            }
            url = f"{api}/api/admin/repairs/{RAIL}?{_q(params)}"
            code, body = _curl(url, token)
            if code != 200:
                raise Halt(f"dry-run HTTP {code}: {str(body)[:300]}")
            res = body["result"]

            # The plan artifact IS the backup, and the durable plan slot holds
            # exactly one plan: bank it before anything can overwrite it.
            (out / f"batch-{n:03d}-dryrun.json").write_text(json.dumps(body, indent=1))

            if res.get("stopped_on_venue_rate_limit"):
                print(f"[{n:03d}] venue 429 budget stop; limit {limit} -> {max(5, limit // 2)}, sleeping 60s")
                limit = max(5, limit // 2)
                time.sleep(60)
                continue

            check_dryrun(res, args.allow_restore or args.check_restores)

            # D70's second source, on the winner-crowning arm only.
            restore_legs = [
                {"leg_id": pl["leg_id"], "market_id": pl["market_id"],
                 "external_id": pl.get("external_id"), "batch": n}
                for pl in ((res.get("plan_artifact") or {}).get("legs") or [])
                if pl.get("verdict") == "restore_winner"
            ]
            if restore_legs and args.check_restores:
                verdicts = second_source_verdicts(
                    api, token, restore_legs, args.disagree_below, args.disagree_margin
                )
                with (out / "restore-second-source.jsonl").open("a") as fh:
                    for v in verdicts:
                        fh.write(json.dumps(v) + "\n")
                totals["restores_checked"] += len(verdicts)
                totals["restores_disagree"] += sum(
                    1 for v in verdicts if v["second_source"] == "DISAGREES")
                totals["restores_uncheckable"] += sum(
                    1 for v in verdicts
                    if v["second_source"] in ("UNCHECKABLE", "UNCOMPARABLE"))
                proposed = totals["legs_written"] + len(res.get("plan_leg_ids") or [])
                rate = (totals["restores_disagree"] / proposed * 100) if proposed else 0.0
                if proposed >= args.rate_floor and rate > 2.0:
                    raise Halt(
                        f"D70 stop rule: {totals['restores_disagree']} of {proposed} "
                        f"proposed changes ({rate:.1f}%) disagree with our capture at "
                        f"settlement — over the 2% bar"
                    )
                for v in verdicts:
                    if v["second_source"] != "CONCORDANT":
                        print(f"      restore {v['leg_id']} {v['second_source']}: "
                              f"{v.get('why')}", flush=True)

            examined = res.get("examined", 0)
            mv = res.get("market_verdicts") or {}
            plan_hash = res.get("plan_hash")
            plan_legs = len(res.get("plan_leg_ids") or [])

            row: dict[str, Any] = {
                "batch": n, "examined": examined,
                "answered": mv.get("answered", 0),
                "unexplained_absence": mv.get("unexplained_absence", 0),
                "leg_verdicts": res.get("leg_verdicts"),
                "plan_hash": plan_hash, "plan_legs": plan_legs,
                "cursor_in": dict(cursor),
            }

            if plan_legs and plan_hash and res.get("plan_persisted"):
                acode, abody = _curl(
                    f"{api}/api/admin/repairs/{RAIL}?apply=true&plan_hash={plan_hash}", token
                )
                if acode != 200:
                    raise Halt(f"apply HTTP {acode}: {str(abody)[:300]}")
                ares = abody["result"]
                (out / f"batch-{n:03d}-apply.json").write_text(json.dumps(abody, indent=1))
                check_apply(ares, plan_legs, args.max_drift_pct)
                row.update({
                    "applied": True,
                    "markets_written": ares.get("markets_written", 0),
                    "legs_written": ares.get("legs_written", 0),
                    "winners_restored": ares.get("winners_restored", 0),
                    "losses_retracted": ares.get("losses_retracted", 0),
                    "drift": ares.get("concurrent_drift_count", 0),
                    "undo": (ares.get("undo") or {}).get("apply"),
                })
                totals["markets_written"] += row["markets_written"]
                totals["legs_written"] += row["legs_written"]
                totals["winners_restored"] += row["winners_restored"]
                totals["losses_retracted"] += row["losses_retracted"]
                totals["drift"] += row["drift"]
            else:
                row["applied"] = False

            totals["batches"] += 1
            totals["examined"] += examined
            totals["answered"] += row["answered"]
            totals["unexplained_absence"] += row["unexplained_absence"]

            with progress.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            print(
                f"[{n:03d}] examined={examined} answered={row['answered']} "
                f"absent={row['unexplained_absence']} written={row.get('legs_written', 0)} "
                f"(retract {row.get('losses_retracted', 0)} / restore "
                f"{row.get('winners_restored', 0)}) cum_legs={totals['legs_written']}",
                flush=True,
            )

            nxt = res.get("next_cursor") or {}
            if res.get("exhausted") or not nxt.get("after_id"):
                halt_reason = (
                    f"exhausted ({res.get('exhausted_scope')}); "
                    f"population_exhausted={res.get('population_exhausted')}"
                )
                break
            if nxt.get("after_id") == cursor.get("after_id") and \
                    nxt.get("after_date") == cursor.get("after_date"):
                raise Halt("cursor did not advance — refusing to loop")
            cursor = nxt
            n += 1
            time.sleep(args.sleep)
        else:
            halt_reason = f"--max-batches {args.max_batches} reached"
    except Halt as e:
        halt_reason = f"HALT: {e}"
    except KeyboardInterrupt:
        halt_reason = "interrupted"

    summary = {
        "halt_reason": halt_reason,
        "totals": totals,
        "last_cursor": cursor,
        # `n` is incremented only at the bottom of a completed batch, so it is
        # already the next batch to run on both the HALT and the max-batches path.
        "next_batch": n,
        "band": args.band, "limit": limit,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1), flush=True)
    return 1 if (halt_reason or "").startswith("HALT") else 0


if __name__ == "__main__":
    sys.exit(main())
