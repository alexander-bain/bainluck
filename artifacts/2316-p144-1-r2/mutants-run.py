import subprocess, sys
from pathlib import Path
W = Path("/Users/bain/bainluck-dev/latency")
RB = "docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md"
GEN = "backend/scripts/season_discovery_admission_sql.py"
RT = "backend/app/routes/events.py"
MD = "backend/app/models/models.py"
M = {
 "m1-route-extra-name-ilike-arm": [(RT, "    sport_filters.append(FuturesMarket.llm_sport_category == llm_category)\n",
     "    sport_filters.append(FuturesMarket.llm_sport_category == llm_category)\n    sport_filters.append(FuturesMarket.name.ilike('%cup%'))\n")],
 "m2-route-tier-list-1-5": [(RT, "                    FuturesMarket.market_tier.in_([1, 2, 3, 4]),\n                )\n                .order_by(FuturesMarket.market_tier, FuturesMarket.id)\n                .limit(400)",
     "                    FuturesMarket.market_tier.in_([1, 2, 3, 4, 5]),\n                )\n                .order_by(FuturesMarket.market_tier, FuturesMarket.id)\n                .limit(400)")],
 "m3-runbook-rename-one-section4-drop": [(RB, "DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sport_id;", "DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sportid;")],
 "m4-runbook-2000-to-20000-and-no-seqscan-line": [(RB, "max_execution_ms = 2000\n", "max_execution_ms = 20000\n"), (RB, "seq_scan_on_futures_markets = none\n", "")],
 "m5-generator-heap-ceiling-30000": [(GEN, '"max_exact_heap_blocks": "3000"', '"max_exact_heap_blocks": "30000"')],
 "m6-runbook-delete-lossy-line": [(RB, "lossy_heap_blocks = 0\n", "")],
 "m7-generator-no-statement-timeout": [(GEN, "            f\"SET statement_timeout = '{GATE_CRITERIA['statement_timeout']}';\",\n", "")],
 "m8-generator-no-plan-only-executions": [(GEN, "PLANS_BEFORE_ANALYZE = 5", "PLANS_BEFORE_ANALYZE = 0")],
 "m9-generator-no-unset-before-gset": [(GEN, '            "\\\\unset sport_ids",\n', "")],
 "m10-models-declare-while-proposed": [(MD, '            "ix_fm_kalshi_resdate_id",', '            "ix_fm_t14_sport_id",')],
 "m11-runbook-state-kept-models-silent": [(RB, "**Index state: PROPOSED**", "**Index state: KEPT**")],
 "m12-runbook-a2-read-by-like": [(RB, " WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');\n```\n\n`IF NOT EXISTS`", " WHERE c.relname LIKE 'ix_fm_t14_%';\n```\n\n`IF NOT EXISTS`")],
 "m13-runbook-p3-null-stats-pass": [(RB, "       coalesce(rows <= 0 OR rows * t14_frac * (1000 + 2 * 40) > 400 * 1024 * 1024, true) AS abort", "       (rows <= 0 OR rows * t14_frac * (1000 + 2 * 40) > 400 * 1024 * 1024) AS abort")],
 "m14-runbook-rollback-no-final-read": [(RB, "-- Last: this read MUST return 0 rows. The rollback is not done until it does.\nSELECT c.relname, i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid\n WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');\n", "")],
 "m15-runbook-no-prepared-xacts-check": [(RB, "SELECT gid, prepared, owner FROM pg_prepared_xacts;\n", "")],
 "m16-runbook-fastupdate-off": [(RB, "WITH (fastupdate = on, gin_pending_list_limit = 4096)", "WITH (fastupdate = off)")],
 "m17-generator-drop-soccer-from-gate-set": [(GEN, '    "soccer_epl",\n', "")],
 "m18-runbook-acceptance-min-calls-1": [(RB, "min_finished_shape_calls = 10\n", "min_finished_shape_calls = 1\n")],
}
names = sys.argv[1:] or list(M)
for name in names:
    touched = set()
    for f, old, new in M[name]:
        p = W / f
        s = p.read_text()
        n = s.count(old)
        if n < 1:
            print(name, "MUTANT DID NOT APPLY", f, repr(old[:60])); break
        p.write_text(s.replace(old, new)); touched.add(f)
    else:
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_season_discovery_index_packet_2316.py", "-q", "-p", "no:cacheprovider"],
                           cwd=W / "backend", capture_output=True, text=True)
        out = r.stdout.strip().splitlines()
        open(f"/tmp/lat2316r-mut/{name}.txt", "w").write(r.stdout + r.stderr)
        print(f"{name}: EXIT {r.returncode} | {out[-1] if out else r.stderr[-200:]}")
    subprocess.run(["git", "-C", str(W), "checkout", "--", *touched])
st = subprocess.run(["git", "-C", str(W), "status", "--short", "--", "backend", "docs"], capture_output=True, text=True).stdout
print("tree after restore (tracked changes):", repr("\n".join(l for l in st.splitlines() if not l.startswith("??"))))
