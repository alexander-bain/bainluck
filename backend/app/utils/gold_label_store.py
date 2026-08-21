"""The ONE store a human label lands in, and the ONE path that writes it (#1933).

── WHAT WAS ACTUALLY SPLIT, MEASURED BEFORE IT WAS FIXED ────────────────────────

#1933 bullet 2 asked for the store to converge or for the split to be justified.
Counted on production 2026-08-20, the split was not a rounding error — it was
most of the corpus:

    ranking_judgments                        88 rows
    discover_review_decisions, label_pass   198 gradeable futures verdicts
      (88 accepted_downrank · 40 accepted_promote
       38 rejected_downrank · 32 rejected_promote)

Every gold-set consumer reads the first table and none reads the second:
``/coverage``, ``/eval-export``, ``labeling_queue`` (already-reviewed dedup),
``discover_label_eval_runs`` (the published ``tapworthy_at_k`` numbers),
``export_discover_labeled_dataset.py`` and ``replay_discover_ranking.py``. So
70% of Alex's labels were invisible to every number computed from "Alex's
labels", against a standing complaint that the corpus is too small to hold out
on (ruling 016). Which table a label landed in depended on which screen he
opened.

── WHY THE MERGE GOES ONE WAY, AND WHY THE OTHER TABLE SURVIVES ─────────────────

``discover_review_decisions`` is **not a label store**. 986 of its rows are
``llm_proposed_*`` — the proposal QUEUE the label pass reads — ``feed.py`` reads
it for the live eval-promote term, ``enrich_markets.py`` for the corrective
few-shot, and ``admin_engagement.py`` writes aggregate engagement decisions into
it. It is a decision/lifecycle table that happens to also hold verdicts.
``ranking_judgments`` is the gold-label store and has no second job.

So convergence is not "delete a table". The GOLD LABEL converges into
``ranking_judgments``; the label pass keeps writing its lifecycle row, because
that row is what undo, duplicate detection and the ranking term read. One label,
one store, two rows with different jobs — and the judgment row says which
decision it came from, so the two can always be re-joined.

── A REJECT IS NOT A LABEL, AND THE ROW SAYS SO ─────────────────────────────────

The label pass elicits ``accept``/``reject`` on an LLM's proposal; the gold set
speaks ``love``/``fine``/``bad``/``kill`` about a card. Those are different
questions and the map between them is lossy in exactly one direction:

* an **accept** affirms the proposal's direction, so the label follows it —
  the human asserted that this card deserves promoting, or deserves downranking.
* a **reject** only denies the direction. "Do not promote this" is not "this is
  bad", and "do not downrank this" is not "this is good"; both land the card in
  the middle, and ``fine`` is the weakest claim consistent with what was asked.

That inference is real and it is recorded rather than laundered:
``label_metadata.label_origin.mapping`` is ``affirmed`` or ``negated``, so a
consumer that wants only directly-elicited labels can filter for the first and
one that wants volume can take both. Writing ``fine`` and forgetting where it
came from would put an inference into the gold set wearing the same clothes as
an observation, and the corpus is far too small to absorb that.

A **skip** produces no label at all. It is the absence of an opinion, and the
verdict route already refuses to treat it as one.

── THE METADATA ENVELOPE LIVES HERE FOR THE REASON THE ISSUE NAMES ──────────────

``structured_label_metadata`` used to be private to ``admin_judgments``, with the
drift-gate manifest stamped ``surface="native_ranking_judgment"`` as a literal.
That is the same shape #1933 filed: a thing every surface needs, owned by the
first surface that needed it. It is here, the surface is an argument, and both
routes call it.
"""

from __future__ import annotations

from typing import Any

from app.models.models import RankingJudgment
from app.utils.reviewer_tier import TIER_ALEX, with_tier

#: The gold vocabulary. All four are in live use.
GOLD_LABELS = ("love", "fine", "bad", "kill")

#: ``discover_review_decisions.decision`` → (gold label, how it was obtained).
#:
#: ``accepted_downrank`` maps to ``bad`` rather than ``kill`` deliberately: a
#: downrank is a bounded −18 term, not a removal, and ``kill`` is the stronger
#: claim that nobody was asked to make.
VERDICT_GOLD_LABEL: dict[str, tuple[str, str]] = {
    "accepted_promote": ("love", "affirmed"),
    "accepted_downrank": ("bad", "affirmed"),
    "rejected_promote": ("fine", "negated"),
    "rejected_downrank": ("fine", "negated"),
}


def verdict_gold_label(decision: str | None) -> tuple[str, str] | None:
    """The gold label a label-pass decision carries, or ``None`` for no label.

    ``None`` is the honest answer for ``skipped`` and for every decision that is
    not a human verdict on a card (``llm_proposed_*``, the engagement-decision
    rows ``admin_engagement`` writes). A caller that turns ``None`` into a label
    is inventing one.
    """
    if not decision:
        return None
    return VERDICT_GOLD_LABEL.get(decision)


def normalize_card_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep a compact, stable copy of the card state the reviewer saw."""

    allowed_keys = [
        "batch_id",
        "feed_request_id",
        "rank",
        "item_type",
        "item_id",
        "market_id",
        "event_id",
        "name",
        "source",
        "category",
        "archetype",
        "quality_class",
        "headline",
        "reason",
        "context",
        "hook_description",
        "image_url",
        "story_key",
        "family_key",
        "group_id",
        "score",
        "rendered_probability",
        "top_outcomes",
        "reasons",
        "has_hook",
        "has_image",
        "explanation_ok",
        "stratum",
        "selection_reason",
    ]
    normalized: dict[str, Any] = {}
    for key in allowed_keys:
        value = snapshot.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        elif key in {"top_outcomes", "reasons"} and isinstance(value, list):
            normalized[key] = value[:5] if key == "top_outcomes" else value[:12]
        elif isinstance(value, dict):
            normalized[key] = value
    normalized["schema_version"] = snapshot.get("schema_version") or "discover-card-v1"
    return normalized


def structured_label_metadata(
    body: dict[str, Any],
    explicit_metadata: Any,
    *,
    gate: dict[str, Any] | None = None,
    live_card: dict[str, Any] | None = None,
    gate_surface: str = "native_ranking_judgment",
) -> dict[str, Any] | None:
    metadata = dict(explicit_metadata) if isinstance(explicit_metadata, dict) else {}
    card_snapshot = body.get("card_snapshot")
    if card_snapshot is None:
        card_snapshot = metadata.pop("card_snapshot", None)
    if isinstance(card_snapshot, dict):
        metadata["card_snapshot"] = normalize_card_snapshot(card_snapshot)

    # ── THE CARD FIELDS ARE DERIVED, THE CONTEXT FIELDS ARE ACCEPTED ─────────
    #
    # UX-P110's finding on the web side, applied here: the snapshot on a stored
    # judgment used to be whatever the phone posted, unvalidated, and it is read
    # back as the record of what Alex saw. So the fields the server can verify
    # are overwritten from the card this transaction actually re-derived, and the
    # ones only the client knows — which sampling batch, which feed request,
    # what rank it sat at — are kept as sent. Which half is which is written on
    # the row rather than left for a reader to guess.
    if live_card is not None:
        snapshot = dict(metadata.get("card_snapshot") or {})
        # Keep the posted copy beside the derived one when they differ, never
        # instead of it. Queue 355's `snapshot_at_write` reasoning: a fix that
        # silently swaps the stale value for the fresh one destroys the evidence
        # for its own necessity.
        posted_name = snapshot.get("name")
        if posted_name and posted_name != live_card.get("name"):
            snapshot["name_at_post"] = posted_name
        for key in ("name", "top_outcomes", "rendered_probability"):
            value = live_card.get(key)
            if value is not None:
                snapshot[key] = value
        snapshot["field_coherent"] = live_card.get("field_coherent")
        snapshot["resolution_date"] = live_card.get("resolution_date")
        snapshot["card_fields_source"] = "server_derived"
        metadata["card_snapshot"] = snapshot

    if gate is not None:
        # Never absent, never implied. A store that cannot say which of its rows
        # were gated cannot report its own coverage, and "no drift_gate key"
        # would read as "fine" to every future reader (ruling 086).
        #
        # ** THE SURFACE IS AN ARGUMENT. ** It was a literal here while this
        # function lived inside the native route, which is how a shared envelope
        # would have gone on describing every row as native's.
        metadata["drift_gate"] = {
            "bound": gate["status"] == "bound",
            "reason": gate.get("reason"),
            "fingerprint": gate.get("fingerprint") or gate.get("expected"),
            "surface": gate_surface,
        }

    fixable_keys = [
        "would_be_interesting_if",
        "fixable_interest_score",
        "fix_type",
        "desired_entity_or_variant",
        "current_entity_or_variant",
        "create_issue_candidate",
    ]
    top_level_fixable = {
        key: metadata.pop(key)
        for key in list(metadata.keys())
        if key in fixable_keys and metadata[key] not in (None, "")
    }
    fixable = {
        key: body[key]
        for key in fixable_keys
        if key in body and body[key] not in (None, "")
    }
    if top_level_fixable:
        fixable = {**top_level_fixable, **fixable}
    if fixable:
        existing = metadata.get("fixable_interest")
        if isinstance(existing, dict):
            fixable = {**existing, **fixable}
        metadata["fixable_interest"] = fixable
    return metadata or None


#: The JSONB path that makes a converged row traceable to the decision it came
#: from — and makes the convergence idempotent, because a backfill can ask which
#: source decisions are already represented instead of guessing from timestamps.
ORIGIN_KEY = "label_origin"


def label_origin(
    *,
    surface: str,
    source_store: str | None = None,
    source_decision_id: int | None = None,
    source_decision: str | None = None,
    source_verdict: str | None = None,
    mapping: str = "direct",
    reconstructed: bool = False,
) -> dict[str, Any]:
    """Where this label came from and how faithfully.

    ``mapping`` is ``direct`` when the human picked the gold label itself (the
    native and web-discover surfaces do), ``affirmed`` when a verdict agreed with
    a proposal's direction, ``negated`` when it only denied one. The distinction
    is the whole reason the label pass can be merged into this store at all
    without laundering an inference as an observation.
    """
    origin: dict[str, Any] = {"surface": surface, "mapping": mapping}
    if source_store:
        origin["source_store"] = source_store
    if source_decision_id is not None:
        origin["source_decision_id"] = source_decision_id
    if source_decision:
        origin["source_decision"] = source_decision
    if source_verdict:
        origin["source_verdict"] = source_verdict
    if reconstructed:
        # The card was rebuilt from the decision row rather than re-derived from
        # live state, because the live state is months gone. Stated on the row:
        # a reader must be able to tell a reconstructed snapshot from a verified
        # one without knowing which queue wrote it.
        origin["reconstructed"] = True
    return origin


def gold_label_row(
    *,
    label: str,
    surface: str,
    reviewer: str,
    metadata: dict[str, Any] | None,
    origin: dict[str, Any] | None = None,
    tier: str = TIER_ALEX,
    item_type: str = "futures",
    market_id: int | None = None,
    event_id: int | None = None,
    market_name: str | None = None,
    rank_seen: int | None = None,
    reason_tags: list[str] | None = None,
    better_than: str | None = None,
    worse_than: str | None = None,
    notes: str | None = None,
    score_at_review: float | None = None,
    category_at_review: str | None = None,
    archetype_at_review: str | None = None,
    quality_class_at_review: str | None = None,
    headline_at_review: str | None = None,
    feed_request_id: str | None = None,
    fixable_interesting: bool = False,
    repair_type: str | None = None,
    repair_target_entity: str | None = None,
    repair_note: str | None = None,
    created_at: Any = None,
) -> RankingJudgment:
    """Build the one row a human label is stored as. Every surface calls this.

    Not a convenience wrapper. The point is that there is exactly one place in
    the codebase where a ``RankingJudgment`` comes into existence, so the next
    surface cannot acquire a store of its own by writing a constructor of its
    own — which is precisely how the split this closes was created.

    ``created_at`` is accepted so a converged historical label keeps the date it
    was actually given. A backfill that stamps 198 June verdicts with today's
    timestamp does not merely lose provenance: it moves them all inside every
    trailing-window measurement, including the one that decides whether the
    drift gate may be tightened.

    Every write carries a tier (Queue 311 B1 / #1170). The default is the
    curator's; the kid surface passes its own.
    """
    envelope = with_tier(dict(metadata or {}), tier)
    if origin:
        envelope[ORIGIN_KEY] = origin

    row = RankingJudgment(
        surface=surface,
        rank_seen=rank_seen,
        item_type=item_type,
        market_id=market_id,
        event_id=event_id,
        market_name=market_name,
        label=label,
        reason_tags=reason_tags if reason_tags is not None else [],
        better_than=better_than,
        worse_than=worse_than,
        notes=notes,
        score_at_review=score_at_review,
        category_at_review=category_at_review,
        archetype_at_review=archetype_at_review,
        quality_class_at_review=quality_class_at_review,
        headline_at_review=headline_at_review,
        feed_request_id=feed_request_id,
        label_metadata=envelope or None,
        fixable_interesting=fixable_interesting,
        repair_type=repair_type,
        repair_target_entity=repair_target_entity,
        repair_note=repair_note,
        reviewer=reviewer,
    )
    if created_at is not None:
        row.created_at = created_at
        # ``date`` has a ``current_date`` server default, which would otherwise
        # disagree with ``created_at`` on every converged row.
        row.date = created_at.date() if hasattr(created_at, "date") else created_at
    return row
