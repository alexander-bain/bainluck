"""The container assembles itself, and says so honestly. #2927 Phase 2.

WHAT THIS FILE IS DEFENDING. Three thousand lines of assembly machinery landed
with no caller: nothing bootstrapped a tree, nothing claimed an id, nothing ran
on a schedule. Wiring it up introduces exactly two ways to lie —

1. a pass that runs before Phase 1's migration is applied and either raises
   hourly or, worse, returns something a counter reads as success; and
2. a pass that writes zero edges and reports `complete`, which is gotcha #53's
   "it returned" mistaken for "it worked".

Both are pinned below. The database half (real edges, real anchors, real
`to_regclass`) is graded in
`tests/integration/test_container_assembly_real_postgres.py`; what is here runs
the real pass against a session double, so the DECISIONS under test are the
ones the code makes.
"""

from datetime import datetime, timezone

import pytest

from app.tasks.container_assembly import (
    ANCHOR_SCOPE_EDITION,
    CONTAINER_TABLES,
    TENNIS_DRAWS,
    anchor_scope,
    containers_tables_present,
    plan_container_tree,
    run_declared_assembly,
)
from app.utils.container_tournaments import (
    DECLARED_TOURNAMENTS,
    US_OPEN_2026,
    DeclaredAnchor,
    declaration_for,
)


# ---------------------------------------------------------------------------
# The declarations
# ---------------------------------------------------------------------------


def test_the_declaration_names_ids_and_never_members():
    """The ship is "nobody writes a list of MEMBERS ever again".

    A declaration may name the tournament and the ids that address it at each
    venue. The moment one carries a market id, the curated hub is back.
    """
    for declared in DECLARED_TOURNAMENTS:
        for anchor in declared.anchors:
            assert isinstance(anchor.provider_id, str)
            assert not anchor.provider_id.isdigit(), (
                f"{anchor.provider_id!r} looks like one of OUR ids; a declaration "
                "names the venue's grouping key, never a member"
            )
            assert anchor.evidence, "an anchor with no provenance is one nobody dares delete"


def test_every_declared_draw_exists_in_the_tree_that_gets_built():
    """An anchor for a draw the bootstrap never creates would be silently dropped."""
    plan = plan_container_tree(
        US_OPEN_2026.tournament,
        US_OPEN_2026.season,
        US_OPEN_2026.display_name,
        window_start=US_OPEN_2026.window_start,
        window_end=US_OPEN_2026.window_end,
    )
    slugs = {p.slug for p in plan}
    for anchor in US_OPEN_2026.anchors:
        assert US_OPEN_2026.slug_for(anchor.draw) in slugs


def test_the_five_tennis_draws_are_all_anchored():
    """Including the three doubles draws, which have been empty since UX-P139."""
    anchored = {a.draw for a in US_OPEN_2026.anchors}
    for draw_slug, _name in TENNIS_DRAWS:
        assert draw_slug in anchored, f"{draw_slug} has no venue id and can never fill"


def test_the_window_covers_the_fan_week_mixed_draw_and_the_mens_final():
    """Both ends are measured, and both ends are load-bearing.

    08-24 is the earliest US Open market we hold (the mixed draw, played the
    week before the main draw); a window opening on main-draw Sunday refuses
    all 22 of its rows. The right edge is one day past the men's final — loose
    enough to include it, tight enough to keep the 09-18 tour out.
    """
    assert US_OPEN_2026.window_start == datetime(2026, 8, 24, tzinfo=timezone.utc)
    assert US_OPEN_2026.window_end == datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert US_OPEN_2026.window_end < datetime(2026, 9, 17, tzinfo=timezone.utc), (
        "the first of next week's tour is 09-17; a window reaching it re-admits "
        "the tournament this bound exists to exclude"
    )


def test_the_bootstrap_carries_the_window_to_every_draw():
    """A tree bootstrapped without a window refuses every coarse anchor."""
    plan = plan_container_tree(
        "us-open", "2026", "US Open 2026",
        window_start=US_OPEN_2026.window_start,
        window_end=US_OPEN_2026.window_end,
    )
    assert plan and all(p.window_start == US_OPEN_2026.window_start for p in plan)
    assert all(p.window_end == US_OPEN_2026.window_end for p in plan)


def test_declaration_lookup_is_by_root_slug():
    assert declaration_for("us-open-2026") is US_OPEN_2026
    assert declaration_for("wimbledon-2027") is None


# ---------------------------------------------------------------------------
# The declared scope override
# ---------------------------------------------------------------------------


def test_anchor_scope_reads_dicts_strings_and_absence():
    class Row:
        def __init__(self, ctx):
            self.claim_context = ctx

    assert anchor_scope(Row({"scope": ANCHOR_SCOPE_EDITION})) == ANCHOR_SCOPE_EDITION
    assert anchor_scope(Row('{"scope": "edition"}')) == ANCHOR_SCOPE_EDITION
    assert anchor_scope(Row(None)) is None
    assert anchor_scope(Row("not json")) is None
    assert anchor_scope(Row({"scope": 7})) is None
    assert anchor_scope(object()) is None


def test_only_the_honey_deuce_claims_a_whole_series_as_one_edition():
    """The exception must stay an exception; every tour-wide id stays bounded."""
    edition_scoped = [a for a in US_OPEN_2026.anchors if a.scope == ANCHOR_SCOPE_EDITION]
    assert [a.provider_id for a in edition_scoped] == ["KXHONEYDEUCE"]


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class TablesSession:
    """Answers only the `to_regclass` probe, with the flags it was given."""

    def __init__(self, present):
        self.present = present
        self.statements = []

    async def execute(self, sql, params=None):
        self.statements.append(str(sql))
        return FakeResult([tuple(self.present)])


@pytest.mark.asyncio
async def test_tables_present_needs_every_table_not_just_the_first():
    assert await containers_tables_present(TablesSession([True] * len(CONTAINER_TABLES)))
    assert not await containers_tables_present(
        TablesSession([True, True, True, False])
    )
    assert not await containers_tables_present(
        TablesSession([False] * len(CONTAINER_TABLES))
    )


@pytest.mark.asyncio
async def test_the_probe_asks_about_all_four_tables():
    session = TablesSession([True] * len(CONTAINER_TABLES))
    await containers_tables_present(session)
    for table in CONTAINER_TABLES:
        assert f"public.{table}" in session.statements[0]


class DryRunSession:
    """A database that holds NOTHING: every container lookup misses.

    Deliberately the harshest shape for a dry run, because the dry run's whole
    job is to be readable before the tables exist.
    """

    def __init__(self):
        self.statements = []

    async def execute(self, sql, params=None):
        self.statements.append(str(sql))
        return FakeResult([])

    async def commit(self):  # pragma: no cover — a dry run must not reach it
        raise AssertionError("apply=False committed")


@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing_and_still_reports_the_plan():
    session = DryRunSession()

    report = await run_declared_assembly(session, US_OPEN_2026, apply=False)

    assert report["apply"] is False
    assert report["bootstrap"]["created"] == []
    assert report["bootstrap"]["would_create"][0] == "us-open-2026"
    assert len(report["bootstrap"]["would_create"]) == 1 + len(TENNIS_DRAWS)
    assert report["anchors"]["claimed"] == 0
    assert len(report["anchors"]["would_claim"]) == len(US_OPEN_2026.anchors)
    assert report["errors"] == [], "a dry run has nothing to anchor to; that is not an error"
    # Nothing to assemble against, and it says so rather than reporting success.
    assert report["members"] == 0
    assert report["terminal"] == "partial"
    assert report["reason"] == "no_member_found"
    assert "INSERT INTO containers" not in " ".join(session.statements)


@pytest.mark.asyncio
async def test_the_undo_lines_travel_with_every_report():
    """D51: the undo is never reconstructed from memory at the moment it is needed."""
    report = await run_declared_assembly(DryRunSession(), US_OPEN_2026, apply=False)
    assert "DELETE FROM containers" in report["undo"]["containers"]
    assert "DELETE FROM event_edges" in report["undo"]["edges"]


def test_a_declared_anchor_defaults_to_no_scope():
    """The default is the fail-closed one: a series is tour-wide until declared."""
    anchor = DeclaredAnchor(provider="kalshi", provider_id="KXWHATEVER", id_kind="series")
    assert anchor.scope is None


# ---------------------------------------------------------------------------
# The receipt a foreign key refuses (found by real Postgres, guarded here)
# ---------------------------------------------------------------------------


class NoLiveRowsSession:
    """Every existence probe comes back empty; nothing else is ever asked."""

    def __init__(self):
        self.statements = []

    async def execute(self, sql, params=None):
        self.statements.append(str(sql))
        return FakeResult([])


@pytest.mark.asyncio
async def test_a_ghost_market_id_is_reported_and_never_receipted():
    """`market_match_receipts.market_id` has a real FK to `futures_markets`.

    A receipt for an id with no row is refused by the database, and because
    receipts flush as ONE batched statement, that refusal takes the whole pass
    with it — one bad candidate wiping the pass, in defiance of gotcha #42.
    Real Postgres caught it (`Key (market_id)=(999999999) is not present`);
    this is the cheap guard that keeps it caught.
    """
    from app.tasks.container_assembly import Candidate, assemble_container
    from app.utils.container_class import MemberEvidence

    class Container:
        id = 1
        slug = "us-open-2026"

    ghost = Candidate(
        child_type="market",
        child_id=999_999_999,
        source="register",
        evidence=MemberEvidence(node_type="market", name="Ghost vs Nobody"),
        external_id="KXATPMATCH-26SEP02AUGKHA",
        market_source="kalshi",
    )

    report = await assemble_container(NoLiveRowsSession(), Container(), [ghost])

    assert report.edges_written == 0
    assert report.receipts_written == 0
    assert report.rejected["container_child_missing"] == 1
    assert [u["child_id"] for u in report.unresolved] == [999_999_999]
    assert report.unresolved[0]["external_id"] == "KXATPMATCH-26SEP02AUGKHA"


# ---------------------------------------------------------------------------
# The verdict contract (CERT-2011's second required repair)
# ---------------------------------------------------------------------------


def test_the_pass_is_enrolled_so_its_terminal_is_authoritative():
    """Enrolment without a terminal is a no-op; a terminal without enrolment
    is ignored. Both halves, or neither is worth anything — and the empty case
    here is the NORMAL one for as long as the Phase 1 migration is held."""
    from app.utils.task_verdict import ENFORCED_TASKS

    assert "assemble_containers" in ENFORCED_TASKS


@pytest.mark.parametrize(
    "summary,green,why",
    [
        (
            {"terminal": "skipped", "reason": "containers_tables_absent"},
            False,
            "the tables are not there; nothing was produced and nothing may be banked",
        ),
        (
            {"terminal": "partial", "reason": "no_member_found", "members": 0},
            False,
            "the pass ran and found no member — an empty hub is not a healthy run",
        ),
        (
            {"terminal": "failed", "reason": "every_edition_failed"},
            False,
            "every edition raised",
        ),
        (
            {"terminal": "complete", "members": 61, "edges_written": 61},
            True,
            "members were actually edged",
        ),
    ],
)
def test_only_a_pass_that_edged_a_member_reads_green(summary, green, why):
    from app.utils.task_verdict import verdict_for

    verdict = verdict_for("assemble_containers", summary)
    assert verdict.is_green is green, why
    assert verdict.authoritative is True, (
        "an unenrolled task falls back to the legacy unknown, whose blocks_success "
        "is False — which is how an empty producer stays green"
    )
