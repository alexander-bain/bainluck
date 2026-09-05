"""LIVE-077-TOUCH-STAMP-PROVENANCE-GUARD — ``last_updated`` stays a PRICE stamp.

WHAT THIS PROTECTS, AND WHY IT EXISTS NOW. Since #3243 / #2898 the tournament
hub grades a rendered probability as live or stale from the NEWER of two
clocks — ``futures_odds_snapshots.captured_at`` (the history clock) and
``futures_outcomes.last_updated`` (the touch stamp). That change was correct on
the population it measured, and CERT-1918 granted it on exactly one condition,
recorded as its follow-up: the touch stamp is only an honest lower bound on
"when did somebody last look at this price" for as long as **every writer of the
column is a price writer that had just read the venue**.

Nothing in the schema says so. ``FuturesOutcome.last_updated`` carries a
``server_default`` and no ``onupdate``; it is stamped explicitly, by hand, at
roughly ninety sites written by different people over two years. Three surfaces
now depend on the reading (``/tournaments/{slug}``, the playoff grid's liveness
gate, ``admin_judgments``' price-freshness read), and the way that reading dies
is not a bad argument — it is a new writer nobody thought about, stamping the
column from a settlement sweep or a volume backfill and thereby telling the
tournament hub that an hours-old number was observed seconds ago.

THE INVARIANT. Every write of ``last_updated`` under ``app/`` falls in one of
three classes, and the class is readable from the statement the write is in:

``price``
    stamped in the same statement as a price column. This is the reading every
    consumer has. Nothing to declare.
``settled``
    stamped in the same statement as a settlement column (``is_winner``,
    ``resolution_source``, ``calibration_probability``). These land on rows that
    are no longer rendered as live, which is why ``backfill_winners`` stamping
    the column at ~50 sites is not a defect. Nothing to declare.
``non-price``
    everything else — a bare touch, or a volume-only write. **These are the ones
    that can lie**, and each must be named in :data:`NON_PRICE_REGISTER` with a
    reason and an entry point, and must be proven non-continuous.

WHY A SOURCE SCAN. There is no runtime seam at which "a non-price writer stamped
a live tournament row" can be observed without standing up Postgres, the venue
clients and a beat; and by the time it is observable the wrong banner has already
shipped. What actually goes wrong over time is a property of the source — a new
site lands and nobody connects it to a freshness reading three surfaces away —
and that is what this scans for.

AND WHY IT SCANS THE WAY IT DOES (gotcha #157). A source-scan guard certifies
the population it SCANS, not the one its name claims. So:

* the file list is the WEAK reading — every ``*.py`` under ``app/`` whose text
  contains ``last_updated`` — never a hand-written list, so a file whose only
  site is in a shape this scan does not yet recognise cannot drop out of the
  sweep before the cross-check sees it;
* a site is attributed to the STATEMENT it belongs to (the whole SQL string, the
  whole upsert dict, the whole run of attribute assignments), not to an N-line
  window: ``backfill_winners`` opens ``UPDATE futures_outcomes SET`` twenty
  lines above the ``last_updated = NOW()`` that belongs to it;
* a value the scan cannot read RAISES. A scanner that skips what it does not
  understand reports a clean zero for exactly the case it was built to catch.

WHAT THIS DOES NOT CLAIM. It does not prove a settlement write never lands on a
row the hub renders live — that is a runtime fact about `status`, argued in
``test_tournament_price_clock_3243.py`` and not re-argued here. It proves the
column's WRITER SET, which is the thing that was undeclared.
"""

from __future__ import annotations

import ast
import pathlib
import re
from dataclasses import dataclass

import pytest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

# The column lives on exactly ONE model (`FuturesOutcome`), which is what makes
# a bare name scan sound: there is no `events.last_updated` for a site to
# belong to instead. `test_the_column_is_unique_to_futures_outcomes` holds that.
COLUMN = "last_updated"

# ---------------------------------------------------------------------------
# What a write looks like, and what a value is allowed to be
# ---------------------------------------------------------------------------

#: The four shapes that reach this column in this tree. Ordered most specific
#: first; `attr` must be tried before `kwarg` or `self.last_updated =` reads as
#: a keyword argument.
_SHAPES = (
    ("mapping", re.compile(r'["\']last_updated["\']\s*:\s*(?P<v>.*)$')),
    ("attr", re.compile(r'(?P<t>[\w\[\]"\'.]+)\.last_updated\s*=(?!=)\s*(?P<v>.*)$')),
    ("kwarg", re.compile(r'(?<![\w.])last_updated\s*=(?!=)\s*(?P<v>.*)$')),
)

#: A line that OPENS with a SQL boolean connective is a predicate, not a SET
#: item. `repair_kalshi_fabricated_loss`'s restore reads
#: `AND last_updated = :applied_version` as a compare-and-set guard, which is a
#: READ of the value apply wrote and must not be counted as a writer.
_PREDICATE = re.compile(r"^\s*(AND|OR|WHERE)\b", re.I)

#: Values that stamp a clock — the writes.
_CLOCK_VALUES = frozenset({
    "func.now()", "now()", "NOW()", "now", "at",
    ":applied_version", ":restored_version",
})

#: Values that hand the stored stamp back out — serialisers, not writes. Matched
#: on shape rather than enumerated, because every route that renders an outcome
#: emits one and the list would rot.
_READ_VALUE = re.compile(
    r"\.isoformat\(\)|^None$|\.get\(|^[\w.]+\[|^raw\.|^info\.|^data\["
)

#: Columns whose presence in the same statement makes the stamp a price
#: observation. `opening_probability` counts: it is only ever written beside a
#: current price.
_PRICE_COLUMNS = (
    "current_probability", "current_yes_bid", "current_yes_ask",
    "current_american_odds", "current_decimal_odds", "price_changed_at",
    "opening_probability", "probability_change_24h", "last_trade_price",
)

#: Columns whose presence makes the stamp a settlement write. These land on rows
#: that have stopped being rendered live — PROVIDED the statement has not said
#: otherwise about its own scope. See `_OPEN_SCOPE`.
_SETTLED_COLUMNS = (
    "is_winner", "resolution_source", "calibration_probability", "settled_at",
)

#: A statement that says IN ITS OWN PREDICATE that it lands on non-terminal rows.
#:
#: CERT-1936 BLOCKED round one of this guard for granting the settlement
#: exemption on keyword presence alone. `_clear_premature_open_winners` sweeps
#: premature winners off markets it explicitly restricts to
#: `status NOT IN ('resolved','closed')`, changes winner metadata only, reads no
#: venue price — and stamped the touch stamp every six hours. The scan read
#: `is_winner` / `resolution_source` in the statement and called it `settled`,
#: which is the whole class the register exists to catch: the exemption was
#: granted by vocabulary, and the rows it was granted over were the OPEN ones
#: the hub renders live.
#:
#: So the exemption now has to survive the statement's own scope claim. The
#: settlement columns say what a write is ABOUT; this says what it lands ON, and
#: a write that has declared its rows still open cannot be excused as a write to
#: rows that have stopped being rendered.
#:
#: MEASURED over the 50 settlement-classified sites at the time of writing: this
#: refuses exactly one, `_clear_premature_open_winners`, and none of the other
#: 49. It is a discriminator, not a net. (The rejected alternative was to demand
#: a POSITIVE `status IN ('resolved','closed')` clause: only 3 of the 50 carry
#: one, because the ordinary settlement write is keyed by outcome id after a
#: result is known and has no business naming a status. A rule 46 real writers
#: fail is a rule that would be satisfied by 46 register entries, which is the
#: shape a guard rots into rather than a guard.)
_OPEN_SCOPE = re.compile(
    r"status\s+NOT\s+IN\b"
    r"|status\s*(!=|<>)\s*'(resolved|closed)'"
    r"|status\s*(=|IN)\s*\(?\s*'(open|active)'",
    re.I,
)

PRICE = "price"
SETTLED = "settled"
NON_PRICE = "non-price"


# ---------------------------------------------------------------------------
# The register — every non-price writer, by name, with its reason
# ---------------------------------------------------------------------------

#: ``(app-relative path, enclosing function) -> (entry point, reason)``.
#:
#: An entry point of ``"unwired"`` claims the function has no caller anywhere
#: under ``app/``; ``"attended:<slug>"`` claims it is reachable only through
#: that slug in ``admin_repairs._REPAIRS``. Both claims are PROVEN below, not
#: taken on trust — a register that is only a list of excuses is the shape that
#: rots.
NON_PRICE_REGISTER: dict[tuple[str, str], tuple[str, str]] = {
    ("tasks/polymarket.py", "_backfill_polymarket_volume"): (
        "unwired",
        "Volume-only write (`SET volume = v.vol, last_updated = NOW()`). "
        "Superseded by repair_polymarket_evidence and never scheduled — its own "
        "docstring records that it has no caller and has never executed. If it "
        "is ever wired, it must stop stamping this column or stamp a dedicated "
        "price-observation column instead.",
    ),
    ("tasks/repair_polymarket_evidence.py", "repair"): (
        "attended:polymarket-evidence",
        "Volume-only write (`SET volume = :vol, last_updated = NOW()`) recording "
        "a CONFIRMED ZERO. Attended repair, run by an operator through "
        "/api/admin/repairs; registered ATTENDED ONLY: never wire this to a "
        "beat. Continuous, it would report a venue-evidence fetch as a fresh "
        "price observation on rows that were never priced.",
    ),
}


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------

def _rel(path: pathlib.Path) -> str:
    """``app/``-relative where possible; the bare name for a synthetic source.

    The mutation tests below drive the real scanner over files in ``tmp_path``,
    which is the only way to show it red without editing the tree it guards.
    """
    try:
        return str(path.relative_to(APP_ROOT))
    except ValueError:
        return path.name


@dataclass(frozen=True)
class Site:
    path: pathlib.Path
    line: int
    function: str
    kind: str
    value: str
    window: str

    @property
    def rel(self) -> str:
        return _rel(self.path)

    @property
    def where(self) -> str:
        return f"app/{self.rel}:{self.line} ({self.function})"

    @property
    def klass(self) -> str:
        if any(c in self.window for c in _PRICE_COLUMNS):
            return PRICE
        if any(c in self.window for c in _SETTLED_COLUMNS):
            # CERT-1936. A settlement write earns its exemption because it lands
            # on rows that have stopped being rendered live. A statement whose
            # own predicate restricts it to non-terminal rows has refuted that
            # premise about itself, and no amount of settlement vocabulary
            # buys it back.
            return NON_PRICE if _OPEN_SCOPE.search(self.window) else SETTLED
        return NON_PRICE


def _docstring_lines(tree: ast.AST) -> set[int]:
    """Lines occupied by a module/class/function docstring.

    Excluded because this file's own prose, and several of the files it scans,
    quote the write shapes verbatim while explaining them.
    """
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            const = body[0].value
            out.update(range(const.lineno, (const.end_lineno or const.lineno) + 1))
    return out


def _enclosing_function(tree: ast.AST, line: int) -> str:
    best_name, best_at = "<module>", -1
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if node.lineno > best_at:
                    best_name, best_at = node.name, node.lineno
    return best_name


def _sql_string_span(tree: ast.AST, line: int) -> tuple[int, int] | None:
    """The multi-line string literal the write sits inside, if any.

    Deliberately only MULTI-line: a single-line constant is often the dict key
    ``"last_updated"`` itself, and taking that as the statement would hide every
    sibling column in the upsert it belongs to. A one-line raw SQL update keeps
    its whole SET list on the line anyway.
    """
    best: tuple[int, int, int] | None = None
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        end = node.end_lineno or node.lineno
        if end == node.lineno or not (node.lineno <= line <= end):
            continue
        span = end - node.lineno
        if best is None or span < best[0]:
            best = (span, node.lineno, end)
    return None if best is None else (best[1], best[2])


def _statement_span(tree: ast.AST, line: int) -> tuple[int, int] | None:
    best: tuple[int, int, int] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        end = node.end_lineno or node.lineno
        if not (node.lineno <= line <= end):
            continue
        span = end - node.lineno
        if best is None or span < best[0]:
            best = (span, node.lineno, end)
    return None if best is None else (best[1], best[2])


def _attribute_run(lines: list[str], line: int, target: str) -> tuple[int, int]:
    """The contiguous run of attribute assignments to ``target`` around ``line``.

    ORM price updates are written as a paragraph — ``existing.current_probability
    = prob`` then five siblings then ``existing.last_updated = now`` — so the
    statement the stamp belongs to is the paragraph, not the one assignment.
    Comment lines and blanks inside the run are crossed; anything else ends it.
    """
    pattern = re.compile(rf"^\s*{re.escape(target)}\.\w+\s*=(?!=)")
    start = end = line
    for i in range(line - 1, 0, -1):
        text = lines[i - 1]
        if pattern.match(text):
            start = i
        elif text.strip() == "" or text.strip().startswith("#"):
            continue
        else:
            break
    for i in range(line + 1, len(lines) + 1):
        text = lines[i - 1]
        if pattern.match(text):
            end = i
        elif text.strip() == "" or text.strip().startswith("#"):
            continue
        else:
            break
    return start, end


def _normalise(value: str) -> str:
    """The value expression, stripped of the syntax that follows it."""
    value = value.split("#")[0].strip()
    value = value.rstrip(",")
    # `last_updated = NOW() WHERE id = :oid"` and `last_updated = NOW() "` —
    # raw SQL keeps going after the value, on the same line.
    for tail in (" WHERE ", " RETURNING ", " FROM "):
        if tail in value:
            value = value.split(tail)[0]
    value = value.strip().rstrip('"').rstrip("'").strip()
    return value


def scan_touch_stamp_writes(
    files: list[pathlib.Path] | None = None,
) -> list[Site]:
    """Every site under ``app/`` that WRITES ``futures_outcomes.last_updated``.

    Raises on a value shape it cannot classify as either a clock or a read.
    """
    sites: list[Site] = []
    for path in sorted(files if files is not None else weak_reading_files()):
        text = path.read_text()
        tree = ast.parse(text)
        lines = text.splitlines()
        skip = _docstring_lines(tree)

        for number, line in enumerate(lines, start=1):
            if number in skip or COLUMN not in line:
                continue
            stripped = line.strip()
            if stripped.startswith("#") or _PREDICATE.match(line):
                continue

            for kind, pattern in _SHAPES:
                match = pattern.search(line)
                if match:
                    break
            else:
                continue

            value = _normalise(match.group("v"))
            if _READ_VALUE.search(value):
                continue
            if value not in _CLOCK_VALUES:
                raise AssertionError(
                    f"app/{_rel(path)}:{number} writes "
                    f"{COLUMN} to a value this scan cannot read:\n"
                    f"  {stripped}\n"
                    f"  value = {value!r}\n"
                    f"Add it to _CLOCK_VALUES if it stamps a clock, or to "
                    f"_READ_VALUE if the line only renders the stored stamp. A "
                    f"shape the scan skips is one it will never classify."
                )

            if kind == "attr":
                span = _attribute_run(lines, number, match.group("t"))
            else:
                span = _sql_string_span(tree, number) or _statement_span(tree, number)
            if span is None:  # pragma: no cover - ast always yields a statement
                raise AssertionError(
                    f"app/{_rel(path)}:{number}: no enclosing "
                    f"statement; the scan cannot say what this stamp is beside."
                )

            sites.append(Site(
                path=path,
                line=number,
                function=_enclosing_function(tree, number),
                kind=kind,
                value=value,
                window="\n".join(lines[span[0] - 1: span[1]]),
            ))
    return sites


def weak_reading_files() -> list[pathlib.Path]:
    """Every ``*.py`` under ``app/`` whose TEXT mentions the column.

    The weak reading on purpose (gotcha #157): the sweep's population is decided
    before any judgement about write shapes, so a file whose only site is in a
    shape ``_SHAPES`` does not yet recognise still enters the scan and still gets
    the chance to raise.
    """
    return [p for p in sorted(APP_ROOT.rglob("*.py")) if COLUMN in p.read_text()]


# ---------------------------------------------------------------------------
# Part 1 — the scan is looking at something
# ---------------------------------------------------------------------------

#: An anti-drift FLOOR, not the sweep's source. Every one of these is a writer
#: today; if the scan stops finding one, the scan has drifted from the code and
#: its clean zero means nothing.
ANCHOR_WRITERS = {
    "tasks/kalshi.py",
    "tasks/kalshi_ws.py",
    "tasks/polymarket.py",
    "tasks/polymarket_ws.py",
    "tasks/futures.py",
    "tasks/futures_price_refresh.py",
    "tasks/tournament_price_refresh.py",
    "tasks/prediction_market_matching.py",
    "tasks/datagolf.py",
    "tasks/backfill_winners.py",
}


def test_the_column_is_unique_to_futures_outcomes():
    """A bare-name scan is only sound while one model owns the name.

    If a second table grows a ``last_updated``, every site below has to start
    proving which table it belongs to, and this guard's clean result stops
    meaning what it says.
    """
    from app.models import models

    owners = {
        cls.__name__
        for cls in models.Base.__subclasses__()
        if COLUMN in getattr(cls, "__table__", None).columns  # type: ignore[union-attr]
    }
    assert owners == {"FuturesOutcome"}, (
        f"{COLUMN} is no longer unique to FuturesOutcome ({sorted(owners)}). "
        f"The scan in this file resolves sites by column name alone."
    )


def test_the_sweep_is_the_weak_reading_not_a_list():
    swept = {str(p.relative_to(APP_ROOT)) for p in weak_reading_files()}
    assert swept >= ANCHOR_WRITERS, (
        f"the text sweep no longer reaches {sorted(ANCHOR_WRITERS - swept)}"
    )
    # And it is wider than the anchors — the anchors are a floor, and a sweep
    # that had collapsed onto them would be a hand-written list wearing a scan.
    assert len(swept) > len(ANCHOR_WRITERS)


def test_the_scan_finds_a_writer_in_every_anchor_file():
    found = {site.rel for site in scan_touch_stamp_writes()}
    missing = ANCHOR_WRITERS - found
    assert not missing, (
        f"these files write {COLUMN} and the scan found no site in them: "
        f"{sorted(missing)}. The scan has drifted from the code."
    )


def test_every_site_is_classified():
    """No site falls out of the three classes — the scan raises rather than
    skipping, so reaching this assert at all is most of the claim."""
    sites = scan_touch_stamp_writes()
    assert sites
    assert {s.klass for s in sites} <= {PRICE, SETTLED, NON_PRICE}


# ---------------------------------------------------------------------------
# Part 2 — the register, and what it has to prove
# ---------------------------------------------------------------------------


def test_every_non_price_writer_is_registered():
    """THE GUARD. A new bare-touch or volume-only stamp fails by name.

    This is the follow-up CERT-1918 named. The tournament hub reads this column
    as "somebody looked at this price just now"; a writer that stamps it without
    having looked at a price makes that sentence false, and the failure is
    silent — a stale number rendered as live, which is the exact defect #3243
    was filed for, arriving from the other direction.
    """
    strays = [
        site for site in scan_touch_stamp_writes()
        if site.klass == NON_PRICE
        and (site.rel, site.function) not in NON_PRICE_REGISTER
    ]
    assert not strays, "\n".join(
        [
            f"{len(strays)} write(s) of {COLUMN} stamp neither a price nor a "
            f"settlement, and are not registered:",
            *(f"  {s.where}  [{s.kind}] {s.value}" for s in strays),
            "",
            "The tournament hub, the playoff grid and admin_judgments all read "
            "this column as a price observation. Either stamp a price in the "
            "same statement, or add the site to NON_PRICE_REGISTER with an "
            "entry point this file can prove non-continuous.",
        ]
    )


def test_the_register_has_no_dead_entries():
    """An entry for a site that no longer exists is an excuse outliving its
    case, and the next reader takes it as evidence the shape is fine."""
    live = {
        (site.rel, site.function)
        for site in scan_touch_stamp_writes()
        if site.klass == NON_PRICE
    }
    dead = set(NON_PRICE_REGISTER) - live
    assert not dead, (
        f"NON_PRICE_REGISTER names sites that are no longer non-price writes: "
        f"{sorted(dead)}. Delete them."
    )


@pytest.mark.parametrize(
    "key", sorted(k for k, v in NON_PRICE_REGISTER.items() if v[0] == "unwired")
)
def test_an_unwired_non_price_writer_really_has_no_caller(key):
    """"Never scheduled" is a claim about the call graph, so it gets checked.

    Any mention of the name under ``app/`` outside its own ``def`` — a call, an
    import, a beat entry — ends the claim; the register entry then has to move
    to an attended entry point or the write has to stop stamping the column.
    """
    rel, function = key
    hits: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        text = path.read_text()
        if function not in text:
            continue
        tree = ast.parse(text)
        skip = _docstring_lines(tree)
        for number, line in enumerate(text.splitlines(), start=1):
            if number in skip or function not in line:
                continue
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.match(rf"\s*(async\s+)?def\s+{re.escape(function)}\b", line):
                continue
            hits.append(f"app/{path.relative_to(APP_ROOT)}:{number}  {stripped}")
    assert not hits, (
        f"{rel}:{function} is registered as an UNWIRED non-price writer, but it "
        f"is referenced:\n" + "\n".join(hits)
    )


@pytest.mark.parametrize(
    "key", sorted(k for k, v in NON_PRICE_REGISTER.items() if v[0].startswith("attended:"))
)
def test_an_attended_non_price_writer_is_attended_and_stays_that_way(key):
    """The attended claim is proven against the repair registry, and against the
    one file every scheduled task in this tree is declared in.

    Every Celery task lives in ``app/tasks/__init__.py`` and calls its
    implementation by name, so "not named there" is an exact reading of "not on
    a beat" — not an approximation.
    """
    from app.routes import admin_repairs

    rel, function = key
    slug = NON_PRICE_REGISTER[key][0].split(":", 1)[1]

    assert slug in admin_repairs._REPAIRS, (
        f"{rel}:{function} claims attended entry point {slug!r}, which is not "
        f"in admin_repairs._REPAIRS"
    )
    module, entry = admin_repairs._REPAIRS[slug]
    assert module.replace(".", "/") == f"app/{rel}"[:-3] and entry == function, (
        f"repair {slug!r} runs {module}:{entry}, not app/{rel}:{function}"
    )

    registry_source = pathlib.Path(admin_repairs.__file__).read_text()
    assert "ATTENDED ONLY: never wire this to a beat." in registry_source

    tasks_init = (APP_ROOT / "tasks" / "__init__.py").read_text()
    module_leaf = module.rsplit(".", 1)[-1]
    assert module_leaf not in tasks_init, (
        f"{module} is now referenced from app/tasks/__init__.py, where every "
        f"scheduled task in this tree is declared. If {function} has become "
        f"continuous it must stop stamping {COLUMN}, or stamp a dedicated "
        f"price-observation column."
    )


# ---------------------------------------------------------------------------
# Part 3 — the scan can fail
# ---------------------------------------------------------------------------
#
# Three mutations, run against synthetic sources through the same entry point
# the real sweep uses. A guard that has never been shown red is a guard whose
# green means nothing.


def _synthetic(tmp_path: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_a_bare_touch_added_to_a_price_poll_is_caught(tmp_path):
    """The case this file exists for: a new writer stamps the column with no
    price beside it."""
    path = _synthetic(tmp_path, "newpoll.py", (
        "from sqlalchemy import func\n"
        "async def _refresh_volumes(session):\n"
        "    await session.execute(\n"
        '        """\n'
        "        UPDATE futures_outcomes\n"
        "        SET volume = :v, last_updated = NOW()\n"
        "        WHERE id = :oid\n"
        '        """\n'
        "    )\n"
    ))
    sites = scan_touch_stamp_writes([path])
    assert [s.klass for s in sites] == [NON_PRICE]
    assert sites[0].function == "_refresh_volumes"


def test_the_same_write_beside_a_price_is_not_flagged(tmp_path):
    """The other direction, so the guard is not merely 'everything is bad'."""
    path = _synthetic(tmp_path, "goodpoll.py", (
        "async def _refresh(session):\n"
        "    await session.execute(\n"
        '        """\n'
        "        UPDATE futures_outcomes\n"
        "        SET current_probability = :p, last_updated = NOW()\n"
        "        WHERE id = :oid\n"
        '        """\n'
        "    )\n"
    ))
    assert [s.klass for s in scan_touch_stamp_writes([path])] == [PRICE]


def test_an_orm_stamp_is_read_with_its_paragraph_not_its_line(tmp_path):
    """The attribute-run window. On its own line ``o.last_updated = now`` is
    bare; the price it belongs to is two lines up."""
    path = _synthetic(tmp_path, "orm.py", (
        "def update(o, prob, now):\n"
        "    o.name = 'x'\n"
        "    o.current_probability = prob\n"
        "    o.last_updated = now\n"
    ))
    assert [s.klass for s in scan_touch_stamp_writes([path])] == [PRICE]

    lonely = _synthetic(tmp_path, "orm_bare.py", (
        "def touch(o, now):\n"
        "    o.volume = 7\n"
        "    o.last_updated = now\n"
    ))
    assert [s.klass for s in scan_touch_stamp_writes([lonely])] == [NON_PRICE]


def test_the_scan_refuses_a_value_it_cannot_read(tmp_path):
    """gotcha #157 — the scan must not skip what it does not understand."""
    path = _synthetic(tmp_path, "weird.py", (
        "def touch(o):\n"
        "    o.last_updated = whatever_the_venue_said\n"
    ))
    with pytest.raises(AssertionError, match="cannot read"):
        scan_touch_stamp_writes([path])


def test_a_compare_and_set_predicate_is_not_counted_as_a_writer(tmp_path):
    """``AND last_updated = :applied_version`` in the fabricated-loss restore is
    a guard on the value apply wrote, not a second write of it."""
    path = _synthetic(tmp_path, "restore.py", (
        "async def restore(session):\n"
        "    await session.execute(\n"
        '        """\n'
        "        UPDATE futures_outcomes\n"
        "        SET is_winner = NULL, last_updated = :restored_version\n"
        "        WHERE id = ANY(:ids)\n"
        "          AND last_updated = :applied_version\n"
        '        """\n'
        "    )\n"
    ))
    sites = scan_touch_stamp_writes([path])
    assert len(sites) == 1 and sites[0].klass == SETTLED


# ---------------------------------------------------------------------------
# CERT-1936 — THE EXEMPTION HAS TO SURVIVE THE STATEMENT'S OWN SCOPE
#
# Round one of this file granted the settlement exemption on keyword presence.
# CERT-1936 found what that lets through, and it was not hypothetical: it was
# already running, every six hours, on exactly the rows that can least afford
# it.
#
# `_clear_premature_open_winners` sweeps guess-family and source-less winners
# off markets it restricts, in its own predicate, to
# `fm.status NOT IN ('resolved','closed')`. It changes winner metadata only. It
# reads no venue price. And it stamped `last_updated = NOW()`. The scan saw
# `is_winner` and `resolution_source` in the statement and filed it `settled`,
# whose whole justification is "these land on rows that have stopped being
# rendered live" — a sentence the statement's own WHERE clause contradicts.
#
# The consequence is #3243's defect from the other direction. The hub grades a
# rendered probability from the newer of the snapshot clock and this stamp, so a
# six-hourly winner-metadata sweep could report an hours-old probability as
# seconds old, on an OPEN market, during a tournament.
#
# The repair is in two halves and both are asserted below:
#
#   1. The sweep stops stamping the column. It corrects winner metadata; the
#      price clock stays where the last real price reading left it.
#   2. The classifier stops taking vocabulary as proof of scope. A statement
#      that has declared its rows non-terminal cannot be excused as a write to
#      rows that are no longer rendered — however many settlement columns it
#      names.
#
# Half 2 has to be proven on the code that actually had the defect, not only on
# a fixture built to fail: once half 1 lands, the real site stops writing the
# column at all and would vanish from the scan whether or not half 2 works. So
# the pre-fix statement is embedded verbatim and re-classified.
# ---------------------------------------------------------------------------

#: `_clear_premature_open_winners`'s statement AS IT SHIPPED, before CERT-1936.
#: Copied from `backfill_winners.py` at cd48d0f6 — the sha the BLOCK graded.
_PRE_FIX_OPEN_WINNER_SWEEP = (
    "async def _clear_premature_open_winners(session):\n"
    "    r = await session.execute(text(\n"
    '        """\n'
    "        UPDATE futures_outcomes fo\n"
    "        SET is_winner = false,\n"
    "            resolution_source = NULL,\n"
    "            last_updated = NOW()\n"
    "        FROM futures_markets fm\n"
    "        WHERE fo.market_id = fm.id\n"
    "          AND fm.status NOT IN ('resolved', 'closed')\n"
    "          AND fo.is_winner = true\n"
    "          AND (fo.resolution_source IS NULL\n"
    "               OR fo.resolution_source IN ('pass2_guess'))\n"
    '        """\n'
    "    ))\n"
)


def test_the_real_open_winner_cleanup_does_not_touch_the_price_clock():
    """Half 1, on the shipped function rather than a copy of it.

    Read off the real source, so moving the statement, reformatting it or
    reintroducing the stamp under a different clock value all fail here.
    """
    import inspect

    from app.tasks.backfill_winners import _clear_premature_open_winners

    source = inspect.getsource(_clear_premature_open_winners)
    # Strip the DOCSTRING and nothing else. The function's SQL is itself a
    # triple-quoted string, so "everything after the docstring closes" would
    # skip the very statement under test — the first draft of this assertion
    # did exactly that and passed against the stamp still in place.
    parts = source.split('"""')
    body = "".join(parts[:1] + parts[2:]) if len(parts) >= 3 else source
    assert "SET is_winner = false" in body, (
        "the SQL statement fell out of the extracted body; this assertion is "
        "no longer reading the write it claims to read"
    )
    assert COLUMN not in body, (
        f"{_clear_premature_open_winners.__name__} writes {COLUMN} again.\n"
        f"It targets markets that are explicitly NOT resolved or closed — rows "
        f"the tournament hub renders live — and it reads no venue price, so a "
        f"stamp here tells the hub a stale probability was just observed "
        f"(CERT-1936, #3243)."
    )
    # The sweep still does its own job; this is not a test that passes because
    # the function was deleted.
    assert "fm.status NOT IN ('resolved', 'closed')" in source
    assert "is_winner = false" in source
    assert "resolution_source = NULL" in source


def test_the_pre_fix_sweep_is_refused_by_the_classifier(tmp_path):
    """Half 2, against the code that actually had the defect.

    A scan guard proven only against a fixture is a guard proven against its
    author. This is the statement that shipped, verbatim, and the classifier
    must refuse to exempt it.
    """
    path = _synthetic(tmp_path, "prefix_sweep.py", _PRE_FIX_OPEN_WINNER_SWEEP)
    sites = scan_touch_stamp_writes([path])

    assert len(sites) == 1, sites
    assert sites[0].function == "_clear_premature_open_winners"
    # It names two settlement columns; under the round-one rule that was enough.
    assert any(c in sites[0].window for c in _SETTLED_COLUMNS)
    assert sites[0].klass == NON_PRICE, (
        "The pre-CERT-1936 sweep classified as a settlement write. That is the "
        "defect the BLOCK found: the exemption was granted by vocabulary over "
        "rows the statement itself holds open."
    )
    # And it would therefore have had to be registered by name, which is what
    # `test_every_non_price_writer_is_registered` enforces on the real tree.
    assert (sites[0].rel, sites[0].function) not in NON_PRICE_REGISTER


def test_a_synthetic_open_market_winner_write_is_refused(tmp_path):
    """The class, not the instance — a fresh writer of the same shape.

    Different function, different columns, different way of saying "open". The
    fix must not be a special case for one regex the one known site happens to
    contain.
    """
    for name, predicate in (
        ("not_in.py", "status NOT IN ('resolved', 'closed')"),
        ("bang_eq.py", "status != 'resolved'"),
        ("eq_open.py", "status = 'open'"),
        ("in_active.py", "status IN ('active')"),
    ):
        path = _synthetic(tmp_path, name, (
            "async def _retag_open_winners(session):\n"
            "    await session.execute(\n"
            '        """\n'
            "        UPDATE futures_outcomes fo\n"
            "        SET is_winner = true,\n"
            "            resolution_source = 'pass2_guess',\n"
            "            last_updated = NOW()\n"
            "        FROM futures_markets fm\n"
            "        WHERE fo.market_id = fm.id\n"
            f"          AND fm.{predicate}\n"
            '        """\n'
            "    )\n"
        ))
        sites = scan_touch_stamp_writes([path])
        assert [s.klass for s in sites] == [NON_PRICE], (
            f"{name}: an open-market winner write was exempted as a settlement"
        )
        assert (sites[0].rel, sites[0].function) not in NON_PRICE_REGISTER


def test_a_real_settlement_write_is_still_exempt(tmp_path):
    """THE CONTROL, and the reason the rule is a scope rule and not a purge.

    An ordinary settlement is keyed by outcome id after a result is known and
    says nothing about status — 46 of the 50 settlement sites on the tree are
    this shape. If the rule demanded a positive `status IN ('resolved','closed')`
    clause it would flag all of them, and 46 register entries is not a guard.
    """
    settled = _synthetic(tmp_path, "settle.py", (
        "async def _grade(session):\n"
        "    await session.execute(\n"
        '        """\n'
        "        UPDATE futures_outcomes\n"
        "        SET is_winner = :won,\n"
        "            resolution_source = 'api_settlement',\n"
        "            last_updated = NOW()\n"
        "        WHERE id = :oid\n"
        '        """\n'
        "    )\n"
    ))
    assert [s.klass for s in scan_touch_stamp_writes([settled])] == [SETTLED]

    # And a settlement that DOES name a terminal status keeps its exemption —
    # the rule reads which scope was claimed, not whether one was.
    terminal = _synthetic(tmp_path, "settle_terminal.py", (
        "async def _grade_closed(session):\n"
        "    await session.execute(\n"
        '        """\n'
        "        UPDATE futures_outcomes fo\n"
        "        SET is_winner = :won,\n"
        "            last_updated = NOW()\n"
        "        FROM futures_markets fm\n"
        "        WHERE fo.market_id = fm.id\n"
        "          AND fm.status IN ('resolved', 'closed')\n"
        '        """\n'
        "    )\n"
    ))
    assert [s.klass for s in scan_touch_stamp_writes([terminal])] == [SETTLED]


def test_the_scope_rule_refuses_exactly_one_site_on_the_real_tree():
    """The population claim, so the rule is known to be a discriminator.

    Measured when CERT-1936's repair was built: of the settlement-classified
    writes on the tree, the open-scope predicate refused one — the sweep — and
    none of the others. After the repair the sweep stamps nothing, so the live
    tree has zero; the pre-fix statement above carries the positive case.
    """
    settled_or_refused = [
        site for site in scan_touch_stamp_writes()
        if any(c in site.window for c in _SETTLED_COLUMNS)
        and not any(c in site.window for c in _PRICE_COLUMNS)
    ]
    refused = [s for s in settled_or_refused if s.klass == NON_PRICE]
    assert refused == [], (
        "A settlement-family write on the tree now claims non-terminal scope:\n"
        + "\n".join(f"  {s.where}" for s in refused)
        + "\nEither drop its touch stamp (it lands on rows still rendered live) "
          "or narrow its predicate to the rows it actually settles."
    )
    assert len(settled_or_refused) >= 40, (
        "The settlement population collapsed; the scan is no longer finding "
        "the writers this rule is measured against."
    )
