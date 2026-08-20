"""A source-priority gate on every `events.commence_time` repair write (#2018).

Queue 385 item 4. #2018 Game 1 was ruled a DO-NOW and then sat **BLOCKED, not
gated** — the adjudication was complete and there was simply no rail on the
deployed tree that could perform the write:

* `event-espn-id` excludes it **by design** (*"ONE COLUMN: espn_id… not
  commence_time"*, ruling (a) — the other fields oscillate and #1981's writer
  owns them);
* `repair_inverted_mlb_events` does the exact re-date needed, but its candidate
  predicate takes only **inverted** rows (`completed_at < commence_time`), and
  `14788546` is not inverted — its `completed_at` (08-18 01:37Z) is properly
  *after* its `commence_time` (08-17 17:40Z). The row is simply on the wrong
  first pitch;
* `db-query` is SELECT-only.

So the gap is one explicit-id arm, not a new rail. That is what this file covers,
plus the thing the queue actually asks for: **the write must pass a source-priority
gate, and `espn` outranks `odds_api`.**

## Why the gate matters more than the one row

The rail previously stamped `commence_time_source = 'mlb_schedule_repair'`
unconditionally. Unconditional is fine while the only caller is MLB ground truth,
and it is a manufacturer the moment a second caller appears — which is exactly the
#1980 shape one table over: a writer with no authority check, correct today
because of who happens to call it.

The gate is therefore written as a **predicate over (current, incoming)** and
tested on pairs the MLB rail itself will never produce. A gate that can only be
exercised by its single well-behaved caller is not a gate.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.event_registry import commence_time_write_authorized

UTC = timezone.utc


class TestSourcePriorityGate:
    """Priority runs espn, then statpal, then odds_api, then the prediction
    markets — and ties LOSE.

    Spelled out in words rather than as a slash-separated chain on one line:
    gitleaks' `generic-api-key` rule scores that chain at entropy 3.73 and fails
    the scan on it. A false positive, but the backstop is worth more than the
    shorthand, so the prose moves rather than the rule.
    """

    def test_odds_api_may_not_overwrite_espn(self):
        ok, reason = commence_time_write_authorized("espn", "odds_api")
        assert ok is False
        assert "priority" in reason or "outrank" in reason

    def test_espn_may_overwrite_odds_api(self):
        ok, _reason = commence_time_write_authorized("odds_api", "espn")
        assert ok is True

    def test_espn_may_overwrite_statpal(self):
        """#2018 Game 1's own shape: the row is `statpal`-sourced."""
        ok, _reason = commence_time_write_authorized("statpal", "espn")
        assert ok is True

    def test_an_equal_source_does_not_overwrite(self):
        """A tie is a refusal.

        Two readings from the same authority disagreeing is a data question, not
        a licence for whichever poll ran last to win. `_update_fields_by_priority`
        has always used strict `>`; this states it as a rule rather than leaving
        it as an operator.
        """
        ok, _reason = commence_time_write_authorized("espn", "espn")
        assert ok is False

    def test_an_unknown_current_source_is_lowest_not_highest(self):
        """Fail OPEN here is correct and fail CLOSED would be wrong.

        An unrecognised or NULL `commence_time_source` means "we do not know who
        wrote this", which must not confer immunity — otherwise the worst-provenance
        rows in the table become the only unfixable ones.
        """
        assert commence_time_write_authorized(None, "odds_api")[0] is True
        assert commence_time_write_authorized("", "odds_api")[0] is True
        assert commence_time_write_authorized("something_new", "odds_api")[0] is True

    def test_an_unknown_INCOMING_source_may_not_write(self):
        """The inverse is NOT symmetric, deliberately.

        An unknown *incoming* source has no established authority, so it ranks 0
        and loses to everything known. Unknown-beats-known in one direction and
        loses in the other is the whole point: provenance we cannot vouch for may
        be corrected, and may not correct.
        """
        assert commence_time_write_authorized("odds_api", "mystery_writer")[0] is False

    def test_the_mlb_ground_truth_rail_outranks_every_poller(self):
        """`mlb_schedule_repair` is MLB's own published schedule, matched against
        a Final with the same teams AND the same score — not a poll."""
        for poller in ("kalshi", "polymarket", "odds_api", "statpal", "espn"):
            ok, _reason = commence_time_write_authorized(poller, "mlb_schedule_repair")
            assert ok is True, f"ground truth refused against {poller}"


class TestExplicitIdArm:
    """The rail must be able to take a row its predicate does not select."""

    def test_game_1_is_not_inverted_so_the_predicate_cannot_reach_it(self):
        """Pin the premise, so the arm is not "fixed" by widening the predicate.

        #2018 Game 1: commence 08-17 17:40Z, completed_at 08-18 01:37Z. That is a
        perfectly ordinary ordering — the row is not inverted, it is on the wrong
        first pitch. Widening `_INVERTED_CANDIDATE_SQL` to catch it would pull in
        every correctly-ordered settled MLB row in the table.
        """
        from app.tasks.schedule_coverage import _classify_scored_inverted

        commence = datetime(2026, 8, 17, 17, 40, tzinfo=UTC)
        completed = datetime(2026, 8, 18, 1, 37, 20, tzinfo=UTC)
        assert completed > commence, "premise: the row is NOT inverted"

        # And the classifier, handed the TRUE start, calls it a re-date — which is
        # the action we want, reachable only if the row gets into the candidate set.
        true_start = datetime(2026, 8, 17, 22, 40, tzinfo=UTC)
        assert _classify_scored_inverted(completed, commence, true_start) == "redate"

    def test_the_candidate_sql_accepts_an_explicit_id_list(self):
        """The arm exists and is parameterised, not hardcoded to one game."""
        from app.tasks.schedule_coverage import build_candidate_sql

        base = build_candidate_sql(explicit_ids=False)
        explicit = build_candidate_sql(explicit_ids=True)

        assert ":explicit_ids" in explicit
        assert ":explicit_ids" not in base
        # The invariant arm must SURVIVE — the explicit list is a union, never a
        # replacement. A rail that only does what it is told stops self-healing.
        assert "completed_at < e.commence_time" in explicit

    def test_an_explicit_id_does_not_bypass_the_ground_truth_gate(self):
        """Naming a row selects it for CONSIDERATION, never for a blind write.

        Every write in this rail is gated on an MLB Final matching the row's teams
        AND final score. The explicit arm changes which rows are looked at; it must
        not change what authorises the write, or "attended" degrades into "typed an
        id".
        """
        import inspect

        from app.tasks import schedule_coverage

        src = inspect.getsource(schedule_coverage.repair_inverted_mlb_events)
        # the ground-truth lookup must not be inside a not-explicit branch
        assert "_mlb_final_for" in src
        assert "if explicit" not in src.replace("if explicit_ids", ""), (
            "the ground-truth gate must not be conditional on how the row was selected"
        )


class TestTheRailRefusesAnUnauthorizedRedate:
    """The gate, exercised through the rail's own write path."""

    def test_redate_is_skipped_when_the_gate_refuses(self):
        from app.tasks.schedule_coverage import authorize_redate

        # a row already carrying a HIGHER-authority time than the incoming writer
        ok, reason = authorize_redate(current_source="espn", incoming_source="odds_api")
        assert ok is False and reason

    def test_redate_proceeds_for_ground_truth(self):
        from app.tasks.schedule_coverage import authorize_redate

        ok, _reason = authorize_redate(
            current_source="statpal", incoming_source="mlb_schedule_repair"
        )
        assert ok is True
