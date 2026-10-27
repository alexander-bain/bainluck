"""Preserve the recovered supersession policy without quadratic roster work."""

from itertools import permutations

from app.utils import prop_families as pf
from app.utils.venue_identity import kalshi_supersedes, venue_identity


def row(source, event, settled=True):
    return {"_vid": venue_identity(source, event), "settled": settled}


def test_indexed_supersession_matches_recovered_predicate_and_preserves_input():
    rows = [
        row("kalshi", "kalshi:KXNBAWFINMVP-26"),
        row("kalshi", "kalshi:KXNBAWFINMVP-27", False),
        row("kalshi", "kalshi:KXNBAEFINMVP-26"),
        row("kalshi", "kalshi:KXNEXTTEAMNFL-26JCHASE"),
        row("kalshi", "kalshi:KXNEXTTEAMNFL-27JBURROW", False),
        row("kalshi", "kalshi:KXGRAMAOTY-69"),
        row("kalshi", "kalshi:KXGRAMAOTY-70", False),
        row("polymarket", "polymarket:KXNBAWFINMVP-27"),
        row("kalshi", "polymarket:KXNBAWFINMVP-26"),
        row("kalshi", None),
    ]
    before = [dict(r) for r in rows]
    # The original candidate's all-pairs predicate is the semantic reference.
    expected = [
        r
        for r in rows
        if not (
            r["settled"] and any(kalshi_supersedes(x["_vid"], r["_vid"]) for x in rows)
        )
    ]
    assert pf._drop_superseded_editions(rows) == expected == rows[1:]
    assert rows == before
    for ordered in permutations(rows[:3]):
        assert pf._drop_superseded_editions(list(ordered)) == [
            r for r in ordered if r is not rows[0]
        ]


def test_large_roster_does_not_compare_every_outcome_to_every_outcome(monkeypatch):
    # With older rows first, the old all-pairs scan repeatedly traversed them
    # before finding the later event. A wall-clock deadline would be noisy;
    # a predicate-call budget detects that cost regardless of host speed.
    rows = [row("kalshi", "kalshi:KXNBAWFINMVP-26") for _ in range(2000)]
    current = row("kalshi", "kalshi:KXNBAWFINMVP-27", False)
    rows.append(current)
    calls = 0

    def counted(later, earlier):
        nonlocal calls
        calls += 1
        return kalshi_supersedes(later, earlier)

    monkeypatch.setattr(pf, "kalshi_supersedes", counted)
    assert pf._drop_superseded_editions(rows) == [current]
    assert calls <= 3 * len(rows)
