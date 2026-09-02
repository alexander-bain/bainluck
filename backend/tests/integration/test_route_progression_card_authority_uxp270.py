"""UX-P270 (#2661; CERT-740 repair): one golfer, one number — and one clock.

UX-P268 made the progression table reproduce `GET /api/golf`'s blend ARITHMETIC.
CERT-740 withheld the token because arithmetic was never the whole gap:

    `/api/golf` serves an hourly Redis snapshot while progression blends live
    outcome rows.

Both surfaces read `futures_outcomes.current_probability`, but through different
clocks. The card is `bainluck:category:golf`, written hourly by the category
precompute with a 7,200 s TTL; this endpoint reads the rows live, and during play
the DataGolf poller rewrites them every 90 seconds. So the two numbers drift apart
whenever a price moves between the snapshot and the request, and no amount of
arithmetic fidelity closes a gap that is made of time.

That is why the inherited UX-P268 suite is green on the defect: all 16 of its tests
hand BOTH surfaces the same captured price set, so its fixtures cannot express
"the card is older than the rows". Every test in this file exists to express
exactly that, and the load-bearing one is `test_stale_card_beats_fresher_rows`.

THE FIX, AND WHY IT POINTS THIS WAY. Two independently-clocked computations of one
quantity cannot be made to agree; only one authority can. The card is the authority
and not the reverse because the reverse is unaffordable — `get_golf` is a ~1.5 s
rebuild behind a 45 ms cached read, and `/api/golf` additionally ships
`max-age=300, stale-while-revalidate=60`, so even a live origin would be read
through a browser cache this endpoint does not share.

DELIBERATE AND STATED: the win column therefore inherits the card's staleness for
the golfers the card carries. That trade is the right way round — a user reading two
different numbers for one golfer on one screen is the reported defect, whereas both
numbers being equally old is the ordinary freshness budget of the page they are
already reading. `test_rows_the_card_does_not_carry_stay_live` and
`test_non_win_stages_stay_live` pin the blast radius: nothing else adopts the
card's clock.

This does NOT re-open CERT-686, which blocked serving the golf tournament HEADLINE
field from this cache. Nothing here changes what the headline reads.

Prices below are real production values for markets 59863411 (DataGolf) and
59759220 (Kalshi), measured 2026-09-02, and the card strings are what
`GET /api/golf` was publishing at the same moment.
"""

from datetime import datetime, timezone
from statistics import mean
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.anyio


def _blend(*source_prices):
    """GET /api/golf's arithmetic: quantize each source to 3dp, mean, quantize."""
    return round(mean(round(v, 3) for v in source_prices), 3)


# --- What the card was publishing (the authority) ---------------------------
CARD_WALLACE = 0.058  # renders "5.8%"
CARD_GERARD = 0.085
CARD_NICOLAI = 0.044  # card spells him "Nicolai Højgaard"
CARD_CHACARRA = 0.033  # single-source; #2661's CONTROL

# --- What the live rows hold, AFTER the card's snapshot was taken ------------
# These are deliberately NOT the prices the card was built from. That difference
# is the entire point of this file: if the endpoint recomputes instead of adopting,
# it publishes the blend of these and contradicts the card all over again.
FRESH_DG_WALLACE = 0.045100
FRESH_KS_WALLACE = 0.054300
LIVE_BLEND_WALLACE = _blend(FRESH_DG_WALLACE, FRESH_KS_WALLACE)  # 0.05 -> "5.0%"

FRESH_DG_GERARD = 0.088700
FRESH_KS_GERARD = 0.078200
LIVE_BLEND_GERARD = _blend(FRESH_DG_GERARD, FRESH_KS_GERARD)  # 0.083 -> "8.3%"

FRESH_DG_NICOLAI = 0.044567
FRESH_KS_NICOLAI = 0.039000
LIVE_BLEND_NICOLAI = _blend(FRESH_DG_NICOLAI, FRESH_KS_NICOLAI)

DG_CHACARRA = 0.033117  # single-source: no secondary market names him

# A golfer in this market's field who is NOT on the card. The card ships only its
# top 15 golfers (`golfers = all_golfers[:_MAX_GOLFERS]`, golf.py) while the table
# shows up to 40, so ~25 rows have no authority to adopt and must stay live.
FRESH_DG_UNRANKED = 0.004200
FRESH_KS_UNRANKED = 0.006000
LIVE_BLEND_UNRANKED = _blend(FRESH_DG_UNRANKED, FRESH_KS_UNRANKED)


def _assert_the_arithmetic_is_still_discriminating():
    """The whole file is vacuous if adopting and recomputing give the same number."""
    assert LIVE_BLEND_WALLACE != CARD_WALLACE
    assert LIVE_BLEND_GERARD != CARD_GERARD
    assert LIVE_BLEND_NICOLAI != CARD_NICOLAI


_assert_the_arithmetic_is_still_discriminating()


# --- DB fixtures -------------------------------------------------------------
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


def _datagolf_win():
    return _market(
        59863411,
        "Omega European Masters - Winner",
        "datagolf:euro:2026134:win",
        "datagolf",
        [
            _outcome("Ryan Gerard", FRESH_DG_GERARD),
            _outcome("Matt Wallace", FRESH_DG_WALLACE),
            # DataGolf spells him without the o-slash; the card spells him with it.
            _outcome("Nicolai Hojgaard", FRESH_DG_NICOLAI),
            _outcome("Eugenio Chacarra", DG_CHACARRA),
            _outcome("Unranked Qualifier", FRESH_DG_UNRANKED),
        ],
    )


def _datagolf_top5():
    return _market(
        59863412,
        "Omega European Masters - Top 5 Finish",
        "datagolf:euro:2026134:top_5",
        "datagolf",
        [
            _outcome("Ryan Gerard", 0.277458),
            _outcome("Matt Wallace", 0.174813),
        ],
    )


def _kalshi_win():
    return _market(
        59759220,
        "Omega European Masters Winner",
        "KXDPWORLDTOUR-OMEM26",
        "kalshi",
        [
            _outcome("Ryan Gerard", FRESH_KS_GERARD),
            _outcome("Matt Wallace", FRESH_KS_WALLACE),
            _outcome("Nicolai Højgaard", FRESH_KS_NICOLAI),
            _outcome("Unranked Qualifier", FRESH_KS_UNRANKED),
        ],
        tier=1,
    )


def _wire(mock_db, *, siblings, cross_source=None):
    results = [
        _result_scalar_one_or_none(_datagolf_win()),
        _result_unique_all(siblings),
    ]
    if cross_source is not None:
        results.append(_result_unique_all(cross_source))
    mock_db.execute.side_effect = results


def _wire_two_source(mock_db):
    _wire(mock_db, siblings=[_datagolf_top5()], cross_source=[_kalshi_win()])


# --- The card cache stub -----------------------------------------------------
CARD_GOLFERS = [
    {"name": "Ryan Gerard", "probability": CARD_GERARD},
    {"name": "Matt Wallace", "probability": CARD_WALLACE},
    {"name": "Nicolai Højgaard", "probability": CARD_NICOLAI},
    {"name": "Eugenio Chacarra", "probability": CARD_CHACARRA},
]


def _card_payload(golfers=None, *, tournament_name="Omega European Masters"):
    return {
        "tournaments": [
            {"name": "Biltmore Championship Asheville", "golfers": []},
            {
                "name": tournament_name,
                "golfers": CARD_GOLFERS if golfers is None else golfers,
            },
        ]
    }


class _Reads:
    """Records whether the endpoint actually consulted the card cache."""

    def __init__(self):
        self.keys = []


def _install_card(monkeypatch, raw, *, reads=None, fail=False):
    """Stub the golf card cache. `raw` may be bytes, str, or None (cold cache)."""
    import json

    import app.tasks.redis_state as redis_state

    tracker = reads if reads is not None else _Reads()

    def _factory():
        if fail:
            raise ConnectionError("redis unreachable")
        client = AsyncMock()

        async def _get(key):
            tracker.keys.append(key)
            return raw

        client.get = _get
        client.aclose = AsyncMock()
        return client

    monkeypatch.setattr(redis_state, "get_async_redis_client", _factory)
    return tracker


def _install_card_payload(monkeypatch, payload=None, **kwargs):
    import json

    body = _card_payload() if payload is None else payload
    return _install_card(monkeypatch, json.dumps(body).encode(), **kwargs)


# --- Request helpers ---------------------------------------------------------
async def _get(client, market_id=59863411, top_n=40):
    resp = await client.get(f"/api/futures/{market_id}/progression?top_n={top_n}")
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
    """The card's `(p * 100).toFixed(1)` for values under 10%."""
    return f"{probability * 100:.1f}%"


# =============================================================================
class TestTheSeedIsReal:
    """If the card stub stops arriving, every claim below silently becomes vacuous."""

    async def test_the_endpoint_reads_the_card_cache(self, client, mock_db, monkeypatch):
        reads = _Reads()
        _install_card_payload(monkeypatch, reads=reads)
        _wire_two_source(mock_db)

        await _get(client)

        assert reads.keys == ["bainluck:category:golf"], (
            "the win column must consult the same key GET /api/golf serves from; "
            f"observed reads: {reads.keys}"
        )

    async def test_the_key_is_the_one_the_precompute_writes(self):
        """A hardcoded reader could drift from the writer and fail silently open."""
        from app.routes.golf import GOLF_CATEGORY_CACHE_KEY
        from app.tasks.precompute_category_pages import CACHE_PREFIX

        assert GOLF_CATEGORY_CACHE_KEY == f"{CACHE_PREFIX}golf"


class TestTheShip:
    """The number the card publishes is the number the table publishes."""

    async def test_stale_card_beats_fresher_rows(self, client, mock_db, monkeypatch):
        """THE CERT-740 GUARD. The card is older than the rows and still wins.

        This is the test the inherited UX-P268 suite could not express: its
        fixtures give both surfaces one captured price set, so recomputing and
        adopting are indistinguishable there. Here the live rows blend to 5.0%
        while the card says 5.8%, which is precisely the split CERT-740 measured
        on production at 11:38Z.
        """
        _install_card_payload(monkeypatch)
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _win_of(body, "Matt Wallace") == CARD_WALLACE
        assert _win_of(body, "Matt Wallace") != LIVE_BLEND_WALLACE

    async def test_every_card_golfer_agrees_at_the_rendered_precision(
        self, client, mock_db, monkeypatch
    ):
        """#2661's headline is "two different numbers", so check the rendered string.

        UX-P268's own lesson: a fix that leaves two different numbers has not
        shipped, however much better the residual looks in float.
        """
        _install_card_payload(monkeypatch)
        _wire_two_source(mock_db)

        body = await _get(client)

        for name, card_value in (
            ("Matt Wallace", CARD_WALLACE),
            ("Ryan Gerard", CARD_GERARD),
            ("Nicolai Hojgaard", CARD_NICOLAI),
        ):
            assert _renders(_win_of(body, name)) == _renders(card_value), name

    async def test_the_o_slash_golfer_binds(self, client, mock_db, monkeypatch):
        """The card says "Nicolai Højgaard"; the row says "Nicolai Hojgaard".

        `ø` has no combining-mark decomposition, so a normalizer built on NFD plus
        combining-mark stripping drops this join while looking correct on every
        other name — measured 13 of 15 against the real 15 of 15. The authority
        must key through `_progression_name_key`, which transliterates it.
        """
        _install_card_payload(monkeypatch)
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _win_of(body, "Nicolai Hojgaard") == CARD_NICOLAI
        assert _win_of(body, "Nicolai Hojgaard") != LIVE_BLEND_NICOLAI

    async def test_published_numbers_drive_the_sort(self, client, mock_db, monkeypatch):
        """The table must be ordered by what it prints, not by what it discarded.

        On the live rows Gerard (8.3%) outranks Wallace (5.0%) and so does the card
        (8.5% vs 5.8%), so ordering alone cannot discriminate. This instead hands
        the card an order that INVERTS the live one and asserts the card's order
        wins — otherwise a reader sees rows sorted by numbers that are not on screen.
        """
        inverted = [
            {"name": "Ryan Gerard", "probability": 0.010},
            {"name": "Matt Wallace", "probability": 0.900},
        ]
        _install_card_payload(monkeypatch, _card_payload(inverted))
        _wire_two_source(mock_db)

        body = await _get(client)
        order = _names(body)

        assert order.index("Matt Wallace") < order.index("Ryan Gerard")

    async def test_terminal_state_is_recomputed_from_the_published_number(
        self, client, mock_db, monkeypatch
    ):
        """`clinched` is a claim about the number on screen, not about the blend."""
        clinched = [{"name": "Matt Wallace", "probability": 0.9995}]
        _install_card_payload(monkeypatch, _card_payload(clinched))
        _wire_two_source(mock_db)

        body = await _get(client)

        for p in body["participants"]:
            if p["name"] == "Matt Wallace":
                assert p["status"].get("win") == "clinched"
                break
        else:  # pragma: no cover - the row must exist
            pytest.fail("Matt Wallace is missing from the response")


class TestTheBlastRadius:
    """Everything the card does NOT publish stays live. CONTROLS."""

    async def test_rows_the_card_does_not_carry_stay_live(
        self, client, mock_db, monkeypatch
    ):
        """~25 of the 40 rows have no authority to adopt; they keep the blend."""
        _install_card_payload(monkeypatch)
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _win_of(body, "Unranked Qualifier") == LIVE_BLEND_UNRANKED

    async def test_non_win_stages_stay_live(self, client, mock_db, monkeypatch):
        """The card publishes a winner number and nothing else; Top 5 is untouched."""
        _install_card_payload(monkeypatch)
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _stage_of(body, "Matt Wallace", "top_5") == 0.174813
        assert _stage_of(body, "Ryan Gerard", "top_5") == 0.277458

    async def test_a_card_only_golfer_never_becomes_a_row(
        self, client, mock_db, monkeypatch
    ):
        """#2661's controls: adopting a price must not import a participant.

        The card and the Kalshi market spell some golfers differently enough that
        they never merge ("Eugenio Lopez-Chacarra"). If the authority could create
        rows, the same golfer would render twice at two prices — worse than the bug.
        """
        with_ghost = CARD_GOLFERS + [
            {"name": "Eugenio Lopez-Chacarra", "probability": 0.026},
            {"name": "Angel Ayora Fanegas", "probability": 0.024},
        ]
        _install_card_payload(monkeypatch, _card_payload(with_ghost))
        _wire_two_source(mock_db)

        body = await _get(client)
        names = _names(body)

        assert "Eugenio Lopez-Chacarra" not in names
        assert "Angel Ayora Fanegas" not in names
        assert "Eugenio Chacarra" in names

    async def test_single_source_golfer_is_unchanged(
        self, client, mock_db, monkeypatch
    ):
        """CONTROL (green on master too). Chacarra is priced by one source.

        #2661 names him as a golfer whose two numbers already agree. The card
        carries him at 0.033 and the raw row is 0.033117, which render identically,
        so this pins that the ship does not disturb an already-correct row.
        """
        _install_card_payload(monkeypatch)
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _renders(_win_of(body, "Eugenio Chacarra")) == _renders(CARD_CHACARRA)


class TestItFailsOpen:
    """No card is never an error: the live blend is a good answer, just not the best."""

    async def test_cold_cache_keeps_the_live_blend(self, client, mock_db, monkeypatch):
        _install_card(monkeypatch, None)
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _win_of(body, "Matt Wallace") == LIVE_BLEND_WALLACE

    async def test_redis_outage_keeps_the_live_blend(self, client, mock_db, monkeypatch):
        _install_card(monkeypatch, None, fail=True)
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _win_of(body, "Matt Wallace") == LIVE_BLEND_WALLACE

    async def test_malformed_payload_keeps_the_live_blend(
        self, client, mock_db, monkeypatch
    ):
        _install_card(monkeypatch, b"{not json")
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _win_of(body, "Matt Wallace") == LIVE_BLEND_WALLACE

    async def test_a_different_tournament_is_never_adopted(
        self, client, mock_db, monkeypatch
    ):
        """The card carries every open tournament; only this one's row may apply."""
        _install_card_payload(
            monkeypatch, _card_payload(tournament_name="Biltmore Championship Asheville")
        )
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _win_of(body, "Matt Wallace") == LIVE_BLEND_WALLACE

    async def test_a_nonnumeric_card_price_is_skipped(
        self, client, mock_db, monkeypatch
    ):
        junk = [
            {"name": "Matt Wallace", "probability": None},
            {"name": "Ryan Gerard", "probability": "8.5%"},
            {"name": "Nicolai Højgaard", "probability": CARD_NICOLAI},
        ]
        _install_card_payload(monkeypatch, _card_payload(junk))
        _wire_two_source(mock_db)

        body = await _get(client)

        assert _win_of(body, "Matt Wallace") == LIVE_BLEND_WALLACE
        assert _win_of(body, "Ryan Gerard") == LIVE_BLEND_GERARD
        assert _win_of(body, "Nicolai Hojgaard") == CARD_NICOLAI


class TestOtherSportsAreUntouched:
    """The authority is a golf card; nothing else may pay for it."""

    async def test_a_non_golf_progression_never_reads_the_card(
        self, client, mock_db, monkeypatch
    ):
        reads = _Reads()
        _install_card_payload(monkeypatch, reads=reads)

        nba = _market(
            700100,
            "NBA Championship Winner",
            "KXNBA-26",
            "kalshi",
            [_outcome("Boston Celtics", 0.21), _outcome("Denver Nuggets", 0.18)],
            tier=1,
            sport="basketball",
        )
        mock_db.execute.side_effect = [
            _result_scalar_one_or_none(nba),
            _result_unique_all([]),
            _result_unique_all([]),
            _result_unique_all([]),
        ]

        resp = await client.get("/api/futures/700100/progression?top_n=40")

        assert resp.status_code == 200, resp.text
        assert reads.keys == [], (
            f"a non-golf progression paid for a golf cache read: {reads.keys}"
        )
