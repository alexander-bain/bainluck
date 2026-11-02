#!/usr/bin/env bash
# Own disposable loopback PostgreSQL only. No production credentials accepted.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
NODE_BIN="${NODE_BIN:-node}"
command -v "$NODE_BIN" >/dev/null || { echo 'Node >=22 required.' >&2; exit 2; }
"$NODE_BIN" -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(2)'
if [[ -z "${PG_BIN:-}" ]]; then
 if command -v pg_ctl >/dev/null; then PG_BIN="$(dirname "$(command -v pg_ctl)")";
 elif command -v pg_config >/dev/null; then PG_BIN="$(pg_config --bindir)";
 else echo 'Set PG_BIN to installed PostgreSQL initdb/pg_ctl directory.' >&2; exit 2; fi
fi
BIN="$(cd "$PG_BIN" && pwd)"
[[ -x "$BIN/pg_ctl" && -x "$BIN/initdb" ]] || { echo 'Missing PostgreSQL tools.' >&2; exit 2; }
[[ -d node_modules/pg ]] || { echo 'Run npm ci --ignore-scripts inside this module first.' >&2; exit 2; }
export PGPORT="${PGPORT:-55492}"
[[ "$PGPORT" =~ ^[0-9]+$ ]] && ((PGPORT>1023 && PGPORT<65536)) || { echo 'Invalid PGPORT.' >&2; exit 2; }
RUN="$(date -u +%Y%m%dT%H%M%SZ)-$$"
DATA="$ROOT/runtime/$RUN-pgdata"; OUT="$ROOT/results/$RUN"
mkdir -p "$ROOT/runtime" "$OUT"
mkdir -m 700 "$DATA"
export OUT OWNED_ROOT="$ROOT" OWNED_PGDATA="$DATA" OWNED_PGBIN="$BIN"
cleanup(){
 if "$BIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
  "$BIN/pg_ctl" -D "$DATA" -m immediate -w stop > "$OUT/cleanup.log" 2>&1 || true
 fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
ARGS=(-D "$DATA" --auth=trust --no-locale --encoding=UTF8)
[[ -z "${PG_SHARE:-}" ]] || ARGS+=(-L "$PG_SHARE")
"$BIN/initdb" "${ARGS[@]}" > "$OUT/initdb.log"
printf "\nlisten_addresses='127.0.0.1'\nunix_socket_directories=''\nport=%s\nfsync=on\nsynchronous_commit=on\n" "$PGPORT" >> "$DATA/postgresql.conf"
"$BIN/pg_ctl" -D "$DATA" -l "$OUT/postgres.log" -w start
"$NODE_BIN" --test --test-concurrency=1 src/test.mjs | tee "$OUT/tests.tap"
REVIEW_TMP="$OUT/independent" "$NODE_BIN" --test review/test_recovery_adversarial.mjs | tee "$OUT/independent.tap"
"$NODE_BIN" src/outage.mjs | tee "$OUT/outage.log"
"$NODE_BIN" src/benchmark.mjs | tee "$OUT/benchmark.log"
printf '%s\n' "$OUT" > results/LATEST
printf 'Passed. Disposable cluster will stop; receipts: %s\n' "$OUT"
