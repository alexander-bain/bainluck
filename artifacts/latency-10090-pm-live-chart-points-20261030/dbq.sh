#!/bin/bash
# usage: dbq.sh NAME  (reads NAME.sql, writes NAME.out.json) — read-only admin db-query
cd "$(dirname "$0")"
source ~/.claude/.env
python3 - "$1" <<'PY' > "$1.req.json"
import json,sys; print(json.dumps({"sql":open(sys.argv[1]+".sql").read(),"limit":500}))
PY
curl -s -m 40 -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -H "x-bainluck-origin: agent-latency" \
  -X POST "$BAINLUCK_API/api/admin/db-query" --data @"$1.req.json" > "$1.out.json"
echo "EXIT $?"; rm -f "$1.req.json"
head -c 6000 "$1.out.json"; echo
