import subprocess, pathlib, sys
R=pathlib.Path("docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md")
G=pathlib.Path("backend/scripts/season_discovery_admission_sql.py")
NEW="""`lock_timeout` restarts for
  each transaction a wait is behind: the second and third waits wait, one after another, on every
  transaction that held a table lock when the wait began, so a wait behind k transactions can last
  up to k × 60 s (lane1b's PG 14 probe: a 4 s `lock_timeout` cancelled at 6.67 s after the
  transaction it first waited on ended at +2.5 s). 18 minutes (3 names × 2 attempts × 3 waits ×
  60 s) is the pass when each wait is behind one transaction. Each further one can add up to 60 s.
  The pass still ends, because each wait's list is fixed when the wait begins, and its end state is
  the final read, not a clock.
"""
OLD="""So one attempt on one name can
  take about 3 × 60 s, and the whole pass at worst about 3 names × 2 attempts × 3 waits × 60 s =
  18 minutes.
"""
muts=[
 ("N3' lane1b: restore 'whole pass at worst ... 18 minutes'",R,NEW,OLD),
 ("N3' restore old sentence beside the new one",R,NEW,NEW+"  So the whole pass at worst takes about 18 minutes.\n"),
 ("N3' restore worst_case_pass_minutes key (runbook)",R,"pass_minutes_if_one_holder_per_wait = 18","worst_case_pass_minutes = 18"),
 ("N3' restore worst_case_pass_minutes key (generator)",G,'"pass_minutes_if_one_holder_per_wait"','"worst_case_pass_minutes"'),
 ("N3' each_further_holder_adds 0s (runbook)",R,"each_further_holder_adds = 60s","each_further_holder_adds = 0s"),
 ("N3' drop each_further_holder_adds (generator)",G,'    "each_further_holder_adds": "60s",\n',""),
 ("N3' drop 'restarts for each transaction'",R,"`lock_timeout` restarts for\n  each transaction a wait is behind","`lock_timeout` bounds\n  each wait"),
 ("N3' k x 60 s -> 60 s",R,"can last\n  up to k × 60 s","can last\n  up to 60 s"),
 ("N3' drop 'Each further one can add'",R," Each further one can add up to 60 s.",""),
 ("N3' end state is a clock",R,"the final read, not a clock.","18 minutes."),
 ("N3 pass minutes 6",R,"pass_minutes_if_one_holder_per_wait = 18","pass_minutes_if_one_holder_per_wait = 6"),
 ("N3 waits 1 generator",G,'"max_lock_waits_per_drop": "3"','"max_lock_waits_per_drop": "1"'),
]
for name,f,a,b in muts:
    orig=f.read_text(); assert orig.count(a)==1,(name,orig.count(a))
    f.write_text(orig.replace(a,b))
    try:
        rc=subprocess.run([sys.executable,"-m","pytest","tests/test_season_discovery_index_packet_2316.py","-q","-x","-p","no:cacheprovider"],cwd="backend",capture_output=True).returncode
    finally:
        f.write_text(orig)
    print(f"{'KILLED' if rc==1 else 'SURVIVED rc=%d'%rc}: {name}")
