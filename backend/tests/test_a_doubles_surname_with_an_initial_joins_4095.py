"""A doubles surname that carries an initial joins to StatPal. #4095.

SHIP (pillar: MATCHING): two real US Open doubles matches on 2026-09-08 —
`Carpico/ Filin` v `Ram/ Salisbury` and `Hsieh S-/Ostapenko` v `Mertens/
Shnaider` — stop being reported as matches StatPal has and we do not. We held
both. The doubles join keyed on whole folded surnames with no initial slot, so
our `Filin N` and StatPal's `Filin` were two different surnames, and **the
initial that exists to disambiguate a player made the row unjoinable instead.**

The fix is `doubles_teams_agree`: each player compared under `keys_agree`, the
rule the SINGLES arm has always obeyed — surname whole and equal, initial
deciding only when both sides carry one. Initial-AWARE, never
initial-DROPPING, and this file's `TestItDidNotDeleteTheDiscriminator` is why
that distinction is the whole safety argument (CERT-1890: stripping `Jr` fused
Martin Damm with his son).

Three things this file holds that a reader should not have to take on trust:

* the widened relation is measured over the WHOLE pinned corpus, not over the
  two cases that motivated it — 1,674 doubles names, with the eligible
  denominator (how many carry an initial at all) asserted so a green run cannot
  be vacuous;
* every pair the widening newly joins is checked for its SHAPE, not just
  counted, so a run that gained the right number of wrong pairs still reds;
* `doubles_key` — the IDENTITY that `register_identity`, the twin sweep's block
  key and the agreement row's denominator are scored on — is asserted
  UNCHANGED. Widening the join without moving the identity is the property that
  keeps this off the D50 gate's scoring, and it is a property, not a hope.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.statpal_api import StatPalAPIService
from app.utils.authority_agreement import Side
from app.utils.authority_tennis_agreement import DOUBLES, pair_tennis_sides
from app.utils.authority_tennis_names import (
    AMBIGUOUS,
    MATCHED,
    doubles_key,
    doubles_side_keys,
    doubles_teams_agree,
    is_doubles_name,
    resolve_tennis_name,
    tennis_names_agree,
)

CORPUS = Path(__file__).parent / "fixtures" / "tennis_name_corpus_20260905.json"
DOUBLES_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "statpal_tennis_livescores_doubles_20260908.json"
)

#: Production's doubles rows for the pinned day, the same nine
#: `test_link_tennis_statpal_fixtures.LIVE_POOL` holds. Duplicated rather than
#: imported because that file's copy is shaped for the LINKER and this one is
#: shaped for the AGREEMENT row, and a shared fixture that has to satisfy both
#: is how one of them quietly stops being production's rows.
LIVE_ROWS = [
    (15307402, "Hsieh/Ostapenko", "Mertens/Shnaider", "2026-09-07T23:20:16+00:00"),
    (15307337, "Gonzalez/Molteni", "Granollers/Zeballos", "2026-09-08T15:00:00+00:00"),
    (15307251, "Heliovaara / Patten", "Cabral / Tracy", "2026-09-08T18:00:00+00:00"),
    (
        15306994,
        "Nys / Roger-Vasselin",
        "Andreozzi / Guinard",
        "2026-09-08T18:00:00+00:00",
    ),
    (
        15307250,
        "Gonzalez / Molteni",
        "Granollers / Zeballos",
        "2026-09-08T18:00:00+00:00",
    ),
    (15306271, "Carpico / Filin N", "Ram / Salisbury", "2026-09-08T18:00:00+00:00"),
    (
        15307370,
        "Siniakova / Townsend",
        "Bucsa / Melichar-Martinez",
        "2026-09-08T22:00:00+00:00",
    ),
    (
        15307368,
        "Hsieh S-W / Ostapenko",
        "Mertens / Shnaider",
        "2026-09-08T23:10:00+00:00",
    ),
    (15308219, "Ram / Salisbury", "Granollers / Zeballos", "2026-09-09T18:00:00+00:00"),
]


@pytest.fixture(scope="module")
def corpus() -> list[str]:
    return json.loads(CORPUS.read_text())["names"]


@pytest.fixture(scope="module")
def corpus_doubles(corpus) -> list[str]:
    return [n for n in corpus if is_doubles_name(n)]


def _old_teams_agree(ours: object, theirs: object) -> bool:
    """The relation as it stood before #4095: whole-string pair equality.

    Written out rather than recovered from git, so the before/after numbers in
    this file are produced by code a reader can see on the page. It is the exact
    body the doubles branch of `tennis_names_agree` used to hold, and
    `TestTheAgreementRowOnThePinnedDay` installs it to take the "before" read.
    """
    a, b = doubles_key(ours), doubles_key(theirs)
    return a is not None and a == b


def _fixtures():
    service = StatPalAPIService.__new__(StatPalAPIService)
    return service._parse_tennis_daily(json.loads(DOUBLES_FIXTURE.read_text()))


class TestTheTwoRealMisses:
    """The rows the issue was filed for, at the level of the name relation."""

    @pytest.mark.parametrize(
        "ours,theirs",
        [
            ("Carpico / Filin N", "Carpico/ Filin"),
            ("Hsieh S-W / Ostapenko", "Hsieh S-/Ostapenko"),
        ],
    )
    def test_they_agree_now_and_did_not_before(self, ours, theirs):
        assert not _old_teams_agree(ours, theirs), (
            "this pair is only interesting because the old relation refused it "
            "— if it agreed before, the test proves nothing"
        )
        assert doubles_teams_agree(ours, theirs)

    def test_the_initial_is_read_off_the_end_of_the_side_not_the_front(self):
        """Both vocabularies write a doubles side surname-FIRST.

        Ours is `Filin N` and `Hsieh S-W`; StatPal's is `Filin` and `Hsieh S-`.
        That is the opposite of the singles shape (`N. Filin`), which is why
        this is its own parser and not a reuse of `statpal_tennis_key`.
        """
        assert doubles_side_keys("Carpico / Filin N") == (
            ("carpico", None),
            ("filin", "n"),
        )
        assert doubles_side_keys("Hsieh S-/Ostapenko") == (
            ("hsieh", "s"),
            ("ostapenko", None),
        )

    def test_a_hyphenated_given_name_keeps_only_its_first_initial(self):
        """`Hsieh S-W` folds to three tokens and yields the initial `s`.

        Su-Wei's first initial, which is the one `statpal_tennis_key` compares
        on the singles side and the one StatPal's own `Hsieh S-` truncates to.
        Taking the LAST would compare `w` against `s` and re-open the miss.
        """
        assert doubles_side_keys("Hsieh S-W / Ostapenko")[0] == ("hsieh", "s")


class TestItDidNotDeleteTheDiscriminator:
    """Initial-AWARE, not initial-dropping. CERT-1890 is why this is the crux."""

    def test_two_present_initials_that_differ_are_a_refusal(self):
        assert not doubles_teams_agree("Carpico / Filin N", "Carpico/ Filin S")

    def test_a_missing_initial_is_unknown_and_never_a_disagreement(self):
        """32.5% of our field carries no given name, so this cannot be required.

        It is the same asymmetry `keys_agree` documents for singles, and it is
        the reason the relation is NOT transitive and therefore not a key.
        """
        assert doubles_teams_agree("Carpico / Filin N", "Carpico/ Filin")
        assert doubles_teams_agree("Carpico/ Filin", "Carpico / Filin S")
        assert not doubles_teams_agree("Carpico / Filin N", "Carpico/ Filin S")

    def test_a_generational_suffix_is_still_not_an_initial(self):
        """`Damm Jr` must not be read as `Damm` + an initial.

        `jr` is two characters, so the trailing-single-character rule cannot
        reach it — the property that keeps the CERT-1890 fusion out. Asserted
        rather than assumed, because "it happens not to match" is one refactor
        away from "it matches".
        """
        assert doubles_side_keys("Damm Jr / Nardi") == (
            ("damm jr", None),
            ("nardi", None),
        )
        assert not doubles_teams_agree("Damm Jr / Nardi", "Damm/ Nardi")

    def test_a_leading_single_character_is_not_stripped(self):
        """`O'Connell` folds to `o connell`, and the `o` is not an initial.

        Treating it as one is the prefix-as-cover mistake the module header
        measures — it is how `Christopher O'Connell` was compared equal to
        `Oleksandra Oliynykova`.
        """
        assert doubles_side_keys("O'Connell / Purcell") == (
            ("o connell", None),
            ("purcell", None),
        )
        assert not doubles_teams_agree("O'Connell / Purcell", "Oliynykova/ Purcell")

    def test_a_surname_is_matched_whole_and_never_as_a_prefix(self):
        assert not doubles_teams_agree("Filinski / Carpico", "Carpico/ Filin")


class TestTheWallsThatWereAlreadyThere:
    """Everything the old relation refused, still refused."""

    def test_a_doubles_name_never_agrees_with_a_singles_one(self):
        assert not tennis_names_agree("Carpico / Filin N", "N. Filin")
        assert not tennis_names_agree("N. Filin", "Carpico/ Filin")

    @pytest.mark.parametrize("bad", ["Galloway/", "A/B/C", "/", "S-/Ostapenko"])
    def test_an_unreadable_pair_agrees_with_nothing(self, bad):
        assert doubles_side_keys(bad) is None
        assert not doubles_teams_agree(bad, "Carpico/ Filin")
        assert not doubles_teams_agree("Carpico/ Filin", bad)

    def test_a_side_that_is_initials_all_the_way_down_names_no_one(self):
        """`S-` alone is not a player, and matching it to whatever shares a
        letter is the silent substitution this module is biased against."""
        assert doubles_side_keys("Hsieh S-W / S-") is None

    def test_one_agreeing_team_is_not_a_match(self):
        assert not doubles_teams_agree("Ram / Salisbury", "Carpico/ Filin")

    def test_partner_order_still_carries_no_information(self):
        assert doubles_teams_agree("Filin N / Carpico", "Carpico/ Filin")


class TestTheIdentityDidNotMove:
    """`doubles_key` is the identity; only the JOIN was widened.

    The distinction is load-bearing and easy to lose. `register_identity`, the
    twin sweep's `block_key` and the agreement row's denominator all score on
    `doubles_key`. Had the widening gone into that function instead, it would
    have silently redefined what the D50 gate measures — and it would have
    fused our own twin rows, which is exactly the finding #2878 exists to keep
    visible.
    """

    def test_two_spellings_of_one_team_are_still_two_identities(self):
        assert doubles_key("Hsieh S-W / Ostapenko") != doubles_key("Hsieh/Ostapenko")
        assert doubles_teams_agree("Hsieh S-W / Ostapenko", "Hsieh/Ostapenko"), (
            "…and yet they AGREE — which is what makes the fixture ambiguous "
            "rather than silently stamped onto one of them"
        )

    def test_a_fixture_our_register_holds_twice_resolves_as_ambiguous(self):
        got = resolve_tennis_name(
            "Hsieh S-/Ostapenko", ["Hsieh S-W / Ostapenko", "Hsieh/Ostapenko"]
        )
        assert got.outcome == AMBIGUOUS
        assert got.candidates == ("Hsieh S-W / Ostapenko", "Hsieh/Ostapenko")

    def test_a_fixture_our_register_holds_once_still_resolves(self):
        got = resolve_tennis_name(
            "Carpico/ Filin", ["Carpico / Filin N", "Ram / Salisbury"]
        )
        assert got.outcome == MATCHED
        assert got.matched == "Carpico / Filin N"

    def test_the_separator_fold_is_untouched(self):
        assert doubles_key("Golubic / Waltert") == doubles_key("Waltert/Golubic")


class TestTheWholeCorpusNotJustTheTwoCases:
    """1,674 real doubles names. A widening is only as good as its sweep."""

    def test_the_eligible_denominator_is_real(self, corpus_doubles):
        """50 of 1,674 names carry an initial on at least one side — 2.99%.

        Asserted because every count below is scoped to this population, and a
        sweep whose eligible set had silently gone to zero would pass every one
        of them while proving nothing (the vacuous-census trap).
        """
        assert len(corpus_doubles) == 1674
        eligible = [
            n
            for n in corpus_doubles
            if (keys := doubles_side_keys(n)) and any(k[1] for k in keys)
        ]
        assert len(eligible) == 50

    def test_the_widening_made_nothing_unreadable(self, corpus_doubles):
        """A stricter parser is the way a widening quietly loses rows."""
        old = {n for n in corpus_doubles if doubles_key(n) is not None}
        new = {n for n in corpus_doubles if doubles_side_keys(n) is not None}
        assert len(old) == 1674
        assert new == old

    def test_it_gained_eighteen_pairs_and_lost_none(self, corpus_doubles):
        gained, lost = self._delta(corpus_doubles)
        assert lost == set(), "a widening that REFUSES something is not a widening"
        assert len(gained) == 18

    def test_every_gained_pair_is_one_team_written_two_ways(self, corpus_doubles):
        """The shape check, and the reason a count alone would not do.

        Eighteen new agreements is the right number of pairs; this asserts they
        are the right pairs. Each must be the SAME two surnames differing only
        in an initial one spelling carries and the other does not —
        `Rojer J-J / Winegar` beside `Rojer/Winegar`. Anything else in this set
        would be two different teams fused, which is the failure mode the whole
        design is arranged against, and it would pass a count.
        """
        gained, _ = self._delta(corpus_doubles)
        for a, b in sorted(gained):
            ka, kb = doubles_side_keys(a), doubles_side_keys(b)
            assert {k[0] for k in ka} == {k[0] for k in kb}, (a, b)
            initials_a = {k[0]: k[1] for k in ka}
            initials_b = {k[0]: k[1] for k in kb}
            differing = [s for s in initials_a if initials_a[s] != initials_b[s]]
            assert differing, (a, b, "identical keys cannot be a GAINED pair")
            for surname in differing:
                assert None in (initials_a[surname], initials_b[surname]), (
                    a,
                    b,
                    surname,
                    "two initials that are both present and differ must never "
                    "agree — that would be the CERT-1890 fusion",
                )

    def test_the_two_filed_rows_are_in_the_gained_set(self, corpus_doubles):
        gained, _ = self._delta(corpus_doubles)
        flat = {frozenset(p) for p in gained}
        assert frozenset({"Carpico / Filin N", "Carpico/Filin"}) in flat
        assert frozenset({"Hsieh S-W / Ostapenko", "Hsieh/Ostapenko"}) in flat

    @staticmethod
    def _delta(names: list[str]) -> tuple[set, set]:
        """Agreeing pairs among our OWN doubles names, before vs after.

        Blocked on a shared surname so this is a grouping and not 1,674² —
        every pair either relation can produce shares at least one whole
        surname, so the block cannot hide one.
        """
        buckets: dict[str, set[str]] = {}
        for n in names:
            keys = doubles_side_keys(n)
            if keys is None:
                continue
            for surname, _initial in keys:
                buckets.setdefault(surname, set()).add(n)
        old: set[tuple[str, str]] = set()
        new: set[tuple[str, str]] = set()
        for bucket in buckets.values():
            ordered = sorted(bucket)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1 :]:
                    if _old_teams_agree(a, b):
                        old.add((a, b))
                    if doubles_teams_agree(a, b):
                        new.add((a, b))
        assert len(old) == 159, (
            "the module header's measured figure — if this moved, the corpus "
            "changed and every number in this class needs re-reading"
        )
        return new - old, old - new


class TestTheAgreementRowOnThePinnedDay:
    """What moved on `tennis_doubles`, measured rather than argued (#4095's ask).

    The pinned 2026-09-08 doubles payload against production's nine doubles
    rows from the same minute. This is the row's own join, not the linker's:
    `pair_tennis_sides` resolves a twin by ASSIGNMENT over the whole candidate
    graph, where `classify_fixture` refuses it as AMBIGUOUS. That difference is
    deliberate and worth seeing side by side — a measurement may pick a
    pairing; the thing that WRITES a fixture id may not.
    """

    @staticmethod
    def _join(agree):
        fixtures = [
            Side(
                ref=f.fixture_id, home=f.home_team, away=f.away_team, start=f.start_time
            )
            for f in _fixtures()
        ]
        rows = [
            Side(ref=str(i), home=h, away=a, start=datetime.fromisoformat(t))
            for i, h, a, t in LIVE_ROWS
        ]
        # Patched on the DEFINING module, not on the agreement module, because
        # `authority_tennis_agreement` binds `tennis_names_agree` by value at
        # import: replacing the name there leaves the real relation in place and
        # the "before" run silently reports the "after" numbers. Swapping
        # `doubles_teams_agree` instead reaches every caller, since
        # `tennis_names_agree` looks it up in module globals at call time.
        with patch("app.utils.authority_tennis_names.doubles_teams_agree", agree):
            return pair_tennis_sides(fixtures, rows, draw=DOUBLES)

    def test_the_two_false_absences_are_gone(self):
        """`statpal_only` 2 → 0. Both were matches we held all along.

        `statpal_only` is the row's way of saying *"StatPal has a fixture we do
        not"*. For these two that was false, and a false entry there is the
        worst kind: it points at the venue when the defect is ours.
        """
        before, after = self._join(_old_teams_agree), self._join(doubles_teams_agree)
        assert [s.ref for s in sorted(before.statpal_only, key=lambda s: s.ref)] == [
            "2632636",
            "2633066",
        ]
        assert after.statpal_only == []

    def test_the_governing_pairing_goes_from_four_of_eleven_to_six_of_nine(self):
        before, after = self._join(_old_teams_agree), self._join(doubles_teams_agree)

        def scored(join):
            return len(join.paired), (
                len(join.paired) + len(join.statpal_only) + len(join.ours_only)
            )

        assert scored(before) == (4, 11)
        assert scored(after) == (6, 9)

    def test_the_ghost_row_of_each_twin_is_what_stays_unpaired(self):
        """3 `ours_only` rows after, and none of them is a fixture we missed.

        `15307337` and `15307402` are the id-less `tennis_other` halves of two
        twins (#2878), and `15308219` is the next round, which had not been
        played. The row is left saying we hold rows StatPal does not — which is
        true, and is the twin finding, not a join defect.
        """
        after = self._join(doubles_teams_agree)
        assert sorted(s.ref for s in after.ours_only) == [
            "15307337",
            "15307402",
            "15308219",
        ]

    def test_the_widening_added_no_refusals(self):
        before, after = self._join(_old_teams_agree), self._join(doubles_teams_agree)

        def counted(join):
            return {k: len(v) for k, v in join.refusals.items() if v}

        assert counted(after) == counted(before) == {}
