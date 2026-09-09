"""A doubles name that names nobody is reported as unreadable, not as missing.

#4095 follow-up `ALIGN-DOUBLES-READABILITY-CONTRACT` (attached by the bus to
CERT-2336). Pillar: TRUTH — a receipt that says something false about its own
pass. It rides #4095's ship and is not a ship of its own.

## the defect

#4095 replaced the doubles JOIN with `doubles_teams_agree`, which reads a side
through `doubles_side_keys`. It did not move the two PREFLIGHTS that stand in
front of that join and decide whether a doubles name is readable at all; both
still asked `doubles_key`, the doubles IDENTITY. The two are not the same
question and they disagree on exactly one class:

    doubles_key("S-/ Ostapenko")        -> ("ostapenko", "s")   readable
    doubles_side_keys("S-/ Ostapenko")  -> None                 names nobody

`S-` is initials all the way down. `_doubles_player_key` refuses it for the
reason `statpal_tennis_key` refuses an initials-only singles name — matching it
to whatever shares a letter is the silent failure the names module is biased
against. But the preflight let it through, the join then agreed with nothing,
and the fixture came back:

* `classify_fixture`  -> `UNMATCHED`      "StatPal has a match we do not"
* `resolve_tennis_name` -> `NO-CANDIDATE` "we do not hold this player"

Both are statements about OUR REGISTER, made because of a failure in OUR PARSER,
and both send a person to look for a row that may well be sitting right there —
`Hsieh S-W / Ostapenko` was on the live board the day #4095 was measured. That is
the false-absence class #4095 exists to kill, produced from the other end. Under
the marquee axiom (standing notice 27) a "the venue has one and we do not" claim
is the one thing this lane must never say carelessly.

Both gates now ask `doubles_side_keys`, so the readability a preflight tests is
the readability the join performs, by construction and not by agreement.

## what this file will not let you get away with

* **The live count is ZERO and this file says so out loud.** Read against
  StatPal's own tennis endpoints on 2026-09-09 (notice 26a: the venue's API, not
  our tables) — `livescores` + `daily/d1` + `daily/d2`, 17 fixtures, 13 distinct
  doubles names — nothing was in the gap. Nor is anything in the 1,674-name
  pinned register corpus. This is a latent contract defect, not a live miss, and
  `TestTheEligiblePopulationIsHonestlyZero` asserts the zero rather than
  reporting a green run that could have been vacuous.
* **Tightening a gate can cost links.** It cannot here, and that is proved twice:
  once as the containment `doubles_side_keys(n) is not None` ⟹
  `doubles_key(n) is not None` over every doubles name in both corpora, and once
  as the whole pinned-day verdict table being byte-identical before and after.
* **`doubles_key` is not deprecated by this.** It is still the identity that
  `register_identity`, the twin sweep's block key and the agreement row's
  denominator score on, and moving it would move the D50 gate's scoring. This
  changes two READABILITY gates and nothing else.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.statpal_api import StatPalFixture
from app.tasks.link_tennis_statpal_fixtures import (
    VERDICT_AMBIGUOUS,
    VERDICT_DOUBLES_UNREADABLE,
    VERDICT_LINK,
    VERDICT_UNMATCHED,
    classify_fixture,
)
from app.utils.authority_tennis_names import (
    NO_CANDIDATE,
    UNREADABLE,
    doubles_key,
    doubles_side_keys,
    doubles_teams_agree,
    is_doubles_name,
    register_identity,
    resolve_tennis_name,
)

from tests.test_link_tennis_statpal_fixtures import LIVE_POOL, _doubles_fixtures

CORPUS = Path(__file__).parent / "fixtures" / "tennis_name_corpus_20260905.json"
#: Every doubles side that reads as a clean pair of STRINGS but names no player.
#:
#: Constructed, and they have to be: the point of this file is that the venue
#: does not currently serve one (`TestTheEligiblePopulationIsHonestlyZero`), so a
#: fixture-only file would test the gap by never entering it. Each is a real
#: shape though — `S-` is precisely how StatPal truncated Hsieh Su-Wei's given
#: name on 2026-09-08 (`Hsieh S-`), and the first entry is that same truncation
#: applied to the surname slot as well.
NAMES_NOBODY = (
    "S-/ Ostapenko",  # one partner truncated to nothing but an initial
    "S- / J R",  # both partners
    "A/B",  # the degenerate case, no spacing
)


def _fixture(home: str, away: str, when: str = "2026-09-08T23:10:00+00:00"):
    """A StatPal doubles fixture with a start time inside `LIVE_POOL`'s window."""
    return StatPalFixture(
        fixture_id="9999999",
        home_team=home,
        away_team=away,
        start_time=datetime.fromisoformat(when),
        league="Wta - Doubles: Us Open (Usa), Hard",
        status="scheduled",
    )


def _corpus_doubles() -> list[str]:
    return [n for n in json.loads(CORPUS.read_text())["names"] if is_doubles_name(n)]


def _statpal_doubles() -> list[str]:
    names: set[str] = set()
    for f in _doubles_fixtures():
        for n in (f.home_team, f.away_team):
            if is_doubles_name(n):
                names.add(n)
    return sorted(names)


class TestTheGapIsReal:
    """The two readers disagree, and they disagree on one nameable class."""

    @pytest.mark.parametrize("name", NAMES_NOBODY)
    def test_the_old_gate_calls_a_name_that_names_nobody_readable(self, name):
        assert doubles_key(name) is not None, (
            "if this reds, `doubles_key` has been tightened and the gap this "
            "file guards has moved — re-derive it, do not delete the test"
        )
        assert doubles_side_keys(name) is None

    @pytest.mark.parametrize("name", NAMES_NOBODY)
    def test_and_the_join_could_never_have_agreed_with_it(self, name):
        """The whole reason the old gate produced a FALSE absence.

        A name in the gap reaches the join and the join refuses every candidate,
        including one that plainly ought to be the same team. `Ostapenko` is
        right there in both strings; `doubles_teams_agree` still says no, because
        one team agreeing is not a match and the other side names nobody.
        """
        for ours in ("Hsieh S-W / Ostapenko", "Hsieh/Ostapenko", "Mertens / Shnaider"):
            assert not doubles_teams_agree(ours, name)


class TestTheLinkerSaysUnreadableInsteadOfMissing:
    """`classify_fixture`: our parse failed, so say that and not "we lack it"."""

    @pytest.mark.parametrize("name", NAMES_NOBODY)
    @pytest.mark.parametrize("slot", ["home", "away"])
    def test_a_side_that_names_nobody_is_doubles_unreadable(self, name, slot):
        """Both slots, because StatPal's first-listed team is not our home side.

        Swept rather than spot-checked: a gate that reads only one slot passes
        every home-slot case and then publishes the away-slot ones as
        `UNMATCHED`, which is the same false absence surviving in half the
        population. (A dropped-away-check mutant lived through the first cut of
        this file for exactly that reason.)
        """
        other = "Mertens / Shnaider"
        fixture = _fixture(name, other) if slot == "home" else _fixture(other, name)
        verdict, matches = classify_fixture(fixture, LIVE_POOL)
        assert (verdict, matches) == (VERDICT_DOUBLES_UNREADABLE, [])

    def test_the_gate_is_scoped_to_doubles_and_leaves_singles_alone(self):
        """`doubles and not (...)`: the first conjunct is load-bearing.

        Without it every SINGLES fixture is measured by a doubles reader, which
        refuses any name with no `/` in it — so the whole singles draw becomes
        `DOUBLES_UNREADABLE` and the linker stops working entirely. The pinned
        singles corpus catches that in its own file; this asserts it here so the
        gate's scope cannot be read out of one file at a time.
        """
        singles = _fixture("Y. Bu", "M. Zheng", when="2026-09-03T22:05:00+00:00")
        verdict, _ = classify_fixture(
            singles,
            [
                {
                    "id": 15301172,
                    "sport_key": "tennis_atp_us_open",
                    "home": "Bu Yunchaokete",
                    "away": "Michael Zheng",
                    "commence_time": datetime.fromisoformat(
                        "2026-09-03T22:05:00+00:00"
                    ),
                    "sport_id": 1,
                }
            ],
        )
        assert verdict == VERDICT_LINK

    def test_the_verdict_it_replaces_is_the_one_that_accuses_our_register(self):
        """Red-first, stated as the before/after it actually is.

        Reverting the gate to `doubles_key` puts this fixture back on the path
        that ends in `UNMATCHED` — which the linker publishes as a receipt saying
        StatPal has a match we do not, about a match whose away side we hold on
        the pinned day and whose home side we never read.
        """
        fixture = _fixture("S-/ Ostapenko", "Mertens / Shnaider")
        old_gate_passes = bool(
            doubles_key(fixture.home_team) and doubles_key(fixture.away_team)
        )
        assert old_gate_passes, "the old gate has to admit it, or there is no bug"

        # What the old gate's fall-through reached: the same window filter and
        # the same join the task runs, with nothing left to stop it.
        assert classify_fixture(fixture, LIVE_POOL)[0] != VERDICT_UNMATCHED

    def test_we_do_hold_the_match_it_used_to_call_missing(self):
        """The claim above is only damning if the row is really there."""
        assert any(
            c["home"] == "Hsieh S-W / Ostapenko" and c["away"] == "Mertens / Shnaider"
            for c in LIVE_POOL
        )


class TestTheResolverSaysUnreadableInsteadOfNoCandidate:
    """`resolve_tennis_name`, the same defect one module down."""

    CANDIDATES = ("Hsieh S-W / Ostapenko", "Hsieh/Ostapenko", "Mertens / Shnaider")

    @pytest.mark.parametrize("name", NAMES_NOBODY)
    def test_a_side_that_names_nobody_is_unreadable(self, name):
        assert resolve_tennis_name(name, self.CANDIDATES).outcome == UNREADABLE

    def test_which_is_the_answer_the_singles_arm_has_always_given(self):
        """Parity is the argument, not taste.

        An initials-only SINGLES name has always resolved `UNREADABLE`, because
        `statpal_tennis_key` refuses it. The doubles arm answered `NO-CANDIDATE`
        for the identical defect, and the two outcomes route a reader to two
        different places — one to the parser, one to the register.
        """
        assert resolve_tennis_name("S.", ("Hsieh Su-Wei",)).outcome == UNREADABLE
        assert resolve_tennis_name("S-/ Ostapenko", self.CANDIDATES).outcome == (
            UNREADABLE
        )

    def test_a_readable_doubles_name_we_simply_lack_is_still_no_candidate(self):
        """The distinction has to cut both ways or it is not a distinction.

        A pair we CAN read and do not hold keeps saying so. If this reds, the fix
        has swallowed real absences into the parser bucket, which is the same
        dishonesty pointing the other way.
        """
        assert (
            resolve_tennis_name("Bolelli/ Vavassori", self.CANDIDATES).outcome
            == NO_CANDIDATE
        )


class TestTighteningCannotCostALink:
    """Both halves of the safety argument, as properties rather than spot checks."""

    def test_the_new_gate_is_strictly_stricter(self):
        """`doubles_side_keys` readable ⟹ `doubles_key` readable, everywhere.

        Over both corpora at once: our register's 1,674 doubles names and every
        doubles name in the pinned StatPal payload. Containment in this direction
        is what makes the change a tightening; a counterexample would mean the
        new gate REFUSES something the old one admitted AND the join accepts,
        which is the one way this could lose a link.
        """
        names = _corpus_doubles() + _statpal_doubles()
        assert len(names) > 1_600, "the corpora did not load; a vacuous pass"
        leaks = [n for n in names if doubles_side_keys(n) and doubles_key(n) is None]
        assert leaks == []

    def test_the_pinned_days_verdicts_are_byte_identical(self):
        """The whole live doubles board, before and after, verdict for verdict.

        Not a count of links: the full table, so a fixture that changed from
        `LINK` to `AMBIGUOUS` (or the reverse) reds even though the totals hold.

        The "before" is taken by putting the OLD reader back in the gate — the
        preflight only ever used its truthiness, so binding the task module's
        `doubles_side_keys` name to `doubles_key` reproduces the old behaviour
        exactly. The join is untouched by that: it reaches the names module's own
        `doubles_side_keys` through `tennis_names_agree`, which is the whole
        point — the two readers were reachable independently, and now the gate
        cannot be given a reader the join does not use.
        """
        expected = {
            ("Carpico/ Filin", "Ram/ Salisbury"): VERDICT_LINK,
            ("Hsieh S-/Ostapenko", "Mertens/ Shnaider"): VERDICT_AMBIGUOUS,
            ("Gonzalez/ Molteni", "Granollers/ Zeballos"): VERDICT_AMBIGUOUS,
            ("Heliovaara/ Patten", "Cabral/ Tracy"): VERDICT_LINK,
            ("Nys/ Roger-Vasselin", "Andreozzi/ Guinard"): VERDICT_LINK,
            ("Siniakova/ Townsend", "Bucsa/ Melichar-Martinez"): VERDICT_LINK,
        }

        def _table():
            return {
                (f.home_team, f.away_team): classify_fixture(f, LIVE_POOL)[0]
                for f in _doubles_fixtures()
            }

        after = _table()
        assert len(after) == 6, "the pinned payload moved; re-derive the table"
        assert after == expected

        with patch(
            "app.tasks.link_tennis_statpal_fixtures.doubles_side_keys",
            new=doubles_key,
        ):
            before = _table()
        assert before == expected

    def test_the_identity_did_not_move(self):
        """`doubles_key`'s consumers are untouched, asserted not hoped for.

        `register_identity` is what the D50 gate's denominator is scored on. This
        ship changes two gates in front of the join and must not be visible to
        it — including for a name in the gap, which `register_identity` keys the
        same way it always did.
        """
        assert register_identity("Hsieh S-W / Ostapenko") == tuple(
            sorted(doubles_key("Hsieh S-W / Ostapenko"))
        )
        assert register_identity("S-/ Ostapenko") == tuple(
            sorted(doubles_key("S-/ Ostapenko"))
        )
        assert register_identity("Hsieh S-W / Ostapenko") != register_identity(
            "Hsieh/Ostapenko"
        ), "the twin (#2878) must stay two identities; that is D39's, not ours"


class TestTheEligiblePopulationIsHonestlyZero:
    """How many real names are in the gap today. None, and that is the finding.

    A guard whose population is empty passes for free, so the emptiness is
    asserted as a MEASUREMENT with its denominator, and the constructed names
    above carry the behaviour. If a later day puts a real name in the gap this
    class reds — which is the correct alarm, because it means the venue started
    serving a shape we would have mis-receipted before today.
    """

    def test_no_name_in_our_register_is_in_the_gap(self):
        doubles = _corpus_doubles()
        assert len(doubles) == 1674, "the pinned corpus moved; re-derive the number"
        gap = [n for n in doubles if doubles_key(n) and doubles_side_keys(n) is None]
        assert gap == []

    def test_no_name_in_the_pinned_statpal_payload_is_in_the_gap(self):
        names = _statpal_doubles()
        assert len(names) == 12, "the pinned payload moved; re-derive the number"
        gap = [n for n in names if doubles_key(n) and doubles_side_keys(n) is None]
        assert gap == []

    def test_the_constructed_names_are_therefore_load_bearing(self):
        """Said plainly, in the suite, so nobody reads this file as a live fix.

        Zero occurrences measured. The ship is that the two gates can no longer
        drift apart, and the receipt a reader acts on can no longer blame our
        register for our parser.
        """
        assert all(
            doubles_key(n) and doubles_side_keys(n) is None for n in NAMES_NOBODY
        )
