"""#6353 — a Discover bundle stops asking "Who wins" about markets nobody wins.

THE DEFECT, read off production 2026-09-15 10:45Z at 390px, Discover page one,
stable at position 18 across three draws of `GET /api/feed?limit=150`:

    chip     🎬 BE EVICTED
    heading  Who wins Be evicted?
    rows     Who will be evicted from Big Brother? (Week 10)      62%
             Will Drew Campbell be evicted in Big Brother s...    18%
             Will Taylor Brown be evicted in Big Brother se...    21%
             Will Rick Devens be evicted in Big Brother sea...    16%

Every row prices who gets THROWN OUT of the house. The heading above them says
"wins", so the 62% beside the name most likely to be evicted reads as the man in
front. The card inverts the polarity of its own contents.

The heading was built by `f"Who wins {label}?"` over `_derive_race_label`, the
longest word run shared by the member names. Two independent faults in one line:

  1. POLARITY / SEMANTICS. `group_id` proves the members are one Polymarket
     event. It does not prove that event is a contest with a winner. Replayed
     over all 48 live entertainment clusters, the template asserted "wins" over
     markets pricing who is EVICTED, who DIES ("Who wins Witcher season 5?"),
     who is merely NOMINATED ("Who wins Best actor?" over an Oscars NOMINATIONS
     market), who PARTICIPATES ("Who wins Eurovision 2027?" over a participants
     market) and who is CAST.
  2. GRAMMAR. The shared run is often a fragment, so the sentence collapsed:
     "Who wins Have a?" (the 24-member Billboard cluster), "Who wins In 2026?",
     "Who wins 1?", "Who wins Mark Ruffalo as Hulk?" — that last one the
     shortest-member fallback firing inside a caller `_derive_race_label`'s own
     docstring had cleared as safe.

THE FIX: read the question instead of deriving it. A Polymarket event stores it
once, on the parent row (`group_type="polymarket_event"`); the children carry
condition hashes and the prices. Measured over the same 48 clusters, that names
exactly one parent in 47 and agrees with the `external_id` anchor on 47/47.

🔴 THE ABSENCE ASSERTIONS ARE THE POINT, and they are two. "Who wins" must not
come back (a test asserting only "the heading is the parent name" passes on a
build that appends the template). And the FOLD must survive a cluster with no
parent — a fix that answered the heading by deleting the bundle would take real
markets off page one, which is the trade #4147 refused.
"""

import pytest

from app.utils.discover_bundles import (
    _award_group_question,
    _make_awards_bundle_item,
    assemble_awards_theme_bundles,
)


def _member(
    market_id: int, name: str, *, parent: bool = False, score: float = 80.0
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "_sort_time": float(market_id),
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "entertainment",
            "group_id": "polymarket:1007243",
            "group_type": "polymarket_event" if parent else "polymarket_sub_market",
            "discover_card": {},
        },
    }


# The four members production folded into position 18, by name and by id.
BIG_BROTHER = [
    _member(60794467, "Who will be evicted from Big Brother? (Week 10)", parent=True, score=80),
    _member(60794469, "Will Drew Campbell be evicted in Big Brother season 28 (Week 10)?", score=72),
    _member(60794471, "Will Taylor Brown be evicted in Big Brother season 28 (Week 10)?", score=70),
    _member(60794473, "Will Rick Devens be evicted in Big Brother season 28 (Week 10)?", score=68),
]


# ── The specimen ─────────────────────────────────────────────────────────────


def test_the_big_brother_card_stops_saying_wins_about_an_eviction():
    bundle = _make_awards_bundle_item("polymarket:1007243", BIG_BROTHER)

    assert (
        bundle["data"]["shared_question"]
        == "Who will be evicted from Big Brother? (Week 10)"
    )
    assert bundle["reason"] == bundle["data"]["shared_question"]
    # The exact served string, gone.
    assert bundle["data"]["shared_question"] != "Who wins Be evicted?"
    assert "who wins" not in bundle["data"]["shared_question"].lower()


def test_the_fold_itself_is_untouched_by_the_question_change():
    """Same members, same slot, same ranking — only the sentence moved."""
    bundle = _make_awards_bundle_item("polymarket:1007243", BIG_BROTHER)

    assert bundle["type"] == "bundle"
    assert bundle["data"]["kind"] == "theme"
    assert bundle["data"]["item_count"] == 4
    assert bundle["data"]["member_ids"] == [60794467, 60794469, 60794471, 60794473]
    assert bundle["score"] == 80


# ── The class, not just the specimen ─────────────────────────────────────────


@pytest.mark.parametrize(
    "parent_name,children",
    [
        # Nobody WINS any of these, and the retired template said somebody did.
        (
            "Who will die in The Witcher: Season 5?",
            ['Will Geralt of Rivia die during "The Witcher: Season 5"?'],
        ),
        (
            "Oscars 2027: Best Actor Nominations",
            ["Will Tom Cruise be nominated for Best Actor at the 99th Academy Awards?"],
        ),
        (
            "Eurovision 2027 Participants",
            ["Will Iceland participate in Eurovision 2027?"],
        ),
        (
            "Who will be cast on Dancing With the Stars: Season 35?",
            ["Will Rob Rausch be cast in Dancing With the Stars: Season 35?"],
        ),
        # The grammar collapses: these derived "Have a", "1", "In 2026".
        (
            "Which artists will have a Billboard #1 song this year?",
            ["Will SZA have a #1 song on the Billboard Hot 100 in 2026?"],
        ),
        (
            "How many views will the #1 Show on Netflix have this week?",
            ["Will the #1 global Netflix show have at least 6 million views this week?"],
        ),
        (
            "Which characters will appear in Avengers: Doomsday?",
            ["Mark Ruffalo as Hulk?", "Tom Holland as Spider-Man?"],
        ),
    ],
)
def test_no_live_cluster_manufactures_a_contest(parent_name: str, children: list[str]):
    members = [_member(1, parent_name, parent=True)] + [
        _member(i + 2, name) for i, name in enumerate(children)
    ]

    bundle = _make_awards_bundle_item("polymarket:test", members)

    assert bundle["data"]["shared_question"] == parent_name
    assert not bundle["data"]["shared_question"].startswith("Who wins ")


# ── Why `group_type` and not `market_type` ───────────────────────────────────


def test_the_parent_is_found_by_group_type_where_market_type_picks_the_child():
    """Production `polymarket:996607`, the cluster that refutes `market_type`.

    The parent is `unshaped` and its own child is `field`, so a parent test
    keyed on `market_type != container_member` selects the CHILD's name and the
    heading becomes a single nominee's binary. `group_type` records which row
    carries the Polymarket EVENT id, which is the question we want.
    """
    parent = _member(60640235, "How many views will the #1 Show on Netflix have this week?", parent=True)
    parent["data"]["market_type"] = "unshaped"
    child = _member(60640236, "Will the #1 global Netflix show have at least 6 million views this week?")
    child["data"]["market_type"] = "field"

    assert _award_group_question([parent, child]) == parent["data"]["name"]
    assert _award_group_question([child, parent]) == parent["data"]["name"]


# ── The no-parent tail: no question, but the bundle still folds ──────────────


def test_a_cluster_with_no_parent_row_folds_with_no_question():
    """Production `polymarket:90177` — both rows are sub-markets.

    Both bundle cards render the member count when `shared_question` is absent,
    which #4147 ruled is the honest answer. What must NOT happen is the members
    vanishing.
    """
    orphans = [
        _member(13792362, "Will the US confirm that aliens exist before 2027?", score=90),
        _member(13792366, "Will the US confirm that aliens exist by September 30?", score=80),
    ]

    assert _award_group_question(orphans) is None

    bundle = _make_awards_bundle_item("polymarket:90177", orphans)
    assert bundle["data"]["shared_question"] is None
    assert bundle["data"]["item_count"] == 2
    assert bundle["data"]["member_ids"] == [13792362, 13792366]
    assert bundle["data"]["debug_bundles"]["question_source"] == "none"


def test_two_parent_rows_state_no_question_rather_than_guessing():
    ambiguous = [
        _member(1, "First authored question?", parent=True),
        _member(2, "Second authored question?", parent=True),
    ]

    assert _award_group_question(ambiguous) is None


def test_a_blank_parent_name_is_not_a_question():
    members = [_member(1, "   ", parent=True), _member(2, "Will A happen?")]

    assert _award_group_question(members) is None


# ── End to end, through the assembler ────────────────────────────────────────


def test_end_to_end_the_served_bundle_carries_the_venue_question():
    survivor = dict(BIG_BROTHER[0])
    survivor["_grouped_members"] = BIG_BROTHER[1:]

    out = assemble_awards_theme_bundles([survivor])

    assert [item["type"] for item in out] == ["bundle"]
    bundle = out[0]
    assert (
        bundle["data"]["shared_question"]
        == "Who will be evicted from Big Brother? (Week 10)"
    )
    assert bundle["data"]["debug_bundles"]["question_source"] == "venue_parent"
    # No member lost to the fix.
    assert bundle["data"]["item_count"] == 4


def test_end_to_end_a_parentless_cluster_keeps_all_of_its_markets():
    survivor = _member(13792362, "Will the US confirm that aliens exist before 2027?", score=90)
    survivor["_grouped_members"] = [
        _member(13792366, "Will the US confirm that aliens exist by September 30?", score=80)
    ]

    out = assemble_awards_theme_bundles([survivor])
    served_ids = {
        member["data"]["id"]
        for item in out
        if item["type"] == "bundle"
        for member in item["data"]["items"]
    }

    assert served_ids == {13792362, 13792366}
