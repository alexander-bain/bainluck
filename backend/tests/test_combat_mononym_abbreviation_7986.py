"""#7986 — a fight card counts one bout twice when a venue abbreviates a mononym.

#7959 made the two venues' halves of one card meet, and `count_distinct_bouts`
began merging a bout both venues price. One bout on the 26 Sep UFC Fight Night
card did not merge, so the card was offered as "12 fights" holding 11:

    Polymarket  UFC Fight Night: Alatengheili vs. John Castaneda (Bantamweight, Prelims)
    Kalshi      Fight Night: Castaneda vs Heili

`castaneda` is shared; `{'alatengheili'} & {'heili'}` is empty, because Kalshi
abbreviates the mononym. One side matches exactly, the other not at all.

The repair admits a loose match on ONE side under three clauses, and every one
of them is load-bearing — each has a test below that reddens if it is dropped:

1. only when the other side matched EXACTLY (two loose sides is a
   name-similarity join, not identity evidence);
2. the loose relation is a SUFFIX of >= 5 characters — an abbreviation keeps the
   tail, whereas the hazard class (a longer DIFFERENT name) shares the head;
3. the exactly-matched token must IDENTIFY one fighter slot on the card, so a
   common surname stops being evidence.

Measured over every open combat market on 2026-09-22 (195 rows, both configs):
exactly one card moves, 26sep26 12 -> 11. UFC 332 stays at 14 and #7959's boxing
control stays unfolded.
"""

import pytest

from app.utils.event_combat import (
    _BOUT_ABBREV_MIN_LEN,
    _side_abbreviates,
    bout_roster_key,
    bouts_are_one_fight,
    count_distinct_bouts,
    fold_venue_scoped_tokens,
    identifying_bout_tokens,
)

# The live specimen, verbatim from production futures_markets on 2026-09-22.
PM_ALATENGHEILI = "UFC Fight Night: Alatengheili vs. John Castaneda (Bantamweight, Prelims)"
KALSHI_HEILI = "Fight Night: Castaneda vs Heili"

# The other ten bouts of that card, verbatim, both venues' spellings. Present so
# the census below is taken over the REAL card and not a two-row strawman.
CARD_26SEP26 = [
    ("Fight Night: Dumont Viana vs Perez", "UFC Fight Night: Norma Dumont vs. Ailin Perez (Women's Bantamweight, Prelims)"),
    ("Fight Night: Demopoulos vs Jauregui", "UFC Fight Night: Vanessa Demopoulos vs. Yazmin Jauregui (Women's Strawweight, Prelims)"),
    ("Fight Night: Jackson vs Simon", "UFC Fight Night: Ricky Simon vs. Montel Jackson (Bantamweight, Prelims)"),
    ("Fight Night: Bellato vs Edwards", "UFC Fight Night: Christian Edwards vs. Rodolfo Bellato (Light Heavyweight, Prelims)"),
    ("Fight Night: Harrell vs Brener", "UFC Fight Night: Elves Brener vs. Josiah Harrell (Lightweight, Main Card)"),
    ("Fight Night: Amaya vs Machado", "UFC Fight Night: Valesca Machado vs. Melissa Amaya (Women's Strawweight, Main Card)"),
    ("Fight Night: Osmanli vs Uulu", "UFC Fight Night: Ilimbek Akylbek Uulu vs. Mehemmedeli Osmanli (Bantamweight, Main Card)"),
    ("Fight Night: Hiestand vs Nakamura", "UFC Fight Night: Brady Hiestand vs. Rinya Nakamura (Bantamweight, Main Card)"),
    ("Fight Night: Vieira vs Bryczek", "UFC Fight Night: Robert Bryczek vs. Rodolfo Vieira (Middleweight, Main Card)"),
    ("Fight Night: Rosas Jr vs Barcelos", "UFC Fight Night: Raoni Barcelos vs. Raul Rosas Jr. (Bantamweight, Main Card)"),
]


def _rows(names):
    """Card rows as `count_distinct_bouts` consumes them, each its own group.

    A distinct `group` per row is the ADVERSARIAL shape: group identity would
    otherwise merge rows for free and hide whether the title test fired at all.
    """
    return [{"name": n, "group": i} for i, n in enumerate(names)]


def _full_card(extra=()):
    names = [PM_ALATENGHEILI, KALSHI_HEILI]
    for kalshi, polymarket in CARD_26SEP26:
        names += [kalshi, polymarket]
    return _rows(list(extra) + names)


# ---------------------------------------------------------------------------
# The ship: the real card, and the served count a reader sees.
# ---------------------------------------------------------------------------


def test_the_26sep_card_holds_eleven_bouts_not_twelve():
    """The whole point. Eleven bouts, twenty-two rows, two venues."""
    rows = _full_card()
    assert len(rows) == 22
    assert count_distinct_bouts(rows) == 11


def test_the_abbreviated_bout_is_the_one_that_moved():
    """Drop the abbreviated pair and the same card reads ten — so the +1 the
    count used to carry was that bout and nothing else."""
    others = [n for kalshi, pm in CARD_26SEP26 for n in (kalshi, pm)]
    assert count_distinct_bouts(_rows(others)) == 10
    assert count_distinct_bouts(_rows(others + [PM_ALATENGHEILI, KALSHI_HEILI])) == 11


def test_the_pair_alone_is_one_bout():
    assert count_distinct_bouts(_rows([PM_ALATENGHEILI, KALSHI_HEILI])) == 1


# ---------------------------------------------------------------------------
# Clause 2 — a SUFFIX, not containment. The class that motivated the choice.
# ---------------------------------------------------------------------------

#: A longer DIFFERENT name that begins the same way. Substring containment
#: admits six of these; a suffix admits none. Each is a real surname pair shape.
PREFIX_HAZARDS = [
    ("Brown", "Browning"),
    ("Costa", "Costabile"),
    ("Perez", "Perezaga"),
    ("Nunes", "Nunespaz"),
    ("Rodriguez", "Rodriguezo"),
    ("Santos", "Santosky"),
    ("Silva", "Silveira"),
    ("Hall", "Marshall"),  # a SUFFIX, but under the 5-char floor
]


@pytest.mark.parametrize("short,long_", PREFIX_HAZARDS)
def test_a_longer_different_name_is_not_an_abbreviation(short, long_):
    """Same opponent, genuinely different second fighter: two bouts, not one."""
    rows = _rows([f"Fight Night: {short} vs Castaneda",
                  f"UFC Fight Night: {long_} vs. John Castaneda"])
    assert count_distinct_bouts(rows) == 2


def test_hall_marshall_is_refused_by_the_length_floor_specifically():
    """`hall` IS a suffix of `marshall`; only the >= 5 floor refuses it. Guards
    the floor against being lowered to `_BOUT_TOKEN_MIN_LEN` for symmetry."""
    assert "marshall".endswith("hall")
    assert _BOUT_ABBREV_MIN_LEN > len("hall")
    assert not _side_abbreviates({"hall"}, {"marshall"})


def test_the_floor_is_not_raised_past_the_specimen_it_exists_for():
    """Six would refuse `heili` and the ship would be inert."""
    assert _BOUT_ABBREV_MIN_LEN <= len("heili")
    assert _side_abbreviates({"heili"}, {"alatengheili"})


# ---------------------------------------------------------------------------
# Clause 3 — the exactly-matched token must identify one fighter slot.
# ---------------------------------------------------------------------------


def test_two_silvas_do_not_let_alves_merge_into_goncalves():
    """The reachable hazard, and the reason clause 3 exists.

    `alves` is a true 5-character suffix of `goncalves`, exactly as `heili` is of
    `alatengheili` — no test on name SHAPE can separate them. What separates them
    is that `silva` here names two different fighters, so it is not evidence.
    """
    rows = _rows([
        "Fight Night: Silva vs Alves",
        "UFC Fight Night: Anderson Silva vs. Renato Goncalves",
        "Fight Night: Pereira vs Silva",
        "UFC Fight Night: Thiago Silva vs. Alex Pereira",
    ])
    assert _side_abbreviates({"alves"}, {"goncalves"})  # clause 2 alone would merge
    assert count_distinct_bouts(rows) == 3


def test_the_same_pair_merges_when_the_surname_is_unshared():
    """The control's positive half: remove the second Silva and the same two
    rows DO merge — so the refusal above is clause 3 firing, not the pair being
    unmatchable for some other reason."""
    rows = _rows([
        "Fight Night: Machado vs Alves",
        "UFC Fight Night: Valesca Machado vs. Renato Goncalves",
    ])
    assert count_distinct_bouts(rows) == 1


def test_identifying_tokens_counts_distinct_sides_not_rows():
    """A venue's parent row and its condition-id children repeat one title
    verbatim; that must not spend the card's budget for a token."""
    keys = [bout_roster_key(PM_ALATENGHEILI)] * 5 + [bout_roster_key(KALSHI_HEILI)]
    assert "castaneda" in identifying_bout_tokens(keys)


def test_a_surname_on_three_sides_stops_identifying():
    keys = [bout_roster_key(n) for n in (
        "UFC Fight Night: Anderson Silva vs. Alex Pereira",
        "UFC Fight Night: Thiago Silva vs. Rodolfo Vieira",
        "Fight Night: Silva vs Nakamura",
    )]
    assert "silva" not in identifying_bout_tokens(keys)
    assert "pereira" in identifying_bout_tokens(keys)


# ---------------------------------------------------------------------------
# Clause 1 — one loose side only, and only beside an exact one.
# ---------------------------------------------------------------------------


def test_both_sides_loose_is_refused():
    """Neither side shares a token; both are suffix-related. That is a
    name-similarity join and must not be identity evidence."""
    x = ({"heili"}, {"aneda"})
    y = ({"alatengheili"}, {"castaneda"})
    assert _side_abbreviates(x[0], y[0]) and _side_abbreviates(x[1], y[1])
    assert not (x[0] & y[0]) and not (x[1] & y[1])  # neither side matches exactly
    every_token = {"heili", "aneda", "alatengheili", "castaneda"}
    assert not bouts_are_one_fight(x, y, every_token)


# ---------------------------------------------------------------------------
# Blast radius — the arm is OFF for every caller that takes no census.
# ---------------------------------------------------------------------------


def test_the_arm_is_off_without_a_census():
    """`bouts_are_one_fight`'s two-argument behaviour is exactly #7959's."""
    x, y = bout_roster_key(KALSHI_HEILI), bout_roster_key(PM_ALATENGHEILI)
    assert bouts_are_one_fight(x, y) is False
    assert bouts_are_one_fight(x, y, {"castaneda"}) is True


def test_the_venue_fold_does_not_take_the_arm():
    """#7959's fold is a cross-source identity claim over a whole card and is
    deliberately left on the strict test. A scoped card whose ONLY overlap with
    the bare token is an abbreviated bout must still refuse to fold."""
    rosters = {
        "26sep26": [KALSHI_HEILI],
        "26sep26ufcfightnight": [PM_ALATENGHEILI],
    }
    assert fold_venue_scoped_tokens(rosters) == {
        "26sep26": "26sep26",
        "26sep26ufcfightnight": "26sep26ufcfightnight",
    }


def test_7959s_boxing_control_still_refuses_to_fold():
    """The live #4093 hazard: a second promotion on the same night, zero shared
    bouts. Unchanged by this ship, and it is why the fold keeps the strict test."""
    rosters = {
        "26sep26": ["Lee Cutler vs Louis Greene"],
        "26sep26zuffaboxing11": [
            "Zuffa Boxing 11: Pullen vs Faretina",
            "Zuffa Boxing 11: Cerda vs Lewis",
        ],
    }
    survivor = fold_venue_scoped_tokens(rosters)
    assert survivor["26sep26zuffaboxing11"] == "26sep26zuffaboxing11"


def test_ufc_332s_disagreement_is_still_two_bouts():
    """NOT in scope, and asserted so a later widening cannot silently take it.

    The venues name a DIFFERENT opponent — Kalshi's "332: Pillado vs Coria"
    against Polymarket's "UFC 332: Alden Coria vs. Imanol Rodriguez". A bout
    counter has no standing to declare one venue wrong, so this stays two.
    """
    rows = _rows([
        "332: Pillado vs Coria",
        "UFC 332: Alden Coria vs. Imanol Rodriguez",
    ])
    assert count_distinct_bouts(rows) == 2


def test_a_card_with_no_abbreviation_is_untouched():
    """Every other live card. Ten bouts, twenty rows, count unchanged by #7986."""
    rows = _rows([n for kalshi, pm in CARD_26SEP26 for n in (kalshi, pm)])
    assert count_distinct_bouts(rows) == 10
