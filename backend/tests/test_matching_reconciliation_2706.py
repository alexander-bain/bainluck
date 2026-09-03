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


def _row(market_id, event_id, event_is_idless=None):
    """One production row: the market, where it points, and whether that event
    is the matcher's own id-less creation. ``None`` = provenance unknown (no
    link, or an events row we could not read)."""
    return (market_id, event_id, event_is_idless)


def _run_golden(pairs, current_rows):
    # Tolerate the 2-tuples the pre-provenance tests were written with: those
    # cases turn on the pair, not on what it attached to.
    rows = [r if len(r) == 3 else (r[0], r[1], None) for r in current_rows]
    with patch.object(mrec, "FIXTURE_PATH") as fp:
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
        [_row(1, 999, event_is_idless=True)],
    )
    assert out["red"] is True
    assert out["rows"][0]["actual_event_id"] == 999
    assert out["rows"][0]["verdict"] == "self_answered"
    assert out["self_answered"] == 1
    assert out["baseline_stale"] == 0


def test_a_negative_pair_that_attaches_to_a_provider_anchored_fixture_is_not_red():
    """The system getting BETTER must not be filed as the system breaking.

    ``a-no-event`` means no event existed AT CAPTURE — the adjudicator's note is
    "global 2+-token check; titles batch-read". When the fixture later shows up
    from a provider and the market attaches to it, the baseline row is stale and
    the matcher is right. Measured on production 2026-09-03: five of the 39 RED
    rows were exactly this, including "Hamburg vs Mainz" landing on the real
    Bundesliga ``Hamburger SV v FSV Mainz 05``.
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 999, event_is_idless=False)],
    )
    assert out["red"] is False
    assert out["count"] == 0
    assert out["baseline_stale"] == 1
    assert out["self_answered"] == 0
    # And it must not ride along in the rows the issue body accuses.
    assert out["rows"] == []


def test_an_event_row_we_cannot_read_is_not_read_as_corroboration():
    """Unknown provenance defaults to RED, not to "a provider vouched for it".

    A dangling ``event_id`` returns NULL for the joined ``external_id IS NULL``
    expression, which is indistinguishable from "anchored" if you test it
    truthily. Absence of evidence is not corroboration (gotcha #53).
    """
    out = _run_golden(
        [_pair(1, None, None, cls="a-no-event")],
        [_row(1, 999, event_is_idless=None)],
    )
    assert out["red"] is True
    assert out["rows"][0]["verdict"] == "self_answered"


def test_a_positive_pair_that_leaves_its_adjudicated_event_is_a_regression():
    """Provenance does not soften a POSITIVE pair. The audit knew the answer.

    Even if the event it moved onto is provider-anchored, the pair had a
    known-correct event and no longer points at it.
    """
    out = _run_golden(
        [_pair(1, 500, 500)],
        [_row(1, 999, event_is_idless=False)],
    )
    assert out["red"] is True
    assert out["rows"][0]["verdict"] == "regressed"
    assert out["regressed"] == 1
    assert out["baseline_stale"] == 0


def test_the_detail_line_reports_the_three_outcomes_separately():
    """One RED number covering "we broke it" and "we fixed it" is unreadable.

    The body is the only place the count is refreshed (see ``build_title``), so
    the split has to survive into ``detail``.
    """
    out = _run_golden(
        [
            _pair(1, 500, 500),                        # regressed
            _pair(2, None, None, cls="a-no-event"),    # self-answered
            _pair(3, None, None, cls="a-no-event"),    # baseline stale
        ],
        [
            _row(1, 999, event_is_idless=False),
            _row(2, 998, event_is_idless=True),
            _row(3, 997, event_is_idless=False),
        ],
    )
    assert out["count"] == 2, "the stale-baseline row must not be accused"
    assert "1 adjudicated pairs regressed" in out["detail"]
    assert "1 negative pairs attached to an id-less event" in out["detail"]
    assert "1 attached to a provider-anchored fixture" in out["detail"]


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
    assert "4503" in issue["title"]
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
