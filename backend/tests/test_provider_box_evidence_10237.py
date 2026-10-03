"""#10268 (for #10237): a freshly received ESPN player box says what it is.

THE GAP. The After matrix (#10237) has to tell a proved final player box from
the midgame numbers a box writer kept. Today it cannot. The live pass stamps
``live: True`` even after ESPN went final. The completed pass, given an empty
answer, keeps the old live box as ``{**old, "live": False}``. Neither writer
records whether ESPN said the game was over, or which game the answer was for.

THE MARKER. Each of the three writers (live pass, completed pass, settled
backfill) writes one sibling key, ``box_score_data.provider_box_evidence``, in
the same whole-dict write as the box. Only a fresh, non-empty player box whose
response header names the ESPN id we asked for gets one. ``captured_at`` is the
box's own ``fetched_at``. ``provider_final`` is ``completed is True`` and the name
is not postponed/canceled/suspended/abandoned/delayed. Retained boxes keep the
marker they already had and never get a new one. The writer decides nothing
about official results. That is the reader's job (Authority).

FIXTURE. ``espn_summary_nfl_401872660_bills_at_texans_10103.json`` is
SOURCE-RETAINED (ESPN's summary, trimmed, values unedited). Its status is
ESPN's own ``STATUS_FINAL`` / ``post`` / ``completed: true``. The trim dropped
``header.id``. ``_summary()`` puts it back as the event's id, which the
fixture's own ``header.competitions[0].id`` carries (REPRESENTATIVE
restoration; ``get_event`` already reads ``header.id`` as the summary's event
id). Every other status variant below is REPRESENTATIVE, built to exercise a
refusal, and is not a claim about production.
"""
from __future__ import annotations

import contextlib
import copy
import inspect
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.utils import provider_box_evidence as pbe
from app.utils.provider_box_evidence import (
    NONFINAL_STATUS_NAMES,
    build_provider_box_evidence,
    provider_status_is_final,
)

FIXTURES = Path(__file__).parent / "fixtures"
SUMMARY = json.loads(
    (FIXTURES / "espn_summary_nfl_401872660_bills_at_texans_10103.json").read_text()
)

EVENT_ID = 14780141
ESPN_EVENT_ID = "401872660"
NFL = "americanfootball_nfl"

FINAL = {"name": "STATUS_FINAL", "state": "post", "completed": True}
IN_PROGRESS = {"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False}
POSTPONED_POST = {"name": "STATUS_POSTPONED", "state": "post", "completed": False}


def _summary(*, header_id=ESPN_EVENT_ID, status=None):
    s = copy.deepcopy(SUMMARY)
    if header_id is not None:
        s["header"]["id"] = header_id
    if status is not None:
        s["header"]["competitions"][0]["status"]["type"] = dict(status)
    return s


async def _context(summary=None):
    """The real ``get_event_context`` over the fixture."""
    from app.services.espn_api import ESPNAPIService

    svc = ESPNAPIService()
    try:
        with patch.object(svc, "_get", AsyncMock(return_value=summary or _summary())):
            return await svc.get_event_context(NFL, ESPN_EVENT_ID)
    finally:
        await svc.close()


# REPRESENTATIVE: the fixture's trim dropped `scoringPlays`.
_PLAY = {"team": "Buffalo Bills", "type": "Field Goal Good", "clock": "0:03",
         "period": 4, "away_score": 24, "home_score": 27}


def _scoring_only(ctx):
    """The same response with no player box: ESPN sent scoring plays only."""
    out = dict(ctx)
    out["box_score"] = {}
    out["box_score_player_identities"] = []
    out["scoring_plays"] = [dict(_PLAY)]
    return out


_EMPTY = {"box_score": {}, "scoring_plays": [], "scores": {}}


# ═══════════════════════════════════════════════════════════════════════════
# 1. The parser: two additive keys, `is_final` untouched
# ═══════════════════════════════════════════════════════════════════════════


def _header_scores(summary):
    from app.services.espn_api import ESPNAPIService

    return ESPNAPIService._parse_header_scores(summary)


def test_STATUS_FINAL_the_source_retained_fixture_carries_the_raw_triple():
    """Authority's build gate 5: the fixture is ESPN's own STATUS_FINAL."""
    out = _header_scores(_summary())
    assert out["provider_status"] == FINAL
    assert out["provider_event_id"] == ESPN_EVENT_ID
    assert out["is_final"] is True


def test_the_header_id_is_the_responses_own_and_is_never_borrowed():
    """With no ``header.id`` the key is None. The competition id is not used."""
    out = _header_scores(_summary(header_id=None))
    assert "id" not in SUMMARY["header"]
    assert SUMMARY["header"]["competitions"][0]["id"] == ESPN_EVENT_ID
    assert out["provider_event_id"] is None


def test_an_integer_header_id_is_stored_as_a_string():
    assert _header_scores(_summary(header_id=401872660))["provider_event_id"] == ESPN_EVENT_ID


def test_IS_FINAL_CONTROL_a_postponed_post_game_still_reads_is_final_as_before():
    """#980's boolean stays as loose as it was. Only the new keys are strict."""
    out = _header_scores(_summary(status=POSTPONED_POST))
    assert out["is_final"] is True
    assert out["provider_status"] == POSTPONED_POST


def test_EMPTY_HEADER_CONTROL_no_competition_still_returns_an_empty_dict():
    assert _header_scores({"header": {"id": ESPN_EVENT_ID, "competitions": []}}) == {}


# ═══════════════════════════════════════════════════════════════════════════
# 2. The pure builder
# ═══════════════════════════════════════════════════════════════════════════

PLAYERS = {"Josh Allen": {"passing_yards": 236.0}}
CAPTURED = "2026-09-14T03:30:00.123456+00:00"


def _scores(status=FINAL, provider_event_id=ESPN_EVENT_ID):
    return {"is_final": True, "provider_event_id": provider_event_id, "provider_status": status}


def _build(**overrides):
    kwargs = dict(
        requested_event_id=ESPN_EVENT_ID,
        players=PLAYERS,
        scores=_scores(),
        captured_at=CAPTURED,
    )
    kwargs.update(overrides)
    return build_provider_box_evidence(**kwargs)


def test_a_matching_fresh_final_box_gets_the_agreed_marker():
    assert _build() == {
        "provider": "espn",
        "provider_event_id": ESPN_EVENT_ID,
        "evidence_kind": "fresh_provider_box",
        "captured_at": CAPTURED,
        "provider_status": FINAL,
        "provider_final": True,
    }


def test_a_nonfinal_status_is_recorded_and_not_final():
    marker = _build(scores=_scores(IN_PROGRESS))
    assert marker["provider_status"] == IN_PROGRESS
    assert marker["provider_final"] is False


@pytest.mark.parametrize("name", sorted(NONFINAL_STATUS_NAMES))
def test_an_excluded_status_is_never_final_even_beside_completed_true(name):
    status = {"name": name, "state": "post", "completed": True}
    marker = _build(scores=_scores(status))
    assert marker["provider_status"] == status
    assert marker["provider_final"] is False


def test_the_excluded_set_is_exactly_the_agreed_five():
    assert NONFINAL_STATUS_NAMES == {
        "STATUS_POSTPONED",
        "STATUS_CANCELED",
        "STATUS_SUSPENDED",
        "STATUS_ABANDONED",
        "STATUS_DELAYED",
    }


@pytest.mark.parametrize(
    "status",
    [
        {"name": "STATUS_FINAL", "state": "post", "completed": False},
        {"name": "STATUS_FINAL", "state": "post", "completed": "true"},
        {"name": "STATUS_FINAL", "state": "post", "completed": 1},
        {"name": "STATUS_FINAL", "state": "post"},
        {"state": "post", "completed": True},
        {"name": "", "state": "post", "completed": True},
        {"name": None, "state": None, "completed": None},
        POSTPONED_POST,
    ],
)
def test_a_post_state_or_final_name_alone_never_asserts_final(status):
    assert _build(scores=_scores(status))["provider_final"] is False


@pytest.mark.parametrize("raw", [None, "STATUS_FINAL", ["STATUS_FINAL"], 7])
def test_a_missing_or_malformed_status_is_recorded_empty_and_not_final(raw):
    scores = _scores()
    scores["provider_status"] = raw
    marker = _build(scores=scores)
    assert marker["provider_status"] == {"name": None, "state": None, "completed": None}
    assert marker["provider_final"] is False


def test_non_scalar_status_fields_are_dropped_not_stored():
    status = {"name": {"x": 1}, "state": ["post"], "completed": True}
    marker = _build(scores=_scores(status))
    assert marker["provider_status"] == {"name": None, "state": None, "completed": True}
    assert marker["provider_final"] is False


@pytest.mark.parametrize(
    "requested, returned",
    [
        (ESPN_EVENT_ID, "401872661"),
        (ESPN_EVENT_ID, None),
        (ESPN_EVENT_ID, ""),
        (ESPN_EVENT_ID, 401872660),
        (None, ESPN_EVENT_ID),
        ("", ESPN_EVENT_ID),
        ("  ", ESPN_EVENT_ID),
    ],
)
def test_a_missing_or_different_id_mints_no_marker(requested, returned):
    assert _build(requested_event_id=requested, scores=_scores(provider_event_id=returned)) is None


def test_an_integer_requested_id_compares_by_its_string():
    assert _build(requested_event_id=401872660)["provider_event_id"] == ESPN_EVENT_ID


@pytest.mark.parametrize("players", [{}, None, [], ["Josh Allen"], "Josh Allen"])
def test_an_empty_or_malformed_player_box_mints_no_marker(players):
    assert _build(players=players) is None


@pytest.mark.parametrize("captured_at", ["", None, 0])
def test_no_capture_string_mints_no_marker(captured_at):
    assert _build(captured_at=captured_at) is None


@pytest.mark.parametrize("scores", [None, {}, [], "final"])
def test_no_scores_mints_no_marker(scores):
    assert _build(scores=scores) is None


def test_the_builder_does_not_change_its_inputs():
    players, scores = copy.deepcopy(PLAYERS), _scores()
    before = (copy.deepcopy(players), copy.deepcopy(scores))
    _build(players=players, scores=scores)
    assert (players, scores) == before


def test_PURITY_the_builder_reads_no_clock_and_imports_nothing_from_the_app():
    source = inspect.getsource(pbe)
    for forbidden in ("import datetime", "from datetime", "import time", "from app"):
        assert forbidden not in source, forbidden


def test_provider_status_is_final_refuses_non_dicts():
    for raw in (None, "STATUS_FINAL", True, ["STATUS_FINAL"]):
        assert provider_status_is_final(raw) is False
    assert provider_status_is_final(FINAL) is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. The three writers
# ═══════════════════════════════════════════════════════════════════════════


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _RecordingSession:
    def __init__(self, events):
        self._events = events
        self.writes: list = []

    async def execute(self, statement, params=None):
        if params is None:
            return _FakeResult(self._events)
        self.writes.append((statement, params))
        return _FakeResult([])

    def begin_nested(self):
        return contextlib.nullcontext()


def _service(context):
    service = MagicMock()
    service.get_event_context = AsyncMock(return_value=context)
    service.close = AsyncMock()
    return service


def _box_event(status, box_score_data=None):
    event = MagicMock()
    event.id = EVENT_ID
    event.espn_id = ESPN_EVENT_ID
    event.status = status
    event.box_score_data = box_score_data
    event.home_score, event.away_score = 27, 24
    event.sport = MagicMock()
    event.sport.key = NFL
    return event


async def _settled_write(context, event=None):
    from app.utils import espn_helpers

    service = _service(context)
    session = _RecordingSession([event or _box_event("completed")])
    with patch("app.services.espn_api.ESPNAPIService", return_value=service):
        await espn_helpers.fetch_completed_box_scores(session, {})
    assert service.get_event_context.await_count == 1
    if not session.writes:
        return None
    assert len(session.writes) == 1
    return json.loads(session.writes[0][1]["bsd"])


async def _live_write(context, event=None):
    from app.utils import espn_helpers

    service = _service(context)
    session = _RecordingSession([event or _box_event("live")])
    with patch("app.services.espn_api.ESPNAPIService", return_value=service):
        await espn_helpers.fetch_live_box_scores(session, {})
    assert service.get_event_context.await_count == 1
    if not session.writes:
        return None
    assert len(session.writes) == 1
    return json.loads(session.writes[0][1]["bsd"])


async def _backfill_write(context, event=None):
    from app.tasks import espn_sync

    event = event or _box_event("completed")
    service = _service(context)

    @asynccontextmanager
    async def _session():
        yield _RecordingSession([event])

    with patch.object(espn_sync, "get_task_session", _session), patch(
        "app.services.espn_api.ESPNAPIService", return_value=service
    ), patch("asyncio.sleep", AsyncMock()):
        await espn_sync._backfill_box_scores(limit=1)
    assert service.get_event_context.await_count == 1
    return event.box_score_data


WRITERS = [_settled_write, _live_write, _backfill_write]


# — gate 1: fresh, matching, final ——————————————————————————————————————————


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", WRITERS)
async def test_every_writer_marks_a_fresh_matching_final_box(writer):
    ctx = await _context()
    stored = await writer(ctx)
    marker = stored["provider_box_evidence"]
    assert marker == {
        "provider": "espn",
        "provider_event_id": ESPN_EVENT_ID,
        "evidence_kind": "fresh_provider_box",
        "captured_at": stored["fetched_at"],
        "provider_status": FINAL,
        "provider_final": True,
    }
    # One clock: the marker's capture IS the box's fetched_at string.
    assert marker["captured_at"] is not None and marker["captured_at"] == stored["fetched_at"]
    # The box beside it is unchanged.
    assert stored["players"] == ctx["box_score"]
    assert stored["player_identities"] == ctx["box_score_player_identities"]
    assert stored["scoring_plays"] == ctx["scoring_plays"]


# — gate 2: fresh nonfinal on a completed row ————————————————————————————————


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", [_settled_write, _backfill_write])
async def test_a_fresh_nonfinal_box_on_a_completed_row_is_marked_not_final(writer):
    ctx = await _context(_summary(status=IN_PROGRESS))
    stored = await writer(ctx)
    assert stored["provider_box_evidence"]["provider_final"] is False
    assert stored["provider_box_evidence"]["provider_status"] == IN_PROGRESS
    # The settled writers' payload semantics are unchanged: no live stamp.
    assert "live" not in stored


# — gate 3: excluded statuses never assert final; is_final unchanged —————————


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", WRITERS)
@pytest.mark.parametrize(
    "status",
    [POSTPONED_POST]
    + [{"name": n, "state": "post", "completed": True} for n in sorted(NONFINAL_STATUS_NAMES)]
    + [{"name": "STATUS_FINAL", "state": "post", "completed": False}],
)
async def test_no_writer_asserts_final_for_an_excluded_or_incomplete_status(writer, status):
    ctx = await _context(_summary(status=status))
    assert ctx["scores"]["is_final"] is True  # #980's loose boolean, unchanged
    stored = await writer(ctx)
    assert stored["provider_box_evidence"]["provider_final"] is False
    assert stored["provider_box_evidence"]["provider_status"] == status


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", WRITERS)
async def test_a_missing_status_block_is_recorded_empty_and_never_final(writer):
    summary = _summary()
    del summary["header"]["competitions"][0]["status"]
    stored = await writer(await _context(summary))
    marker = stored["provider_box_evidence"]
    assert marker["provider_status"] == {"name": None, "state": None, "completed": None}
    assert marker["provider_final"] is False


# — gate 4: the live writer stays live ——————————————————————————————————————


@pytest.mark.asyncio
async def test_a_final_box_fetched_by_the_live_pass_keeps_live_true():
    stored = await _live_write(await _context())
    assert stored["live"] is True
    assert stored["provider_box_evidence"]["provider_final"] is True


# — gate 5: identity, and a scoring-only answer ——————————————————————————————


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", WRITERS)
@pytest.mark.parametrize("header_id", [None, "401872661"])
async def test_a_missing_or_different_header_id_writes_the_box_with_no_marker(writer, header_id):
    ctx = await _context(_summary(header_id=header_id))
    stored = await writer(ctx)
    assert "provider_box_evidence" not in stored
    # The box itself is written exactly as before.
    assert stored["players"] == ctx["box_score"]
    assert stored["player_identities"] == ctx["box_score_player_identities"]


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", WRITERS)
async def test_a_scoring_only_answer_writes_its_plays_and_no_marker(writer):
    ctx = _scoring_only(await _context())
    assert ctx["scores"]["provider_status"] == FINAL
    stored = await writer(ctx)
    assert stored["scoring_plays"] == ctx["scoring_plays"]
    assert stored["players"] == {}
    assert "provider_box_evidence" not in stored


@pytest.mark.asyncio
async def test_a_scoring_only_answer_does_not_carry_the_old_boxs_marker_over():
    """The completed pass replaces the whole dict. The old marker described the
    old players, so it must not ride onto a box with none."""
    live_box = await _live_write(await _context(_summary(status=IN_PROGRESS)))
    assert live_box["provider_box_evidence"]["provider_final"] is False
    settled = await _settled_write(
        _scoring_only(await _context()), event=_box_event("completed", live_box)
    )
    assert "provider_box_evidence" not in settled


# — gate 6: retained, dark, error, empty ————————————————————————————————————


@pytest.mark.asyncio
async def test_an_empty_answer_over_a_live_box_keeps_its_old_marker_exactly():
    live_box = await _live_write(await _context(_summary(status=IN_PROGRESS)))
    old_marker = copy.deepcopy(live_box["provider_box_evidence"])
    settled = await _settled_write(_EMPTY, event=_box_event("completed", live_box))
    assert settled["live"] is False
    # Not restamped and not promoted: the same capture and the same false final.
    assert settled["provider_box_evidence"] == old_marker
    assert settled["provider_box_evidence"]["provider_final"] is False
    assert settled["provider_box_evidence"]["captured_at"] == live_box["fetched_at"]
    assert settled["fetched_at"] == live_box["fetched_at"]
    assert settled["players"] == live_box["players"]


@pytest.mark.asyncio
async def test_LEGACY_an_empty_answer_over_a_box_with_no_marker_mints_none():
    legacy = {
        "source": "espn",
        "fetched_at": "2026-09-14T02:00:00+00:00",
        "players": {"Josh Allen": {"passing_yards": 120.0}},
        "scoring_plays": [],
        "live": True,
    }
    settled = await _settled_write(_EMPTY, event=_box_event("completed", dict(legacy)))
    assert settled == {**legacy, "live": False}
    assert "provider_box_evidence" not in settled


@pytest.mark.asyncio
async def test_an_empty_answer_with_no_box_writes_the_error_stamp_and_no_marker():
    settled = await _settled_write(_EMPTY)
    assert settled["error"] == "not_available"
    assert "provider_box_evidence" not in settled


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", [_settled_write, _live_write])
async def test_authority_dark_writes_nothing(writer):
    assert await writer(None) is None


@pytest.mark.asyncio
async def test_backfill_authority_dark_leaves_the_stored_box_alone():
    stored = {"source": "espn", "fetched_at": "x", "players": {"A": {"hits": 1.0}}}
    event = _box_event("completed", copy.deepcopy(stored))
    assert await _backfill_write(None, event=event) == stored


@pytest.mark.asyncio
async def test_backfill_empty_answer_keeps_the_old_marker_and_only_adds_checked_at():
    old = await _backfill_write(await _context(_summary(status=IN_PROGRESS)))
    old_marker = copy.deepcopy(old["provider_box_evidence"])
    after = await _backfill_write(_EMPTY, event=_box_event("completed", copy.deepcopy(old)))
    assert after["provider_box_evidence"] == old_marker
    assert after["provider_box_evidence"]["captured_at"] == old["fetched_at"]
    assert after["fetched_at"] == old["fetched_at"]
    # The checked-at keys are anti-thrash bookkeeping, not a capture.
    assert set(after) == set(old)


@pytest.mark.asyncio
async def test_backfill_empty_answer_with_no_box_writes_the_error_stamp_and_no_marker():
    stored = await _backfill_write(_EMPTY)
    assert stored["error"] == "not_available"
    assert "provider_box_evidence" not in stored


# — gate 7: a later genuinely fresh capture replaces box and marker together ——


@pytest.mark.asyncio
async def test_a_later_fresh_final_box_replaces_the_box_and_its_marker_together():
    live_box = await _live_write(await _context(_summary(status=IN_PROGRESS)))
    live_box["fetched_at"] = live_box["provider_box_evidence"]["captured_at"] = (
        "2026-09-14T02:00:00+00:00"
    )
    settled = await _settled_write(await _context(), event=_box_event("completed", live_box))
    marker = settled["provider_box_evidence"]
    assert marker["provider_final"] is True
    assert marker["captured_at"] == settled["fetched_at"] != "2026-09-14T02:00:00+00:00"
    # Nothing beyond the agreed fields: no revision or version from the writer.
    assert set(marker) == {
        "provider",
        "provider_event_id",
        "evidence_kind",
        "captured_at",
        "provider_status",
        "provider_final",
    }
    assert "live" not in settled


# — gate 8: nothing else moves ————————————————————————————————————————————————


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", WRITERS)
async def test_the_marker_is_the_only_new_key_on_the_box(writer):
    with_id = await writer(await _context())
    without_id = await writer(await _context(_summary(header_id=None)))
    assert set(with_id) - set(without_id) == {"provider_box_evidence"}
    for key in set(without_id) - {"fetched_at", "period_scores_checked_at", "scores_checked_at"}:
        assert with_id[key] == without_id[key], key
