"""#7445 — the #7354 repair rail APPLIED TWICE must write nothing the second time.

## what happened, and why the unit guards could not see it

The rail merged with 54 unit guards and a real-Postgres census gate. Both were
right about what they measured. Neither could see this, because the defect is
not in one pass's decision — it is in the *relationship between two passes*, and
no fake session in the suite ever applied a write and then re-planned the row it
had just written.

Found by the after-check on the rail's own production apply (live/448). After
repairing `ev14947547` (Paris Saint-Germain 2-2 Stade Rennais, Ligue 1,
2026-08-23) at 08:59:56Z, the dry run immediately afterwards did **not** read
zero — it reported the same event repairable again::

    population=42 (settled, espn_id, last 60d, sport=soccer_france_ligue_one)
    swapped=1 repairable=1 aligned=40 unresolved=1 nothing_to_repair=0
      [repair] ev14947547 … Paris Saint-Germain vs Stade Rennais: 2-2 -> 2-2  score_snapshots=swap

The two other events repaired in the same pass read `[skip_nothing_to_repair]`.
That is the idempotence the rail is built on, and it works — for them.

## why a DRAW is different

`SLOT_COPY_PROOF` asks whether a store still holds ESPN's pair in ESPN's slots.
On a level final the swapped pair and the true pair are the SAME pair, so the
proof is satisfied by the correct orientation too: it is unfalsifiable and
answers yes forever. Every pass re-swaps the series — and a series' mid-game rows
are **not** symmetric (`0-1`, `0-2`, `1-2`), so each run alternates the in-game
score line between right and wrong, with nothing in the ledger able to say which
state the data is in.

## what this gate asserts, and why the corpus has two games in it

`apply` → `apply` → **the second pass writes zero rows**, on a real server,
through the shipped `run()` — the same function the Heroku one-off calls.

🔴 **A second pass that writes zero is only interesting if the first pass wrote
something.** A rail broken into refusing everything satisfies "the second pass
is a no-op" perfectly. So the corpus carries two swapped games:

* `DRAW` — level final, genuinely swapped by name, with asymmetric mid-game
  snapshot rows. Never written, in either pass, and its rows are asserted
  byte-identical across all three observations.
* `DECISIVE` — the specimen's shape, 38-27. **Repaired in pass 1** (that is the
  non-vacuity control) and `nothing_to_repair` in pass 2.

If the symmetry gate is ever widened past a level final, `DECISIVE` stops being
repaired and this file goes red rather than getting quieter.

The red-first arm performs surgery on the SHIPPED function to revert the gate and
asserts the draw's rows *do* flip on the second pass — so the fix cannot be read
as decoration, and removing it makes the surgery a no-op that fails loudly.
"""

from __future__ import annotations

import contextlib
import os
import textwrap
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7445 "
        "idempotence gate (CI job `search-recall` provides one)"
    ),
)

DRAW, DECISIVE = 74450001, 74450002

SOCCER_KEY = "soccer_france_ligue_one"
NCAAF_KEY = "americanfootball_ncaaf"

PSG, RENNES = "Paris Saint-Germain", "Stade Rennais"
WVU, UVA = "West Virginia Mountaineers", "Virginia Cavaliers"

#: The draw's true mid-game series, in OUR row's orientation (PSG home). Rennes
#: scored 9' and 38', PSG 71' and 82', so PSG — our home — trail throughout and
#: only the LAST point is symmetric. These are the rows that flipped.
DRAW_SERIES = ((0, 0), (0, 1), (0, 2), (1, 2), (2, 2))

#: The decisive game's series, slot-copied and therefore backwards: it holds
#: ESPN's pair in ESPN's slots, which is the proof that authorises the write.
DECISIVE_SERIES = ((0, 0), (7, 0), (14, 10), (27, 38))


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    """Real Postgres with the real schema, dropped and rebuilt.

    The rail's runtime DDL (`bak_7354_settled_orientation_swap`) is dropped on
    the way in AND the way out. This file applies, so the table is genuinely
    created here — leaving it behind is how #6919's gate broke a search test
    several hundred lines away in the same CI job, because
    `Base.metadata.drop_all` cannot see a table no model declares.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base
    from scripts.repair_7354_settled_orientation_swap import BAK_TABLE

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {BAK_TABLE}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            await _seed(s)
            yield s
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {BAK_TABLE}"))
        await engine.dispose()


async def _seed(session) -> None:
    """Two settled, swapped games — one level, one decisive."""
    from app.models import Event, Sport
    from app.models.models import ESPNSnapshot, ScoreSnapshot, WinProbSnapshot

    now = datetime.now(timezone.utc)
    session.add(Sport(id=7445_01, key=SOCCER_KEY, name="Ligue 1"))
    session.add(Sport(id=7445_02, key=NCAAF_KEY, name="NCAAF"))
    await session.flush()

    for eid, sport_id, home, away, score, espn_id, series, leg in (
        (DRAW, 7445_01, PSG, RENNES, (2, 2), "401876487", DRAW_SERIES, 0.05),
        (DECISIVE, 7445_02, WVU, UVA, (27, 38), "401856802", DECISIVE_SERIES, 0.05),
    ):
        commence = now - timedelta(days=3)
        session.add(
            Event(
                id=eid,
                sport_id=sport_id,
                home_team_name=home,
                away_team_name=away,
                commence_time=commence,
                completed_at=commence + timedelta(hours=3),
                status="completed",
                home_score=score[0],
                away_score=score[1],
                espn_id=espn_id,
                espn_win_prob_home=leg,
                win_probability_sources={"espn": {"value": leg}},
            )
        )
        for i, (h, a) in enumerate(series):
            at = commence + timedelta(minutes=15 * i)
            session.add(ScoreSnapshot(
                event_id=eid, captured_at=at, home_score=h, away_score=a))
            session.add(ESPNSnapshot(
                event_id=eid, captured_at=at, home_score=h, away_score=a,
                home_win_probability=leg, away_win_probability=1 - leg))
        session.add(WinProbSnapshot(
            event_id=eid, source="espn", captured_at=commence,
            home_win_probability=leg, away_win_probability=1 - leg))
    await session.commit()


@contextlib.asynccontextmanager
async def _yield(session):
    yield session


class _Espn:
    """ESPN answering READABLY, so the verdict is a positive `swapped`.

    That matters here in a way it did not for the census gate: this file is
    about what happens AFTER a write, so every gate in front of the write must
    genuinely pass. Both rows are neutral-site swaps — ESPN's home is our away.
    """

    _BY_ID = {
        "401876487": (RENNES, PSG, 2, 2),
        "401856802": (UVA, WVU, 27, 38),
    }

    async def get_event(self, sport_key, espn_id):  # noqa: D102
        home, away, hs, as_ = self._BY_ID[str(espn_id)]

        def team(name):
            return SimpleNamespace(
                name=name, display_name=name, abbreviation=None,
                location=None, nickname=None, short_display_name=name)

        return SimpleNamespace(
            status="post", home_score=hs, away_score=as_,
            home_team=team(home), away_team=team(away))


async def _apply(session, monkeypatch, capsys, **kwargs) -> tuple[int, str]:
    """Execute the SHIPPED `run()` with `--apply` against this database."""
    import app.services.espn_api as espn_mod
    import app.tasks.base as base
    from scripts import repair_7354_settled_orientation_swap as rail

    monkeypatch.setattr(base, "get_task_session", lambda: _yield(session))
    monkeypatch.setattr(espn_mod, "ESPNAPIService", _Espn)
    # The rail refuses to write anywhere but the producer app, by design. The
    # gate is the census file's subject and `TestTheWriteIsGatedOnTheNamedApp`'s;
    # here it is satisfied rather than tested.
    monkeypatch.setenv("HEROKU_APP_NAME", rail.PRODUCER_APP)

    params = {"apply": True, "limit": 50, "sport": None, "offset": 0,
              "since_days": 60}
    params.update(kwargs)
    code = await rail.run(**params)
    return code, capsys.readouterr().out


def _committed(out: str) -> tuple[int, dict]:
    """Parse the operator's `COMMITTED events=N rows: {...}` line.

    Parsed rather than substring-matched so a changed key order, or a count that
    grows a digit, cannot turn a real regression into a passing `in` test.
    """
    import ast
    import re

    m = re.search(r"COMMITTED events=(\d+) rows: (\{.*?\})", out)
    assert m, f"the apply pass printed no COMMITTED line:\n{out}"
    return int(m.group(1)), ast.literal_eval(m.group(2))


async def _series(session, event_id) -> dict:
    """Every store this rail can write, read back as plain scalars.

    Copied to scalars deliberately (gotcha #6): the rail commits and rolls back
    inside the same session, which expires live ORM objects.
    """
    from sqlalchemy import text

    out = {}
    for key, sql in (
        ("score_snapshots",
         "SELECT home_score, away_score FROM score_snapshots "
         "WHERE event_id = :e ORDER BY captured_at"),
        ("espn_snapshots",
         "SELECT home_score, away_score FROM espn_snapshots "
         "WHERE event_id = :e ORDER BY captured_at"),
        ("espn_leg",
         "SELECT home_win_probability, away_win_probability FROM win_prob_snapshots "
         "WHERE event_id = :e AND source = 'espn' ORDER BY captured_at"),
    ):
        out[key] = [tuple(r) for r in
                    (await session.execute(text(sql), {"e": event_id})).all()]
    row = (await session.execute(text(
        "SELECT home_score, away_score, espn_win_prob_home FROM events "
        "WHERE id = :e"), {"e": event_id})).first()
    out["event"] = tuple(row)
    return out


@needs_postgres
class TestASecondApplyWritesNothing:
    """The production failure: run the rail twice, read the rows."""

    async def test_the_second_pass_writes_zero_rows(
        self, session, monkeypatch, capsys
    ):
        """Read off the operator's OWN summary line, not off a re-derivation.

        `COMMITTED events=N rows: {...}` is what a person sees after
        `heroku run:detached`, so that is what is asserted — the same line that
        would have made the production defect visible had it read zero.
        """
        code, first = await _apply(session, monkeypatch, capsys)
        assert code == 0, first

        # ⭐ NON-VACUITY, asserted before anything else: if the first pass wrote
        # nothing, "the second pass wrote nothing" is a statement about a dead
        # rail and every other arm in this file is worthless.
        events, rows = _committed(first)
        assert events == 1, f"the first pass repaired {events} events:\n{first}"
        assert sum(rows.values()) > 0, f"the first pass wrote no rows:\n{first}"

        code, second = await _apply(session, monkeypatch, capsys)
        assert code == 0, second

        events, rows = _committed(second)
        assert events == 0, (
            f"the second pass committed {events} event(s) — the rail is not "
            f"idempotent:\n{second}")
        assert rows == dict.fromkeys(rows, 0), (
            f"the second pass wrote rows {rows} — the rail is not idempotent:\n"
            + second)
        assert "[repair] ev" not in second, second

    async def test_the_draws_asymmetric_rows_are_identical_across_both_passes(
        self, session, monkeypatch, capsys
    ):
        """The actual damage. `0-1`, `0-2`, `1-2` are not symmetric, so a
        re-swap is visible in the data even though the FINAL point is not.
        """
        before = await _series(session, DRAW)
        assert before["score_snapshots"] == list(DRAW_SERIES), before

        await _apply(session, monkeypatch, capsys)
        after_one = await _series(session, DRAW)

        await _apply(session, monkeypatch, capsys)
        after_two = await _series(session, DRAW)

        assert after_one == before, "pass 1 wrote the draw"
        assert after_two == before, "pass 2 wrote the draw"

    async def test_the_draw_is_reported_and_counted_on_every_pass(
        self, session, monkeypatch, capsys
    ):
        """A refusal nobody can see is a refusal nobody can audit. The event
        must not vanish into `nothing_to_repair` — it has its own counter and
        its own ledger line, on the second pass as much as the first.
        """
        _, first = await _apply(session, monkeypatch, capsys)
        _, second = await _apply(session, monkeypatch, capsys)

        for out in (first, second):
            assert "symmetric_final=1" in out, out
            assert f"[skip_symmetric_final] ev{DRAW}" in out, out
            assert "level at 2-2" in out, out

    async def test_the_decisive_game_is_repaired_once_and_then_left_alone(
        self, session, monkeypatch, capsys
    ):
        """⭐ THE ADMITTED CONTROL. Every other arm in this class is satisfied by
        a rail that refuses everything; this one is not.
        """
        before = await _series(session, DECISIVE)
        assert before["event"][:2] == (27, 38)

        await _apply(session, monkeypatch, capsys)
        after_one = await _series(session, DECISIVE)

        # Repaired: ESPN's away score is our home's.
        assert after_one["event"][:2] == (38, 27)
        assert after_one["score_snapshots"] == [(a, h) for h, a in DECISIVE_SERIES]
        assert after_one != before

        await _apply(session, monkeypatch, capsys)
        assert await _series(session, DECISIVE) == after_one, (
            "the second pass re-swapped the decisive game — the idempotence the "
            "rail already had has regressed"
        )


@needs_postgres
class TestTheDefectIsReproducibleFromTheShippedFunction:
    """Red-first, executed rather than remembered."""

    async def test_reverting_the_symmetry_gate_flips_the_draw_again(
        self, session, monkeypatch, capsys
    ):
        """Textual surgery on the SHIPPED planner reverts the gate, and the draw
        alternates again.

        This keeps the fix from being read as decoration: if the gate is ever
        removed, the surgery finds nothing and this arm fails on its own
        assertion rather than passing quietly.
        """
        import inspect

        from scripts import repair_7354_settled_orientation_swap as rail

        src = textwrap.dedent(inspect.getsource(rail.plan_orientation_repair))
        assert "if slot_pair == true_pair:" in src, (
            "the symmetry gate is not in plan_orientation_repair — this arm is "
            "no longer reverting anything (#7445)"
        )
        reverted = src.replace("if slot_pair == true_pair:", "if False:", 1)

        ns = dict(vars(rail))
        exec(compile(reverted, "<reverted>", "exec"), ns)  # noqa: S102
        monkeypatch.setattr(rail, "plan_orientation_repair",
                            ns["plan_orientation_repair"])

        before = await _series(session, DRAW)
        await _apply(session, monkeypatch, capsys)
        after_one = await _series(session, DRAW)
        await _apply(session, monkeypatch, capsys)
        after_two = await _series(session, DRAW)

        assert after_one["score_snapshots"] != before["score_snapshots"], (
            "the reverted planner did not write the draw — the surgery missed, "
            "so the green above proves nothing"
        )
        # And the alternation itself: pass 2 puts it back, which is exactly why
        # no ledger can say which state the data is in.
        assert after_two["score_snapshots"] == before["score_snapshots"]
