"""#6211 — bisect WHERE the DataGolf population dies, CTE by CTE, on production."""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
    calibration_truth_eligible_sql,
)

ctes = _calibration_population_ctes(market_info_extra="AND fm.source = 'datagolf'")

SQL = (
    "WITH "
    + ctes
    + f""",
    probe AS (
      SELECT 'A market_info markets' AS step, COUNT(*)::bigint AS n FROM market_info
      UNION ALL SELECT 'B virtual_market markets', COUNT(*) FROM virtual_market
      UNION ALL SELECT 'C vm_stats vms', COUNT(*) FROM vm_stats
      UNION ALL SELECT 'D clean_vms vms', COUNT(*) FROM clean_vms
      UNION ALL SELECT 'E outcomes of market_info markets', COUNT(*)
                  FROM futures_outcomes fo JOIN market_info mi ON mi.market_id = fo.market_id
      UNION ALL SELECT 'F   + opening_probability in (0,1)', COUNT(*)
                  FROM futures_outcomes fo JOIN market_info mi ON mi.market_id = fo.market_id
                  WHERE fo.opening_probability IS NOT NULL
                    AND fo.opening_probability > 0 AND fo.opening_probability < 1
      UNION ALL SELECT 'G   + truth-eligible source', COUNT(*)
                  FROM futures_outcomes fo JOIN market_info mi ON mi.market_id = fo.market_id
                  LEFT JOIN market_result_shape mrs ON mrs.market_id = fo.market_id
                  WHERE fo.opening_probability IS NOT NULL
                    AND fo.opening_probability > 0 AND fo.opening_probability < 1
                    AND {calibration_truth_eligible_sql(n_outcomes_col='mrs.n_outcomes')}
      UNION ALL SELECT 'H   + join virtual_market', COUNT(*)
                  FROM futures_outcomes fo JOIN virtual_market vm ON vm.market_id = fo.market_id
                  LEFT JOIN market_result_shape mrs ON mrs.market_id = fo.market_id
                  WHERE fo.opening_probability IS NOT NULL
                    AND fo.opening_probability > 0 AND fo.opening_probability < 1
                    AND {calibration_truth_eligible_sql(n_outcomes_col='mrs.n_outcomes')}
      UNION ALL SELECT 'I   + join clean_vms (5 cols)', COUNT(*)
                  FROM futures_outcomes fo JOIN virtual_market vm ON vm.market_id = fo.market_id
                  JOIN clean_vms cv ON cv.vm_id = vm.vm_id AND cv.source = vm.source
                   AND cv.category IS NOT DISTINCT FROM vm.category
                   AND cv.is_grouped IS NOT DISTINCT FROM vm.is_grouped
                   AND cv.mutually_exclusive IS NOT DISTINCT FROM vm.mutually_exclusive
                  LEFT JOIN market_result_shape mrs ON mrs.market_id = fo.market_id
                  WHERE fo.opening_probability IS NOT NULL
                    AND fo.opening_probability > 0 AND fo.opening_probability < 1
                    AND {calibration_truth_eligible_sql(n_outcomes_col='mrs.n_outcomes')}
      UNION ALL SELECT 'J ranked_outcomes', COUNT(*) FROM ranked_outcomes
      UNION ALL SELECT 'K normalized', COUNT(*) FROM normalized
      UNION ALL SELECT 'L deduped', COUNT(*) FROM deduped
    )
    SELECT step, n FROM probe ORDER BY step"""
)

SQL = "\n".join(ln for ln in SQL.splitlines() if not ln.lstrip().startswith("--"))
assert ";" not in SQL

env = os.environ
out = subprocess.run(
    ["curl", "-s", "--max-time", "180", "-X", "POST",
     "-H", f"Authorization: Bearer {env['ADMIN_TOKEN']}",
     "-H", "Content-Type: application/json",
     f"{env['BAINLUCK_API']}/api/admin/db-query",
     "-d", json.dumps({"sql": SQL, "limit": 50})],
    capture_output=True, text=True,
)
d = json.loads(out.stdout)
if "rows" not in d:
    print(json.dumps(d)[:2000])
    raise SystemExit(1)
print(f"duration_ms={d['duration_ms']}")
for step, n in d["rows"]:
    print(f"  {step:40s} {n:8d}")
