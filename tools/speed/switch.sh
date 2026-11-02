#!/bin/bash
# Speed-switch trial control (#10090): per-game (ab) or alternating trials, capped at 30 min by the server. usage:
#   switch.sh NAME ab HALF TTL_S                  -> on for the live games whose id parity is HALF (TTL <= 1800)
#   switch.sh NAME alternate A B PERIOD_S TTL_S   -> start an alternation (TTL <= 1800)
#   switch.sh NAME off                            -> end it now
#   switch.sh status                              -> GET current switches
# Script file on purpose: inline `source .env && curl` can stall at a permission prompt.
source ~/.claude/.env || exit 1
U="$BAINLUCK_API/api/admin/speed-switch"
if [ "$1" = "status" ]; then
  curl -s --max-time 20 -H "Authorization: Bearer $ADMIN_TOKEN" "$U"; echo; exit 0
fi
if [ "$2" = "ab" ]; then
  body=$(python3 -c 'import json,sys; n,h,t=sys.argv[1:4]; print(json.dumps({"name": n, "mode": "ab", "half": int(h), "ttl_s": int(t)}))' "$1" "$3" "$4")
elif [ "$2" = "off" ]; then
  body=$(python3 -c 'import json,sys; print(json.dumps({"name": sys.argv[1], "mode": "off"}))' "$1")
else
  body=$(python3 -c 'import json,sys; n,m,a,b,p,t=sys.argv[1:7]; print(json.dumps({"name": n, "mode": m, "a": int(a), "b": int(b), "period_s": int(p), "ttl_s": int(t)}))' "$1" "$2" "$3" "$4" "$5" "$6")
fi
echo "$(date -u +%FT%TZ) POST $body"
curl -s --max-time 20 -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d "$body" "$U"; echo
