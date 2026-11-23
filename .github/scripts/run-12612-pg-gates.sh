#!/usr/bin/env bash
# #12612: run root-level Postgres-gated test files with fail-on-skip enforcement.
# Kept outside ci.yml to preserve workflow-file byte headroom under GitHub's 512 KB cap.
set -euo pipefail
mode="$1"
shift
if [ "$mode" = "cal" ]; then
  python - <<'PY'
import asyncio, asyncpg
async def go():
    c = await asyncpg.connect(user="postgres", password="postgres", database="postgres", host="localhost", port=5432)
    await c.execute("DROP DATABASE IF EXISTS bl_cal12612")
    await c.execute("CREATE DATABASE bl_cal12612")
    await c.close()
asyncio.run(go())
PY
fi
log="/tmp/gate12612_${mode}.txt"
python -m pytest "$@" -v -rs > "$log" 2>&1 || { cat "$log"; exit 1; }
cat "$log"
if grep -qiE "[0-9]+ skipped" "$log"; then
  echo "::error::#12612 real-Postgres gate (${mode}) skipped"
  exit 1
fi
grep -qE "[^0-9][1-9][0-9]* passed([,[:space:]]|$)" "$log" || {
  echo "::error::#12612 real-Postgres gate (${mode}) ran no tests"
  exit 1
}
