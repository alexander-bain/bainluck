#!/bin/sh
# Future Native-owned execution after reviewed composition; not run by author.
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
python3 - "$ROOT" <<'PY'
from pathlib import Path
import subprocess
import sys
import tempfile
root = Path(sys.argv[1])
app = root / 'ios/Bain Luck/BainLuckWatch Watch App'
try:
    with tempfile.TemporaryDirectory(prefix='watch-nfl-rich-landing-') as temporary:
        binary = Path(temporary) / 'checks'
        subprocess.run(['swiftc', '-parse-as-library', '-swift-version', '5', '-Onone',
            str(app / 'WatchNFLCollectionModels.swift'),
            str(app / 'WatchNFLGamePresentation.swift'),
            str(root / 'tools/tests/watch-nfl-rich-landing/main.swift'),
            '-o', str(binary)], check=True, timeout=90)
        subprocess.run([str(binary), str(root / 'tools/tests/watch-nfl-collection/fixtures')], check=True, timeout=30)
except subprocess.TimeoutExpired:
    raise SystemExit(124)
except subprocess.CalledProcessError as error:
    raise SystemExit(error.returncode if error.returncode > 0 else 1)
PY
