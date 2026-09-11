"""The additive eligibility record carried by one published probability reading.

CU-4 (#5311). `Event.win_probability_sources` is the column every hero, card and
Discover row re-aggregates, and `compute_aggregate_probability` re-weights it AT
READ TIME on every request. That is the fact this module exists for:

    The admission gate is a WRITER-side function. `admissible_as_blend_speaker`
    (#5031) is called from exactly two places, both inside `live_blend.py`. Once
    a reading has been stamped into the JSONB, every serve-time reader will
    faithfully re-weight that number for as long as the key sits there — the
    gate that would have refused it ran, and passed, weeks earlier, on a
    different row.

So an entry written by a gated writer and an entry written by an ungated one are
INDISTINGUISHABLE after the fact. Not "hard to tell apart" — indistinguishable:
the stored shape is `{"value": 0.62, "updated_at": "..."}` and it names neither
the market the number came from nor the rule that let it speak. #5031's own
specimen (event 15301219 holding 0.070 off an Exact Score `2 - 2` leg) is not
detectable from the column at all; it was found by re-deriving the reading from
the markets. That is what makes "zero ineligible probability inputs in the
served payload" unanswerable today, and it is Alex's *"stale JSONB cannot bypass
it"* clause on #5273.

THE EVIDENCE ALREADY EXISTS AT THE WRITE MOMENT AND IS DISCARDED. `BlendReading`
carries `market` and `outcome` — the row that spoke — and
`_phase2_persist_group_reading` writes them into the SNAPSHOT's `game_state`
("why did the blend say that has to name the one that said it") while stamping
only value+time onto the reading itself. The snapshot is a different table, it
is written only when `write_snapshot=True`, and no serve-time reader joins it:
`compute_aggregate_probability` takes an event and does no query. So the audit
trail exists beside the number and not on it.

This module is the record that closes that gap, and NOTHING ELSE. In particular:

  * **It does not classify.** It has no opinion about whether a market is a game
    winner. `game_market_class` is the one shared recognizer and a second copy
    of it is the #1951 drift failure — "the second copy does not throw when it
    disagrees, it just quietly answers differently". The record is MINTED by the
    existing gate (`live_blend`) and only READ here and in `aggregation`.
  * **It is additive.** A reading with no record computes bit-for-bit what it
    computes today. The population is entirely record-free until the writers
    deploy and re-poll, so a gate that refused the unrecorded would blank every
    hero on the site; that repair is CU-1R's, attended, with a backup and an
    undo. Here, absence is `UNVERIFIED` — reported, never refused.

Pure, and imports nothing from the app, for the `sport_keys.py` reason: both
`live_blend` (the minter) and `aggregation` (the reader) depend on it, and
neither may end up importing the other through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


# Bumped when the MEANING of a stored record changes, so a reader can tell a
# record it understands from one written by a newer writer. Additive fields do
# not bump it; a changed interpretation of an existing field does.
ELIGIBILITY_RECORD_VERSION = 1

# The key the record lives under, inside the source's own entry. A sibling of
# `value` and `updated_at`, never a replacement for either — `stamp_source_reading`
# merges into the entry precisely so a writer that ADDS a field is not a writer
# that deletes the fields it does not recognise.
ELIGIBILITY_KEY = "eligibility"

# ── The three grades ─────────────────────────────────────────────────────────
#
# VERIFIED and INELIGIBLE are both POSITIVE assertions by a named rule: it looked
# at this reading's originating market and said yes, or said no. UNVERIFIED is
# the absence of an assertion, which is a different thing from a negative one and
# must never be collapsed into it (T15 §"positive proof, with abstention", and
# the doctrine behind gotcha #53: an empty answer is a response shape, not a fact).
VERIFIED = "verified"
UNVERIFIED = "unverified"
INELIGIBLE = "ineligible"

# A fourth grade, and it is a grade about the QUESTION rather than the reading.
# Reported separately so a census is not a wall of false positives: see
# `MARKET_DERIVED_SOURCES`.
NOT_APPLICABLE = "not_applicable"

# The scope a reading must have to sit in the winner slot. Named, rather than
# implied, because "winner" alone is insufficient — T15 admission rule 4: "a bare
# 'winner' token is insufficient: set winner and tournament winner are winners of
# different things", and `kxatpsetwinner` carrying the same two player names as
# `kxatpmatch` is the case that already bit the devig.
SCOPE_FULL_EVENT_WINNER = "full_event_winner"

# ── Which sources the record is a question FOR ───────────────────────────────
#
# The #5031 defect class needs a source that publishes MANY child questions per
# event and leaves us to pick one: Polymarket decomposes a game into a dozen rows
# sharing the match-winner's exact two-outcome shape and its "A vs. B" title, and
# Kalshi mints a per-team pair beside its spreads, totals and props. Choosing
# wrong there is how an Exact Score price becomes a match winner.
#
# `betting`, `espn`, `stat_model`, `mlb` and `final_result` do not select among
# sibling questions at all — each is a model, a purpose-built consensus over one
# market key (Odds API `h2h`), or the resolved score. There is no wrong sibling
# to pick, so the ABSENCE of an eligibility record on them is expected and is not
# a finding. Grading them `UNVERIFIED` would bury the two sources that matter
# under five that never had the defect.
#
# This is deliberately NOT "every source with a gate": it is every source whose
# reading is minted by choosing one market from several. Adding a source here
# asserts that its writer can pick the wrong question.
MARKET_DERIVED_SOURCES = frozenset({"kalshi", "polymarket"})


@dataclass(frozen=True)
class EligibilityRecord:
    """What a named rule asserted about the reading it admitted.

    ``rule`` is the admission function that spoke, qualified by the issue that
    defines its behaviour, so a stored record stays legible after the function is
    edited. ``market_id`` and ``source_market_id`` are the evidence pointer — our
    row and the venue's own id for it — and they are what make an
    already-written entry gradeable after the fact rather than only re-derivable.

    ``semantic_type`` is reserved and left ``None`` by every writer today: CU-1
    (#5273) is open, so `semantic_market_type` / `market_metadata.
    content_understanding_v1` do not exist yet. It is declared here so that
    landing CU-1 is an additive write into a field readers already tolerate,
    rather than a second record shape competing with this one.
    """

    status: str
    scope: Optional[str] = None
    rule: Optional[str] = None
    market_id: Optional[int] = None
    source_market_id: Optional[str] = None
    semantic_type: Optional[str] = None
    version: int = ELIGIBILITY_RECORD_VERSION

    def to_entry(self) -> dict:
        """The JSONB form: only the fields that carry information.

        Nulls are dropped rather than stored. This column is read on every
        request for every event on a page, and a record is written per source
        per poll; a fixed six-key dict of mostly-``None`` would grow the row for
        nothing. A reader must therefore treat a missing key as ``None``, which
        `from_entry` does.
        """
        record: dict[str, Any] = {"v": self.version, "status": self.status}
        if self.scope is not None:
            record["scope"] = self.scope
        if self.rule is not None:
            record["rule"] = self.rule
        if self.market_id is not None:
            record["market_id"] = self.market_id
        if self.source_market_id is not None:
            record["source_market_id"] = self.source_market_id
        if self.semantic_type is not None:
            record["semantic_type"] = self.semantic_type
        return record


def verified_record(
    *,
    rule: str,
    market_id: Optional[int] = None,
    source_market_id: Optional[str] = None,
    scope: str = SCOPE_FULL_EVENT_WINNER,
) -> EligibilityRecord:
    """The record a gate mints when it has ADMITTED a reading.

    Callers pass the market that actually spoke — `BlendReading.market`, never
    the group's primary. Those are not always the same row, and naming the wrong
    one is worse than naming none: it would make an unsubstantiated reading look
    substantiated by a market that did not produce it. That distinction is
    CERT-767's lesson and `_phase2_persist_group_reading` already honours it for
    the snapshot's `game_state`.
    """
    return EligibilityRecord(
        status=VERIFIED,
        scope=scope,
        rule=rule,
        market_id=market_id,
        source_market_id=source_market_id,
    )


def ineligible_record(
    *,
    rule: str,
    reason: Optional[str] = None,
    market_id: Optional[int] = None,
) -> EligibilityRecord:
    """The record for a reading a named rule REFUSES.

    Reachable only for a value that must stay in the column while being refused
    by the blend — the CU-1R (#5310) repair's case, where a contaminated leg is
    marked rather than deleted so the correction is reviewable and history is not
    rewritten. A writer that simply declines to write does not need this: it
    writes nothing, and the retirement path (`_retire_unbacked_blend_source`)
    removes the key.

    ``reason`` rides in the ``rule`` string rather than as a field of its own,
    because the reader's only decision is refuse-or-not and a free-text field
    that no reader branches on is a field that drifts.
    """
    return EligibilityRecord(
        status=INELIGIBLE,
        rule=f"{rule}:{reason}" if reason else rule,
        market_id=market_id,
    )


def from_entry(raw: Any) -> Optional[EligibilityRecord]:
    """Read a record out of one `win_probability_sources` entry, or ``None``.

    ``None`` means "this reading carries no assertion" and covers every way that
    can happen: the legacy bare-float shape, a dict written before this record
    existed, a malformed record, a record from a FUTURE version this reader
    cannot interpret.

    NEVER RAISES, and that is load-bearing rather than defensive habit. This runs
    inside `_tier1_readings`, on the request path, over a column that provably
    holds several shapes at once (`parse_source_entry`'s docstring). A record
    that cannot be read must degrade to "no assertion" — the monotone default,
    exactly as an unparseable `updated_at` degrades to full weight — because the
    alternative is a malformed JSONB key taking down a page.

    A future-version record reads as no assertion rather than as VERIFIED: this
    reader cannot substantiate what it cannot interpret, and a rolling deploy
    puts an old reader in front of a new writer routinely.
    """
    if not isinstance(raw, dict):
        return None
    record = raw.get(ELIGIBILITY_KEY)
    if not isinstance(record, dict):
        return None

    version = record.get("v")
    if not isinstance(version, int) or isinstance(version, bool):
        return None
    if version > ELIGIBILITY_RECORD_VERSION:
        return None

    status = record.get("status")
    if status not in (VERIFIED, UNVERIFIED, INELIGIBLE):
        return None

    def _text(key: str) -> Optional[str]:
        value = record.get(key)
        return value if isinstance(value, str) and value else None

    market_id = record.get("market_id")
    if isinstance(market_id, bool) or not isinstance(market_id, int):
        market_id = None

    return EligibilityRecord(
        status=status,
        scope=_text("scope"),
        rule=_text("rule"),
        market_id=market_id,
        source_market_id=_text("source_market_id"),
        semantic_type=_text("semantic_type"),
        version=version,
    )


def is_refused(raw: Any) -> bool:
    """Whether this entry carries a POSITIVE refusal and must not reach the blend.

    The whole read-side gate, in one predicate, and it is deliberately the
    narrowest one that is honest today. It answers "did a rule look at this and
    say no", not "can this be substantiated" — because on the current population
    nothing can be substantiated (no writer has stamped a record yet), so the
    wider question refuses every reading on the site.

    The wider gate is a REPAIR, not a flag flip: CU-1R runs the bounded admin
    pattern (dry-run census by exact ids, backup, attended apply, one-command
    undo) and only then can `UNVERIFIED` mean anything but "we have not asked".
    Tightening this predicate before that lands would take the site dark to fix
    a defect measured at ~10 events.
    """
    record = from_entry(raw)
    return record is not None and record.status == INELIGIBLE


def grade_entry(source: str, raw: Any) -> str:
    """The census grade for ONE source's entry: the four constants above.

    `NOT_APPLICABLE` for a source that does not choose among sibling questions
    (see `MARKET_DERIVED_SOURCES`) and carries no record — its reading cannot be
    the #5031 defect. A record present on such a source is still graded on its
    merits, because a writer that took the trouble to assert something is
    entitled to be read.

    This is the function a served-payload census counts, so it must return a
    grade for every entry rather than only for the interesting ones: a
    denominator built by skipping rows is how a recut "improves" by shrinking
    (T15 §5, and #5251's lesson).
    """
    record = from_entry(raw)
    if record is not None:
        return record.status
    return UNVERIFIED if source in MARKET_DERIVED_SOURCES else NOT_APPLICABLE


def grade_sources(sources: Optional[dict]) -> dict[str, str]:
    """`{source: grade}` over a whole `win_probability_sources` column.

    Every key present is graded, including keys with no usable value and keys
    that are not blend sources at all — this is the census's raw material and
    the decision about what counts belongs to the census, not to the grader.
    """
    if not isinstance(sources, dict):
        return {}
    return {str(source): grade_entry(str(source), raw) for source, raw in sources.items()}
