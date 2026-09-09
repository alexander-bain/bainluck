"""#4223 — a question is not a contender, so it never gets a row on a field card.

Mystery-shopping `/sports` after #4203 deployed (standing notice 4 / D48). Seven
of the twelve field cards on the props strip read like this one, verbatim from
the served payload on production `462a961b`:

    Major League Cricket: Texas Super Kings vs Seattle Orcas
      1. Orcas                        100%
      2. Orcas - Completed match?     100%
      3. Orcas - Who wins the toss?   100%

Three different questions about one fixture — the match winner, "was the match
completed", and the toss — folded into a "field" because they share a long
prefix, with the toss question printed as if it were a player. "Orcas" is also
half of "Seattle Orcas", and "York" (from "Mi New York") appeared the same way
on three more cards.

The existing shape test in ``extract_container_member_entities`` already refuses
a differing span carrying ``:``, brackets or `` vs ``, on exactly this reasoning
(#4153). ``?`` is the same rule and the plainest case of it: **no name ends in a
question mark.**

Measured over 153 at-risk production groups the same night: 88 fold today, and
**42 of those 88 produce an entity carrying a ``?``** — not only question tails
but dates and dollar amounts (``$1.2T?``, ``December 31?``), which are threshold
ladders being mis-sold as fields. **Zero** legitimate entities in that sample
contained one, which is why this is a ban and not a heuristic.

A space-padded dash was measured alongside it and deliberately NOT banned: it
costs 0 additional groups in the same sample, so it would be a rule with no
case, and reserve-team names ("Bayern - II") are real.
"""

import pytest

from app.utils.market_grouping import (
    detect_container_field_groups,
    extract_container_member_entities,
)

# ── the card Alex would have seen ─────────────────────────────────────────

_CRICKET = [
    "Major League Cricket: Texas Super Kings vs Seattle Orcas",
    "Major League Cricket: Texas Super Kings vs Seattle Orcas - Completed match?",
    "Major League Cricket: Texas Super Kings vs Seattle Orcas - Who wins the toss?",
]


def test_the_toss_question_does_not_become_a_contender():
    """The production group `polymarket:592965`, member names unmodified."""
    assert extract_container_member_entities(_CRICKET) is None


def test_the_whole_card_goes_not_just_the_bad_row():
    """Fail closed. A field with one bogus row is not a field with two good ones.

    Refusing only the offending member would leave "Orcas" alone on a card
    titled with the fixture — a ranked field of one, which is the repetition
    #4153 removed wearing a different hat.
    """
    members = [
        {"id": i, "name": n, "source": "polymarket", "probability": 1.0}
        for i, n in enumerate(_CRICKET, start=1)
    ]
    parents = {
        "polymarket:592965": "Major League Cricket: Texas Super Kings vs Seattle Orcas"
    }
    assert detect_container_field_groups({"polymarket:592965": members}, parents) == {}


@pytest.mark.parametrize(
    "group_id,names",
    [
        # The other three cricket fixtures on the strip the same night. "York"
        # is the tail of "Mi New York" — the affix snap stopped at a space that
        # falls inside a proper noun, which is its own defect (#4223 repair 3)
        # and is not what this test is about.
        (
            "polymarket:592973",
            [
                "Major League Cricket: Washington Freedom vs Mi New York",
                "Major League Cricket: Washington Freedom vs Mi New York - Completed match?",
                "Major League Cricket: Washington Freedom vs Mi New York - Who wins the toss?",
            ],
        ),
        # A threshold ladder sold as a field: the "entities" are dollar amounts.
        (
            "polymarket:102007",
            [
                "Will the market cap reach $1.2T?",
                "Will the market cap reach $1.4T?",
                "Will the market cap reach $1.6T?",
            ],
        ),
        # And one sold as a field of DATES.
        (
            "polymarket:117601",
            [
                "Will it happen by December 31?",
                "Will it happen by June 30?",
            ],
        ),
    ],
)
def test_the_other_shapes_the_census_found(group_id, names):
    assert extract_container_member_entities(names) is None, group_id


# ── what the ban must NOT cost ────────────────────────────────────────────


def test_a_question_mark_in_the_SHARED_wording_is_untouched():
    """Almost every one of these markets is a question. Only the SLOT is checked.

    The template's own "?" lives in the shared suffix and never reaches an
    entity, so the ban must not touch the fields it is there to protect. If this
    ever reds, the ban has been applied to the wrong string.
    """
    template = "Will {} advance to the Final in Women's Singles at the 2026 US Open?"
    assert extract_container_member_entities(
        [template.format("Coco Gauff"), template.format("Iga Swiatek")]
    ) == ["Coco Gauff", "Iga Swiatek"]


def test_the_real_us_open_field_still_folds_end_to_end():
    """#4153's ship, re-asserted through the detector this change edits."""
    template = "Will {} advance to the Final in Women's Singles at the 2026 US Open?"
    roster = [("Aryna Sabalenka", 0.93), ("Coco Gauff", 0.43), ("Jessica Pegula", 0.37)]
    members = [
        {"id": i, "name": template.format(e), "source": "polymarket", "probability": p}
        for i, (e, p) in enumerate(roster, start=1)
    ]
    parents = {
        "polymarket:910235": "US Open 2026: To Reach the Final (Women's Singles)"
    }
    group = detect_container_field_groups({"polymarket:910235": members}, parents)[
        "polymarket:910235"
    ]
    assert [e["name"] for e in group["entries"]] == [
        "Aryna Sabalenka",
        "Coco Gauff",
        "Jessica Pegula",
    ]


def test_a_space_padded_dash_is_still_allowed():
    """Measured at 0 groups' cost, so it is not banned. Pin that on purpose.

    A future session reading the cricket names will be tempted to ban `" - "`
    too. It buys nothing the `?` ban does not already buy, and it would refuse a
    real reserve-team field.
    """
    template = "Will {} win the Regionalliga in 2026-27?"
    assert extract_container_member_entities(
        [template.format("Bayern - II"), template.format("Dortmund - Reserves")]
    ) == ["Bayern - II", "Dortmund - Reserves"]
