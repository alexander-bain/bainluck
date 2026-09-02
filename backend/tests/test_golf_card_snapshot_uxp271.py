"""UX-P271 (#2661; CERT-746 repair): the snapshot receipt, and what it must outlive.

Route-level behaviour is guarded in
`tests/integration/test_route_progression_card_binding_uxp271.py`. This file guards
the two things that live outside the request: the TTL derivation the bind depends
on, and the writer that registers a snapshot before anyone can ask for it.

The load-bearing one is `test_a_snapshot_outlives_every_card_a_browser_can_hold`.
The whole repair rests on a claim about time — that a registered snapshot stays
resolvable for as long as some browser might still be showing the card it names —
and that claim is a sum of three constants owned by three different modules. A
comment asserting they add up is worth nothing the first time one of them moves.
"""

import json

import pytest

from app.utils.golf_card_snapshot import (
    CARD_CACHE_TTL_S,
    CARD_HTTP_MAX_AGE_S,
    CARD_HTTP_SWR_S,
    CARD_RECEIPT_FIELD,
    SNAPSHOT_KEY_PREFIX,
    SNAPSHOT_TTL_S,
    card_win_map,
    card_win_receipt,
    progression_name_key,
    resolve_snapshot,
    snapshot_body,
    snapshot_key,
    stamp_card_payload,
)

TOURNAMENT = "Omega European Masters"
GOLFERS = [
    {"name": "Ryan Gerard", "probability": 0.085},
    {"name": "Matt Wallace", "probability": 0.058},
    {"name": "Nicolai Højgaard", "probability": 0.044},
]


def _payload(golfers=None, name=TOURNAMENT):
    return {"tournaments": [{"name": name, "golfers": golfers if golfers is not None else GOLFERS}]}


# =============================================================================
class TestTheSnapshotOutlivesTheCard:
    """The bind is only as good as the window it survives."""

    def test_a_snapshot_outlives_every_card_a_browser_can_hold(self):
        """THE derivation. A card response reaching a browser can be as old as

            the Redis card key's own TTL
          + the HTTP freshness window
          + the stale-while-revalidate window

        and a snapshot that expires first leaves the page holding a card nobody
        can resolve — which degrades to exactly the defect CERT-746 named.
        """
        assert SNAPSHOT_TTL_S >= (
            CARD_CACHE_TTL_S + CARD_HTTP_MAX_AGE_S + CARD_HTTP_SWR_S
        )

    def test_the_mirrored_card_ttl_still_equals_the_writers(self):
        """Goes red the day the precompute's TTL is raised, which is the only way
        the sum above can silently stop being true."""
        from app.tasks.precompute_category_pages import CACHE_TTL

        assert CARD_CACHE_TTL_S == CACHE_TTL, (
            f"the card key's TTL moved to {CACHE_TTL}; SNAPSHOT_TTL_S must follow "
            "or a live card can outlive the snapshot naming it"
        )

    def test_the_mirrored_http_window_still_equals_the_policys(self):
        """The other half of the sum, owned by the cache middleware.

        Also pins the premise of the whole ship: `/api/golf` really is HTTP-cached.
        If it ever stops being, this repair is not wrong — it is unnecessary — and
        a reader should find that out here rather than by re-deriving CERT-746.
        """
        from app.utils.http_cache_policy import CACHE_RULES, cache_control_for

        rule = dict(CACHE_RULES).get("/api/golf")
        assert rule == CARD_HTTP_MAX_AGE_S, (
            f"/api/golf's max-age is {rule}, not the mirrored {CARD_HTTP_MAX_AGE_S}"
        )

        directive = cache_control_for(
            method="GET",
            status_code=200,
            path="/api/golf",
            identity_bearing=False,
            route_directive=None,
        )
        assert directive == (
            f"public, max-age={CARD_HTTP_MAX_AGE_S}, "
            f"stale-while-revalidate={CARD_HTTP_SWR_S}"
        ), directive


# =============================================================================
class TestStampingACardPayload:
    def test_every_tournament_with_golfers_is_stamped_and_registered(self):
        payload = _payload()
        writes = stamp_card_payload(payload)

        entry = payload["tournaments"][0]
        assert entry[CARD_RECEIPT_FIELD] == card_win_receipt(card_win_map(entry))
        assert [k for k, _ in writes] == [snapshot_key(entry[CARD_RECEIPT_FIELD])]

    def test_the_registered_body_round_trips_through_resolve(self):
        """The writer and the reader must agree, or the bind never fires in
        production while every unit test passes on its own half."""
        payload = _payload()
        writes = stamp_card_payload(payload)
        receipt = payload["tournaments"][0][CARD_RECEIPT_FIELD]
        (_key, body) = writes[0]

        assert resolve_snapshot(body, receipt, TOURNAMENT) == card_win_map(
            payload["tournaments"][0]
        )

    def test_stamping_twice_is_idempotent(self):
        """The route stamps on the cache-hit path too. If that were not stable,
        every request would issue a different receipt for identical bytes."""
        payload = _payload()
        stamp_card_payload(payload)
        first = payload["tournaments"][0][CARD_RECEIPT_FIELD]
        stamp_card_payload(payload)

        assert payload["tournaments"][0][CARD_RECEIPT_FIELD] == first

    def test_a_tournament_with_no_golfers_registers_nothing(self):
        payload = _payload(golfers=[])
        writes = stamp_card_payload(payload)

        assert writes == []
        assert payload["tournaments"][0][CARD_RECEIPT_FIELD] is None

    def test_a_malformed_golfer_does_not_cost_the_tournament_its_receipt(self):
        payload = _payload(golfers=GOLFERS + [{"name": "Broken"}, "not a dict"])
        writes = stamp_card_payload(payload)

        assert len(writes) == 1
        assert payload["tournaments"][0][CARD_RECEIPT_FIELD] is not None

    def test_keys_live_under_a_single_namespace(self):
        payload = _payload()
        writes = stamp_card_payload(payload)
        assert writes[0][0].startswith(SNAPSHOT_KEY_PREFIX)


# =============================================================================
class TestResolveRefusesRatherThanGuesses:
    """Each refusal is a way the table could otherwise print numbers the page is
    not showing — which is the defect, not a lesser version of it."""

    def setup_method(self):
        self.wins = card_win_map(_payload()["tournaments"][0])
        self.receipt = card_win_receipt(self.wins)
        self.body = snapshot_body(TOURNAMENT, self.wins)

    def test_the_happy_path_resolves(self):
        assert resolve_snapshot(self.body, self.receipt, TOURNAMENT) == self.wins

    def test_another_tournaments_snapshot_is_refused(self):
        assert resolve_snapshot(self.body, self.receipt, "Biltmore Championship") is None

    def test_a_body_that_does_not_hash_to_its_receipt_is_refused(self):
        tampered = dict(self.wins)
        tampered["name:matt wallace"] = 0.99
        assert (
            resolve_snapshot(snapshot_body(TOURNAMENT, tampered), self.receipt, TOURNAMENT)
            is None
        )

    @pytest.mark.parametrize(
        "raw", [None, "", b"", "not json", "[]", '{"wins": {}}', '{"wins": null}']
    )
    def test_unusable_bytes_are_refused(self, raw):
        assert resolve_snapshot(raw, self.receipt, TOURNAMENT) is None

    def test_an_empty_receipt_is_refused(self):
        assert resolve_snapshot(self.body, "", TOURNAMENT) is None

    def test_a_snapshot_with_no_stored_tournament_still_resolves(self):
        """Forward compatibility in the safe direction: a body written before the
        tournament field existed still binds, because the receipt already proves
        the numbers are the ones asked for."""
        body = json.dumps({"tournament": "", "wins": self.wins}, separators=(",", ":"))
        assert resolve_snapshot(body, self.receipt, TOURNAMENT) == self.wins


# =============================================================================
class TestTheSharedNormalizer:
    """CONTROL (green on the parent too). `progression_name_key` moved modules in
    this ship; it must not have changed behaviour while moving."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Nicolai Højgaard", "name:nicolai hojgaard"),
            ("Hojgaard, Nicolai", "name:nicolai hojgaard"),
            ("Yes: Matt Wallace", "name:matt wallace"),
            ('"Ryan Gerard"', "name:ryan gerard"),
            ("Eugenio Chacarra", "name:eugenio chacarra"),
        ],
    )
    def test_the_key_is_unchanged_by_the_move(self, raw, expected):
        assert progression_name_key(raw) == expected

    def test_the_route_still_exposes_it_under_its_original_name(self):
        """`routes/futures.py` imports it under `_progression_name_key`. Anything
        that patched or referenced that path keeps working."""
        from app.routes import futures

        assert futures._progression_name_key("Nicolai Højgaard") == (
            "name:nicolai hojgaard"
        )


# =============================================================================
class TestThePrecomputeRegistersBeforeItPublishes:
    """Ordering is the correctness property, not a tidiness one.

    If the card key were written first, a request landing in between would read a
    receipt whose snapshot does not exist yet, fall back, and print the other
    card's numbers — the defect, in the one window this code creates itself.
    """

    async def test_snapshots_are_written_before_the_card_key(self, monkeypatch):
        from contextlib import asynccontextmanager

        import app.routes.golf as golf_routes
        import app.tasks.base as task_base
        import app.tasks.redis_state as redis_state
        import app.utils.golf_base as golf_base
        from app.tasks.precompute_category_pages import _precompute_golf

        built = _payload()
        built["tournaments"][0]["market_ids"] = [1]

        @asynccontextmanager
        async def _session():
            yield object()

        async def _get_golf(db):
            return built

        writes = []

        class _Redis:
            def set(self, key, value, ex=None):
                writes.append(key)

        monkeypatch.setattr(task_base, "get_task_session", _session)
        monkeypatch.setattr(golf_routes, "get_golf", _get_golf)
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _Redis())
        monkeypatch.setattr(golf_base, "publish_envelope_sync", lambda *a, **k: None)

        await _precompute_golf()

        card_index = writes.index("bainluck:category:golf")
        snapshot_indexes = [
            i for i, k in enumerate(writes) if k.startswith(SNAPSHOT_KEY_PREFIX)
        ]
        assert snapshot_indexes, f"no snapshot was registered; wrote {writes}"
        assert max(snapshot_indexes) < card_index, (
            "every snapshot must be registered BEFORE the card key it names is "
            f"published; write order was {writes}"
        )

    async def test_the_published_card_carries_its_receipts(self, monkeypatch):
        """The stamp must reach the bytes stored under the card key, or the page
        never learns the receipt to send."""
        from contextlib import asynccontextmanager

        import app.routes.golf as golf_routes
        import app.tasks.base as task_base
        import app.tasks.redis_state as redis_state
        import app.utils.golf_base as golf_base
        from app.tasks.precompute_category_pages import _precompute_golf

        built = _payload()
        stored = {}

        @asynccontextmanager
        async def _session():
            yield object()

        async def _get_golf(db):
            return built

        class _Redis:
            def set(self, key, value, ex=None):
                stored[key] = value

        monkeypatch.setattr(task_base, "get_task_session", _session)
        monkeypatch.setattr(golf_routes, "get_golf", _get_golf)
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _Redis())
        monkeypatch.setattr(golf_base, "publish_envelope_sync", lambda *a, **k: None)

        await _precompute_golf()

        card = json.loads(stored["bainluck:category:golf"])
        receipt = card["tournaments"][0][CARD_RECEIPT_FIELD]
        assert receipt
        assert snapshot_key(receipt) in stored
