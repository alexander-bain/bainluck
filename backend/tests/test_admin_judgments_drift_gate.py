"""#1933 — the NATIVE judgment write path, gated against card drift.

``test_graded_card_contract.py`` proves the shared decision in isolation. This
proves the route wired to it: that the card is re-derived from LIVE rows inside
the write transaction rather than trusted from the request body, that a moved
card is refused with the same typed conflict the web pass raises, and that a
refusal writes NOTHING.

The fake session below is deliberate about one thing: it records every row it is
asked to add. A gate that "refuses" by returning a 409 after committing is a gate
that does not exist, and the only way to catch that is to look at what the
session was told to write.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin_judgments, admin_utils


def _outcome(name, probability, rank=1):
    return SimpleNamespace(
        id=rank,
        name=name,
        current_probability=probability,
        probability_change_24h=0.0,
        rank=rank,
    )


def _market(*pairs, name="Michigan Senate winner?", status="open", market_id=109081):
    return SimpleNamespace(
        id=market_id,
        name=name,
        status=status,
        description=None,
        llm_sport_category="politics",
        sport=None,
        source="kalshi",
        hook_description=None,
        image_url=None,
        group_id=None,
        resolution_date=datetime(2026, 11, 3, tzinfo=timezone.utc),
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        outcomes=[_outcome(n, p, i + 1) for i, (n, p) in enumerate(pairs)],
    )


FIELD = (("Democrat", 0.61), ("Republican", 0.39))


class _Session:
    """Answers the live re-read, and remembers whether anything was written."""

    def __init__(self, market=None):
        self.market = market
        self.added: list = []
        self.commits = 0

    async def execute(self, statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.market)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        row.id = 4242
        row.date = date(2026, 8, 20)
        row.created_at = datetime(2026, 8, 20, tzinfo=timezone.utc)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )
    # Queue 390: authorization resolves ONCE, in
    # `admin_utils._resolve_admin_principal`. `admin_judgments` no longer runs
    # its own copy of the token comparison, so patching only the module-local
    # name silently stops taking effect and every write here turns 403.
    monkeypatch.setattr(
        admin_utils, "_check_admin_secret", lambda secret, **kw: secret == "ok"
    )

    def _build(session):
        app = FastAPI()
        app.include_router(admin_judgments.router)

        async def _override():
            return session

        app.dependency_overrides[admin_judgments.get_db] = _override
        app.dependency_overrides[admin_judgments.get_db_rw] = _override
        return TestClient(app)

    return _build


def _post(client, session, **extra):
    body = {
        "secret": "ok",
        "label": "love",
        "item_type": "futures",
        "market_id": 109081,
        "market_name": "Michigan Senate winner?",
    }
    body.update(extra)
    return client(session).post("/admin/ranking-judgments", json=body)


def _served_fingerprint(market):
    return admin_judgments._native_card_fingerprint(market)


# ── the gate binds ───────────────────────────────────────────────────────────


def test_the_served_fingerprint_lets_the_judgment_through(client):
    """A guard that refuses everything is as useless as one that refuses nothing.
    The digest the sampler served, posted straight back, must be accepted."""
    market = _market(*FIELD)
    session = _Session(market)
    response = _post(
        client, session, card_fingerprint=_served_fingerprint(market)
    )
    assert response.status_code == 200
    assert response.json()["drift_gate"] == {"bound": True, "reason": None}
    assert len(session.added) == 1
    assert session.commits == 1


def test_a_reprice_between_sampling_and_grading_is_refused_and_writes_nothing(client):
    """The defect, end to end. The card is fingerprinted at sampling time, the
    field moves, and the label posted against the old picture never lands."""
    sampled = _market(*FIELD)
    stale_digest = _served_fingerprint(sampled)

    moved = _market(("Democrat", 0.42), ("Republican", 0.58))
    session = _Session(moved)

    response = _post(client, session, card_fingerprint=stale_digest)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["status"] == "conflict"
    assert detail["reason"] == "card_drifted"
    assert detail["writes"] == 0
    # The refusal carries the live card so the app can re-render it.
    assert detail["live_card"]["title"] == "Michigan Senate winner?"
    # ** The half a status code cannot prove. **
    assert session.added == []
    assert session.commits == 0


def test_a_move_too_small_to_see_does_not_refuse(client):
    """The load-bearing property, inherited from the web pass: the fingerprint is
    taken at the resolution the SCREEN prints, so a poll tick cannot 409 a
    labeling session. Native rounds with `renderedPercent`, the same rule."""
    sampled = _market(("Democrat", 0.6101), ("Republican", 0.3899))
    session = _Session(_market(("Democrat", 0.6104), ("Republican", 0.3896)))
    response = _post(
        client, session, card_fingerprint=_served_fingerprint(sampled)
    )
    assert response.status_code == 200, response.json()


def test_a_settled_market_is_refused_even_with_an_unmoved_field(client):
    """Native has no lifecycle gate of its own. Status is in the digest for
    exactly this: the picture did not move, but the card would not be served
    now, and a label against a settled question is not a taste judgment."""
    sampled = _market(*FIELD, status="open")
    session = _Session(_market(*FIELD, status="resolved"))
    response = _post(
        client, session, card_fingerprint=_served_fingerprint(sampled)
    )
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "card_drifted"


def test_a_renamed_market_is_refused(client):
    """#1873's copy half. The exemplar Alex reported was 2024-era TEXT, not a
    wrong percentage, so a title change must move the digest."""
    sampled = _market(*FIELD, name="Oscar winner: Best Picture")
    session = _Session(_market(*FIELD, name="Oscar Winner: Best Picture"))
    response = _post(
        client, session, card_fingerprint=_served_fingerprint(sampled)
    )
    assert response.status_code == 409


# ── the unbound arm, which only this surface has ─────────────────────────────


def test_a_pre_gate_client_still_writes_and_is_stamped_unbound(client):
    """The build already on Alex's phone does not send the key. Refusing it would
    void every label from it on the surface #1933 says he prefers — so it writes,
    and the row says it was not gated."""
    session = _Session(_market(*FIELD))
    response = _post(client, session)  # no card_fingerprint key at all

    assert response.status_code == 200
    assert response.json()["drift_gate"] == {
        "bound": False,
        "reason": "client_did_not_declare_gate",
    }
    stamp = session.added[0].label_metadata["drift_gate"]
    assert stamp["bound"] is False
    assert stamp["reason"] == "client_did_not_declare_gate"
    # The live digest is recorded even though nothing was compared against it,
    # so a later reader can tell WHICH card the ungated label was written on.
    assert stamp["fingerprint"] == _served_fingerprint(_market(*FIELD))


def test_a_gate_aware_client_that_sends_nothing_is_refused(client):
    """Empty is a declaration, not a legacy build. This is the row that stops
    the unbound arm collapsing into 'never refuse' — without it, a client could
    bypass the whole gate by clearing one string."""
    session = _Session(_market(*FIELD))
    response = _post(client, session, card_fingerprint="")
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "card_fingerprint_missing"
    assert session.added == []


def test_an_event_judgment_is_unbound_for_a_named_reason(client):
    session = _Session(None)
    response = _post(
        client,
        session,
        item_type="event",
        market_id=None,
        event_id=771,
    )
    assert response.status_code == 200
    assert response.json()["drift_gate"]["reason"] == "no_market_target"


# ── the audit trail is derived, not accepted ────────────────────────────────


def test_the_stored_card_fields_come_from_the_server_not_the_body(client):
    """UX-P110's finding, applied to this surface: the stored snapshot is read
    back as the record of what Alex saw, and it used to be whatever the phone
    posted."""
    market = _market(*FIELD)
    session = _Session(market)
    response = _post(
        client,
        session,
        card_fingerprint=_served_fingerprint(market),
        card_snapshot={
            "schema_version": "discover-card-v1",
            "batch_id": "batch-9",
            "name": "A TITLE THE SERVER NEVER SERVED",
            "rendered_probability": 0.01,
            "top_outcomes": [{"name": "Fabricated", "probability": 0.01}],
            "rank": 3,
        },
    )
    assert response.status_code == 200

    snapshot = session.added[0].label_metadata["card_snapshot"]
    assert snapshot["name"] == "Michigan Senate winner?"
    assert snapshot["rendered_probability"] == pytest.approx(0.61)
    assert snapshot["top_outcomes"][0]["name"] == "Democrat"
    assert snapshot["card_fields_source"] == "server_derived"
    # The posted copy is KEPT beside the derived one, never instead of it — a
    # fix that silently swaps them destroys the evidence for its own necessity.
    assert snapshot["name_at_post"] == "A TITLE THE SERVER NEVER SERVED"
    # Context the server genuinely does not know is still the client's.
    assert snapshot["batch_id"] == "batch-9"
    assert snapshot["rank"] == 3


def test_the_stored_market_name_is_the_live_one(client):
    """`market_name` feeds `_cluster_identity`, so a stale copy forks one
    question into two clusters."""
    market = _market(*FIELD)
    session = _Session(market)
    response = _post(
        client,
        session,
        card_fingerprint=_served_fingerprint(market),
        market_name="Michigan senate winner?",
    )
    assert response.status_code == 200
    assert session.added[0].market_name == "Michigan Senate winner?"


# ── the fingerprint is over the CARD, not over the sampling run ─────────────


def test_rank_and_stratum_cannot_reach_the_digest(client):
    """Otherwise a card re-sampled at a different position tomorrow would refuse
    a verdict for a change nobody can see on screen — and the verdict path, which
    has no rank at all, could never agree with the GET."""
    market = _market(*FIELD)
    a = admin_judgments._serialize_labeling_candidate(market, rank=1, stratum="top_feed_like")
    b = admin_judgments._serialize_labeling_candidate(market, rank=17, stratum="stale_fixable")
    assert a["card_fingerprint"] == b["card_fingerprint"]
    assert a["rank"] != b["rank"]


def test_the_verdict_path_and_the_sampler_derive_the_same_digest(client):
    """Not two implementations that agree — literally the same function. Asserted
    because a hand-rolled second derivation here is precisely the shape of the
    defect #1933 filed."""
    market = _market(*FIELD)
    served = admin_judgments._serialize_labeling_candidate(
        market, rank=4, stratum="top_feed_like"
    )["card_fingerprint"]
    assert admin_judgments._native_card_fingerprint(market) == served


def test_the_candidates_endpoint_serves_a_fingerprint_on_every_card(client):
    market = _market(*FIELD)
    row = admin_judgments._serialize_labeling_candidate(market, rank=1, stratum="s")
    assert row["card_fingerprint"]
    assert len(row["card_fingerprint"]) == 16
