"""#1933 bullet 2 — one store, one write path, and the flip criterion.

``test_graded_card_contract.py`` proves the gate decision in isolation and
``test_admin_judgments_drift_gate.py`` / ``test_admin_label_pass_drift.py`` prove
each route wired to it. This proves the CONVERGENCE: that a label-pass verdict
now lands in the gold store, that the inference it rests on is recorded rather
than laundered, that the historical backfill cannot double-write or backdate
wrongly, and that the fail-closed flip criterion cannot be passed by silence.

The two properties worth stating outright, because both were live defects:

* a ``reject`` is not a label. It denies a proposal's direction and says nothing
  positive about the card, so its ``fine`` is marked ``negated`` and a consumer
  can drop it.
* "zero unbound" over a quiet window is not evidence. This table has already gone
  77 days without a write.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.gold_label_store import (
    GOLD_LABELS,
    ORIGIN_KEY,
    VERDICT_GOLD_LABEL,
    gold_label_row,
    label_origin,
    structured_label_metadata,
    verdict_gold_label,
)
from app.utils.graded_card import (
    FLIP_MIN_BOUND,
    FLIP_MIN_DAYS,
    FLIP_WINDOW_DAYS,
    flip_readiness,
)
from app.utils.reviewer_tier import TIER_ALEX, TIER_KID, tier_of


# ── THE MAP FROM A VERDICT TO A LABEL ────────────────────────────────────────


@pytest.mark.parametrize(
    "decision,label,mapping",
    [
        ("accepted_promote", "love", "affirmed"),
        ("accepted_downrank", "bad", "affirmed"),
        ("rejected_promote", "fine", "negated"),
        ("rejected_downrank", "fine", "negated"),
    ],
)
def test_verdict_maps_to_the_stated_label(decision, label, mapping):
    assert verdict_gold_label(decision) == (label, mapping)
    assert label in GOLD_LABELS


@pytest.mark.parametrize(
    "decision",
    ["skipped", "llm_proposed_promote", "llm_proposed_downrank", "needs_data_fix",
     "ignored", "", None],
)
def test_a_non_verdict_produces_no_label(decision):
    """A skip is the absence of an opinion and a proposal is not a human's.

    The failure this forbids is a caller that treats ``None`` as "pick a
    default": every one of these would arrive in the gold set as an opinion
    nobody gave.
    """
    assert verdict_gold_label(decision) is None


def test_a_reject_never_maps_to_a_strong_label():
    """``reject`` only denies a direction — it cannot assert love or kill.

    Guarding the reasoning, not the table: someone reading "rejected_downrank"
    as "he liked it" and mapping it to ``love`` is the plausible edit, and it
    would push inferred positives into a corpus with a single-digit positive
    count.
    """
    for decision, (label, mapping) in VERDICT_GOLD_LABEL.items():
        if decision.startswith("rejected_"):
            assert mapping == "negated"
            assert label == "fine", (
                f"{decision} claims {label}; a reject supports only the "
                "weakest middle label"
            )


def test_affirmed_and_negated_are_distinguishable_on_the_row():
    """The inference is recorded, so a consumer can refuse to consume it."""
    row = gold_label_row(
        label="fine",
        surface="label_pass",
        reviewer="alex",
        metadata=None,
        origin=label_origin(
            surface="label_pass",
            source_store="discover_review_decisions",
            source_decision_id=41,
            source_decision="rejected_downrank",
            source_verdict="reject",
            mapping="negated",
        ),
    )
    origin = row.label_metadata[ORIGIN_KEY]
    assert origin["mapping"] == "negated"
    assert origin["source_decision_id"] == 41
    assert origin["source_verdict"] == "reject"
    # ...and a directly-elicited label is not mistakable for it.
    direct = gold_label_row(
        label="love",
        surface="native_discover",
        reviewer="alex",
        metadata=None,
        origin=label_origin(surface="native_discover", mapping="direct"),
    )
    assert direct.label_metadata[ORIGIN_KEY]["mapping"] == "direct"


# ── THE SHARED ROW CONSTRUCTOR ───────────────────────────────────────────────


def test_there_is_exactly_one_place_a_gold_label_is_constructed():
    """The structural guard, and the only one that closes the CLASS.

    #1933's own words: "a fix that lives inside one route handler is a fix that
    the next surface will also miss." Converging two stores by hand fixes the
    two surfaces that exist today; it does nothing about the third, which will
    acquire a store of its own the moment someone writes
    ``RankingJudgment(...)`` in a new route — exactly as ``admin_judgments``
    once did, in good faith, with no test to say otherwise.

    So: outside the store module and the model definition, that constructor may
    not appear. A new surface has to come through ``gold_label_row``, which is
    where the tier, the origin and the gate stamp are applied.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    allowed = {
        root / "app" / "utils" / "gold_label_store.py",  # the one write path
        root / "app" / "models" / "models.py",  # the class definition itself
    }

    scanned = list((root / "app").rglob("*.py")) + list(
        (root / "scripts").rglob("*.py")
    )

    # THE DETECTOR MANIFEST (UX-P111 item 4's carry). A sweep that reports
    # "found nothing" is indistinguishable from a sweep that never ran, so this
    # one states the population it examined and proves it can see a positive:
    # both allowed files must be inside the scan, and the model file must
    # actually contain the string being hunted. Without this, a typo'd glob
    # would make the guard pass forever.
    assert len(scanned) > 200, f"the scan found only {len(scanned)} files"
    for path in allowed:
        assert path in scanned, f"{path} is not even in the scanned population"
    assert "RankingJudgment(" in (root / "app" / "models" / "models.py").read_text(
        encoding="utf-8"
    ), "the detector cannot see the one occurrence it is known to be excluding"

    offenders = []
    for path in scanned:
        if path in allowed:
            continue
        if "RankingJudgment(" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(root)))

    assert offenders == [], (
        "a gold label is being constructed outside the one write path: "
        f"{offenders}. Route it through `gold_label_store.gold_label_row` — "
        "the split this test exists to prevent started exactly here."
    )


def test_every_row_carries_a_tier():
    row = gold_label_row(label="bad", surface="label_pass", reviewer="alex", metadata=None)
    assert tier_of(row) == TIER_ALEX
    kid = gold_label_row(
        label="bad", surface="play", reviewer="kid", metadata=None, tier=TIER_KID
    )
    assert tier_of(kid) == TIER_KID


def test_converged_rows_keep_their_original_date():
    """A backfill that stamps today's date moves history inside every window.

    Specifically the 14-day window the flip criterion is measured over: 198
    backdated June verdicts landing today would flood it with rows that were
    never gated.
    """
    when = datetime(2026, 6, 11, 18, 30, tzinfo=timezone.utc)
    row = gold_label_row(
        label="bad",
        surface="label_pass",
        reviewer="alex",
        metadata=None,
        created_at=when,
    )
    assert row.created_at == when
    assert row.date == when.date(), "the date column must not disagree with created_at"


def test_a_row_without_an_explicit_date_defers_to_the_server():
    """The live path must NOT pin a timestamp — the DB default is the truth."""
    row = gold_label_row(label="love", surface="native_discover", reviewer="alex", metadata=None)
    assert getattr(row, "created_at", None) is None


# ── THE METADATA ENVELOPE IS SHARED, AND THE SURFACE IS AN ARGUMENT ──────────


def test_the_gate_stamp_names_the_surface_that_wrote_it():
    """It was a hardcoded literal while this lived inside the native route.

    A shared envelope that still says "native_ranking_judgment" for a label-pass
    row is worse than an unshared one: the coverage manifest would attribute
    every converged row to the wrong surface.
    """
    native = structured_label_metadata(
        {}, None, gate={"status": "bound", "fingerprint": "abc"},
    )
    assert native["drift_gate"]["surface"] == "native_ranking_judgment"

    web = structured_label_metadata(
        {}, None,
        gate={"status": "bound", "fingerprint": "abc"},
        gate_surface="label_pass_verdict",
    )
    assert web["drift_gate"]["surface"] == "label_pass_verdict"
    assert web["drift_gate"]["bound"] is True


def test_server_derived_card_fields_are_marked_as_such():
    metadata = structured_label_metadata(
        {"card_snapshot": {"name": "what the client posted"}},
        None,
        gate={"status": "bound", "fingerprint": "abc"},
        live_card={"name": "what the server derived", "field_coherent": True},
    )
    snapshot = metadata["card_snapshot"]
    assert snapshot["name"] == "what the server derived"
    # The posted spelling survives beside it, never instead of it.
    assert snapshot["name_at_post"] == "what the client posted"
    assert snapshot["card_fields_source"] == "server_derived"


# ── THE FLIP CRITERION ───────────────────────────────────────────────────────


def test_a_silent_window_is_not_ready_to_flip():
    """THE load-bearing leg. Zero unbound over zero traffic proves nothing.

    Named failure this encodes: `ranking_judgments` went 2026-05-25 → 2026-08-10
    without a single write. A criterion with only the zero-leg would have read
    READY for eleven consecutive weeks on no evidence at all.
    """
    verdict = flip_readiness(bound=0, unbound=0, distinct_days=0)
    assert verdict["ready"] is False
    assert "window_had_traffic" in verdict["blocked_on"]
    assert "traffic_spanned_sessions" in verdict["blocked_on"]
    # ...and the zero-leg on its own PASSES, which is exactly why it is not enough.
    assert verdict["legs"][0]["pass"] is True


def test_one_long_session_cannot_retire_a_build():
    """An old binary is retired by not being launched; one day is one launch."""
    verdict = flip_readiness(bound=500, unbound=0, distinct_days=1)
    assert verdict["ready"] is False
    assert verdict["blocked_on"] == ["traffic_spanned_sessions"]


def test_any_unbound_write_blocks_the_flip():
    verdict = flip_readiness(bound=200, unbound=1, distinct_days=9)
    assert verdict["ready"] is False
    assert verdict["blocked_on"] == ["no_unbound_writes"]


def test_all_three_legs_together_are_ready():
    verdict = flip_readiness(
        bound=FLIP_MIN_BOUND, unbound=0, distinct_days=FLIP_MIN_DAYS
    )
    assert verdict["ready"] is True
    assert verdict["blocked_on"] == []
    assert verdict["window_days"] == FLIP_WINDOW_DAYS


def test_the_window_is_longer_than_the_measured_labelling_gap():
    """N is derived from cadence, not chosen.

    Measured 2026-08-20: distinct labelling days 08-10 → 08-14 → 08-17 → 08-20,
    gaps of 4/3/3 days. The window has to span several of those or a clean
    result is one session, not a trend.
    """
    longest_recent_gap = 4
    assert FLIP_WINDOW_DAYS >= 3 * longest_recent_gap


def test_every_failing_leg_says_which_one():
    """A criterion that answers only "no" tells nobody what to go fix."""
    verdict = flip_readiness(bound=1, unbound=3, distinct_days=1)
    assert set(verdict["blocked_on"]) == {
        "no_unbound_writes",
        "window_had_traffic",
        "traffic_spanned_sessions",
    }
    for leg in verdict["legs"]:
        assert leg["why"], f"{leg['leg']} has no stated reason"
        assert leg["observed"] is not None


# ── THE ROUTE: A VERDICT LANDS IN BOTH STORES, IN ONE TRANSACTION ────────────
#
# This is #1933's acceptance criterion itself — "a label recorded on native
# appears in the same store and the same coverage count as one recorded on web".
# Everything above proves the parts; this proves the wire.

from types import SimpleNamespace  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.models.models import DiscoverReviewDecision, RankingJudgment  # noqa: E402
from app.routes import admin_label_pass  # noqa: E402

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=30)


def _proposal(decision="llm_proposed_promote"):
    return SimpleNamespace(
        id=7,
        item_type="futures",
        item_id="109081",
        item_name="Michigan Senate winner? (as the evaluator saw it)",
        category="politics",
        archetype="civic",
        decision=decision,
        features={"generation": "g1", "evidence_generation": "g1"},
        created_at=NOW,
    )


def _market():
    return SimpleNamespace(
        id=109081,
        name="Michigan Senate winner?",
        status="open",
        resolution_date=FUTURE,
        volume_24h=4200,
        llm_sport_category="politics",
        market_tier=2,
    )


def _outcomes():
    return [
        SimpleNamespace(id=1, market_id=109081, name="Democrat", current_probability=0.565),
        SimpleNamespace(id=2, market_id=109081, name="Republican", current_probability=0.435),
    ]


class _VerdictSession:
    """Answers the verdict path's reads in order and records every write."""

    def __init__(self, proposal, market, duplicate=False):
        self._results = [
            SimpleNamespace(scalar_one_or_none=lambda: proposal),
            SimpleNamespace(scalar_one_or_none=lambda: market),
            SimpleNamespace(first=lambda: (1,) if duplicate else None),
        ]
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    async def execute(self, statement):
        return self._results.pop(0)

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        self.flushes += 1
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = 900 + self.added.index(row)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def verdict_client(monkeypatch):
    monkeypatch.setattr(
        admin_label_pass, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    async def _no_kill_switch():
        return False

    monkeypatch.setattr(admin_label_pass, "_eval_promote_enabled", _no_kill_switch)

    async def _outcomes_for(db, ids):
        return {109081: _outcomes()}

    monkeypatch.setattr(admin_label_pass, "_load_outcomes", _outcomes_for)

    def _build(session):
        app = FastAPI()
        app.include_router(admin_label_pass.router)

        async def _override():
            return session

        app.dependency_overrides[admin_label_pass.get_db] = _override
        app.dependency_overrides[admin_label_pass.get_db_rw] = _override
        return TestClient(app)

    return _build


def _served_fingerprint(proposal, market):
    return admin_label_pass._live_features(proposal, market, _outcomes())["card_fingerprint"]


def _post_verdict(verdict_client, session, proposal, market, verdict="accept"):
    return verdict_client(session).post(
        "/label-pass/verdict?secret=ok",
        json={
            "decision_id": proposal.id,
            "verdict": verdict,
            "features": {"card_fingerprint": _served_fingerprint(proposal, market)},
        },
    )


def _rows(session, model):
    return [r for r in session.added if isinstance(r, model)]


def test_an_accept_writes_the_lifecycle_row_AND_the_gold_label(verdict_client):
    """The convergence, end to end.

    Before this, the label pass wrote only the left-hand row and every gold-set
    consumer reads the right-hand one — which is how 198 of Alex's verdicts
    became invisible to every number computed from "Alex's labels".
    """
    proposal, market = _proposal(), _market()
    session = _VerdictSession(proposal, market)

    response = _post_verdict(verdict_client, session, proposal, market)

    assert response.status_code == 200, response.json()
    assert response.json()["gold_label"] == "love"
    assert session.commits == 1

    assert len(_rows(session, DiscoverReviewDecision)) == 1
    gold = _rows(session, RankingJudgment)
    assert len(gold) == 1, "the verdict did not reach the gold store"
    assert gold[0].label == "love"
    assert gold[0].surface == "label_pass"
    assert gold[0].market_id == 109081


def test_the_gold_row_is_traceable_back_to_the_decision_that_made_it(verdict_client):
    """The join key, and the idempotency key for the historical convergence.

    It is stamped by the FORWARD path too, which is what stops the backfill
    double-writing verdicts recorded between the deploy and the repair.
    """
    proposal, market = _proposal(), _market()
    session = _VerdictSession(proposal, market)
    _post_verdict(verdict_client, session, proposal, market)

    lifecycle = _rows(session, DiscoverReviewDecision)[0]
    origin = _rows(session, RankingJudgment)[0].label_metadata[ORIGIN_KEY]
    assert origin["source_decision_id"] == lifecycle.id
    assert origin["source_store"] == "discover_review_decisions"
    assert origin["mapping"] == "affirmed"
    assert origin.get("reconstructed") is not True


def test_the_gold_row_records_the_card_the_server_verified(verdict_client):
    """Not the title the evaluator stamped at birth.

    `market_name` feeds cluster identity, so a stale copy forks one question
    into two clusters — the same correction UX-P110 made to `item_name` on the
    lifecycle row, which would have been pointless to make on one row and skip
    on the other.
    """
    proposal, market = _proposal(), _market()
    session = _VerdictSession(proposal, market)
    _post_verdict(verdict_client, session, proposal, market)

    gold = _rows(session, RankingJudgment)[0]
    assert gold.market_name == "Michigan Senate winner?"
    assert gold.market_name != proposal.item_name
    snapshot = gold.label_metadata["card_snapshot"]
    assert snapshot["card_fields_source"] == "server_derived"
    assert snapshot["rendered_probability"] == pytest.approx(0.565)


def test_the_gold_row_is_stamped_bound_by_the_same_gate(verdict_client):
    proposal, market = _proposal(), _market()
    session = _VerdictSession(proposal, market)
    _post_verdict(verdict_client, session, proposal, market)

    gate = _rows(session, RankingJudgment)[0].label_metadata["drift_gate"]
    assert gate["bound"] is True
    assert gate["surface"] == "label_pass_verdict"
    assert gate["fingerprint"] == _served_fingerprint(proposal, market)


def test_a_skip_writes_no_gold_label(verdict_client):
    """A skip is the absence of an opinion. It still retires the proposal."""
    proposal, market = _proposal(), _market()
    session = _VerdictSession(proposal, market)

    response = _post_verdict(verdict_client, session, proposal, market, verdict="skip")

    assert response.status_code == 200, response.json()
    assert response.json()["gold_label"] is None
    assert len(_rows(session, DiscoverReviewDecision)) == 1
    assert _rows(session, RankingJudgment) == []


def test_a_drifted_card_writes_to_NEITHER_store(verdict_client):
    """The refusal must not have grown a hole.

    Adding a second write to a gated path is exactly where a gate stops covering
    everything it used to: the 409 still fires, and a row lands anyway.
    """
    proposal, market = _proposal(), _market()
    session = _VerdictSession(proposal, market)

    response = verdict_client(session).post(
        "/label-pass/verdict?secret=ok",
        json={
            "decision_id": proposal.id,
            "verdict": "accept",
            "features": {"card_fingerprint": "a-digest-from-a-card-that-moved"},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "card_drifted"
    assert session.added == []
    assert session.commits == 0
    assert session.rollbacks == 1


def test_a_downrank_accept_is_bad_not_kill(verdict_client):
    """A downrank is a bounded term, not a removal; `kill` was never asked for."""
    proposal, market = _proposal(decision="llm_proposed_downrank"), _market()
    session = _VerdictSession(proposal, market)
    _post_verdict(verdict_client, session, proposal, market)
    assert _rows(session, RankingJudgment)[0].label == "bad"


def test_a_reject_lands_as_a_negated_fine(verdict_client):
    proposal, market = _proposal(decision="llm_proposed_downrank"), _market()
    session = _VerdictSession(proposal, market)
    _post_verdict(verdict_client, session, proposal, market, verdict="reject")

    gold = _rows(session, RankingJudgment)[0]
    assert gold.label == "fine"
    assert gold.label_metadata[ORIGIN_KEY]["mapping"] == "negated"
    assert gold.label_metadata[ORIGIN_KEY]["source_verdict"] == "reject"
