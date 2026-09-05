"""`GET /api/admin/statpal/authority-agreement` — the row the bus reads. #2867.

Bus bucket `M-R-AUTHORITY` appends one row per sport per day and a flip needs
seven consecutive rows at ≥99.5%. That makes this endpoint's failure modes
specific: it is not enough for it to return 200 with plausible numbers, because
a plausible number banked seven days running is exactly what a bad gate looks
like from the outside.

So the three things pinned here are the three that would quietly corrupt a
streak rather than break a page:

  * **the route is reachable at the path the bus will call.** An admin router
    that is written and never mounted answers 404 to a correct request, and the
    bus would log seven `READ-FAILED` days for a healthy system (gotcha #2).
  * **"not measured" never renders as "measured and disagreed."** Before the
    first pass after deploy there is no banked row, and publishing zeros there
    resets a streak that nothing has actually falsified (gotcha #53).
  * **the banked row and the table are published side by side, not merged.**
    The pass says what it believed; the census says what the table holds. When
    they differ, something outside the stamper wrote a StatPal anchor — a
    finding that is invisible the moment either number is dropped.
"""

from __future__ import annotations

import pytest

from app.routes import admin_providers
from app.utils.authority_agreement import READ_OK, SHADOW_STAMPERS

ROUTE_PATH = "/api/admin/statpal/authority-agreement"


class _Row(tuple):
    """A `.first()` result: indexable exactly like the driver's."""


class FakeSession:
    """Answers the endpoint's two censuses by EXACT text, and nothing else.

    An unknown statement raises rather than returning zeros — a census that
    answers "0" to a query it does not recognise publishes a confident wrong
    number, which is the one outcome a ledger cannot survive.
    """

    def __init__(self, *, anchors=0, column_agrees=0, duplicate_ids=0):
        self._anchors = anchors
        self._agrees = column_agrees
        self._dupes = duplicate_ids
        self.params: list[dict] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.params.append(dict(params or {}))
        if sql == admin_providers._ANCHOR_CENSUS:
            return _Result(_Row((self._anchors, self._agrees)))
        if sql == admin_providers._DUPLICATE_IDS:
            return _Result(_Row((self._dupes,)))
        raise AssertionError(
            "the endpoint ran a statement this guard does not know:\n"
            f"{sql}\nAdd it here deliberately — do not let it answer zero."
        )


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


def _agreement_row(**over):
    row = {
        "sport_key": "americanfootball_nfl",
        "read": READ_OK,
        "denominator": 272,
        "identity": {
            "both": 272,
            "statpal_only": 0,
            "ours_only": 0,
            "pct": 100.0,
            "governs": True,
        },
        "schedule": {"within": 243, "off_by_hours": 24, "wrong_day": 5,
                     "time_missing": 0, "governs": False},
        "anchors": {"anchored": 244, "unanchored": 28, "mismatch": 0,
                    "polluted_column": 46, "pct_of_both": 89.71,
                    "governs": False},
    }
    row.update(over)
    return row


@pytest.fixture
def call(monkeypatch):
    """Invoke the endpoint with auth stubbed and metrics under our control."""

    async def _call(*, metrics, session):
        monkeypatch.setattr(
            admin_providers, "_check_admin_secret", lambda *a, **k: None
        )
        import app.tasks.redis_state as redis_state

        monkeypatch.setattr(redis_state, "get_task_metrics", lambda name: metrics)
        return await admin_providers.statpal_authority_agreement(
            request=None, secret="x", db=session
        )

    return _call


# ---------------------------------------------------------------------------
# Reachability — the bus calls a path, not a function
# ---------------------------------------------------------------------------


def test_the_route_is_mounted_at_the_path_the_bus_will_call():
    from app.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert ROUTE_PATH in paths, (
        "an admin router that is written and never mounted answers 404 to a "
        "correct request (gotcha #2)"
    )


def test_it_is_a_read_and_stays_one():
    from app.main import app

    methods = {
        m
        for r in app.routes
        if getattr(r, "path", None) == ROUTE_PATH
        for m in (getattr(r, "methods", None) or set())
    }
    assert methods <= {"GET", "HEAD"}


# ---------------------------------------------------------------------------
# What it publishes
# ---------------------------------------------------------------------------


async def test_the_banked_row_is_published_verbatim(call):
    banked = _agreement_row()
    session = FakeSession(anchors=244, column_agrees=244)
    out = await call(
        metrics={
            "last_result_summary": {"agreement": banked},
            "last_success_at": "2026-09-04T10:23:02.864712+00:00",
        },
        session=session,
    )

    # One entry per shadowed sport since step 3 added NBA and NHL; the fake
    # metrics are the same for all three, so this pins the NFL entry by name
    # rather than by position.
    (nfl,) = [s for s in out["sports"] if s["sport_key"] == "americanfootball_nfl"]
    assert nfl["agreement"] == banked
    assert nfl["last_pass_at"] == "2026-09-04T10:23:02.864712+00:00"
    assert nfl["pass_age_seconds"] >= 0
    assert "identity governs" in out["gate"].lower() or "Identity governs" in out["gate"]


# ---------------------------------------------------------------------------
# The summary above the sports
#
# It is the first sentence anybody reading this payload reads, so it is the
# cheapest place to send a reader to the wrong number — and the reader it sends
# is the bus, which turns a wrong number into a seven-day streak. The wording it
# replaced said "identity >= 99.5% on the governing bucket", which was true of
# the buckets and wrong about the numbers: identity carries TWO, and the one a
# reader reaches for after that sentence reads 3.40 for NBA and governs nothing.
# ---------------------------------------------------------------------------


def test_the_summary_names_every_gate_state():
    """A fifth state added without the copy is a state nobody reading is told about."""
    from app.utils import authority_agreement as aa

    states = {aa.GATE_MEETS, aa.GATE_BELOW, aa.GATE_NO_SCORE, aa.GATE_PENDING}
    missing = sorted(s for s in states if s not in aa.FLIP_GATE_SUMMARY)
    assert not missing, (
        f"the gate summary does not name {missing}; a reader who meets that "
        "state in a row has to guess whether it advances, resets or carries"
    )
    # And it says what each state DOES, not merely that it exists.
    for verb in ("advances", "resets", "carry it unchanged"):
        assert verb in aa.FLIP_GATE_SUMMARY


def test_the_summary_never_scores_identity_as_a_single_number():
    """The pre-D63 wording, and every rephrasing of it, stays out.

    `identity` is one bucket holding two questions with different answers. Any
    sentence that puts the bar straight after the bare word sends the reader to
    `identity.pct` — which is the governing number for NFL and meaningless for
    NBA and NHL, and telling the two apart is the whole of D63.
    """
    import re

    from app.utils.authority_agreement import FLIP_BAR_PCT, FLIP_GATE_SUMMARY

    offender = re.search(
        r"identity[^.]{0,40}(>=|≥|at least|above)\s*9?9",
        FLIP_GATE_SUMMARY,
        re.IGNORECASE,
    )
    assert offender is None, (
        f"the summary scores 'identity' against the bar directly ({offender!r}); "
        "identity has two numbers and which one governs is per sport"
    )
    assert "per sport" in FLIP_GATE_SUMMARY
    assert "identity.governing" in FLIP_GATE_SUMMARY
    assert str(FLIP_BAR_PCT) in FLIP_GATE_SUMMARY


async def test_the_endpoint_publishes_the_shared_summary_not_a_copy_of_it(call):
    """A second copy in the route file keeps saying MEETS after the constant stops."""
    from app.utils.authority_agreement import FLIP_GATE_SUMMARY

    out = await call(
        metrics={"last_result_summary": {"agreement": _agreement_row()}},
        session=FakeSession(),
    )
    assert out["gate"] == FLIP_GATE_SUMMARY


async def test_the_table_census_is_reported_beside_the_pass_not_merged_into_it(call):
    session = FakeSession(anchors=244, column_agrees=240, duplicate_ids=2)
    out = await call(
        metrics={"last_result_summary": {"agreement": _agreement_row()}},
        session=session,
    )

    live = out["sports"][0]["live"]
    assert live["anchor_prefix"] == "americanfootball_nfl"
    assert live["anchors"] == 244
    assert live["column_agrees"] == 240
    # An anchor whose column no longer agrees reads as STALE on every lookup, so
    # it resolves nothing while looking like a link.
    assert live["half_links"] == 4
    assert live["duplicate_ids"] == 2
    # The banked row is untouched by the census — two instruments, two answers.
    assert out["sports"][0]["agreement"]["anchors"]["anchored"] == 244


async def test_the_census_is_scoped_to_this_sports_id_space(call):
    session = FakeSession(anchors=1, column_agrees=1)
    await call(metrics={"last_result_summary": {}}, session=session)

    prefixes = [p.get("prefix") for p in session.params if "prefix" in p]
    likes = [p.get("like_prefix") for p in session.params if "like_prefix" in p]
    # One census per shadowed sport, each scoped to its OWN id space and never a
    # bare `statpal:` — the whole point is that NBA's 1043639 and NHL's 649052
    # are neighbours in one provider's numbering and must not be counted
    # together (D55).
    assert prefixes == [f"{k}:" for k in sorted(SHADOW_STAMPERS)]
    assert likes == [f"{k}:%" for k in sorted(SHADOW_STAMPERS)]


# ---------------------------------------------------------------------------
# Not measured is not a disagreement
# ---------------------------------------------------------------------------


async def test_no_banked_row_yet_says_so_instead_of_publishing_zeros(call):
    out = await call(
        metrics={"task": "stamp_nfl_statpal_fixtures", "status": "no_data"},
        session=FakeSession(),
    )
    nfl = out["sports"][0]
    assert nfl["agreement"] is None
    assert "not measured" in nfl["note"]
    # And the table census still runs — the join may exist before a row does.
    assert nfl["live"]["anchors"] == 0


async def test_an_unparseable_pass_stamp_is_neither_fresh_nor_old(call):
    out = await call(
        metrics={
            "last_result_summary": {"agreement": _agreement_row()},
            "last_success_at": "not-a-timestamp",
        },
        session=FakeSession(),
    )
    nfl = out["sports"][0]
    assert nfl["pass_age_seconds"] is None
    assert nfl["last_pass_at"] == "not-a-timestamp"


async def test_every_shadowed_sport_gets_a_row_even_with_nothing_banked(call):
    out = await call(metrics={}, session=FakeSession())
    assert {s["sport_key"] for s in out["sports"]} == set(SHADOW_STAMPERS)
    assert out["spec"].endswith("ARTIFACT-AUTHORITY-LEDGER-SPEC.md")
