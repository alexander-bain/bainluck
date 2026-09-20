"""#7397 rider — the typeahead headline-contender shed log cannot be forged.

THE DEFECT. `GET /api/events/typeahead?q=...` takes free text a reader controls.
When the headline-contender bonus lane blew its statement timeout, the shed
handler logged that text back:

    logger.warning(
        "typeahead headline-contender lane timed out for %r — shipping "
        "the dropdown unchanged", q
    )

CodeQL grades that `py/log-injection` at MEDIUM — alert **#2065**, open on
`refs/heads/master` since 2026-09-06T04:11:58Z, recorded at
`backend/app/routes/events.py:10068` col 43, which is the `q` on that line. A
query containing a newline forges a whole log line downstream of us. It was not
introduced by #7397; #7397's diff sits in the same function, which is why the
alert surfaced on PR #7401's merge ref as the only open alert there and stopped
the ship under notice 32.

THE FIX is the move five prior repairs in this tree already made (#5728, #5905,
#6249, #6355, #6532): spend a value the reader does not control. Here there is
no trusted re-source for free text — unlike `/search`, this route never calls
`_record_search_query` — so the line spends `len(q)`, an int.

WHAT THIS FILE PINS, and what it deliberately does not:

* It is scoped to ONE handler, located by the mark it writes. Fifteen other
  logging calls in `events.py` still spend `q`, all of them `search_events`'
  diagnostics, two of them CodeQL alerts in their own right (#2861, #2852).
  Degrading another lane's timeout diagnostics is that lane's call; a file-wide
  ban here would be a ban I cannot honour, and a guard nobody can keep green is
  a guard that gets deleted.
* The ban is not "the name `q` is absent" — that would forbid the fix itself.
  It is "`q` reaches this call ONLY as the argument of `len`", which is the
  actual policy, and it is enforced against ALL of the route's request-supplied
  parameters, read off the signature rather than hardcoded, so a future
  `Query(...)` parameter logged here reddens too.
* The last test renders the call the way `logging` would, with a forged query,
  and asserts on the RESULTING MESSAGE. A source-level ban proves nothing if the
  value arrives by a shape the ban did not imagine; the record is the fact.

Every test here is RED on the pre-fix source.
"""

import ast
import inspect
import textwrap

import pytest

import app.routes.events as events_module
from app.routes.events import typeahead_search

#: The mark the shed handler writes. Located by this rather than by position, so
#: reordering the route's stages cannot silently point this file at a different
#: handler — the same reason `test_lat_p239_typeahead_headline_shed_3394.py`
#: locates it this way.
SHED_MARK = "headline_contenders_TIMED_OUT"

#: A query that forges a second log line if it is ever interpolated raw.
FORGED_QUERY = "red sox\nWARNING:app.routes.events:transfer approved"

LOGGING_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}


def _route_function() -> ast.AsyncFunctionDef:
    """The route's own tree."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(typeahead_search)))
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            return node
    raise AssertionError("`typeahead_search`'s source did not parse to a function")


def _request_supplied_parameters() -> set[str]:
    """Every parameter of the route bound to a FastAPI request extractor.

    Read off the signature instead of hardcoded to `q`: the property being
    guarded is "nothing the caller supplies reaches this log line", and a
    hardcoded name stops guarding the moment a second one is added.
    """
    fn = _route_function()
    args = fn.args
    positional = args.posonlyargs + args.args
    pairs = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
    pairs += [
        (a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None
    ]
    supplied = set()
    for arg, default in pairs:
        if not isinstance(default, ast.Call):
            continue
        func = default.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in {"Query", "Path", "Body", "Form", "Header", "Cookie"}:
            supplied.add(arg.arg)
    return supplied


def _shed_handler() -> ast.ExceptHandler:
    for node in ast.walk(_route_function()):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if any(
            isinstance(const, ast.Constant) and const.value == SHED_MARK
            for const in ast.walk(node)
        ):
            return node
    raise AssertionError(
        f"no except handler in `typeahead_search` marks {SHED_MARK!r} — the "
        "headline lane's shed path has moved or gone, and this whole file is "
        "now vacuous rather than passing"
    )


def _logging_calls(node: ast.AST) -> list[ast.Call]:
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr in LOGGING_METHODS
        and isinstance(child.func.value, ast.Name)
        and child.func.value.id in {"logger", "logging", "log"}
    ]


def _names_excused_by_len(call: ast.Call) -> set[int]:
    """`id()` of every Name node that is the sole argument of a `len(...)`.

    `len(q)` is the sanctioned form, so a flat "the name never appears" ban
    would forbid the fix it is meant to protect. This is what makes the ban
    below express the policy rather than a spelling of it.
    """
    excused = set()
    for child in ast.walk(call):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "len"
            and len(child.args) == 1
            and not child.keywords
            and isinstance(child.args[0], ast.Name)
        ):
            excused.add(id(child.args[0]))
    return excused


class TestTheGuardIsLookingAtSomething:
    """If these fail, every assertion below has stopped meaning anything."""

    def test_the_route_takes_a_request_supplied_query(self):
        supplied = _request_supplied_parameters()
        assert "q" in supplied, (
            "`typeahead_search` no longer takes a `q` bound to `Query(...)`. "
            "Either the route was renamed out from under this file or the "
            "signature reader is broken; in both cases the ban below is now "
            "banning nothing."
        )

    def test_the_shed_handler_still_logs(self):
        """The cheap way to pass this file is to delete the log line. That is
        not the fix — a lane that sheds silently is the thing LAT-P239's marks
        exist to prevent — so the presence of the call is asserted first."""
        calls = _logging_calls(_shed_handler())
        assert len(calls) == 1, (
            "the headline shed handler emits "
            f"{len(calls)} logging calls, expected exactly 1. If the lane now "
            "sheds without saying so, the timeout is invisible in production; "
            "if it says so twice, this file is guarding one of them."
        )


class TestTheShedLogCannotBeForged:
    """CodeQL `py/log-injection` alert #2065, pinned at the call site."""

    def test_no_request_supplied_value_reaches_the_call(self):
        """RED on the pre-fix source, which passed `q` positionally."""
        call = _logging_calls(_shed_handler())[0]
        supplied = _request_supplied_parameters()
        excused = _names_excused_by_len(call)

        offenders = sorted(
            {
                node.id
                for arg in list(call.args) + [kw.value for kw in call.keywords]
                for node in ast.walk(arg)
                if isinstance(node, ast.Name)
                and node.id in supplied
                and id(node) not in excused
            }
        )
        assert not offenders, (
            "the headline shed log spends request-supplied value(s) "
            f"{offenders} — that is CodeQL `py/log-injection` (#2065, medium): "
            "a query carrying a newline forges a log line. Spend a value the "
            "reader does not control; `len(q)` is the sanctioned form here and "
            "is excused by this guard."
        )

    def test_a_forged_query_cannot_reach_the_emitted_record(self):
        """The assertion is on the MESSAGE, not on the source.

        A source-level ban proves nothing if the value arrives in a shape the
        ban did not imagine, so the call's own argument expressions are
        evaluated against a forged query and rendered the way `logging` renders
        them.
        """
        call = _logging_calls(_shed_handler())[0]
        namespace = dict(vars(events_module))
        namespace["q"] = FORGED_QUERY

        try:
            template = eval(compile(ast.Expression(call.args[0]), "<log>", "eval"), namespace)
            values = tuple(
                eval(compile(ast.Expression(arg), "<log>", "eval"), namespace)
                for arg in call.args[1:]
            )
        except NameError as exc:  # pragma: no cover — a deliberate stop
            pytest.fail(
                "the shed log now spends a value this guard cannot evaluate "
                f"({exc}). That is not a harness failure to route around: a new "
                "value in this log line is exactly what wants reading before it "
                "ships. Add it to the namespace only once you have checked it "
                "carries nothing the caller supplied."
            )

        message = template % values if values else template

        assert "\n" not in message, (
            f"the emitted record spans more than one line: {message!r}. Whatever "
            "reaches this call carries the caller's newline, so the log can be "
            "forged even if the source-level ban above is green."
        )
        assert "transfer approved" not in message, (
            f"the forged query's payload reached the record: {message!r}"
        )
        assert "red sox" not in message, (
            "the query text itself reached the record even though the forged "
            f"newline did not: {message!r}. #2065 is about the value being "
            "reader-controlled, not about one character."
        )

    def test_the_record_still_names_the_lane_and_its_cost(self):
        """Not spending the query must not mean saying nothing useful.

        A shed line that names neither the lane nor a dimension of the query is
        the silent-degradation failure mode wearing a log call.
        """
        call = _logging_calls(_shed_handler())[0]
        namespace = dict(vars(events_module))
        namespace["q"] = FORGED_QUERY
        template = eval(compile(ast.Expression(call.args[0]), "<log>", "eval"), namespace)
        values = tuple(
            eval(compile(ast.Expression(arg), "<log>", "eval"), namespace)
            for arg in call.args[1:]
        )
        message = template % values if values else template

        assert "headline" in message.lower(), (
            f"the shed record does not name the lane that shed: {message!r}"
        )
        assert str(len(FORGED_QUERY)) in message, (
            "the shed record carries no measure of the query that caused it. "
            f"`len(q)` is what #2065 leaves us: {message!r}"
        )
