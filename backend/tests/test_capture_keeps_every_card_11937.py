"""#11937: the nightly capture keeps every candidate's drawn card, not only the first ten.

Alex opened /grade on the Nov 9 and Nov 10 slates at 8:30 PM PT Nov 10 and found
"most of those cards were empty or incomplete". The deck now deals cards past
the opening ten, but the capture stored the served payload (``card``) only for
positions 1-10. So every deeper card fell back to a box: a grouped card showed
its title and nothing else, a multi-outcome market a bare percent with no name,
a game "100%" with no team (captures on #11937).

What must hold: every candidate a slate stores carries the payload a reader
would be shown. Served cards keep their served payload at every position, and
an unserved candidate keeps the scored item it was ranked from, which is the
same feed-item shape. Nothing else about the slate changes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.ranking_eval import MAX_CANDIDATES, build_slate

NOW = datetime(2026, 11, 10, 15, 15, tzinfo=timezone.utc)


def futures(i, **data):
    return {"type": "futures", "score": 100 - i, "data": {"id": i, "name": f"Market {i}", **data}}


def bundle(slug):
    return {"type": "bundle", "score": 80, "data": {"id": f"roundup:{slug}", "title": slug,
                                                   "rows": [{"label": "A", "rendered_percent": 40}]}}


class TestEveryCandidateCarriesItsCard:
    def test_served_cards_keep_their_payload_past_the_opening_ten(self):
        served = [futures(i) for i in range(1, 30)] + [bundle("cfp-picture")]
        order, cands = build_slate(served, [], now=NOW)
        assert all("card" in c for c in cands)
        assert cands[24]["card"] == futures(25)
        assert cands[29]["card"]["type"] == "bundle"
        assert cands[29]["card"]["data"]["rows"] == [{"label": "A", "rendered_percent": 40}]

    def test_an_unserved_candidate_keeps_the_scored_item_it_was_ranked_from(self):
        order, cands = build_slate([futures(1)], [futures(50, top_outcome="Jon Rahm")], now=NOW)
        assert cands[1]["served_position"] is None
        assert cands[1]["card"] == futures(50, top_outcome="Jon Rahm")

    def test_the_cap_still_holds_with_cards_on(self):
        served = [futures(i) for i in range(1, 400)]
        pool = [futures(i) for i in range(1000, 1300)]
        order, cands = build_slate(served, pool, now=NOW)
        assert len(cands) == MAX_CANDIDATES and all("card" in c for c in cands)
