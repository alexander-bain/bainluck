"""#2094 — routing the already-tagged negatives into the defect clusters.

UX-P117 wired ``defect_route()`` into both write paths, forward-only. This proves
the backward half, and it guards the five ways a backfill of this shape goes
wrong:

1. it overwrites a ``fix_type`` a human chose in the ReviewTab select with one
   inferred from a chip tap — losing the only considered answer in the corpus;
2. it writes ``label_metadata`` by ORM attribute assignment, so the JSONB change
   is invisible to the session and the commit writes nothing while the census
   reports success (gotcha #4, and #683's shape);
3. it rewrites historical tag spellings instead of canonicalising on read, so a
   corpus is mutated to fit a table that could have folded it;
4. it sets ``create_issue_candidate`` and drops 71 auto-candidates into triage;
5. it reports "the cluster list is no longer empty" without knowing how many
   clusters the endpoint will actually return.
"""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.sql.dml import Update

from app.models.models import RankingJudgment
from app.tasks.backfill_defect_routes import proposed_metadata, repair


def _judgment(id, label="bad", tags=("stale",), metadata=None, market_id=None):
    return SimpleNamespace(
        id=id,
        label=label,
        reason_tags=list(tags),
        label_metadata=metadata,
        item_type="futures",
        market_id=market_id if market_id is not None else 900 + id,
        event_id=None,
    )


class _Session:
    """Answers the candidate select, then records the Core updates it is given.

    Recording the STATEMENTS rather than only a count is what makes guard 2
    testable: an ORM attribute assignment issues no statement at all, so a test
    that only checks a counter passes against the defect it exists to catch.
    """

    def __init__(self, rows, *, verified=None):
        self.rows = list(rows)
        self._verified = list(rows if verified is None else verified)
        self.updates: list = []
        self.statements: list = []
        self.commits = 0
        self._calls = 0

    async def execute(self, statement):
        self._calls += 1
        self.statements.append(statement)
        if isinstance(statement, Update):
            self.updates.append(statement)
            return SimpleNamespace(rowcount=1)
        rows = self.rows if self._calls == 1 else self._verified
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: list(rows))
        )

    async def commit(self):
        self.commits += 1

    def written_values(self):
        return [dict(u.compile().params) for u in self.updates]


async def test_a_dry_run_writes_nothing_and_returns_its_plan():
    session = _Session([_judgment(1)])
    census = await repair(session, apply=False)

    assert census["applied"] is False
    assert session.updates == []
    assert session.commits == 0
    assert census["writable"] == 1
    assert census["plan"][0]["fix_type"] == "staleness"


async def test_stale_is_the_corpus_headline_and_it_routes_to_staleness():
    """40% of the corpus is `stale`; it is the reason the rail was built."""
    session = _Session([_judgment(i) for i in range(1, 6)])
    census = await repair(session, apply=True)

    assert census["written"] == 5
    assert census["by_fix_type"] == {"staleness": 5}
    assert session.commits == 1


async def test_an_existing_human_fix_type_is_never_overwritten():
    """Guard 1. A ReviewTab select is a considered answer; a chip tap is not.

    The row is tagged `stale`, which WOULD route to `staleness` — so if
    precedence were not honoured the inferred value would silently replace the
    human's `bad_image`. Nothing about the row makes it un-routable; only the
    precedence rule protects it.
    """
    human = {"fixable_interest": {"fix_type": "bad_image", "derived_from": "human"}}
    session = _Session([_judgment(1, metadata=human)])
    census = await repair(session, apply=True)

    assert census["already_routed_left_alone"] == 1
    assert census["writable"] == 0
    assert session.updates == []


async def test_the_write_is_a_core_update_and_does_not_mutate_the_orm_row():
    """Guard 2 — gotcha #4, in both directions.

    A Core `update()` statement must be ISSUED (an ORM assignment issues none),
    and the live row's `label_metadata` must be UNTOUCHED (an in-place mutation
    of the JSONB dict is the silent-failure mode this codebase documents).
    """
    row = _judgment(1, metadata={"card_snapshot": {"group_id": "g1"}})
    session = _Session([row])
    await repair(session, apply=True)

    assert len(session.updates) == 1
    assert isinstance(session.updates[0], Update)
    values = session.written_values()[0]
    written = next(v for k, v in values.items() if isinstance(v, dict))
    assert written["fixable_interest"]["fix_type"] == "staleness"
    # the pre-existing key survives, and the ORM row is unchanged
    assert written["card_snapshot"] == {"group_id": "g1"}
    assert row.label_metadata == {"card_snapshot": {"group_id": "g1"}}


async def test_historical_spellings_route_without_being_rewritten():
    """Guard 3. `boring` predates the alias; it must route and stay `boring`."""
    row = _judgment(1, tags=("boring",))
    session = _Session([row])
    census = await repair(session, apply=True)

    assert census["by_fix_type"] == {"ranking_rule": 1}
    assert row.reason_tags == ["boring"], "no stored tag may be rewritten"
    values = session.written_values()[0]
    written = next(v for k, v in values.items() if isinstance(v, dict))
    assert written["fixable_interest"]["reason_tags_routed"] == ["low_stakes"]


async def test_it_never_sets_create_issue_candidate():
    """Guard 4 — 71 auto-candidates at once is the cried-wolf failure."""
    session = _Session([_judgment(i) for i in range(1, 4)])
    await repair(session, apply=True)

    for values in session.written_values():
        written = next(v for k, v in values.items() if isinstance(v, dict))
        assert "create_issue_candidate" not in written["fixable_interest"]


async def test_a_backfilled_route_is_marked_as_a_reconstruction():
    session = _Session([_judgment(1)])
    await repair(session, apply=True)

    written = next(
        v for k, v in session.written_values()[0].items() if isinstance(v, dict)
    )
    assert written["fixable_interest"]["reconstructed"] is True
    assert written["fixable_interest"]["derived_from"] == "reason_tags"


async def test_a_positive_label_files_no_defect_even_if_the_query_returns_it():
    """`love` and `fine` carry the same 24-tag row; a tag on them is praise.

    Both other gates are held OPEN — the tag is `stale`, which routes, and the
    row has no existing `fixable_interest` — so only the LABEL gate can produce
    this result. (UX-P117's mutation M1: a test that pairs a positive label with
    a non-routing tag asserts the tag gate under the label gate's name.)

    The gate is defended TWICE — in the SQL predicate and again in
    `defect_route` — and this asserts the half that EXECUTES, by handing the
    repair rows the query was supposed to have excluded. A fake session does not
    run a WHERE clause, so a test that asserted the filter here would assert
    nothing at all; the SQL half is pinned separately below.
    """
    session = _Session([_judgment(1, label="love"), _judgment(2, label="fine")])
    census = await repair(session, apply=True)

    assert census["writable"] == 0
    assert session.updates == []


async def test_the_candidate_query_asks_only_for_negative_labels():
    """The other half of the same gate — pinned on the compiled statement.

    Defence in depth is only defence if both layers are real: this one keeps the
    scan off the whole corpus, and nothing that executes in-process can observe
    it.
    """
    session = _Session([_judgment(1)])
    await repair(session, apply=False)

    where = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "ranking_judgments.label IN ('bad', 'kill')" in where


async def test_a_tagged_negative_that_names_no_defect_is_counted_not_written():
    """`movement` is the positive vocabulary — a known non-route, not a gap."""
    session = _Session([_judgment(1, tags=("movement",))])
    census = await repair(session, apply=True)

    assert census["unroutable_no_defect_tag"] == 1
    assert census["writable"] == 0


async def test_an_untagged_negative_is_silence_not_a_shortfall():
    session = _Session([_judgment(1, tags=())])
    census = await repair(session, apply=False)

    assert census["untagged_no_complaint"] == 1
    assert census["tagged_negatives"] == 0
    assert census["unroutable_no_defect_tag"] == 0


async def test_the_projection_counts_clusters_not_rows():
    """Guard 5, and it is the claim the directive actually makes.

    Three `stale` complaints about three DIFFERENT markets are three clusters of
    one — `_cluster_identity` falls back to `item_type:market_id` when the card
    snapshot carries no group key. Two complaints sharing a `group_id` collapse.
    Without this the census could report "71 routed" and imply a cluster list
    that never materialises.
    """
    shared = {"card_snapshot": {"group_id": "shared-family"}}
    session = _Session(
        [
            _judgment(1, market_id=11),
            _judgment(2, market_id=22),
            _judgment(3, metadata=shared, market_id=33),
            _judgment(4, metadata=dict(shared), market_id=44),
        ]
    )
    census = await repair(session, apply=False)

    assert census["writable"] == 4
    assert census["projected_clusters"] == 3
    assert census["largest_cluster"] == 2


async def test_the_after_census_is_read_back_not_counted():
    """A counter proves statements were issued; a re-read proves they landed."""
    routed = _judgment(1)
    verified = _judgment(
        1, metadata={"fixable_interest": {"fix_type": "staleness"}}
    )
    session = _Session([routed], verified=[verified])
    census = await repair(session, apply=True)

    assert census["written"] == 1
    assert census["verified_carrying_fix_type"] == 1


async def test_proposed_metadata_copies_rather_than_mutates():
    existing = {"card_snapshot": {"group_id": "g"}}
    out = proposed_metadata(existing, {"fix_type": "staleness"})

    assert out is not existing
    assert "fixable_interest" not in existing
    assert out["fixable_interest"]["fix_type"] == "staleness"


async def test_the_repair_is_registered_on_the_rail():
    """A repair nobody can invoke is a script with extra steps."""
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["label-defect-routes"] == (
        "app.tasks.backfill_defect_routes",
        "repair",
    )


async def test_the_registry_and_the_module_docstring_agree():
    """The file's own standing rule — a drifted list reads as a missing rail."""
    from app.routes import admin_repairs

    assert "label-defect-routes" in (admin_repairs.__doc__ or "")


def test_the_model_column_is_jsonb_so_core_update_is_required():
    """Pins WHY the write is a Core update — if this column ever stops being
    JSONB the reasoning in the module docstring needs re-deriving, not deleting.
    """
    assert type(RankingJudgment.__table__.c.label_metadata.type).__name__ == "JSONB"
