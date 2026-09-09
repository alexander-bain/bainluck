"""#4153 — one Polymarket container group is ONE card, not one card per member.

Alex, shopping /sports on 2026-09-08: the "Player Props & Projections" strip is
"a wall of the same sentence with the names swapped" — twelve cards that were
four questions. Measured on the served pool the same night: 84 of the 100
candidate rows are ``container_member`` legs of just 18 questions.

His acceptance, verbatim from the issue: *"assert no `group_id` appears on more
than one card in `feed`."* `test_no_group_id_appears_on_more_than_one_card` is
that sentence; everything else here guards the ways a fold could be wrong
instead of absent — a partial field, a fabricated title, a bad split, or a card
that links somewhere the numbers are not.
"""

import pytest

from app.utils.market_grouping import (
    CONTAINER_FOLD_MIN_SHARED_AFFIX_CHARS,
    detect_container_field_groups,
    extract_container_member_entities,
)


def _member(market_id: int, name: str, probability, source="polymarket"):
    return {
        "id": market_id,
        "name": name,
        "source": source,
        "probability": probability,
    }


def _us_open_final_members():
    """The real shape, from production group ``polymarket:910235``."""
    template = "Will {} advance to the Final in Women's Singles at the 2026 US Open?"
    return [
        _member(1, template.format("Belinda Bencic"), 0.833),
        _member(2, template.format("Maria Sakkari"), 0.480),
        _member(3, template.format("Coco Gauff"), 0.425),
        _member(4, template.format("Elena Rybakina"), 0.385),
        _member(5, template.format("Iga Swiatek"), 0.230),
    ]


PARENT = {"polymarket:910235": "US Open 2026: To Reach the Final (Women's Singles)"}


# ── the entity split ──


def test_entities_are_the_swapped_slot_and_nothing_else():
    names = [m["name"] for m in _us_open_final_members()]
    assert extract_container_member_entities(names) == [
        "Belinda Bencic",
        "Maria Sakkari",
        "Coco Gauff",
        "Elena Rybakina",
        "Iga Swiatek",
    ]


def test_a_shared_first_name_does_not_get_sliced_mid_word():
    """The common prefix runs into the entity; it must back off to a space.

    Without the word-boundary snap the shared run is "Will Em", and the card
    would print rows reading "ma Navarro" and "ily Appleton".
    """
    template = "Will {} advance to the Final in Women's Singles at the 2026 US Open?"
    names = [template.format("Emma Navarro"), template.format("Emily Appleton")]
    assert extract_container_member_entities(names) == [
        "Emma Navarro",
        "Emily Appleton",
    ]


def test_two_members_reducing_to_the_same_label_refuse_the_whole_split():
    """One row per player or no card: a duplicate label hides a real member."""
    names = [
        "Will Coco Gauff advance to the Final?",
        "Will Coco Gauff advance to the Final?",
    ]
    assert extract_container_member_entities(names) is None


def test_members_sharing_almost_no_wording_are_not_one_question():
    """The grab-bag case — three different questions about one game.

    Production ``polymarket:13338`` is exactly this: "Will the Dodgers beat the
    Padres?", "Will the Dodgers and Padres combine for 8 or more runs?" and
    "Will there be at least 1 run scored in the first inning?". Folding those
    under one title would be a lie, so the split has to refuse them.
    """
    names = [
        "Will the Dodgers beat the Padres?",
        "Will there be at least 1 run scored in the first inning?",
    ]
    entities = extract_container_member_entities(names)
    if entities is not None:  # pragma: no cover - documents the bound
        shared = len("Will ") + len("?")
        assert (
            shared >= CONTAINER_FOLD_MIN_SHARED_AFFIX_CHARS
        ), "a fold this loose would put unrelated questions under one title"
        pytest.fail(f"expected refusal, got {entities}")


def test_a_single_member_is_not_a_field():
    assert extract_container_member_entities(["Will Coco Gauff advance?"]) is None


# ── the coincidence case: a shared WORD is not a shared TEMPLATE ──
#
# Both specimens below are real, and both have a `market_type='field'` parent, so
# the parent gate does not stop them — a two-player MATCH is a `field` too, and
# its group carries the match's side-markets. Found by running the splitter over
# the whole open tennis population rather than over one night's pool; the first
# sha of this ship (`bd0ea14f`, CERT-2322) would have rendered these.


def test_two_questions_ending_on_the_same_surname_do_not_fold():
    """polymarket:945776 — parent "US Open WTA: Marta Kostyuk vs Sloane Stephens".

    The shared run is " Stephens": 9 characters, past
    `CONTAINER_FOLD_MIN_SHARED_AFFIX_CHARS`. Splitting on it yields the row labels
    "Set 2 Winner: Kostyuk vs" and "US Open WTA: Marta Kostyuk vs Sloane", which
    is worse on a screen than the repetition this ship removes.
    """
    names = [
        "Set 2 Winner: Kostyuk vs Stephens",
        "US Open WTA: Marta Kostyuk vs Sloane Stephens",
    ]
    assert extract_container_member_entities(names) is None


def test_the_same_coincidence_in_the_mens_draw_does_not_fold():
    """polymarket:956563 — parent "US Open ATP: Daniil Medvedev vs Arthur Rinderknech"."""
    names = [
        "Set 3 Winner: Medvedev vs Rinderknech",
        "US Open ATP: Daniil Medvedev vs Arthur Rinderknech",
    ]
    assert extract_container_member_entities(names) is None


@pytest.mark.parametrize(
    "group_id,names",
    [
        # What varies is the question, not the player.
        (
            "polymarket:968290",
            [
                "US Open WTA (Doubles): Bouzkova/Sorribes Tormo vs Danilina/Khromacheva",
                "Set 1 Winner: Bouzkova/Sorribes Tormo vs Danilina/Khromacheva",
            ],
        ),
        (
            "polymarket:982930",
            [
                "Sintra, Qualifying: Completed Match: Rocha vs Faria",
                "Sintra: Rocha vs Faria",
            ],
        ),
        # Two handicap lines on one match — the differing span is a fixture.
        (
            "polymarket:987752",
            [
                "Set Handicap: Topo (-1.5) vs Sachko: M15 Sharm",
                "Set Handicap: Sachko (-1.5) vs Topo: M15 Sharm",
            ],
        ),
    ],
)
def test_a_differing_span_that_is_a_question_or_a_fixture_does_not_fold(
    group_id, names
):
    """These three survived the template-length rule on production 2026-09-08.

    Each shares a long run of wording — the players — while what actually varies
    between the members is the QUESTION. Splitting on the shared run inverts the
    card: the title would be one member's question and the rows would be the
    other questions.
    """
    assert extract_container_member_entities(names) is None, group_id


def test_a_digit_in_a_name_is_not_by_itself_a_refusal():
    """Schalke 04 is an entity. The shape test bans `:`/brackets/`vs`, not digits."""
    template = "Will {} win the Bundesliga in 2026-27?"
    assert extract_container_member_entities(
        [template.format("Schalke 04"), template.format("Bayern Munich")]
    ) == ["Schalke 04", "Bayern Munich"]


def test_the_real_fields_still_fold_under_the_template_rule():
    """The controls. The rule must cost a genuine field nothing.

    The US Open family shares 62 characters around a 14-character name; the
    Ballon d'Or family shares 49 around 17. Both clear it with room.
    """
    us_open = [m["name"] for m in _us_open_final_members()]
    assert extract_container_member_entities(us_open) is not None

    ballon = "Will {} finish in the top 5 of the 2026 Ballon d'Or?"
    assert extract_container_member_entities(
        [ballon.format("Cristiano Ronaldo"), ballon.format("Rodri")]
    ) == ["Cristiano Ronaldo", "Rodri"]

    # The tightest real family seen: a short template around a short slot.
    assert extract_container_member_entities(
        ["Will Alcaraz win the title?", "Will Sinner win the title?"]
    ) == ["Alcaraz", "Sinner"]


# ── the fold ──


def test_the_wall_becomes_one_card_ranked_leader_first():
    folds = detect_container_field_groups(
        {"polymarket:910235": _us_open_final_members()}, PARENT
    )
    assert list(folds) == ["polymarket:910235"]
    fold = folds["polymarket:910235"]
    assert fold["title"] == "US Open 2026: To Reach the Final (Women's Singles)"
    assert [e["name"] for e in fold["entries"]] == [
        "Belinda Bencic",
        "Maria Sakkari",
        "Coco Gauff",
        "Elena Rybakina",
        "Iga Swiatek",
    ]
    assert fold["entries"][0]["probability"] == pytest.approx(0.833)


def test_the_leader_is_first_even_when_the_query_returns_her_last():
    """#2789's failure, rebuilt: the card must not lead with a 0.09% row.

    ``FuturesMarket.outcomes`` declares no ordering and neither does the
    membership query, so the leader arriving last is the normal case, not a
    contrived one.
    """
    members = list(reversed(_us_open_final_members()))
    fold = detect_container_field_groups({"polymarket:910235": members}, PARENT)[
        "polymarket:910235"
    ]
    assert fold["entries"][0]["name"] == "Belinda Bencic"


def test_ties_break_on_the_name_so_two_rebuilds_agree():
    template = "Will {} advance to the Final in Women's Singles at the 2026 US Open?"
    members = [
        _member(1, template.format("Zoe Zed"), 0.5),
        _member(2, template.format("Amy Able"), 0.5),
    ]
    fold = detect_container_field_groups({"polymarket:910235": members}, PARENT)
    assert [e["name"] for e in fold["polymarket:910235"]["entries"]] == [
        "Amy Able",
        "Zoe Zed",
    ]


def test_no_parent_row_means_no_fold():
    """The title is the one thing on this card a reader cannot check.

    A group with no ``market_type='field'`` parent has no venue-authored
    wording, and inventing one out of the members' grammar ("Who advance to
    the Final…") is worse than the repetition.
    """
    assert (
        detect_container_field_groups(
            {"polymarket:910235": _us_open_final_members()}, {}
        )
        == {}
    )


def test_an_empty_parent_name_is_not_a_title():
    assert (
        detect_container_field_groups(
            {"polymarket:910235": _us_open_final_members()},
            {"polymarket:910235": "   "},
        )
        == {}
    )


def test_unpriced_members_are_dropped_and_can_sink_the_fold():
    template = "Will {} advance to the Final in Women's Singles at the 2026 US Open?"
    members = [
        _member(1, template.format("Coco Gauff"), 0.425),
        _member(2, template.format("Iga Swiatek"), None),
    ]
    # One priced member left — a claim about one player, which already has a
    # correct card of its own.
    assert detect_container_field_groups({"polymarket:910235": members}, PARENT) == {}


def test_the_parents_prices_are_never_used():
    """#4163. The parent field row is stale where the members are polled.

    Measured on production 2026-09-08: parent ``59556600`` carries 0.000000 for
    Belinda Bencic while her live member leg reads 0.833. The fold borrows the
    parent's TEXT and nothing else, so this test asserts on the only surface
    that could betray it — every number on the card traces to a member.
    """
    members = _us_open_final_members()
    fold = detect_container_field_groups({"polymarket:910235": members}, PARENT)[
        "polymarket:910235"
    ]
    member_prices = {float(m["probability"]) for m in members}
    for entry in fold["entries"]:
        assert entry["probability"] in member_prices
    assert 0.0 not in [e["probability"] for e in fold["entries"]]


def test_market_ids_cover_every_member_so_none_survives_into_the_strip():
    members = _us_open_final_members()
    fold = detect_container_field_groups({"polymarket:910235": members}, PARENT)[
        "polymarket:910235"
    ]
    assert set(fold["market_ids"]) == {m["id"] for m in members}


def test_the_card_links_to_the_leader_not_to_the_parent():
    """The strip card is a link. The parent page is where the prices are wrong.

    The route reads ``entries[0]["market_id"]`` for the card's id, so the fold
    owes it the LEADER's market, not the parent's.
    """
    fold = detect_container_field_groups(
        {"polymarket:910235": _us_open_final_members()}, PARENT
    )["polymarket:910235"]
    assert fold["entries"][0]["market_id"] == 1  # Bencic, the 83.3% leader
