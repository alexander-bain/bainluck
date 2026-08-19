"""Who produced a `discover_interactions` row — the runtime allowlist.

This is the gate between Alex's 250 gold labels and a model that learns his
taste instead of the warmer's. Without it every dwell/dismiss in
`discover_interactions` is an unfalsifiable mixture, and interestingness tuning
grades echo as preference.

WHY THIS CONSTANT EXISTS SEPARATELY FROM THE MIGRATIONS

A migration is a historical record of what was applied, so it may not change
meaning later because application code moved. That leaves the schema's copy of
the value list frozen, and it leaves it **split across two revisions**:

* ``add_disc_interactions_provenance.PROVENANCE_VALUES_AS_APPLIED`` — the six
  values that revision created, in enum-ordinal order;
* ``add_prov_play_enum_value.PLAY_VALUE`` — ``play``, appended as the seventh by
  the next revision, because the first one had already run in production and an
  Alembic revision runs once.

So there are lists in more than one place, and lists in more than one place
drift — which is the exact defect this whole change is fixing, one layer up. The
receiver accepted ``play`` while the enum could only store six values, so **the
ORM took a value the database would reject**, and it looked fine until it met a
real PostgreSQL enum.

They are bound by a test (``test_discover_provenance.py``) rather than by an
import. A test can fail; an import would only have hidden the split behind
whichever module loaded first. The binding is against the **chain** — the six
plus ``play``, in that order — not against any single migration file. Binding to
one file is what let the shipped enum diverge from both while an assertion about
it stayed green.

ABSENCE AND INVALIDITY BOTH MEAN ``unknown``, NEVER ``user``

That is the whole safety property. ``user`` is the slice that trains on Alex's
taste, so anything that defaults INTO it silently poisons the training set with
whatever produced it. A writer that did not stamp is not a user; a writer that
stamped something we do not recognise is not a user either. Both are
``unknown``, and ``unknown`` is excluded from the training slice by predicate,
not by hope.

``play`` IS ITS OWN VALUE and is never folded into ``user``, and never inferred
after receipt from ``source == "play"``. Training slices decide Play inclusion
explicitly per slice (``WHERE provenance = 'user'`` vs ``= 'play'``). Inferring
it later would re-create the mixture the column exists to end.
"""

from __future__ import annotations

#: The seven values, **in the ordinal order PostgreSQL actually declares them**:
#: the six from ``add_disc_int_provenance`` followed by ``play``, which
#: ``add_prov_play_value`` appends with ``ALTER TYPE … ADD VALUE`` and therefore
#: lands last. Verified against production's ``pg_enum`` on 2026-08-19.
#:
#: The order is load-bearing, not cosmetic: enum ordinals are what
#: ``ORDER BY provenance`` and every btree range scan on the column mean, so a
#: tuple written in a prettier order would describe a type neither database has.
#: A test asserts this equals
#: ``PROVENANCE_VALUES_AS_APPLIED + (PLAY_VALUE,)``.
PROVENANCE_VALUES: tuple[str, ...] = (
    "user",
    "warmer",
    "sentinel",
    "gold_session",
    "admin",
    "unknown",
    "play",
)

#: The allowlist, as a set, for the receiver's membership test.
PROVENANCE_ALLOWED: frozenset[str] = frozenset(PROVENANCE_VALUES)

#: What an unstamped or unrecognised writer becomes. Never ``user``.
PROVENANCE_FALLBACK = "unknown"

#: The header every real transport stamps at source. Trust the writer, not the
#: log: the surface a row arrives on is not evidence of who produced it, because
#: warmers and sentinels arrive on the same routes as people.
PROVENANCE_HEADER = "X-Discover-Provenance"


def normalize_provenance(raw: str | None) -> str:
    """The receiver's whole decision, as a pure function.

    ``None``, empty, whitespace, wrong case and unrecognised values all resolve
    to :data:`PROVENANCE_FALLBACK`. Case and surrounding whitespace are
    forgiving because a transport typo must not become a *silent* mislabel —
    but an unknown WORD is never guessed at.
    """
    candidate = (raw or "").strip().lower()
    return candidate if candidate in PROVENANCE_ALLOWED else PROVENANCE_FALLBACK
