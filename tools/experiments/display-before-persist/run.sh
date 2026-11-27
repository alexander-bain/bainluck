#!/usr/bin/env bash
# Own a disposable local cluster. Never use an existing database or credentials.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
if [[ -z "${PG_BIN:-}" ]]; then
  if command -v pg_ctl >/dev/null 2>&1; then
    PG_BIN="$(dirname "$(command -v pg_ctl)")"
  elif command -v pg_config >/dev/null 2>&1; then
    PG_BIN="$(pg_config --bindir)"
  else
    echo 'Set PG_BIN to the installed PostgreSQL directory containing initdb and pg_ctl.' >&2
    exit 2
  fi
fi
BIN="$(cd "$PG_BIN" && pwd)"
for executable in initdb pg_ctl; do
  [[ -x "$BIN/$executable" ]] || { echo "Missing $BIN/$executable" >&2; exit 2; }
done
[[ -d node_modules/pg ]] || { echo 'Run npm ci --ignore-scripts in this experiment first.' >&2; exit 2; }
mkdir -p .runtime local-results
DATA="$(mktemp -d "$ROOT/.runtime/pg-XXXXXX")"
OUT="$ROOT/local-results/$(basename "$DATA")"
mkdir -p "$OUT"
export PGPORT="${PGPORT:-55491}"
export DISPLAY_PERSIST_OWNED_PGDATA="$DATA"
# Validate before appending to postgresql.conf. Fixed loopback is intentional.
[[ "$PGPORT" =~ ^[0-9]+$ ]] && (( PGPORT > 1023 && PGPORT < 65536 )) || {
  echo 'PGPORT must be an integer from 1024 to 65535.' >&2; exit 2;
}
cleanup() {
  # On start failure, this exact owned data directory still cannot stop another server.
  if "$BIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
    "$BIN/pg_ctl" -D "$DATA" -m immediate -w stop > "$OUT/cleanup.log" 2>&1 || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
INIT_ARGS=(-D "$DATA" --auth=trust --no-locale --encoding=UTF8)
[[ -z "${PG_SHARE:-}" ]] || INIT_ARGS+=(-L "$PG_SHARE")
"$BIN/initdb" "${INIT_ARGS[@]}" > "$OUT/initdb.log"
printf "\nlisten_addresses='127.0.0.1'\nunix_socket_directories=''\nport=%s\nfsync=on\nsynchronous_commit=on\n" "$PGPORT" >> "$DATA/postgresql.conf"
"$BIN/pg_ctl" -D "$DATA" -l "$OUT/postgres.log" -w start
node --test --test-concurrency=1 checks/unit.mjs checks/postgres.mjs 2>&1 | tee "$OUT/tests.tap"
printf 'Passed. Local receipts: %s\n' "$OUT"
# Keep the stopped data directory available for inspection; it is gitignored.
