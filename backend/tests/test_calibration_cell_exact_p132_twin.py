"""CAL-P132 — guards for the ``twin`` dimension.

``twin`` asks whether a row's ``group_id`` publishes the SAME question at TWO
grains at once — a ``field`` market listing every candidate answer AND a shelf
of ``container_member`` binaries asking about those answers one at a time — and
then labels which of the two grains the row itself is.

It exists because nothing already on the rail can see the dominant structure of
``polymarket/tech``. 29.2% of that cell's 2,973 raw markets are podcast and
keynote word bingo, and Polymarket publishes each such event twice: group
``polymarket:555948`` carries a 22-leg field, *"What will Tim Cook say at Apple
WWDC 2026 on June 8th?"*, alongside fourteen binaries, *"Will Tim Cook say
'Siri' during the Apple WWDC 2026 event on June 8th?"*. Both reach the curve.

* ``market_type`` separates the two grains but cannot tell a twinned field from
  a lone one, so the control and the suspect pool into a single 81.3% arm.
* ``series`` keys on the group and splits the cell into 289 arms — past
  ``rule_search``'s ``MAX_CLASSES``, so it is not searchable at all. ``twin`` is
  ``series`` collapsed onto the one property of a group that is a claim about
  the PRODUCT rather than about one event.

Everything that can go wrong here is silent. A mis-scoped group census does not
error; it moves markets between two well-formed arms and changes a verdict.

* **🔴 LEAKAGE IS STILL THE ONE THAT MATTERS.** CAL-P130 made this the standing
  test for any new dimension, and it is why ``shape`` and ``sumband`` — which
  branch on ``sh.mw``, the realized win count — are disqualified on this cell
  before their numbers are read.
  :func:`test_the_expression_never_reads_a_realized_winner` is the guard to keep
  if the rest are ever trimmed.
* **The group census must NOT be chunk-scoped.** The rail chunks on ``fm.id``.
  If ``grpcomp`` counted only the chunk's own rows, twin-ness would become a
  property of where the chunk boundary fell — a market reading ``b_field_only``
  because its siblings were 1,000,000 ids away, and the fold printing a clean
  table about it. That is gotcha #53 in its usual costume, and
  :func:`test_the_group_census_counts_the_whole_group_not_the_chunk` is the
  guard.
* **The census must not filter on status or category either.** A twin is a fact
  about what was PUBLISHED. A group whose field resolved and whose members did
  not is still a group that asked one question twice.
* **The suffix is a CROSS, not a gate** — CAL-P131's ``|full`` / ``|part`` rule
  applied to a second dimension. Labelling the group without labelling the row's
  own grain would pool the two grains of a twinned group and dilute a defect in
  one of them by the other. ``a_twinned|f`` versus ``a_twinned|m``, against the
  ``b_field_only|f`` control, is the entire question.

THE ONE THING THESE TESTS DO NOT PROVE. They model the shipped ``CASE``
expression in Python from its own literals, and they read the SQL of the
pre-pass as text. They do not execute Postgres. The shipped expression was
additionally executed SERVER-SIDE against production during CAL-P132; that run
is evidence these tests cannot supply and is recorded in
``artifacts/cal-p132/RULE-DESIGN-polymarket-tech.md``.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


# ---------------------------------------------------------------- the model


def _group_arm(g_fields: int | None, g_members: int | None, grouped: bool) -> str:
    """Model the GROUP half of the shipped ``TWIN_EXPR``.

    ``grouped`` is ``fm11.group_id IS NOT NULL``. ``g_fields``/``g_members`` are
    ``grpcomp``'s counts, ``None`` when the LEFT JOIN found no census row.
    """
    if not grouped:
        return "z_ungrouped"
    f = g_fields or 0
    m = g_members or 0
    if f >= 1 and m >= 1:
        return "a_twinned"
    if f >= 1:
        return "b_field_only"
    if m >= 1:
        return "c_members_only"
    return "d_no_grain"


def _grain(market_type: str | None) -> str:
    """Model the GRAIN half of the shipped ``TWIN_EXPR``."""
    if market_type == "field":
        return "f"
    if market_type == "container_member":
        return "m"
    return "o"


def _arm(
    g_fields: int | None,
    g_members: int | None,
    grouped: bool,
    market_type: str | None,
) -> str:
    return f"{_group_arm(g_fields, g_members, grouped)}|{_grain(market_type)}"


# ------------------------------------------------- the model tracks the SQL


def test_the_group_arms_in_the_model_are_exactly_the_ones_in_the_sql():
    """The four group labels are read out of the shipped expression, not typed.

    A model that lists its own labels drifts the moment the SQL grows a fifth.
    """
    literals = set(re.findall(r"THEN '([a-z_]+)'", cce.TWIN_EXPR))
    grain_literals = {"f", "m", "o"}
    group_literals = {x for x in literals if x not in grain_literals}
    assert group_literals == {
        "z_ungrouped",
        "a_twinned",
        "b_field_only",
        "c_members_only",
    }, group_literals
    modelled = {
        _group_arm(f, m, grouped)
        for f, m, grouped in (
            (None, None, False),
            (1, 1, True),
            (1, 0, True),
            (0, 1, True),
            (0, 0, True),
        )
    }
    assert modelled == group_literals | {"d_no_grain"}


def test_the_grain_labels_in_the_model_are_exactly_the_ones_in_the_sql():
    assert set(re.findall(r"THEN '([fmo])'", cce.TWIN_EXPR)) == {"f", "m"}
    assert "ELSE 'o' END" in cce.TWIN_EXPR
    assert {_grain(x) for x in ("field", "container_member", "quantity", None)} == {
        "f",
        "m",
        "o",
    }


def test_the_two_market_type_literals_are_the_shape_vocabulary():
    """``field`` and ``container_member`` are ``app.utils.market_shape``'s names.

    If the shape vocabulary is ever renamed, this dimension silently collapses
    to a single ``|o`` arm and reports a clean table about it.
    """
    from app.utils import market_shape

    source = Path(market_shape.__file__).read_text()
    for literal in ("field", "container_member"):
        assert f"'{literal}'" in cce.TWIN_EXPR or f'"{literal}"' in cce.TWIN_EXPR
        assert (
            f'"{literal}"' in source or f"'{literal}'" in source
        ), f"{literal!r} is no longer a market_shape label"


# ------------------------------------------------------------ 🔴 LEAKAGE


def test_the_expression_never_reads_a_realized_winner():
    """A rule keyed on this dimension must be evaluable BEFORE a winner exists.

    ``shape`` and ``sumband`` branch on ``sh.mw``. If ``twin`` did too, an
    exclusion rule built on it would select resolved markets by their
    resolution, and every ECE it reported would be measured on a population
    defined by the answer.
    """
    for name, blob in (
        ("TWIN_EXPR", cce.TWIN_EXPR),
        ("TWIN_JOIN", cce.TWIN_JOIN),
        ("TWIN_PRE", cce.TWIN_PRE),
    ):
        for forbidden in (
            "is_winner",
            "sh.mw",
            "sh.mn",
            ".mw",
            "win_count",
            "resolution_source",
            "calibration_probability",
            "opening_probability",
        ):
            assert forbidden not in blob, (
                f"{name} references {forbidden!r} — that is a realized-outcome "
                "or price input and makes any rule built on this dimension leak"
            )


def test_the_inputs_are_only_group_id_and_market_type():
    """The dimension's whole claim is that it reads two structural columns."""
    columns = set(re.findall(r"fm1[12]\.([a-z_]+)", cce.TWIN_PRE + cce.TWIN_JOIN))
    columns |= set(re.findall(r"fm11\.([a-z_]+)", cce.TWIN_EXPR))
    assert columns <= {"id", "group_id", "market_type"}, columns


# ------------------------------------ 🔴 the census must not be chunk-scoped


def test_the_group_census_counts_the_whole_group_not_the_chunk():
    """``grpcomp`` selects from ``futures_markets``, not from ``market_info``.

    ``market_info`` carries the rail's ``fm.id >= lo AND fm.id < hi`` chunk
    bound. Aggregating over it would make twin-ness depend on the chunk width:
    the 22-leg WWDC field and its fourteen binaries share a group but not
    necessarily a chunk, and a chunk holding only the field would label it
    ``b_field_only`` — the CONTROL arm — and print a clean table.
    """
    pre = cce.TWIN_PRE
    body = pre[pre.index("grpcomp AS (") :]
    assert "FROM futures_markets fm12" in body, (
        "the group census must aggregate over futures_markets; aggregating over "
        "market_info makes twin-ness a property of the chunk boundary"
    )
    # ``market_info`` may appear ONLY inside the group-id filter, never as the
    # census's own FROM. Excise the one sanctioned subquery and assert nothing
    # is left — a blanket "FROM market_info" ban would fail on that subquery,
    # which is the legitimate use.
    sanctioned = "SELECT group_id FROM market_info WHERE group_id IS NOT NULL"
    assert sanctioned in body
    assert "market_info" not in body.replace(sanctioned, "")


def test_the_census_filters_groups_but_never_markets():
    """The ``IN`` clause narrows which GROUPS are censused, not which markets.

    Adding ``AND fm12.id >= ...`` or ``AND fm12.status = 'resolved'`` here would
    reintroduce exactly the bug the test above forbids, from the other side.
    """
    body = cce.TWIN_PRE[cce.TWIN_PRE.index("grpcomp AS (") :]
    where = body[body.index("WHERE") : body.index("GROUP BY")]
    for forbidden in ("fm12.id", "status", "llm_sport_category", "source"):
        assert forbidden not in where, (
            f"the group census restricts markets on {forbidden!r} — a twin is a "
            "fact about what was published, not about what resolved or where "
            "the chunk boundary fell"
        )


def test_the_census_is_grouped_by_the_key_it_is_joined_on():
    body = cce.TWIN_PRE[cce.TWIN_PRE.index("grpcomp AS (") :]
    assert "GROUP BY fm12.group_id" in body
    assert "gc.group_id = fm11.group_id" in cce.TWIN_JOIN


def test_the_row_is_joined_to_its_own_market_not_to_the_group():
    assert "fm11.id = d.market_id" in cce.TWIN_JOIN


# ------------------------------------------------- the arms behave as claimed


@pytest.mark.parametrize(
    "g_fields,g_members,grouped,market_type,expected",
    [
        # The WWDC group: one 22-leg field + fourteen binaries.
        (1, 14, True, "field", "a_twinned|f"),
        (1, 14, True, "container_member", "a_twinned|m"),
        # The control: a field published once, with no binary shelf.
        (1, 0, True, "field", "b_field_only|f"),
        # A binary shelf with no field over it.
        (0, 7, True, "container_member", "c_members_only|m"),
        # A group of neither grain (quantity ladders, duels).
        (0, 0, True, "quantity", "d_no_grain|o"),
        # Ungrouped markets short-circuit before the census is consulted.
        (None, None, False, "field", "z_ungrouped|f"),
    ],
)
def test_the_worked_arms(g_fields, g_members, grouped, market_type, expected):
    assert _arm(g_fields, g_members, grouped, market_type) == expected


def test_a_twinned_group_labels_its_two_grains_differently():
    """The suffix is the point: without it both grains pool into one arm."""
    f = _arm(1, 14, True, "field")
    m = _arm(1, 14, True, "container_member")
    assert f != m
    assert f.split("|")[0] == m.split("|")[0] == "a_twinned"


def test_the_control_and_the_suspect_share_a_grain_and_differ_in_the_group():
    """``b_field_only|f`` is a control for ``a_twinned|f``, not a second suspect.

    Same market shape, same category, same price scale, published ONCE. If the
    two arms ever stopped sharing their grain suffix the comparison would be
    between different things and the dose-response reading would be wrong —
    CAL-P131's ``c_sum_coherent|full`` / ``d_sum_1.33_4|full`` pairing made the
    same requirement of ``bandratio``.
    """
    assert _arm(1, 14, True, "field").endswith("|f")
    assert _arm(1, 0, True, "field").endswith("|f")


def test_ungrouped_wins_over_every_census_result():
    """``z_ungrouped`` is tested FIRST, so a stale census cannot override it.

    A LEFT JOIN on a NULL group_id yields NULL counts, but the ordering is what
    guarantees it: if the census branch were tested first, a group_id of NULL
    joining nothing would fall through to ``d_no_grain`` and a genuinely
    ungrouped market would be reported as a grouped one with no grains.
    """
    expr = cce.TWIN_EXPR
    assert expr.index("z_ungrouped") < expr.index("a_twinned")
    assert _arm(None, None, False, "field") == "z_ungrouped|f"
    # even if a census row somehow existed, ungrouped still wins
    assert _arm(9, 9, False, "field") == "z_ungrouped|f"


def test_twinned_wins_over_the_two_single_grain_arms():
    """The arms are marginal-with-precedence and ``a_twinned`` is tested first.

    A twinned group satisfies ``g_fields >= 1`` as well, so without the ordering
    it would report as ``b_field_only`` and the control arm would be
    contaminated by the very rows it is supposed to control for.
    """
    expr = cce.TWIN_EXPR
    assert expr.index("a_twinned") < expr.index("b_field_only")
    assert expr.index("b_field_only") < expr.index("c_members_only")
    assert _arm(1, 1, True, "field") == "a_twinned|f"


def test_a_missing_census_row_reads_as_no_grain_not_as_twinned():
    """A LEFT JOIN miss must fail SAFE — into the arm that claims nothing."""
    assert _arm(None, None, True, "quantity") == "d_no_grain|o"


# ------------------------------------------------------------- registration


def test_the_dimension_is_registered_under_the_name_the_queue_uses():
    assert "twin" in cce.DIMENSIONS
    assert cce.DIMENSIONS["twin"] == (cce.TWIN_EXPR, cce.TWIN_JOIN, cce.TWIN_PRE)


def test_the_dimension_is_not_a_per_chunk_dimension():
    """``ladder`` is per-chunk because it needs a Python pre-pass. This is not.

    A per-chunk dimension recomputes its classification per chunk, which is the
    behaviour this dimension is specifically built to avoid.
    """
    assert "twin" not in cce.PER_CHUNK_DIMENSIONS


def test_the_pre_pass_starts_with_the_comma_the_chain_requires():
    """``cell_sql`` splices ``pre`` straight after the producer's CTE list."""
    assert cce.TWIN_PRE.startswith(",")


def test_the_pre_pass_does_not_shadow_another_dimensions_cte_name():
    """``grpcomp`` must be unique across the rail, or two dimensions collide."""
    others = [
        blob
        for name, (_e, _j, pre) in cce.DIMENSIONS.items()
        for blob in (pre,)
        if name != "twin" and pre
    ]
    for blob in others:
        assert "grpcomp AS (" not in blob


def test_the_table_aliases_do_not_collide_with_another_dimensions():
    """``fm11``/``fm12`` must not be reused by a join spliced in alongside.

    Only one dimension's join is spliced per fold, so the real risk is a future
    edit reusing the alias inside the PRODUCER's chain. Assert against it.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    chain = _calibration_population_ctes(market_info_extra="")
    for alias in ("fm11", "fm12"):
        assert f" {alias}" not in chain, f"alias {alias} is taken by the producer"


def test_the_sql_survives_the_comment_stripper():
    """``db-query`` refuses multi-statement input and counts comment semicolons."""
    sql = cce.cell_sql("polymarket", "tech", 0, 1_000_000, "twin")
    assert sql.count(";") == 0
    assert "grpcomp" in sql
    assert "a_twinned" in sql


def test_the_fold_groups_on_the_dimension_and_the_bucket():
    sql = cce.cell_sql("polymarket", "tech", 0, 1_000_000, "twin")
    assert "GROUP BY 1, 2" in sql
    assert "adj_opening_probability" in sql
