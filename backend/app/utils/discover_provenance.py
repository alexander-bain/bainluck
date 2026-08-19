"""Who produced a `discover_interactions` row — the runtime allowlist.

This is the gate between Alex's 250 gold labels and a model that learns his
taste instead of the warmer's. Without it every dwell/dismiss in
`discover_interactions` is an unfalsifiable mixture, and interestingness tuning
grades echo as preference.

WHY THIS CONSTANT EXISTS SEPARATELY FROM THE MIGRATION

`add_disc_interactions_provenance.py` carries its own frozen copy of the seven
values, and it must: a migration is a historical record of what was applied, so
it may not change meaning later because application code moved. That leaves two
lists, and two lists drift — which is the exact defect this whole change is
fixing, one layer up. The receiver accepted ``play`` while the enum could only
store six values, so **the ORM took a value the database would reject**, and it
looked fine until it met a real PostgreSQL enum.

So the two lists are bound by a test (``test_discover_provenance.py``) rather
than by an import. A test can fail; an import would only have hidden the split
behind whichever module loaded first.

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

#: The seven values, in the order the enum declares them. MUST equal
#: ``add_disc_interactions_provenance.PROVENANCE_VALUES``; a test asserts it.
PROVENANCE_VALUES: tuple[str, ...] = (
    "user",
    "play",
    "warmer",
    "sentinel",
    "gold_session",
    "admin",
    "unknown",
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
