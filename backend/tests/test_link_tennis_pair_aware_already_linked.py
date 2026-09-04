"""Holding the integer is not holding the link. CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED`.

`link_tennis_statpal_fixtures` refuses to WRITE a link unless both shapes land —
`events.statpal_fixture_id` and the `('statpal', 'tennis:<id>', 'game')` anchor —
because a scalar with no anchor is a row that says "linked" to one reader and
"nothing" to another (CERT-871 FOLLOW-UP `AUTHORITY-006-LINK-WRITE-OUTCOMES`).

Its `_already_linked` lookup then READ a link out of exactly the evidence the
write path had just decided was not enough:

    SELECT statpal_fixture_id, id FROM events
     WHERE statpal_fixture_id = ANY(:fixture_ids)

Two halves of one file disagreeing about what "linked" means — and the
disagreement resolves the flattering way every time, because the lookup's answer
is a SUCCESS counter. Two real states get counted as successes:

* **a half-link** — a tennis row whose scalar was written before the whitelist
  closed, or by any other writer, with no anchor behind it. It reports as
  `already_linked` on every pass forever, which is the one report under which
  nobody ever repairs it;
* **a cross-sport scalar** — `statpal_fixture_id` is not sport-scoped, and 10,941
  non-tennis rows carried one when this was written (measured 2026-09-04). The
  integer ranges do not overlap today. Nothing keeps them apart, and on the day
  they touch, a genuine tennis miss disappears into `already_linked` because an
  NFL row happens to hold that number.

## what this file is, and what the PG file next to it is

The decision — *given these holders, is this a link?* — is pure, so it is tested
here, in every shard, against every shape including the ones production has not
produced yet. `tests/integration/test_link_tennis_already_linked_pg.py` proves
the other half: that the statement finding those holders executes on a real
server with real array binding and a real varchar join.

Neither substitutes for the other. A perfect classifier fed by a statement that
raises is a task that links nothing; a perfect statement feeding a classifier
that calls a half-link a success is what shipped.
"""

from __future__ import annotations

import pytest

from app.tasks.link_tennis_statpal_fixtures import (
    PRIOR_FOREIGN_SPORT,
    PRIOR_MULTIPLE_HOLDERS,
    PRIOR_PAIRED,
    PRIOR_STATES_THAT_ARE_A_LINK,
    PRIOR_UNANCHORED,
    PRIOR_VANISHED,
    classify_prior,
)

#: A real US Open fixture id and the anchor it must be paired with.
FIXTURE = "2631673"
TENNIS_ANCHOR = "tennis:2631673"


def _holder(event_id: int, sport_key: str, *anchors: str) -> dict:
    return {"event_id": event_id, "sport_key": sport_key, "anchors": set(anchors)}


class TestOnlyBothShapesIsALink:
    def test_a_tennis_row_with_its_anchor_is_the_link(self):
        prior = classify_prior(
            FIXTURE, [_holder(301, "tennis_atp_us_open", TENNIS_ANCHOR)]
        )

        assert prior["state"] == PRIOR_PAIRED
        assert prior["event_id"] == 301

    def test_a_tennis_row_with_no_anchor_is_a_half_link_not_a_success(self):
        """The defect, stated as a test.

        Before this, the scalar alone returned `{fixture: 301}` and the caller
        read any truthy answer as "linked". The row is half-written; the report
        said the task had nothing to do.
        """
        prior = classify_prior(FIXTURE, [_holder(301, "tennis_atp_us_open")])

        assert prior["state"] == PRIOR_UNANCHORED
        assert prior["state"] not in PRIOR_STATES_THAT_ARE_A_LINK
        assert prior["expected_anchor"] == TENNIS_ANCHOR, (
            "the receipt must name the anchor that is missing, or the finding "
            "cannot be acted on without re-deriving the key by hand"
        )

    def test_an_anchor_for_a_different_fixture_does_not_pair_this_one(self):
        """Presence of *an* anchor is not presence of *the* anchor.

        A row can legitimately carry a StatPal `game` anchor for some other id —
        that is what a mis-link looks like — and counting it would make the pair
        check a row-has-any-anchor check.
        """
        prior = classify_prior(FIXTURE, [_holder(301, "tennis_atp", "tennis:2629999")])

        assert prior["state"] == PRIOR_UNANCHORED

    def test_the_pair_check_survives_extra_anchors_on_the_row(self):
        prior = classify_prior(
            FIXTURE,
            [_holder(301, "tennis_wta", "tennis:2629999", TENNIS_ANCHOR)],
        )

        assert prior["state"] == PRIOR_PAIRED


class TestASportOutsideTennisIsNotOurLink:
    def test_a_baseball_row_holding_the_integer_is_named_not_counted(self):
        """The arm that has 10,941 rows waiting for it.

        `already_linked` here would mean "StatPal's tennis match 2631673 is
        linked", on the evidence that an MLB row holds the number 2631673. The
        fixture is still missing and the report must keep saying so.
        """
        prior = classify_prior(FIXTURE, [_holder(303, "baseball_mlb")])

        assert prior["state"] == PRIOR_FOREIGN_SPORT
        assert prior["state"] not in PRIOR_STATES_THAT_ARE_A_LINK
        assert prior["event_id"] == 303
        assert prior["sport_key"] == "baseball_mlb"

    def test_an_nfl_row_with_its_own_valid_anchor_is_still_foreign(self):
        """A correctly-linked NFL row is not a correctly-linked tennis match.

        The holder can be perfectly healthy in its own sport — scalar and
        `americanfootball_nfl:` anchor both present — and still be the wrong
        answer to "is this tennis fixture linked?".
        """
        prior = classify_prior(
            "280445",
            [_holder(900, "americanfootball_nfl", "americanfootball_nfl:280445")],
        )

        assert prior["state"] == PRIOR_FOREIGN_SPORT

    @pytest.mark.parametrize(
        "sport_key", ["tennis", "tennis_atp", "tennis_wta_wimbledon", "tennis_other"]
    )
    def test_every_tennis_key_shape_reads_as_tennis(self, sport_key):
        """The keys are minted per tournament, so the space is matched by prefix.

        If this narrowed to an enumeration, the next Slam we add would classify
        as `FOREIGN_SPORT` and every one of its links would be reported as a
        problem — a false alarm is as corrosive here as a hidden one.
        """
        prior = classify_prior(FIXTURE, [_holder(301, sport_key, TENNIS_ANCHOR)])

        assert prior["state"] == PRIOR_PAIRED

    def test_an_unknown_sport_key_is_foreign_rather_than_guessed(self):
        """`statpal_id_space` returning None must not fall through to a link.

        `statpal_anchor_key(id, None)` still takes the legacy digit-derived
        branch (D55's bridge), so passing an unknown space straight through
        would silently key the fixture by digit count — the exact inference D55
        removed. Refused instead.
        """
        prior = classify_prior(FIXTURE, [_holder(301, "", TENNIS_ANCHOR)])

        assert prior["state"] == PRIOR_FOREIGN_SPORT
        assert prior["state"] not in PRIOR_STATES_THAT_ARE_A_LINK


class TestTwoHoldersIsNeverALink:
    def test_two_rows_holding_one_scalar_are_both_named(self):
        """`statpal_fixture_id` has a plain index, not a unique one.

        Nothing at the schema level forbids two rows holding one id, and the old
        dict comprehension resolved it by keeping whichever row the server
        returned last — a silent coin flip over what is, by definition, a
        duplicate worth reporting (D35: filed, not fixed here).
        """
        prior = classify_prior(
            FIXTURE,
            [
                _holder(301, "tennis_atp_us_open", TENNIS_ANCHOR),
                _holder(302, "tennis_atp_us_open"),
            ],
        )

        assert prior["state"] == PRIOR_MULTIPLE_HOLDERS
        assert prior["event_ids"] == [301, 302], (
            "both rows must be named — a receipt that reports only one of a "
            "duplicate pair cannot be acted on"
        )

    def test_it_is_not_a_link_even_when_one_holder_is_perfectly_paired(self):
        """The tempting shortcut, refused on purpose.

        One holder having both shapes does not make the OTHER row's claim on the
        id go away, and treating the pass as done leaves the duplicate in place
        with nothing counting it.
        """
        prior = classify_prior(
            FIXTURE,
            [
                _holder(301, "tennis_atp", TENNIS_ANCHOR),
                _holder(302, "tennis_atp", TENNIS_ANCHOR),
            ],
        )

        assert prior["state"] not in PRIOR_STATES_THAT_ARE_A_LINK


class TestTheLinkVocabularyCannotDriftOpen:
    def test_paired_is_the_only_state_that_counts_as_linked(self):
        assert PRIOR_STATES_THAT_ARE_A_LINK == {PRIOR_PAIRED}

    def test_every_prior_state_is_distinct(self):
        """A copy-paste that made two states equal would silently widen the
        whitelist, because membership is by value."""
        states = [
            PRIOR_PAIRED,
            PRIOR_UNANCHORED,
            PRIOR_FOREIGN_SPORT,
            PRIOR_MULTIPLE_HOLDERS,
            PRIOR_VANISHED,
        ]
        assert len(set(states)) == len(states)

    def test_vanished_is_not_a_link_and_is_not_produced_by_the_classifier(self):
        """CERT-895 repair. It is the absence of a holder, not a kind of holder.

        `classify_prior` is only ever called with at least one holder — it is
        built from rows the server returned — so `VANISHED` cannot come from
        here. It is minted by the post-lost-race re-read when the id it just
        lost to has no holder at all, and it is emphatically not a link.
        """
        assert PRIOR_VANISHED not in PRIOR_STATES_THAT_ARE_A_LINK

        produced = {
            classify_prior(FIXTURE, [_holder(301, "tennis_atp", TENNIS_ANCHOR)])["state"],
            classify_prior(FIXTURE, [_holder(301, "tennis_atp")])["state"],
            classify_prior(FIXTURE, [_holder(303, "baseball_mlb")])["state"],
            classify_prior(
                FIXTURE, [_holder(301, "tennis_atp"), _holder(302, "tennis_atp")]
            )["state"],
        }
        assert PRIOR_VANISHED not in produced

    def test_a_new_prior_state_cannot_arrive_unclassified(self):
        """The guard shaped like `test_link_tennis_write_outcomes`'s.

        Add a fifth `PRIOR_*` constant to the task and this fails here, where
        somebody has to decide whether it means "linked" — rather than defaulting
        into `unpaired` unexamined, or worse, into the success count.
        """
        from app.tasks import link_tennis_statpal_fixtures as task

        declared = {
            value
            for name, value in vars(task).items()
            if name.startswith("PRIOR_") and isinstance(value, str)
        }
        assert declared == {
            PRIOR_PAIRED,
            PRIOR_UNANCHORED,
            PRIOR_FOREIGN_SPORT,
            PRIOR_MULTIPLE_HOLDERS,
            PRIOR_VANISHED,
        }, (
            "a prior state was added or renamed. Decide whether it means the "
            f"fixture is linked before it reaches production: {sorted(declared)}"
        )
