"""Canonical issue-filing taxonomy — the ONE severity→priority mapping.

Every rail that CREATES a GitHub issue (sentinels, watchdogs, the alert intake,
the rage-shake bug reporter, the cockpit one-tap filer, the browser-audit sweep)
derives its labels here, so a freshly-filed issue can never arrive on the board
without a priority.

WHY THIS MODULE EXISTS. `BOARD-TAXONOMY.md` invariant 1 is *"every open issue has
priority+area+type (or taxonomy-exempt)"*, and the board lint that enforces it read
**41 open issues missing `priority:*`** on 2026-08-28. Four of those were filed by a
rail. A rail defect is the only half of that number a code change can close
permanently — a human-filed card needs a human triage pass, but a rail files the
same shape forever. Before this module each rail carried its own literal label list,
so "does this rail emit a priority?" had eight independent answers and three of them
were *no*: `scripts/alert_intake.py` (Sentry + CI failures), the weekly
feature-request digest, and the browser-audit sweep filer.

THE DEFAULT IS P2, AND THAT IS A RULING, NOT A GUESS. Alex ratified it 2026-07-27
(handoff README, Process v3 §5; Queue #279 / C72): *"sentinels/watchdogs/alert-intake
file NEW issues at priority:p2 + needs-triage — priority is earned at triage, not
stamped at birth."* So an unmapped or absent severity resolves to P2 and never to
"no label at all". `BOARD-TAXONOMY.md` names exactly two family defaults below P2 —
`parked` and Browser-audit, both P3 — and those are honoured by ``FAMILY_DEFAULT_PRIORITY``.

THE ONE INVARIANT WORTH REMEMBERING: :func:`priority_label` **always returns a label**.
There is no ``None`` branch, because every ``if priority:`` guard in this codebase was
a place an issue could be born unprioritized (`admin_file_issue.py` had one, and
`bug_report_github.build_labels` had another).

This module imports nothing from the rest of the codebase — same discipline as
``sport_keys.py`` (gotcha #3) — so any rail, task, route, or standalone script can
import it without dragging in the app. ``scripts/alert_intake.py`` runs on a bare
GitHub Actions runner with no installed dependencies and loads this file directly by
path for exactly that reason.
"""

# The closed set, most severe first. `BOARD-TAXONOMY.md`: "priority: p0 (drop
# everything) | p1 | p2 | p3. Priority lives in LABELS ONLY — never in titles."
PRIORITY_LABELS: tuple[str, ...] = (
    "priority:p0",
    "priority:p1",
    "priority:p2",
    "priority:p3",
)

# The ratified birth priority for an auto-filed issue (Alex 2026-07-27, Queue #279).
DEFAULT_PRIORITY = "priority:p2"

PRIORITY_PREFIX = "priority:"
AREA_PREFIX = "area:"
TYPE_PREFIX = "type:"

# Severity vocabulary → priority. Rails speak different dialects: Sentry emits
# `fatal`/`error`/`warning`/`info`, the watchdogs emit `p0`..`p3`, the calibration
# and flow sentinels emit `P1`/`P2`, GitHub Actions emits a run `conclusion`. Every
# dialect any rail in this repo actually produces is mapped here rather than in the
# rail, so adding a rail is a one-line lookup and not a fifth copy of this table.
SEVERITY_TO_PRIORITY: dict[str, str] = {
    # --- P0: drop everything ---
    "p0": "priority:p0",
    "sev0": "priority:p0",
    "fatal": "priority:p0",
    "critical": "priority:p0",
    "blocker": "priority:p0",
    # --- P1 ---
    "p1": "priority:p1",
    "sev1": "priority:p1",
    "error": "priority:p1",
    "high": "priority:p1",
    "red": "priority:p1",
    # --- P2: the default tier ---
    "p2": "priority:p2",
    "sev2": "priority:p2",
    "warning": "priority:p2",
    "warn": "priority:p2",
    "medium": "priority:p2",
    "moderate": "priority:p2",
    "amber": "priority:p2",
    # --- P3 ---
    "p3": "priority:p3",
    "sev3": "priority:p3",
    "info": "priority:p3",
    "low": "priority:p3",
    "minor": "priority:p3",
    "nit": "priority:p3",
}

# Per-family birth priority, overriding ``DEFAULT_PRIORITY`` when the rail supplies
# no severity of its own. `BOARD-TAXONOMY.md`, "Family defaults": parked → p3,
# Browser-audit → p3. A family default is a FLOOR for the no-severity case only — a
# rail that measured a real severity still wins (see :func:`priority_label`).
FAMILY_DEFAULT_PRIORITY: dict[str, str] = {
    "browser-audit": "priority:p3",
    "parked": "priority:p3",
    "digest": "priority:p3",
}


def normalize_severity(severity: object) -> str:
    """Lower-cased severity token, tolerant of every dialect a rail hands us.

    Accepts ``"P1"``, ``"p1"``, ``"priority:p1"``, ``"  Error "``, ``1``, an enum's
    ``.value``, or ``None``. Returns ``""`` when there is nothing to read — callers
    treat that as "no severity measured", not as an error.
    """
    if severity is None:
        return ""
    text = str(severity).strip().lower()
    if text.startswith(PRIORITY_PREFIX):
        text = text[len(PRIORITY_PREFIX) :]
    # A bare integer severity ("0".."3") is the priority tier itself.
    if text in {"0", "1", "2", "3"}:
        text = f"p{text}"
    return text


def priority_label(severity: object = None, *, family: str | None = None) -> str:
    """The ``priority:pN`` label this issue is born with. **Never returns ``None``.**

    Resolution order, most specific first:

    1. a severity this rail actually measured and that :data:`SEVERITY_TO_PRIORITY`
       recognises;
    2. the filing family's default (:data:`FAMILY_DEFAULT_PRIORITY` — Browser-audit
       and parked are P3 per `BOARD-TAXONOMY.md`);
    3. :data:`DEFAULT_PRIORITY` (P2, the ratified birth priority).

    An *unrecognised* severity falls through to 2/3 rather than raising. A rail
    inventing a new word should still file — losing the whole alert to a KeyError is
    strictly worse than filing it one tier off, and the sentinel that files blind is
    the failure this repo has already paid for twice.
    """
    mapped = SEVERITY_TO_PRIORITY.get(normalize_severity(severity))
    if mapped:
        return mapped
    if family:
        family_default = FAMILY_DEFAULT_PRIORITY.get(str(family).strip().lower())
        if family_default:
            return family_default
    return DEFAULT_PRIORITY


def ensure_taxonomy(
    labels: "list[str] | tuple[str, ...] | None" = None,
    *,
    severity: object = None,
    family: str | None = None,
    area: str | None = None,
    type_: str | None = None,
) -> list[str]:
    """A rail's label list with the required taxonomy families guaranteed present.

    ADDITIVE AND IDEMPOTENT, by design. A family already represented in ``labels`` is
    left exactly as the caller wrote it — this function fills gaps, it never
    re-decides. That matters most for ``priority:``: the shared sentinel rail already
    refuses to edit an existing issue's labels so a human's P0 is never silently
    downgraded by a later P2-default re-observation, and normalizing at *filing* time
    must not reintroduce that downgrade from the other end.

    ``area`` / ``type_`` are the rail's derivable fallbacks and may be ``None`` when a
    rail genuinely cannot derive one; only ``priority:`` is unconditional, because
    only ``priority:`` has a ratified default that applies to every issue.

    Order is preserved and duplicates are dropped, so the emitted list is stable
    enough for a test to pin.
    """
    out: list[str] = []
    seen: set[str] = set()
    for label in labels or ():
        text = str(label).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)

    def _missing(prefix: str) -> bool:
        return not any(existing.startswith(prefix) for existing in out)

    if _missing(PRIORITY_PREFIX):
        out.append(priority_label(severity, family=family))
    if area and _missing(AREA_PREFIX):
        out.append(area if area.startswith(AREA_PREFIX) else f"{AREA_PREFIX}{area}")
    if type_ and _missing(TYPE_PREFIX):
        out.append(type_ if type_.startswith(TYPE_PREFIX) else f"{TYPE_PREFIX}{type_}")
    return out
