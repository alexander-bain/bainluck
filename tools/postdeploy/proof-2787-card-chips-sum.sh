#!/usr/bin/env bash
# live/054 — post-deploy proof for #2787 (the 4th arm of #2084).
#
# ## Why this cannot be an API assertion, unlike proof-2084-duel-sum.sh
#
# #2084's fix moved the decision to the SERVER, so its proof reads two integers
# out of `/api/feed` and adds them up. #2787's defect is the opposite shape: the
# server's numbers were already right and the shared `components/EventCard.tsx`
# rounded each side again, alone, inside `AnimatedProbability`'s `useTransform`.
# Nothing in any payload can show that. The two numbers only ever disagree ON
# SCREEN, so the proof has to read the screen.
#
# ## What it asserts
#
# For every card on a league rail that prints TWO percentages, those two
# percentages sum to exactly 100. The pre-fix production reading on
# /sports/tennis_atp_us_open (2026-09-03, `842e6167`) was three cards at 101:
# 82/19, 20/81 and 18/83.
#
# It also asserts the page printed some pairs at all. Zero pairs is the shape a
# blank page and a perfect page share, and reporting "0 violations" over an
# empty list is the failure mode this script most needs to refuse.
#
#   tools/postdeploy/proof-2787-card-chips-sum.sh [url ...]

set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

URLS=("$@")
if [ ${#URLS[@]} -eq 0 ]; then
  URLS=(
    "https://www.bainluck.com/sports/tennis_atp_us_open"
    "https://www.bainluck.com/sports/baseball_mlb"
  )
fi

node tools/card-chip-sum.mjs "${URLS[@]}"
