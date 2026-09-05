"""CAL-P1002 — the MEASURED sigma ledger, read by the APP because it now DECIDES.

D62 = A (Alex, 2026-09-04). Until this module existed the measured
cluster-bootstrap standard error lived entirely in ``backend/scripts/`` and was
a *reporting* column: it printed beside the board's ``50/sqrt(n)`` estimate and
changed no verdict. D62 flips it — the measured number decides which cells go on
the repair queue — and D46's rule then forces the rest: ``cells_at_bar`` is a
SERVED field, so an overlay that decides it has to be computed where the field
is computed, or the served needle and the script's needle disagree from day one.

So the CONSUMING half of ``calibration_sigma_ledger.py`` moves here. The
BUILDING half (``--build``, the artifact fold, the ``--show`` renderer) stays in
the script, which imports every name below rather than restating it. That
direction is the load-bearing one and it is the same one CAL-P998 established
for the bars: the app cannot import ``scripts/`` (not on the dyno's path), so a
definition the script kept would become a second implementation of the gate.

WHY THE LEDGER FILE MOVED, AND WHY THAT IS NOT A TIDY-UP
--------------------------------------------------------
The ledger was committed at ``<repo>/artifacts/calibration-scorecard/measured-sigma.json``.
**That path does not exist on the dyno.** Heroku builds this app through
``timanovsky/subdir-heroku-buildpack`` with ``PROJECT_PATH=backend`` — the
buildpack promotes ``backend/`` to the slug root and discards everything beside
it, so the repo-root ``artifacts/`` tree is not deployed at all. An app-side
read of the old path would have returned "absent" on every production request
while returning a perfectly good ledger in every test and every local run.

That is CAL-P129's bug — the overlay silently absent because a path resolved
somewhere real code never looks — one environment worse, because the
environment where it fails is the only one that serves readers. So the ledger
now lives in ``app/data/`` beside the other committed data files the app reads,
where "is it deployed" has the same answer as "is the app deployed".

The scorecard's ``history.jsonl`` stays in ``artifacts/``. It is the board's
memory, written by a script, read by nothing served. Only the file that decides
a served number had to move.

FAIL LOUD, NOT CLOSED, AND NEVER SILENT
----------------------------------------
:func:`load_default` never raises at the request path. A missing or incoherent
ledger degrades the score to the row estimate — the pre-D62 behaviour, which is
a defensible number rather than no number — and returns a REASON with it. The
reason is published on ``scorecard.sigma_overlay``, because a needle that
quietly changes basis is exactly the failure this module was written to end: on
the 2026-09-04 board the two bases read 35/48 and 34/48, and nothing on the wire
would have said which one a reader was looking at.

Everything below this line about the ledger's semantics — what is stored and why
it is the SE and not the sigma, the two ECEs, ``COVERAGE_BAND``,
``CELL_DRIFT_BAND`` and the ``CARRIED`` status — is CAL-P128's and CAL-P998's
reasoning, moved with the code it governs. The full derivation, the sweep tables
and the war stories stay in ``backend/scripts/calibration_sigma_ledger.py``'s
docstring; what is repeated here is only what a reader of *this* file needs to
not misuse it.

THIS MODULE IMPORTS NOTHING FROM THE APP. Same rule as ``sport_keys.py`` and
``calibration_scoring.py``, same reason.
"""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path

#: The committed ledger, anchored to the PACKAGE and therefore to the slug.
#: ``parents[1]`` is ``app/``; the file sits in ``app/data/`` with the other
#: committed data the app reads. Absolute for CAL-P129's reason (a relative
#: default resolves against the caller's CWD and produces a complete, plausible
#: board with the whole overlay silently missing) and inside ``backend/`` for
#: this module's docstring's reason (``PROJECT_PATH=backend``).
LEDGER_PATH = Path(__file__).resolve().parents[1] / "data" / "calibration_measured_sigma.json"

SCHEMA = 1

#: Tolerance for :func:`validate`'s reproduction of a stored sigma from its
#: stored SE. A transcription check, not a statistical one — both numbers come
#: out of one bootstrap run. 0.01 is one unit in the last place the board prints.
SIGMA_RECHECK_TOL = 0.01

STATUS_FRESH = "FRESH"
STATUS_STALE = "STALE"
STATUS_ABSENT = "ABSENT"
STATUS_POPULATION_DIVERGENCE = "POPULATION_DIVERGENCE"

#: Measured on another population, but the CELL has not materially moved.
#: Deliberately its own value and never an alias of :data:`STATUS_FRESH`: the
#: whole warrant for carrying an entry is that the consumer can still tell it
#: apart from one measured on the payload it is being applied to.
STATUS_CARRIED = "CARRIED"

#: The statuses whose measured sigma is allowed to DECIDE a verdict (D62 = A).
#: ``POPULATION_DIVERGENCE`` is excluded on purpose and that exclusion is the
#: conservative half of this change: when the rail and the payload disagree
#: about how many rows the cell holds, the SE and the excess describe different
#: populations and their ratio is not a sigma of either — so those cells keep
#: being decided by the board's own estimate, and their measured numbers are
#: still shown because they are the only measurement of that cell anyone has.
DECIDING_STATUSES = frozenset({STATUS_FRESH, STATUS_CARRIED})

#: The band of ``n_exact / n_payload`` inside which the bootstrap's rail and the
#: published payload are taken to be describing the same cell. Two-sided: a
#: first draft used a one-sided floor on the theory that only an under-counting
#: rail could hurt, which quietly assumed the payload is always right, and
#: ``polymarket/basketball`` is 43.44% phantom (CAL-P126) and it is not.
COVERAGE_BAND = (0.90, 1.10)

#: The band of ``n_now / n_at_measurement`` inside which an entry measured on a
#: DIFFERENT population still describes this cell — the time axis of the same
#: comparison :data:`COVERAGE_BAND` makes on the rail axis, and the same width,
#: because it is the same question about the same quantity.
CELL_DRIFT_BAND = (0.90, 1.10)


def cell_key(source: str, category: str) -> str:
    return f"{source}/{category}"


def cell_drift(entry: dict, n_payload: int | None) -> float | None:
    """``n_payload / n_at_measurement`` — how much the cell moved since.

    Returns ``None`` when either side is unknown, which is NOT a pass: a drift
    that cannot be computed cannot clear :data:`CELL_DRIFT_BAND`, so the entry
    stays stale. An untestable claim is refused, not assumed (gotcha #53).
    """
    measured_n = ((entry or {}).get("as_measured") or {}).get("n")
    if not measured_n or not n_payload:
        return None
    return round(n_payload / measured_n, 4)


def variance_ratio_vs_board(se_bootstrap: float, se_row: float) -> float | None:
    """Measured variance over the BOARD'S ``50/sqrt(n)`` variance.

    Squared because this is a ratio of VARIANCES, not of standard errors.
    Values BELOW 1 are legitimate and common — the denominator is a
    maximum-variance binomial bound, not an SRS variance, so a cell whose bins
    sit far from ``p=0.5`` measures under 1 with nothing wrong. Which is why
    this is not called ``design_effect``.
    """
    if not se_row or se_bootstrap is None:
        return None
    return round((se_bootstrap / se_row) ** 2, 3)


def effective_n(n: int, ratio: float | None) -> int | None:
    """The row count at which the board's own formula gives the measured SE."""
    if not ratio or not n:
        return None
    return int(round(n / ratio))


def exact_coverage(n_exact: int | None, n_payload: int | None) -> float | None:
    """How much of the published cell the bootstrap actually resampled."""
    if not n_exact or not n_payload:
        return None
    return round(n_exact / n_payload, 4)


class LedgerIncoherent(ValueError):
    """The ledger parsed but failed :func:`validate`.

    Its own class rather than a bare ``ValueError`` because the two failures
    this module can hit are different stories and only one of them is about the
    ledger's CONTENT. ``json.JSONDecodeError`` is a ``ValueError`` subclass, so
    catching ``ValueError`` would file a truncated or half-written file as
    ``ledger_incoherent`` — "an entry cannot reproduce its own sigma", which is
    a claim about the measurement — when the true story is "these bytes are not
    JSON", which is a claim about the file. The reasons are published on the
    wire, so the distinction is one a reader acts on.
    """


def validate(ledger: dict) -> list[str]:
    """Return a list of problems. Empty list means the ledger is coherent.

    Each entry must reproduce its own measured sigma from its own stored SE.
    That is the only claim the ledger makes about itself and it is the one that
    matters: if it holds, a consumer recomputing sigma against a CURRENT excess
    is doing the arithmetic the bootstrap did with a fresher numerator.
    """
    problems: list[str] = []
    if ledger.get("schema") != SCHEMA:
        problems.append(f"schema {ledger.get('schema')!r} != {SCHEMA}")
    for key, e in (ledger.get("entries") or {}).items():
        if cell_key(e.get("source", "?"), e.get("category", "?")) != key:
            problems.append(f"{key}: key does not match source/category")
        se = e.get("se_bootstrap_pp")
        m = e.get("as_measured") or {}
        excess, stored = m.get("excess"), m.get("sigma_bootstrap")
        if not se:
            problems.append(f"{key}: no se_bootstrap_pp")
            continue
        if excess is None or stored is None:
            problems.append(f"{key}: cannot re-check sigma (missing excess/sigma)")
            continue
        recomputed = excess / se
        if not math.isclose(recomputed, stored, abs_tol=SIGMA_RECHECK_TOL):
            problems.append(
                f"{key}: stored sigma {stored:.4f} != excess/se {recomputed:.4f}"
            )
        if not e.get("population_version"):
            problems.append(f"{key}: no population_version — cannot be applied safely")
    return problems


def load(path: Path | str = LEDGER_PATH, *, missing_ok: bool = False) -> dict:
    """Load and validate. A ledger that fails :func:`validate` RAISES.

    Refusing beats degrading. A silently-wrong SE now moves cells across the
    ratified gate — since D62 it decides — and it would do so in the direction
    that makes the board look shorter, which is the failure mode this program
    keeps having.

    ``missing_ok`` is the same sentence applied to ABSENCE: an absent file and
    an empty ledger are different facts and they used to produce identical
    output (gotcha #53). Only callers entitled to the empty reading — the
    builder, which legitimately runs before any ledger exists — ask for it by
    name. :func:`load_default` does NOT: it catches the refusal and reports it.
    """
    p = Path(path)
    if not p.exists():
        if missing_ok:
            return {"schema": SCHEMA, "entries": {}}
        raise FileNotFoundError(
            f"sigma ledger not found: {p}\n"
            "This is refused rather than read as 'nothing has been measured' — "
            "an empty overlay is a claim about the board, not about a file."
        )
    ledger = json.loads(p.read_text())
    problems = validate(ledger)
    if problems:
        raise LedgerIncoherent(f"sigma ledger {p} is incoherent: {problems}")
    return ledger


# ---------------------------------------------------------------------------
# The request path
# ---------------------------------------------------------------------------

#: ``(ledger_or_None, reason_or_None)``, memoised per process. The ledger is a
#: COMMITTED file: it changes on deploy and a dyno that has read it once has
#: read the only version it will ever serve. Re-reading per request would put a
#: filesystem call on ``/api/calibration``'s tier-1 path — the one that answers
#: from process memory with no database work at all — for a file that cannot
#: have changed.
_cached: tuple[dict | None, str | None] | None = None
_lock = threading.Lock()

#: Reasons published on ``scorecard.sigma_overlay.reason``. Enumerated so a
#: guard can assert on them rather than on prose that gets reworded.
REASON_ABSENT = "ledger_absent"
REASON_INCOHERENT = "ledger_incoherent"
#: Bytes that are not JSON. Separate from :data:`REASON_INCOHERENT` because
#: "this file is not the ledger" and "this ledger's arithmetic does not check
#: out" send a reader to different places — see :class:`LedgerIncoherent`.
REASON_MALFORMED = "ledger_malformed"
REASON_UNREADABLE = "ledger_unreadable"


def load_default(*, refresh: bool = False) -> tuple[dict | None, str | None]:
    """The request-path read: ``(ledger, reason)``, and it never raises.

    A failure returns ``(None, reason)`` and the score falls back to the
    board's row estimate — a defensible number rather than no number — with the
    reason travelling onto the wire. It does NOT fall back silently, which is
    the whole point: the two bases give different needles (35/48 and 34/48 on
    the 2026-09-04 board) and a reader must be able to tell which they have.
    """
    global _cached
    if refresh:
        with _lock:
            _cached = None
    if _cached is not None:
        return _cached
    with _lock:
        if _cached is None:
            try:
                _cached = (load(LEDGER_PATH), None)
            except FileNotFoundError:
                _cached = (None, f"{REASON_ABSENT}: {LEDGER_PATH.name}")
            except LedgerIncoherent as exc:
                _cached = (None, f"{REASON_INCOHERENT}: {exc}")
            except json.JSONDecodeError as exc:
                # Ordered AFTER LedgerIncoherent and named separately on purpose:
                # both are `ValueError`s and one catch would file bad bytes as a
                # bad measurement. See `LedgerIncoherent`.
                _cached = (None, f"{REASON_MALFORMED}: {exc.msg} at line {exc.lineno}")
            except Exception as exc:  # noqa: BLE001 — a ledger never takes the page down
                _cached = (None, f"{REASON_UNREADABLE}: {type(exc).__name__}")
    return _cached


def lookup(
    ledger: dict,
    source: str,
    category: str,
    population_version: str | None,
    n_payload: int | None = None,
):
    """Return ``(entry, status)``. Never returns a number without its status.

    ``n_payload`` is what turns a population mismatch into a QUESTION rather
    than a verdict: an entry from another population whose cell is still the
    same size within :data:`CELL_DRIFT_BAND` is ``CARRIED``, one whose cell has
    moved is ``STALE``. Before CAL-P998 the test was ``population_version``
    identity, and that left the overlay covering 0 of 14 queued cells with 14
    measured entries committed — the correction expiring on every republish.

    The argument is OPTIONAL and its absence fails closed to the pre-amendment
    behaviour: a caller that cannot say how big the cell is now gets ``STALE``.
    """
    e = (ledger.get("entries") or {}).get(cell_key(source, category))
    if e is None:
        return None, STATUS_ABSENT
    carried = False
    if population_version and e.get("population_version") != population_version:
        drift = cell_drift(e, n_payload)
        if drift is None or not (CELL_DRIFT_BAND[0] <= drift <= CELL_DRIFT_BAND[1]):
            return e, STATUS_STALE
        carried = True
    cov = e.get("exact_coverage")
    if cov is not None and not (COVERAGE_BAND[0] <= cov <= COVERAGE_BAND[1]):
        # Checked AFTER the carry test and it outranks it: a cell whose rail and
        # payload describe different populations has no sigma to offer, and that
        # is true whether the entry is fresh or carried.
        return e, STATUS_POPULATION_DIVERGENCE
    return e, (STATUS_CARRIED if carried else STATUS_FRESH)
