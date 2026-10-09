#!/bin/sh
# Native-owned future execution only, after this proposal is reviewed and composed.
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
python3 - "$ROOT" <<'PY'
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
app = root / 'ios/Bain Luck/BainLuckWatch Watch App'
files = [
    app / 'WatchMLBCollectionModels.swift',
    app / 'WatchMLBCollectionAPIClient.swift',
    app / 'WatchMLBCollectionStore.swift',
    root / 'tools/tests/watch-mlb-collection/DecoderChecks.swift',
    root / 'tools/tests/watch-mlb-collection/main.swift',
]
fixtures = root / 'tools/tests/watch-mlb-collection/fixtures'
# No SDK/simulator/package resolution. Uses actual model/store/API sources, with
# the transport injected before runtime. No source extraction or policy stubs.
try:
    with tempfile.TemporaryDirectory(prefix='watch-mlb-collection-') as temporary:
        binary = Path(temporary) / 'checks'
        subprocess.run(
            ['swiftc', '-parse-as-library', '-swift-version', '5', '-Onone',
             *map(str, files), '-o', str(binary)],
            check=True, timeout=90,
        )
        # Broken request fencing must fail in bounded time, never hang a gate.
        subprocess.run([str(binary), str(fixtures)], check=True, timeout=30)
except subprocess.TimeoutExpired as error:
    print(f'MLB harness timeout: {error.cmd}', file=sys.stderr)
    raise SystemExit(124)
except subprocess.CalledProcessError as error:
    raise SystemExit(error.returncode if error.returncode > 0 else 1)
PY
