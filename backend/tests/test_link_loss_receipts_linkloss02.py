"""LINKLOSS-02 — a link that is REMOVED or REPLACED leaves a receipt.

THE QUESTION THAT HAD NO ANSWER. On 2026-09-02 the bus asked whether an event
merge had dropped 261 market links. It was unanswerable, and not for want of
looking: ``market_match_receipts`` knew only ``linked`` and ``rejected``, both
of them statements about an ATTEMPT to attach. A market that had a price on a
game card yesterday and none today left the same evidence as one that was never
linked — the last receipt still read ``linked``, and the row underneath it sat
at NULL. Meanwhile ``futures_markets`` had no transition timestamp at all, so
the markets that had simply SETTLED out of the open population could not be
subtracted from the drop.

Four writers can end or move a link, and this file holds each of them to the
same contract:

1.  the matcher's Phase 1.5 re-validation (unlink and relink);
2.  the matcher's Phase 2 wrong-game sweeps, the #944 relink and the Q435
    segment reconcile (bulk moves);
3.  a twin cleanup repointing children onto the survivor;
4.  an operator running an admin repair.

WHAT IS TESTED HERE, AND WHY IN THIS SHAPE. Two of the guards are source scans,
which is a shape worth justifying rather than assuming. The receipt for an
unlink is written on a *different session* from the unlink, published after a
commit that happens in a caller three call-frames up; there is no unit-level
seam at which "the unlink happened and the receipt did not" can be observed
without rebuilding most of the matcher's session machinery in fakes. What can
be stated mechanically is the invariant that actually goes wrong over time — a
NEW unlink site lands and nobody wires a receipt to it — and that is a property
of the source. Both scans therefore RAISE on a shape they cannot classify: a
scanner that skips what it does not understand reports zero for exactly the case
it was built to catch.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import re

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils import event_child_repoint as ecr
from app.utils import market_settlement as ms
from app.utils import match_receipts as mr

NOW_KW = dict(
    source="kalshi", external_id="KXNFLGAME-25SEP07DALPHI-DAL",
    market_name="Dallas Cowboys vs Philadelphia Eagles",
)


def _receipt(**kw):
    from datetime import datetime, timezone

    base = dict(
        market_id=1, phase=mr.PHASE_PHASE15_REVALIDATE,
        attempted_at=datetime(2026, 9, 2, 19, 0, tzinfo=timezone.utc),
        **NOW_KW,
    )
    base.update(kw)
    return mr.MatchReceipt(**base)


# =============================================================================
# Part 1 — the vocabulary is closed, countable, and fits its columns
# =============================================================================


def test_every_outcome_constant_is_in_the_registry():
    """A value that exists only as a module constant is not a value the census
    can GROUP BY — the same argument that closes the reject enum."""
    declared = {
        v for k, v in vars(mr).items()
        if k.startswith("OUTCOME_") and isinstance(v, str)
    }
    assert declared == set(mr.OUTCOMES)


def test_every_actor_constant_is_in_the_registry():
    declared = {
        v for k, v in vars(mr).items()
        if k.startswith("ACTOR_") and isinstance(v, str)
    }
    assert declared == set(mr.ACTORS)


def test_the_new_outcome_does_not_fit_the_old_column():
    """Proves the migration's ALTER is load-bearing, not cosmetic.

    ``superseded_by_twin_merge`` is longer than the ``String(16)`` the first
    receipts migration created. Without the widening every twin-merge receipt
    would raise on insert — and receipt writes are deliberately swallowed, so
    the failure would be a silent, permanent zero in the one bucket the census
    was built to count.
    """
    assert len(mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE) > 16


def test_outcomes_actors_and_phases_fit_the_columns_the_migration_creates():
    from app.models.models import MarketMatchReceipt as M

    assert len(max(mr.OUTCOMES, key=len)) <= M.outcome.type.length
    assert len(max(mr.ACTORS, key=len)) <= M.actor.type.length
    assert len(max(mr.PHASES, key=len)) <= M.phase.type.length


def test_an_unknown_actor_is_refused_by_name():
    with pytest.raises(ValueError) as exc:
        _receipt().unlink(42, "someone")
    assert "someone" in str(exc.value)
    assert "ACTORS" in str(exc.value)


# =============================================================================
# Part 2 — (previous_event_id, linked_event_id) reads as loss / move / attach
# =============================================================================


def test_an_unlink_names_what_it_detached_from():
    r = _receipt().unlink(42)
    assert r.outcome == mr.OUTCOME_UNLINKED
    assert r.previous_event_id == 42
    assert r.linked_event_id is None
    assert r.actor == mr.ACTOR_MATCHER_PASS
    assert r.reject_reason is None


def test_a_supersede_names_both_ends_of_the_move():
    r = _receipt().supersede(42, 91)
    assert r.outcome == mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE
    assert r.previous_event_id == 42
    assert r.linked_event_id == 91
    assert r.actor == mr.ACTOR_TWIN_CLEANUP


def test_a_first_attach_is_not_a_move():
    """A plain link carries no previous id and no actor.

    If it did, every ordinary attach would land in the link-change census and
    the 261 the bus is trying to explain would be buried under thousands.
    """
    r = _receipt().link(91)
    assert r.previous_event_id is None
    assert r.actor is None


def test_a_relink_is_a_link_that_says_where_it_came_from():
    r = _receipt().link(91, previous_event_id=42, cause="mislinked")
    assert r.outcome == mr.OUTCOME_LINKED
    assert r.linked_event_id == 91
    assert r.previous_event_id == 42
    assert r.actor == mr.ACTOR_MATCHER_PASS


def test_relinking_to_the_same_event_is_not_a_move():
    """Idempotence. These passes re-run every 15 minutes over the same rows;
    counting a no-op re-link as a move would manufacture a link-change wave
    out of a pass that changed nothing."""
    r = _receipt().link(42, previous_event_id=42)
    assert r.previous_event_id is None
    assert r.actor is None


def test_the_row_carries_the_two_new_columns():
    row = _receipt().unlink(42).to_row()
    assert row["previous_event_id"] == 42
    assert row["actor"] == mr.ACTOR_MATCHER_PASS
    assert row["outcome"] == mr.OUTCOME_UNLINKED


def test_the_upsert_overwrites_the_previous_link_and_actor():
    """The table is ONE ROW PER MARKET, upserted.

    An unlink lands on top of the market's earlier ``linked`` row. If the
    conflict clause did not carry these two columns, the row would end up
    ``outcome='unlinked'`` beside a stale ``actor``/``previous_event_id`` from
    an older change — or, on the first unlink of a market that was linked, no
    actor at all. Reading the SET list is the only place this is observable
    without a live PostgreSQL.
    """
    src = inspect.getsource(mr.flush_receipts)
    for column in ("previous_event_id", "actor"):
        assert f'"{column}": stmt.excluded.{column}' in src, (
            f"{column} is written on insert but not on conflict — the upsert "
            f"would leave a stale value on every re-attempt"
        )


# =============================================================================
# Part 3 — a fabricated link loss is worse than none (CERT-771, widened)
# =============================================================================


class _DurabilitySession:
    def __init__(self, durable: dict):
        self._durable = durable

    async def execute(self, stmt):
        rows = list(self._durable.items())

        class _R:
            def all(self_inner):
                return rows

        return _R()


def test_an_unlink_that_did_not_land_is_downgraded_not_published():
    """The direction that matters most.

    A published ``unlinked`` whose row is still attached does not merely lose
    information: it INVENTS a link loss, in the one table the census reads to
    decide whether links were lost. That is a strictly worse failure than the
    un-durable attach CERT-771 caught, and it must be caught by the same read.
    """
    ghost = _receipt(market_id=1).unlink(42)
    real = _receipt(market_id=2).unlink(42)

    n = asyncio.run(mr.verify_links_are_durable(
        _DurabilitySession({1: 42, 2: None}), [ghost, real]
    ))

    assert n == 1
    assert ghost.outcome == mr.OUTCOME_REJECTED
    assert ghost.reject_reason == mr.REJECT_LINK_NOT_DURABLE
    assert ghost.detail["claimed_outcome"] == mr.OUTCOME_UNLINKED
    assert ghost.detail["observed_event_id"] == 42
    assert ghost.detail["previous_event_id"] == 42
    # The unlink that DID land is published untouched.
    assert real.outcome == mr.OUTCOME_UNLINKED
    assert real.previous_event_id == 42


def test_a_supersede_is_verified_against_the_survivor():
    landed = _receipt(market_id=1).supersede(42, 91)
    stranded = _receipt(market_id=2).supersede(42, 91)

    n = asyncio.run(mr.verify_links_are_durable(
        _DurabilitySession({1: 91, 2: 42}), [landed, stranded]
    ))

    assert n == 1
    assert landed.outcome == mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE
    assert stranded.reject_reason == mr.REJECT_LINK_NOT_DURABLE


def test_a_rejected_receipt_is_still_not_re_read():
    """``rejected`` asserts nothing about ``event_id``, so widening the check
    must not start charging a database read for rows that make no claim."""
    reads = []

    class _CountingSession:
        async def execute(self, stmt):
            reads.append(stmt)
            raise AssertionError("a rejected receipt must not be re-read")

    n = asyncio.run(mr.verify_links_are_durable(
        _CountingSession(), [_receipt().reject(mr.REJECT_NO_CANDIDATE)]
    ))
    assert n == 0 and reads == []


def test_the_out_of_band_writer_never_raises_and_reports_zero():
    """A merge that has already deleted the losing event must not then fail
    because its explanation could not be written."""

    class _Boom:
        def __call__(self):
            raise RuntimeError("no session today")

    written = asyncio.run(mr.record_link_change_receipts(
        [{"id": 1, "source": "kalshi", "external_id": "x", "name": "y"}],
        previous_event_id=42, new_event_id=91,
        actor=mr.ACTOR_TWIN_CLEANUP, phase=mr.PHASE_TWIN_MERGE,
        session_factory=_Boom(),
    ))
    assert written == 0


def test_a_matcher_move_is_a_link_and_a_twin_move_is_a_supersede():
    """The out-of-band writer picks the outcome off the actor.

    Collapsing them would make one merge read as hundreds of matching
    decisions — the exact misreading ``superseded_by_twin_merge`` exists to
    prevent.
    """
    captured = []

    class _Session:
        async def execute(self, stmt):
            class _R:
                def all(self_inner):
                    return [(1, 91)]
            return _R()

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    async def _run(actor):
        import app.utils.match_receipts as m

        original = m.flush_receipts

        async def _spy(session, receipts, chunk=500):
            captured.append(receipts[0].outcome)
            return await original(session, receipts, chunk)

        m.flush_receipts = _spy
        try:
            # flush_receipts will fail on the fake session; the writer swallows
            # it, and the outcome was already captured before the write.
            await m.record_link_change_receipts(
                [{"id": 1, "source": "kalshi", "external_id": "x", "name": "y"}],
                previous_event_id=42, new_event_id=91,
                actor=actor, phase=mr.PHASE_TWIN_MERGE,
                session_factory=lambda: _Session(),
            )
        finally:
            m.flush_receipts = original

    asyncio.run(_run(mr.ACTOR_TWIN_CLEANUP))
    asyncio.run(_run(mr.ACTOR_MATCHER_PASS))
    assert captured == [mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE, mr.OUTCOME_LINKED]


# =============================================================================
# Part 4 — no unlink site in the matcher without a receipt beside it
#
# The ratchet. Every existing site is wired; what this catches is the NEXT one.
# =============================================================================

#: How many source lines after an ``event_id``-clearing write the receipt call
#: may appear. Every current site writes it within three; ten leaves room for a
#: log line and a blank without letting a receipt at the bottom of an unrelated
#: branch count as coverage.
_RECEIPT_WINDOW = 10


def _unlink_sites(source: str) -> list[int]:
    """Line numbers (1-based) of every write that clears a market's event link.

    Two shapes, and the scan REFUSES to be clever about a third: an ORM
    attribute assignment and a Core ``.values(event_id=None)``. A new shape
    (raw ``SET event_id = NULL``) is caught by
    :func:`test_the_scan_refuses_a_shape_it_cannot_classify`, which fails rather
    than reporting the clean zero a silent skip would produce.
    """
    sites = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"\bmarket\.event_id\s*=\s*None\b", stripped):
            sites.append(i)
        elif re.search(r"\.values\(event_id=None\)", stripped):
            sites.append(i)
    return sites


def test_every_unlink_in_the_matcher_records_a_link_change():
    source = inspect.getsource(pmm)
    lines = source.splitlines()
    sites = _unlink_sites(source)

    assert len(sites) >= 4, (
        "the scan found fewer unlink sites than the four this change wired — "
        "it has stopped matching the code it is guarding"
    )

    for line_no in sites:
        window = "\n".join(lines[line_no - 1: line_no - 1 + _RECEIPT_WINDOW])
        assert "_record_link_change" in window, (
            f"prediction_market_matching.py:{line_no} clears a market's "
            f"event_id with no receipt within {_RECEIPT_WINDOW} lines. A link "
            f"that ends without a receipt is the hole LINKLOSS-02 closed."
        )


def test_the_scan_refuses_a_shape_it_cannot_classify():
    """A scanner that silently skips an unrecognised write reports zero for
    exactly the case it exists to catch. Prove the two shapes it does know are
    the two the module uses, by finding every event_id-to-None write with a
    second, independent reading — the AST."""
    tree = ast.parse(inspect.getsource(pmm))
    ast_sites = 0
    for node in ast.walk(tree):
        # `x.event_id = None`
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if node.value.value is None and any(
                isinstance(t, ast.Attribute) and t.attr == "event_id"
                for t in node.targets
            ):
                ast_sites += 1
        # `.values(event_id=None)`
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "values":
                for kw in node.keywords:
                    if (
                        kw.arg == "event_id"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is None
                    ):
                        ast_sites += 1

    regex_sites = len(_unlink_sites(inspect.getsource(pmm)))
    assert ast_sites == regex_sites, (
        f"the AST sees {ast_sites} event_id-clearing writes and the line scan "
        f"sees {regex_sites}. A write in a shape the scan cannot see is a "
        f"write it will never demand a receipt for."
    )


def test_the_bulk_move_passes_receipt_their_moves():
    """#944 and Q435 both MOVE links in bulk SQL, hundreds at a time."""
    relink = inspect.getsource(pmm._relink_collapsed_game_markets)
    # Asserted on the SQL identifiers, not on the word "RETURNING": the comment
    # explaining the clause also contains that word, so a bare containment
    # check stays green with the clause deleted (measured — mutation M7 of this
    # change's battery survived exactly that assertion).
    assert "RETURNING fm.id" in relink, (
        "the relink reports a rowcount only — a count cannot name which event "
        "each market came off, which is the whole question"
    )
    assert "from_eid" in relink and "to_eid" in relink, (
        "the relink returns rows but not the PAIR; a receipt that cannot say "
        "where a link came from explains nothing"
    )
    assert "_receipt_bulk_moves" in relink

    reconcile = inspect.getsource(pmm._reconcile_kalshi_match_segments)
    assert "_receipt_bulk_moves" in reconcile


def test_a_bulk_adopt_is_not_counted_as_a_move():
    """An ADOPT attaches a market that was on nothing. Counting it as a move
    would inflate the census with links that were never lost."""
    written = asyncio.run(pmm._receipt_bulk_moves(
        [(None, 91, {"id": 1, "source": "kalshi", "external_id": "x",
                     "name": None})],
        phase=mr.PHASE_SEGMENT_RECONCILE, label="test",
    ))
    assert written == 0


def test_the_matcher_publishes_link_changes_after_the_commit():
    """A receipt published before the commit is re-read against the pre-change
    row and downgraded — reporting a real unlink as a failed one."""
    src = inspect.getsource(pmm._match_prediction_markets)
    commit = src.index("await session.commit()", src.index("_phase15_revalidate"))
    flush = src.index("_flush_pass_receipts(", commit)
    assert commit < flush, (
        "Phase 1.5's receipts are flushed before its commit, so every unlink "
        "will be downgraded as un-durable"
    )


# =============================================================================
# Part 5 — settled_at: the subtraction that makes the census readable
# =============================================================================

#: The one settlement write that must NOT stamp. It is a ``pg_insert`` of a
#: market that settled some time in the past and is only now being ingested by
#: the Kalshi settled-events backfill; stamping it with the ingest clock would
#: assert it settled today. NULL means "we did not observe it", which is true.
_STAMP_EXEMPT = {"app/tasks/kalshi.py": ["pg_insert"]}


def test_the_stamp_keeps_the_first_observation():
    """Every settlement writer is idempotent by design — the Kalshi poll
    re-reads its settled window, the winner backfill re-runs its phases. A
    plain assignment would move the stamp forward on each sweep, so a market
    that settled on Tuesday would report settling whenever it was last swept.
    """
    assert "COALESCE" in ms.settled_at_sql()
    assert ms.settled_at_sql("fm") == (
        "settled_at = COALESCE(fm.settled_at, NOW())"
    )

    from app.models.models import FuturesMarket

    values = ms.settled_values(FuturesMarket.settled_at)
    assert set(values) == {"settled_at"}
    assert "coalesce" in str(values["settled_at"]).lower()


#: A DIRECT write names the column and the value in one place, so the stamp
#: belongs beside it. Six lines each way covers every raw-SQL ``SET`` list and
#: every ``.values()`` in the tree.
_DIRECT_WINDOW = 6

#: Every shape in the tree that WRITES ``'resolved'`` as a literal. The value
#: is on the same line as the column in all four, which is what makes them
#: mechanically separable from the several hundred places that merely READ
#: ``status = 'resolved'`` in a WHERE clause.
_DIRECT_WRITE = re.compile("|".join([
    r"SET\s+status\s*=\s*'resolved'",                # raw SQL SET list
    r'\.status\s*=\s*"resolved"',                    # ORM attribute assignment
    r'(^|[\s(])status\s*=\s*"resolved"',             # .values(status=...)
    r'"status"\s*:\s*[^,]*"resolved"',               # upsert dict literal,
                                                     # including the ternary
]))

#: A raw-SQL status write, whatever it writes. Captured rather than matched so
#: an UNRECOGNISED value fails loudly instead of being skipped — a scanner that
#: drops what it does not understand reports the clean zero it was built to
#: catch.
_SQL_SET_STATUS = re.compile(r"SET\s+status\s*=\s*'(\w+)'")

#: Values a raw-SQL ``SET status`` on ``futures_markets`` may write without the
#: scan understanding more. ``open`` is the un-resolve direction and has its own
#: test; anything else is a transition nobody has thought about here.
_KNOWN_SET_VALUES = {"resolved", "open"}

#: How far back to look for the ``UPDATE <table>`` a ``SET`` belongs to. Every
#: raw-SQL update in these files puts the two within a couple of lines.
_UPDATE_LOOKBACK = 8


def _sql_update_target(lines: list[str], i: int) -> str | None:
    """The table the ``SET`` on line ``i`` belongs to, or None if unreadable.

    ``events`` also has a ``status`` column and also gets bulk transitions, so a
    scan that did not read the table would demand a ``settled_at`` on a table
    that does not have one.
    """
    for j in range(i, max(-1, i - _UPDATE_LOOKBACK), -1):
        m = re.search(r"UPDATE\s+(\w+)", lines[j])
        if m:
            return m.group(1)
    return None


def _resolved_writes(text: str) -> list[tuple[int, str]]:
    """Every place in ``text`` that writes a market's status as 'resolved'.

    Returns ``(line_number, window_text)``.

    WHAT THIS DOES NOT COVER, stated rather than implied: a write whose value
    reaches the statement through a local (``"status": market_status`` in the
    Kalshi poll) is invisible to any line-level scan, because the line carries
    no value at all. That one shape has its own named test —
    :func:`test_the_kalshi_poll_upsert_couples_the_stamp_to_the_status` — and
    the two together are the coverage claim. A guard that pretended to cover it
    by widening the window until it happened to pass would be worse than one
    that says where it stops.
    """
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        sql_set = _SQL_SET_STATUS.search(stripped)
        if sql_set:
            target = _sql_update_target(lines, i)
            if target is None:
                raise AssertionError(
                    f"line {i + 1} sets a status and the scan cannot find the "
                    f"table it belongs to within {_UPDATE_LOOKBACK} lines:\n"
                    f"  {stripped}"
                )
            if target != "futures_markets":
                continue
            if sql_set.group(1) not in _KNOWN_SET_VALUES:
                raise AssertionError(
                    f"line {i + 1} moves a market to an unrecognised status:\n"
                    f"  {stripped}\n"
                    f"Decide whether it needs a settled_at stamp and add it to "
                    f"_KNOWN_SET_VALUES — a transition this scan cannot read "
                    f"is one it will never demand a stamp for."
                )
            if sql_set.group(1) != "resolved":
                continue
        elif "SET status" in stripped:
            raise AssertionError(
                f"line {i + 1} sets a status to a non-literal the scan cannot "
                f"read:\n  {stripped}"
            )
        elif not _DIRECT_WRITE.search(stripped):
            continue

        out.append((i + 1, "\n".join(
            lines[max(0, i - _DIRECT_WINDOW): i + _DIRECT_WINDOW + 1]
        )))
    return out


@pytest.mark.parametrize("path", [
    "app/tasks/kalshi.py",
    "app/tasks/kalshi_ws.py",
    "app/tasks/polymarket.py",
    "app/tasks/polymarket_ws.py",
    "app/tasks/datagolf.py",
    "app/tasks/futures.py",
    "app/tasks/backfill_winners.py",
    "app/routes/admin_data_quality.py",
])
def test_every_settlement_writer_stamps_settled_at(path):
    """The column needs EVERY writer, and there are nine across four files
    written by different hands at different times in three SQL dialects.

    A convention ("remember to also set settled_at") is exactly the shape that
    goes short: a tenth writer lands, nobody notices, and the column develops a
    hole that reads as "these markets never settled" — the fabricated-absence
    failure gotcha #53 names.
    """
    import pathlib

    text = pathlib.Path(path).read_text()
    writes = _resolved_writes(text)
    assert writes, (
        f"{path} is listed as a settlement writer and the scan found none in "
        f"it — the scan has drifted from the code, which is the failure mode "
        f"that makes a green source guard meaningless"
    )
    lines = text.splitlines()
    for line_no, statement in writes:
        # The exemption marker can sit further from the write than the stamp
        # would (``pg_insert(FuturesMarket)`` opens ~13 lines above its
        # ``status=``), so it gets its own, wider look-back.
        exempt_window = "\n".join(lines[max(0, line_no - 25): line_no])
        if any(m in exempt_window for m in _STAMP_EXEMPT.get(path, [])):
            continue
        assert "settled_at" in statement, (
            f"{path}:{line_no} settles a market without stamping settled_at. "
            f"Use app.utils.market_settlement (settled_values / "
            f"settled_at_sql), or add the site to _STAMP_EXEMPT with a reason."
        )


def test_the_kalshi_poll_upsert_couples_the_stamp_to_the_status():
    """The one writer the line scan structurally cannot see.

    The Kalshi poll computes ``market_status`` into a local and hands it to two
    upsert dicts, so neither dict line carries the value ``'resolved'`` at all.
    It is also the writer that matters most for this column: it rewrites
    ``status`` on EVERY poll and can flip a market back to ``'open'`` (the
    #2199 revert loop), so a stamp written anywhere but inside these two dicts
    would survive a reopen and count an open market as one that had left the
    open population.
    """
    src = inspect.getsource(
        __import__("app.tasks.kalshi", fromlist=["x"])
    )
    # Both dicts — the insert values and the on-conflict SET — write the status
    # from the local, and both must write the stamp in the same dict.
    dict_writes = [
        i for i, line in enumerate(src.splitlines())
        if '"status": market_status,' in line
    ]
    assert len(dict_writes) == 2, (
        "the Kalshi poll's insert/update pair has changed shape; re-derive "
        "which dicts write the status before trusting this guard"
    )
    lines = src.splitlines()
    for i in dict_writes:
        window = "\n".join(lines[i: i + 12])
        assert '"settled_at"' in window, (
            f"kalshi poll dict at offset {i} writes status without settled_at"
        )
        assert "market_status ==" in window, (
            "the stamp must be conditioned on the same local the status is, or "
            "a reopen leaves a settled_at behind"
        )


def test_reopening_a_market_clears_the_stamp():
    """Two passes un-resolve DataGolf markets that were resolved by mistake.
    A stamp left behind would count an open market as one that left the open
    population."""
    import pathlib

    dg = inspect.getsource(
        __import__("app.tasks.datagolf", fromlist=["x"])._poll_datagolf_markets
    )
    assert '.values(status="open", settled_at=None)' in dg

    bw = pathlib.Path("app/tasks/backfill_winners.py").read_text()
    assert "SET status = 'open', settled_at = NULL" in bw


def test_the_migration_backfills_nothing():
    """NULL means "we did not observe it settle", and that is the honest value
    for every market resolved before the column existed. Stamping them with the
    release clock would assert that hundreds of thousands of markets settled
    the moment the migration ran — a fabricated timestamp in the one column
    added to stop a fabricated answer."""
    import pathlib

    src = pathlib.Path("alembic/versions/link_loss_receipts.py").read_text()
    upgrade = src[src.index("def upgrade"):src.index("def downgrade")]
    assert "UPDATE" not in upgrade.upper().replace("UPDATED", "")
    assert "execute(" not in upgrade


# =============================================================================
# Part 6 — the merge rail hands back what it moved
# =============================================================================


class _RepointSession:
    """Answers the pre-read with two markets and every UPDATE with a rowcount."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt, params=None):
        text = str(stmt)
        self.statements.append(text)

        class _Row:
            def __init__(self, i):
                self.id = i
                self.source = "kalshi"
                self.external_id = f"KX-{i}"
                self.name = f"market {i}"

        class _R:
            rowcount = 2

            def all(self_inner):
                return [_Row(1), _Row(2)]

        return _R()


def test_the_repoint_reads_the_markets_before_it_moves_them():
    """After the UPDATE the previous event id is gone from the row. Reading
    afterwards would produce receipts that cannot say where anything came
    from, which is the same as no receipt."""
    session = _RepointSession()
    out = asyncio.run(
        ecr.repoint_event_children(session, keep_id=91, orphan_id=42)
    )
    assert [m["id"] for m in out["markets"]] == [1, 2]

    select_at = next(
        i for i, s in enumerate(session.statements)
        if s.startswith("SELECT id, source")
    )
    update_at = next(
        i for i, s in enumerate(session.statements)
        if "UPDATE futures_markets" in s
    )
    assert select_at < update_at


def test_the_merge_rails_receipt_after_their_commit():
    from app.tasks import reconcile_unanchored_events as rue
    from app.tasks import sports

    for src in (
        inspect.getsource(sports._merge_duplicate_events_impl),
        inspect.getsource(rue.run_reconcile_unanchored),
    ):
        call = src.index("record_twin_merge_receipts(")
        before = src[:call]
        assert "commit()" in before, (
            "the merge receipts its moves before committing them, so every "
            "one will be re-read as un-durable and downgraded"
        )
        # …and where the repoint is visible in the same function, the commit
        # sits between the two rather than being some earlier unrelated one.
        if "repoint_event_children(" in before:
            assert (
                before.rindex("commit()")
                > before.rindex("repoint_event_children(")
            )
