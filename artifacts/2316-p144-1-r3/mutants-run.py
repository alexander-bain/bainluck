import subprocess, sys
from pathlib import Path
W = Path("/Users/bain/bainluck-dev/latency")
RB = "docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md"
GEN = "backend/scripts/season_discovery_admission_sql.py"
MD = "backend/app/models/models.py"
DROPS2 = ("-- Attempt 2 of 2, the last.\nDROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_external_id_trgm;\n"
          "DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_llm_sport_category;\nDROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sport_id;\n")
# name -> (expected exit, edits). Expected 1 = the guard must kill it; 0 = control.
M = {
 "r1a-a-gen-no-serial-set": (1, [(GEN, 'GATE_SESSION_SETTINGS = ("statement_timeout", "max_parallel_workers_per_gather")', 'GATE_SESSION_SETTINGS = ("statement_timeout",)')]),
 "r1a-b-gen-workers-2": (1, [(GEN, '"max_parallel_workers_per_gather": "0",', '"max_parallel_workers_per_gather": "2",')]),
 "r1a-c-runbook-no-parallel-line": (1, [(RB, "parallel_bitmap_heap_scan = none\n", "")]),
 "r1a-d-gen-no-parallel-key": (1, [(GEN, '    "parallel_bitmap_heap_scan": "none",\n', "")]),
 "r1a-e-runbook-no-workers-line": (1, [(RB, "max_parallel_workers_per_gather = 0\n", "")]),
 "r1b-a-runbook-maxq-20000": (1, [(RB, "reader_check_max_maxq_ms = 2000\n", "reader_check_max_maxq_ms = 20000\n")]),
 "r1b-b-runbook-no-unmeasured-line": (1, [(RB, "reader_check_none_in_window = UNMEASURED\n", "")]),
 "r1b-c-gen-no-owner": (1, [(GEN, '    "reader_check_taken_by": "latency",\n', "")]),
 "r1b-d-all3-maxq-5000": (1, [(RB, "reader_check_max_maxq_ms = 2000\n", "reader_check_max_maxq_ms = 5000\n"),
     (GEN, '"reader_check_max_maxq_ms": "2000"', '"reader_check_max_maxq_ms": "5000"'),
     ("backend/tests/test_season_discovery_index_packet_2316.py", '"reader_check_max_maxq_ms": "2000"', '"reader_check_max_maxq_ms": "5000"')]),
 "r6-a-s4-until-sentence": (1, [(RB, "The second attempt is the last; there is no third.", "Re-run the DROP until the final read returns 0 rows.")]),
 "r6-b-a2-reread-until": (1, [(RB, "If P1c shows a row, read it once a minute for at most 10 minutes.", "Re-read P1c until it returns no row.")]),
 "r6-c-a2-repeat-step2": (1, [(RB, "If it is still there, run step 2 a second time, once.", "If it is still there, repeat step 2.")]),
 "r6-d-s4-no-attempt-2": (1, [(RB, DROPS2, "")]),
 "r6-e-s4-third-attempt": (1, [(RB, DROPS2, DROPS2 + DROPS2.replace("-- Attempt 2 of 2, the last.", "-- Attempt 3."))]),
 "r6-f-s4-no-if-gate": (1, [(RB, "\\if :no_build_in_flight\n", "")]),
 "r6-g-s4-no-unset": (1, [(RB, "\\unset no_build_in_flight\n", "")]),
 "r6-h-runbook-bounds-3-attempts": (1, [(RB, "max_drop_attempts_per_index = 2\n", "max_drop_attempts_per_index = 3\n")]),
 "r6-i-gen-reread-60min": (1, [(GEN, '"a2_p1c_reread_max_minutes": "10"', '"a2_p1c_reread_max_minutes": "60"')]),
 "r6-j-a2-prose-60min": (1, [(RB, "for at most 10 minutes.", "for at most 60 minutes.")]),
 "r6-k-hold-branch-drops": (1, [(RB, "\\echo HOLD: an index build is in flight on futures_markets. Nothing was dropped.\n",
     "\\echo HOLD: an index build is in flight on futures_markets. Nothing was dropped.\nDROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sport_id;\n")]),
 "r6-l-final-read-inside-if": (1, [(RB, "\\endif\n-- Final read. 0 rows: ROLLED BACK. Any row: ROLLBACK INCOMPLETE. Nothing runs after it.\n",
     "-- Final read. 0 rows: ROLLED BACK. Any row: ROLLBACK INCOMPLETE. Nothing runs after it.\n"),
     (RB, " WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');\n```\n\n```text rollback-bounds",
      " WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');\n\\endif\n```\n\n```text rollback-bounds")]),
 "r6-m-no-on-error-stop-off": (1, [(RB, "with psql's default `ON_ERROR_STOP` **off**, so", "so")]),
 "r6-n-incomplete-models-declare": (1, [(RB, "**Index state: PROPOSED**", "**Index state: ROLLBACK INCOMPLETE**"),
     (MD, '            "ix_fm_kalshi_resdate_id",', '            "ix_fm_t14_sport_id",')]),
 "r6-o-no-operator": (1, [(RB, "The operator is Alex.", "")]),
 "CONTROL-incomplete-models-silent": (0, [(RB, "**Index state: PROPOSED**", "**Index state: ROLLBACK INCOMPLETE**")]),
}
names = sys.argv[1:] or list(M)
FILES = {f for _, edits in M.values() for f, _, _ in edits}
ORIG = {f: (W / f).read_text() for f in FILES}  # restored byte-for-byte after every mutant
bad = 0
for name in names:
    want, edits = M[name]
    applied = True
    for f, old, new in edits:
        p = W / f
        s = p.read_text()
        if s.count(old) != 1:
            print(name, "MUTANT DID NOT APPLY", f, repr(old[:60])); bad += 1; applied = False; break
        p.write_text(s.replace(old, new))
    if applied:
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_season_discovery_index_packet_2316.py", "-q", "-p", "no:cacheprovider"],
                           cwd=W / "backend", capture_output=True, text=True)
        out = r.stdout.strip().splitlines()
        open(f"/tmp/lat2316r3-mut/{name}.txt", "w").write(r.stdout + r.stderr)
        ok = r.returncode == want
        bad += not ok
        print(f"{name}: EXIT {r.returncode} (want {want}) {'OK' if ok else 'WRONG'} | {out[-1] if out else r.stderr[-200:]}")
    for f, text in ORIG.items():
        (W / f).write_text(text)
print("restored:", all((W / f).read_text() == t for f, t in ORIG.items()))
print("wrong outcomes:", bad)
