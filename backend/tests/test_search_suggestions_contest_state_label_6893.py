"""#6893 — the "Right now" row does not headline a chip with the STATE of a contest.

WHAT A PERSON SAW. `GET /api/events/search-suggestions`, production, 2026-09-18
07:36:34Z (cache generation 3, i.e. a fresh build), master `cf729f250` — the
FIRST card of the row, not the third:

    {"query": "Completed Match",
     "label": "Falling -98.9 points — M15 Hurghada: Chirag Duhan ...",
     "type": "futures", "market_id": 61317583}

`futures_outcomes` 230896865 sat at `current_probability = 0.001` with
`probability_change_24h = -0.989` on market 61317583
(`M15 Hurghada: Chirag Duhan vs Millen Hurrion`, `market_type = field`,
`market_tier = 5`, `event_id = NULL`). At 0.1%, "Completed Match" means the
match will NOT be completed — a retirement. The row was selling a decided ITF
M15 result as the day's biggest movement, under a headline naming no thing a
person can look up.

WHY #3987'S THREE GATES ALL PASSED IT, WHICH IS THE PART WORTH KEEPING. This is
not a regression: every gate #3987 shipped still works, and the row satisfies
each one.

  * defect 1, settled eligibility — bars `current_probability` at EXACTLY 0.0 or
    1.0. The specimen is 0.001.
  * defect 2, shape — bars `quantity` / `unshaped` / `container_member`. The
    specimen is `field`.
  * defect 2, lexical — bars a token-initial digit. `Completed Match` has none.
  * defect 3, tier — the market has no event, so the gate's deliberate
    `event_id IS NULL` arm carries it.

So the hole is none of those: it is that `_SUGGESTION_SIDE_LABELS`, the file's
documented home for "outcome names that name a SIDE of a market rather than a
thing to look up", did not carry the yes-side of "will this match be
completed?". The list was otherwise working on the same ranking — `tie` (35
eligible rows) and `match winner` (15) were refused that morning.

THE CORPUS IS PRODUCTION, AND THE CONTROLS ARE THE REASON THE RULE IS A LIST.
`_STATE_NAMES` and `_ENTITY_CONTROLS` were read out of the live eligible pool on
2026-09-18 by lane1b/326: all 659 distinct outcome names on fixture-shaped
markets, run through the real `_suggestion_is_prop_text` and
`_suggestion_entity_name`. 185 survived both; 63 of those were not a substring
of their own market title.

⚠️ THAT 63 IS WHY THERE IS NO CLEVER STRUCTURAL RULE HERE, AND IT WAS MEASURED
BEFORE THE LIST WAS TOUCHED. "The outcome must appear in its own fixture's
name" is the tempting general rule and it is WRONG: most of the 63 are real
players, because the market title carries surnames only — `Zuzanna Pawlikowska`
vs `Pawlikowska vs Ceuca`, `Felix Auger-Aliassime` vs `Auger-Aliassime vs
Halys`. That rule would delete genuine entities to catch four phrases.
`_ENTITY_CONTROLS` below is exactly that population, so a future author who
reaches for the structural rule reddens this file.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routes.events import (
    _SUGGESTION_SIDE_LABELS,
    _mover_chips,
    _suggestion_entity_name,
)

#: Phrase-shaped outcome names that survived BOTH display gates on 2026-09-18
#: and name a state of the contest rather than a competitor. The complete set
#: over the census described in the module docstring — not a sample.
_STATE_NAMES = (
    "Completed Match",
    "Both Teams to Score",
    "Both Teams to Score in First Half",
    "Any Other Score",
)

#: Real people from the SAME 63 rows — outcome names on fixture markets that are
#: NOT substrings of their own market title. Every one must keep its chip.
_ENTITY_CONTROLS = (
    "Zuzanna Pawlikowska",
    "Felix Auger-Aliassime",
    "Gabriele Thomas Brancatelli",
    "Emily Appleton",
    "Kristijan Juhas",
    "Ekaterina Perelygina",
    "Dusan Obradovic",
    "Charles Bertimon",
    "Elena Milovanovic",
    "Chirag Duhan",
)


def _row(name, *, market_name, market_id=61317583, change=-0.989, event=None):
    """One ranked mover outcome, in the shape `_mover_chips` consumes."""
    return SimpleNamespace(
        name=name,
        market_id=market_id,
        probability_change_24h=change,
        market=SimpleNamespace(id=market_id, name=market_name, event=event),
    )


# ---------------------------------------------------------------------------
# 0 — the corpus is not self-serving
# ---------------------------------------------------------------------------


def test_the_corpus_separates_two_classes_and_not_one_string():
    """Prove the fixture is a CLASS with a real control side before trusting it.

    #3675 closed on `Yes` and its grammar then served `Completed Match`; #3987
    closed on `Cut more than 25bps` and the grammar then served `Completed
    Match` again. A file that tests one string is how that happens.
    """
    assert len(_STATE_NAMES) >= 4 and len(_ENTITY_CONTROLS) >= 10
    assert not set(_STATE_NAMES) & set(_ENTITY_CONTROLS)
    assert (
        "Completed Match" in _STATE_NAMES
    ), "the SERVED instance must be in the corpus"
    # Every control is a two-or-three-word Title Case human name, i.e. the state
    # names are NOT separable from them by shape — which is the finding that
    # rules out a structural rule and leaves the vocabulary list.
    for name in _ENTITY_CONTROLS:
        assert name[0].isupper() and " " in name or name.isalpha()


# ---------------------------------------------------------------------------
# 1 — the display rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", _STATE_NAMES)
def test_a_contest_state_is_not_an_entity(name):
    assert _suggestion_entity_name(name) is None, (
        f"{name!r} would be served as a chip query — tapping it runs "
        f"/search?q={name}, which names no entity and leads nowhere in particular"
    )


@pytest.mark.parametrize("name", _ENTITY_CONTROLS)
def test_a_real_player_still_names_themselves(name):
    assert _suggestion_entity_name(name) == name, (
        f"{name!r} is a person from the same production ranking, on a fixture "
        "market whose title carries surnames only; a rule that removes them has "
        "removed the section's reason to exist"
    )


# ---------------------------------------------------------------------------
# 2 — the served chip, driven through the real builder
# ---------------------------------------------------------------------------


def test_the_served_production_chip_is_gone():
    """The exact row production served at rank 1 on 2026-09-18 makes no chip."""
    chips = _mover_chips(
        [
            _row(
                "Completed Match",
                market_name="M15 Hurghada: Chirag Duhan vs Millen Hurrion",
            )
        ]
    )
    assert chips == [], f"the #6893 specimen is still served: {chips!r}"


def test_the_section_is_filtered_and_not_deleted():
    """A real player on the identical market shape still supplies the chip.

    The specimen and the control differ ONLY in the outcome name, so a fix that
    reddens this test has barred the market rather than the label.
    """
    chips = _mover_chips(
        [
            _row(
                "Completed Match",
                market_name="M15 Hurghada: Chirag Duhan vs Millen Hurrion",
            ),
            _row(
                "Gabriele Thomas Brancatelli",
                market_name="Brancatelli vs Ivanov",
                market_id=61317578,
                change=-0.9635,
            ),
        ]
    )
    assert [c["query"] for c in chips] == ["Gabriele Thomas Brancatelli"]
    # And the label is still the house points formatting (#5608), unchanged.
    assert chips[0]["label"].startswith("Falling -96.4 points — ")


def test_a_state_label_does_not_spend_a_limit_slot():
    """Refusal is a `continue`, not a consumed slot — the row keeps its length.

    `_mover_chips` takes `limit` rows; if a refused row counted against it the
    row would simply get shorter, which is the failure #3987 defect 1 called out
    when it argued the settled gate belonged in the query.
    """
    rows = [
        _row(
            "Completed Match",
            market_name=f"M15 Hurghada: A{i} vs B{i}",
            market_id=900 + i,
        )
        for i in range(5)
    ]
    rows += [
        _row(
            "Emily Appleton",
            market_name="Appleton vs Kuzmova",
            market_id=61310744,
            change=-0.5,
        ),
        _row(
            "Charles Bertimon",
            market_name="Bertimon vs Gretskiy",
            market_id=61317582,
            change=-0.4,
        ),
    ]
    chips = _mover_chips(rows, limit=2)
    assert [c["query"] for c in chips] == ["Emily Appleton", "Charles Bertimon"]


# ---------------------------------------------------------------------------
# 3 — the recurrence guard
# ---------------------------------------------------------------------------


def test_every_side_label_can_actually_fire():
    """A Title-Case or padded entry is a silent no-op, and looks correct in review.

    The membership test is `name.casefold() in _SUGGESTION_SIDE_LABELS` over a
    whitespace-collapsed name, so an entry carrying a capital or a stray space
    can never match anything — it reads as a fix and refuses nothing. This is
    the trap that would let the next author "add `Completed Match`" and ship a
    chip that is still served.
    """
    for label in _SUGGESTION_SIDE_LABELS:
        assert (
            label == label.casefold()
        ), f"{label!r} is not casefolded and can never match"
        assert label == " ".join(
            label.split()
        ), f"{label!r} carries padding and can never match"


def test_the_new_labels_are_in_the_shared_vocabulary_not_a_private_list():
    """The fix must live in `_SUGGESTION_SIDE_LABELS` so every caller inherits it.

    `_suggestion_entity_name` is the only consumer today, but the frozenset is
    the documented home for this class; a private check inside one function
    would not be found by the next person adding a section to the row.
    """
    for name in _STATE_NAMES:
        assert name.casefold() in _SUGGESTION_SIDE_LABELS
