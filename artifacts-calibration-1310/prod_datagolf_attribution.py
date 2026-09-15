"""#6211 — run the REAL population CTE chain on production, scoped to DataGolf.

``market_info_extra`` narrows ``market_info`` to ``source = 'datagolf'``, which
cascades through every downstream CTE, so the scan is the 340 DataGolf markets and
their ~57k outcomes rather than the whole futures universe. Prints the first
``deduped`` reason for every candidate row, by market kind — the attribution the
issue says is the fix's first task.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
)

REASON_SQL = """
    CASE
      WHEN NOT is_liquid THEN 'illiquid'
      WHEN is_poly_placeholder THEN 'poly_placeholder'
      WHEN is_below_writer_bar THEN 'below_writer_bar'
      WHEN is_malformed_binary THEN 'malformed_binary'
      WHEN is_esports_bundle THEN 'esports_bundle'
      WHEN is_player_props_placeholder THEN 'player_props_placeholder'
      WHEN is_golf_placeholder THEN 'golf_placeholder'
      WHEN is_kalshi_prop_threshold THEN 'kalshi_prop_threshold'
      WHEN is_weather_wide_spread THEN 'weather_wide_spread'
      WHEN is_no_winner_market THEN 'no_winner_market'
      WHEN is_draw_authority_missing THEN 'draw_authority_missing'
      WHEN is_orphan_partition THEN 'orphan_partition'
      WHEN is_identity_disputed THEN 'identity_disputed'
      WHEN is_field_incomplete THEN 'field_incomplete'
      WHEN is_mex_normalized THEN 'PUBLISHED_mex_normalized'
      WHEN is_threshold_ladder AND rn <> 1 THEN 'ladder_non_representative'
      WHEN is_threshold_ladder THEN 'PUBLISHED_ladder'
      WHEN is_multi AND adj_opening_probability <= 0.005 THEN 'multi_tail_lo'
      WHEN is_multi AND adj_opening_probability >= 0.98 THEN 'multi_head_hi'
      WHEN is_multi AND mp_hit THEN 'multi_modal_price'
      WHEN is_multi THEN 'PUBLISHED_multi'
      WHEN rn <> 1 THEN 'non_representative_rn'
      ELSE 'PUBLISHED_rn1'
    END"""

ctes = _calibration_population_ctes(market_info_extra="AND fm.source = 'datagolf'")

SQL = (
    "WITH "
    + ctes
    + """, mp_flagged AS (
        SELECT ro.*, (mp.vm_id IS NOT NULL) AS mp_hit
        FROM normalized ro
        LEFT JOIN mode_prices mp
          ON mp.vm_id = ro.vm_id AND mp.source = ro.source
         AND mp.mode_price = ro.adj_opening_probability
    )
    SELECT split_part(mkt.external_id, ':', 4) AS kind,
           """
    + REASON_SQL
    + """ AS reason,
           (f.calibration_probability IS NOT NULL
            AND f.calibration_probability IS DISTINCT FROM f.opening_probability)
             AS price_moved,
           COUNT(*) AS n,
           COUNT(*) FILTER (WHERE mp_flagged.is_winner) AS w
    FROM mp_flagged
    JOIN futures_markets mkt ON mkt.id = mp_flagged.market_id
    JOIN futures_outcomes f ON f.id = mp_flagged.outcome_id
    GROUP BY 1, 2, 3
    ORDER BY n DESC"""
)

# The generated CTEs carry ~3k lines of prose comments, and a `;` inside one
# trips db-query's multi-statement guard. Drop whole comment lines only (a
# trailing `--` on a code line would need string-literal awareness).
SQL = "\n".join(
    ln for ln in SQL.splitlines() if not ln.lstrip().startswith("--")
)
assert ";" not in SQL, "a `;` survives outside a comment line"

body = json.dumps({"sql": SQL, "limit": 300})
env = os.environ
out = subprocess.run(
    [
        "curl", "-s", "--max-time", "120", "-X", "POST",
        "-H", f"Authorization: Bearer {env['ADMIN_TOKEN']}",
        "-H", "Content-Type: application/json",
        f"{env['BAINLUCK_API']}/api/admin/db-query",
        "-d", body,
    ],
    capture_output=True, text=True,
)
d = json.loads(out.stdout)
if "rows" not in d:
    print(json.dumps(d)[:1500])
    raise SystemExit(1)

print(f"duration_ms={d['duration_ms']}  rows={d['row_count']}  truncated={d['truncated']}")
print(f"{'kind':10s} {'reason':28s} {'moved':6s} {'n':>7s} {'w':>7s}")
tot = totw = pub = pubw = 0
for kind, reason, moved, n, w in sorted(d["rows"], key=lambda r: (str(r[0]), -r[3])):
    print(f"{str(kind):10s} {reason:28s} {str(moved):6s} {n:7d} {w:7d}")
    tot += n
    totw += w
    if reason.startswith("PUBLISHED"):
        pub += n
        pubw += w
print(f"\nCANDIDATES {tot} ({totw} winners)   PUBLISHED {pub} ({pubw} winners)")
