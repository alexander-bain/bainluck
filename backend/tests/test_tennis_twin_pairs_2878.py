"""#2878 — the key that finds the twins, and the guard that stops it hiding a real match.

THE DEFECT. Every US Open match exists twice. authority/048 measured 240 in-span
tennis singles rows on 2026-09-06 and found **24 provable duplicate pairs plus 6
byte-identical rows**, and — more useful than the count — why every duplicate
census before it returned zero:

    the ghost and the real row differ in **exactly the two fields a duplicate
    census naturally keys on** — name spelling (24/24: ``Fritz vs Cerundolo``
    against ``Taylor Fritz vs Francisco Cerundolo``) and kickoff (never shared;
    the ghost carries ``00:00:00`` or a round ``18:00:00``).

WHY NEITHER EXISTING RAIL REACHES THEM, which is what this module exists for:

* ``event_registry._proven_duplicates`` is id-anchored (guards 1-3) and lane1/154
  measured zero shared ``(source, source_id)`` between any twin and its
  canonical; its guard 4 wants both rows within 30 minutes and the ghost's
  kickoff is the field that is wrong. It also fires only at ingest, so it could
  not reach 24 rows already in the table even if the predicate were repaired.
* ``reconcile_unanchored_events`` COUNTS them — its ``ANCHORED_TWIN_UNSEEN``
  bucket is this exact population — and its docstring forbids acting on that
  count: *"That predicate is a METER and must never become a MERGE."*

This suite pins the narrow thing that is safe: not a merge, which DELETEs and
needs an id, but a LABEL with an existing reader and no deleter. What is asserted
below, in order:

1. the measured pairs are found, in both orientations;
2. the ghost is identified by authority/048's 240/240 structural asymmetry — only
   tournament-keyed rows are ever linked — and never by which row looks nicer;
3. every way the asymmetry can fail produces REFUSE, not a guess;
4. the three fusions ``authority_tennis_names`` was written to prevent stay
   prevented, including one this module had to add a guard for.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.tennis_twin_pairs import (  # noqa: E402
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    TWIN_FOUND,
    TwinRow,
    block_key,
    classify_pair,
    players_agree,
    row_is_id_anchored,
)


def ghost(event_id, home, away, sport_key="tennis_atp", *, settled=False, anchored=False):
    """A bare tour-key row: no tournament key, no score, no provider id.

    Deliberately NOT "an empty row". Measured on production, 110 of 172 ghosts
    carry prediction markets and 63 carry more of them than their own canonical.
    What a ghost never carries is a score (`row_has_settled_result`) or a
    provider id (`row_is_id_anchored`, 0/1259 on production).
    """
    return TwinRow(
        event_id=event_id,
        home_team_name=home,
        away_team_name=away,
        sport_key=sport_key,
        is_tournament_keyed=False,
        has_settled_result=settled,
        is_id_anchored=anchored,
    )


def canonical(
    event_id, home, away, sport_key="tennis_atp_us_open", *, settled=True, anchored=True
):
    """The tournament-keyed row: carries the result, and carries a provider id.

    `settled` defaults True so the settled arm's fixtures read unchanged;
    `anchored` defaults True because 250/250 tournament-keyed rows on production
    carry one. Both are overridable so the refusals can be exercised.
    """
    return TwinRow(
        event_id=event_id,
        home_team_name=home,
        away_team_name=away,
        sport_key=sport_key,
        is_tournament_keyed=True,
        has_settled_result=settled,
        is_id_anchored=anchored,
    )


class TestTheMeasuredPairs:
    """The 24 pairs authority/048 found, by the shape they were found in."""

    @pytest.mark.parametrize(
        "short_home,short_away,full_home,full_away",
        [
            ("Fritz", "Cerundolo", "Taylor Fritz", "Francisco Cerundolo"),
            ("Swiatek", "Zheng", "Iga Swiatek", "Qinwen Zheng"),
            ("Osaka", "Rybakina", "Naomi Osaka", "Elena Rybakina"),
            ("Darderi", "Zverev", "Luciano Darderi", "Alexander Zverev"),
        ],
    )
    def test_surname_only_ghost_pairs_with_its_full_name_canonical(
        self, short_home, short_away, full_home, full_away
    ):
        v = classify_pair(
            ghost(1, short_home, short_away),
            canonical(2, full_home, full_away),
        )
        assert v.outcome == TWIN_FOUND
        assert v.ghost_id == 1 and v.canonical_id == 2

    def test_the_verdict_does_not_depend_on_argument_order(self):
        """A sweep must not care which row it happened to read first."""
        g, c = ghost(1, "Fritz", "Cerundolo"), canonical(2, "Taylor Fritz", "Francisco Cerundolo")
        forward, backward = classify_pair(g, c), classify_pair(c, g)
        assert forward.outcome == backward.outcome == TWIN_FOUND
        assert forward.ghost_id == backward.ghost_id == 1
        assert forward.canonical_id == backward.canonical_id == 2

    def test_a_flipped_twin_is_still_the_same_fixture(self):
        """Home and away are not stable across sources; the registry's own
        structured match treats a swapped orientation as a match for this
        reason, and a twin stored flipped is still one match."""
        v = classify_pair(
            ghost(1, "Cerundolo", "Fritz"),
            canonical(2, "Taylor Fritz", "Francisco Cerundolo"),
        )
        assert v.outcome == TWIN_FOUND and v.ghost_id == 1
        assert "swapped" in v.reason

    def test_two_different_matches_are_not_a_twin(self):
        v = classify_pair(
            ghost(1, "Fritz", "Cerundolo"),
            canonical(2, "Iga Swiatek", "Qinwen Zheng"),
        )
        assert v.outcome == NOT_A_TWIN


class TestTheGhostIsChosenByStructureNotByTaste:
    """authority/048's 240/240 finding, restated as a precondition.

    Every case here is one where a namable pair exists but the asymmetry that
    licenses hiding one of them does not hold. All of them must REFUSE. Tagging
    the wrong row of a true pair is the failure that takes a real match off the
    product, and it is worse than leaving a duplicate visible.
    """

    def test_two_tournament_keyed_rows_are_never_resolved(self):
        v = classify_pair(
            canonical(1, "Taylor Fritz", "Francisco Cerundolo"),
            canonical(2, "Fritz", "Cerundolo"),
        )
        assert v.outcome == REFUSE_AMBIGUOUS
        assert v.ghost_id is None

    def test_two_bare_rows_are_never_resolved(self):
        v = classify_pair(ghost(1, "Fritz", "Cerundolo"), ghost(2, "Taylor Fritz", "Francisco Cerundolo"))
        assert v.outcome == REFUSE_AMBIGUOUS
        assert v.ghost_id is None

    def test_a_bare_row_that_got_settled_is_not_a_ghost(self):
        """The population stopped obeying the asymmetry, so it stops being
        tagged rather than being tagged wrongly.

        A bare-keyed row that carries a final score is a row somebody settled,
        and the whole basis for calling the other one canonical has gone.
        Measured 0/172 on production — so if this ever fires in a real sweep,
        the premise has changed and the refusal is the correct output.
        """
        settled = ghost(1, "Fritz", "Cerundolo", settled=True)
        v = classify_pair(settled, canonical(2, "Taylor Fritz", "Francisco Cerundolo"))
        assert v.outcome == REFUSE_AMBIGUOUS
        assert "carries a result" in v.reason

    def test_a_row_never_twins_with_itself(self):
        g = ghost(1, "Fritz", "Cerundolo")
        assert classify_pair(g, g).outcome == NOT_A_TWIN

    def test_a_misclassified_row_does_not_pair_across_disciplines(self):
        """#3559 files tennis matches under `baseball_other`. A cross-sport pair
        is never one fixture, whatever the names do."""
        v = classify_pair(
            ghost(1, "Fritz", "Cerundolo", sport_key="baseball_other"),
            canonical(2, "Taylor Fritz", "Francisco Cerundolo"),
        )
        assert v.outcome == NOT_A_TWIN


class TestTheUnplayedArm:
    """#2693 — the half the score could not reach.

    Six US Open quarter-finals were printing twice on 2026-09-07 with no score
    on either row. What separates them is the PROVIDER ID: 250/250
    tournament-keyed rows carry one, 0/1259 bare rows do, and the shape holds on
    all 161 settled tags and all 6 unplayed pairs.

    Every refusal below is a case where the population has stopped obeying that
    structure. Under-tagging stays the intended failure direction, so each of
    these is the CORRECT output and not a shortcoming.
    """

    @pytest.mark.parametrize(
        "short_home,short_away,full_home,full_away",
        [
            ("Swiatek", "Zheng", "Iga Swiatek", "Qinwen Zheng"),
            ("Andreeva", "Potapova", "Mirra Andreeva", "Anastasia Potapova"),
            ("Cerundolo", "Blockx", "Francisco Cerundolo", "Alexander Blockx"),
            ("Osaka", "Rybakina", "Naomi Osaka", "Elena Rybakina"),
            ("Zverev", "Darderi", "Alexander Zverev", "Luciano Darderi"),
            ("Khachanov", "Tien", "Karen Khachanov", "Learner Tien"),
        ],
    )
    def test_the_six_quarter_finals_are_decided_before_a_ball_is_struck(
        self, short_home, short_away, full_home, full_away
    ):
        """The exact six pairs on production, by the shape they were found in."""
        v = classify_pair(
            ghost(1, short_home, short_away),
            canonical(2, full_home, full_away, settled=False),
        )
        assert v.outcome == TWIN_FOUND
        assert (v.ghost_id, v.canonical_id) == (1, 2)

    def test_the_verdict_does_not_depend_on_argument_order(self):
        g = ghost(1, "Cerundolo", "Blockx")
        c = canonical(2, "Francisco Cerundolo", "Alexander Blockx", settled=False)
        assert classify_pair(g, c) == classify_pair(c, g)

    def test_an_unplayed_pair_whose_bare_row_has_a_provider_id_is_refused(self):
        """🔴 The tripwire. 0/1259 bare rows carried an id when this was measured.

        If one ever does, the conjunction that licenses the whole judgement has
        broken and the honest answer is to stop, not to fall back on the sport
        key alone.
        """
        v = classify_pair(
            ghost(1, "Swiatek", "Zheng", "tennis_wta", anchored=True),
            canonical(2, "Iga Swiatek", "Qinwen Zheng", "tennis_wta_us_open",
                      settled=False),
        )
        assert v.outcome == REFUSE_AMBIGUOUS
        assert "carries a provider id" in v.reason

    def test_an_unplayed_pair_with_no_provider_id_anywhere_is_refused(self):
        """Neither a score nor an id: nothing separates them, so nothing is written."""
        v = classify_pair(
            ghost(1, "Swiatek", "Zheng", "tennis_wta"),
            canonical(2, "Iga Swiatek", "Qinwen Zheng", "tennis_wta_us_open",
                      settled=False, anchored=False),
        )
        assert v.outcome == REFUSE_AMBIGUOUS
        assert "neither carries a provider id" in v.reason

    def test_the_settled_arm_does_not_consult_the_anchor(self):
        """🔴 The already-shipped arm is untouched, and that is deliberate.

        161 labels are on disk, written on the score. Re-deciding them on a
        second column would be this module arbitrating against itself, so a
        settled pair whose canonical happens to carry no provider id is still
        TWIN_FOUND — exactly as it was before #2693.
        """
        v = classify_pair(
            ghost(1, "Fritz", "Cerundolo"),
            canonical(2, "Taylor Fritz", "Francisco Cerundolo", anchored=False),
        )
        assert v.outcome == TWIN_FOUND

    def test_the_anchor_reader_accepts_any_one_of_the_three_providers(self):
        """`row_is_id_anchored` asks whether SOME provider knows this fixture."""
        assert not row_is_id_anchored(
            external_id=None, espn_id=None, statpal_fixture_id=None
        )
        for field in ("external_id", "espn_id", "statpal_fixture_id"):
            kwargs = {
                "external_id": None,
                "espn_id": None,
                "statpal_fixture_id": None,
                field: "x",
            }
            assert row_is_id_anchored(**kwargs), field

    def test_market_count_is_not_the_anchor(self):
        """🔴 The mistake `row_has_settled_result` documents, restated.

        A ghost typically has MORE markets than its canonical (63/172), so any
        reading of "which row has substance" that counts markets points the
        wrong way. `row_is_id_anchored` takes no market argument at all — this
        pins that it cannot acquire one by accident.
        """
        import inspect

        params = set(inspect.signature(row_is_id_anchored).parameters)
        assert params == {"external_id", "espn_id", "statpal_fixture_id"}


class TestTheFusionsThatMustNotHappen:
    """Each of these deleted a discriminator when it was tried for real."""

    def test_a_generational_suffix_keeps_two_players_apart(self):
        """`authority_tennis_names` keeps the suffix because stripping it fuses
        Martin Damm with Martin Damm Jr. Keeping it is not sufficient here and
        running the pair is what showed it: `our_tennis_keys('Damm Jr')` yields
        `('damm', 'j')` through the surname-FIRST reading — the one that exists
        so `Wu Yibing` can join `Yibing Wu` — and a `None` initial on the bare
        `Damm` cannot disagree with it. Hence the explicit suffix comparison."""
        assert players_agree("Damm", "Damm Jr") is False
        assert players_agree("Martin Damm", "Martin Damm Jr") is False
        # and the suffix must not become a wildcard in the other direction
        assert players_agree("Damm", "Martin Damm") is True

    def test_a_futures_title_is_not_a_player(self):
        """Futures-market titles sit in the same column and fold to keys that
        collide with nothing real."""
        title = "Black Desert Resort (Men's Doubles) Winner"
        assert players_agree(title, "Winner") is False
        assert block_key(title, "Fritz") is None

    def test_doubles_never_matches_singles(self):
        """Doubles outnumber singles better than 2:1 on a US Open day; fusing
        the draws manufactures pairs that do not exist."""
        assert players_agree("Fritz/Cerundolo", "Fritz") is False
        v = classify_pair(
            ghost(1, "Fritz/Cerundolo", "Swiatek/Zheng"),
            canonical(2, "Taylor Fritz", "Iga Swiatek"),
        )
        assert v.outcome == NOT_A_TWIN

    def test_a_doubles_team_is_order_insensitive(self):
        assert players_agree("Fritz/Cerundolo", "Cerundolo/Fritz") is True

    def test_diacritics_are_one_player(self):
        assert players_agree("Bondar", "Anna Bondár") is True


class TestTheBlockKey:
    """The coarse bucket. Looser than the confirm step, deliberately: a block
    key that could refuse a true pair would hide it from the careful predicate."""

    def test_both_spellings_of_one_fixture_share_a_bucket(self):
        assert block_key("Fritz", "Cerundolo") == block_key(
            "Taylor Fritz", "Francisco Cerundolo"
        )

    def test_the_bucket_does_not_depend_on_home_and_away_order(self):
        assert block_key("Fritz", "Cerundolo") == block_key("Cerundolo", "Fritz")

    def test_unreadable_rows_bucket_to_none_rather_than_to_each_other(self):
        """Two rows we cannot read are not thereby the same match — the failure
        that makes a census report pairs it invented."""
        assert block_key("", "Fritz") is None
        assert block_key(None, "Fritz") is None

    def test_different_fixtures_get_different_buckets(self):
        assert block_key("Fritz", "Cerundolo") != block_key("Swiatek", "Zheng")


# ════════════════════════════════════════════════════════════════════════════
# #4617 — a surname that runs to more than one token
# ════════════════════════════════════════════════════════════════════════════

#: Bare row → its canonical, one per naming convention on the tour. Every one of
#: these was measured FALSE against `players_agree` before #4617 and TRUE after;
#: the five single-token controls at the end passed both times and are here so a
#: regression that broke them is visible in the same table.
_ONE_PLAYER_TWO_SPELLINGS = [
    # Dutch/Belgian particles — the live US Open specimen is the first row
    ("Van de Zandschulp", "Botic van de Zandschulp"),
    ("de Minaur", "Alex de Minaur"),
    ("Van Rijthoven", "Tim Van Rijthoven"),
    ("De Jong", "Jesper De Jong"),
    # Spanish/Argentine double surnames
    ("Davidovich Fokina", "Alejandro Davidovich Fokina"),
    ("Bautista Agut", "Roberto Bautista Agut"),
    ("Carreno Busta", "Pablo Carreno Busta"),
    ("Ramos Vinolas", "Albert Ramos Vinolas"),
    ("Del Potro", "Juan Martin Del Potro"),
    ("Moro Canas", "Alejandro Moro Canas"),
    # Hyphenated — folded to two tokens, so it fails the same way
    ("Auger-Aliassime", "Felix Auger-Aliassime"),
    ("Gueymard Wayenburg", "Arthur Gueymard Wayenburg"),
    # Single-token controls: unaffected by #4617, and passing before it
    ("Munar", "Jaume Munar"),
    ("Tsitsipas", "Stefanos Tsitsipas"),
    ("Etcheverry", "Tomas Martin Etcheverry"),
    ("Baez", "Sebastian Baez"),
    ("Struff", "Jan-Lennard Struff"),
]


class TestAMultiTokenSurnameIsStillOneSurname:
    """#4617. The bare row's whole value is a surname; the confirm step read one
    of that surname's own tokens as a forename and refused the pair.

    ``our_tennis_keys('Van de Zandschulp')`` yielded ``('zandschulp', 'v')`` —
    the ``'v'`` from *Van* — against the canonical's real ``('zandschulp', 'b')``
    from *Botic*, so no combination of the 24 readings could ever agree. On the
    live tournament that printed ``Zverev / Van de Zandschulp`` twice
    (``15307491`` bare with 18 markets, ``15307525`` tournament-keyed with 8)
    while the structurally identical ``Khachanov / Blockx`` and
    ``Gauff / Rybakina`` were both tagged.

    **The defect was two functions in this one module disagreeing about the same
    pair**, so every case below asserts both of them, which is why the guard is
    written as a table and not as one assertion per name.
    """

    @pytest.mark.parametrize("bare,canon", _ONE_PLAYER_TWO_SPELLINGS)
    def test_the_bucket_and_the_confirm_step_agree_on_one_player(self, bare, canon):
        """Measured 12/17 FALSE before #4617 — every failure a multi-token or
        hyphenated surname, every single-token name passing. Dutch, Spanish,
        Argentine and French conventions are a large share of the draw, so this
        was a hole in a whole naming SHAPE rather than a long tail."""
        assert players_agree(bare, canon) is True
        # …and the coarse key must still bucket them, or the confirm step above
        # is never reached on a real sweep and this test would pass vacuously
        # while the twin stayed on the page.
        assert block_key(bare, "Zverev") == block_key(canon, "Alexander Zverev")

    def test_the_live_specimen_is_now_one_fixture(self):
        """The end the reader sees: `15307491`/`15307525` returned NOT_A_TWIN
        ("participants disagree") and printed two cards for one match. Modelled
        on the unplayed arm, which is the state the pair was actually in."""
        verdict = classify_pair(
            ghost(15307491, "Zverev", "Van de Zandschulp", settled=False),
            canonical(
                15307525,
                "Alexander Zverev",
                "Botic van de Zandschulp",
                settled=False,
                anchored=True,
            ),
        )
        assert verdict.outcome == TWIN_FOUND
        assert verdict.ghost_id == 15307491

    def test_it_reads_the_surname_whole_and_not_as_a_wildcard(self):
        """The widening is bounded by the surname still having to match WHOLE.

        These three are different people who share a token, and the fix must not
        reach them — `('moro canas', None)` cannot address `Alejandro Canas`
        because that row's surname run is `canas`, not `moro canas`. Measured
        False both before and after, i.e. these are the cases that make the
        parametrised table above mean something."""
        assert players_agree("Moro Canas", "Alejandro Canas") is False
        assert players_agree("Bautista Agut", "Roberto Bautista") is False
        assert players_agree("De Jong", "Jesper de Minaur") is False

    def test_a_bare_surname_still_cannot_separate_two_brothers(self):
        """`Zverev` vs `Mischa Zverev` agrees — and did before #4617 too, via the
        single-token `('zverev', None)` reading that has always been emitted.

        Pinned as EXISTING behaviour so it is not read as something the fix
        introduced. A bare surname genuinely does not carry the information; what
        backstops it is `classify_pair`'s asymmetry guard and the 96h fence, not
        the name predicate."""
        assert players_agree("Zverev", "Mischa Zverev") is True

    def test_the_two_functions_are_not_required_to_agree_in_general(self):
        """Stated so the guard above is not over-read into a false invariant.

        The block key is deliberately LOOSER than the confirm step, so it buckets
        `Moro Canas` with `Alejandro Canas` — two different players — and the
        confirm step is what refuses them. The invariant is one-directional:
        anything `players_agree` confirms, `block_key` must also bucket, because
        a pair the key drops never reaches the careful predicate at all. The
        reverse is the design."""
        assert block_key("Moro Canas", "Zverev") == block_key(
            "Alejandro Canas", "Alexander Zverev"
        )
        assert players_agree("Moro Canas", "Alejandro Canas") is False
