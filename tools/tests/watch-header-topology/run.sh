#!/bin/bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
task_dir="$(mktemp -d)"
trap 'rm -rf "$task_dir"' EXIT
source_file="$repo_root/ios/Bain Luck/BainLuckWatchUITests/PickerCurrentGameJourneyTests.swift"
python3 - "$source_file" "$task_dir/Topology.swift" <<'PYEXTRACT'
import sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
a='// BEGIN WATCH_HEADER_LABEL_TOPOLOGY'; b='// END WATCH_HEADER_LABEL_TOPOLOGY'
assert s.count(a)==1 and s.count(b)==1
Path(sys.argv[2]).write_text('import Foundation\n'+s.split(a,1)[1].split(b,1)[0])
PYEXTRACT
swiftc "$task_dir/Topology.swift" "$repo_root/tools/tests/watch-header-topology/main.swift" -o "$task_dir/checks"
"$task_dir/checks"
