#!/bin/bash
# LAT-P243 second method: does a real user typing a HEAD term hit a cold read?
# Cycles across head terms so each is revisited every ~13 min — far rarer than the
# warmer's ~40s pass — so the probe does not warm what it measures.
# Excludes 'sta'/'red': #3399's shed makes those two unrepresentative of the head.
source ~/.claude/.env
END=$1
TERMS=('stanley cup' 'masters winner' 'world series' 'world cup' 'red sox' 'chiefs'
       'nba champion' 'yankees' 'grammys' "ballon d'or" 'oscars' 'fed' 'pats'
       'tennis' 'revs' 'us open' 'celtics' 'lakers' 'us recession 2026' 'lebron james'
       'carlos alcaraz' 'ben shelton' 'boston red sox' 'red sox world series')
i=0
while [ "$(date +%s)" -lt "$END" ]; do
  Q="${TERMS[$((i % ${#TERMS[@]}))]}"
  ENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$Q")
  T=$(curl -s -m 25 -o /dev/null -w '%{time_total}' "$BAINLUCK_API/api/events/typeahead?q=$ENC")
  printf '{"at":%s,"q":"%s","time_total_s":%s}\n' "$(date +%s)" "${Q//\"/}" "$T" >> .lat247-headprobe.jsonl
  i=$((i+1)); sleep 20
done
