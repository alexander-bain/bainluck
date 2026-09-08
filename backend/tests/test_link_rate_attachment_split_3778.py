"""#3778: the published link rate must say what markets are attached TO.

`GET /api/admin/prediction-markets/link-rate` is named in CLAUDE.md as the
canonical link-rate surface, is hourly-cached, and is quoted as health. Its
`linked` counter is `futures_markets.event_id IS NOT NULL` and nothing else --
the query never touched the `events` table at all. So a market attached to an
event row its OWN ingest minted counts exactly like one attached to a row ESPN
anchored, a twin-generating ingest and a healthy one publish the same number,
and the metric CANNOT FALL.

Measured read-only on production 2026-09-07, open markets whose events commence
in the last 14 days: kalshi **27.3% self-minted** (309/1,130), polymarket
**78.7%** (9,184/11,670) -- while the bus's Kalshi ATP/WTA attach receipt read
`244/244 (100%), flat` and the US Open men's semi-final page rendered with no
Kalshi curve at all.

These tests drive `_compute_link_rate` itself, not just the classifier, because
the defect being fixed was never in a predicate -- it was in what the query
selected and what the loop counted. The rows are supplied directly, so no
database is required.

`self_minted` IS NOT A DUPLICATE COUNT. See `_classify_attachment`'s docstring
and `test_self_minted_is_not_reported_as_a_duplicate_count` in
test_admin_matching_link_rate.py; the twin question is #3582's and #2693's.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.routes.admin_matching import _compute_link_rate


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Hands back one queued result per `execute`, in call order.

    `_compute_link_rate` issues exactly two data queries -- Kalshi then
    Polymarket -- when `stmt_timeout_s=None` skips the `SET LOCAL` statement.
    If that ever stops being true this raises rather than silently reusing a
    result, so the test cannot quietly start measuring the wrong query.
    """

    def __init__(self, *results):
        self._queue = list(results)
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        if not self._queue:
            raise AssertionError(
                f"_compute_link_rate issued {self.calls} queries; this fixture "
                "supplies two. The shape of the function changed -- update the "
                "fixture rather than the assertion."
            )
        return _Result(self._queue.pop(0))


def _market(event_id, espn_id, event_external_id, *, status="open", name=None):
    """One selected row, with the columns both loops actually read."""
    return SimpleNamespace(
        sport="basketball",
        league="NBA",
        event_id=event_id,
        status=status,
        external_id="KXNBAGAME-26MAY18BOSNYK",
        category="game",
        name=name or "Celtics vs Knicks",
        event_espn_id=espn_id,
        event_external_id=event_external_id,
    )


def _run(kalshi_rows, poly_rows):
    session = _FakeSession(kalshi_rows, poly_rows)
    payload = asyncio.run(_compute_link_rate(session, stmt_timeout_s=None))
    assert session.calls == 2
    return payload


#: The real US Open men's semi-final pair from #3778, and the reason the split
#: exists: ghost 15304989 carried the two Kalshi markets and has no espn_id,
#: while 15305016 is the same match, ESPN-anchored, where the curve should be.
GHOST = _market(15304989, None, None)
ANCHORED = _market(15305016, "182722", None)

#: An unlinked market, deliberately NOT `status="open"`.
#:
#: `_should_exclude_stale_open_unlinked_game_market` drops an OPEN, unlinked
#: Kalshi market whose ticker date is long past -- and the shared fixture
#: ticker's date is. An open unlinked row here would be removed from the
#: denominator entirely, so a test asserting "it lands in neither bucket" would
#: pass because the row was never counted at all: green for the wrong reason.
#: Settled keeps it in the denominator, which is what these tests need to see.
UNLINKED = _market(None, None, None, status="settled")


def test_the_split_partitions_linked_exactly():
    """`linked_anchored + linked_self_minted == linked`, per source.

    The invariant that makes the two new numbers safe to publish beside the
    old one: nothing is double counted and nothing falls between them.
    """
    payload = _run([GHOST, ANCHORED, UNLINKED], [])
    totals = payload["kalshi"]["totals"]
    assert totals["linked"] == 2
    assert totals["linked_anchored"] == 1
    assert totals["linked_self_minted"] == 1
    assert totals["linked_anchored"] + totals["linked_self_minted"] == totals["linked"]


def test_the_old_numbers_are_unchanged_by_the_split():
    """`linked` still means `event_id IS NOT NULL`.

    The split is additive. A caller reading `link_rate_all_pct` -- CLAUDE.md
    quotes this endpoint as health -- must see exactly what it saw before, or
    this becomes a silent redefinition rather than a disclosure.
    """
    payload = _run([GHOST, ANCHORED, UNLINKED], [])
    totals = payload["kalshi"]["totals"]
    assert totals["total"] == 3
    assert totals["linked"] == 2
    assert totals["link_rate_all_pct"] == round(2 / 3 * 100, 1)


def test_the_flattering_number_and_the_honest_one_disagree_on_the_real_pair():
    """The whole point, stated as a comparison.

    On the recorded semi-final pair the old rate reports a perfect 100% and
    the new one reports 50%. If these two ever agree on this fixture the
    split has stopped measuring anything.
    """
    payload = _run([GHOST, ANCHORED], [])
    totals = payload["kalshi"]["totals"]
    assert totals["link_rate_all_pct"] == 100.0
    assert totals["anchored_rate_all_pct"] == 50.0
    assert totals["anchored_rate_pct"] == 50.0


def test_an_unlinked_market_is_counted_in_neither_bucket():
    payload = _run([UNLINKED], [])
    totals = payload["kalshi"]["totals"]
    # Present in the denominator -- otherwise the assertions below would hold
    # of a row that was filtered out before the split ever saw it.
    assert totals["total"] == 1
    assert totals["linked"] == 0
    assert totals["linked_anchored"] == 0
    assert totals["linked_self_minted"] == 0
    assert totals["anchored_rate_all_pct"] == 0


def test_a_provider_anchored_row_counts_as_anchored():
    payload = _run([_market(15305016, None, "odds_api:abc123")], [])
    assert payload["kalshi"]["totals"]["linked_anchored"] == 1
    assert payload["kalshi"]["totals"]["linked_self_minted"] == 0


def test_polymarket_is_split_on_the_same_terms():
    """Both loops, because both were blind and Polymarket's share is the larger.

    Polymarket rows must survive `_is_polymarket_matcher_game_level`, so the
    name carries a real 'vs'.
    """
    poly_ghost = _market(15304989, None, None, name="Celtics vs Knicks")
    poly_anchored = _market(15305016, "182722", None, name="Celtics vs Knicks")
    payload = _run([], [poly_ghost, poly_anchored])
    totals = payload["polymarket"]["totals"]
    assert totals["linked"] == 2
    assert totals["linked_anchored"] == 1
    assert totals["linked_self_minted"] == 1


def test_the_open_split_tracks_status():
    """The headline rate is the OPEN one, so the open split must be separate.

    A settled self-minted market is real history; an OPEN one is a market a
    reader can be looking at right now on a page with no curve.
    """
    payload = _run(
        [
            _market(15304989, None, None, status="open"),
            _market(15304990, None, None, status="settled"),
            _market(15305016, "182722", None, status="open"),
        ],
        [],
    )
    totals = payload["kalshi"]["totals"]
    assert totals["linked_self_minted"] == 2
    assert totals["open_linked_self_minted"] == 1
    assert totals["open_linked_anchored"] == 1
    assert (
        totals["open_linked_anchored"] + totals["open_linked_self_minted"]
        == totals["open_linked"]
    )


def test_the_split_is_non_vacuous_end_to_end():
    """#3778 acceptance item 3, at the level that can actually go wrong.

    The classifier can be correct while the QUERY feeds it a column that is
    always NULL -- which is precisely the pre-fix state, where the select
    never joined `events`. Then every linked market reads self_minted and the
    all-anchored direction never fires. Both buckets must be occupied by a
    run of the real function.
    """
    payload = _run([GHOST, ANCHORED], [GHOST, ANCHORED])
    for source in ("kalshi", "polymarket"):
        totals = payload[source]["totals"]
        assert totals["linked_anchored"] >= 1, f"{source}: no anchored row"
        assert totals["linked_self_minted"] >= 1, f"{source}: no self_minted row"


def test_per_sport_rows_carry_the_split_too():
    """The by_sport breakdown is what a reader drills into; a split that
    existed only in the totals would send them back to the flat number."""
    payload = _run([GHOST, ANCHORED], [])
    (bucket,) = payload["kalshi"]["by_sport"]
    assert bucket["linked_anchored"] == 1
    assert bucket["linked_self_minted"] == 1


@pytest.mark.parametrize("blank", ["", None])
def test_a_blank_id_does_not_anchor_a_row(blank):
    """An empty string is an absence wearing a value; anchoring on it would
    re-flatter the number this split exists to deflate."""
    payload = _run([_market(15304989, blank, blank)], [])
    assert payload["kalshi"]["totals"]["linked_self_minted"] == 1
    assert payload["kalshi"]["totals"]["linked_anchored"] == 0
