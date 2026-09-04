#!/usr/bin/env python3
"""CAL-P128 — the board's sigma column, MEASURED instead of assumed.

WHY THIS FILE EXISTS
--------------------
``calibration_scorecard.py`` decides whether a cell goes on the repair queue by
asking whether its excess over the bar is established at ``SIGMA_GATE = 2.0``
standard errors. That gate is ratified and it is doing real work -- on the
2026-08-28 payload it cut the material over-bar list from 32 cells to 20.

The gate is not the problem. Its INPUT is. The scorecard's standard error is
``cell_se_pp(n) = 50/sqrt(n)`` over the cell's ROW count, and its own docstring
calls that "CONSERVATIVE" on the grounds that a binomial at p=0.5 is the
maximum-variance case. That reasoning is sound for *independent* rows and it is
the wrong model for this population, because these rows are not independent:

* ``kalshi/golf`` publishes 19.8 rows per market -- eighty "will X finish top
  10" rungs on one tournament, all determined by one leaderboard.
* ``polymarket/baseball`` publishes 7.6 rows per market.

A binomial SE over rows is a claim about how many INDEPENDENT observations the
cell contains, and on a clustered population it is not conservative at all --
it is too small, so the sigma it produces is too big, and cells land on the
queue that the sample cannot actually distinguish from the bar. CAL-P114
criterion 3 read golf at 7.8 sigma on the row basis; the measured value is
1.42, which is UNDER the ratified gate.

This has now happened enough times to stop being an anecdote. CAL-P120 removed
six cells this way and CAL-P127 removed a seventh, each one re-derived by hand
in a session and then carried forward as a paragraph in a handoff note. A
number that has to be re-derived by hand every session is a number the board
does not actually have.

So this file is the ledger: the measured cluster-bootstrap standard error for
every cell it has been run on, committed, keyed by cell, and carrying the
population it was measured against.

WHAT IS STORED, AND WHY IT IS THE SE AND NOT THE SIGMA
------------------------------------------------------
The load-bearing quantity is ``se_bootstrap_pp``, NOT the sigma.

A sigma is ``(ECE - bar) / SE``. Two of those three move for reasons that have
nothing to do with the sample's correlation structure: ``ECE`` moves whenever
the population is re-published, and ``bar`` moves whenever Alex re-ratifies a
cohort threshold (he did, on 2026-08-28, and every stored sigma from before
that instant silently meant something else afterwards). Storing the sigma bakes
both of them into a constant.

``SE`` is the one term that is a property of the SAMPLE -- of how many
independent markets the cell really contains and how hard they are correlated.
So the ledger stores the SE and lets the consumer recompute the sigma against
whatever the current ECE and bar are. That keeps the arithmetic in exactly one
place and it survives a re-ratification without anyone having to remember to
re-run twelve bootstraps.

The sigma as measured is stored too, but only as a CHECK -- :func:`validate`
recomputes it from the stored SE and refuses the ledger if they disagree. An
entry that cannot reproduce its own headline number is a transcription error,
and the whole point of this file is to stop numbers being carried by hand.

THE SE IS MEASURED ON THE EXACT RAIL AND APPLIED TO THE PAYLOAD
----------------------------------------------------------------
``calibration_cluster_sigma.py`` resamples the markets of the EXACT rail, so
the sigma it prints is ``(exact_ece - bar) / SE`` -- not ``(payload_ece - bar)
/ SE``. The two ECEs are close but not equal, because the rail's id-range sweep
and the published fold do not select the same rows: golf reads 3.84 over 20,666
rows on the rail and 3.88 over 20,500 on the payload.

The board scores the payload, so a consumer of this ledger divides the PAYLOAD
excess by this SE. That is a deliberate basis shift and it is recorded as one:
every entry stores ``ece_exact`` and ``ece_payload`` side by side, ``validate``
re-checks the stored sigma against the exact-rail numerator it was actually
computed from, and a consumer can size the shift instead of discovering it.

Mixing them is nonetheless the right move rather than a compromise. The
quantity the gate is about is the significance of the PUBLISHED excess, so the
payload belongs in the numerator; and the best available estimate of that
excess's standard error is the one that measured the correlation structure
instead of assuming it away. What would not be defensible is doing this
silently, which is why the two ECEs are never collapsed into one field.

THE PAIR CRITERION 3 AND CRITERION 6 ASKED FOR -- AND WHY IT IS NOT A
TEXTBOOK DESIGN EFFECT
----------------------------------------------------------------------
Alex's answer on criteria 3 and 6 was to report ``effective_n`` and a design
effect as a PAIR rather than either alone. Both fall straight out of the two
standard errors and neither needs a new measurement:

``variance_ratio_vs_board``  ``(se_bootstrap / se_row) ** 2``
``effective_n``              ``n / variance_ratio_vs_board`` -- the row count at
                             which the BOARD'S OWN formula would reproduce the
                             measured SE. Golf publishes 20,500 rows and its
                             measured SE is the one ``50/sqrt(n)`` would give
                             at about 7,050.

**The name matters, because this ratio is NOT a classical design effect and the
sweep proved it the hard way.** A design effect divides the true variance by the
SIMPLE-RANDOM-SAMPLE variance. This ratio divides it by ``50/sqrt(n)``, which is
the board's MAXIMUM-VARIANCE binomial bound -- the ``p=0.5`` case. Those are
different denominators and the gap between them is not small:

* ``kalshi/crypto`` measures 0.835 and ``polymarket/cricket`` 0.485. A classical
  design effect cannot go below 1 by clustering. These are below 1 because
  those cells' bins sit far from ``p=0.5``, so the true SRS variance is well
  under the board's bound and that slack outweighs the clustering inflation.
* Their measured sigmas are consequently HIGHER than the board's, not lower --
  cricket reads 5.87 on the board and 8.42 measured.

So the correction does not run one way. Reading this ratio as "how much
clustering inflates the variance" is wrong in both directions: it overstates
clustering wherever ``p`` is far from 0.5, and it hides that the board's
conservatism was doing real work. CAL-P127 quoted golf's 2.91 as a "design
effect"; that number is reproduced here exactly, under a name that says what it
is a ratio TO.

POPULATION DIVERGENCE -- AND WHY IT IS NOT "THE RAIL UNDER-COUNTS"
-------------------------------------------------------------------
The bootstrap runs on the EXACT rail; the board scores the PAYLOAD. Where the
two disagree about how many rows the cell contains, the SE and the excess are
measurements of DIFFERENT populations, and dividing one by the other is not a
sigma of anything. ``exact_coverage`` is ``n_exact / n_payload`` and it is
stored on every entry so that disagreement is visible rather than assumed away.

On the 2026-08-29 sweep ten of twelve cells sat inside ±3% of 1.0. Two did not,
and it would be easy -- and wrong -- to read both as the rail missing rows:

``polymarket/basketball`` 0.641
    The payload is the inflated side, not the rail the deficient one. CAL-P126
    measured this cell at **43.44% phantom**: 13,116 published rows carrying
    only 7,419 distinct outcomes, with 11,394 rows duplicated. The rail's 8,426
    is far nearer that 7,419 than the payload's 13,135 is. So the rail is closer
    to the truth here, and the *board's* ``50/sqrt(n)`` is the number built on a
    population that does not exist -- an inflated ``n`` makes the board's SE too
    small and its sigma too big.
``polymarket/hockey`` 0.780
    Unexplained. This cell is in CAL-P126's unmeasured 21, so there is no
    phantom measurement to attribute the gap to and no warrant for assuming it
    is the same cause.

The first draft of this file called the flag ``LOW_COVERAGE`` and reasoned that
a subsample SE is too big, so the sigma is too small, so the failure direction
is the one that shortens the board. That reasoning is sound ONLY if the rail is
the deficient side, and on the one cell it actually mattered for, it is not.
Hence the neutral name: the flag records that the two populations DISAGREE, and
declines to adjudicate which is right from inside this file.

Either way the consequence is the same and it is conservative: an entry outside
:data:`COVERAGE_BAND` reports its numbers and is counted as neither established
nor refuted. Whether the fix is a rail repair or a producer dedup is a question
for the cell's own diagnosis, not for a standard error.

STALENESS IS A STATE, NOT A JUDGEMENT CALL
-------------------------------------------
Every entry carries the ``population_version`` it was measured on. A bootstrap
SE is a measurement of one specific set of rows; when the producer restages,
the rows change and the entry describes a population that is no longer being
served. :func:`lookup` therefore returns a STATUS -- ``FRESH``, ``STALE`` or
``ABSENT`` -- and never silently hands back a number from a different
population. A consumer that wants to use a stale entry has to say so out loud.

This is gotcha #53 in ledger form: "it returned a number" is not "the number
applies to what you are looking at".

AMENDED 2026-09-03 (CAL-P998) -- THE STATE IS THE CELL'S, NOT THE VERSION'S
-----------------------------------------------------------------------------
The rule above was right about the principle and wrong about the test, and the
cost of the difference was measured on the live board before this paragraph was
written: **the overlay covered 0 of 14 queued cells while 14 measured entries
sat in this file.** Every entry was banked against ``q268``; production serves
``q269``; so every entry read ``STALE`` and the board ran entirely on the
``50/sqrt(n)`` estimate this file exists to correct. A correction that expires
on every republish -- and the producer republishes several times a day -- is a
correction the board never actually has. CAL-P120's six cells and CAL-P127's
seventh were re-derived by hand *because* of this, not in spite of it.

``population_version`` is a proxy for the question that matters, and it is a
poor one. The question is whether THIS CELL still contains the rows the SE was
measured over. This file already owns the instrument for asking that directly
-- :data:`COVERAGE_BAND` compares ``n_exact`` with ``n_payload`` on the RAIL
axis -- and the same comparison on the TIME axis separates the live board
cleanly:

===============================  =========  =========  =======
cell                             n at q268  n at q269  drift
===============================  =========  =========  =======
``kalshi/golf``                     20,500     21,085   +2.9%
``kalshi/tech``                      1,203      1,246   +3.6%
``kalshi/entertainment``             8,355      8,922   +6.8%
``polymarket/cricket``               3,252      2,944    -9.5%
``polymarket/hockey``                2,281      1,730   -24.2%
``polymarket/economics``            12,882      9,656   -25.0%
``polymarket/golf``                  6,463      4,339   -32.9%
``polymarket/basketball``           13,135      7,591   -42.2%
===============================  =========  =========  =======

Those are two different facts wearing one status. The kalshi cells are the same
cells with a few days more settlement on them; the polymarket cells are not --
``polymarket/basketball``'s 42% is CAL-P126's phantom duplication being
*removed*, i.e. the population genuinely changed underneath the measurement. A
version-identity test cannot tell them apart and throws both away. A material
test keeps the first and still refuses the second, which is what the original
paragraph was actually trying to protect.

So :func:`lookup` gains a fourth status, ``CARRIED``: measured on another
population, but the cell has not materially moved. It is a SEPARATE status and
never collapses into ``FRESH`` -- the consumer counts it in its own bucket and
the render names the population it came from, so "say so out loud" is enforced
by the shape of the return rather than by a convention. The load-bearing reason
this is legitimate at all is the one this file already states above: the ledger
stores the SE precisely BECAUSE the SE is the term that does not move when the
ECE, the bar or the population version do.

**The residual, named rather than hidden.** A stable ``n`` is necessary, not
sufficient -- a cell could in principle exchange its rows wholesale and keep its
count. There is no cheap payload-side test for that, so ``CARRIED`` carries
``population_version`` and ``generated_at`` onto the row: the age of the
measurement is a fact on the board, not a constant buried in this file. A
carried entry is a standing request to re-measure, and the scorecard counts it
so the measurement lane can see the backlog.

AMENDED 2026-09-04 (CAL-P1002) -- THE CONSUMING HALF MOVED INTO THE APP
------------------------------------------------------------------------
Alex ruled D62 = A: the measured sigma DECIDES the repair queue rather than
reporting beside it. ``cells_at_bar`` is a served field
(``/api/calibration.scorecard``, CAL-P998 / D46), so the moment this ledger
decides it, it has to be read where that field is computed -- otherwise the
served needle and this board's needle are two different numbers on day one,
which is the condition D46 was created to end.

So everything that READS a ledger -- the statuses, the two bands, ``lookup``,
``validate``, ``load`` -- now lives in :mod:`app.utils.calibration_sigma` and is
imported below. This file keeps what BUILDS one: the artifact fold, ``--build``,
``--show``. The names are re-exported unchanged, so ``calibration_scorecard.py``
and ``calibration_cluster_sigma.py`` import the same symbols they always did and
there is still exactly one definition of each.

**The ledger FILE moved with them, and that was not tidying.** It was committed
at ``artifacts/calibration-scorecard/measured-sigma.json``; Heroku builds this
app through ``subdir-heroku-buildpack`` with ``PROJECT_PATH=backend``, so the
repo-root ``artifacts/`` tree is not in the slug and that path does not exist on
the dyno. Reading it from the app would have produced a perfect ledger in every
test and an absent one on every production request -- CAL-P129's bug in the one
environment that serves readers. It now lives in ``backend/app/data/``. The
scorecard's ``history.jsonl`` stays here: it is written by a script and read by
nothing served.

Usage::

    # rebuild from every sigma artifact on disk
    python3 backend/scripts/calibration_sigma_ledger.py --build \\
        artifacts/cal-p12*/sigma-*.json

    # read it back
    python3 backend/scripts/calibration_sigma_ledger.py --show
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# `backend/`, so `app.utils.calibration_sigma` imports whether this script is
# run from the repo root or from `backend/`. Same two-entry insert as
# `calibration_scorecard.py`, same reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The READING half, imported and never re-implemented (CAL-P1002). Re-exported
# below so every existing caller of this module keeps resolving these names.
from app.utils.calibration_sigma import (  # noqa: E402,F401
    CELL_DRIFT_BAND,
    COVERAGE_BAND,
    DECIDING_STATUSES,
    LEDGER_PATH,
    SCHEMA,
    SIGMA_RECHECK_TOL,
    STATUS_ABSENT,
    STATUS_CARRIED,
    STATUS_FRESH,
    STATUS_POPULATION_DIVERGENCE,
    STATUS_STALE,
    cell_drift,
    cell_key,
    effective_n,
    exact_coverage,
    load,
    lookup,
    validate,
    variance_ratio_vs_board,
)

__all__ = [
    "CELL_DRIFT_BAND", "COVERAGE_BAND", "DECIDING_STATUSES", "LEDGER_PATH",
    "SCHEMA", "SIGMA_RECHECK_TOL", "STATUS_ABSENT", "STATUS_CARRIED",
    "STATUS_FRESH", "STATUS_POPULATION_DIVERGENCE", "STATUS_STALE",
    "build", "cell_drift", "cell_key", "effective_n", "entry_from_sigma_json",
    "exact_coverage", "load", "lookup", "validate", "variance_ratio_vs_board",
]


def entry_from_sigma_json(obj: dict, artifact: str) -> dict:
    """Fold one ``calibration_cluster_sigma.py`` output into a ledger entry."""
    se = obj["se"]
    sig = obj["sigma"]
    payload = obj.get("payload") or {}
    exact = obj.get("exact") or {}
    n = payload.get("n")
    ratio = variance_ratio_vs_board(se.get("bootstrap"), se.get("row"))
    return {
        "source": obj["source"],
        "category": obj["category"],
        # The population this SE describes. Not decoration -- `lookup` refuses
        # to apply the entry to any other one.
        "population_version": payload.get("population_version"),
        "generated_at": payload.get("generated_at"),
        # The load-bearing number.
        "se_bootstrap_pp": se.get("bootstrap"),
        # Kept so a reader can see what the correction did rather than having
        # to trust that it did something.
        "se_row_pp": se.get("row"),
        "se_market_pp": se.get("market"),
        "clusters": obj.get("clusters"),
        "rows_per_cluster": obj.get("rows_per_cluster"),
        "variance_ratio_vs_board": ratio,
        "effective_n": effective_n(n, ratio),
        # How much of the published cell the bootstrap actually saw. Below
        # COVERAGE_BAND this entry reports but does not decide.
        "exact_coverage": exact_coverage(exact.get("n"), n),
        # `as_measured` is the CHECK, not the answer. `validate` reproduces
        # `sigma_bootstrap` from `se_bootstrap_pp` and refuses on a mismatch.
        #
        # TWO ECEs, AND THE DIFFERENCE IS NOT A ROUNDING ERROR. The bootstrap
        # resamples the EXACT RAIL's markets, so both its SE and its point
        # estimate are on the exact rail's population -- `ece_exact`, over
        # `exact.n` rows. The board scores the PAYLOAD -- `ece_payload`, over
        # `n` rows. They differ because the rail's id-range sweep and the
        # published fold do not select identically (golf 3.84 vs 3.88 over
        # 20,666 vs 20,500 rows; baseball 4.68 vs 4.80 over 41,102 vs 43,768).
        #
        # `excess` here is therefore the EXACT-rail one, because that is the
        # numerator the stored sigma was actually divided by, and `validate`
        # has to be able to reproduce it. A consumer that applies this SE to
        # the PAYLOAD excess is making a documented basis shift, and
        # `payload_excess` is stored so it can size that shift rather than
        # assume it away.
        "as_measured": {
            "n": n,
            "n_exact": exact.get("n"),
            "ece_payload": payload.get("ece"),
            "ece_exact": exact.get("ece"),
            "bar": obj.get("bar"),
            "excess": obj.get("excess"),
            "payload_excess": (
                round(payload["ece"] - obj["bar"], 6)
                if payload.get("ece") is not None and obj.get("bar") is not None
                else None
            ),
            "sigma_row": sig.get("row"),
            "sigma_bootstrap": sig.get("bootstrap"),
            "bootstrap_ci": obj.get("bootstrap_ci"),
            "established_at_gate": obj.get("established"),
            "sigma_gate": obj.get("sigma_gate"),
        },
        "boot": obj.get("boot"),
        "seed": obj.get("seed"),
        "artifact": artifact,
    }


def build(paths: list[Path]) -> dict:
    """Fold sigma artifacts into a ledger, newest measurement per cell winning.

    "Newest" is by ``generated_at`` of the population measured, not by file
    mtime: re-running the same cell against the same payload must be
    idempotent, and a re-measured cell on a FRESHER payload must win over a
    stale one regardless of which file was touched last.
    """
    entries: dict[str, dict] = {}
    for p in sorted(paths):
        obj = json.loads(Path(p).read_text())
        if "se" not in obj or "sigma" not in obj:
            continue
        entry = entry_from_sigma_json(obj, str(p))
        key = cell_key(entry["source"], entry["category"])
        prev = entries.get(key)
        if prev is None or (entry.get("generated_at") or "") >= (
            prev.get("generated_at") or ""
        ):
            entries[key] = entry
    return {
        "schema": SCHEMA,
        "note": (
            "Measured cluster-bootstrap standard errors per published calibration "
            "cell. Built by calibration_sigma_ledger.py --build from "
            "calibration_cluster_sigma.py artifacts. The load-bearing field is "
            "se_bootstrap_pp; sigma is recomputed by the consumer against the "
            "CURRENT excess so a re-ratified bar cannot silently invalidate it."
        ),
        "entries": dict(sorted(entries.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", nargs="+", metavar="SIGMA_JSON")
    ap.add_argument("--out", default=str(LEDGER_PATH))
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    if args.build:
        # Third instance of the same class, fixed in the same commit: a
        # mistyped or moved artifact used to be filtered out here and the run
        # then printed "wrote ... (13 cells from 13 artifacts)" for fourteen
        # arguments. Silently building a SHORTER ledger is how a cell loses its
        # measurement without anybody deciding to drop it.
        missing = [x for x in args.build if not Path(x).exists()]
        if missing:
            print("ARTIFACT(S) NOT FOUND — nothing written:")
            for m in missing:
                print(f"  {m}")
            return 1
        paths = [Path(x) for x in args.build]
        ledger = build(paths)
        problems = validate(ledger)
        if problems:
            print("LEDGER INVALID — nothing written:")
            for p in problems:
                print(f"  {p}")
            return 1
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
        print(f"wrote {out}  ({len(ledger['entries'])} cells from {len(paths)} artifacts)")

    if args.show or not args.build:
        ledger = load(args.out if args.build else LEDGER_PATH, missing_ok=True)
        entries = ledger.get("entries") or {}
        if not entries:
            print("ledger is empty")
            return 0
        print(f"{'cell':<28} {'pop':>5} {'sig_row':>8} {'sig_boot':>9} "
              f"{'varrat':>7} {'n':>8} {'eff_n':>8} {'cover':>6}")
        for key, e in entries.items():
            m = e["as_measured"]
            cov = e.get("exact_coverage")
            low = cov is not None and not (
                COVERAGE_BAND[0] <= cov <= COVERAGE_BAND[1]
            )
            print(
                f"{key:<28} {str(e['population_version']):>5} "
                f"{m['sigma_row']:>8.2f} {m['sigma_bootstrap']:>9.2f} "
                f"{e['variance_ratio_vs_board']:>7.2f} {m['n']:>8,} "
                f"{e['effective_n']:>8,} {(f'{cov:.3f}' if cov else '—'):>6}"
                + ("  POPULATION DIVERGENCE — reports, does not decide" if low else "")
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
