"""UX-P271 (#2661; CERT-746 repair): the table quotes the card it is reading.

UX-P270 made the progression endpoint adopt the win numbers `GET /api/golf`
publishes, so `/categories/golf` stops printing two probabilities for one golfer.
CERT-746 withheld the token because it adopted *a* card and not *the* card:

    `/api/golf` ships `public, max-age=300, stale-while-revalidate=60`, so the page
    can render a card response up to 360 s old out of an HTTP cache, while the
    progression request — which carries no `Cache-Control` at all — reads Redis at
    request time. If the hourly precompute lands in between, the card shows
    snapshot N and the table adopts snapshot N+1.

Both halves were re-measured against production before this file was written
rather than taken from the block: `/api/golf` answers
`cache-control: public, max-age=300, stale-while-revalidate=60`, and
`/api/futures/{id}/progression` answers with no `Cache-Control` header at all.

WHY THE INHERITED UX-P270 SUITE IS GREEN ON THIS DEFECT, AND STAYS GREEN. All 17
of its tests install ONE Redis payload and let both surfaces read it, so "the card
the browser is holding" and "the card Redis holds now" are the same object in every
fixture it has. It cannot express this bug in principle, and it needed no edit —
which is the tell, not the reassurance. Every fixture in THIS file installs two
different card snapshots at once, which is the only way the two clocks can be
observed to disagree.

THE BIND. A snapshot is named by a receipt over its own contents, the page sends
the receipt of the card it is holding, and the endpoint resolves THAT snapshot.
Content-addressing rather than a counter is deliberate and
`test_two_snapshots_with_the_same_numbers_share_a_receipt` pins why: in a quiet
market consecutive precomputes publish identical numbers, and a counter would
manufacture a mismatch — and a refetch — every hour to prove nothing had moved.

THE RESIDUAL, GUARDED RATHER THAN HIDDEN. Redis here is a ~100MB LRU shared with
Celery, so a snapshot can be evicted inside its TTL. The endpoint must not then
adopt a *different* snapshot while the caller believes it got the one it asked
for — that is the original defect wearing a fix's clothes. `TestAnUnresolvable
ReceiptSaysSo` pins that it falls back to the current card AND echoes that card's
own receipt, which is what lets the page converge.

Prices are the production values for markets 59863411 (DataGolf) and 59759220
(Kalshi) measured 2026-09-02, and the card strings are what `GET /api/golf` was
publishing at the same moment.
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.golf_card_snapshot import (
    CARD_RECEIPT_FIELD,
    card_win_map,
    card_win_receipt,
    snapshot_body,
    snapshot_key,
)

pytestmark = pytest.mark.anyio

CARD_KEY = "bainluck:category:golf"
TOURNAMENT = "Omega European Masters"

# --- Snapshot N: the card the browser is holding -----------------------------
# These are the numbers on screen. They are what the Win column must print.
OLD_GERARD = 0.085
OLD_WALLACE = 0.058  # renders "5.8%" — #2661's headline golfer
OLD_NICOLAI = 0.044
OLD_CHACARRA = 0.033  # single-source; #2661's named CONTROL

# --- Snapshot N+1: the card Redis holds NOW ----------------------------------
# Deliberately different in every position. If the endpoint reads "the current
# card" instead of "the card that was asked for", these are what it prints, and
# the user sees two numbers again — which is the whole of CERT-746.
NEW_GERARD = 0.091
NEW_WALLACE = 0.050  # renders "5.0%" — CERT-740's own worked figure
NEW_NICOLAI = 0.039
NEW_CHACARRA = 0.031

# What the live rows hold. Different again from BOTH cards, so a test that passes
# cannot be passing because the blend happens to agree with a snapshot.
LIVE_DG_GERARD = 0.0887
LIVE_KS_GERARD = 0.0782
LIVE_DG_WALLACE = 0.0451
LIVE_KS_WALLACE = 0.0543
LIVE_DG_NICOLAI = 0.044567
LIVE_KS_NICOLAI = 0.039
LIVE_DG_CHACARRA = 0.033117
LIVE_DG_UNRANKED = 0.0042
LIVE_KS_UNRANKED = 0.006


def _golfers(gerard, wallace, nicolai, chacarra):
    return [
        {"name": "Ryan Gerard", "probability": gerard},
        {"name": "Matt Wallace", "probability": wallace},
        # The card spells him with the o-slash; DataGolf does not. The shared
        # normalizer is what joins them, and the receipt is computed over its keys.
        {"name": "Nicolai Højgaard", "probability": nicolai},
        {"name": "Eugenio Chacarra", "probability": chacarra},
    ]


OLD_GOLFERS = _golfers(OLD_GERARD, OLD_WALLACE, OLD_NICOLAI, OLD_CHACARRA)
NEW_GOLFERS = _golfers(NEW_GERARD, NEW_WALLACE, NEW_NICOLAI, NEW_CHACARRA)


def _entry(golfers, *, name=TOURNAMENT):
    return {"name": name, "golfers": golfers}


def _card_payload(golfers, *, name=TOURNAMENT):
    """A `GET /api/golf` payload, stamped the way the route stamps one."""
    entry = _entry(golfers, name=name)
    payload = {
        "tournaments": [
            {"name": "Biltmore Championship Asheville", "golfers": []},
            entry,
        ]
    }
    # Stamped through the SHIPPED function, not a reimplementation of it, so these
    # fixtures cannot drift from what the route actually publishes.
    from app.utils.golf_card_snapshot import stamp_card_payload

    stamp_card_payload(payload)
    return payload


def _receipt_for(golfers, *, name=TOURNAMENT):
    return card_win_receipt(card_win_map(_entry(golfers, name=name)))


OLD_RECEIPT = _receipt_for(OLD_GOLFERS)
NEW_RECEIPT = _receipt_for(NEW_GOLFERS)


def _assert_the_two_snapshots_are_distinguishable():
    """If the two fixtures ever collide, every claim in this file goes vacuous."""
    assert OLD_RECEIPT != NEW_RECEIPT, (
        "the stale and current cards must have different receipts, or 'bound to "
        "the one I asked for' and 'bound to whatever is current' are the same test"
    )
    assert OLD_WALLACE != NEW_WALLACE


_assert_the_two_snapshots_are_distinguishable()


# --- DB fixtures (same shapes as the UX-P270 suite) --------------------------
def _result_unique_all(values):
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = values
    return result


def _result_scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _outcome(name, probability, *, change=None, team_id=None):
    return SimpleNamespace(
        name=name,
        team_id=team_id,
        current_probability=probability,
        probability_change_24h=change,
    )


def _market(market_id, name, external_id, source, outcomes, *, tier=None, sport="golf"):
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        source=source,
        market_tier=tier,
        status="open",
        llm_sport_category=sport,
        canonical_market_key=None,
        resolution_date=datetime(2026, 9, 6, tzinfo=timezone.utc),
        event_id=None,
        outcomes=outcomes,
    )


def _datagolf_win(sport="golf"):
    return _market(
        59863411,
        "Omega European Masters - Winner",
        "datagolf:euro:2026134:win",
        "datagolf",
        [
            _outcome("Ryan Gerard", LIVE_DG_GERARD),
            _outcome("Matt Wallace", LIVE_DG_WALLACE),
            _outcome("Nicolai Hojgaard", LIVE_DG_NICOLAI),
            _outcome("Eugenio Chacarra", LIVE_DG_CHACARRA),
            _outcome("Unranked Qualifier", LIVE_DG_UNRANKED),
        ],
        sport=sport,
    )


def _datagolf_top5(sport="golf"):
    return _market(
        59863412,
        "Omega European Masters - Top 5 Finish",
        "datagolf:euro:2026134:top_5",
        "datagolf",
        [
            _outcome("Ryan Gerard", 0.277458),
            _outcome("Matt Wallace", 0.174813),
        ],
        sport=sport,
    )


def _kalshi_win(sport="golf"):
    return _market(
        59759220,
        "Omega European Masters Winner",
        "KXDPWORLDTOUR-OMEM26",
        "kalshi",
        [
            _outcome("Ryan Gerard", LIVE_KS_GERARD),
            _outcome("Matt Wallace", LIVE_KS_WALLACE),
            _outcome("Nicolai Højgaard", LIVE_KS_NICOLAI),
            _outcome("Unranked Qualifier", LIVE_KS_UNRANKED),
        ],
        tier=1,
        sport=sport,
    )


def _wire_two_source(mock_db, sport="golf"):
    mock_db.execute.side_effect = [
        _result_scalar_one_or_none(_datagolf_win(sport)),
        _result_unique_all([_datagolf_top5(sport)]),
        _result_unique_all([_kalshi_win(sport)]),
    ]


# --- The Redis stub ----------------------------------------------------------
class _Reads:
    def __init__(self):
        self.keys = []


def _install_redis(monkeypatch, mapping, *, reads=None, fail=False):
    """Stub Redis with a KEY-ADDRESSED map rather than one blanket payload.

    This is the difference from the UX-P270 harness and the reason this file can
    see the defect at all: the current card and the pinned snapshot are two
    different keys holding two different sets of numbers, exactly as production
    holds them for the 360 s after a precompute lands.
    """
    import app.tasks.redis_state as redis_state

    tracker = reads if reads is not None else _Reads()

    def _factory():
        if fail:
            raise ConnectionError("redis unreachable")
        client = AsyncMock()

        async def _get(key):
            tracker.keys.append(key)
            value = mapping.get(key)
            return value.encode() if isinstance(value, str) else value

        client.get = _get
        client.aclose = AsyncMock()
        return client

    monkeypatch.setattr(redis_state, "get_async_redis_client", _factory)
    return tracker


def _both_cards(*, pinned=OLD_GOLFERS, current=NEW_GOLFERS, pinned_tournament=TOURNAMENT):
    """Redis as it looks in the CERT-746 window: snapshot N pinned, N+1 current."""
    pinned_map = card_win_map(_entry(pinned, name=pinned_tournament))
    return {
        CARD_KEY: json.dumps(_card_payload(current)),
        snapshot_key(card_win_receipt(pinned_map)): snapshot_body(
            pinned_tournament, pinned_map
        ),
    }


# --- Request helpers ---------------------------------------------------------
async def _get(client, *, receipt=None, market_id=59863411, top_n=40):
    url = f"/api/futures/{market_id}/progression?top_n={top_n}"
    if receipt is not None:
        url += f"&golf_card_receipt={receipt}"
    resp = await client.get(url)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _win_of(body, name):
    for p in body["participants"]:
        if p["name"] == name:
            return p["probabilities"].get("win")
    return None


def _stage_of(body, name, stage):
    for p in body["participants"]:
        if p["name"] == name:
            return p["probabilities"].get(stage)
    return None


def _names(body):
    return [p["name"] for p in body["participants"]]


def _renders(probability):
    """The card's `(p * 100).toFixed(1)` — the precision the user actually reads."""
    return f"{probability * 100:.1f}%"


# =============================================================================
class TestTheSeedIsReal:
    """If the stub stops arriving as designed, every claim below is vacuous."""

    async def test_the_pinned_snapshot_is_asked_for_first(
        self, client, mock_db, monkeypatch
    ):
        reads = _Reads()
        _install_redis(monkeypatch, _both_cards(), reads=reads)
        _wire_two_source(mock_db)

        await _get(client, receipt=OLD_RECEIPT)

        assert reads.keys[0] == snapshot_key(OLD_RECEIPT), (
            "the endpoint must resolve the caller's snapshot BEFORE falling back "
            f"to the current card; it read {reads.keys}"
        )

    async def test_a_resolved_snapshot_never_reads_the_current_card(
        self, client, mock_db, monkeypatch
    ):
        """Not an optimization claim — a correctness one.

        If the current card is read at all on the bound path, some later edit can
        prefer it, and the bug returns silently. The bound path must not depend on
        the value of a key it is deliberately ignoring.
        """
        reads = _Reads()
        _install_redis(monkeypatch, _both_cards(), reads=reads)
        _wire_two_source(mock_db)

        await _get(client, receipt=OLD_RECEIPT)

        assert CARD_KEY not in reads.keys, reads.keys

    async def test_without_a_receipt_the_current_card_is_read(
        self, client, mock_db, monkeypatch
    ):
        reads = _Reads()
        _install_redis(monkeypatch, _both_cards(), reads=reads)
        _wire_two_source(mock_db)

        await _get(client)

        assert reads.keys == [CARD_KEY], reads.keys


# =============================================================================
class TestTheCardOnScreenIsTheOneAdopted:
    """The load-bearing class. CERT-746's defect, expressed as failing assertions."""

    async def test_a_stale_card_receipt_beats_the_newer_card_in_redis(
        self, client, mock_db, monkeypatch
    ):
        """THE test. The browser holds snapshot N; Redis has moved on to N+1.

        UX-P270 reads "the current card" and prints N+1 beside a card showing N,
        which is #2661 all over again with an extra hop. Bound to the receipt, the
        table prints what the user is looking at.
        """
        _install_redis(monkeypatch, _both_cards())
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        assert _renders(_win_of(body, "Matt Wallace")) == _renders(OLD_WALLACE), (
            "the table must print the card ON SCREEN (5.8%), not the card Redis "
            f"holds now (5.0%); it printed {_renders(_win_of(body, 'Matt Wallace'))}"
        )

    async def test_every_bound_golfer_matches_the_card_on_screen(
        self, client, mock_db, monkeypatch
    ):
        """One golfer agreeing could be a coincidence; the whole card cannot be.

        Compared at the precision the page renders, not the precision the endpoint
        computes in — "closer" is not "fixed" when the user reads one decimal.
        """
        _install_redis(monkeypatch, _both_cards())
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        for golfer in OLD_GOLFERS:
            live = _win_of(body, golfer["name"].replace("ø", "o"))
            shown = _win_of(body, golfer["name"]) if live is None else live
            assert shown is not None, f"{golfer['name']} is missing from the table"
            assert _renders(shown) == _renders(golfer["probability"]), golfer["name"]

    async def test_the_applied_receipt_is_echoed(self, client, mock_db, monkeypatch):
        _install_redis(monkeypatch, _both_cards())
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        assert body["golf_card_receipt"] == OLD_RECEIPT

    async def test_the_bound_numbers_drive_the_sort(
        self, client, mock_db, monkeypatch
    ):
        """The table must be ordered by the numbers it prints.

        #2661's second clause is that the table's own sort reorders the
        leaderboard. Adopting a value without re-sorting on it reintroduces that.
        """
        inverted = _golfers(0.010, 0.400, 0.020, 0.030)
        _install_redis(
            monkeypatch, _both_cards(pinned=inverted, current=NEW_GOLFERS)
        )
        _wire_two_source(mock_db)

        body = await _get(client, receipt=_receipt_for(inverted))

        assert _names(body)[0] == "Matt Wallace", _names(body)


# =============================================================================
class TestAnUnresolvableReceiptSaysSo:
    """Redis is a shared LRU: a snapshot can vanish inside its TTL.

    The requirement is not that this never happens — it is that the endpoint never
    pretends it did not. Adopting different numbers under the caller's receipt is
    the original defect with a receipt attached.
    """

    async def test_an_evicted_snapshot_falls_back_to_the_current_card(
        self, client, mock_db, monkeypatch
    ):
        _install_redis(monkeypatch, {CARD_KEY: json.dumps(_card_payload(NEW_GOLFERS))})
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        assert _renders(_win_of(body, "Matt Wallace")) == _renders(NEW_WALLACE)

    async def test_an_evicted_snapshot_echoes_a_DIFFERENT_receipt(
        self, client, mock_db, monkeypatch
    ):
        """The signal the page converges on. Without it the fallback is silent."""
        _install_redis(monkeypatch, {CARD_KEY: json.dumps(_card_payload(NEW_GOLFERS))})
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        assert body["golf_card_receipt"] == NEW_RECEIPT
        assert body["golf_card_receipt"] != OLD_RECEIPT, (
            "echoing the requested receipt while serving different numbers would "
            "tell the page it is bound when it is not"
        )

    async def test_a_snapshot_belonging_to_another_tournament_is_refused(
        self, client, mock_db, monkeypatch
    ):
        """A receipt is caller-supplied. It must not be a pointer into someone
        else's numbers: without the tournament check, one page could make another
        tournament's probabilities appear in this table."""
        mapping = _both_cards(pinned_tournament="Biltmore Championship Asheville")
        _install_redis(monkeypatch, mapping)
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        assert _renders(_win_of(body, "Matt Wallace")) == _renders(NEW_WALLACE)
        assert body["golf_card_receipt"] == NEW_RECEIPT

    async def test_a_snapshot_that_does_not_hash_to_its_receipt_is_refused(
        self, client, mock_db, monkeypatch
    ):
        """What makes the address content-addressed in practice, not just intent."""
        tampered = card_win_map(_entry(OLD_GOLFERS))
        tampered["name:matt wallace"] = 0.99
        _install_redis(
            monkeypatch,
            {
                CARD_KEY: json.dumps(_card_payload(NEW_GOLFERS)),
                snapshot_key(OLD_RECEIPT): snapshot_body(TOURNAMENT, tampered),
            },
        )
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        assert _win_of(body, "Matt Wallace") != 0.99
        assert body["golf_card_receipt"] == NEW_RECEIPT

    @pytest.mark.parametrize(
        "receipt", ["", "not-a-receipt", "../../etc/passwd", "a" * 64]
    )
    async def test_a_junk_receipt_never_breaks_the_page(
        self, client, mock_db, monkeypatch, receipt
    ):
        _install_redis(monkeypatch, {CARD_KEY: json.dumps(_card_payload(NEW_GOLFERS))})
        _wire_two_source(mock_db)

        body = await _get(client, receipt=receipt)

        assert _renders(_win_of(body, "Matt Wallace")) == _renders(NEW_WALLACE)

    async def test_an_over_long_receipt_is_rejected_by_validation(
        self, client, mock_db, monkeypatch
    ):
        """Bounded input: a caller cannot make this endpoint build unbounded keys."""
        _install_redis(monkeypatch, {CARD_KEY: json.dumps(_card_payload(NEW_GOLFERS))})
        _wire_two_source(mock_db)

        resp = await client.get(
            f"/api/futures/59863411/progression?top_n=40&golf_card_receipt={'a' * 65}"
        )

        assert resp.status_code == 422, resp.status_code

    async def test_a_dead_redis_leaves_the_live_blend(
        self, client, mock_db, monkeypatch
    ):
        _install_redis(monkeypatch, {}, fail=True)
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        assert body["golf_card_receipt"] is None
        assert _win_of(body, "Matt Wallace") is not None


# =============================================================================
class TestBlastRadius:
    """Controls. Every one of these is GREEN ON MASTER TOO — verified by the red
    run, not asserted by the label. Their job is to pin what must NOT move."""

    async def test_no_receipt_behaves_exactly_as_UX_P270(
        self, client, mock_db, monkeypatch
    ):
        """CONTROL (green on the parent too). The receipt is additive: a caller
        that sends none — an older client, or any other consumer of this endpoint —
        gets precisely the previous behaviour."""
        _install_redis(monkeypatch, _both_cards())
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _renders(_win_of(body, "Matt Wallace")) == _renders(NEW_WALLACE)

    async def test_rows_the_card_does_not_carry_stay_live(
        self, client, mock_db, monkeypatch
    ):
        """CONTROL (green on the parent too). The card ships its top golfers; the
        table shows up to 40. Rows with no authority keep the live blend and are
        left strictly fresher — binding must not make them staler."""
        _install_redis(monkeypatch, _both_cards())
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        win = _win_of(body, "Unranked Qualifier")
        assert win is not None
        assert win not in (OLD_WALLACE, NEW_WALLACE)

    async def test_non_win_stages_stay_live(self, client, mock_db, monkeypatch):
        """CONTROL (green on the parent too). `win` is the only cell the card also
        publishes. Top 5 must keep its own number at its own freshness."""
        _install_redis(monkeypatch, _both_cards())
        _wire_two_source(mock_db)

        body = await _get(client, receipt=OLD_RECEIPT)

        assert _stage_of(body, "Ryan Gerard", "top_5") == pytest.approx(0.277458)

    async def test_the_authority_never_creates_a_row(
        self, client, mock_db, monkeypatch
    ):
        """#2661's two named controls, in the binding path.

        A golfer on the card who is not in this market's field must not become a
        row. Kalshi spells two of them differently (`Eugenio Lopez-Chacarra`,
        `Angel Ayora Fanegas`); letting the authority add participants renders the
        same golfer twice at two prices, which is worse than the reported bug.
        """
        ghost = OLD_GOLFERS + [{"name": "Angel Ayora Fanegas", "probability": 0.02}]
        _install_redis(monkeypatch, _both_cards(pinned=ghost))
        _wire_two_source(mock_db)

        body = await _get(client, receipt=_receipt_for(ghost))

        assert "Angel Ayora Fanegas" not in _names(body)

    async def test_a_non_golf_progression_echoes_no_receipt(
        self, client, mock_db, monkeypatch
    ):
        """CONTROL (green on the parent too). The field is golf-scoped; nothing
        else acquires a card authority or a receipt."""
        _install_redis(monkeypatch, _both_cards())
        _wire_two_source(mock_db, sport="basketball")

        body = await _get(client, receipt=OLD_RECEIPT)

        assert body.get("golf_card_receipt") is None


# =============================================================================
class TestTheReceiptIsContentAddressed:
    """Why a content hash and not a counter or a timestamp."""

    def test_two_snapshots_with_the_same_numbers_share_a_receipt(self):
        """The reason this does not cost a refetch an hour.

        In a quiet market consecutive precomputes publish identical numbers. A
        counter or a `generated_at` would change anyway, so every hour the page
        would see a mismatch and re-read the card past its HTTP cache to discover
        that nothing had moved.
        """
        rebuilt = _golfers(OLD_GERARD, OLD_WALLACE, OLD_NICOLAI, OLD_CHACARRA)
        assert _receipt_for(rebuilt) == OLD_RECEIPT

    def test_one_changed_number_is_a_different_receipt(self):
        moved = _golfers(OLD_GERARD, OLD_WALLACE + 0.001, OLD_NICOLAI, OLD_CHACARRA)
        assert _receipt_for(moved) != OLD_RECEIPT

    def test_key_order_does_not_change_the_receipt(self):
        """Two processes build this payload — the worker and the web dyno. If dict
        ordering could change the address, they would disagree about what a
        snapshot is called and the bind would fail intermittently."""
        shuffled = list(reversed(OLD_GOLFERS))
        assert _receipt_for(shuffled) == OLD_RECEIPT

    def test_a_tournament_with_no_golfers_is_stamped_none(self):
        """Not the receipt of the empty map: there is nothing to bind to, and one
        shared address for every empty tournament is a cross-tournament hazard."""
        payload = _card_payload([], name="Empty Open")
        empty = next(t for t in payload["tournaments"] if t["name"] == "Empty Open")
        assert empty[CARD_RECEIPT_FIELD] is None


# =============================================================================
class TestTheCardRouteIssuesTheReceipt:
    """The page can only send a receipt the card route gave it.

    A backend that binds perfectly and a card payload with nothing to bind BY is
    the same as no fix at all — the half of a two-endpoint ship that is easiest to
    leave out, because every test of the other half still passes.
    """

    async def test_the_card_route_stamps_what_it_serves(
        self, client, mock_db, monkeypatch
    ):
        _install_redis(
            monkeypatch, {CARD_KEY: json.dumps(_card_payload(OLD_GOLFERS))}
        )

        resp = await client.get("/api/golf")

        assert resp.status_code == 200, resp.text
        entry = next(
            t for t in resp.json()["tournaments"] if t["name"] == TOURNAMENT
        )
        assert entry[CARD_RECEIPT_FIELD] == OLD_RECEIPT

    async def test_a_payload_written_before_this_deploy_is_stamped_on_read(
        self, client, mock_db, monkeypatch
    ):
        """The transition case, and it lasts up to the card key's full 7,200 s TTL.

        Stamping is a pure function of the bytes served, so an unstamped payload
        left in Redis by the previous deploy still reaches the client with a
        receipt — and because the receipt is recomputed from those same bytes on
        the progression side, it matches without any snapshot being registered.
        """
        legacy = {
            "tournaments": [
                {"name": TOURNAMENT, "golfers": OLD_GOLFERS},
            ]
        }
        assert CARD_RECEIPT_FIELD not in legacy["tournaments"][0]
        _install_redis(monkeypatch, {CARD_KEY: json.dumps(legacy)})

        resp = await client.get("/api/golf")

        assert resp.status_code == 200, resp.text
        assert resp.json()["tournaments"][0][CARD_RECEIPT_FIELD] == OLD_RECEIPT

    async def test_the_receipt_the_card_issues_is_the_one_progression_honours(
        self, client, mock_db, monkeypatch
    ):
        """End to end across the two endpoints, which is where a receipt scheme
        actually breaks: one side hashing something the other does not."""
        _install_redis(
            monkeypatch, {CARD_KEY: json.dumps(_card_payload(OLD_GOLFERS))}
        )
        card = (await client.get("/api/golf")).json()
        issued = next(
            t for t in card["tournaments"] if t["name"] == TOURNAMENT
        )[CARD_RECEIPT_FIELD]

        _install_redis(monkeypatch, _both_cards(pinned=OLD_GOLFERS))
        _wire_two_source(mock_db)
        body = await _get(client, receipt=issued)

        assert body["golf_card_receipt"] == issued
        assert _renders(_win_of(body, "Matt Wallace")) == _renders(OLD_WALLACE)
