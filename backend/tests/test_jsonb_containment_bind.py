"""`cast(json.dumps(x), JSONB)` double-encodes, and `@>` never says so.

## The defect this file exists to catch

Every taxonomy-tag filter in the app matched zero rows, silently, from the day
it was written. Three call sites spelled containment as::

    Event.event_tags.op("@>")(cast(json.dumps(["sport:soccer"]), JSONB))

`cast()` over a bare Python value builds a bind whose type is the cast target.
`JSONB`'s bind processor serializes with `json.dumps` — so an already-serialized
string is serialized AGAIN and reaches PostgreSQL as a JSON string scalar,
``'"[\\"sport:soccer\\"]"'``, not a JSON array. Containment against an array of
strings is then simply false, with no error and no log line.

Reader cost: all 29 `/categories/<slug>` pages served zero items while the
`/categories` index advertised up to 9,191 markets for the same tag, and the
"More Like This" section never rendered on any event or futures detail page.

## What each arm here does

`TestTheBindGoesOnTheWireAsAnArray` is the oracle: it compiles the real
expression against the real asyncpg dialect and runs the real bind processor,
so it asserts the bytes, not the shape. This is the only arm that would have
caught the original defect — the SQL text is identical either way.

`TestTheBrokenSpellingIsGoneRepoWide` is the cheap net for the class: a static
sweep of `app/` for `cast(<something>.dumps(...), JSONB)`. It needs no database
and covers call sites nobody thought to test.

Neither replaces `tests/integration/test_feed_static_tag_filter.py`, which
drives the route — a pure-lib guard stays green if someone deletes the call.
"""

import ast
import json
import pathlib

import pytest
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB, asyncpg as pg_asyncpg

from app.models.models import Event, FuturesMarket
from app.utils.jsonb_containment import jsonb_contains

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"


def _wire_values(expr):
    """Compile `expr` for asyncpg and return the post-bind-processor values.

    This is the whole point of the file: the compiled SQL string is byte
    identical for the correct and the broken spelling. Only the processed bind
    value differs.
    """
    dialect = pg_asyncpg.dialect()
    compiled = select(Event.id).where(expr).compile(dialect=dialect)
    out = []
    for key, bindparam in compiled.binds.items():
        value = compiled.params.get(key)
        if value is None:
            continue
        processor = bindparam.type.bind_processor(dialect)
        out.append(processor(value) if processor else value)
    return out


class TestTheBindGoesOnTheWireAsAnArray:
    def test_helper_sends_a_json_array_not_a_json_string(self):
        wire = _wire_values(jsonb_contains(Event.event_tags, ["sport:soccer"]))
        assert wire == ['["sport:soccer"]']
        # The distinguishing property, stated directly: what arrives must parse
        # as a list. The broken form parses as a str.
        assert isinstance(json.loads(wire[0]), list)

    def test_the_broken_spelling_really_does_double_encode(self):
        """Pin the defect itself, so this file fails if the premise stops holding."""
        wire = _wire_values(
            Event.event_tags.op("@>")(cast(json.dumps(["sport:soccer"]), JSONB))
        )
        assert wire == ['"[\\"sport:soccer\\"]"']
        assert isinstance(json.loads(wire[0]), str)

    def test_the_two_spellings_differ_only_in_the_bind_type_annotation(self):
        """Why no reviewer caught it: the statement is the same but for one token.

        asyncpg annotates each parameter with the bind's inferred type, so the
        broken form reads `CAST($1::JSONB AS JSONB)` and the correct one
        `CAST($1::VARCHAR AS JSONB)`. That token is the ONLY textual tell — and
        the broken one is the one that looks right. Everything a reviewer scans
        for (the operator, the column, the cast target) is identical.
        """
        dialect = pg_asyncpg.dialect()
        good = str(
            select(Event.id)
            .where(jsonb_contains(Event.event_tags, ["sport:soccer"]))
            .compile(dialect=dialect)
        )
        bad = str(
            select(Event.id)
            .where(
                Event.event_tags.op("@>")(cast(json.dumps(["sport:soccer"]), JSONB))
            )
            .compile(dialect=dialect)
        )
        assert good != bad
        assert good.replace("$1::VARCHAR", "$1::JSONB") == bad
        # ...and the tell points the wrong way: the BROKEN spelling is the one
        # whose SQL says JSONB.
        assert "$1::JSONB" in bad and "$1::VARCHAR" in good

    @pytest.mark.parametrize(
        "value",
        [
            ["sport:soccer"],
            ["tier:1"],
            ["source:kalshi"],
            ["sport:soccer", "tier:1"],
            ["sport:entertainment"],
        ],
    )
    def test_every_namespace_survives_the_round_trip(self, value):
        wire = _wire_values(jsonb_contains(Event.event_tags, value))
        assert json.loads(wire[0]) == value

    def test_it_works_on_the_futures_column_too(self):
        wire = _wire_values(jsonb_contains(FuturesMarket.market_tags, ["sport:golf"]))
        assert json.loads(wire[0]) == ["sport:golf"]

    def test_the_operator_is_still_containment(self):
        sql = str(
            select(Event.id)
            .where(jsonb_contains(Event.event_tags, ["sport:soccer"]))
            .compile(dialect=pg_asyncpg.dialect())
        )
        assert "@>" in sql
        assert "events.event_tags" in sql

    def test_literal_is_what_makes_it_work(self):
        """Guard the mechanism, not just the outcome.

        Dropping `literal()` is a one-token edit that reintroduces the defect,
        so assert that the bind's type is NOT JSONB (which is what would make
        its processor re-serialize).
        """
        dialect = pg_asyncpg.dialect()
        compiled = (
            select(Event.id)
            .where(jsonb_contains(Event.event_tags, ["sport:soccer"]))
            .compile(dialect=dialect)
        )
        typed = [
            type(bp.type).__name__
            for key, bp in compiled.binds.items()
            if compiled.params.get(key) is not None
        ]
        assert typed and "JSONB" not in typed


def _broken_containment_sites(root=None):
    """Every `cast(<*>.dumps(...), JSONB)` under `root`, as (path, lineno).

    `root` is a parameter so the self-check below can drive THIS function over a
    known-bad sample. A sweep that a test reimplements inline is a sweep whose
    body can be deleted without any test noticing.
    """
    root = APP_DIR if root is None else pathlib.Path(root)
    hits = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:  # pragma: no cover - the suite has other guards
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "cast"):
                continue
            if len(node.args) != 2:
                continue
            target = node.args[1]
            target_name = (
                target.id
                if isinstance(target, ast.Name)
                else getattr(target, "attr", None)
            )
            if target_name != "JSONB":
                continue
            inner = node.args[0]
            # `cast(literal(json.dumps(x)), JSONB)` is the CORRECT spelling —
            # `literal` pins the bind type to String, so the JSONB processor
            # never runs. Only an unwrapped `.dumps(...)` is the defect.
            if not isinstance(inner, ast.Call):
                continue
            if getattr(inner.func, "attr", None) == "dumps":
                try:
                    label = str(path.relative_to(APP_DIR.parent))
                except ValueError:  # a self-check root outside the repo
                    label = str(path)
                hits.append((label, inner.lineno))
    return hits


class TestTheBrokenSpellingIsGoneRepoWide:
    def test_no_module_casts_a_dumps_result_straight_to_jsonb(self):
        hits = _broken_containment_sites()
        assert hits == [], (
            "cast(json.dumps(x), JSONB) double-encodes the bind — the value "
            "reaches PostgreSQL as a JSON string scalar and `@>` is silently "
            "false forever. Use app.utils.jsonb_containment.jsonb_contains(), "
            "or cast(literal(json.dumps(x)), JSONB). Offending sites: "
            + ", ".join(f"{p}:{ln}" for p, ln in hits)
        )

    def test_the_sweep_can_actually_see_the_pattern(self, tmp_path):
        """A finder that finds nothing proves nothing — prove it on a sample.

        This drives `_broken_containment_sites` ITSELF over a known-bad file,
        rather than reimplementing the walk here. Reimplementing it is how the
        guard above ends up permanently green the day somebody empties the AST
        walk's body: a test that restates the code cannot fail with it.
        """
        sample = tmp_path / "sample.py"
        sample.write_text(
            "import json\n"
            "from sqlalchemy import cast, literal\n"
            "from sqlalchemy.dialects.postgresql import JSONB\n"
            "bad = cast(json.dumps(x), JSONB)\n"
            "good = cast(literal(json.dumps(x)), JSONB)\n"
        )
        hits = _broken_containment_sites(root=tmp_path)
        assert [ln for _p, ln in hits] == [4], (
            "the sweep must flag the bad line (4) and spare the correct "
            f"literal() spelling on line 5 — got {hits}"
        )

    def test_the_correct_literal_spelling_is_not_flagged(self):
        """`entity_seed` / `entity_registry` already do it right — keep them clean."""
        hits = dict(_broken_containment_sites())
        assert "app/tasks/entity_seed.py" not in hits
        assert "app/services/entity_registry.py" not in hits
