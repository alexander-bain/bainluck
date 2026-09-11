"""An opening price is written with the basis that produced it — #5401.

WHY THIS EXISTS. ``futures_outcomes.opening_source`` records HOW a leg's opening
price was obtained, and on the published calibration curve that field turns out
to be the sharpest single predictor of whether the price is honest. Measured
through the producer's own CTE chain on 2026-09-11
(``scripts/calibration_fold_opening_source.py``), published ``kalshi/golf``:

    basis              band    legs    won   implied   realised
    bid_ask_midpoint     hi     289    273     272.3      94.5%
    bid_ask_midpoint     lo   7,399  1,341   1,260.9      18.1%
    (untagged)           hi     418    101     388.2      24.2%
    (untagged)           lo  12,513  1,422   2,263.6      11.4%

A leg carrying a basis is priced almost exactly right in both bands. A leg
carrying none is not: the untagged cohort alone accounts for 1,129 of the cell's
1,061 net missing winners — the whole of the miss the accuracy page shows, and
then some, since the tagged cohort is mildly UNDER-priced and offsets it.

SO THE FIELD IS LOAD-BEARING, AND IT WAS NOT BEING WRITTEN. In ``kalshi.py`` the
poller's upsert sets ``opening_source`` on the CONFLICT arm and, until #5401, not
on the INSERT arm. A leg whose opening was captured the first time the poller
ever saw it — the common case in a 150-runner golf field, where most legs are
seen once and never re-polled while tradeable — was therefore born with a real
opening price and no record of where it came from, indistinguishable from rows
that predate the column entirely.

That is the same defect CAL-P1004R found at this exact ``pg_insert`` one column
over (``test_futures_outcome_is_winner_named_4788.py``): the conflict arm was
maintained and the insert arm was not.

WHAT THIS FILE DOES NOT CLAIM. Tagging the basis does not repair the curve. The
untagged legs already published stay published, and the exclusion that would
take them out of the curve is a population change gated on a
``q269 -> q270`` version bump (see #5401). This guard stops the flow of untagged
openings; it does not drain the stock, and it makes no claim that ANY particular
basis value is a good price — only that a price arrives with its provenance
attached, which is the precondition for ever ruling on it.

THE OTHER VENUES ARE NOT FIXED HERE, AND THE COUNT IS PINNED SO THEY STAY
VISIBLE. The scan below discovers every Core writer that names
``opening_probability`` rather than reading a list someone typed, and the
remaining untagged venues are hand-classified into :data:`KNOWN_UNTAGGED` with
their follow-up. A ninth site fails this file on the day it is written.
"""

import ast
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.models import FuturesOutcome

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

#: The column that says how the opening beside it was obtained.
BASIS_COLUMN = "opening_source"

#: The column whose presence makes the basis mandatory.
OPENING_COLUMN = "opening_probability"

MODEL = "FuturesOutcome"

INSERT_FUNCS = {"insert", "pg_insert"}

#: Writers that name an opening WITHOUT its basis and are deliberately left
#: alone by #5401, each with the reason. This is the hand-classified VERDICT on
#: a scanned population — the population itself is discovered below, so a new
#: offender cannot hide by not being on a list.
#:
#: Every entry here is a venue whose openings reach the same curve with the same
#: missing provenance; they are out of scope for #5401 only because #5401 is
#: scoped to the two Kalshi cells it measured, and polymarket/datagolf ingest is
#: another lane's file (notice 41 / D39). Filed as the follow-up named below.
KNOWN_UNTAGGED_FOLLOW_UP = "#5401 follow-up: the other venues write untagged openings"
KNOWN_UNTAGGED = {
    "app/tasks/polymarket.py",
    "app/tasks/futures.py",
    "app/tasks/datagolf.py",
}


def _module_aliases(tree):
    aliases = {MODEL}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == MODEL:
                    aliases.add(alias.asname or alias.name)
    return aliases


def _insert_aliases(tree):
    aliases = set(INSERT_FUNCS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in INSERT_FUNCS:
                    aliases.add(alias.asname or alias.name)
    return aliases


def _is_model_ref(node, model_aliases):
    if isinstance(node, ast.Name):
        return node.id in model_aliases
    if isinstance(node, ast.Attribute):
        return node.attr == MODEL
    return False


def _is_insert_func(func, insert_aliases):
    if isinstance(func, ast.Name):
        return func.id in insert_aliases
    if isinstance(func, ast.Attribute):
        return func.attr in INSERT_FUNCS
    return False


def _chain_root(node, insert_aliases):
    current = node
    while True:
        if isinstance(current, ast.Call):
            if _is_insert_func(current.func, insert_aliases):
                return current
            if isinstance(current.func, ast.Attribute):
                current = current.func.value
                continue
            return current
        if isinstance(current, ast.Attribute):
            current = current.value
            continue
        return current


def _keyword(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw
    return None


def _opening_writer_sites():
    """Every writer in ``app/`` that stores an opening price on an outcome.

    Discovered, not listed. Returns ``(relative_path, lineno, call)`` triples.

    BOTH CONSTRUCTION SHAPES, and the second one is not optional: the first
    version of this scan read only ``pg_insert(FuturesOutcome).values(...)`` and
    reported three untagged venues. ``datagolf.py`` writes its openings through
    the ORM constructor instead, so a scan that calls itself a class tripwire
    was silently missing a whole venue — the same blindness #4819 closed in the
    4788 guard, reproduced here by copying only half of it.
    """
    sites = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        model_aliases = _module_aliases(tree)
        insert_aliases = _insert_aliases(tree)
        rel = str(path.relative_to(APP_ROOT.parent))

        for node in ast.walk(tree):
            call = None
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "values"
            ):
                base = _chain_root(node, insert_aliases)
                if (
                    isinstance(base, ast.Call)
                    and _is_insert_func(base.func, insert_aliases)
                    and base.args
                    and _is_model_ref(base.args[0], model_aliases)
                ):
                    call = node
            elif isinstance(node, ast.Call) and _is_model_ref(node.func, model_aliases):
                call = node

            if call is None or _keyword(call, OPENING_COLUMN) is None:
                continue
            sites.append((rel, call.lineno, call))
    return sites


def test_the_scan_finds_opening_writers_at_all():
    """A rename that blinds the scan must fail loudly, not report green."""
    sites = _opening_writer_sites()
    assert sites, (
        "found no Core insert against FuturesOutcome naming "
        f"{OPENING_COLUMN} — the recogniser has gone blind, teach it the new "
        "shape rather than deleting this file"
    )
    assert any(p == "app/tasks/kalshi.py" for p, _, _ in sites), (
        "the Kalshi poller is the subject of #5401 and must be in the scanned "
        "population; if it moved, point the scan at where it went"
    )


def test_the_kalshi_poller_names_the_basis_on_the_insert_arm():
    """#5401. The conflict arm records the basis; so must the insert arm."""
    offenders = [
        f"{path}:{lineno}"
        for path, lineno, call in _opening_writer_sites()
        if path == "app/tasks/kalshi.py" and _keyword(call, BASIS_COLUMN) is None
    ]
    assert not offenders, (
        "These Kalshi writers store an opening price with no record of the "
        "basis that produced it, so the leg is indistinguishable from the "
        "untagged historical cohort that carries the whole of the published "
        f"kalshi/golf miss (#5401):\n  " + "\n  ".join(offenders) + "\n\n"
        f"Name it: `{BASIS_COLUMN}=\"bid_ask_midpoint\" if has_real_trading "
        "else None`, mirroring `opening_probability` on the same call and the "
        "conflict arm a few lines above."
    )


def test_the_untagged_venues_are_exactly_the_ones_we_know_about():
    """A count tripwire on the class, so a ninth site cannot arrive quietly.

    This is NOT an assertion that the four venues below are acceptable — they
    write the same untagged openings into the same curve. It records that they
    are OUT OF SCOPE for #5401 and in whose follow-up, and it fails the moment
    the set changes in either direction: a new offender, or one of these fixed
    without the record being updated.
    """
    untagged = {
        path
        for path, _, call in _opening_writer_sites()
        if _keyword(call, BASIS_COLUMN) is None
    }
    assert untagged == KNOWN_UNTAGGED, (
        "the set of writers storing an opening with no basis has changed.\n"
        f"  now:      {sorted(untagged)}\n"
        f"  recorded: {sorted(KNOWN_UNTAGGED)}\n"
        f"If you fixed one, drop it from KNOWN_UNTAGGED. If you added one, "
        f"name the basis instead — see {KNOWN_UNTAGGED_FOLLOW_UP}."
    )


def _sqlite_engine():
    engine = sa.create_engine("sqlite://")
    FuturesOutcome.__table__.create(engine)
    return engine


def _basis(session, external_id):
    return session.execute(
        sa.select(FuturesOutcome.opening_source).where(
            FuturesOutcome.external_id == external_id
        )
    ).scalar_one()


def test_an_omitted_basis_stores_null_beside_a_real_opening():
    """The semantics the static rule rests on, demonstrated rather than asserted.

    ``opening_source`` is a plain nullable String(30) with no server default, so
    an insert that omits it stores NULL — and NULL beside a NOT NULL
    ``opening_probability`` is exactly the row shape that made 12,931 published
    golf legs unreadable. The conditional the poller now writes must also store
    a real NULL when there was no trading, rather than the string ``"None"``.
    """
    engine = _sqlite_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(FuturesOutcome).values(
                market_id=1, external_id="omitted", name="omitted",
                current_probability=0.95, opening_probability=0.95,
            )
        )
        conn.execute(
            sa.insert(FuturesOutcome).values(
                market_id=1, external_id="tagged", name="tagged",
                current_probability=0.95, opening_probability=0.95,
                opening_source="bid_ask_midpoint" if True else None,
            )
        )
        conn.execute(
            sa.insert(FuturesOutcome).values(
                market_id=1, external_id="no_trading", name="no_trading",
                current_probability=0.95, opening_probability=None,
                opening_source="bid_ask_midpoint" if False else None,
            )
        )

    with Session(engine) as session:
        assert _basis(session, "omitted") is None, (
            "omitting the column must store NULL — if it ever gains a server "
            "default, the untagged cohort stops being identifiable and #5401's "
            "whole measurement basis changes"
        )
        assert _basis(session, "tagged") == "bid_ask_midpoint"
        assert _basis(session, "no_trading") is None, (
            "no opening means no basis: the conditional must reach the database "
            "as SQL NULL, not as the string 'None'"
        )
