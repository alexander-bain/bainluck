"""#5906 — the futures detail page stops publishing prose the Discover card refuses.

THE READER'S COMPLAINT, verbatim, and every specimen below is taken from it.
``/futures/8641774`` (*Brazil Série B: Winner*) served, at 11:57Z on 2026-09-13:

    hero     Juventude 50%
    caption  "As Brazil's Série B heats up, Novorizontino has surged to the
              top, shifting the dynamics of the league..."
    table    Novorizontino  —

Three statements about one board, no two of which agree. The caption crowns a
club the hero does not, and the table declines to give that club a number at all
(#5876 withheld its refuted midpoint).

WHY THIS IS AN ADOPTION AND NOT A NEW POLICY. ``is_hook_stale`` has gated the
Discover card since ``app/utils/hook_staleness.py`` shipped; the detail
serializer published ``market.hook_description`` raw. The Brazil hook is policy
1, generated 2026-06-29 (76 days before the reading) and names a leader that has
since changed — it trips rules 0, 1 AND 2, and the feed had been refusing it the
whole time.

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it:

- A rule that suppressed EVERY hook would pass every suppression assertion here.
  So ``test_a_publishable_hook_survives_the_gate`` is the control: a policy-2,
  one-day-old hook whose named leader is still the leader and whose legs are all
  priced must come through the serializer UNCHANGED. If that test is ever
  deleted or weakened, the rest of this file proves nothing.
- ``hook_names_unpriced_outcome`` is inert on today's production population (0
  of 11,444 open hooks are policy 2, so rule 0 fires first on all of them). It
  is therefore tested as a UNIT, against the clause that will outlive that
  count, not only through the route.
- A bare substring test would fire on the word "sports" via the Série B club
  named **Sport**. That false positive is asserted SPARED by name, from the same
  board, because it is the one the word-boundary rule exists for.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.hook_staleness import (
    CURRENT_HOOK_POLICY_VERSION,
    HOOK_POLICY_METADATA_KEY,
    MIN_MATCHABLE_OUTCOME_NAME,
    hook_names_unpriced_outcome,
)

#: The caption production served, verbatim.
_BRAZIL_HOOK = (
    "As Brazil's Série B heats up, Novorizontino has surged to the top, "
    "shifting the dynamics of the league and intensifying the race for promotion."
)


class TestHookNamesUnpricedOutcome:
    """The clause that survives the policy-2 transition (unit level)."""

    def test_fires_when_the_hook_names_a_leg_the_page_withholds(self):
        assert hook_names_unpriced_outcome(
            hook_description=_BRAZIL_HOOK,
            unpriced_outcome_names=["Novorizontino"],
        )

    def test_spares_the_same_hook_when_that_leg_is_priced(self):
        # The caller passes only the WITHHELD names, so a priced Novorizontino
        # simply never reaches the rule. This is the honest-market control.
        assert not hook_names_unpriced_outcome(
            hook_description=_BRAZIL_HOOK, unpriced_outcome_names=[]
        )

    def test_a_hook_naming_a_different_withheld_leg_is_spared(self):
        assert not hook_names_unpriced_outcome(
            hook_description=_BRAZIL_HOOK,
            unpriced_outcome_names=["Ponte Preta", "Avaí"],
        )

    def test_the_club_named_sport_is_not_matched_by_the_word_sports(self):
        # The whole reason for word boundaries. Série B really does carry a club
        # called Sport, and prose about "sports" is not prose about that club.
        assert not hook_names_unpriced_outcome(
            hook_description="A busy weekend across Brazilian sports.",
            unpriced_outcome_names=["Sport"],
        )

    def test_the_club_named_inter_is_not_matched_by_the_word_winter(self):
        # The LEADING boundary specifically. "Sport"/"sports" only exercises the
        # trailing one — drop the leading `\b` and that test still passes, while
        # `Inter` starts matching inside "winter". Both edges, both directions.
        assert not hook_names_unpriced_outcome(
            hook_description="A winter break has slowed the run-in.",
            unpriced_outcome_names=["Inter"],
        )

    def test_the_club_named_sport_is_matched_when_the_hook_means_the_club(self):
        # The other direction, so the boundary rule cannot pass by refusing
        # everything — that would be the same vacuity in miniature.
        assert hook_names_unpriced_outcome(
            hook_description="Sport have climbed into the promotion places.",
            unpriced_outcome_names=["Sport"],
        )

    @pytest.mark.parametrize("needle", ["Avaí", "Ceará"])
    def test_accented_names_bound_correctly(self, needle):
        # `\b` is Unicode-aware for str patterns; an ASCII-only boundary would
        # mis-handle the trailing accented character.
        assert hook_names_unpriced_outcome(
            hook_description=f"{needle} have steadied after a poor run.",
            unpriced_outcome_names=[needle],
        )

    @pytest.mark.parametrize("needle", ["C", "D", "Yes", "No"])
    def test_slot_names_too_short_to_carry_identity_are_ignored(self, needle):
        # A one- or two-character needle matches almost any sentence; suppressing
        # on it would empty hooks for markets with nothing wrong with them.
        assert len(needle) < MIN_MATCHABLE_OUTCOME_NAME
        assert not hook_names_unpriced_outcome(
            hook_description="Contracts C and D are quiet; No side has moved.",
            unpriced_outcome_names=[needle],
        )

    def test_matching_is_case_insensitive(self):
        assert hook_names_unpriced_outcome(
            hook_description="novorizontino lead the table.",
            unpriced_outcome_names=["Novorizontino"],
        )

    @pytest.mark.parametrize("hook", [None, ""])
    def test_no_hook_is_not_a_suppression(self, hook):
        assert not hook_names_unpriced_outcome(
            hook_description=hook, unpriced_outcome_names=["Novorizontino"]
        )

    def test_a_none_name_in_the_list_does_not_raise(self):
        # `outcomes` rows can carry a null name; the caller passes them straight
        # through and a crash here would 500 the detail page.
        assert not hook_names_unpriced_outcome(
            hook_description=_BRAZIL_HOOK, unpriced_outcome_names=[None, ""]
        )

    def test_a_name_containing_regex_metacharacters_is_matched_literally(self):
        # Outcome names are venue strings, not patterns. An unescaped "+" or "("
        # would either raise or match the wrong thing.
        #
        # This one also pins the per-edge boundary: an unconditional `\b` on
        # both sides makes this needle unmatchable forever, silently, because
        # neither "(" nor ")" can sit on a word boundary. It failed exactly that
        # way on the first run of this file.
        assert hook_names_unpriced_outcome(
            hook_description="The O/U 2.5 (Over) leg is the one moving.",
            unpriced_outcome_names=["(Over)"],
        )

    def test_a_name_with_one_punctuated_edge_binds_only_the_other_edge(self):
        # Asymmetric: "+3.5" opens on punctuation and closes on a digit, so the
        # leading boundary must be dropped and the trailing one kept.
        assert hook_names_unpriced_outcome(
            hook_description="The +3.5 side has taken the money.",
            unpriced_outcome_names=["+3.5"],
        )
        assert not hook_names_unpriced_outcome(
            hook_description="The +3.55 side has taken the money.",
            unpriced_outcome_names=["+3.5"],
        )


def _market(
    *,
    hook_description,
    hook_generated_at,
    hook_leader_at_generation,
    policy_version,
    outcomes,
):
    metadata = None
    if policy_version is not None:
        metadata = {HOOK_POLICY_METADATA_KEY: policy_version}
    return SimpleNamespace(
        id=8641774,
        name="Brazil Série B: Winner",
        description=None,
        category="sports",
        source="polymarket",
        external_id="serie-b",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=1,
        llm_sport_category="soccer",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=hook_description,
        hook_generated_at=hook_generated_at,
        hook_leader_at_generation=hook_leader_at_generation,
        image_url=None,
        category_tags=[],
        market_metadata=metadata,
        outcomes=outcomes,
    )


def _outcome(oid, name, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"club-{oid}",
        current_probability=prob,
        current_american_odds=110,
        rank=oid,
        rank_change_24h=None,
        probability_change_24h=0.01,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=None,
    )


#: Market 8641774's honest rows as production served them, plus the withheld
#: leg the caption names. Juventude is the hero the reader actually sees.
_BOARD = [
    _outcome(1, "Novorizontino", 0.4815),
    _outcome(2, "Juventude", 0.499),
    _outcome(3, "Avaí", 0.0205),
    _outcome(4, "Botafogo-SP", 0.018),
]


class TestTheDetailSerializerRunsTheGate:
    def test_the_brazil_caption_is_refused(self):
        from app.routes.futures import _format_market_detail

        market = _market(
            hook_description=_BRAZIL_HOOK,
            # 76 days, as production held it (2026-06-29 read on 2026-09-13).
            hook_generated_at=datetime.now(timezone.utc) - timedelta(days=76),
            hook_leader_at_generation="Novorizontino",
            policy_version=None,  # policy 1: absent, as all 11,444 rows are
            outcomes=_BOARD,
        )
        # id 1 (Novorizontino) is the leg #5876 withholds.
        detail = _format_market_detail(market, None, {1})

        assert detail["prices_withheld"] == 1
        assert detail["hook_description"] is None, (
            "the caption naming a club whose price this same response withholds "
            "must not be published"
        )
        assert detail["hook_withheld"] is True

    def test_a_publishable_hook_survives_the_gate(self):
        """THE CONTROL. Delete this and the file proves nothing.

        A rule that empties every hook would satisfy every other assertion in
        this file. This is a hook with nothing wrong with it: current policy,
        one day old, its named leader is still the leader, and every leg it
        could name carries a price.
        """
        from app.routes.futures import _format_market_detail

        hook = "Juventude have opened a gap at the top of Série B."
        market = _market(
            hook_description=hook,
            hook_generated_at=datetime.now(timezone.utc) - timedelta(days=1),
            hook_leader_at_generation="Juventude",
            policy_version=CURRENT_HOOK_POLICY_VERSION,
            outcomes=[
                _outcome(2, "Juventude", 0.499),
                _outcome(3, "Avaí", 0.0205),
                _outcome(4, "Botafogo-SP", 0.018),
            ],
        )
        detail = _format_market_detail(market, None, set())

        assert detail["prices_withheld"] == 0
        assert detail["hook_description"] == hook
        assert detail["hook_withheld"] is False

    def test_a_market_with_no_hook_reports_no_suppression(self):
        # `hook_withheld` has to tell "we refused prose" from "there was never
        # any", or a probe cannot read the key at all.
        from app.routes.futures import _format_market_detail

        market = _market(
            hook_description=None,
            hook_generated_at=None,
            hook_leader_at_generation=None,
            policy_version=CURRENT_HOOK_POLICY_VERSION,
            outcomes=[_outcome(2, "Juventude", 0.499)],
        )
        detail = _format_market_detail(market, None, set())

        assert detail["hook_description"] is None
        assert detail["hook_withheld"] is False

    def test_a_current_hook_naming_a_withheld_leg_is_still_refused(self):
        """The clause that outlives the policy-1 population, through the route.

        Everything about this hook is fresh and correctly versioned — rule 0
        cannot fire, rule 1 cannot fire, and the leader it names IS the leader.
        It is refused only because it talks about a club whose price this same
        response declines to state.
        """
        from app.routes.futures import _format_market_detail

        hook = "Juventude lead, with Novorizontino closing fast."
        market = _market(
            hook_description=hook,
            hook_generated_at=datetime.now(timezone.utc) - timedelta(hours=2),
            hook_leader_at_generation="Juventude",
            policy_version=CURRENT_HOOK_POLICY_VERSION,
            outcomes=_BOARD,
        )
        detail = _format_market_detail(market, None, {1})

        assert detail["hook_description"] is None
        assert detail["hook_withheld"] is True

    def test_a_stale_hook_naming_no_withheld_leg_is_refused(self):
        """Clause A alone, isolated — otherwise dropping it survives this file.

        The Brazil specimen trips BOTH clauses, so a gate that called only
        ``hook_names_unpriced_outcome`` would still pass
        ``test_the_brazil_caption_is_refused``. Here nothing is withheld at all,
        so the only thing that can refuse this hook is its 76-day age and its
        retired policy version.
        """
        from app.routes.futures import _format_market_detail

        market = _market(
            hook_description="Juventude have opened a gap at the top of Série B.",
            hook_generated_at=datetime.now(timezone.utc) - timedelta(days=76),
            hook_leader_at_generation="Juventude",
            policy_version=None,  # policy 1
            outcomes=[
                _outcome(2, "Juventude", 0.499),
                _outcome(3, "Avaí", 0.0205),
            ],
        )
        detail = _format_market_detail(market, None, set())

        assert detail["prices_withheld"] == 0, "no leg is withheld on this board"
        assert detail["hook_description"] is None
        assert detail["hook_withheld"] is True

    def test_a_fresh_policy_one_hook_is_refused_on_the_policy_rule_alone(self):
        """Rule 0, isolated through the route.

        A mutation battery found rules 0 and 1 masking each other: the Brazil
        specimen is policy 1 AND 76 days old, so disabling either one left the
        other firing and both mutants survived. They are separately load-bearing
        for THIS ship — rule 0 is the difference between 11,444 suppressed hooks
        and 10,629 — so each gets a specimen that only it can refuse.

        This hook is one day old and its leader has not changed. The only thing
        wrong with it is the prompt that wrote it.
        """
        from app.routes.futures import _format_market_detail

        market = _market(
            hook_description="Juventude have opened a gap at the top of Série B.",
            hook_generated_at=datetime.now(timezone.utc) - timedelta(days=1),
            hook_leader_at_generation="Juventude",
            policy_version=None,  # policy 1, and nothing else is wrong
            outcomes=[_outcome(2, "Juventude", 0.499), _outcome(3, "Avaí", 0.0205)],
        )
        detail = _format_market_detail(market, None, set())

        assert detail["hook_withheld"] is True
        assert detail["hook_description"] is None

    def test_an_aged_policy_two_hook_is_refused_on_the_age_rule_alone(self):
        """Rule 1, isolated through the route — the mirror of the test above."""
        from app.routes.futures import _format_market_detail

        market = _market(
            hook_description="Juventude have opened a gap at the top of Série B.",
            hook_generated_at=datetime.now(timezone.utc) - timedelta(days=76),
            hook_leader_at_generation="Juventude",
            policy_version=CURRENT_HOOK_POLICY_VERSION,  # current policy, just old
            outcomes=[_outcome(2, "Juventude", 0.499), _outcome(3, "Avaí", 0.0205)],
        )
        detail = _format_market_detail(market, None, set())

        assert detail["hook_withheld"] is True
        assert detail["hook_description"] is None

    def test_the_leader_is_read_after_the_display_pipeline(self):
        """Rule 2 must compare the hook against the leader the HERO prints.

        Isolated so that only the READ POSITION can decide it:

        - Novorizontino carries the higher STORED price (0.60 vs 0.499), so on
          the raw rows it is the leader — and it is also the hook's leader at
          generation, so a gate reading raw order finds no leader change.
        - #5876 withholds it, so the leader the reader actually sees, and the
          one the hero prints, is Juventude — a change, and rule 2 fires.
        - The hook names only Juventude, which is PRICED, so clause B is inert
          here and cannot be what refuses it.
        """
        from app.routes.futures import _format_market_detail

        board = [
            _outcome(1, "Novorizontino", 0.60),
            _outcome(2, "Juventude", 0.499),
            _outcome(3, "Avaí", 0.0205),
        ]
        market = _market(
            hook_description="Juventude are chasing hard at the top.",
            hook_generated_at=datetime.now(timezone.utc) - timedelta(hours=2),
            hook_leader_at_generation="Novorizontino",
            policy_version=CURRENT_HOOK_POLICY_VERSION,
            outcomes=board,
        )
        detail = _format_market_detail(market, None, {1})

        # The hero the reader sees is Juventude, not the stored frontrunner —
        # and note the SERVED ARRAY still leads with the withheld Novorizontino,
        # because withholding nulls a price without re-sorting. That is the trap
        # this test exists for: `outcomes[0]` is not the hero.
        assert detail["outcomes"][0]["name"] == "Novorizontino"
        assert detail["outcomes"][0]["probability"] is None
        assert (
            max(detail["outcomes"], key=lambda o: o.get("probability") or 0)["name"]
            == "Juventude"
        ), "the client's own rule (page.tsx:394) crowns Juventude"
        assert detail["hook_withheld"] is True, (
            "reading the leader off the raw rows would find Novorizontino still "
            "top, miss the change, and publish the hook"
        )
