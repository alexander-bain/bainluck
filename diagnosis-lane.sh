#!/bin/bash
# Dedicated TBH diagnosis worker. Does not alter or restart the build lanes.
set -euo pipefail
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${DIAGNOSIS_PYTHON:-/usr/local/bin/python3}"
RUNNER="$SELF_DIR/tools/diagnosis/runner.py"
case "${1:-status}" in
  status|once|dry-run)
    exec "$PYTHON" "$RUNNER" "${1:-status}" ;;
  start|stop)
    exec "$PYTHON" "$SELF_DIR/tools/diagnosis/service.py" "$1" ;;
  window)
    exec "$PYTHON" "$SELF_DIR/tools/diagnosis/window.py" ;;
  watch)
    exec "$PYTHON" -u "$SELF_DIR/tools/diagnosis/monitor.py" ;;
  *) echo "Usage: $0 {start|stop|status|once|dry-run|window|watch}" >&2; exit 2 ;;
esac
