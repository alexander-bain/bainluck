"""#2706 — the production reconciliation job: the SYSTEM files the issue.

THE BAR, from the program brief: *"nothing the authority knows about is missing,
doubled, or half-sourced for more than an hour without an issue existing — and
the SYSTEM files that issue, not a person."*

The CI gate next door replays the golden set against a frozen fixture, so it
catches a change to the matcher's LOGIC before it merges. It cannot catch the
other half, and the other half is where every failure in this program actually
came from: production data moving under a matcher nobody changed. The 8/28 wave
went unattempted with no code change. The Li–Vekic links landed on a ghost twin
with no code change. Bublik and Harris were "attached" with no price snapshots
with no code change.

So the tests here hold four lines:

1. **A check that cannot RUN is unmeasurable, never GREEN.** A failed query that
   read as GREEN would auto-CLOSE a real open issue — the worst possible
   direction for a self-healing rail to fail in.
2. **The baseline is a regression baseline.** Most golden pairs are the audit's
   open failure classes; filing them every fifteen minutes would be noise, and
   noise is how an alert channel dies.
3. **One fingerprint per SUBJECT, derived from the subject alone.** A
   content-derived fingerprint would file a fresh issue every time the count
   moved by one.
4. **The filed issue carries the receipt.** An alert that says "40 markets
   regressed" and not "here is the query that says why" hands a human the same
   dig the system just did.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

# NOTE: ``from app.tasks import matching_reconciliation`` resolves to the CELERY
# TASK of that name, not to this module — the repo names each sentinel's task
# after its module. ``import a.b.c as x`` binds the module itself.
import app.tasks.matching_reconciliation as mrec


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    """Answers each query in order; a check that queries more than it should
    runs out and raises, which is how a silently-added query gets noticed."""

    def __init__(self, results=None, scalar=0, raises=None):
        self._results = list(results or [])
        self._scalar = scalar
        self._raises = raises

    async def execute(self, stmt, params=None):
        if self._raises:
            raise self._raises
        return _Result(self._results.pop(0))

    async def scalar(self, stmt):
        if self._raises:
            raise self._raises
        return self._scalar


# =============================================================================
# The golden check is a REGRESSION check
# =============================================================================


def _fake_fixture(pairs):
    return json.dumps({"pairs": pairs})


def _pair(market_id, correct, at_capture, title="A vs B", cls="attached-correct"):
    return {
        "market_id": market_id,
        "correct_event_id": correct,
        "failure_class": cls,
        "title": title,
        "market": {"event_id_at_capture": at_capture},
    }


#: Real production id shapes, so a test cannot pass on a vocabulary that does
#: not exist. Sampled 2026-09-03 (see ``anchor_provenance``'s measurement note).
_ODDS_API_ID = "6fda1c04dbc63f6c24f795f05e32d11b"   # 29,333 events; 96.7% have odds
_KALSHI_DERIVED_ID = "pm_kalshi_KXATPMATCH-26FEB21DESHI"  # 11,584; 0 have odds
_POLYMARKET_DERIVED_ID = "pm_polymarket_113849"           # 10,394; 0 have odds


def _row(market_id, event_id, external_id=None, event_missing=False):
    """One production row: the market, where it points, the ``external_id`` of
    the event it points at, and whether that events row could be read at all.

    ``external_id=None`` with ``event_missing=False`` is a real id-less event —
    the matcher's own creation. ``event_missing=True`` is a dangling
    ``event_id``, which is a DIFFERENT claim and must not be reported as one.
    """
    return (market_id, event_id, external_id, event_missing)


def _run_golden(pairs, current_rows, accepted=None):
    """Run the check over synthetic pairs.

    ``accepted`` defaults to EMPTY, never to the shipped map: a synthetic market
    id must never collide with a real adjudicated one, and the default in a test
    should be the default in production — nothing is accepted until somebody
    adjudicates it.
    """
    # Tolerate the 2-tuples the pre-provenance tests were written with: those
    # cases turn on the pair, not on what it attached to.
    rows = [tuple(r) + (None, False)[len(r) - 2:] for r in current_rows]
    with patch.object(mrec, "FIXTURE_PATH") as fp, \
            patch.object(mrec, "ACCEPTED_ATTACHMENTS", dict(accepted or {})):
        fp.read_text.return_value = _fake_fixture(pairs)
        return asyncio.run(mrec.check_golden_pairs(_Session([rows])))


def test_a_pair_that_was_right_and_is_now_wrong_is_the_finding():
    out = _run_golden(
        [_pair(1, 500, 500, "Ann Li vs Donna Vekic")],
        [(1, 15299648)],  # moved onto the ghost twin
    )
    assert out["red"] is True
    assert out["count"] == 1
    assert out["rows"][0]["expected_event_id"] == 500
    assert out["rows"][0]["actual_event_id"] == 15299648


def test_a_pair_that_was_already_wrong_is_not_filed_every_fifteen_minutes():
    """Most of the 709 are the audit's OPEN failure classes.

    Treating a known-open failure as a fresh alert every cycle is how an alert
    channel stops being read. It is tracked by #2693, not re-filed by a beat.
    """
    out = _run_golden(
        [_pair(1, 500, None, cls="a-no-event")],
        [(1, None)],
    )
    assert out["red"] is False
    assert out["count"] == 0


def test_a_pair_that_recovers_is_counted_but_does_not_file():
    out = _run_golden([_pair(1, 500, None)], [(1, 500)])
    assert out["red"] is False
    assert out["recovered"] == 1


def test_a_negative_pair_that_attaches_to_an_idless_event_is_red():
    """A negative pair that attaches to an event the MATCHER created is RED.

    This test used to be ``..._that_acquires_a_link_is_a_regression``, and its
    docstring read "550 of the 709 say 'belongs on no event'. Attaching one is a
    false attach." THAT CLAIM WAS THE DEFECT, asserted. The old assertion is
    deliberately not preserved: it encoded the conflation this change removes.
    What survives is the half of it that is true — no outside source says this
    event exists, so nothing corroborates the attachment.
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 999, external_id=None)],
    )
    assert out["red"] is True
    assert out["rows"][0]["actual_event_id"] == 999
    assert out["rows"][0]["verdict"] == "self_answered"
    assert out["self_answered"] == 1
    assert out["baseline_stale"] == 0


def test_a_negative_pair_on_its_adjudicated_provider_anchored_fixture_is_not_red():
    """THE CONTROL. The system getting BETTER must not be filed as it breaking.

    ``a-no-event`` means no event existed AT CAPTURE — the adjudicator's note is
    "global 2+-token check; titles batch-read". When the fixture later shows up
    from a provider, a human adjudicates the market onto it, and the market is
    there, the baseline row is stale and the matcher is right. Measured on
    production 2026-09-03: five of the 39 RED rows were exactly this, including
    "Hamburg vs Mainz" landing on the real Bundesliga ``Hamburger SV v FSV Mainz
    05`` (market 59700394 -> event 15291033, in ``ACCEPTED_ATTACHMENTS``).

    It takes BOTH halves. This is the arm that proves the repair below did not
    simply turn the promotion off.
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 999, external_id=_ODDS_API_ID)],
        accepted={1: 999},
    )
    assert out["red"] is False
    assert out["count"] == 0
    assert out["baseline_stale"] == 1
    assert out["self_answered"] == 0
    assert out["unadjudicated"] == 0
    # And it must not ride along in the rows the issue body accuses.
    assert out["rows"] == []


def test_a_negative_pair_on_an_unrelated_provider_anchored_event_is_red():
    """THE REPAIR. A provider-anchored destination is not a correspondence.

    ``anchor_provenance`` is a property of the DESTINATION ALONE — it takes an
    id string and nothing else, so it cannot see the market's teams, sport,
    kickoff or id. Promoting on it by itself accepted every one of the 29,333
    Odds-API-anchored events in the database as a valid destination for every
    market: attach "Hawaii vs Stanford" to a Bundesliga fixture three weeks away
    and the check called it ``baseline_stale`` and went green.

    Same input as the control above, one thing changed: nobody adjudicated this
    market onto this event.
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event", title="Hawaii vs Stanford")],
        [_row(1, 999, external_id=_ODDS_API_ID)],
        accepted={},
    )
    assert out["red"] is True
    assert out["count"] == 1
    assert out["baseline_stale"] == 0
    assert out["unadjudicated"] == 1
    assert out["rows"][0]["verdict"] == "unadjudicated"
    # The destination IS real — that is the point. It is the wrong one.
    assert out["rows"][0]["anchor_provenance"] == "schedule_provider"


def test_an_accepted_market_that_moves_to_another_anchored_event_is_red():
    """Acceptance is per ATTACHMENT, not per market.

    A market with an adjudicated destination that now sits somewhere else is the
    case a per-market allowlist would wave through forever, and it is the one
    worth waking up for: a human said event 999 and the matcher says 998.
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 998, external_id=_ODDS_API_ID)],
        accepted={1: 999},
    )
    assert out["red"] is True
    assert out["rows"][0]["verdict"] == "unadjudicated"
    # The row says where the adjudication put it, so the body reads as a move.
    assert out["rows"][0]["accepted_event_id"] == 999
    assert out["rows"][0]["actual_event_id"] == 998


def test_an_accepted_attachment_that_loses_its_provider_anchor_is_red():
    """Acceptance does not outlive the corroboration it was granted on.

    The five rows were adjudicated onto fixtures an outside schedule provider
    carried. If one of those events stops being anchored — the ``external_id``
    goes NULL, or the events row cannot be read — the pair is back to the
    matcher's word alone, and a stale human decision must not keep it green.
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 999, external_id=None)],
        accepted={1: 999},
    )
    assert out["red"] is True
    assert out["rows"][0]["verdict"] == "self_answered"
    assert out["rows"][0]["anchor_provenance"] == "idless"
    assert out["baseline_stale"] == 0


def test_a_prediction_market_derived_event_is_not_outside_corroboration():
    """THE HOLE THE ``IS NOT NULL`` PROXY LEFT OPEN.

    21,978 events carry a ``pm_kalshi_*`` / ``pm_polymarket_*`` ``external_id``:
    the registry CREATED them from a prediction market. ZERO of 587 sampled on
    2026-09-03 carry a single bookmaker odds snapshot, against 96.7% of Odds API
    events. So a prediction market attaching to an event a prediction market
    created is the matcher answering itself one step removed — the id-less case
    laundered through the ingest path — and reading it as "a provider anchors
    this now" would promote a real self-attachment out of RED.

    24,232 markets still hang off those events, so the row shape is live in the
    database even though the creation path is frozen.
    """
    for external_id in (_KALSHI_DERIVED_ID, _POLYMARKET_DERIVED_ID):
        out = _run_golden(
            [_pair(1, None, None, cls="a-no-event")],
            [_row(1, 999, external_id=external_id)],
        )
        assert out["red"] is True, external_id
        assert out["baseline_stale"] == 0, external_id
        assert out["self_answered"] == 1, external_id
        assert out["rows"][0]["anchor_provenance"] == "market_derived", external_id


def test_an_external_id_we_synthesized_ourselves_is_not_outside_corroboration():
    """``events.external_id`` is not provider-only BY CONSTRUCTION.

    ``POST /api/admin/events/create`` builds
    ``manual_{sport}_{home}_{away}_{unix_ts}`` out of our own field values and
    writes it straight to the column, bypassing ``find_or_create_event()``. It
    is the one shape where "an id is present" and "somebody outside carries this
    fixture" come apart on purpose, so it must never promote a row out of RED.
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 999, external_id="manual_soccer_epl_Ipswich_Liverpool_1757030400")],
    )
    assert out["red"] is True
    assert out["baseline_stale"] == 0
    assert out["rows"][0]["anchor_provenance"] == "synthesized"


def test_an_unrecognised_id_vocabulary_stays_red_rather_than_promoting_itself():
    """The discriminator is an ALLOWLIST, so a new upstream id shape is RED.

    A denylist would silently promote whatever vocabulary arrives next. Gotcha
    #53: absence of evidence that an id is self-derived is not evidence that an
    outside provider wrote it.
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 999, external_id="statpal-nfl-2026-week1-0007")],
    )
    assert out["red"] is True
    assert out["rows"][0]["anchor_provenance"] == "unknown"
    assert out["baseline_stale"] == 0


def test_the_detail_line_names_which_uncorroborated_provenance():
    """"34 uncorroborated" hides whether the matcher INVENTED the event or
    attached to an id nobody has adjudicated. Those need different fixes, and
    the body is the only place the count is refreshed."""
    out = _run_golden(
        [
            _pair(1, None, None, cls="a-no-event"),
            _pair(2, None, None, cls="a-no-event"),
        ],
        [
            _row(1, 998, external_id=None),
            _row(2, 997, external_id=_KALSHI_DERIVED_ID),
        ],
    )
    assert out["by_provenance"] == {"idless": 1, "market_derived": 1}
    assert "1 idless" in out["detail"]
    assert "1 market_derived" in out["detail"]


def test_an_event_row_we_cannot_read_is_not_read_as_corroboration():
    """Unknown provenance defaults to RED, not to "a provider vouched for it".

    A dangling ``event_id`` returns NULL for the joined ``external_id IS NULL``
    expression, which is indistinguishable from "anchored" if you test it
    truthily. Absence of evidence is not corroboration (gotcha #53).
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 999, event_missing=True)],
    )
    assert out["red"] is True
    assert out["rows"][0]["verdict"] == "self_answered"
    # RED for the same reason, but NOT reported as the finding "the matcher
    # created this event" — that claim needs an events row we actually read.
    assert out["rows"][0]["anchor_provenance"] == "unreadable"


def test_the_corroborating_set_is_an_allowlist_of_one_and_says_so():
    """A regression arm for the discriminator itself.

    If ``CORROBORATING_PROVENANCE`` ever grows to include ``market_derived`` or
    ``unknown``, every self-attachment in those classes silently leaves RED and
    the board goes quiet while the matcher is still answering itself.
    """
    assert mrec.CORROBORATING_PROVENANCE == frozenset({"schedule_provider"})
    assert mrec.anchor_provenance(_ODDS_API_ID) == "schedule_provider"
    assert mrec.anchor_provenance(None) == "idless"
    assert mrec.anchor_provenance(_KALSHI_DERIVED_ID) == "market_derived"
    assert mrec.anchor_provenance(_POLYMARKET_DERIVED_ID) == "market_derived"
    assert mrec.anchor_provenance("manual_nfl_A_B_1757030400") == "synthesized"
    assert mrec.anchor_provenance("something-new") == "unknown"
    # An events row we could not read outranks whatever the join returned.
    assert mrec.anchor_provenance(None, event_row_missing=True) == "unreadable"
    # Case and length are load-bearing: the Odds API id is 32 lowercase hex.
    assert mrec.anchor_provenance(_ODDS_API_ID.upper()) == "unknown"
    assert mrec.anchor_provenance(_ODDS_API_ID[:31]) == "unknown"


def test_a_positive_pair_that_leaves_its_adjudicated_event_is_a_regression():
    """Provenance does not soften a POSITIVE pair. The audit knew the answer.

    Even if the event it moved onto is provider-anchored, the pair had a
    known-correct event and no longer points at it.
    """
    out = _run_golden(
        [_pair(1, 500, 500)],
        [_row(1, 999, external_id=_ODDS_API_ID)],
    )
    assert out["red"] is True
    assert out["rows"][0]["verdict"] == "regressed"
    assert out["regressed"] == 1
    assert out["baseline_stale"] == 0


def test_the_detail_line_reports_the_four_outcomes_separately():
    """One RED number covering "we broke it" and "we fixed it" is unreadable.

    The body is the only place the count is refreshed (see ``build_title``), so
    the split has to survive into ``detail`` — and the unadjudicated class needs
    its own number, because its fix is "a human looks at this attachment" and
    the self-answered fix is "the matcher stops inventing events".
    """
    out = _run_golden(
        [
            _pair(1, 500, 500),                        # regressed
            _pair(2, None, None, cls="a-no-event"),    # self-answered
            _pair(3, None, None, cls="a-no-event"),    # baseline stale
            _pair(4, None, None, cls="a-no-event"),    # unadjudicated
        ],
        [
            _row(1, 999, external_id=_ODDS_API_ID),
            _row(2, 998, external_id=None),
            _row(3, 997, external_id=_ODDS_API_ID),
            _row(4, 996, external_id=_ODDS_API_ID),
        ],
        accepted={3: 997},
    )
    assert out["count"] == 3, "the accepted row must not be accused"
    assert (out["regressed"], out["self_answered"], out["unadjudicated"]) == (1, 1, 1)
    assert "1 adjudicated pairs regressed" in out["detail"]
    assert "1 negative pairs attached to an event no outside provider" in out["detail"]
    assert "1 idless" in out["detail"]
    assert "1 attached to a provider-anchored event nobody has adjudicated" in out["detail"]
    assert "1 sit on one of the 1 adjudicated-accepted fixtures" in out["detail"]


def test_every_accepted_attachment_is_a_pair_the_audit_said_belongs_nowhere():
    """The map may only make a NEGATIVE pair stale — never silence a regression.

    Read against the SHIPPED fixture, not a synthetic one: this is the guard
    that stops ``ACCEPTED_ATTACHMENTS`` from becoming a mute button. A positive
    pair has a known-correct event id, so "accepting" some other destination for
    it would delete the one finding the golden set exists to make.
    """
    pairs, _ = mrec.load_golden_baseline()
    by_market = {int(p["market_id"]): p for p in pairs}
    assert mrec.ACCEPTED_ATTACHMENTS, "the map is the whole promotion path"
    for market_id, event_id in mrec.ACCEPTED_ATTACHMENTS.items():
        pair = by_market.get(market_id)
        assert pair is not None, f"market {market_id} is not in the golden set"
        assert pair["correct_event_id"] is None, (
            f"market {market_id} is a POSITIVE pair adjudicated onto "
            f"{pair['correct_event_id']}; accepting {event_id} for it would hide "
            "a regression"
        )
        assert pair["market"].get("event_id_at_capture") is None, (
            f"market {market_id} was already attached at capture, so it is not "
            "a fixture-appeared-later row"
        )
        assert isinstance(event_id, int)


def test_the_accepted_attachments_are_the_five_adjudicated_on_2026_09_03():
    """A tripwire on the map's exact contents.

    Each entry is a human's judgement recorded in the module comment above it
    (unique team pair, and for the Kalshi rows a ticker-derived date equal to
    the event's). Growing the map is fine; growing it WITHOUT saying so in a
    diff is how a promotion path quietly widens back into ``IS NOT NULL``.
    """
    assert mrec.ACCEPTED_ATTACHMENTS == {
        59173320: 15294048,   # Campbell vs East Tennessee St. -> ETSU v Campbell
        59692113: 15297976,   # Vitória SC vs. Casa Pia AC     -> Vitória v Casa Pia
        59692121: 15299112,   # FC Alverca vs. SC Braga        -> Alverca v Braga
        59700394: 15291033,   # Hamburg vs Mainz               -> HSV v Mainz 05
        59700643: 15291104,   # Ipswich Town vs Liverpool      -> Ipswich v Liverpool
    }


def test_a_market_that_no_longer_exists_is_counted_not_accused():
    """A deleted market is not a matching regression. Saying so would make the
    twin cleanup (#2693 step 2) look like a matcher failure."""
    out = _run_golden([_pair(1, 500, 500)], [])
    assert out["red"] is False
    assert out["vanished"] == 1


# =============================================================================
# The invariants
# =============================================================================


def test_anchor_collision_is_red_when_one_provider_id_names_two_events():
    out = asyncio.run(
        mrec.check_anchor_collision(_Session([[("kalshi", "tennis:123", "game", 2)]]))
    )
    assert out["red"] is True
    assert out["rows"][0]["events"] == 2


def test_anchor_collision_is_green_on_the_measured_baseline_of_zero():
    out = asyncio.run(mrec.check_anchor_collision(_Session([[]])))
    assert out["red"] is False and out["count"] == 0


def test_market_multi_event_stays_scoped_to_open():
    """INVARIANTS (b) records that the unscoped form TIMES OUT (fp fedd618081365d6b).

    A job that ran the unscoped query every fifteen minutes would trade a
    reliable check for an intermittent one, and an intermittent check reads as
    GREEN whenever it fails.
    """
    import inspect

    src = inspect.getsource(mrec.check_market_multi_event)
    assert "status = 'open'" in src


def test_receipt_coverage_is_red_while_any_market_has_never_been_attempted():
    out = asyncio.run(mrec.check_receipt_coverage(_Session(scalar=4503)))
    assert out["red"] is True and out["count"] == 4503


def test_receipt_coverage_is_green_at_zero():
    out = asyncio.run(mrec.check_receipt_coverage(_Session(scalar=0)))
    assert out["red"] is False


def test_linked_unsourced_catches_attached_but_not_charting():
    """Bublik and Harris: linked, outcomes priced, no curve on the card."""
    out = asyncio.run(mrec.check_linked_unsourced(_Session([
        [(15299463, "polymarket", 11, None)],
    ])))
    assert out["red"] is True
    assert out["rows"][0]["event_id"] == 15299463
    assert out["rows"][0]["linked_markets"] == 11


def test_linked_unsourced_counts_events_not_markets():
    """Only the game-winner feeds the blend; a spread or a total is SUPPOSED to
    write nothing. Counting markets accused 300 rows of a fault 264 of them
    cannot commit — the honest unit is one card missing one curve (36 pairs,
    measured 2026-09-02)."""
    import inspect

    src = inspect.getsource(mrec.check_linked_unsourced)
    assert "GROUP BY 1, 2" in src
    assert "SELECT fm.event_id, fm.source" in src


# =============================================================================
# Unmeasurable is not GREEN
# =============================================================================


def test_a_check_that_raises_is_recorded_as_unmeasurable_and_never_files_green():
    """The direction that matters. If a failed query read as GREEN, the rail
    would auto-CLOSE a real open issue on the strength of a database error."""
    calls = []

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Session(raises=RuntimeError("statement timeout"))

        async def __aexit__(self, *exc):
            return False

    with patch.object(mrec, "get_task_session", _Factory()):
        out = asyncio.run(mrec._run_matching_reconciliation(file_issues=False))

    assert out["checks_run"] == 0
    assert out["checks_failed"] == len(mrec.CHECKS)
    assert out["red"] == []
    assert not calls, "nothing should have been filed"


def test_detect_only_never_touches_github():
    """The verification form the bus runs. It must not file."""

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Session(raises=RuntimeError("no db in tests"))

        async def __aexit__(self, *exc):
            return False

    with patch.object(mrec, "get_task_session", _Factory()), \
            patch("app.tasks.sentinel_filing.reconcile_issue") as rec:
        out = asyncio.run(mrec._run_matching_reconciliation(file_issues=False))
    assert out["filing"] == "skipped"
    rec.assert_not_called()


# =============================================================================
# Filing: one issue per subject, with the receipt attached
# =============================================================================


def test_the_fingerprint_is_per_subject_not_per_finding():
    """A content-derived fingerprint files a fresh issue every time the count
    moves by one — the duplicate class the shared rail exists to prevent,
    reached from the fingerprint side."""
    a = mrec._finding("golden", True, 40, "40 regressed", [{"market_id": 1}])
    b = mrec._finding("golden", True, 41, "41 regressed", [{"market_id": 2}])
    assert mrec.fingerprint_for(a["key"]) == mrec.fingerprint_for(b["key"])
    assert mrec.fingerprint_for("golden") != mrec.fingerprint_for("receipt_coverage")


def test_every_check_has_a_distinct_fingerprint():
    keys = [c.__name__.replace("check_", "") for c in mrec.CHECKS]
    fps = {mrec.fingerprint_for(k) for k in keys}
    assert len(fps) == len(keys)


def test_the_title_is_per_subject_too_because_the_rail_never_refreshes_it():
    """The fingerprint's argument, one layer up.

    ``reconcile_issue`` comments and re-points the BODY on a still-RED subject;
    the title is written once at creation and frozen. A title built from the
    finding's detail therefore freezes a count that keeps moving. Measured
    2026-09-03: #2728 was titled "1 of 709 adjudicated pairs regressed" while
    its body said 39.
    """
    a = mrec._finding("golden", True, 1, "1 of 709 adjudicated pairs regressed")
    b = mrec._finding("golden", True, 39, "39 of 709 adjudicated pairs regressed")
    assert mrec.build_title(a) == mrec.build_title(b)


def test_no_drift_title_carries_a_count():
    """The general form: no title may contain a digit from any observation.

    Asserted over every check, not just ``golden``, because the defect was in
    the shared title builder and showed up on three subjects at once.
    """
    for check_key in mrec.SUBJECTS:
        low = mrec.build_title(mrec._finding(check_key, True, 1, "1 thing"))
        high = mrec.build_title(mrec._finding(check_key, True, 4242, "4242 things"))
        assert low == high, f"{check_key} title moves with the count: {low!r} vs {high!r}"
        assert "4242" not in high, f"{check_key} title carries the count: {high}"


def test_every_check_key_has_a_stable_subject():
    """Class guard: a new check that forgets ``SUBJECTS`` must redden here.

    The key set is scanned out of the module source because the keys are
    string literals at the ``_finding`` call sites and do not match the check
    function names (``check_golden_pairs`` emits ``golden``). The scan asserts
    its own yield first — a regex that silently matched nothing would make this
    test vacuously green, which is the failure mode a source-scanning guard has.
    """
    import inspect
    import re

    src = inspect.getsource(mrec)
    keys = set(re.findall(r'_finding\(\s*"([a-z_0-9]+)"', src))
    assert len(keys) == len(mrec.CHECKS), (
        f"source scan found {len(keys)} check key(s) {sorted(keys)} for "
        f"{len(mrec.CHECKS)} checks — the scan is broken, not the map"
    )
    assert keys == set(mrec.SUBJECTS), (
        f"checks without a subject: {sorted(keys - set(mrec.SUBJECTS))}; "
        f"subjects with no check: {sorted(set(mrec.SUBJECTS) - keys)}"
    )


def test_the_golden_subject_names_every_red_class_not_just_regressions():
    """A subject may not describe a strictly narrower condition than it files.

    The golden check files THREE kinds of RED: a pair that lost a known-correct
    answer (*regressed*), a negative pair that attached to an event nobody
    adjudicated it onto (*unadjudicated*), and one that attached to an event no
    schedule provider anchors (*self-answered*). Measured against production
    2026-09-03, all 34 RED rows were the third kind and 0 were regressions — so
    a subject saying only "have regressed" sends the one reader a board has
    looking for the class that is not there.

    A tripwire, not a proof: it cannot check that the words match the code, only
    that no class was dropped from the sentence. That is the regression it
    exists for — the subject being quietly narrowed while the check keeps filing
    all three. It is also blind to a FOURTH red class being added; the binding
    guard below is the one that catches that, by reading the classes out of the
    code instead of naming them here.
    """
    subject = mrec.SUBJECTS["golden"]
    assert "regress" in subject, f"golden subject dropped the regression class: {subject!r}"
    assert "vouches for" in subject, (
        f"golden subject dropped the self-answered class: {subject!r}"
    )
    assert "unadjudicated" in subject, (
        f"golden subject dropped the unadjudicated class — a provider-anchored "
        f"attachment nobody has judged is RED and must be named: {subject!r}"
    )


#: For each RED verdict ``check_golden_pairs`` can file, the phrase in
#: ``SUBJECTS["golden"]`` that names it to a human.
#:
#: Deliberately NOT derivable from the verdict name. ``self_answered`` is
#: written for a reader as "no schedule provider vouches for" — a guard that
#: just looked for the verdict's own identifier in the sentence would pass on
#: ``regressed`` and ``unadjudicated`` and never notice that the third class was
#: missing, which is exactly the vacuous-green shape this map exists to avoid.
#:
#: A NEW red verdict with no entry here fails the binding guard rather than
#: shipping a subject that hides it. Adding the entry is not enough either: the
#: phrase then has to actually appear in the subject.
GOLDEN_RED_VERDICT_PHRASES = {
    "regressed": "regress",
    "self_answered": "vouches for",
    "unadjudicated": "unadjudicated",
}


def _verdict_assigned(stmt):
    """``row["verdict"] = "X"`` -> ``"X"``, else ``None``."""
    import ast

    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    if not (
        isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Name)
        and target.value.id == "row"
        and isinstance(target.slice, ast.Constant)
        and target.slice.value == "verdict"
    ):
        return None
    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
        return stmt.value.value
    return None


def _append_target(stmt):
    """``bucket.append(row)`` -> ``"bucket"``, else ``None``."""
    import ast

    if not isinstance(stmt, ast.Expr):
        return None
    call = stmt.value
    if not (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "append"
        and isinstance(call.func.value, ast.Name)
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "row"
    ):
        return None
    return call.func.value.id


def _golden_check_ast():
    import ast
    import inspect
    import textwrap

    return ast.parse(textwrap.dedent(inspect.getsource(mrec.check_golden_pairs)))


def _golden_verdict_buckets() -> dict[str, str]:
    """Read the check's own source: which list does each verdict land in?

    Pairs every ``row["verdict"] = "X"`` with the next ``bucket.append(row)`` in
    the same statement list, which is how the check is written at every one of
    its branches.
    """
    import ast

    mapping: dict[str, str] = {}
    for node in ast.walk(_golden_check_ast()):
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field, None)
            if not isinstance(stmts, list):
                continue
            for i, stmt in enumerate(stmts):
                verdict = _verdict_assigned(stmt)
                if verdict is None:
                    continue
                for later in stmts[i + 1 :]:
                    bucket = _append_target(later)
                    if bucket:
                        mapping[verdict] = bucket
                        break
    return mapping


def _golden_red_buckets() -> set[str]:
    """The list names summed into ``red_rows`` — the check's own RED definition."""
    import ast

    for node in ast.walk(_golden_check_ast()):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "red_rows"
        ):
            return {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
    return set()


def test_the_golden_subject_is_bound_to_the_red_verdicts_the_code_actually_files():
    """The hardening the string tripwire above cannot do (follow-up on CERT-864).

    That test names the three RED classes as literals, so it can only catch a
    class being REMOVED from the sentence. It is blind to the opposite and more
    likely drift: a fourth RED class being added to ``check_golden_pairs`` while
    the subject keeps describing three. The board would then be triaged by a
    title that does not mention the thing it is filing.

    So this one derives the RED set from the code instead of restating it —
    ``row["verdict"] = "X"`` paired with the bucket the row is appended to, and
    the buckets summed into ``red_rows`` — and requires every RED verdict to be
    named in the subject via ``GOLDEN_RED_VERDICT_PHRASES``. A new red verdict
    has no phrase entry, so it reddens here.

    Every derivation asserts its own yield before it is used. A source-scanning
    guard whose scan quietly matches nothing is worse than no guard: it is a
    green light with nothing behind it.
    """
    verdict_buckets = _golden_verdict_buckets()
    assert len(verdict_buckets) >= 4, (
        f"source scan found only {len(verdict_buckets)} verdict->bucket pair(s) "
        f"{sorted(verdict_buckets)} in check_golden_pairs — the scan is broken, "
        f"not the code. Fix the scan before trusting this guard."
    )

    red_buckets = _golden_red_buckets()
    assert red_buckets, (
        "source scan found no `red_rows = ...` assignment in check_golden_pairs "
        "— the scan is broken, not the code."
    )

    red_verdicts = {v for v, b in verdict_buckets.items() if b in red_buckets}
    assert red_verdicts, (
        f"no verdict lands in a red bucket: verdicts {sorted(verdict_buckets)} "
        f"vs red buckets {sorted(red_buckets)} — the scan is broken."
    )

    # Known-hit anchors. These prove the derivation DISCRIMINATES rather than
    # sweeping every verdict into RED: baseline_stale is the one verdict the
    # check deliberately does not count, and a scan that returned "everything"
    # would still satisfy the assertions above.
    assert "self_answered" in red_verdicts, (
        f"derivation lost a known RED class; got {sorted(red_verdicts)}"
    )
    assert "baseline_stale" in verdict_buckets, (
        "derivation lost baseline_stale entirely; got "
        f"{sorted(verdict_buckets)} — the scan is broken."
    )
    assert "baseline_stale" not in red_verdicts, (
        "baseline_stale is NOT red — it is the matcher being confirmed and the "
        f"baseline row being stale. Derivation says: {sorted(red_verdicts)}"
    )

    unnamed = sorted(v for v in red_verdicts if v not in GOLDEN_RED_VERDICT_PHRASES)
    assert not unnamed, (
        f"check_golden_pairs files RED verdict(s) {unnamed} that "
        f"GOLDEN_RED_VERDICT_PHRASES does not name. Add the phrase a human "
        f"would read for each, then make SUBJECTS['golden'] actually say it — "
        f"a subject that omits a class it files sends the board's one reader "
        f"looking for the wrong thing."
    )

    subject = mrec.SUBJECTS["golden"]
    for verdict in sorted(red_verdicts):
        phrase = GOLDEN_RED_VERDICT_PHRASES[verdict]
        assert phrase in subject, (
            f"SUBJECTS['golden'] does not name the {verdict!r} class: expected "
            f"the phrase {phrase!r} in {subject!r}"
        )


def test_an_unknown_check_key_raises_rather_than_inventing_a_title():
    with pytest.raises(KeyError, match="no SUBJECTS entry"):
        mrec.build_title(mrec._finding("a_check_nobody_declared", True, 1, "x"))


def test_the_body_declares_the_dedupe_key_in_the_form_the_rail_parses():
    """The shared rail only OWNS a fingerprint when the declaration matches its
    parser. A body that declares it any other way is a body the GREEN path can
    never find, so the issue would never auto-close."""
    from app.tasks.sentinel_filing import declared_fingerprints

    finding = mrec._finding("golden", True, 1, "one regressed", [{"market_id": 7}])
    body = mrec.build_body(finding)
    assert (mrec.MARKER, mrec.fingerprint_for("golden")) in declared_fingerprints(body)


def test_the_body_carries_the_receipt_query_for_the_market_it_names():
    """An alert that says what broke but not how to see why hands a human the
    dig the system just did."""
    finding = mrec._finding(
        "golden", True, 1, "one regressed",
        [{"market_id": 59669077, "expected_event_id": 1, "actual_event_id": None}],
    )
    body = mrec.build_body(finding, mrec.receipts_hint_for(finding))
    assert "match-receipts?market_id=59669077" in body


def test_the_body_never_truncates_silently():
    rows = [{"market_id": i} for i in range(80)]
    finding = mrec._finding("golden", True, 80, "80 regressed", rows)
    body = mrec.build_body(finding)
    assert f"{80 - mrec.MAX_LISTED} more" in body
    assert "**Count:** 80" in body


def test_every_filed_issue_carries_the_matching_drift_label():
    filed = {}

    def _fake(**kw):
        filed.update(kw)
        return {"action": "filed"}

    finding = mrec._finding("golden", True, 1, "one regressed", [{"market_id": 7}])
    with patch("app.tasks.sentinel_filing.reconcile_issue", _fake):
        mrec.file_findings([finding], open_issues=[])
    assert mrec.DRIFT_LABEL in filed["labels"]
    assert "alert-intake" in filed["labels"], (
        "without the source label the rail's own dedup read cannot see the "
        "issue, and it re-files on every run"
    )


def test_a_green_check_resolves_its_issue_rather_than_leaving_the_board_to_grow():
    calls = []

    def _fake(**kw):
        calls.append(kw)
        return {"action": "resolved"}

    finding = mrec._finding("receipt_coverage", False, 0, "0 unattempted")
    with patch("app.tasks.sentinel_filing.reconcile_issue", _fake):
        mrec.file_findings([finding], open_issues=[])
    assert calls[0]["red"] is False
    assert "GREEN" in calls[0]["green_comment"]


def test_the_task_is_registered_and_scheduled_on_the_matching_cadence():
    """A job nobody runs files nothing."""
    from app.tasks import celery_app

    assert "app.tasks.matching_reconciliation" in celery_app.tasks
    entry = celery_app.conf.beat_schedule["matching-reconciliation"]
    assert entry["task"] == "app.tasks.matching_reconciliation"
    assert entry["options"]["queue"] == "heavy"
    # Four fires an hour, the same cadence as the matcher it guards.
    assert len(str(entry["schedule"]).split(",")) >= 4


def test_the_admin_trigger_exists_so_a_run_can_be_reproduced_without_a_beat():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/admin/matching-reconciliation/run" in paths


# =============================================================================
# The acceptance test: a SEEDED violation produces a real issue, once, and the
# same issue closes on recovery. Seeded, never production — the brief is
# explicit about that, and a job that had to break production to prove it works
# would be a worse bug than the one it detects.
# =============================================================================


class _SeededSession:
    """A database in which exactly one invariant is violated.

    Everything else answers clean, so the test proves the ONE seeded subject
    files and the others do not — a job that filed five issues for one violation
    would bury the finding it just made.
    """

    def __init__(self, unattempted=0, anchor_collisions=(), unsourced=(),
                 links_not_durable=0):
        self._queue = [
            [],                       # golden: markets, keyed below
            list(anchor_collisions),  # anchor_collision
            [],                       # market_multi_event
            list(unsourced),          # linked_unsourced
            [],                       # receipt_contradicts_link
        ]
        # Scalars answer in check order, so seeding one subject cannot
        # accidentally light up another and make "one violation, one issue"
        # pass for the wrong reason.
        self._scalars = [unattempted, links_not_durable]

    async def execute(self, stmt, params=None):
        return _Result(self._queue.pop(0))

    async def scalar(self, stmt):
        return self._scalars.pop(0)


def _run_with_github(session, monkeypatch, open_issues):
    """Drive the whole job with the real filing rail and a stubbed GitHub."""
    from app.tasks import bug_report_github as gh
    from app.tasks import sentinel_filing as sf

    created, comments, closed = [], [], []
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(
        gh, "create_github_issue",
        lambda title, body, labels: (
            created.append({"title": title, "body": body, "labels": labels}),
            (4242, "NODE"),
        )[1],
    )
    monkeypatch.setattr(gh, "add_to_project_board", lambda nid: None)
    monkeypatch.setattr(
        gh, "comment_on_issue",
        lambda n, b: comments.append({"issue": n, "body": b}),
    )
    monkeypatch.setattr(gh, "update_issue_body", lambda n, b: None)
    monkeypatch.setattr(
        gh, "close_issue", lambda n, comment=None: closed.append(n)
    )
    monkeypatch.setattr(
        sf, "fetch_open_alert_issues",
        lambda: sf.OpenIssuesResult(ok=True, issues=list(open_issues)),
    )

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(mrec, "get_task_session", _Factory())
    result = asyncio.run(mrec._run_matching_reconciliation(file_issues=True))
    return result, created, comments, closed


def _empty_golden(monkeypatch):
    monkeypatch.setattr(
        mrec, "load_golden_baseline", lambda: ([], {}),
    )


def test_a_seeded_violation_files_one_issue_with_the_receipt_and_the_label(monkeypatch):
    """The acceptance criterion: point it at a violation, get an issue."""
    _empty_golden(monkeypatch)
    result, created, comments, closed = _run_with_github(
        _SeededSession(unattempted=4503), monkeypatch, open_issues=[]
    )

    assert "receipt_coverage" in result["red"]
    assert len(created) == 1, (
        f"one seeded violation should file exactly one issue, got "
        f"{[c['title'] for c in created]}"
    )
    issue = created[0]
    assert mrec.DRIFT_LABEL in issue["labels"]
    # The count lives in the BODY, which the rail refreshes every cycle — never
    # in the title, which is written once and then frozen for the issue's life.
    assert "**Count:** 4503" in issue["body"]
    assert "4503" not in issue["title"]
    assert issue["title"] == (
        "[Matching Drift] receipt_coverage: open unlinked markets have never "
        "been attempted"
    )
    assert "match-receipts" in issue["body"], "the alert must carry the receipt query"
    assert not closed


def test_the_second_cycle_comments_instead_of_filing_a_duplicate(monkeypatch):
    """Deduped per subject. 96 cycles a day means 96 issues if this breaks."""
    _empty_golden(monkeypatch)
    fp = mrec.fingerprint_for("receipt_coverage")
    existing = {
        "number": 4242,
        "title": "[Matching Drift] receipt_coverage: 4503 …",
        "body": f"`{mrec.MARKER}:{fp}`  (dedupe key — do not remove)",
    }
    _r, created, comments, closed = _run_with_github(
        _SeededSession(unattempted=4400), monkeypatch, open_issues=[existing]
    )
    assert created == [], "filed a duplicate for a subject already open"
    assert comments and comments[0]["issue"] == 4242
    assert not closed


def test_recovery_closes_the_very_issue_the_violation_opened(monkeypatch):
    """RED→GREEN, not RED→forever. A board that only grows stops being read."""
    _empty_golden(monkeypatch)
    fp = mrec.fingerprint_for("receipt_coverage")
    existing = {
        "number": 4242,
        "title": "[Matching Drift] receipt_coverage: 4503 …",
        "body": f"`{mrec.MARKER}:{fp}`  (dedupe key — do not remove)",
    }
    result, created, comments, closed = _run_with_github(
        _SeededSession(unattempted=0), monkeypatch, open_issues=[existing]
    )
    assert result["red"] == [] or "receipt_coverage" not in result["red"]
    assert created == []
    assert closed == [4242]


def test_a_clean_run_with_no_open_issues_files_nothing_at_all(monkeypatch):
    """The steady state. Any chatter here is 96 no-op writes a day."""
    _empty_golden(monkeypatch)
    result, created, comments, closed = _run_with_github(
        _SeededSession(unattempted=0), monkeypatch, open_issues=[]
    )
    assert created == [] and comments == [] and closed == []
    assert result["red"] == []


def test_the_unsourced_age_guard_reads_created_at_not_updated_at():
    """The first draft measured `updated_at`, which moves on every price poll.

    It therefore says nothing about how long a market has been ATTACHED, and it
    let a market linked two minutes ago be accused while its first snapshot was
    still in flight. Measured 2026-09-02 twenty minutes apart, the count fell
    36 -> 18 on its own: a check reporting a queue depth and calling it a
    defect. An alert that heals itself between two runs teaches the reader to
    ignore it.
    """
    import inspect

    src = inspect.getsource(mrec.check_linked_unsourced)
    assert "fm.created_at <" in src
    assert "fm.updated_at" not in src


def test_the_unsourced_window_is_symmetric_and_near_term():
    """+24h counted events the 2-minute live poller has legitimately not reached
    yet. A missing curve is a defect near kickoff, a not-yet a day out."""
    assert mrec.UNSOURCED_WINDOW_HOURS <= 6
    src = __import__("inspect").getsource(mrec.check_linked_unsourced)
    assert ":hrs * INTERVAL '1 hour'" in src
    assert "INTERVAL '24 hours'" not in src


# =============================================================================
# CERT-772: a link lost to a sibling's rollback must be VISIBLE to this job
# =============================================================================


def test_a_receipt_that_disagrees_with_the_database_is_red():
    """The exact hole CERT-772 named.

    Before this arm, a market whose link was rolled back was invisible to every
    other check: `receipt_coverage` counts markets with NO receipt and this one
    has one, `linked_unsourced` joins through the now-NULL `event_id`, and
    `golden` only sees its fixed 709 ids. All five could be GREEN while the
    market sat unattached and its one-query answer said "linked".
    """
    out = asyncio.run(mrec.check_receipt_contradicts_link(
        _Session([[(1, 42, None, "pass2_general", None)]], scalar=0)
    ))
    assert out["red"] is True
    assert out["rows"][0]["receipt_says_event_id"] == 42
    assert out["rows"][0]["database_says_event_id"] is None


def test_the_write_time_downgrades_are_reported_too_not_just_the_lies():
    """`link_not_durable` is the healthy path — the guard caught it before
    publication. It must still be reported: nonzero means the matcher IS losing
    links, even though the receipt no longer misstates it."""
    out = asyncio.run(mrec.check_receipt_contradicts_link(
        _Session([[]], scalar=7)
    ))
    assert out["red"] is True
    assert out["count"] == 7
    assert "link_not_durable" in out["detail"]


def test_agreement_between_receipt_and_database_is_green():
    out = asyncio.run(mrec.check_receipt_contradicts_link(
        _Session([[]], scalar=0)
    ))
    assert out["red"] is False and out["count"] == 0


def test_the_contradiction_check_is_wired_into_the_run():
    """An arm nobody calls closes no hole."""
    assert mrec.check_receipt_contradicts_link in mrec.CHECKS
