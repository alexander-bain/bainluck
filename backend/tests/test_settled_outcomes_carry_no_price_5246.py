"""#5246 — a settled outcome carries its settlement, not the last price anyone paid.

THE DEFECT THESE GUARD. On US Open men's semifinal day the winner card offered
48 names with four players alive, and priced Alexander Zverev at 34% while
Kalshi said 49.5%. The four survivors' stored probabilities were exactly right
(sum 1.0100); the 44 eliminated players were already graded
`is_winner=false, resolution_source='api_settlement'` and still carried the last
number anyone paid for them, so the column summed to 1.4800 and the rail's
renormalisation taxed every live outcome by a third.

The grade landed and the price did not. Three things had to be true at once:

  1. the settling statement wrote the verdict and not the price,
  2. the price poller's settled refusal tested for a CROWN, not for a GRADE, so
     a resolved-NO leg stayed eligible for re-pricing forever, and
  3. no poll could correct either, because the venue quotes nothing on a
     `finalized` market and every price site refuses a None.

WHY THESE ARE STRING GUARDS AND NOT DATABASE GUARDS. Every real-Postgres gate in
this repo is env-gated (`CALIBRATION_TEST_DATABASE_URL` in 24 files,
`SEARCH_TEST_DATABASE_URL` in 122) and SKIPS in CI, which has no Postgres
service. A skipped guard is not a guard. So these read the real objects the call
sites splice — `_SETTLED_PRICE_SET_SQL`'s return value and `ELIGIBLE_OUTCOMES_SQL`
— never a re-derivation of them.

🔴 AND THEY ARE NOT WHOLE-STATEMENT GUARDS, WHICH THEY WERE FOR ONE CI RUN. The
first draft hoisted both settling UPDATEs into a `settled_grade_update_sql()`
helper precisely so a test could read the composed string. Three of this repo's
existing guards went red at once, and every one of them was right:

  * `test_kalshi_forward_capture_grade_p1004` — the helper needed a
    `won = result == "yes"` line to pick a branch, and that is the two-state
    grade CAL-P1004 exists to keep out of this file (it maps `""` and `"scalar"`
    onto "this outcome lost", at the top authority rung).
  * `test_touch_stamp_provenance_live077` — moving `last_updated=NOW()` inside a
    helper put it where that scan cannot classify it.
  * `test_duplicate_condition_leg_never_wins_q487` — its positive control counts
    the in-class SQL concatenations by hand-classified site, and merging two into
    one shrank the population, which is how a source-scan guard goes vacuous.

The statements are inline because this repo READS them inline. So the
composition is proved where the repo already proves it, and the guard below
asserts only what is genuinely new: the clause's content, and that both call
sites splice it with DIFFERENT prices.
"""

import collections
import re

from app.utils.agent_origin import tagged

import pytest


# --- the producer: the grade and the price are one settlement ----------------


def _task_module_source():
    """The source of the `backfill_winners` MODULE — never the Celery task.

    🔴 `from app.tasks import backfill_winners` does NOT reliably give the
    module. `app/tasks/__init__.py` defines a Celery task of the same name, so
    the attribute on the package is a `celery.local.PromiseProxy` whose
    `inspect.getsource` is the 427-character task wrapper — in which every
    pattern below finds nothing and every `not in` assertion passes.

    It is worse than a plain bug because it is ORDER-DEPENDENT: importing the
    module anywhere earlier in the process also binds it as an attribute of the
    package, so the `from` form yields the real module in a full run and the
    proxy when the file runs alone. That is a guard that passes both ways —
    green in CI, vacuous under sharding, and unfalsifiable by re-running it.

    `importlib.import_module` names the module and cannot resolve to the task.
    """
    import importlib
    import inspect

    return inspect.getsource(importlib.import_module("app.tasks.backfill_winners"))


def _task_module_code():
    """`_task_module_source()` with comments stripped.

    A source scan that reads PROSE grades the prose. This file's own first
    version of the CAL-P1004 assertion below failed on the comment that
    *explains* the fix — the string `rs == "yes"` appears there describing what
    the code used to be. Mirrors `test_kalshi_forward_capture_grade_p1004`'s
    `_code_lines`, which strips for the same reason and says so.
    """
    out = []
    for line in _task_module_source().splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(line.split("  #")[0])
    return "\n".join(out)


def _price_set(price):
    from app.utils.settled_price import settled_price_set_sql

    return settled_price_set_sql(price)


def _settlement_call_sites():
    """The two `_SETTLED_PRICE_SET_SQL(...)` arguments in the settled-events sweep.

    A source scan, deliberately, and in the same form the three guards that
    already police this file use (`test_duplicate_condition_leg_never_wins_q487`
    reads it with `ast`, `test_touch_stamp_provenance_live077` and
    `test_kalshi_forward_capture_grade_p1004` read it as text). The first draft
    of this ship hoisted both UPDATEs into a helper so a test could read the
    composed string, and all three of those guards went red — the statements are
    inline because this repo reads them inline. So the composition is proved
    where the repo proves it, and this asserts only that both call sites exist
    and ask for DIFFERENT prices.
    """
    return re.findall(r"settled_price_set_sql\(SETTLED_(YES|NO)_PRICE\)",
                      _task_module_source())


@pytest.mark.parametrize("price", ["0.0", "1.0"])
def test_the_settlement_price_clause_writes_the_price(price):
    """The clause the settling UPDATEs splice in writes the settlement price.

    This is #5246's producer half: before the fix those UPDATEs set `is_winner`
    and `resolution_source` and left `current_probability` holding a dead
    player's last quote.
    """
    sql = _price_set(price)
    assert f"current_probability={price}" in sql
    assert "current_american_odds=NULL" in sql


def test_the_two_settlement_prices_are_not_each_other():
    """A winner settles at 1.0 and a loser at 0.0.

    Pinned separately because the parametrised test above passes on a mutant
    that returns the same clause for both arguments — each case only ever reads
    its own substring.
    """
    assert _price_set("1.0") != _price_set("0.0")
    assert "current_probability=1.0" in _price_set("1.0")
    assert "current_probability=0.0" not in _price_set("1.0")
    assert "current_probability=0.0" in _price_set("0.0")
    assert "current_probability=1.0" not in _price_set("0.0")


def test_both_settlement_call_sites_ask_for_the_price():
    """The YES branch and the NO branch each splice the clause, with DIFFERENT prices.

    The positive control for the source scan above: a refactor that drops one
    call site, or points both at the same price, fails here rather than shipping
    a sweep that prices only half of what it grades.
    """
    sites = _settlement_call_sites()
    # Six now, not two: the retired sweep's pair plus the two LIVE graders'
    # pairs (CERT-2637). Both prices must appear, and neither may vanish.
    assert set(sites) == {"YES", "NO"}, sites
    assert sites.count("YES") == sites.count("NO") == 3, sites


def test_the_change_stamp_compares_against_the_price_being_written():
    """`price_changed_at` stamps only when the write moves the stored value.

    The CASE must test the SAME literal the SET writes. A mutant that hardcodes
    one side — comparing against 0.0 while writing 1.0 — stamps every crowned
    leg as freshly moved on every sweep, reproducing #2024 in the column added
    to fix it. Both sides are cast to the stored `Numeric(7, 6)` for the reason
    `app/utils/price_change_stamp.py` exists: a provider float and its rounded
    stored form are otherwise never equal.
    """
    for price in ("1.0", "0.0"):
        sql = _price_set(price)
        assert (
            f"IS DISTINCT FROM CAST({price} AS numeric(7,6))" in sql
        ), f"{price}: change stamp must compare against the price it writes"
        assert "ELSE fo.price_changed_at END" in sql


def test_settlement_never_widens_past_the_venues_own_two_answers():
    """The price literal is interpolated, so the set of legal literals is closed.

    `_SETTLED_PRICE_SET_SQL` builds SQL by f-string. That is safe only while the
    argument cannot be anything but `"0.0"` or `"1.0"`, and the raise is what
    keeps it that way — including against a future caller that decides to pass a
    "probability we are fairly confident about".
    """
    for bad in ("0.5", "0", "1", "", "0.0; DROP TABLE futures_outcomes"):
        with pytest.raises(ValueError):
            _price_set(bad)


def test_the_settling_sweep_still_refuses_to_overwrite_a_better_verdict():
    """#5246 adds columns to the SET clause; it must not loosen who is eligible.

    An already-`api_settlement` row is not in `OVERWRITABLE_WINNER_SOURCES_SQL`,
    which is also why the repair script and this producer are independent of
    each other — the fix cannot reach the rows already carrying residue, and the
    repair cannot be undone by the fix.
    """
    from app.utils.resolution_authority import OVERWRITABLE_WINNER_SOURCES_SQL

    assert "api_settlement" not in OVERWRITABLE_WINNER_SOURCES_SQL


# --- CERT-2637: EVERY live Kalshi settlement writer, not the one I read first --


#: Every function that stamps `resolution_source = 'api_settlement'` on a Kalshi
#: outcome, hand-classified 2026-09-11 against the live call graph. The first
#: version of #5246 patched ONE of these — `_resolve_winners_only`, which is
#: retired — and was therefore inert on every path a reader's row travels.
#:
#: Pinned as a set, not a count, so a new settlement writer fails this by NAME
#: rather than by arithmetic somebody has to interpret.
#:
#: 🔴 CERT-2641 WIDENED THIS, AND THE LESSON IS ABOUT THE POPULATION, NOT THE
#: TWO NAMES ADDED. The first census hard-coded its two FILES, so it could only
#: ever police writers in the files I already knew about — and two mounted,
#: executable rails escaped it: the legacy admin endpoint
#: `run_lean_settled` (which also carried CAL-P1004's two-state read, sending
#: `""` and `"scalar"` to the loser list) and the attended
#: `_apply_reviewed_plan`, which restores a venue-confirmed winner to the
#: `api_settlement` rung. "A settlement writer is a population, not a place" was
#: the right sentence attached to the wrong scan: a hand-written FILE list is
#: just a longer place. The file list is DISCOVERED now — see
#: `_discovered_settlement_files` — and only the VERDICT stays hand-classified.
LIVE_KALSHI_SETTLEMENT_WRITERS = {
    "app/tasks/backfill_winners.py": {
        "_backfill_kalshi_winners",
        "_backfill_kalshi_winners_targeted",
        "_backfill_kalshi_winners_via_markets",
        "_resolve_winners_only",
    },
    "app/tasks/kalshi.py": {
        "_backfill_candlestick_snapshots",
        "_backfill_from_settled_events",
        "_create_settled_market",
        # Found by the widened census, not by CERT-2641, and it is the largest
        # of the three: the 2-hourly poll is the bulk writer of Kalshi outcome
        # rows. It grades through `graded_columns`, so the literal
        # `api_settlement` never appears in it and the old scan was blind to it.
        "_poll_kalshi_markets",
    },
    # Mounted admin endpoint, reachable by anyone holding the admin secret. It
    # runs the settled-events scan inline for one series, bypassing Celery.
    "app/routes/admin_data_quality.py": {"run_lean_settled"},
    # Attended repair. Its `restore_winner` branch puts a venue-confirmed winner
    # back on the `api_settlement` rung; the retraction branch moves only
    # `resolution_source` and is not a settlement write.
    "app/tasks/repair_kalshi_fabricated_loss.py": {"_apply_reviewed_plan"},
}

#: Settlement writers in the same files that are NOT Kalshi and are NOT fixed
#: here. Named rather than filtered out, so the census below still SEES them and
#: a Kalshi writer cannot hide by being mistaken for one of these.
#:
#: Polymarket is deliberately a separate ship, on evidence rather than
#: convenience: `polymarket_condition_refresh` grades off `outcomePrices` at
#: `>= 0.95` / `<= 0.05`, so a settled Polymarket leg already carries a
#: near-terminal price rather than a frozen mid-market quote. That is a
#: materially different starting state and wants its own measurement before
#: anything writes a hard 0 or 1 over it. The DATA half of #5246 covers both —
#: the repair clears any `api_settlement` loser on an open market whatever its
#: source — so this gap is forward-only, and it is tracked.
#:
#: CERT-2641's discovery pass added the last two: they are Polymarket writers in
#: files the old census never opened, and they are named here rather than
#: silently skipped so the forward-only gap stays countable.
NON_KALSHI_SETTLEMENT_WRITERS = {
    "app/tasks/backfill_winners.py": {"_backfill_polymarket_winners_from_api"},
    "app/tasks/kalshi.py": set(),
    "app/routes/admin_data_quality.py": set(),
    "app/tasks/repair_kalshi_fabricated_loss.py": set(),
    "app/tasks/polymarket.py": {"_sync_polymarket_resolved_status"},
    "app/tasks/tournament_price_refresh.py": {"_settle_resolved_outcomes"},
}


def _settlement_writers(path):
    """`{function name: source}` for every function writing `api_settlement`.

    Parsed with `ast` rather than grepped so a function is attributed to the
    function it is actually IN — the sites are 3–5 levels of nesting deep inside
    500-line task bodies, and a line-number heuristic mis-attributes them.
    """
    import ast

    with open(path) as fh:  # CodeQL py/file-not-closed
        src = fh.read()
    tree = ast.parse(src)
    lines = src.split("\n")
    # CERT-2641: WRITES only, on the same predicate the file-level discovery
    # uses. The looser "mentions both words" form attributed four admin
    # endpoints that only READ the grade in a WHERE (`debug_winner_backfill`,
    # `debug_settled_precheck`, `debug_phase3`, `calibration_decomposition`) —
    # a census that cannot tell a SET from a WHERE names innocents and buries
    # the writers it exists to find.
    hits = _settlement_write_lines(path)
    funcs = sorted(
        (n.lineno, n.end_lineno, n.name)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    out = {}
    for h in hits:
        enclosing = [f for f in funcs if f[0] <= h <= f[1]]
        if not enclosing:
            continue
        lo, hi, name = enclosing[-1]
        out.setdefault(name, "\n".join(lines[lo - 1 : hi]))
    return out


#: Line shapes that MENTION the grade without writing it. Splitting reads from
#: writes is not fussiness: `resolution_source` appears in a compare-and-swap
#: WHERE all over this codebase, and a census that counted those would report
#: half the task tree as settlement writers and drown the two real ones.
_READ_ONLY_MARKERS = ("!=", "<>", "is distinct", "is not distinct", "==")

#: Helpers that RETURN the `{is_winner, resolution_source}` pair, so the call
#: site writes the grade without the literal `'api_settlement'` ever appearing
#: in it. `graded_columns` is the only one today (`app/utils/
#: kalshi_market_status.py`, returning `VENUE_SETTLEMENT_SOURCE`).
#:
#: 🔴 THIS IS WHY THE PREDICATE NEEDS THEM, and it is a finding about the old
#: census rather than a convenience. `kalshi._create_settled_market` writes the
#: grade exclusively through `graded_columns`, so the only reason the previous
#: scan ever attributed it was a COMMENT four lines up that happens to spell
#: `api_settlement`. The census was carrying a real writer on the strength of
#: prose about it — the same class of mistake as grading the comment that
#: explains a fix, and it would have dropped the writer silently the moment
#: somebody tidied the comment.
_GRADE_WRITE_HELPERS = ("graded_columns(",)


def _docstring_lines(tree):
    """1-indexed line numbers belonging to a docstring.

    Prose that QUOTES the string being searched for is not code. This module's
    own docstrings, and `kalshi_fabricated_loss`'s and
    `polymarket_condition_refresh`'s, all spell
    `resolution_source = 'api_settlement'` while describing the defect — and a
    scan that grades prose reports the explanation as the offence.
    `_task_module_code` strips `#` comments for exactly this reason; `ast` is how
    the same rule reaches a docstring.
    """
    import ast

    out = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                out.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return out


def _settlement_write_lines(path):
    """1-indexed lines in `path` that WRITE `resolution_source='api_settlement'`.

    Accepts the two forms the codebase actually uses — a SQL assignment and a
    Core `.values()` / dict entry — and rejects comparisons and prose.
    """
    import ast

    with open(path) as fh:  # CodeQL py/file-not-closed
        src = fh.read()
    try:
        prose = _docstring_lines(ast.parse(src))
    except SyntaxError:
        return []

    hits = []
    for i, raw in enumerate(src.splitlines(), start=1):
        if i in prose or raw.lstrip().startswith("#"):
            continue
        code = raw.split("  #")[0]
        # A helper's own `def` line is the DEFINITION, not a call site. Without
        # this, `kalshi_market_status.py` — which executes no database write at
        # all — is reported as a settlement writer by virtue of declaring the
        # function every real writer goes through.
        if code.lstrip().startswith(("def ", "async def ")):
            continue
        if any(h in code for h in _GRADE_WRITE_HELPERS):
            hits.append(i)
            continue
        if "api_settlement" not in code or "resolution_source" not in code:
            continue
        low = code.lower()
        if low.lstrip().startswith(("and ", "or ", "where ")):
            continue
        # A `WHERE` to the LEFT of the column makes this a predicate, not an
        # assignment — including the aggregate form that reads nothing like a
        # WHERE clause at a glance:
        #   COUNT(*) FILTER (WHERE fo.resolution_source = 'api_settlement')
        # Two admin dashboards COUNT settled legs that way, and a census that
        # called them writers would demand they carry a terminal price.
        if "where" in low.split("resolution_source")[0]:
            continue
        if any(m in low for m in _READ_ONLY_MARKERS):
            continue
        hits.append(i)
    return hits


def _discovered_settlement_files():
    """Every file under `app/` that writes `resolution_source = 'api_settlement'`.

    🔴 THE BLOCK THIS ANSWERS (CERT-2641). The census used to iterate a
    hand-written list of two FILES, so a writer in any third file was invisible
    to it — and two mounted, executable rails were. A scan whose population is
    enumerated by hand cannot report the thing it was built to report; it can
    only confirm what its author already believed. So the FILES are discovered
    and only the VERDICT is hand-classified.

    Comments are stripped for the reason `_task_module_code` gives: a source
    scan that reads PROSE grades the prose, and this module's own docstrings
    quote the string being searched for.
    """
    import os

    found = set()
    for root, _dirs, files in os.walk("app"):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn).replace(os.sep, "/")
            if _settlement_write_lines(path):
                found.add(path)
    return found


def test_no_settlement_writer_lives_in_a_file_the_census_cannot_see():
    """The census's population is DISCOVERED, so a new file cannot hide in it.

    This is the guard CERT-2641 actually needed. `run_lean_settled` and
    `_apply_reviewed_plan` both stamped `api_settlement` for months while a
    green census reported full compliance, because neither lived in one of the
    two files the census looked at.

    A new file here is not necessarily a bug — it is unclassified. Read it,
    decide whether it is a Kalshi settlement writer, and put it in one of the
    two maps above. Failing loudly on an unclassified file is the entire point:
    the alternative is what shipped, which was passing quietly on an unread one.
    """
    discovered = _discovered_settlement_files()
    classified = set(LIVE_KALSHI_SETTLEMENT_WRITERS) | set(
        NON_KALSHI_SETTLEMENT_WRITERS
    )
    unclassified = discovered - classified
    assert not unclassified, (
        "these files write `resolution_source = 'api_settlement'` and no one "
        f"has classified them: {sorted(unclassified)}. Add each to "
        "LIVE_KALSHI_SETTLEMENT_WRITERS (and it must then carry the terminal "
        "price) or to NON_KALSHI_SETTLEMENT_WRITERS with the reason."
    )


def test_the_census_file_list_is_not_secretly_a_hand_written_list():
    """Negative control on the discovery itself.

    `_discovered_settlement_files` is only worth anything if it actually reads
    the tree. If it silently returned `set()` — a bad cwd, a renamed package, an
    `os.walk` over nothing — then the test above passes vacuously and the census
    is back to being a hand-written list with extra steps (gotcha: an emptiness
    guard its own caller cannot see).
    """
    discovered = _discovered_settlement_files()
    assert len(discovered) >= 4, (
        f"discovery found only {sorted(discovered)} — it is not reading the "
        f"tree, so the guard above cannot fail"
    )
    # And it must find the two rails that escaped the first census, by name.
    assert "app/routes/admin_data_quality.py" in discovered
    assert "app/tasks/repair_kalshi_fabricated_loss.py" in discovered


def test_the_settlement_writer_census_has_not_moved():
    """Positive control. A scan that finds nothing passes the test below.

    If this fails, a Kalshi settlement writer was added, removed or renamed —
    classify it by hand and add it to the set, because the test below can only
    police writers it knows about.
    """
    for path, expected in LIVE_KALSHI_SETTLEMENT_WRITERS.items():
        found = set(_settlement_writers(path))
        assert found == expected | NON_KALSHI_SETTLEMENT_WRITERS[path], path


def test_every_live_kalshi_api_settlement_writer_sets_terminal_price():
    """🔴 THE BLOCK THIS ANSWERS (CERT-2637).

    The first version added the price to the settling UPDATEs in
    `_resolve_winners_only` — which is RETIRED. `_backfill_all_winners` reaches
    `_backfill_kalshi_winners`, `_backfill_kalshi_winners_targeted` and
    `_backfill_kalshi_winners_via_markets`; the four-times-daily
    `kalshi._backfill_from_settled_events` grades on its own schedule; and
    `_create_settled_market` mints already-graded rows. Every one of them stamped
    `api_settlement` and left the price behind, so the ship was inert where it
    mattered — and worse than inert once the price-refresh refusal landed, since
    that made the residue those paths keep creating permanently unreachable.

    A settlement writer is a POPULATION, not a place. This asserts over the
    population.
    """
    for path, names in LIVE_KALSHI_SETTLEMENT_WRITERS.items():
        writers = _settlement_writers(path)
        for name in names:
            body = writers[name]
            # Three legal routes, and the FIRST TWO ARE THE POINT. A raw
            # `text()` UPDATE splices `settled_price_set_sql`, a Core update
            # splats `settled_price_values`; both guarantee all three columns by
            # construction, and neither leaves the literal column names in the
            # source for a scan to find. The third — spelling the columns out —
            # is only reachable where the price depends on a bind param the
            # helper cannot see (`kalshi._backfill_candlestick_snapshots`), and
            # it is held to naming all three.
            via_helper = (
                "settled_price_set_sql(" in body or "settled_price_values(" in body
            )
            spelled_out = all(
                col in body
                for col in ("current_probability",
                            "current_american_odds",
                            "price_changed_at")
            )
            assert via_helper or spelled_out, (
                f"{path}::{name} stamps api_settlement without writing a "
                f"terminal price — the leg keeps the last number anyone paid "
                f"for a contract that is over, and no poll can ever correct it"
            )
            assert "price_changed_at" in body or via_helper, (
                f"{path}::{name} moves the price without the #2024 change stamp"
            )


#: The writers CERT-2641 found outside the first census, and what each owes.
#: `prices_both_sides` is False for a writer that only ever writes one verdict:
#: `_apply_reviewed_plan`'s restore branch puts back a WINNER and never a loser,
#: so demanding a NO price there would be demanding a branch that must not exist.
_REACHABLE_WRITERS = [
    ("app/routes/admin_data_quality.py", "run_lean_settled", True, True),
    ("app/tasks/repair_kalshi_fabricated_loss.py", "_apply_reviewed_plan",
     False, False),
]


@pytest.mark.parametrize(
    "path,name,prices_both_sides,partitions_results", _REACHABLE_WRITERS
)
def test_every_reachable_kalshi_api_settlement_writer_sets_terminal_price_and_refuses_undeclared_results(
    path, name, prices_both_sides, partitions_results
):
    """🔴 THE BLOCK THIS ANSWERS (CERT-2641), on the two rails it named.

    Both are REACHABLE and neither is scheduled, which is exactly why they were
    missed: `run_lean_settled` is a mounted admin POST that runs the settled
    scan inline for one series, and `_apply_reviewed_plan` is the attended
    fabricated-loss repair. Between them they stamped `api_settlement` without a
    terminal price, and the admin one also carried CAL-P1004's two-state read,
    so `""` (the venue has not called it) and `"scalar"` (settles on a number)
    were written as LOSSES onto the rung `is_downgrade` protects.

    Asserted on the writer's own source rather than a re-derivation, and on the
    SET clause rather than the whole statement: `is_winner` legitimately appears
    in a compare-and-swap WHERE, so a whole-statement check would pass on a
    mutant that moved a column into the SET.
    """
    body = _settlement_writers(path)[name]

    # 🔴 THE CALL FORM, NOT THE BARE NAME. `run_lean_settled` imports
    # `SETTLED_YES_PRICE`, `SETTLED_NO_PRICE` and `settled_price_set_sql` INSIDE
    # the function, so all three names are in its body text no matter what it
    # does with them. A mutant that deleted the YES price clause outright left
    # every bare-name assertion green — the import alone satisfied them. Asked
    # as calls, with the price named in the argument, the two SET clauses are
    # the only thing that can answer.
    def _asks(price_const):
        return re.search(
            r"settled_price_set_sql\(\s*" + price_const + r"\b", body
        ) or re.search(r"settled_price_values\(", body)

    assert _asks("SETTLED_YES_PRICE"), (
        f"{path}::{name} stamps api_settlement without asking the SHARED clause "
        f"for the winner's price. A settled leg keeps the last number anyone "
        f"paid, and the ship's own price-refresh refusal then makes it "
        f"permanently unreachable."
    )
    if prices_both_sides:
        assert re.search(
            r"settled_price_set_sql\(\s*SETTLED_NO_PRICE\b", body
        ), (
            f"{path}::{name} writes is_winner=false somewhere and prices only "
            f"the winners — that is #5246's residue, re-created by half a fix"
        )

    if partitions_results:
        # The undeclared refusal, at the writer that had the two-state read.
        assert "gradeable_winner(" in body, (
            f"{path}::{name} decides a verdict without the three-state helper, "
            f"so an undeclared or scalar result becomes a recorded LOSS"
        )
        assert 'result") == "yes"' not in body and "== 'yes'" not in body, (
            f"{path}::{name} still compares the venue's result to the literal "
            f'"yes" — that is the CAL-P1004 partition the helper replaced'
        )


def test_the_polls_settled_price_is_actually_applied_not_merely_computed():
    """🔴 A SOURCE SCAN PROVES THE TEXT IS THERE, NOT THAT IT RUNS.

    This test exists because its absence let a mutant through. The census above
    accepts `_poll_kalshi_markets` on the strength of the string
    `settled_price_values(` appearing in its body — and that string sits on the
    line that COMPUTES the price. Changing the branch that APPLIES it to
    `if False:` left every population assertion green: the computation stayed,
    the write reverted, and the leg went back to carrying a live quote.

    So this binds the STRUCTURE, with `ast`, not the text: the terminal price
    must be applied inside a branch conditioned on `settled_price`, and it must
    reach both arms of the upsert — the conflict arm through
    `update_set.update(settled_price)` and the INSERT arm through
    `settled_price.get(...)`, which is the arm that decides what a row is BORN
    holding.
    """
    import ast

    with open("app/tasks/kalshi.py") as fh:  # CodeQL py/file-not-closed
        tree = ast.parse(fh.read())

    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_poll_kalshi_markets"
    )

    guarded = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.If)
        and isinstance(n.test, ast.Name)
        and n.test.id == "settled_price"
    ]
    assert guarded, (
        "no `if settled_price:` branch in _poll_kalshi_markets — the terminal "
        "price is computed and never applied, so a settled leg keeps the last "
        "quote the poll derived"
    )

    applied = ast.dump(ast.Module(body=guarded, type_ignores=[]))
    assert "update_set" in applied and "settled_price" in applied, (
        "the settled branch does not write the price into `update_set`"
    )
    assert "price_changed_at" in applied, (
        "the settled branch moves the price without re-stamping #2024 against "
        "the terminal value"
    )

    # The INSERT arm: what a row is born holding.
    insert_kwargs = [
        kw
        for call in ast.walk(fn)
        if isinstance(call, ast.Call)
        for kw in call.keywords
        if kw.arg == "current_probability"
    ]
    assert insert_kwargs, "no `current_probability=` in the upsert"
    assert any(
        "settled_price" in ast.dump(kw.value) for kw in insert_kwargs
    ), (
        "the INSERT arm still names the live quote unconditionally, so a leg "
        "already settled the first time the poll sees it is BORN with a price "
        "for a contract that is over"
    )


def test_the_undeclared_result_never_becomes_a_loss_at_the_admin_writer():
    """The refusal is a PROPERTY of the helper, exercised on the real values.

    The source assertions above prove the admin endpoint calls
    `gradeable_winner`; this proves what that call does with the four results
    the block enumerated, so the pair cannot both be satisfied by a helper that
    stopped refusing.
    """
    from app.utils.kalshi_market_status import gradeable_winner

    assert gradeable_winner("finalized", "yes") is True
    assert gradeable_winner("finalized", "no") is False
    # Neither list. Not a loss.
    assert gradeable_winner("finalized", "") is None
    assert gradeable_winner("finalized", "scalar") is None
    assert gradeable_winner("closed", "") is None
    assert gradeable_winner("active", "") is None


#: Writers that never read a venue result and never write a loss, because their
#: verdicts arrive already decided in a plan an operator has read and bound
#: (`bind_apply`). Exempting them from the two population assertions below is a
#: STATEMENT ABOUT THEIR SHAPE, not a softening: demanding a NO branch of
#: `_apply_reviewed_plan` would be demanding a branch that must not exist —
#: its whole purpose is restoring winners a fabricated loss took away. The
#: property that keeps them safe is asserted directly in
#: `test_a_plan_bound_writer_is_bound_to_a_reviewed_plan`.
PLAN_BOUND_WRITERS = {
    ("app/tasks/repair_kalshi_fabricated_loss.py", "_apply_reviewed_plan"),
}


def test_a_plan_bound_writer_is_bound_to_a_reviewed_plan():
    """The exemption above must buy its own safety, not just skip the check.

    A writer excused from the venue-result partition is only safe if something
    else decides its verdicts. For `_apply_reviewed_plan` that is `bind_apply`,
    which refuses any apply not bound to the dry-run an operator actually read,
    plus the compare-and-swap on the exact prior `(is_winner,
    resolution_source)` the plan recorded.
    """
    for path, name in PLAN_BOUND_WRITERS:
        body = _settlement_writers(path)[name]
        assert "bind_apply(" in body, (
            f"{path}::{name} is exempt from the venue-result partition but is "
            f"not bound to a reviewed plan either — nothing decides its verdicts"
        )
        assert "restore_winner" in body, (
            f"{path}::{name} is exempt from the NO-side price on the grounds "
            f"that it only restores winners; that branch is no longer there"
        )
        # The exemption is only legitimate while the writer really never writes
        # a loss onto the settlement rung.
        assert "is_winner = false" not in body and "is_winner=false" not in body


def test_both_sides_of_every_settlement_are_priced():
    """YES and NO, in every writer that spells the two branches separately.

    A writer that priced only the winners would leave exactly #5246's
    population — the eliminated field — untouched, which is the whole defect.
    """
    for path, names in LIVE_KALSHI_SETTLEMENT_WRITERS.items():
        for name, body in _settlement_writers(path).items():
            if name not in names or (path, name) in PLAN_BOUND_WRITERS:
                continue
            if "is_winner = true" in body or "is_winner=true" in body:
                assert "SETTLED_YES_PRICE" in body or "1.0" in body, f"{path}::{name}"
            if "is_winner = false" in body or "is_winner=false" in body:
                assert "SETTLED_NO_PRICE" in body or "0.0" in body, f"{path}::{name}"
            # A writer that spells one branch and not the other is the exact
            # half-fix this cert blocked: pricing winners while the eliminated
            # field — #5246's whole population — keeps its residue.
            if "SETTLED_YES_PRICE" in body:
                assert "SETTLED_NO_PRICE" in body, f"{path}::{name}: YES only"


def test_the_undeclared_refusal_survives_the_price_write():
    """Pricing a settlement must not start pricing a NON-settlement.

    `gradeable_winner` returns None for `result=""` and `result="scalar"`, and
    every writer must still skip those rather than zero their price on a grade
    the venue never gave. This is the interaction that made CAL-P1004 worth
    fixing in the same ship rather than filing.
    """
    from app.utils import kalshi_market_status as kms

    assert kms.gradeable_winner("finalized", "scalar") is None
    assert kms.gradeable_winner("active", "") is None
    for path in LIVE_KALSHI_SETTLEMENT_WRITERS:
        writers = _settlement_writers(path)
        for name in LIVE_KALSHI_SETTLEMENT_WRITERS[path]:
            if (path, name) in PLAN_BOUND_WRITERS:
                continue  # reads no venue result; see PLAN_BOUND_WRITERS
            body = writers[name]
            # Either the writer asks the three-state helper itself, or its
            # caller has already partitioned on it and the writer only ever
            # receives a decided list.
            assert (
                "gradeable_winner" in body
                or "graded_columns" in body
                or "yes_tickers" in body
                or "yes_t" in body
            ), f"{path}::{name} reaches a grade with no three-state route"


# --- the durability guard: a graded leg is not a quotable leg ----------------


def test_the_price_poll_refuses_a_leg_the_venue_resolved_no():
    """The settled refusal tests the GRADE as well as the CROWN.

    Before #5246 this predicate was `is_winner IS NOT TRUE` alone, which is a
    test for a crown: a leg the venue resolved NO carries `is_winner = FALSE`
    and passed it. Nothing had re-priced one only because Kalshi returns
    `yes_bid: null, yes_ask: null, last_price: null` on a `finalized` market —
    the venue's grace, not our guard.
    """
    from app.tasks.futures_price_refresh import ELIGIBLE_OUTCOMES_SQL

    assert "is_winner IS NOT TRUE" in ELIGIBLE_OUTCOMES_SQL
    assert "resolution_source IS DISTINCT FROM 'api_settlement'" in ELIGIBLE_OUTCOMES_SQL


def test_the_refusal_is_tri_state_safe_and_not_a_plain_inequality():
    """`IS DISTINCT FROM`, never `!=`.

    `resolution_source` is nullable and an ungraded outcome holds NULL.
    `resolution_source != 'api_settlement'` evaluates to NULL for those rows —
    falsy — so the plain inequality would make EVERY ungraded outcome ineligible
    and the poller would write nothing at all, for every market, permanently.
    That is #2199's failure mode inverted: the same predicate's `is_winner` leg
    carries the same warning for the same reason.
    """
    from app.tasks.futures_price_refresh import ELIGIBLE_OUTCOMES_SQL

    assert "!=" not in ELIGIBLE_OUTCOMES_SQL
    assert "<>" not in ELIGIBLE_OUTCOMES_SQL


def test_the_refusal_does_not_reach_the_revisable_grades():
    """Only the venue's own settlement is refused, not every non-NULL source.

    Most `resolution_source` values are inferences the system is allowed to
    revise, and a live quote is better evidence than a guess. Widening this to
    `resolution_source IS NOT NULL` would freeze the price of every row a
    guessing pass has ever touched — 71,050 `pass2_loser` rows and 42,517
    `pass2_guess` rows on production alone.
    """
    from app.tasks.futures_price_refresh import ELIGIBLE_OUTCOMES_SQL

    assert "resolution_source IS NOT NULL" not in ELIGIBLE_OUTCOMES_SQL
    for revisable in ("pass2_guess", "multi_max_prob", "binary_higher_wins",
                      "box_score", "game_score", "clean_resolution"):
        assert revisable not in ELIGIBLE_OUTCOMES_SQL


# --- the repair: what it clears, and what it refuses to clear ----------------


def _leg(market_id, outcome_id, survives, residue=0.01):
    return {
        "market_id": market_id,
        "outcome_id": outcome_id,
        "outcome_name": f"player {outcome_id}",
        "residue": residue,
        "live_field_survives": survives,
    }


def test_the_repair_clears_a_market_that_still_has_a_live_field():
    """The US Open shape: 44 dead legs beside four live ones."""
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import plan

    rows = [_leg(34277822, i, True) for i in range(44)]
    clear, refuse = plan(rows)
    assert len(clear) == 44
    assert refuse == []


def test_the_repair_refuses_to_blank_a_card():
    """Where no live priced leg survives, zeroing every candidate is refused.

    An open market whose entire field has been graded a loser is a different
    defect — its status is wrong — and replacing a wrong card with an all-zero
    card would hide it. This clause refuses 4,613 of 11,740 production
    candidates across 1,139 markets, so it is not decoration.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import plan

    rows = [_leg(999, i, False) for i in range(6)]
    clear, refuse = plan(rows)
    assert clear == []
    assert len(refuse) == 6


def test_the_refusal_is_decided_per_market_not_per_leg():
    """One market's verdict never leaks into another's, and never splits.

    The question — *does a live priced field survive here?* — is a property of
    the MARKET. A per-leg answer would clear a market's legs one at a time and
    blank the card on the last one, which is the exact outcome the refusal
    exists to prevent.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import plan

    rows = [_leg(1, 10, True), _leg(2, 20, False), _leg(1, 11, True),
            _leg(2, 21, False)]
    clear, refuse = plan(rows)
    assert {leg["outcome_id"] for leg in clear} == {10, 11}
    assert {leg["outcome_id"] for leg in refuse} == {20, 21}


def test_a_market_whose_legs_disagree_fails_closed():
    """Disagreement within a market refuses the market, it does not clear it.

    The scan's `EXISTS` is keyed on `market_id` alone, so no production row can
    reach this today — which is precisely why it is worth pinning. Reading the
    first leg's answer instead of requiring all of them would let a future
    per-leg scan clear a whole market off one row, silently, in the one function
    whose job is to refuse.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import plan

    clear, refuse = plan([_leg(7, 70, True), _leg(7, 71, False)])
    assert clear == []
    assert {leg["outcome_id"] for leg in refuse} == {70, 71}


def test_an_empty_reconciliation_is_not_a_clean_backup():
    """gotcha #53: `all()` over an empty mapping is True.

    Without the emptiness test, a reconciliation that inspected nothing — the
    first run, before the backup table exists — reads as a clean pass and
    `--apply` proceeds with no undo.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        backup_is_exact,
    )

    assert backup_is_exact({}) is False
    assert backup_is_exact({"futures_outcomes": 1}) is False
    assert backup_is_exact({"futures_outcomes": 0}) is True


def test_a_small_plan_names_which_of_its_two_causes_happened():
    """A sanity floor that names two causes needs a discriminator, not an override.

    "The filter broke" and "the job is already done" both present as a plan
    below the floor, and `--allow-small` would let the first through wearing the
    second's clothes. The manifest is the discriminator: only a successful
    forward write puts a row in it.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        SANITY_FLOOR,
        explain_small_plan,
    )

    assert explain_small_plan(SANITY_FLOOR, 0).message == ""
    assert "ALREADY APPLIED" in explain_small_plan(10, SANITY_FLOOR).message
    assert "FILTER BROKE" in explain_small_plan(10, 10).message


def test_the_discriminator_decides_the_write_and_not_only_the_wording():
    """The half of the floor rule that was decorative for two sessions.

    The test above asserted only on the MESSAGE, so it passed against a function
    whose two branches refused `--apply` identically — the discriminator changed
    the wording of the refusal and nothing else. That is the one-sided shape: it
    proves the diagnosis is computed, never that the diagnosis is USED. It cost
    the #5246 re-drain a session, on the exact branch the design was written to
    let through.

    So assert the two causes DIVERGE, and assert it on the field the caller
    branches on:

      * `FILTER BROKE`     -> blocks (the cause the floor exists for)
      * `ALREADY APPLIED`  -> does NOT block (a drained backlog is a done job)
      * plan above floor   -> does NOT block, and says nothing

    A guard that refuses everything passes every one-sided test, so this one
    pins both sides.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        SANITY_FLOOR,
        explain_small_plan,
    )

    broke = explain_small_plan(10, 10)
    drained = explain_small_plan(10, SANITY_FLOOR)
    big = explain_small_plan(SANITY_FLOOR, 0)

    assert broke.blocks_apply is True
    assert drained.blocks_apply is False
    assert big.blocks_apply is False

    # The two small-plan causes must not agree — that agreement WAS the bug.
    assert broke.blocks_apply != drained.blocks_apply

    # A drained backlog still explains itself; silence would hide a real state.
    assert drained.message
    assert big.message == ""


def test_the_boundary_of_the_drained_backlog_branch_is_the_floor_itself():
    """Pin the threshold from BOTH sides, or a tuned constant is unguarded.

    `manifest + plan >= SANITY_FLOOR` is the whole discriminator, so a mutation
    to `>` or to `SANITY_FLOOR + 1` must be caught. One row either side of the
    boundary flips the verdict, and this asserts both.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        SANITY_FLOOR,
        explain_small_plan,
    )

    plan = 10
    exactly_at = explain_small_plan(plan, SANITY_FLOOR - plan)
    one_short = explain_small_plan(plan, SANITY_FLOOR - plan - 1)

    assert exactly_at.blocks_apply is False
    assert "ALREADY APPLIED" in exactly_at.message
    assert one_short.blocks_apply is True
    assert "FILTER BROKE" in one_short.message


def test_apply_is_refused_on_a_broken_filter_and_reached_on_a_drained_backlog():
    """The caller's branch, read from the source it actually runs.

    The two tests above bind the verdict; this binds the ONE line that consumes
    it. `if small:` (the old form) is truthy for both causes; `if
    small.blocks_apply:` is the fix. A source-scan proves the text is present,
    not that it runs — so this is deliberately narrow: it asserts the refusal is
    keyed on the field, and that the bare-truthiness form is gone.
    """
    import inspect

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    src = inspect.getsource(mod.run)

    assert "if small.blocks_apply:" in src, (
        "the apply refusal must branch on the discriminator's verdict"
    )
    assert "if small:" not in src, (
        "bare truthiness refuses BOTH causes — that was the defect"
    )
    # The explanation is still printed for every small plan, blocking or not.
    assert "if small.message:" in src


def _drive_apply(monkeypatch, *, plan_count, manifest_rows):
    """Run `run()` under `--backup --apply` against a fake session.

    Returns the list of SQL strings the run actually executed, so the caller
    asks "did the forward write happen", not "does the source say it would".

    Everything the run touches EXCEPT the branch under test is stubbed: the
    cohort scan, the manifest count, the backup and its reconciliation. That is
    deliberate — the subject is the one `if`, and a stub that also decided the
    outcome would make the test vacuous in the way the file's own docstring
    warns about. `plan` is stubbed to a fixed size so both cases below present
    an IDENTICALLY small plan and differ only in the discriminator's input.
    """
    import asyncio
    from contextlib import asynccontextmanager

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    executed: list[str] = []

    class _Result:
        rowcount = 1

        @staticmethod
        def fetchall():
            return []

    class _Session:
        async def execute(self, stmt, params=None):
            executed.append(str(stmt))
            return _Result()

        async def commit(self):
            executed.append("COMMIT")

    @asynccontextmanager
    async def _fake_session():
        yield _Session()

    legs = [
        {"outcome_id": i, "market_id": 1, "residue": 0.01}
        for i in range(plan_count)
    ]

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    monkeypatch.setattr(mod, "plan", lambda rows: (legs, []))
    monkeypatch.setattr(mod, "manifest_count", _async_const(manifest_rows))
    monkeypatch.setattr(mod, "backup", _async_const(None))
    # The venue precondition (#5515) is stubbed WIDE OPEN here so it cannot be
    # what stops the write in either branch below — the subject of these tests
    # is the sanity floor's discriminator, and a second gate that also refused
    # would make them pass for the wrong reason. The precondition's own
    # behaviour is driven separately by `_drive_apply_with_venue`.
    monkeypatch.setattr(mod, "attach_venue_coordinates", _async_const(None))
    monkeypatch.setattr(
        mod,
        "confirm_against_venue",
        _async_const((legs, [], collections.Counter())),
    )
    # `backup_is_exact` requires a non-empty dict of zeros, so the backup gate
    # PASSES and cannot be what stops the write in either case below.
    monkeypatch.setattr(mod, "reconcile_backup", _async_const({"missing": 0}))

    class _Args:
        limit = None
        backup = True
        apply = True

    asyncio.run(mod.run(_Args()))
    return executed


def _async_const(value):
    async def _f(*a, **kw):
        return value

    return _f


def test_the_floors_two_causes_reach_opposite_WRITE_outcomes_when_actually_run():
    """The same small plan writes on one cause and refuses on the other.

    THIS IS THE TEST THE SOURCE SCAN ABOVE CANNOT BE. `inspect.getsource` proves
    `if small.blocks_apply:` is present in the text; it cannot prove the run
    reaches it, that the backup gate above it does not return first, or that the
    non-blocking cause gets all the way to the UPDATE. The defect it is guarding
    (#5452) was exactly a discriminator that computed the right answer and did
    not change what the caller DID — a shape a text assertion is structurally
    blind to.

    So both cases below present a plan of the SAME size, far under the floor,
    and differ in one input: how many rows the manifest already holds. That is
    the discriminator, and nothing else varies.
    """
    import pytest

    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        SANITY_FLOOR,
        SQL,
    )

    plan_count = 5
    mp = pytest.MonkeyPatch()

    # DRAINED BACKLOG: manifest + plan clears the floor -> the write proceeds.
    try:
        drained = _drive_apply(
            mp, plan_count=plan_count, manifest_rows=SANITY_FLOOR - plan_count
        )
    finally:
        mp.undo()

    # FILTER BROKE: one row short of the floor -> the write is refused.
    mp = pytest.MonkeyPatch()
    try:
        broken = _drive_apply(
            mp, plan_count=plan_count, manifest_rows=SANITY_FLOOR - plan_count - 1
        )
    finally:
        mp.undo()

    clear_sql = SQL["clear"]

    assert sum(s == clear_sql for s in drained) == plan_count, (
        "a drained backlog is the branch the floor was BUILT to allow: every "
        "planned row must be cleared"
    )
    assert "COMMIT" in drained

    assert not any(s == clear_sql for s in broken), (
        "a broken filter must not write a single row"
    )
    assert "COMMIT" not in broken

    # The two runs must genuinely DIVERGE. Asserting only the refusal would pass
    # against a run that refuses both — which is the #5452 defect exactly.
    assert drained != broken


def test_the_repair_writes_only_the_price_columns():
    """No verdict moves, and no calibration input moves.

    The grade is already correct — this repair stops the price contradicting it.
    `opening_probability` and `calibration_probability` are the curve's inputs
    (gotcha #144) and `last_updated` is the poll-touch clock three surfaces read
    as liveness; none of them belong to a script that reads no venue price.

    The assertion is made against the SET clause alone. `is_winner` and
    `resolution_source` DO appear in the statement — in the WHERE, as the
    compare-and-swap premise — and a whole-statement substring test would
    either fail on that or, written the other way, pass on a mutant that moved
    a column from the WHERE into the SET.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import SQL

    clear = SQL["clear"]
    set_clause, where_clause = clear.split("WHERE", 1)
    assert "current_probability = 0" in set_clause
    assert "current_american_odds = NULL" in set_clause
    assert "price_changed_at = NOW()" in set_clause
    for untouched in ("opening_probability", "calibration_probability",
                      "last_updated", "is_winner", "resolution_source"):
        assert untouched not in set_clause, f"{untouched} must not be written"
    # ...and the grade columns are still READ, which is the next test's subject.
    assert "is_winner" in where_clause


def test_the_forward_write_is_a_compare_and_swap_on_its_own_premise():
    """If the row moved between the plan and the write, the write no-ops.

    The plan is a snapshot and the apply loop is a network round trip per row.
    Re-asserting every clause of the premise in the UPDATE means a row that has
    since been re-graded, re-priced or already cleared is declined rather than
    overwritten with a zero — which is why a decline is reported as the good
    case rather than an error.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import (
        RESIDUE_FLOOR,
        SETTLED_SOURCE,
        SQL,
    )

    clear = SQL["clear"]
    assert "WHERE id = :oid" in clear
    assert "is_winner = false" in clear
    assert f"resolution_source = '{SETTLED_SOURCE}'" in clear
    assert f"current_probability > {RESIDUE_FLOOR}" in clear


def test_the_repair_stays_inside_open_markets():
    """Scope stops where the defect stops.

    963,492 markets are `resolved` and are not rendered as live winner cards;
    51,762 are `open` and are. A repair that widened to the resolved side would
    rewrite a million terminal prices to buy no reader anything.
    """
    from scripts.repair_5246_settled_outcomes_still_carrying_a_price import SQL

    assert "status = 'open'" in SQL["scan"]


# --- CAL-P1004, found from #5246: an undeclared market is not a loss ---------


def test_the_settled_sweep_grades_through_the_three_state_helper():
    """The settled-events sweep asks `gradeable_winner`, not `rs == "yes"`.

    This was the last of this file's four Kalshi graders still carrying the
    two-state form, and it escaped `test_kalshi_forward_capture_grade_p1004`'s
    scan on a NAME — that pattern is `result\\w* == "yes"` and the local here was
    called `rs`. Pinned by behaviour rather than by that pattern so the next
    rename cannot slip through the same gap.
    """
    src = _task_module_code()
    assert 'rs == "yes"' not in src
    assert 'rs is not None' not in src
    assert "kms.gradeable_winner(" in src
    # The skip is COUNTED, not silent — gotcha #53.
    assert 'settled_stats["undeclared"] += 1' in src


@pytest.mark.parametrize(
    "status,result,expected",
    [
        ("finalized", "yes", True),
        ("finalized", "no", False),
        ("determined", "yes", True),
        # The two that used to be graded as LOSSES at the top authority rung.
        ("finalized", "scalar", None),
        ("closed", "", None),
        ("active", "", None),
        ("inactive", "", None),
        # A stray result on a status the measured table says carries none.
        ("closed", "yes", None),
    ],
)
def test_only_a_declared_result_reaches_a_verdict(status, result, expected):
    """`""` and `"scalar"` are absences, and an absence is not a loss.

    Measured on CAL-P053's sample, `scalar` was 39 of 204 results — roughly one
    settled market in five. Every one of them was recorded as "this outcome
    lost". #5246 made that worse before it made it better: the sweep now writes
    `current_probability = 0` beside the verdict, so an undeclared market would
    have had its price zeroed on a grade the venue never gave.
    """
    from app.utils import kalshi_market_status as kms

    assert kms.gradeable_winner(status, result) is expected


# ---------------------------------------------------------------------------
# #5515 — the venue-agreement precondition.
#
# The repair's own docstring used to assert "the grade is already right". On
# 2026-09-10 #3617's producer began stamping `api_settlement` losses onto legs
# Kalshi still lists `active`, and on 2026-09-11 this repair zeroed 167 of them
# on screen — the FTSE 100 ladder's "At least £10,900" rung rendered 0% while
# stored at 0.995 and trading at the venue. These tests bind the premise to the
# venue instead of to the docstring.
# ---------------------------------------------------------------------------


def _venue_leg(**over):
    """A leg that satisfies every PRE-venue clause, so only the venue can refuse it."""
    leg = {
        "outcome_id": 198634385,
        "market_id": 52755923,
        "outcome_name": "At least £10,900",
        "outcome_ticker": "KXFTSE-26DEC31-10900",
        "residue": 0.995,
        "live_field_survives": True,
        "source": "kalshi",
        "event_ticker": "KXFTSE-26DEC31",
    }
    leg.update(over)
    return leg


def _book(status, result, ticker="KXFTSE-26DEC31-10900"):
    return {ticker: {"ticker": ticker, "status": status, "result": result}}


def test_a_leg_the_venue_still_lists_active_is_refused():
    """THE REGRESSION, in the shape production actually served.

    `KXFTSE-26DEC31-10900` on 2026-09-12: stored `is_winner = false,
    resolution_source = 'api_settlement'`, priced 0.995, on an `open` market
    resolving 2027-01-01 whose siblings are priced — so it passes the cohort
    SQL and the sibling refusal together, and the venue reports it `active`
    with an empty result. Nothing except the venue can stop this row.
    """
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    call = mod.venue_verdict(_venue_leg(), _book("active", ""))

    assert call.verdict == mod.VENUE_REFUTES
    assert "active" in call.reason


def test_a_venue_confirmed_loss_is_the_one_shape_that_clears():
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    call = mod.venue_verdict(_venue_leg(), _book("finalized", "no"))

    assert call.verdict == mod.VENUE_AGREES


def test_an_inverted_grade_is_refused_rather_than_priced_to_zero():
    """The venue says this side WON and the row says it lost.

    lane1b/179 found one of these in 619 venue-checked rows. Zeroing its price
    would make a wrong verdict look settled, which is worse than the residue
    the repair exists to clear.
    """
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    call = mod.venue_verdict(_venue_leg(), _book("finalized", "yes"))

    assert call.verdict == mod.VENUE_REFUTES
    assert "yes" in call.reason


@pytest.mark.parametrize(
    "status,result",
    [("finalized", ""), ("finalized", "void"), ("closed", ""), ("initialized", "")],
)
def test_every_shape_short_of_a_declared_loss_refuses(status, result):
    """Fail-closed: AGREES is reachable only by the one positive statement."""
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    assert mod.venue_verdict(
        _venue_leg(), _book(status, result)
    ).verdict != mod.VENUE_AGREES


def test_an_unreadable_event_refuses_instead_of_clearing():
    """A transport failure must never read as licence to write (gotcha #36)."""
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    call = mod.venue_verdict(_venue_leg(), None)

    assert call.verdict == mod.VENUE_UNKNOWN
    assert call.reason == "event_unreadable"


def test_a_leg_absent_from_the_venues_book_is_refused():
    """8 rows stored, 7 markets served — the FTSE event's real shape."""
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    call = mod.venue_verdict(_venue_leg(), _book("finalized", "no", "SOMETHING-ELSE"))

    assert call.verdict == mod.VENUE_UNKNOWN
    assert call.reason == "leg_absent_from_book"


def test_a_source_with_no_venue_reader_is_refused_and_says_so():
    """Polymarket has no reader here, so its rows are named, not trusted."""
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    call = mod.venue_verdict(
        _venue_leg(source="polymarket"), _book("finalized", "no")
    )

    assert call.verdict == mod.VENUE_UNKNOWN
    assert "polymarket" in call.reason


def test_a_leg_whose_market_vanished_from_the_lookup_fails_closed():
    """`attach_venue_coordinates` leaving `source` unset must not widen the write."""
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    call = mod.venue_verdict(
        _venue_leg(source=None, event_ticker=None), _book("finalized", "no")
    )

    assert call.verdict == mod.VENUE_UNKNOWN


def test_the_split_counts_every_refusal_by_reason():
    """The operator must see WHY a plan shrank, not merely that it did."""
    import asyncio

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    legs = [
        _venue_leg(outcome_id=1, outcome_ticker="T-LOST"),
        _venue_leg(outcome_id=2, outcome_ticker="T-LIVE"),
        _venue_leg(outcome_id=3, source="polymarket"),
    ]
    book = {
        "T-LOST": {"ticker": "T-LOST", "status": "finalized", "result": "no"},
        "T-LIVE": {"ticker": "T-LIVE", "status": "active", "result": ""},
    }

    async def _reader(tickers):
        return {"KXFTSE-26DEC31": mod.VenueRead(book, "")}

    confirmed, refused, reasons = asyncio.run(
        mod.confirm_against_venue(legs, reader=_reader)
    )

    assert [leg["outcome_id"] for leg in confirmed] == [1]
    assert len(refused) == 2
    assert reasons["venue_status:active"] == 1
    assert reasons["no_venue_reader:polymarket"] == 1


def test_the_reader_is_never_asked_about_a_source_it_cannot_read():
    """A polymarket-only plan makes no Kalshi calls at all."""
    import asyncio

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    asked = []

    async def _reader(tickers):
        asked.append(tickers)
        return {}

    confirmed, refused, _ = asyncio.run(
        mod.confirm_against_venue(
            [_venue_leg(source="polymarket")], reader=_reader
        )
    )

    assert asked == []
    assert confirmed == [] and len(refused) == 1


def _drive_apply_with_venue(monkeypatch, legs, book):
    """Run `run()` under `--backup --apply` with the REAL venue precondition.

    Only the network is stubbed. `attach_venue_coordinates`,
    `confirm_against_venue`, `venue_verdict` and the gating in `run` are all the
    shipped ones, so this answers the question the source cannot: did the
    verdict reach the write, or merely get computed near it.

    Returns the outcome ids the forward write was actually executed for.
    """
    import asyncio
    from contextlib import asynccontextmanager

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    written: list[int] = []

    class _Result:
        rowcount = 1

        @staticmethod
        def fetchall():
            return []

    class _Session:
        async def execute(self, stmt, params=None):
            sql = str(stmt)
            if "UPDATE futures_outcomes" in sql and params and "oid" in params:
                written.append(params["oid"])
            return _Result()

        async def commit(self):
            return None

    @asynccontextmanager
    async def _fake_session():
        yield _Session()

    async def _reader(tickers):
        return {t: mod.VenueRead(book, "http_404" if book is None else "")
                for t in tickers}

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    monkeypatch.setattr(mod, "plan", lambda rows: (legs, []))
    monkeypatch.setattr(mod, "manifest_count", _async_const(mod.SANITY_FLOOR))
    monkeypatch.setattr(mod, "backup", _async_const(None))
    monkeypatch.setattr(mod, "reconcile_backup", _async_const({"missing": 0}))
    # The coordinates are stamped by the fixture, not read from the DB — the
    # subject is the verdict's effect on the write, not the lookup.
    monkeypatch.setattr(mod, "attach_venue_coordinates", _async_const(None))
    monkeypatch.setattr(
        mod, "_read_books", _reader
    )

    class _Args:
        limit = None
        backup = True
        apply = True

    asyncio.run(mod.run(_Args()))
    return written


def test_the_venue_verdict_reaches_the_write_and_does_not_merely_get_computed(
    monkeypatch,
):
    """THE MUTANT THIS KILLS: the check relocated after the write loop, or ignored.

    Two legs identical in every stored respect — same market, same grade, same
    residue, both past the sibling refusal, both on a plan well clear of the
    sanity floor. They differ only in what the venue says. If the precondition
    is computed but not gating, or runs after the loop, BOTH are written and
    this fails; that is exactly how #5452's discriminator was decorative for two
    sessions, and how `explain_small_plan`'s was before it.
    """
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    lost = _venue_leg(outcome_id=111, outcome_ticker="T-LOST")
    live = _venue_leg(outcome_id=222, outcome_ticker="T-LIVE")
    book = {
        "T-LOST": {"ticker": "T-LOST", "status": "finalized", "result": "no"},
        "T-LIVE": {"ticker": "T-LIVE", "status": "active", "result": ""},
    }

    written = _drive_apply_with_venue(monkeypatch, [lost, live], book)

    assert written == [111], (
        f"the venue-refuted leg 222 reached the forward write: {written}"
    )
    assert mod.VENUE_AGREES != mod.VENUE_REFUTES


def test_an_unreadable_venue_writes_nothing_at_all(monkeypatch):
    """Fail closed end-to-end: no answer from Kalshi means no zeros written."""
    written = _drive_apply_with_venue(
        monkeypatch, [_venue_leg(outcome_id=333, outcome_ticker="T-LOST")], None
    )

    assert written == []


def test_the_settled_statuses_do_not_admit_a_trading_market():
    """A widening of this set is the one edit that silently restores the defect."""
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    assert "active" not in mod.VENUE_SETTLED_STATUSES
    assert "initialized" not in mod.VENUE_SETTLED_STATUSES
    assert mod.VENUE_SETTLED_STATUSES == frozenset({"finalized", "settled"})
    assert mod.VENUE_LOSS_RESULT == "no"


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeSvc:
    """A KalshiAPIService-shaped stub that serves a scripted status sequence."""

    BASE_URL = "https://venue.test"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

        class _Client:
            async def get(_self, url, params=None, headers=None):
                self.calls += 1
                # Notice 39: the read must go through the carrier, and the
                # assertion is EQUALITY with it rather than "the header is
                # present" — `tagged()` legitimately yields `{}` for a
                # third-party host and for an unnamed agent, so a presence
                # check would be vacuous in exactly the environment CI runs in,
                # while still failing if the kwarg is dropped (`None != {}`).
                assert headers == tagged(url)
                return self._responses.pop(0)

        self.client = _Client()


def _event_payload(ticker, status, result):
    return {"event": {"markets": [
        {"ticker": ticker, "status": status, "result": result}
    ]}}


def test_a_rate_limited_read_is_retried_not_counted_as_a_venue_answer():
    """429 is the venue saying "later", and refusing on it fabricates a finding.

    MEASURED, which is why this test exists: at 8-wide with no backoff, Kalshi
    rate-limited 183 of 309 event tickers and the run reported 421 rows
    `event_unreadable` — a number that reads as "the venue does not list these"
    and was produced entirely by the rig. Three of the first six re-read
    sequentially answered 200.
    """
    import asyncio

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    svc = _FakeSvc([
        _FakeResponse(429),
        _FakeResponse(429),
        _FakeResponse(200, _event_payload("T-LOST", "finalized", "no")),
    ])
    monkey_sleep = asyncio.sleep

    async def _go():
        # Keep the test fast without stubbing the retry itself away.
        mod.asyncio.sleep = lambda _s: monkey_sleep(0)
        try:
            return await mod.read_event_book(svc, "KXFOO")
        finally:
            mod.asyncio.sleep = monkey_sleep

    read = asyncio.run(_go())

    assert svc.calls == 3, "the reader gave up on a rate limit"
    assert read.book is not None
    assert read.book["T-LOST"]["result"] == "no"


def test_a_persistent_rate_limit_ends_in_a_refusal_named_as_such():
    """Exhausted retries still refuse — but the reason must not read as a 404."""
    import asyncio

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    svc = _FakeSvc([_FakeResponse(429)] * mod.VENUE_READ_ATTEMPTS)
    real_sleep = asyncio.sleep

    async def _go():
        mod.asyncio.sleep = lambda _s: real_sleep(0)
        try:
            return await mod.read_event_book(svc, "KXFOO")
        finally:
            mod.asyncio.sleep = real_sleep

    read = asyncio.run(_go())

    assert read.book is None
    assert read.reason == "rate_limited"
    assert read.reason != "http_404"


def test_a_404_is_an_answer_and_costs_no_retry():
    """Kalshi purges MARKET rows (gotcha #35); a 404 is not worth four attempts."""
    import asyncio

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    svc = _FakeSvc([_FakeResponse(404)])
    read = asyncio.run(mod.read_event_book(svc, "KXGONE"))

    assert svc.calls == 1
    assert read.book is None and read.reason == "http_404"


def test_the_refusal_report_names_the_transport_cause(monkeypatch):
    """`event_unreadable` alone cannot tell an operator whether to re-run."""
    import asyncio

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    async def _reader(tickers):
        return {t: mod.VenueRead(None, "rate_limited") for t in tickers}

    _, refused, reasons = asyncio.run(
        mod.confirm_against_venue([_venue_leg()], reader=_reader)
    )

    assert len(refused) == 1
    assert reasons["event_unreadable:rate_limited"] == 1


def test_the_venue_read_budget_is_pinned_at_its_measured_value():
    """A tuned constant needs a guard pinning it from BOTH sides.

    8-wide is the value that was MEASURED failing: Kalshi rate-limited 183 of
    309 event tickers on 2026-09-12 and the run reported the shortfall as a
    venue finding. The backoff added since makes 8 survivable rather than
    correct — it would simply spend the run sleeping. 1-wide is the opposite
    error: 309 sequential reads inside a repair nobody will wait for. Neither
    bound is arbitrary, so neither is left unasserted.
    """
    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    assert 2 <= mod.VENUE_CONCURRENCY <= 4, (
        "8-wide was measured rate-limiting 183/309 event tickers; 1-wide is a "
        "309-read serial crawl. Re-measure before moving this."
    )
    assert mod.VENUE_READ_ATTEMPTS >= 3
    assert mod.VENUE_BACKOFF_SECONDS >= 1.0


def test_the_backup_covers_exactly_what_the_venue_confirmed(monkeypatch):
    """The undo must describe the write, not the plan.

    A backup keyed on the PRE-venue plan records rows this repair never
    touched, and the manifest then answers "what did the repair do?" with a
    superset — the CERT-2439 lesson this script's `MANIFEST_TABLE` comment was
    written for. The write loop is already gated; this binds the undo to the
    same set.
    """
    import asyncio
    from contextlib import asynccontextmanager

    from scripts import repair_5246_settled_outcomes_still_carrying_a_price as mod

    backed_up = []

    class _Result:
        rowcount = 1

        @staticmethod
        def fetchall():
            return []

    class _Session:
        async def execute(self, stmt, params=None):
            return _Result()

        async def commit(self):
            return None

    @asynccontextmanager
    async def _fake_session():
        yield _Session()

    async def _backup(session, outcome_ids):
        backed_up.extend(outcome_ids)

    lost = _venue_leg(outcome_id=111, outcome_ticker="T-LOST")
    live = _venue_leg(outcome_id=222, outcome_ticker="T-LIVE")
    book = {
        "T-LOST": {"ticker": "T-LOST", "status": "finalized", "result": "no"},
        "T-LIVE": {"ticker": "T-LIVE", "status": "active", "result": ""},
    }

    async def _reader(tickers):
        return {t: mod.VenueRead(book, "") for t in tickers}

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    monkeypatch.setattr(mod, "plan", lambda rows: ([lost, live], []))
    monkeypatch.setattr(mod, "manifest_count", _async_const(mod.SANITY_FLOOR))
    monkeypatch.setattr(mod, "attach_venue_coordinates", _async_const(None))
    monkeypatch.setattr(mod, "_read_books", _reader)
    monkeypatch.setattr(mod, "backup", _backup)
    monkeypatch.setattr(mod, "reconcile_backup", _async_const({"missing": 0}))

    class _Args:
        limit = None
        backup = True
        apply = True

    asyncio.run(mod.run(_Args()))

    assert backed_up == [111], (
        f"the backup covered rows the venue refused: {backed_up}"
    )
