"""#7429's outage refusal must hold in `run`, not just in `prewrite_verdict`.

THE CLASS THIS GUARDS is **a decision proven on the extracted helper and
assumed at the call site**. CERT-3190 shipped `run` with these clauses in the
wrong order — an empty plan returned 0 before the unreadable refusal could
run — so a total Kalshi outage exited 0 as a clean population. The repair
(#7600 / CERT-3195) hoisted the decision into the pure `prewrite_verdict`,
and every test written for it calls that function DIRECTLY.

That leaves the fixed thing unguarded in the only place it failed. Nothing
currently executed asserts that `run` still calls `prewrite_verdict`, still
calls it before the backup, or still honours its exit code: move the backup
above the call, or drop the `if code is not None` branch, and the whole
existing suite stays green. Hoisting a decision out of a coroutine to make it
testable does not test the coroutine.

So these tests drive the real `async def run(args)` across the real boundary
with a recording session, and assert the three things an operator is owed
when the venue is dark: **exit 2, the refusal on stdout, and not one write
statement issued.**

`test_a_readable_venue_reaches_the_write` is not a courtesy — it is the
control. A "wrote nothing" assertion against a rig that could never write is
vacuous, and this is the test that proves the recorder sees writes when they
happen.
"""

import contextlib
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.kalshi_api import KalshiMarket  # noqa: E402
from scripts import (  # noqa: E402
    repair_7429_kalshi_count_leg_labels as mod,
)

#: Any statement that changes the database. `_CANDIDATES_SQL` and the backup
#: coverage count are reads and match none of these.
_WRITE = re.compile(r"\b(CREATE\s+TABLE|INSERT\s+INTO|UPDATE)\b", re.IGNORECASE)


class _Args:
    def __init__(self, apply=False, backup=False, allow_unreadable=False, show=10):
        self.apply = apply
        self.backup = backup
        self.allow_unreadable = allow_unreadable
        self.show = show


class _Row:
    """A candidate row exactly as `_CANDIDATES_SQL` hands it to `run`."""

    def __init__(self, id, name, external_id, event_ticker=None):
        self.id = id
        self.name = name
        self.external_id = external_id
        self.event_ticker = (
            event_ticker if event_ticker is not None else external_id.rsplit("-", 1)[0]
        )


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _RecordingSession:
    """Every statement `run` issues, so "wrote nothing" is measured.

    Deliberately answers the backup-coverage count with "fully covered": the
    point is to leave `--apply`'s own downstream gate wide open, so that if
    the outage refusal ever stops firing, nothing else accidentally catches
    the write and makes this test pass for the wrong reason.
    """

    def __init__(self, rows):
        self._rows = rows
        self.statements = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        if "FROM futures_outcomes o" in sql and "JOIN futures_markets" in sql:
            return _Result(rows=self._rows)
        if sql.lstrip().upper().startswith("SELECT COUNT(*)"):
            return _Result(scalar=len(params["ids"]) if params else 0)
        return _Result()

    async def commit(self):
        self.commits += 1

    @property
    def writes(self):
        return [s for s in self.statements if _WRITE.search(s)]


class _OutageService:
    """Kalshi refuses every read — the measured 2026-09-20 20:09Z condition."""

    def __init__(self):
        self.calls = 0

    async def get_markets(self, **kwargs):
        self.calls += 1
        raise Exception("Client error '429 Too Many Requests' for url ...")

    def parse_markets(self, raw):  # pragma: no cover — never reached
        return raw


class _LiveService:
    """The venue answers, corroborating every leg it is asked about."""

    def __init__(self, legs):
        self.legs = legs
        self.calls = 0

    async def get_markets(
        self, status=None, event_ticker=None, limit=None, cursor=None
    ):
        self.calls += 1
        return list(self.legs.get(event_ticker, [])), None

    def parse_markets(self, raw):
        return raw


@pytest.fixture
def rig(monkeypatch):
    """Wire `run` to a recorded session, a fake venue and a free clock."""

    def _build(rows, service):
        session = _RecordingSession(rows)

        @contextlib.asynccontextmanager
        async def _fake_session(**kwargs):
            yield session

        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
        monkeypatch.setattr(
            "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: service
        )

        # The retry budget is real; only its cost is faked.
        async def _no_sleep(_):
            return None

        monkeypatch.setattr(mod, "_asyncio_sleep", _no_sleep)
        # `--apply`/`--backup` are gated on the producer app (wrong_app_refusal),
        # which is a different refusal than the one under test.
        monkeypatch.setenv("HEROKU_APP_NAME", mod.PRODUCER_APP)
        return session

    return _build


# --------------------------------------------------------------------------
# The regression, driven through the boundary it actually failed at
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_total_outage_exits_2_and_writes_nothing_through_run(rig, capsys):
    """Every event unreadable, `--apply` asked for: refuse, and write nothing.

    This is the exact shape that exited 0 before #7600. Asserted here on
    `run`'s own return value rather than on `prewrite_verdict`'s, because the
    defect was never in the decision — it was in when `run` consulted it.
    """
    rows = [
        _Row(1, "E45", "RSENATESEATS-27-E45"),
        _Row(2, "E46", "RSENATESEATS-27-E46"),
        _Row(3, "E3", "KXHOUSEWINSTATE-AZD-E3"),
    ]
    service = _OutageService()
    session = rig(rows, service)

    code = await mod.run(_Args(apply=True, backup=True))

    assert code == 2, "a total venue outage must refuse, not report a clean population"

    out = capsys.readouterr().out
    assert "REFUSING --apply" in out
    # The operator is owed the size of the blind spot, in events and in rows.
    assert "3 of 3 candidate rows" in out
    assert "UNREADABLE   -> blind spot  3" in out

    assert (
        session.writes == []
    ), "the refusal fired but the run still issued a write statement"
    assert session.commits == 0, "nothing was written, so nothing may be committed"


@pytest.mark.asyncio
async def test_the_refusal_precedes_the_backup_not_merely_the_apply(rig, capsys):
    """`--backup` alone is ungated; `--backup --apply` together is not.

    The backup ordering is a separate fact from the exit code, and it is the
    one a re-ordering would break most quietly: a manifest taken from a
    blind-spotted plan describes the wrong set, and `--apply` then checks its
    coverage against exactly that manifest — the two agree with each other and
    disagree with the venue.
    """
    rows = [_Row(1, "E45", "RSENATESEATS-27-E45")]
    session = rig(rows, _OutageService())

    code = await mod.run(_Args(apply=True, backup=True))

    assert code == 2
    assert not any(
        "CREATE TABLE" in s or mod.BACKUP_TABLE in s for s in session.statements
    ), "a backup manifest was taken from a plan the venue never answered for"


@pytest.mark.asyncio
async def test_allow_unreadable_still_reaches_the_write_through_run(rig, capsys):
    """The deliberate-partial escape hatch survives the trip through `run`.

    Without this, a refusal that had become unconditional — the over-correction
    of the bug above — would look identical to a correct one.
    """
    rows = [_Row(1, "E45", "RSENATESEATS-27-E45")]
    session = rig(rows, _OutageService())

    code = await mod.run(_Args(apply=True, backup=True, allow_unreadable=True))

    assert code == 0
    # Nothing was corroborated, so there is nothing to write even here: the
    # hatch accepts a partial repair, it does not invent one.
    assert session.writes == []
    out = capsys.readouterr().out
    assert "nothing to repair" in out


# --------------------------------------------------------------------------
# The control: the rig can see a write, so "no writes" above means something
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_readable_venue_reaches_the_write(rig, capsys):
    """Same rig, venue answering — the backup and the UPDATE both land.

    If this ever fails, every "writes nothing" assertion in this file is
    vacuous and proves only that the fake cannot write.
    """
    rows = [_Row(1, "E3", "KXHOUSEWINSTATE-AZD-E3")]
    service = _LiveService(
        {
            "KXHOUSEWINSTATE-AZD": [
                KalshiMarket(
                    ticker="KXHOUSEWINSTATE-AZD-E3",
                    event_ticker="KXHOUSEWINSTATE-AZD",
                    title="How many House seats will Democrats win in Arizona?",
                    yes_sub_title="3",
                    status="active",
                )
            ]
        }
    )
    session = rig(rows, service)

    code = await mod.run(_Args(apply=True, backup=True))

    assert code == 0
    out = capsys.readouterr().out
    assert "corroborated -> REPAIR      1" in out
    assert "rewrote 1 names" in out

    kinds = " ".join(session.writes).upper()
    assert "CREATE TABLE" in kinds and "INSERT INTO" in kinds, "no backup was taken"
    assert "UPDATE FUTURES_OUTCOMES" in kinds, "the corroborated leg was not rewritten"
    assert session.commits >= 1


@pytest.mark.asyncio
async def test_the_write_control_is_the_venues_word_not_the_ticker(rig, capsys):
    """The control must not pass by rewriting on the ticker alone.

    Same readable venue, but it CONTRADICTS the stored label — Kalshi's own
    `yes_sub_title` is `'E85'`, the verbatim `KXSPOTIFY2D` payload. A run that
    writes here would make the control above agree with the defect #7429
    exists to remove.
    """
    rows = [_Row(1, "E85", "KXSPOTIFY2D-26MAR23-E85")]
    service = _LiveService(
        {
            "KXSPOTIFY2D-26MAR23": [
                KalshiMarket(
                    ticker="KXSPOTIFY2D-26MAR23-E85",
                    event_ticker="KXSPOTIFY2D-26MAR23",
                    title="Spotify Top Song rank",
                    yes_sub_title="E85",
                    status="closed",
                )
            ]
        }
    )
    session = rig(rows, service)

    code = await mod.run(_Args(apply=True, backup=True))

    assert code == 0
    assert session.writes == [], "a leg the venue contradicts was rewritten anyway"
    assert "refused      -> left alone  1" in capsys.readouterr().out
