"""#10090: a live price frame's `source_snapshot` (the row's complete sources).

The refresher builds it from the bag its stamp UPDATE RETURNED, the bag that
also computed the frame's `p`, and copies the frame's own singleton `rev`.
These cases cover the public shape, the identity guard, the empty and
priceless maps, strict JSON, encoded overhead, and that a folded page never
receives a row's map. The real stamp, commit, rollback and cancel run in
`tests/integration/test_live_blend_source_snapshot_10090_pg.py`.
"""

import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.config.win_prob_sources import WIN_PROB_SOURCES
from app.utils.live_push import build_frame, build_source_snapshot
from app.utils.price_evidence import NOT_EVALUATED, TRADEABLE_BOOK, UNPROVEN
from app.utils.probability_eligibility import (
    MarketRef,
    ineligible_record,
    verified_record,
)
from app.utils.probability_source_format import format_probability_sources

STAMP = "2026-10-19T09:00:00+00:00"


def bag():
    return {
        "polymarket": {
            "value": 0.61, "updated_at": STAMP,
            "eligibility": verified_record(rule="t", market_id=7).to_entry(),
        },
        "kalshi": {"value": 0.58, "updated_at": STAMP},
        "betting": 0.6,
        "betting_book_count": 9,
        "_internal": {"x": 1},
        "statpal_injuries": [{"player": "x"}],
    }


def expected_map(sources):
    public = format_probability_sources(sources)
    if "polymarket" in public:
        public["polymarket"]["price_evidence"] = NOT_EVALUATED
    return public


def frame(event_id=7, rev=41, sources=None, p=0.6):
    out = build_frame(
        event_id=event_id, probability=p, source="polymarket",
        source_value=0.61, updated_at=STAMP, status="live", rev=rev,
    )
    snapshot = build_source_snapshot(
        event_id, out["rev"], bag() if sources is None else sources,
    )
    if snapshot is not None:
        out["source_snapshot"] = snapshot
    return out


def test_snapshot_is_the_public_map_of_the_same_bag_under_the_frames_revision():
    out = frame()
    assert out["source_snapshot"] == {
        "event_id": 7,
        "rev": {"7": 41},
        "win_probability_sources": expected_map(bag()),
    }
    # Not shared with the frame: a reader mutating one cannot move the other.
    assert out["source_snapshot"]["rev"] is not out["rev"]
    # The legacy fields are exactly build_frame's.
    legacy = {k: v for k, v in out.items() if k != "source_snapshot"}
    assert legacy == build_frame(
        event_id=7, probability=0.6, source="polymarket", source_value=0.61,
        updated_at=STAMP, status="live", rev=41,
    )
    sources = out["source_snapshot"]["win_probability_sources"]
    # Non-source shapes are dropped exactly as on detail; the count stays.
    assert set(sources) == {"polymarket", "kalshi", "betting", "betting_book_count"}
    assert sources["kalshi"]["updated_at"] == STAMP


def test_polymarket_price_evidence_is_explicitly_not_evaluated():
    sources = frame()["source_snapshot"]["win_probability_sources"]
    assert sources["polymarket"]["price_evidence"] == NOT_EVALUATED
    # Never a positive claim, and distinct from "read and refused".
    assert NOT_EVALUATED not in (TRADEABLE_BOOK, UNPROVEN)
    # Detail stamps the field on Polymarket only; so does the snapshot.
    assert all(
        "price_evidence" not in entry
        for key, entry in sources.items() if key != "polymarket"
    )


@pytest.mark.parametrize("rev", [
    None, {}, {"8": 41}, {"7": 41, "8": 3}, {"7": True}, {"7": -1},
    {"7": "41"}, {"7": 41.0}, [41], 41,
])
def test_no_snapshot_without_this_rows_exact_singleton_revision(rev):
    assert build_source_snapshot(7, rev, bag()) is None


@pytest.mark.parametrize("sources", [None, [], "polymarket", 0.6])
def test_no_snapshot_from_a_bag_that_is_not_a_dict(sources):
    assert build_source_snapshot(7, {"7": 41}, sources) is None


def test_build_frame_without_revision_carries_no_snapshot():
    out = frame(rev=None)
    assert out["rev"] is None and "source_snapshot" not in out


@pytest.mark.parametrize("sources", [
    {},
    {"_internal": {"x": 1}, "statpal_injuries_updated": STAMP},
    {"polymarket": {
        "value": 0.5, "updated_at": STAMP,
        "eligibility": ineligible_record(rule="t").to_entry(),
    }},
])
def test_empty_and_priceless_bags_are_complete_empty_maps(sources):
    out = frame(sources=sources, p=None)
    # A present, complete, empty map: not absence, and it adds no number,
    # clock or source of its own.
    assert out["source_snapshot"] == {
        "event_id": 7, "rev": {"7": 41}, "win_probability_sources": {},
    }
    assert out["p"] is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_map_that_is_not_strict_json_omits_the_snapshot_not_the_frame(bad):
    sources = bag()
    sources["kalshi"] = {"value": bad, "updated_at": STAMP}
    out = frame(sources=sources)
    assert "source_snapshot" not in out
    assert out["p"] == 0.6 and out["rev"] == {"7": 41}


def test_a_formatter_failure_omits_the_snapshot_and_never_raises(monkeypatch):
    from app.utils import probability_source_format

    def broken(_):
        raise RuntimeError("formatter defect")

    monkeypatch.setattr(probability_source_format, "format_probability_sources", broken)
    assert build_source_snapshot(7, {"7": 41}, bag()) is None


def test_encoded_overhead_is_bounded_for_the_whole_source_catalog():
    contributors = (MarketRef(market_id=1), MarketRef(market_id=2))
    full = {
        key: {
            "value": 0.123456789, "updated_at": STAMP,
            "eligibility": verified_record(
                rule="full_event_winner#5311", market_id=1,
                source_market_id="x" * 66, contributors=contributors,
            ).to_entry(),
        }
        for key in WIN_PROB_SOURCES
    }
    full["betting_book_count"] = 14
    out = frame(sources=full)
    assert len(out["source_snapshot"]["win_probability_sources"]) == len(WIN_PROB_SOURCES) + 1
    legacy = {k: v for k, v in out.items() if k != "source_snapshot"}
    overhead = len(json.dumps(out).encode()) - len(json.dumps(legacy).encode())
    # One public map, bounded by the source catalog: measured 2,376 bytes for
    # these 9 entries (~264 each with eligibility fields). Per frame, synthetic,
    # and not a production payload measurement.
    assert overhead <= 320 * (len(WIN_PROB_SOURCES) + 1), overhead


def test_refresher_counts_an_omitted_snapshot():
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    assert LiveBlendRefresher("polymarket").stats["source_snapshot_omitted"] == 0


def own_frame(event_id=1, rev=11):
    return frame(event_id=event_id, rev=rev) | {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _next_payload(stream):
    chunk = await asyncio.wait_for(anext(stream), 1)
    return chunk, json.loads(chunk.split("data: ")[1])


@pytest.mark.asyncio
async def test_singleton_page_receives_the_row_snapshot_unchanged(monkeypatch):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    stream = route._stream(1, Request(), [1])
    try:
        await anext(stream)
        await anext(stream)
        sent = own_frame()
        hub.subscriptions["live:event:1"].offer(json.dumps(sent))
        _, payload = await _next_payload(stream)
        assert payload == sent and "source_snapshot" in payload
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_folded_page_never_receives_a_row_snapshot(monkeypatch):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests._event_stream_legacy_view import install_legacy_view
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    # #10090: predates the stream's owned coverage read and asserts chunk
    # position, so reconcile controls are dropped too; see
    # tests/_event_stream_legacy_view.py.
    install_legacy_view(monkeypatch, drop_reconcile=True)

    hub, projected = Hub(), []
    quote = {"event_id": 1, "blend_fold_revision": {"1": 11, "2": 22},
             "win_probability_sources": {"espn": {"value": 0.2}}}

    async def project(event_id, incoming):
        projected.append(incoming)
        return quote

    hub.project_folded_quote = project
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    stream = route._stream(1, Request(), [1, 2])
    try:
        await anext(stream)
        await anext(stream)
        # The page's own row moved: raw frame, then the fold's authority.
        sent = own_frame(1, 11)
        hub.subscriptions["live:event:1"].offer(json.dumps(sent))
        chunk, raw = await _next_payload(stream)
        assert chunk.startswith("event: probability\n")
        stripped = {k: v for k, v in sent.items() if k != "source_snapshot"}
        assert raw == {**stripped, "folded_quote_pending": True}
        chunk, enriched = await _next_payload(stream)
        assert chunk.startswith("event: folded_probability\n")
        assert "source_snapshot" not in enriched
        assert enriched == {**stripped, "folded_quote_pending": False,
                            "folded_quote": quote}
        # The projection still keys on the frame it was given.
        assert projected == [sent]
        # A sibling's frame becomes an invalidation with no map at all.
        sibling = own_frame(2, 22)
        hub.subscriptions["live:event:2"].offer(json.dumps(sibling))
        _, raw = await _next_payload(stream)
        assert raw["invalidation"] is True and "source_snapshot" not in raw
        _, enriched = await _next_payload(stream)
        assert "source_snapshot" not in enriched
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_folded_page_replay_never_receives_a_row_snapshot(monkeypatch):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    hub = Hub()
    retained = own_frame(1, 11)

    async def latest(ids):
        return [(1, json.dumps(retained))] if 1 in ids else []

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", latest)
    stream = route._stream(1, Request(), [1, 2])
    try:
        await anext(stream)
        await anext(stream)
        chunk, floor = await _next_payload(stream)
        assert chunk.startswith("event: fold_preview_floor\n")
        assert floor == {"event_id": 1, "floor": {"1": 11}}
        _, raw = await _next_payload(stream)
        assert raw["rev"] == {"1": 11} and "source_snapshot" not in raw
    finally:
        await stream.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("returned_rev,snapshot_rev", [
    (None, None), (True, None), ("42", None), (42, {"1": 42}),
])
async def test_the_real_batch_publishes_the_legacy_frame_when_the_writer_has_no_revision(
    monkeypatch, returned_rev, snapshot_rev,
):
    """Speed's composed check, 2026-10-19: on the writer compatibility path the
    stamp RETURNS a bag but no revision (the fixture behind
    `test_the_real_batch_reports_the_lock`). An optional snapshot that read the
    missing revision as a dict threw there and the frame was never published.

    No exact singleton revision means no snapshot and the unchanged legacy
    frame: the same keys build_frame always sent, published, counted. The
    integer arm is the control: the same batch with a real revision carries it.
    """
    from tests.test_live_blend_refresh import (
        _event_and_market, _one_event_refresher, _RecordingSession,
    )

    event, market = _event_and_market()
    session = _RecordingSession([(market, event)], [], {
        "polymarket": {"value": 0.9, "updated_at": STAMP},
    })
    session.returned_rev = returned_rev
    r, published = _one_event_refresher(monkeypatch, session)
    await r.refresh([1])

    assert r.stats["stamped"] == 1 and r.stats["errors"] == 0
    (out,) = published
    legacy = set(frame(rev=None))
    if snapshot_rev is None:
        assert set(out) == legacy and out["rev"] is None, out
        assert r.stats["source_snapshot_omitted"] == 1
    else:
        assert set(out) == legacy | {"source_snapshot"}, out
        assert out["rev"] == out["source_snapshot"]["rev"] == snapshot_rev
        assert r.stats["source_snapshot_omitted"] == 0
    assert out["p"] == 0.9 and out["event_id"] == 1
