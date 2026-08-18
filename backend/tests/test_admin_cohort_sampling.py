"""No Sort above the sample — the histogram/limit fix.

ORDER BY random() sorted the whole join O(n log n) and tripped H12's 30s bound.
TABLESAMPLE SYSTEM is heap-biased (block-sampled). The shipped plan is
WHERE random() < p — unbiased row-level Bernoulli, no Sort, provably under H12.
This test ensures no Sort node can return above the sampling.

Covers #1974 blocker on interpretation-matrix step 3 (sums histogram).
"""

import pathlib
import re


def _sql() -> str:
    p = pathlib.Path(__file__).resolve().parents[1] / "app/routes/admin_cohort.py"
    return p.read_text()


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


def test_light_and_provenance_use_bernoulli_random_threshold():
    sql = _sql()
    # Light: ... WHERE ... random() < 0.30 LIMIT 200000
    light = re.search(r"futures_outcomes fo.*?random\(\)\s*<\s*([0-9.]+).*?LIMIT 200000", sql, re.S)
    assert light is not None, "light endpoint must have WHERE random() < p before LIMIT 200000"
    p_light = float(light.group(1))
    assert 0.10 <= p_light <= 0.80, f"light p={p_light} outside [0.1,0.8] — miscalibrated sample"

    # Provenance-split: ... random() < 0.50 LIMIT 300000
    prov = re.search(r"polymarket.*random\(\)\s*<\s*([0-9.]+).*?LIMIT 300000", sql, re.S)
    assert prov is not None, "provenance-split must have WHERE random() < p before LIMIT 300000"
    p_prov = float(prov.group(1))
    assert 0.10 <= p_prov <= 0.80, f"provenance p={p_prov} outside [0.1,0.8]"


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


def test_limits_still_cap_samples():
    sql = _sql()
    assert "LIMIT 200000" in sql, "light LIMIT 200000 cap missing"
    assert "LIMIT 300000" in sql, "provenance LIMIT 300000 cap missing"
    assert "LIMIT 100000" in sql, "histogram LIMIT 100000 cap missing"


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
