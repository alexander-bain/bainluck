#!/bin/bash
# Fleet status, pause/resume and workday/quiet/full capacity.
exec python3 "$(cd "$(dirname "$0")" && pwd)/scripts/lane_control.py" "$@"
