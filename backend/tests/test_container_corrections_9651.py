"""A corrected hub stays corrected — the parts no database is needed for. #9651.

The database half (the lock, the non-resurrection race, the one-snapshot read,
re-admission) is graded against real Postgres in
`tests/integration/test_container_assembly_real_postgres.py`. What is here pins
the vocabulary, the DDL's agreement with it, the read classification, the
migration's place in the chain, and the one path that must not change at all:
a pass on a database where the correction migration has not run.
"""

import re
from pathlib import Path

import pytest

from app.utils import container_corrections as cc
from app.utils.container_graph import (
    CORRECTION_ACTIONS,
    CORRECTION_SCOPES,
    EDGE_NODE_TYPES,
    PUBLICATION_STATES,
    ContainerVocabularyError,
    validate_correction,
    validate_publication_state,
)

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "container_corrections.py"


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class TestTheVocabulary:
    def test_unpublished_is_a_state_and_the_default_in_the_ddl(self):
        assert "unpublished" in PUBLICATION_STATES
        assert "DEFAULT 'unpublished'" in cc.ADD_CONTAINER_COLUMNS_SQL

    @pytest.mark.parametrize(
        "scope,action",
        [
            ("member", "withdraw"),
            ("member", "readmit"),
            ("publication", "publish"),
            ("publication", "withdraw"),
        ],
    )
    def test_the_legal_pairs(self, scope, action):
        assert validate_correction(scope, action) == (scope, action)

    @pytest.mark.parametrize(
        "scope,action",
        [
            ("member", "publish"),
            ("publication", "readmit"),
            ("member", "admit"),
            ("member", "add"),
            ("edition", "withdraw"),
        ],
    )
    def test_every_other_pair_is_refused(self, scope, action):
        with pytest.raises(ContainerVocabularyError):
            validate_correction(scope, action)

    def test_no_member_action_can_add_a_member(self):
        """A correction subtracts; only evidence adds."""
        assert CORRECTION_ACTIONS["member"] == frozenset({"withdraw", "readmit"})

    def test_an_unknown_publication_state_is_refused(self):
        with pytest.raises(ContainerVocabularyError):
            validate_publication_state("live")


class TestTheDdlAgreesWithTheVocabulary:
    """The CHECKs are a second copy of the sets; a drift is a silent refusal."""

    def test_every_publication_state_is_in_the_check(self):
        for state in PUBLICATION_STATES:
            assert f"'{state}'" in cc._PUBLICATION_CHECK
        assert len(re.findall(r"'(\w+)'", cc._PUBLICATION_CHECK)) == len(
            PUBLICATION_STATES
        )

    def test_every_scope_and_action_is_in_the_ledger_check(self):
        for scope in CORRECTION_SCOPES:
            assert f"scope = '{scope}'" in cc.CREATE_LEDGER_SQL
            for action in CORRECTION_ACTIONS[scope]:
                assert f"'{action}'" in cc.CREATE_LEDGER_SQL

    def test_every_node_type_may_be_withdrawn(self):
        for node_type in EDGE_NODE_TYPES:
            assert f"'{node_type}'" in cc.CREATE_LEDGER_SQL

    def test_the_downgrade_drops_exactly_what_the_upgrade_adds(self):
        down = " ".join(cc.DOWNGRADE_STATEMENTS)
        assert f"DROP TABLE IF EXISTS {cc.LEDGER_TABLE}" in down
        assert f"DROP COLUMN IF EXISTS {cc.REVISION_COLUMN}" in down
        assert f"DROP COLUMN IF EXISTS {cc.PUBLICATION_COLUMN}" in down
        assert "events" not in down and "event_edges" not in down

    def test_the_upgrade_is_additive_and_rerunnable(self):
        up = " ".join(cc.UPGRADE_STATEMENTS)
        assert "DROP" not in up.upper()
        assert "CONCURRENTLY" not in up.upper()  # gotcha #31
        assert up.count("IF NOT EXISTS") == 4


# ---------------------------------------------------------------------------
# The read classification
# ---------------------------------------------------------------------------


class TestReadState:
    @pytest.mark.parametrize(
        "exists,state,count,expected",
        [
            (False, None, 0, "unavailable"),
            (False, "published", 5, "unavailable"),
            (True, None, 5, "unpublished"),  # un-migrated database
            (True, "unpublished", 5, "unpublished"),
            (True, "withdrawn", 5, "withdrawn"),
            (True, "published", 0, "empty"),
            (True, "published", 3, "published"),
            (True, "PUBLISHED", 3, "unpublished"),  # unknown ⇒ closed
            (True, "live", 3, "unpublished"),
        ],
    )
    def test_the_table(self, exists, state, count, expected):
        assert cc.read_state(exists, state, count) == expected
        assert expected in cc.READ_STATES


# ---------------------------------------------------------------------------
# The migration
# ---------------------------------------------------------------------------


class TestTheMigration:
    def test_its_id_fits_and_it_follows_the_head_it_was_written_on(self):
        text = MIGRATION.read_text()
        revision = re.search(r'^revision = "([^"]+)"', text, re.M).group(1)
        down = re.search(r'^down_revision = "([^"]+)"', text, re.M).group(1)
        assert len(revision) <= 32  # gotcha #1
        assert down == "wps_rev_trigger"

    def test_it_is_the_only_head(self):
        revisions, parents = set(), set()
        for path in (BACKEND / "alembic" / "versions").glob("*.py"):
            text = path.read_text()
            rev = re.search(
                r"^revision\s*(?::\s*str)?\s*=\s*['\"]([^'\"]+)", text, re.M
            )
            down = re.search(r"^down_revision[^=]*=\s*(.+)$", text, re.M)
            if rev:
                revisions.add(rev.group(1))
                parents.update(
                    re.findall(r"['\"]([^'\"]+)['\"]", down.group(1) if down else "")
                )
        # ONE head, not THIS head: pinning the name made the first successor
        # migration (#4571's `score_observation_stamp`) read as a branchpoint.
        # The deploy-breaking property is a second head, so that is asserted;
        # that this revision is in the chain is asserted beside it.
        heads = revisions - parents
        assert len(heads) == 1, f"expected a single Alembic head, got {heads}"
        assert "container_corrections" in revisions
        assert heads == {"container_corrections"} or "container_corrections" in parents

    def test_it_runs_the_helpers_statements_not_a_copy(self):
        text = MIGRATION.read_text()
        assert "UPGRADE_STATEMENTS" in text and "DOWNGRADE_STATEMENTS" in text
        assert "CREATE TABLE" not in text


# ---------------------------------------------------------------------------
# The un-migrated pass must not change
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._rows[0][0] if self._rows else None


class _Session:
    """Answers the probe with the given flags and existence with every id.

    ``withdrawn`` is what the ledger read returns. Everything else is recorded
    and answered empty, so the test sees every statement the pass issued.
    """

    def __init__(self, ledger, columns, live_ids, withdrawn=()):
        self.flags = (ledger, columns)
        self.live_ids = live_ids
        self.withdrawn = list(withdrawn)
        self.statements = []

    async def execute(self, sql, params=None):
        sql_text = str(sql)
        self.statements.append(sql_text)
        if "to_regclass('public.container_corrections')" in sql_text:
            return _Result([self.flags])
        if sql_text.startswith("SELECT id FROM futures_markets"):
            return _Result([(i,) for i in self.live_ids])
        if "FROM container_corrections" in sql_text:
            return _Result([("market", i, "withdraw") for i in self.withdrawn])
        if "RETURNING id, membership_revision" in sql_text:
            return _Result([(params["cid"], 1)])
        return _Result([])


def _candidate(market_id):
    from app.tasks.container_assembly import Candidate
    from app.utils.container_class import MemberEvidence

    return Candidate(
        child_type="market",
        child_id=market_id,
        source="register",
        evidence=MemberEvidence(node_type="market", name="Chiefs at Bills"),
        external_id=f"KX-{market_id}",
        market_source="kalshi",
    )


class _Container:
    id = 7
    slug = "nfl-2026-week-4"


@pytest.mark.asyncio
async def test_an_unmigrated_pass_issues_no_correction_statement():
    from app.tasks.container_assembly import assemble_container

    session = _Session(ledger=False, columns=False, live_ids=[11, 12])
    report = await assemble_container(
        session, _Container(), [_candidate(11), _candidate(12)]
    )

    assert report.corrections == "absent"
    assert report.revision is None
    assert report.by_class  # both members classified and edged
    issued = " ".join(session.statements[1:])  # everything after the probe
    assert "container_corrections" not in issued
    assert "FOR UPDATE" not in issued
    assert "membership_revision" not in issued


@pytest.mark.asyncio
async def test_a_migrated_pass_never_edges_a_withdrawn_member():
    from app.tasks.container_assembly import assemble_container

    session = _Session(ledger=True, columns=True, live_ids=[11, 12], withdrawn=[12])
    report = await assemble_container(
        session, _Container(), [_candidate(11), _candidate(12)]
    )

    assert report.corrections == "honoured"
    assert [w["child_id"] for w in report.withdrawn] == [12]
    assert report.rejected[cc.WITHHELD_WITHDRAWN] == 1
    assert sum(report.by_class.values()) == 1
    assert report.added == 1 and report.revision == 1
    # The lock is taken BEFORE the ledger is read — the order is the guarantee.
    lock = next(i for i, s in enumerate(session.statements) if "FOR UPDATE" in s)
    ledger = next(
        i for i, s in enumerate(session.statements) if "FROM container_corrections" in s
    )
    assert lock < ledger


@pytest.mark.asyncio
async def test_a_probe_with_no_answer_reads_as_absent():
    class Silent:
        async def execute(self, sql, params=None):
            return _Result([])

    schema = await cc.correction_schema_present(Silent())
    assert not schema.ledger and not schema.columns


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason,actor", [("", "ops"), ("   ", "ops"), ("why", ""), (None, "ops")]
)
async def test_a_correction_without_a_reason_and_an_actor_is_refused_before_any_write(
    reason, actor
):
    session = _Session(ledger=True, columns=True, live_ids=[])
    with pytest.raises(cc.CorrectionRefused):
        await cc.withdraw_member(
            session,
            container_id=7,
            child_type="market",
            child_id=12,
            reason=reason,
            actor=actor,
        )
    assert session.statements == []


@pytest.mark.asyncio
async def test_a_correction_on_an_unmigrated_database_is_refused_not_dropped():
    session = _Session(ledger=False, columns=False, live_ids=[])
    with pytest.raises(cc.CorrectionSchemaAbsent):
        await cc.withdraw_member(
            session,
            container_id=7,
            child_type="market",
            child_id=12,
            reason="wrong week",
            actor="ops",
        )
