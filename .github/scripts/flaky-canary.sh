#!/usr/bin/env bash
# #12252 item 2 — the flaky-canary job: run the quarantined tests (open `Flaky: <id>` issues)
# for real, with every outcome visible, and never block a merge (the job is non-required and
# continue-on-error). Runs from backend/ with the database-integration job's Postgres + Redis
# services; provisions the same pinned pieces the shared tail uses (pg_trgm, redislite).
set -uo pipefail
mapfile -t ids < <(python -c 'import json, os, sys; [print(i) for i in json.loads(os.environ.get("CI_QUARANTINE") or "[]")]')
if [ "${#ids[@]}" -eq 0 ]; then
  echo "No quarantined tests."; exit 0
fi
python - <<'PYPG'
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def provision():
    engine = create_async_engine(os.environ["SEARCH_TEST_DATABASE_URL"])
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    finally:
        await engine.dispose()
asyncio.run(provision())
PYPG
dir="$RUNNER_TEMP/canary-redis"
wheel=redislite-6.2.912183-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
pip download --no-deps --only-binary=:all: redislite==6.2.912183 -d "$dir" >/dev/null
echo "d5ed8af4d03225a9b19e279d40f8d8feae872f87a9cd9f017751864fe7b224c6  $dir/$wheel" | sha256sum -c -
python -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extract('redislite/bin/redis-server', sys.argv[2])" "$dir/$wheel" "$dir"
chmod +x "$dir/redislite/bin/redis-server"
export EVENT_FRAME_REDIS_SERVER="$dir/redislite/bin/redis-server" EVENT_FRAME_REDIS_REQUIRED=1
export CI_QUARANTINE_MODE=canary
python -m pytest "${ids[@]}" -v -rA -p no:cacheprovider > /tmp/flaky-canary.txt 2>&1
status=$?
cat /tmp/flaky-canary.txt
{
  echo "## flaky-canary — ${#ids[@]} quarantined test(s), exit ${status}"
  echo
  grep -E "^(PASSED|FAILED|ERROR) tests/" /tmp/flaky-canary.txt | sed 's/^/- /'
} >> "$GITHUB_STEP_SUMMARY"
grep -E "^(FAILED|ERROR) tests/" /tmp/flaky-canary.txt | while read -r outcome test _; do
  echo "::warning title=flaky-canary (#12252)::${test} ${outcome} — still flaky; its Flaky issue stays open"
done
exit "$status"
