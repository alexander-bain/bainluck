#!/usr/bin/env bash
# #11681 DIAGNOSTIC ONLY, DO NOT MERGE. Read-only observation around the
# shared-tail #11138 held-row step. Usage: l1diag.sh pre|post (cwd: backend/).
# Kept out of ci.yml because that file sits ~2.3 KB under GitHub's 512 KB
# workflow-file limit.
set -u
D="$GITHUB_WORKSPACE/.github/diagnostics"
O="$RUNNER_TEMP/l1obs"
mkdir -p "$O"
pg() { python - "$@" <<'PY'
import asyncio, os, sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def main(stmts, autocommit):
    kw = {"isolation_level": "AUTOCOMMIT"} if autocommit else {}
    e = create_async_engine(os.environ["SEARCH_TEST_DATABASE_URL"], **kw)
    try:
        async with e.connect() as c:
            for q in stmts:
                r = await c.execute(text(q))
                print(q, "=", r.scalar() if r.returns_rows else "ok")
    finally:
        await e.dispose()
asyncio.run(main(sys.argv[2:], sys.argv[1] == "ac"))
PY
}
case "$1" in
pre)
  {
    echo "head=$(git rev-parse HEAD) tree=$(git rev-parse 'HEAD^{tree}')"
    python -c "import sys, sqlalchemy, asyncpg, greenlet, gc; print(sys.version); print('sqlalchemy', sqlalchemy.__version__, 'asyncpg', asyncpg.__version__, 'greenlet', greenlet.__version__, 'gc_threshold', gc.get_threshold())"
    nproc; lscpu | grep -E 'Model name|^CPU\(s\)|Thread|MHz|Hypervisor'
    cat /proc/pressure/cpu
    pg ro "select version()" "show synchronous_commit" "show fsync" "show wal_sync_method" "show shared_buffers" "select count(*) from pg_namespace"
  } > "$O/manifest.txt" 2>&1
  cat "$O/manifest.txt"
  # Per-database statement durations, parameters suppressed; reset in post.
  pg ac "ALTER DATABASE bl_searchtest SET log_parameter_max_length = 0" \
        "ALTER DATABASE bl_searchtest SET log_min_duration_statement = 0" || echo "::warning::#11681 statement log not enabled"
  pg ro "show log_min_duration_statement" "show log_parameter_max_length" "show log_line_prefix"
  cid=$(docker ps --filter "ancestor=postgres:15" -q | head -1)
  full=$(docker inspect -f '{{.Id}}' "$cid")
  stat=$(ls /sys/fs/cgroup/system.slice/docker-"$full".scope/cpu.stat 2>/dev/null || echo -)
  printf '%s\n%s\n' "$cid" "$stat" > "$O/pg-container.txt"
  date -u +%Y-%m-%dT%H:%M:%S.%3NZ > "$O/held-row-step-start.txt"
  nohup python -I "$D/l1sampler.py" "$O/host-100ms.csv" "$stat" 1200 > /dev/null 2>&1 &
  echo $! > "$O/sampler.pid"
  # Only the held-row step loads the plugin (-p l1observe); post clears these.
  echo "PYTHONPATH=$D" >> "$GITHUB_ENV"
  echo "L1OBS_OUT=$O/observer.json" >> "$GITHUB_ENV"
  ;;
post)
  date -u +%Y-%m-%dT%H:%M:%S.%3NZ > "$O/held-row-step-end.txt"
  kill "$(cat "$O/sampler.pid" 2>/dev/null)" 2>/dev/null
  pg ac "ALTER DATABASE bl_searchtest RESET log_min_duration_statement" \
        "ALTER DATABASE bl_searchtest RESET log_parameter_max_length"
  echo "PYTHONPATH=" >> "$GITHUB_ENV"
  cp /tmp/held-row11138.txt "$O/" 2>/dev/null
  cid=$(head -1 "$O/pg-container.txt" 2>/dev/null)
  if [ -n "$cid" ]; then
    docker logs "$cid" 2>&1 | python -I "$D/l1pglog.py" | gzip > "$O/pg-timings.csv.gz"
  fi
  # Redaction control: no parameters, passwords or connection strings uploaded.
  # (held-row11138.txt is the gate's own output, already printed in the job log.)
  for f in "$O"/*; do
    case "$f" in */held-row11138.txt) continue ;; esac
    if zcat -f "$f" | grep -aqE 'postgres:postgres|parameters:|postgresql\+asyncpg'; then
      echo "::error::#11681 redaction control failed for $(basename "$f"); withheld"
      rm -f "$f"; echo withheld > "$f.WITHHELD"
    fi
  done
  ls -la "$O"
  exit 0
  ;;
esac
