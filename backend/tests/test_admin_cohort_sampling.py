"""No Sort above the sample — the histogram/limit fix.

ORDER BY random() sorted the whole join O(n log n) and tripped H12's 30s bound.
TABLESAMPLE SYSTEM is heap-biased (block-sampled). The shipped plan is
WHERE random() < p — unbiased row-level Bernoulli, no Sort, provably under H12.
This test ensures no Sort node can return above the sampling.

Covers #1974 blocker on interpretation-matrix step 3 (sums histogram).

**AMENDED BY CAL-P071 (2026-08-18), and the amendment is the interesting part.**
Two endpoints stopped sampling altogether: `cohort_provenance_split` and
`cohort_sums_histogram` now aggregate in SQL and return a bounded number of bin
rows over the FULL population, so there is no sample to cap and no sampling
fraction to calibrate. Two assertions here mandated the sampling
*implementation* rather than the property it was chosen for —
`test_light_and_provenance_use_bernoulli_random_threshold` required
`random() < p` before `LIMIT 300000`, and `test_limits_still_cap_samples`
required all three LIMIT constants — and would have failed the stronger fix.

Read as sentences (gotcha #130): *"the provenance split must carry a 300k row
cap"* is not signable as a product claim once the endpoint returns ~1,000 rows
by construction. *"no Sort node can return above the sampling"* is, and it is
kept verbatim below, because it is the property #1974 was actually about.

The light endpoint still samples and its Bernoulli fix is untouched — the
amendment narrows these assertions to the endpoint that still needs them, and
adds their positive counterpart for the two that no longer do.
"""

import pathlib
import re


def _sql() -> str:
    p = pathlib.Path(__file__).resolve().parents[1] / "app/routes/admin_cohort.py"
    return p.read_text()


def _executable_source(fn) -> str:
    """A function's source with its docstring removed.

    Both endpoints now explain in their docstrings which idiom they removed and
    why, and a grep cannot tell an explanation from a call — written naively,
    an `ORDER BY random()` tripwire fails on its own subject's prose.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(fn).lstrip())
    node = tree.body[0]
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:]
    return ast.unparse(tree)


def test_no_order_by_random_remains():
    # Executable code only — comments may name the retired idiom for provenance.
    import io, tokenize
    src = _sql()
    kept = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(tok.string)
    code = " ".join(kept)
    assert "ORDER BY random()" not in code, (
        "ORDER BY random() reintroduced in executable code — it Sorts the whole join and trips H12 30s. "
        "Use WHERE random() < p instead."
    )
    assert code.count("random ( )") == 0  # tokenized form


def test_light_uses_bernoulli_random_threshold():
    """The one endpoint that still samples. Narrowed from `_light_and_provenance_`
    by CAL-P071 — the provenance split no longer samples at all (see below)."""
    sql = _sql()
    # Light: ... WHERE ... random() < 0.30 LIMIT 200000
    light = re.search(r"futures_outcomes fo.*?random\(\)\s*<\s*([0-9.]+).*?LIMIT 200000", sql, re.S)
    assert light is not None, "light endpoint must have WHERE random() < p before LIMIT 200000"
    p_light = float(light.group(1))
    assert 0.10 <= p_light <= 0.80, f"light p={p_light} outside [0.1,0.8] — miscalibrated sample"


def test_the_aggregating_endpoints_do_not_sample_at_all():
    """The positive counterpart, so "stopped sampling" cannot silently become
    "sampling came back under a different constant".

    A row-shipping endpoint needs a cap and therefore needs a defensible
    sampling fraction; an aggregating one returns O(cells x bins) rows whatever
    the population does, and a cap on it would be a silent truncation of the
    ANSWER rather than of the input. These two declare `sampled: False` on the
    wire for the same reason — `n_all` used to be a 300k-sample count that said
    nothing about being one.
    """
    from app.routes import admin_cohort

    for fn in (admin_cohort.cohort_provenance_split,
               admin_cohort.cohort_sums_histogram):
        src = _executable_source(fn)
        assert "GROUP BY" in src, f"{fn.__name__} must aggregate in SQL"
        assert "random ( )" not in src, (
            f"{fn.__name__} samples again — it aggregates over the full "
            "population, so a sample would trade exactness for nothing."
        )
        big = [int(m) for m in re.findall(r"LIMIT\s+(\d+)", src, re.I) if int(m) >= 1000]
        assert not big, (
            f"{fn.__name__} carries a population-scale LIMIT again ({big}) — "
            "on an aggregate that truncates the ANSWER, not the input. A small "
            "declared top-N over an already-aggregated table is fine and must "
            "report how many rows it dropped."
        )


def test_no_tablesample_system_remains():
    import io, tokenize
    src = _sql()
    kept = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(tok.string)
    code = " ".join(kept)
    assert "TABLESAMPLE" not in code, (
        "TABLESAMPLE SYSTEM reintroduced in executable code — it is block-sampled and heap-biased. "
        "Use WHERE random() < p (row-level Bernoulli) instead."
    )


def test_the_sampling_endpoint_still_caps_its_sample():
    """Narrowed by CAL-P071 from a three-way LIMIT check. The two removed
    constants belonged to endpoints that no longer ship rows; asserting their
    presence would have required keeping a cap in order to keep a test."""
    sql = _sql()
    assert "LIMIT 200000" in sql, "light LIMIT 200000 cap missing"


def test_no_sort_node_above_sample_in_explain_shape():
    """The plan shape must have no Sort between Limit and Scan.

    This is a source-level proxy for EXPLAIN (ANALYZE, BUFFERS) shape:
    ORDER BY random() emits a Sort node; WHERE random() < p emits a Filter.
    A future EXPLAIN on prod should show `Limit -> Nested Loop -> Seq/Index Scan
    Filter: random() < ...` with no Sort, Execution Time <3s. The source check
    ensures the Sort cannot return before EXPLAIN is even run.
    """
    import io, tokenize
    src = _sql()
    kept = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(tok.string)
    code = " ".join(kept)
    assert "ORDER BY random()" not in code
    assert "Sort Key: (random()" not in code
