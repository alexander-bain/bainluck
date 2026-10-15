#!/usr/bin/env bash
# Early local feedback only; does not replace hosted or composed-source gates.
set -euo pipefail
exec "${PYTHON:-python3}" "$(dirname "$0")/pre_offer_gate.py" "$@"
