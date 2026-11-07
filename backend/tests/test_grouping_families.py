"""The grouping sentinel's family selector (#12231): pure, no DB, no network.

Each test names the property the weekly count depends on. A family that
changes its key when its members are read in another order would be filed
twice from Nov 26, and a block that silently skips events would undercount
without saying so.
"""

import random
from datetime import datetime, timedelta, timezone

from app.utils import grouping_families as gf
from app.utils.grouping_families import Atom

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
_ids = iter(range(1, 10**6))


def kalshi(ticker, title="t", event_title=None, created=T0):
    return Atom(
        market_id=next(_ids),
        source="kalshi",
        external_id=ticker,
        group_id=f"kalshi:{ticker}",
        title=title,
        event_title=event_title,
        outcome_names=("Yes", "No"),
        created_at=created,
    )


def poly(event_id, event_title, n=1, outcomes=("Yes", "No"), created=T0):
    return [
        Atom(
            market_id=next(_ids),
            source="polymarket",
            external_id=f"0x{event_id}{i}",
            group_id=f"polymarket:{event_id}",
            title=f"{event_title} #{i}",
            event_title=event_title,
            outcome_names=tuple(outcomes),
            created_at=created + timedelta(minutes=i),
        )
        for i in range(n)
    ]


# --- keys --------------------------------------------------------------------
def test_series_code_is_the_ticker_before_its_first_dash():
    assert gf.kalshi_series_code("KXHIGHNY-26NOV07") == "KXHIGHNY"
    assert gf.kalshi_series_code("APPLEUS") == "APPLEUS"
    assert gf.kalshi_series_code("kxmlbgame-26aug26bosmia") == "KXMLBGAME"
    assert gf.kalshi_series_code("") is None
    assert gf.kalshi_series_code(None) is None


def test_kxmlbgame_is_not_kxmlb():
    # The prefix trap `event_series_ticker` documents: a startswith test would
    # put every MLB game into the AL/NL championship futures series.
    a, b = kalshi("KXMLBGAME-26AUG26BOSMIA"), kalshi("KXMLB-26")
    assert gf.primary_key(a) == (gf.KIND_KALSHI_SERIES, "KXMLBGAME")
    assert gf.primary_key(b) == (gf.KIND_KALSHI_SERIES, "KXMLB")


def test_primary_keys_by_venue():
    (p,) = poly(77, "Who will win?")
    assert gf.primary_key(p) == (gf.KIND_POLYMARKET_EVENT, "polymarket:77")
    loose = Atom(1, "polymarket", "0xabc", None, "x", None, ("Yes",), T0)
    assert gf.primary_key(loose) is None
    other = Atom(2, "datagolf", "datagolf:pga:1:win", None, "x", None, ("A",), T0)
    assert gf.primary_key(other) is None


# --- families ----------------------------------------------------------------
def test_a_kalshi_series_is_one_family_across_its_events():
    atoms = [kalshi(f"KXHIGHNY-26NOV0{d}") for d in range(1, 6)] + [kalshi("KXHIGHMIA-26NOV01")]
    fams = {(f.kind, f.key): f for f in gf.build_families(atoms).families}
    assert fams[(gf.KIND_KALSHI_SERIES, "KXHIGHNY")].size == 5
    assert fams[(gf.KIND_KALSHI_SERIES, "KXHIGHMIA")].size == 1


def test_threshold_events_merge_into_one_title_template_family():
    atoms = (
        poly(1, "NHL: Players to Record 80+ Points", n=3, outcomes=("Yes", "No", "Connor McDavid"))
        + poly(2, "NHL: Players to Record 100+ Points", n=2, outcomes=("Yes", "No", "Connor McDavid"))
        + poly(3, "Fed decision in December?", n=4)
    )
    fams = gf.build_families(atoms).families
    template = [f for f in fams if f.kind == gf.KIND_TITLE_TEMPLATE]
    assert len(template) == 1
    assert template[0].key == "nhl players to record {} points"
    assert template[0].size == 5
    assert template[0].event_keys == ("polymarket:1", "polymarket:2")
    # The merged events are no longer families of their own; the unrelated one is.
    keys = {(f.kind, f.key) for f in fams}
    assert (gf.KIND_POLYMARKET_EVENT, "polymarket:1") not in keys
    assert (gf.KIND_POLYMARKET_EVENT, "polymarket:3") in keys


def test_the_key_is_the_words_every_title_shares_so_closure_widens_it():
    atoms = (
        poly(1, "NHL: Players to Record 80+ Points")
        + poly(2, "NHL: Players to Record 100+ Points")
        + poly(3, "NHL: Players to Record 50+ Goals")
    )
    (template,) = [f for f in gf.build_families(atoms).families if f.kind == gf.KIND_TITLE_TEMPLATE]
    assert template.key == "nhl players to record {}"


def test_family_keys_do_not_depend_on_read_order():
    # Fingerprints are kind + key. If the key moved with the order rows were
    # read in, one family would be filed under two fingerprints.
    atoms = (
        poly(1, "NHL: Players to Record 80+ Points", n=2)
        + poly(2, "NHL: Players to Record 100+ Points", n=2)
        + poly(3, "NHL: Players to Record 50+ Goals", n=2)
        + [kalshi(f"KXNHLPTS-{i}") for i in range(3)]
    )
    want = [(f.kind, f.key, f.member_ids) for f in gf.build_families(atoms).families]
    rng = random.Random(12231)
    for _ in range(5):
        shuffled = atoms[:]
        rng.shuffle(shuffled)
        assert [(f.kind, f.key, f.member_ids) for f in gf.build_families(shuffled).families] == want


def test_an_oversized_block_is_narrowed_until_it_can_be_compared():
    # 600 events share their first two words, which is over BLOCK_CAP, so the
    # block is split by the next words (city) and each half is compared.
    atoms = []
    for city in ("nyc", "miami"):
        for d in range(1, 301):
            atoms += poly(f"{city}{d}", f"Highest temperature in {city} on November {d}")
    grouping = gf.build_families(atoms)
    template = [f for f in grouping.families if f.kind == gf.KIND_TITLE_TEMPLATE]
    assert template, "the narrowed blocks must still be compared"
    assert sum(f.size for f in template) == 600
    assert grouping.unblocked_events == 0


def test_a_block_that_cannot_be_narrowed_is_counted_not_dropped():
    # Every title is identical except one word in the middle, and there are
    # more of them than BLOCK_CAP at every depth on every side. They cannot be
    # compared, and the count says so.
    atoms = []
    for i in range(gf.BLOCK_CAP + 50):
        atoms += poly(f"c{i}", f"Will the price of coin{i} close above 100 on Friday")
    grouping = gf.build_families(atoms)
    assert grouping.unblocked_events == gf.BLOCK_CAP + 50
    assert all(f.kind == gf.KIND_POLYMARKET_EVENT for f in grouping.families)


def test_families_are_largest_first():
    atoms = [kalshi(f"KXA-{i}") for i in range(2)] + [kalshi(f"KXB-{i}") for i in range(4)]
    sizes = [f.size for f in gf.build_families(atoms).families]
    assert sizes == sorted(sizes, reverse=True)


# --- the uncovered rule ------------------------------------------------------
def test_one_covered_member_covers_the_family():
    atoms = [kalshi(f"KXSNOW-{i}") for i in range(6)]
    (fam,) = gf.build_families(atoms).families
    ids = set(fam.member_ids)
    assert gf.uncovered_families([fam], covered={min(ids)}, eligible=ids, min_markets=5) == []
    assert gf.uncovered_families([fam], covered=set(), eligible=ids, min_markets=5) == [fam]


def test_only_eligible_members_count_toward_the_threshold():
    atoms = [kalshi(f"KXSNOW-{i}") for i in range(6)]
    (fam,) = gf.build_families(atoms).families
    four = set(sorted(fam.member_ids)[:4])
    assert gf.uncovered_families([fam], covered=set(), eligible=four, min_markets=5) == []


def test_fingerprint_is_kind_plus_key():
    fp = gf.family_fingerprint(gf.KIND_KALSHI_SERIES, "KXHIGHNY")
    assert len(fp) == 12 and all(c in "0123456789abcdef" for c in fp)
    assert fp == gf.family_fingerprint(gf.KIND_KALSHI_SERIES, "KXHIGHNY")
    assert fp != gf.family_fingerprint(gf.KIND_POLYMARKET_EVENT, "KXHIGHNY")


def test_the_key_is_not_the_detectors_last_pair():
    # With the goals ladder read first, the detector's last pair is the two
    # points ladders and its skeleton is "... {} points". The family's key must
    # still be what all three titles share.
    atoms = (
        poly(1, "NHL: Players to Record 50+ Goals")
        + poly(2, "NHL: Players to Record 80+ Points")
        + poly(3, "NHL: Players to Record 100+ Points")
    )
    (template,) = [f for f in gf.build_families(atoms).families if f.kind == gf.KIND_TITLE_TEMPLATE]
    assert template.key == "nhl players to record {}"


def test_events_with_no_event_title_do_not_depend_on_read_order():
    # 99 open Polymarket events (52 with 2+ markets) had no member carrying the
    # event title on Nov 7, so their title, outcome sample and label come from
    # their members. Those must be read in one order whatever order atoms come in.
    def untitled(event_id, titles, outcomes):
        return [
            Atom(next(_ids), "polymarket", f"0x{event_id}{i}", f"polymarket:{event_id}", t, None, tuple(o), T0)
            for i, (t, o) in enumerate(zip(titles, outcomes))
        ]

    many = [(f"Name {c}",) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    atoms = (
        untitled(1, ["NHL: Players to Record 80+ Points", "NHL: Players to Record 90+ Points"], many[:2])
        + untitled(2, ["NHL: Players to Record 100+ Points", "Something else entirely"], many[2:4])
        + untitled(3, [f"Who wins round {i}?" for i in range(26)], many)
    )
    want = [(f.kind, f.key, f.label, f.member_ids) for f in gf.build_families(atoms).families]
    rng = random.Random(1209)
    for _ in range(8):
        shuffled = atoms[:]
        rng.shuffle(shuffled)
        got = [(f.kind, f.key, f.label, f.member_ids) for f in gf.build_families(shuffled).families]
        assert got == want
