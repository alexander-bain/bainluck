import subprocess, pathlib, sys
R=pathlib.Path("docs/audits/latency/2316-p144-1-season-discovery-index-runbook.md")
NEW368="`lock_timeout` bounds each lock request, and one DROP waits up to three times:"
NEW246="bounds each of its lock\n   requests; §4 says how long a DROP can wait)."
muts=[
 ("N3a lane1b: restore 'bounds each *wait*' at line 368",R,NEW368,"`lock_timeout` bounds each *wait*, and one DROP waits up to three times:"),
 ("N3a restore 'bounds each *wait*' beside the new clause",R,NEW368,NEW368.replace("waits up to three times:","waits up to three times (it bounds each *wait*):")),
 ("N3a drop the clause's subject (bounds each wait, unemphasised)",R,"bounds each lock request, and","bounds each wait, and"),
 ("N3a optional: restore line 246 'bounds it)'",R,NEW246,"bounds it)."),
 ("N3a optional: drop the §4 pointer at line 246",R,"; §4 says how long a DROP can wait","")
]
for name,f,a,b in muts:
    orig=f.read_text(); assert orig.count(a)==1,(name,orig.count(a))
    f.write_text(orig.replace(a,b))
    try:
        rc=subprocess.run([sys.executable,"-m","pytest","tests/test_season_discovery_index_packet_2316.py","-q","-x","-p","no:cacheprovider"],cwd="backend",capture_output=True).returncode
    finally:
        f.write_text(orig)
    print(f"{'KILLED' if rc==1 else 'SURVIVED rc=%d'%rc}: {name}")
