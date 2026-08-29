"""#2024 — the futures touch-stamps, and the coupling that decides whether they
may be changed.

UX-P106 item 2. `futures_markets.updated_at` and `futures_outcomes.last_updated`
are written `func.now()` UNCONDITIONALLY inside the ON CONFLICT update set of
the routine polls, so every row the poller *sees* gets a fresh timestamp whether
or not anything about it changed. Measured on production 2026-08-19/20 UTC:
**2,005 outcomes stamped fresh inside one minute, not one of which had moved.**
The stamp records that the poller ran.

#2024 offers two fixes and asks for a consumer audit before either is chosen:

    1. stamp on change (a `WHERE` / `IS DISTINCT FROM` on the upsert), or
    2. add an explicit `price_changed_at` and leave the touch-stamps alone.

** THE AUDIT REFUSES OPTION 1, AND THE EVIDENCE IS IN THIS FILE. **

`app/routes/playoffs.py` uses `outcome.last_updated` as a HARD STALENESS GATE on
the playoff grid: an outcome whose stamp predates the cutoff is `continue`d — it
does not render. Under option 1 that stamp stops advancing on any price that is
merely STABLE, so a team parked at 3% for a week would drop out of the grid.
That is not a subtle regression; it is grid blanking, on the surface the Grid
Sentinel exists to protect, caused by a change made three files away.

So this file is not a unit test of behaviour. It is the predicate that #2024's
warning could not be: *"which downstream consumers read these two columns has
not been audited"* is prose, and three separate recovery rails in this repo have
been written by people who cited a prose gotcha and still walked into it
(gotcha #35). A predicate cannot be skim-read.

WHAT IT ASSERTS, in both directions:

  * the WRITE side — the exact set of task files that stamp unconditionally. A
    new unconditional stamper reds this, so it gets considered rather than
    absorbed.
  * the READ side — the exact set of call sites that gate on `last_updated` as
    a freshness/staleness filter. A new gate reds this, because it becomes one
    more thing option 1 would break.

Either list changing is the signal to re-run the audit, not to update the list.

NOT ASSERTED HERE: that the current behaviour is correct. It is the defect
#2024 is open on. This file pins the COUPLING, so that whoever fixes the write
cannot do it without seeing the reads.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


def _src_files(*dirs: str) -> list[str]:
    out: list[str] = []
    for d in dirs:
        for p in sorted((BACKEND / d).rglob("*.py")):
            out.append(str(p.relative_to(BACKEND)))
    return out


# ---------------------------------------------------------------------------
# WRITE side
# ---------------------------------------------------------------------------

#: Task files that stamp a futures touch-column with an unconditional ``now()``
#: inside a routine POLL path. Measured, not guessed — see ``test_write_side``.
#:
#: ``backfill_winners.py`` and ``repair_kalshi_fabricated_loss.py`` are
#: deliberately absent: their ``last_updated = NOW()`` writes accompany a
#: RESOLUTION write (``is_winner``, ``resolution_source``,
#: ``calibration_probability``), so the row genuinely changed and the stamp is
#: honest. #2024 is about the POLLS.
POLL_STAMPERS = {
    "app/tasks/kalshi.py",
    "app/tasks/polymarket.py",
    "app/tasks/futures.py",
}

_STAMP = re.compile(
    r"""["']?(?:last_updated|updated_at|volume_updated_at)["']?\s*[:=]\s*func\.now\(\)"""
)

#: The number of unconditional touch-stamp sites per poll file, MEASURED.
#: A census rather than a boolean, so the tripwire moves when a stamp is added
#: OR removed — "is there at least one" would sit green through half a fix.
POLL_STAMP_COUNTS = {
    "app/tasks/kalshi.py": 5,
    # 7 -> 9 (UX-P157, #2256). The per-condition sub-market upsert began writing
    # `volume_24h`, and its `volume_updated_at` stamp comes with it on both the
    # insert and the conflict-update path — the same pair the PARENT event
    # upsert twenty lines up has always written.
    #
    # THE AUDIT'S CONCLUSION, RE-CHECKED RATHER THAN THE COUNT BUMPED, which is
    # what this census asks for by name:
    #
    #   • The severe consumer is untouched. `routes/playoffs.py` drops an
    #     outcome from the playoff grid on a stale stamp, and it gates on
    #     `FuturesOutcome.last_updated` — a different table and a different
    #     column from `FuturesMarket.volume_updated_at`. Neither of the two new
    #     sites writes `last_updated`.
    #   • `volume_updated_at` had exactly ONE reader in the tree
    #     (`routes/calibration.py`'s zero-volume admin diagnostic) and it
    #     DISPLAYS the value; it never gates on it. Grepped, not assumed.
    #
    #     ⚠️ SUPERSEDED THE NEXT DAY, and the census is why it is written down
    #     rather than discovered later: UX-P158 gave the column a SECOND reader
    #     that DOES gate on it. `routes/tournaments._load_prices` refuses to
    #     read a NULL `volume_24h` as "nobody traded it" unless this stamp says
    #     the venue was asked within the last 24 hours. So the "when the poller
    #     last looked" semantics above are now load-bearing on a user-visible
    #     surface, and a writer that stamped this column WITHOUT having looked
    #     would put a mark on a number nobody measured. Both existing writers
    #     stamp it in the same statement that writes the figure; a future one
    #     must too.
    #   • The new sites carry #2024's own ambiguity — a conflict-update stamps
    #     on every poll whether or not the figure moved — and that is
    #     deliberate consistency with the parent row, whose semantics for this
    #     column are already "when the poller last looked". A sub-market row
    #     that meant something different from its own parent would be a second
    #     reading of one column, which is the disease #2024 is about.
    "app/tasks/polymarket.py": 9,
    "app/tasks/futures.py": 2,
    # #2199: the price refresher. A FOURTH writer, and the census is why it had
    # to declare itself — it exists precisely because the three above cannot
    # reach every market they are assumed to cover.
    "app/tasks/futures_price_refresh.py": 1,
}


#: Fields that mark a write as a PRICE write — the poll path #2024 is about.
_PRICE_FIELDS = (
    "current_probability",
    "current_yes_bid",
    "current_yes_ask",
    "probability_change_24h",
    "volume_24h",
    "current_american_odds",
)

#: Where an update's field block starts. The stamp is classified by the company
#: it keeps INSIDE its own block, not by whatever is nearby in the file.
_BLOCK_START = re.compile(r"set_=\{|\.values\(|update_set(?:\s*:\s*dict)?\s*=\s*\{")


def _poll_stamp_sites(src: str) -> list[int]:
    """Touch-stamp sites on a PRICE write, i.e. #2024's surface.

    `backfill_winners.py` and `repair_kalshi_fabricated_loss.py` stamp
    `last_updated` too, but always alongside `is_winner` / `resolution_source`
    in a block that writes no price — the row genuinely changed, so the stamp is
    honest and they are not this issue's surface.

    The discriminator is deliberately block-scoped. A crude ±400-character
    window got this wrong in both directions on the first draft: it excluded
    `kalshi.py`'s MAIN poll upsert (a conditional `is_winner` is appended a few
    lines below the block) and would have let a resolution write through
    wherever a price happened to be mentioned nearby.
    """
    starts = [m.end() for m in _BLOCK_START.finditer(src)]
    sites: list[int] = []
    for m in _STAMP.finditer(src):
        prior = [s for s in starts if s <= m.start()]
        block = src[prior[-1] : m.end()] if prior else src[max(0, m.start() - 400) : m.end()]
        if "resolution_source" in block and not any(f in block for f in _PRICE_FIELDS):
            continue
        sites.append(src[: m.start()].count("\n") + 1)
    return sites


def test_write_side_is_exactly_the_known_poll_stampers() -> None:
    """Every file that stamps a futures touch-column on a POLL path.

    A file arriving here is a file #2024's fix has to cover. A file leaving it
    means the fix landed — at which point the audit's conclusion below has to be
    re-checked, not deleted.
    """
    found = {}
    for f in _src_files("app/tasks"):
        src = _read(f)
        # Scope to the futures tables; `events`/`teams` stamps are a different
        # column family with different consumers.
        if "FuturesOutcome" not in src and "futures_outcomes" not in src:
            continue
        sites = _poll_stamp_sites(src)
        if sites:
            found[f] = len(sites)

    assert found == POLL_STAMP_COUNTS, {
        "unexpected_new_stamper": sorted(set(found) - set(POLL_STAMP_COUNTS)),
        "stamper_that_disappeared": sorted(set(POLL_STAMP_COUNTS) - set(found)),
        "count_drift": {
            k: (POLL_STAMP_COUNTS.get(k), found.get(k))
            for k in set(found) | set(POLL_STAMP_COUNTS)
            if POLL_STAMP_COUNTS.get(k) != found.get(k)
        },
        "why": (
            "#2024 — this census moving means the poll touch-stamps changed. "
            "Before updating it, re-read READ_SIDE_CONSUMERS below: "
            "`routes/playoffs.py` DROPS an outcome from the playoff grid on a "
            "stale stamp, so a change-stamp blanks every merely-STABLE price."
        ),
    }


# ---------------------------------------------------------------------------
# READ side — the reason option 1 is refused
# ---------------------------------------------------------------------------

#: Call sites that gate on ``last_updated`` as a FRESHNESS filter, i.e. that
#: read it as "the poller is alive" rather than "this price is fresh". These are
#: what option 1 would break.
#:
#: The severe one is ``routes/playoffs.py``: a stamp older than the cutoff drops
#: the outcome from the playoff grid entirely.
#:
#: The reading recorded against each is the deliverable #2024's acceptance lists
#: FIRST ("each one's intended reading recorded"), and it is what decides the
#: design: the set is MIXED, so no single meaning for the column can serve it.
READ_SIDE_CONSUMERS = {
    "app/routes/playoffs.py": (
        "POLLER ALIVE — grid staleness gate. An outcome whose stamp predates the "
        "cutoff is `continue`d and does NOT render. This is the veto on option 1: "
        "a change-stamp blanks every stable price out of the playoff grid."
    ),
    "app/routes/admin_judgments.py": (
        "PRICE FRESH — the #2019 labeling sampler's price-age floor. The consumer "
        "#2024 was found through, and the one that is WRONG today: it is filtering "
        "on a stamp that says the poller ran."
    ),
    "app/routes/oscars.py": (
        "NEITHER — `outcome.last_updated > existing_ts` is a max() fold over "
        "nominees to display 'last updated'. Insensitive to the change either way, "
        "but it is a comparison site and is recorded so the set is complete."
    ),
}

_GATE = re.compile(r"last_updated\s*(?:<|>=|<=|>)\s*")


def test_read_side_consumers_are_exactly_the_audited_set() -> None:
    """Every place a stamp COMPARISON is made against the futures columns.

    A new entry here widens the blast radius of #2024's option 1. It is not a
    list to keep current; it is a list whose growth is the finding.
    """
    found = {f for f in _src_files("app/routes", "app/utils") if _GATE.search(_read(f))}
    assert found == set(READ_SIDE_CONSUMERS), {
        "unaudited_new_consumer": sorted(found - set(READ_SIDE_CONSUMERS)),
        "consumer_that_disappeared": sorted(set(READ_SIDE_CONSUMERS) - found),
        "why": "#2024 — each of these is a consumer whose reading option 1 could invert",
    }


def test_the_audited_readings_disagree_with_each_other() -> None:
    """The audit's conclusion, as an assertion rather than a paragraph.

    Both readings — "the poller is alive" and "this price is fresh" — are live
    on the SAME column. That is the whole finding: there is no value the column
    can take that satisfies both, which is why #2024's option 2 (a separate
    `price_changed_at`) is the fix and option 1 is refused.
    """
    readings = {v.split(" —")[0] for v in READ_SIDE_CONSUMERS.values()}
    assert {"POLLER ALIVE", "PRICE FRESH"} <= readings, (
        "One of the two conflicting readings left the audit. If only one "
        "reading survives, option 1 (stamp on change) may now be safe — re-run "
        f"the audit rather than assuming. readings={sorted(readings)}"
    )


def test_the_playoff_grid_really_does_drop_a_stale_outcome() -> None:
    """The specimen behind the refusal, asserted rather than described.

    If this stops being true the refusal weakens and #2024's option 1 gets
    cheaper — so it is checked, not trusted.
    """
    src = _read("app/routes/playoffs.py")
    window = src[src.index("_stale_skipped += 1") - 400 : src.index("_stale_skipped += 1") + 60]
    assert "last_updated" in window, "the grid's stale gate no longer reads last_updated"
    assert "continue" in window, "the grid's stale gate no longer DROPS the outcome"


def test_futures_outcome_timestamp_columns() -> None:
    """#2024's central claim, held to the schema rather than to memory.

    ── THIS TEST RED WHEN THE COLUMN LANDED, WHICH IS WHAT IT WAS FOR ─────────

    UX-P106 wrote it asserting `FuturesOutcome` had NOTHING that answers price
    freshness — no timestamp but `opening_captured_at` and the touch-stamp — and
    said in its own docstring: *"when the column lands, this test is the one
    that should red."* UX-P107 landed it and it did.

    So it flips rather than being deleted. The claim it now pins is the one that
    replaced it: `price_changed_at` exists, and `last_updated` is still there
    beside it, unnarrowed, because `routes/playoffs.py` gates the grid on it.
    """
    from app.models.models import FuturesOutcome

    timestamps = {
        c.name
        for c in FuturesOutcome.__table__.columns
        if str(c.type).startswith("TIMESTAMP") or "DateTime" in str(type(c.type))
    }
    assert timestamps == {
        "opening_captured_at",
        "last_updated",
        "price_changed_at",
    }, f"FuturesOutcome's timestamp columns changed. found={sorted(timestamps)}"

    # NULLABLE, and it must stay so. The column is populated forward by the
    # polls; a NOT NULL with a server_default would stamp every historical row
    # with the deploy time — a fabricated answer to "when did this price last
    # move", which is gotcha #53 written into a schema.
    assert FuturesOutcome.__table__.c.price_changed_at.nullable is True
    assert FuturesOutcome.__table__.c.price_changed_at.server_default is None


#: Every price-writing site that must maintain `price_changed_at`, MEASURED.
#: A census rather than a boolean for the same reason as `POLL_STAMP_COUNTS`:
#: a new price writer that forgets the stamp is a provider whose column quietly
#: goes stale while the other two look healthy.
PRICE_CHANGE_STAMPERS = {
    "app/tasks/kalshi.py": 2,
    "app/tasks/polymarket.py": 3,
    "app/tasks/futures.py": 1,
    # #2199. Its one price write carries the conditional change-stamp beside the
    # unconditional touch-stamp, so a refreshed-but-unmoved price does not read
    # as a move — `routes/playoffs.py` drops an outcome from the grid on a stale
    # stamp, and this writer's whole cohort is the tier-1 championship fields
    # that grid renders.
    "app/tasks/futures_price_refresh.py": 1,
}


def test_every_price_writer_maintains_price_changed_at() -> None:
    """The writer half of #2024's option 2.

    Pairs with `test_write_side_is_exactly_the_known_poll_stampers`: that census
    counts the UNCONDITIONAL touch-stamps (which are correct and must stay),
    this one counts the CONDITIONAL price-change stamps beside them. The two
    together are the statement that the columns now mean different things.
    """
    found = {}
    for f in _src_files("app/tasks"):
        n = _read(f).count("price_changed_at_value(")
        if n:
            found[f] = n
    assert found == PRICE_CHANGE_STAMPERS, {
        "writer_missing_the_stamp": sorted(set(PRICE_CHANGE_STAMPERS) - set(found)),
        "unexpected_new_writer": sorted(set(found) - set(PRICE_CHANGE_STAMPERS)),
        "count_drift": {
            k: (PRICE_CHANGE_STAMPERS.get(k), found.get(k))
            for k in set(found) | set(PRICE_CHANGE_STAMPERS)
            if PRICE_CHANGE_STAMPERS.get(k) != found.get(k)
        },
        "why": "#2024 — a price writer without the change-stamp leaves the column stale for that provider only",
    }


def test_there_is_exactly_one_change_stamp_predicate() -> None:
    """#1951's rule, applied before the second copy exists rather than after.

    Five call sites across three poll tasks. A second inlined `case(...)`
    comparing a price would be a predicate free to drift — and a drifted
    change-detector does not throw, it just stops stamping.
    """
    import re

    inline = [
        f
        for f in _src_files("app/tasks")
        if re.search(r"price_changed_at[\"']?\s*[:=]\s*case\(", _read(f))
    ]
    assert inline == [], f"inline change-stamp predicate in {inline}; use price_change_stamp"


def test_the_index_is_not_in_the_migration_chain() -> None:
    """Gotcha #31, as a predicate.

    UX-P106 measured `Seq Scan on futures_outcomes, total cost 156,591` on the
    sampler's own price-age predicate — the column has no index. The fix is a
    manual `CREATE INDEX CONCURRENTLY` run by the Integrator, NOT a migration:
    concurrent index builds hang Heroku's ~5-minute release phase (the May 22
    `odds_snapshots` outage) and a non-concurrent one locks the table against
    the live pollers.

    The pull to "just add it to the migration while we're here" is exactly what
    caused that outage, so it is checked rather than trusted. The DDL is
    recorded in the migration's docstring for whoever runs it.
    """
    import re
    from pathlib import Path

    #: ── A RATCHET, NOT A CLEAN GATE, AND THE REASON IS A REAL FINDING ────────
    #:
    #: Writing this guard turned up TWO MIGRATIONS ALREADY IN THE CHAIN that do
    #: exactly what gotcha #31 forbids — `op.execute("COMMIT")` to escape the
    #: transaction, then `CREATE INDEX CONCURRENTLY` — on `futures_markets` and
    #: `events`, two of the largest tables in the database.
    #:
    #: They are grandfathered rather than fixed. Gotcha #8: a migration that has
    #: already run on Heroku must never be altered, and these have. The risk they
    #: carry now is not a re-run, it is PRECEDENT — they are what the next person
    #: greps for and copies, which is one of the ways #31 keeps recurring. So
    #: they are named here with the reason, and a THIRD one reds.
    #:
    #: (`4623658a2704` is deliberately absent: its body is `pass` and the DDL
    #: lives in a comment for manual application — the pattern this queue
    #: followed, and the one that is correct.)
    GRANDFATHERED = {"add_market_tags.py", "add_taxonomy_tags.py"}

    def _executed(src: str) -> str:
        """Source with docstrings and comments removed — what actually runs.

        A first draft split on `\"\"\"` and took the tail, which flagged
        `4623658a2704` for RECORDING the DDL in a comment. A guard that cannot
        tell an executed statement from a written-down one teaches the next
        reader to stop writing the deploy step down.
        """
        src = re.sub(r'"""(?:.|\n)*?"""', "", src)
        src = re.sub(r"'''(?:.|\n)*?'''", "", src)
        return "\n".join(re.sub(r"#.*$", "", line) for line in src.split("\n"))

    versions = Path(BACKEND / "alembic/versions")
    offenders = sorted(
        p.name
        for p in versions.glob("*.py")
        if p.name not in GRANDFATHERED and re.search(r"CONCURRENTLY", _executed(p.read_text(encoding="utf-8")), re.I)
    )
    assert offenders == [], (
        f"CONCURRENTLY index build inside a migration: {offenders}. Gotcha #31 — "
        "this hangs Heroku's release phase and takes the app down (May 22, "
        "odds_snapshots). Record the DDL in the docstring and apply it manually."
    )

    migration = _read("alembic/versions/add_outcome_price_changed_at.py")
    assert "ix_futures_outcomes_last_updated" in migration, (
        "the manual index DDL left the migration's docstring — it is the only "
        "place the deploy step is written down"
    )
    body = migration.split('"""')[-1]
    assert "create_index" not in body, "the index was moved into the migration body"


def test_the_reader_switch_is_DISCHARGED() -> None:
    """** THE DEBT IS PAID, AND THE REMINDER IS INVERTED RATHER THAN DELETED. **

    UX-P107 wrote this as `test_the_reader_switch_is_still_OWED` and said in its
    own body: "When it lands, this test reds and gets deleted." It landed in
    UX-P108 and it did red. It is inverted in place instead, so #2024's whole
    life — writer, named residual, reader — stays legible in one file rather
    than ending in a deletion nobody can find later.

    ** AND P107 CALLED THE HAZARD CORRECTLY: ** "the new column is populated
    forward, so every row not yet re-polled reads NULL, and a bare
    `price_changed_at >= cutoff` would silently empty the sampler." That is
    exactly what the shipped policy avoids — NULL is UNKNOWN, never STALE
    (gotcha #53), so an unstamped row falls back to `last_updated` and the
    deploy is a no-op on day one.

    The BEHAVIOUR of that policy is asserted in
    `tests/test_taste_price_freshness_null_policy.py`, which compiles the real
    query and kills the two mutants that matter. This test only holds the two
    structural facts that make it true: the new column is read, and the old one
    is still present as the fallback.
    """
    source = _read("app/routes/admin_judgments.py")
    assert "price_changed_at" in source, (
        "admin_judgments.py stopped reading `price_changed_at` — the #2024 "
        "reader switch has been reverted. `last_updated` alone cannot see an "
        "actively-polled market whose price has not moved in three months."
    )
    assert "last_updated" in source, (
        "the `last_updated` FALLBACK is gone from admin_judgments.py. It is "
        "what keeps a never-re-polled row (price_changed_at IS NULL) in the "
        "sampler — without it the taste strata empty on deploy, which is the "
        "failure UX-P107 named when it left this reminder."
    )
