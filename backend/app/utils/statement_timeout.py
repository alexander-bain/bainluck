"""Is this exception our own budget guard firing, or a real error?

One question, asked in two places and answered the same way, because getting it
wrong in either direction is a bug with a different shape:

* too WIDE and a genuine query defect is contained as "ran out of time" — the
  part silently does nothing forever (gotcha #45: never catch-all around work
  nobody is watching);
* too NARROW and a routine budget expiry propagates as a 500.

``SET LOCAL statement_timeout`` cancellation surfaces through asyncpg as
``QueryCanceledError`` and through psycopg2 as ``QueryCanceled``, and SQLAlchemy
re-wraps both in a ``DBAPIError`` whose ``__cause__`` carries the original. Class
name first, message second, so a wrapped cancellation is recognised without
importing either driver here (this module imports nothing, and must stay that
way — it is reached from route code on the request path).

🔴 ORIGIN, AND WHY THIS FILE IS NOT YET THE ONLY COPY.
``app/tasks/backfill_winners.py::_is_statement_timeout`` is where this predicate
was first written and it is character-for-character the same question. Ruling 005
(extract-on-touch) says the second customer collapses the duplicate — but
``backfill_winners.py`` is carried by an unmerged, cert-held branch
(``program/calibration-118``), and editing it from this lane would hand the
Integrator a conflict in a 7,000-line file for a two-line change. The fold is
therefore PARKED (LAT-P145-2), not skipped: this module is the shared home, the
task-side copy is the one that moves, and it moves the moment that branch lands.
"""


def is_statement_timeout(exc: BaseException) -> bool:
    """True only for a cancellation caused by our own ``SET LOCAL statement_timeout``.

    Total by construction: this is called from inside ``except`` handlers whose
    whole job is to keep a page rendering, so it must never be the thing that
    raises. An exception with an unreadable ``str()`` reads as "not a timeout",
    which routes it to the loud path — the safe direction (a real error reported
    as a real error).
    """
    seen: set[int] = set()
    cursor: BaseException | None = exc
    while cursor is not None and id(cursor) not in seen:
        seen.add(id(cursor))
        if type(cursor).__name__.startswith("QueryCanceled"):
            return True
        try:
            text_form = str(cursor).lower()
        except Exception:  # pragma: no cover - a __str__ that raises
            text_form = ""
        if "statement timeout" in text_form or "querycancelederror" in text_form:
            return True
        # SQLAlchemy wraps the driver error; the driver error is the one that
        # knows it was cancelled.
        cursor = cursor.__cause__ or cursor.__context__
    return False
