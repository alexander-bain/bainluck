#!/bin/bash
cd "$(dirname "$0")"; source ~/.claude/.env
curl -s -m 40 -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -H "x-bainluck-origin: agent-latency" -X POST "$BAINLUCK_API/api/admin/db-query" --data @"$1" > "$2"; echo "EXIT $?"
