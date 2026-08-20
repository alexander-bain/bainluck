"""#1933 bullet 2 — the BACKWARD half: converging 198 historical verdicts.

The forward path is proven in ``test_gold_label_store_convergence.py``. This
proves the repair that moves what is already there, and it guards the four ways
a backfill of this shape goes wrong:

1. it runs twice and doubles the corpus;
2. it stamps every converged row with today's date, which silently moves months
   of history inside every trailing window — including the one the fail-closed
   flip criterion is measured over;
3. it files pre-gate rows as ``unbound`` rather than ``unrecorded``, putting
   permanently-unfixable rows in front of a criterion that needs unbound to
   reach zero;
4. it hits a deleted market, the FK aborts the transaction, and the failure is
   attributed to anything but the orphan.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.models import RankingJudgment
from app.tasks.converge_label_stores import CONVERGEABLE_DECISIONS, repair
from app.utils.gold_label_store import ORIGIN_KEY

JUNE = datetime(2026, 6, 11, 18, 30, tzinfo=timezone.utc)
AUGUST = datetime(2026, 8, 4, 9, 15, tzinfo=timezone.utc)


def _decision(id, decision, item_id="109081", created_at=JUNE, item_type="futures"):
    return SimpleNamespace(
        id=id,
        item_type=item_type,
        item_id=item_id,
        item_name="Michigan Senate winner?",
        category="politics",
        archetype="civic",
        family_key="senate:mi:2026",
        decision=decision,
        features={"generation": "g1", "probability": 0.565},
        created_at=created_at,
    )


class _Session:
    """Ordered answers for: converged-ids → candidates → live markets → count."""

    def __init__(self, *, converged_ids, candidates, live_market_ids):
        self._results = [
            SimpleNamespace(all=lambda: [(str(i),) for i in converged_ids]),
            SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: list(candidates))
            ),
            SimpleNamespace(all=lambda: [(i,) for i in live_market_ids]),
            SimpleNamespace(scalar_one=lambda: 88 + len(candidates)),
        ]
        self.added: list = []
        self.commits = 0

    async def execute(self, statement):
        return self._results.pop(0)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1


def _session(candidates, *, converged_ids=(), live=(109081,)):
    return _Session(
        converged_ids=converged_ids, candidates=candidates, live_market_ids=live
    )


async def test_a_dry_run_writes_nothing_and_returns_its_plan():
    """Dry-run is the default on this rail, and it has to be a real one."""
    session = _session([_decision(1, "accepted_promote")])
    census = await repair(session, apply=False)

    assert census["applied"] is False
    assert session.added == []
    assert session.commits == 0
    assert census["writable"] == 1
    assert census["plan"][0]["label"] == "love"
    assert census["plan"][0]["mapping"] == "affirmed"


async def test_an_apply_converges_each_verdict_to_its_label():
    session = _session(
        [
            _decision(1, "accepted_promote"),
            _decision(2, "accepted_downrank"),
            _decision(3, "rejected_promote"),
            _decision(4, "rejected_downrank"),
        ]
    )
    census = await repair(session, apply=True)

    assert census["written"] == 4
    assert session.commits == 1
    assert [r.label for r in session.added] == ["love", "bad", "fine", "fine"]
    assert census["by_label"] == {"love": 1, "bad": 1, "fine": 2}
    assert census["by_mapping"] == {"affirmed": 2, "negated": 2}


async def test_it_will_not_convert_a_decision_twice():
    """Idempotency, and the key is the one the FORWARD path stamps too.

    Without this, re-running the repair after the deploy would double every
    verdict recorded in between — in a corpus of a few hundred rows, that is not
    a nuisance, it is a different dataset.
    """
    session = _session(
        [_decision(1, "accepted_promote"), _decision(2, "accepted_downrank")],
        converged_ids=(1,),
    )
    census = await repair(session, apply=True)

    assert census["already_converged"] == 1
    assert census["written"] == 1
    assert session.added[0].label_metadata[ORIGIN_KEY]["source_decision_id"] == 2


async def test_a_converged_row_keeps_the_date_the_verdict_was_given():
    """Not today's. See the module docstring, failure 2."""
    session = _session([_decision(1, "accepted_downrank", created_at=JUNE)])
    await repair(session, apply=True)

    row = session.added[0]
    assert row.created_at == JUNE
    assert row.date == JUNE.date()


async def test_converged_rows_are_unrecorded_by_the_gate_not_unbound():
    """A June verdict predates the gate; nothing was ever asked of it.

    ``/coverage`` counts a row with no ``drift_gate`` key as ``unrecorded``, and
    that is the honest bucket. Filing 198 of these as ``unbound`` would park
    permanently-unfixable rows in front of the flip criterion's zero-leg.
    """
    session = _session([_decision(1, "accepted_promote")])
    await repair(session, apply=True)

    metadata = session.added[0].label_metadata
    assert "drift_gate" not in metadata
    assert metadata[ORIGIN_KEY]["reconstructed"] is True
    assert (
        metadata["card_snapshot"]["card_fields_source"]
        == "reconstructed_from_decision_row"
    ), "a rebuilt card must not claim it was server-verified"


async def test_a_verdict_whose_market_is_gone_is_skipped_and_counted():
    """`market_id` is a real FK — an orphan would abort the whole transaction.

    Counted by name, because "converged 1 of 2" must not be able to read as
    "converged them all" (ruling 086).
    """
    session = _session(
        [
            _decision(1, "accepted_promote", item_id="109081"),
            _decision(2, "accepted_promote", item_id="999999"),
        ],
        live=(109081,),
    )
    census = await repair(session, apply=True)

    assert census["orphaned_market_gone"] == 1
    assert census["orphaned_decision_ids"] == [2]
    assert census["written"] == 1
    assert [r.market_id for r in session.added] == [109081]


async def test_only_gradeable_verdicts_are_in_scope():
    """The population is a decision, and every exclusion has a reason.

    `skipped` is the absence of an opinion; the proposals are the machine's; the
    email rows are about a newsletter, not a feed card.
    """
    assert set(CONVERGEABLE_DECISIONS) == {
        "accepted_promote",
        "accepted_downrank",
        "rejected_promote",
        "rejected_downrank",
    }
    for excluded in ("skipped", "llm_proposed_promote", "needs_data_fix", "ignored"):
        assert excluded not in CONVERGEABLE_DECISIONS


async def test_a_non_numeric_item_id_is_excluded_and_reported():
    """The `email` rows carry a non-market item_id and would crash `int()`."""
    session = _session(
        [
            _decision(1, "accepted_promote"),
            _decision(2, "accepted_promote", item_id="polymarket-email-2026-08-04"),
        ]
    )
    census = await repair(session, apply=False)

    assert census["non_numeric_item_id"] == 1
    assert census["writable"] == 1


async def test_every_written_row_is_a_ranking_judgment_in_the_gold_store():
    """The whole point: one table, and this repair writes into it."""
    session = _session([_decision(1, "accepted_promote")])
    await repair(session, apply=True)
    assert all(isinstance(r, RankingJudgment) for r in session.added)
    assert session.added[0].surface == "label_pass"
    assert session.added[0].reviewer == "alex"


async def test_the_limit_bounds_the_write_but_not_the_census():
    """A bounded run still has to report the size of what it did not do."""
    session = _session(
        [_decision(i, "accepted_promote") for i in range(1, 6)]
    )
    census = await repair(session, apply=False, limit=2)
    assert census["writable"] == 2
    assert census["source_decisions_total"] == 5
