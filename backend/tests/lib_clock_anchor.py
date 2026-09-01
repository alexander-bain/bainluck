"""The anchor guard, generalised over the anchor's NAME.

WHAT THIS IS FOR
================

A test that asserts behaviour relative to *now* needs a fixed instant to build
its fixtures from. If that instant is a **literal**, and anything downstream
bounds it against a **rolling** window, the test is a bomb whose fuse is exactly
as long as the bound:

    NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)   # <- the fuse
    ...                                                          #    SENTINEL_MAX_AGE_S = 30 days

That one detonated at 2026-08-31T12:00:00Z. ``backend-tests (2)`` went red,
``deploy`` skipped, and for fifteen hours nothing reached production with
thirteen certified branches stacked behind it. **No commit caused it. Time
passed.** A test that reds because time passed, with no code change, is not
testing the product — it is a scheduled outage with a stack trace.

The fix is always the same shape: derive the anchor from the clock, offset it by
a fixed amount, and truncate. Gotcha #44 — **offset FIRST, then truncate**::

    NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)

This module is the guard that makes the fix stick, so the next author's
tidy-looking literal cannot quietly re-arm it.

PROVENANCE — DO NOT RE-DERIVE THIS
==================================

The implementation below is CERT-589's, lifted verbatim in behaviour and
generalised from the hardcoded name ``NOW`` to any anchor name. It is the
survivor of **five** consecutive certs, every one of which found the anchor fine
and the GUARD hollow:

* **CERT-568** — the guard compared the anchor's VALUE against a re-derived one
  and passed within an hour. A *fresh* literal satisfies that trivially. The
  general lesson, and the reason none of this is a value check: **a guard
  against "someone hardcoded a value" cannot itself be a check on the value.**
  It has to read the CODE.
* **CERT-571** — the scan took the FIRST module-level binding; Python uses the
  LAST one executed. A shadowing literal below the real anchor walked past it.
* **CERT-577** — "module level" was read as ``tree.body``. ``if True:`` /
  ``try:`` nests a binding one level down in the AST while executing at module
  scope exactly like a top-level statement. **The rule is SCOPE, not DEPTH.**
* **CERT-581** — presence-as-provenance. ``datetime.now(tz) if False else
  <literal>`` contains a real clock call whose result is discarded. No amount of
  extra AST care separates that from the real thing; *running* it against a
  moving clock separates it instantly.
* **CERT-583** — behaviour at N points is behaviour at N points. Both fake
  instants sat in 2031, so ``... if datetime.now().year == 2031 else <literal>``
  tracked perfectly across them and bound the constant in the real run. A
  conditional can simply RECOGNISE the sampled calendar.

So the guard is two complementary halves, and **both are required**:

* :func:`assert_anchor_grammar` — an ALLOWLIST. The right-hand side may be a
  clock call, a fixed +/- offset and a truncation, and nothing else. Anything
  that can SELECT between two values is refused **by shape**, whether or not
  anyone has thought of the trick it enables. This is what bounds the space of
  expressions to ones whose behaviour two samples genuinely characterise.
* :func:`assert_value_tracks_the_clock` — evaluates the right-hand side against
  two clocks and requires the value to follow both, exactly. This catches a
  grammatically legal anchor that still does not track
  (``datetime.now(tz).replace(year=2026)`` parses fine and is pinned), which no
  grammar can see.

🔴 IF YOU USE THIS, ALSO EXERCISE ITS FAILURE PATH. ``tests/test_clock_anchor_
guard.py`` carries every disclosed attack and each must raise. Four of the five
certs above landed on a green suite: a guard nobody has watched fail is a guard
nobody knows the shape of.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone

#: The ONLY calls an anchor's right-hand side may make. An allowlist, because
#: the denylist approach lost four times running. Adding a name here is a
#: deliberate act with this comment attached; forgetting to add one fails loudly
#: and safely.
ANCHOR_CLOCK_CALLS = frozenset(
    {"now", "utcnow", "today", "fromtimestamp", "time", "time_ns"}
)
ANCHOR_SHAPING_CALLS = frozenset({"replace", "astimezone", "timedelta"})


def module_level_stores(tree: ast.AST, name: str) -> list[ast.Name]:
    """Every module-scope STORE of ``name``.

    Scope, not depth (CERT-577): everything that is not a new binding scope is
    module level however deeply it is nested, so this recurses through
    executable bodies (``if`` / ``try`` / ``for`` / ``while`` / ``with`` /
    ``match``) and stops only at ``def`` / ``async def`` / ``class`` /
    ``lambda``, where the name is a LOCAL and cannot touch the fixture.

    It collects every STORE, not just assignment statements — ``for X in ...``,
    ``with ... as X``, ``X += ...`` and walrus all rebind the anchor, and a scan
    that only knows about ``Assign`` calls each of them clean.
    """
    out: list[ast.Name] = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                continue  # a new scope — this name in there is not the anchor
            if (
                isinstance(child, ast.Name)
                and child.id == name
                and isinstance(child.ctx, ast.Store)
            ):
                out.append(child)
            walk(child)

    walk(tree)
    return out


def assert_anchor_grammar(node: ast.AST, name: str = "the anchor") -> None:
    """Refuse any anchor expression outside ``clock() +/- timedelta`` + truncation.

    Walks the right-hand side and permits only the node types that shape a clock
    reading. Anything that can select BETWEEN values — ``IfExp``, ``BoolOp``,
    ``Compare``, ``Subscript``, a comprehension, a lambda — is rejected
    outright, because selection is how every disclosed attack smuggled a
    constant past a check that had already seen a real clock call.
    """
    allowed_nodes = (
        ast.Expression, ast.Call, ast.Attribute, ast.Name, ast.Constant,
        ast.BinOp, ast.Sub, ast.Add, ast.UnaryOp, ast.USub, ast.keyword, ast.Load,
    )
    for child in ast.walk(node):
        if not isinstance(child, allowed_nodes):
            raise AssertionError(
                f"`{name}` uses `{type(child).__name__}`, which is not part of the "
                "permitted grammar. It reads as:\n"
                f"    {ast.unparse(node)}\n"
                "An anchor may only be a clock call, a fixed +/- timedelta, and a "
                "truncation such as `.replace(microsecond=0)`. Anything that can "
                "CHOOSE between two values — a conditional, an `or`/`and`, an index, "
                "a comparison — is refused by shape, because that is how a hardcoded "
                "instant hides behind a real clock call (CERT-581, CERT-583). If you "
                "need something genuinely new here, widen this grammar deliberately "
                "and add the attack to `tests/test_clock_anchor_guard.py`."
            )
        if isinstance(child, ast.Call):
            fn = child.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if fname not in ANCHOR_CLOCK_CALLS | ANCHOR_SHAPING_CALLS:
                raise AssertionError(
                    f"`{name}` calls `{fname}`, which is not an approved clock or "
                    "shaping call. It reads as:\n"
                    f"    {ast.unparse(node)}\n"
                    f"Permitted: {sorted(ANCHOR_CLOCK_CALLS | ANCHOR_SHAPING_CALLS)}. "
                    "`datetime(...)` is deliberately absent — constructing an instant "
                    "is the thing this guard exists to forbid."
                )
    # And at least one of them must actually BE a clock read, or the grammar is
    # satisfied by an expression that never consults the clock at all.
    calls = {
        (c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None))
        for c in ast.walk(node)
        if isinstance(c, ast.Call)
    }
    if not (calls & ANCHOR_CLOCK_CALLS):
        raise AssertionError(
            f"`{name}` never reads the clock. It reads as:\n"
            f"    {ast.unparse(node)}\n"
            f"One of {sorted(ANCHOR_CLOCK_CALLS)} must appear."
        )


def assert_value_tracks_the_clock(value: ast.AST, name: str = "the anchor") -> None:
    """Evaluate the expression against two clocks; require it to follow both.

    The sandbox hands the expression a ``datetime`` whose
    ``.now()``/``.utcnow()``/``.today()`` and a ``time`` whose ``.time()`` report
    a controlled instant, then advances that instant and evaluates again. A
    clock-derived anchor shifts by exactly the amount the clock shifted. A
    constant — reached through a dead branch, a short-circuit, an index, or
    spelled plainly — does not move at all.

    ``_FrozenDatetime`` SUBCLASSES the real ``datetime``, so arithmetic,
    ``.replace()`` and ``.isoformat()`` on the result behave exactly as they do
    in production; only the clock entry points are substituted.
    """
    # Both instants are whole minutes with no sub-second component, so the
    # truncations a sane anchor performs (`.replace(microsecond=0)`,
    # `.replace(second=0)`) are no-ops and the tracking test is an exact
    # equality rather than a tolerance nobody can reason about.
    #
    # 🔴 CERT-583: THE FIRST INSTANT IS THE REAL NOW, AND THE SECOND IS IN A
    # DIFFERENT YEAR. Anchoring the first sample to the ACTUAL current time
    # removes the fixed calendar there is to recognise, and straddling a year
    # boundary means a year-gated conditional can no longer satisfy both
    # evaluations: it either returns its constant at both points (caught by
    # `before != after`) or switches between them (caught by the exact `shift`
    # equality).
    first = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    shift = timedelta(days=400, hours=5, minutes=7)
    assert (first + shift).year != first.year, "the two samples must straddle a year"

    def _evaluate(instant):
        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant if tz else instant.replace(tzinfo=None)

            @classmethod
            def utcnow(cls):
                return instant.replace(tzinfo=None)

            @classmethod
            def today(cls):
                return instant.replace(tzinfo=None)

        class _FrozenTime:
            @staticmethod
            def time():
                return instant.timestamp()

            @staticmethod
            def time_ns():
                return int(instant.timestamp() * 1_000_000_000)

        sandbox = {
            "datetime": _FrozenDatetime,
            "timedelta": timedelta,
            "timezone": timezone,
            "time": _FrozenTime,
        }
        expression = ast.Expression(body=value)
        ast.fix_missing_locations(expression)
        try:
            return eval(compile(expression, "<anchor>", "eval"), sandbox)  # noqa: S307
        except Exception as exc:  # noqa: BLE001 — fail CLOSED, never open
            raise AssertionError(
                f"`{name}`'s right-hand side could not be evaluated against a fake "
                f"clock ({type(exc).__name__}: {exc}). It reads as:\n"
                f"    {ast.unparse(value)}\n"
                "This guard proves the anchor tracks the clock by RUNNING it, so an "
                "expression it cannot run is refused rather than waved through. If "
                "the anchor legitimately needs another name, add it to `sandbox` "
                "above — do not weaken the check."
            ) from exc

    before, after = _evaluate(first), _evaluate(first + shift)

    assert before != after, (
        f"`{name}` does NOT track the clock: moving the clock forward by {shift} "
        f"left it at exactly {before!r}. It reads as:\n"
        f"    {ast.unparse(value)}\n"
        "That means the value that actually binds is a CONSTANT, whatever the "
        "source looks like — a dead `datetime.now(...)` branch, a short-circuit, or "
        "an unused element all put a clock call in the text without letting it reach "
        "the result (CERT-581). A constant anchor is fresh on the day it is written "
        "and silently crosses a rolling bound later, taking a backend shard red with "
        "no code change. Derive it from the clock."
    )
    assert after - before == shift, (
        f"`{name}` moved by {after - before} when the clock moved by {shift}, so it "
        "is only PARTLY derived from the clock. It reads as:\n"
        f"    {ast.unparse(value)}\n"
        "The anchor must be the current time plus or minus a fixed offset, so that "
        "it is always the same distance behind 'now' and can never age out."
    )


def assert_anchor_is_clock_derived(src: str, name: str) -> None:
    """The whole guard, over SOURCE TEXT rather than over a file.

    A parameter and not a ``__file__`` read, so the battery in
    ``tests/test_clock_anchor_guard.py`` can run these very assertions against
    the attacks that beat the previous versions of them. **A guard whose failure
    path is never executed is a guard whose failure path is not known to work.**
    """
    tree = ast.parse(src)

    stores = module_level_stores(tree, name)
    assert stores, f"module-level `{name}` binding not found"
    assert len(stores) == 1, (
        f"`{name}` is bound {len(stores)} times at module scope, on lines "
        f"{sorted(n.lineno for n in stores)}. The LAST one executed wins at "
        "runtime, so a guard that inspects any single binding can be satisfied by a "
        "dead one while a literal elsewhere becomes the real fixture anchor. Nesting "
        "it under `if`/`try`/`for`/`with` does not make it a different scope. Keep "
        "exactly one binding."
    )

    # The sole store must belong to a plain assignment whose value we can read.
    # A `for`/`with`/augmented/walrus binding reaches here and is refused BY NAME,
    # rather than falling through to an attribute error.
    assigns = [
        n
        for n in ast.walk(tree)
        if (isinstance(n, ast.Assign) and any(t is stores[0] for t in n.targets))
        or (isinstance(n, ast.AnnAssign) and n.target is stores[0] and n.value is not None)
    ]
    assert len(assigns) == 1, (
        f"`{name}` is bound on line {stores[0].lineno} by something other than a "
        "plain assignment with a readable right-hand side (a `for`, `with`, "
        "augmented or walrus binding). The anchor must be a single assignment that "
        "calls the clock."
    )

    # The single-binding and plain-assignment checks ABOVE are what make the two
    # below trustworthy: they guarantee that the one expression examined here is
    # the one that really binds the anchor at import.
    assert_anchor_grammar(assigns[0].value, name)
    assert_value_tracks_the_clock(assigns[0].value, name)


def assert_no_absolute_date_literals(src: str, *, allow: tuple[str, ...] = ()) -> None:
    """Refuse a hardcoded instant ANYWHERE at module scope in ``src``.

    The anchor guard covers the case where the fuse is the anchor. It does not
    cover the case where the anchor is honest and **one field of the fixture** is
    a literal — measured, that is the more common shape of the two:

        NOW = datetime.now(timezone.utc)              # honest
        ...
        "resolution_date": datetime(2026, 9, 14, tzinfo=timezone.utc),   # the fuse

    That row's market is "open" until 2026-09-14 and dropped by the reader after,
    so the test passes for as long as the calendar allows and then does not.
    Express every fixture date as an offset from the anchor and there is nothing
    to expire.

    ``allow`` lists substrings of the unparsed call that are genuinely calendar
    facts rather than freshness data (a real tournament's historical date, say).
    Each entry is a deliberate exemption and should say why at the call site.
    """
    tree = ast.parse(src)
    offenders = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                continue
            if isinstance(child, ast.Call):
                fn = child.func
                fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                if fname in {"datetime", "date"} and child.args:
                    a0 = child.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, int) and a0.value >= 1900:
                        text = ast.unparse(child)
                        if not any(a in text for a in allow):
                            offenders.append((child.lineno, text))
            walk(child)

    walk(tree)
    assert not offenders, (
        "hardcoded absolute instant(s) at module scope:\n"
        + "\n".join(f"    line {ln}: {t}" for ln, t in offenders)
        + "\nA fixture date that is compared against a rolling bound is a bomb with "
        "a fuse as long as the bound. Express it as an offset from the module's "
        "clock-derived anchor — `NOW + timedelta(days=2)` — so it is always the same "
        "distance from 'now' and can never age out. If it really is a calendar fact "
        "and not freshness data, pass it in `allow=` and say why."
    )
