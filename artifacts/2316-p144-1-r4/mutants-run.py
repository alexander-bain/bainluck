import subprocess, pathlib, sys
R=pathlib.Path("docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md")
G=pathlib.Path("backend/scripts/season_discovery_admission_sql.py")
muts=[
 ("N2 hold >=0",R,"SELECT count(*) = 0 AS no_build_in_flight","SELECT count(*) >= 0 AS no_build_in_flight"),
 ("N2 prose maxq 5000",R,"**Pass: `maxq` ≤ 2,000 ms**","**Pass: `maxq` ≤ 5,000 ms**"),
 ("N2 on-failure drops reader",R,"(mean, size or reader check over its bound)","(mean or size over its bound)"),
 ("N2 at least 1 h",R,"(at least 6 h after the build)","(at least 1 h after the build)"),
 ("N2 one more read",R,"It is not retried for a better number.","Take one more read for a better number."),
 ("N2 no Gather dropped",R,"no `Parallel Bitmap Heap Scan` and no\n`Gather` in any plan","no `Parallel Bitmap Heap Scan` in any plan"),
 ("N2 stmt timeout 1s",R,"\\set ON_ERROR_STOP off\nSET statement_timeout = 0;","\\set ON_ERROR_STOP off\nSET statement_timeout = '1s';"),
 ("N1 drop ON_ERROR_STOP",R,"\\set ON_ERROR_STOP off\n",""),
 ("N1 ON_ERROR_STOP on",R,"\\set ON_ERROR_STOP off\n","\\set ON_ERROR_STOP on\n"),
 ("N3 worst 6 runbook",R,"worst_case_pass_minutes = 18","worst_case_pass_minutes = 6"),
 ("N3 waits 1 generator",G,'"max_lock_waits_per_drop": "3"','"max_lock_waits_per_drop": "1"'),
 ("N3 third-wait cost dropped",R,"an index cancelled at the third wait (`indisvalid = f, indisready = f`) takes\n  no writes and the planner ignores it; ",""),
]
for name,f,a,b in muts:
    orig=f.read_text(); assert orig.count(a)==1,(name,orig.count(a))
    f.write_text(orig.replace(a,b))
    try:
        rc=subprocess.run([sys.executable,"-m","pytest","tests/test_season_discovery_index_packet_2316.py","-q","-x","-p","no:cacheprovider"],cwd="backend",capture_output=True).returncode
    finally:
        f.write_text(orig)
    print(f"{'KILLED' if rc==1 else 'SURVIVED rc=%d'%rc}: {name}")
