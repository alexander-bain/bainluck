"""Tests for Morning Digest v1 content selection + rendering (Queue #200)."""

from app.utils.morning_digest import (
    DigestCandidate,
    render_digest_payload,
    select_digest_candidates,
)


def _cand(mid, name, prob, interest, category=None, dedup_key=None, volume=None, leader="Yes"):
    return DigestCandidate(
        market_id=mid,
        name=name,
        leader_name=leader,
        leader_prob=prob,
        interestingness=interest,
        volume_24h=volume,
        category=category,
        dedup_key=dedup_key,
    )


def test_selects_by_interestingness_descending():
    cands = [
        _cand(1, "Low", 0.5, 10.0),
        _cand(2, "High", 0.5, 90.0),
        _cand(3, "Mid", 0.5, 50.0),
    ]
    picked = select_digest_candidates(cands, limit=3)
    assert [c.market_id for c in picked] == [2, 3, 1]


def test_respects_limit():
    cands = [_cand(i, f"Q{i}", 0.5, float(100 - i), dedup_key=f"k{i}") for i in range(20)]
    picked = select_digest_candidates(cands, limit=5)
    assert len(picked) == 5


def test_dedups_by_dedup_key():
    cands = [
        _cand(1, "Dup A", 0.6, 90.0, dedup_key="same"),
        _cand(2, "Dup B", 0.6, 80.0, dedup_key="same"),
        _cand(3, "Other", 0.6, 70.0, dedup_key="other"),
    ]
    picked = select_digest_candidates(cands, limit=5)
    assert [c.market_id for c in picked] == [1, 3]


def test_caps_per_category():
    cands = [
        _cand(1, "P1", 0.6, 99.0, category="politics", dedup_key="p1"),
        _cand(2, "P2", 0.6, 98.0, category="politics", dedup_key="p2"),
        _cand(3, "P3", 0.6, 97.0, category="politics", dedup_key="p3"),
        _cand(4, "E1", 0.6, 50.0, category="economics", dedup_key="e1"),
    ]
    picked = select_digest_candidates(cands, limit=5, max_per_category=2)
    cats = [c.category for c in picked]
    assert cats.count("politics") == 2
    assert "economics" in cats


def test_affinity_boosts_matching_category():
    cands = [
        _cand(1, "Politics", 0.5, 50.0, category="politics", dedup_key="p"),
        _cand(2, "Sports", 0.5, 55.0, category="sports", dedup_key="s"),
    ]
    # Without affinity, sports (55) beats politics (50).
    assert select_digest_candidates(cands, limit=1)[0].market_id == 2
    # With a strong politics affinity, politics wins.
    picked = select_digest_candidates(cands, limit=1, category_affinities={"politics": 0.5})
    assert picked[0].market_id == 1


def test_render_payload_lines_and_deeplink():
    items = [
        _cand(42, "Will the Fed cut rates in September?", 0.64, 80.0, leader="Yes"),
        _cand(7, "Who wins the Best Picture Oscar?", 0.31, 70.0, leader="Some Long Film Title"),
    ]
    payload = render_digest_payload(items)
    assert payload.title
    assert "64%" in payload.body
    assert "31%" in payload.body
    assert payload.body.count("\n") == 1  # two items -> one newline
    # Deep link points at the top item.
    assert payload.data["type"] == "morning_digest"
    assert payload.data["market_id"] == "42"
    assert payload.data["url"] == "/futures/42"
    assert len(payload.items) == 2


def test_render_empty_is_graceful():
    payload = render_digest_payload([])
    assert payload.title
    assert payload.body
    assert payload.data["url"] == "/discover"


def test_probability_clamped_and_rounded():
    items = [_cand(1, "Q", 1.5, 50.0, leader="Yes")]  # out-of-range prob
    payload = render_digest_payload(items)
    assert "100%" in payload.body
