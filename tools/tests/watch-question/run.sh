#!/bin/sh
# Native-owned future execution; this proposal has not been compiled.
set -eu
QUESTION_ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
python3 - "$QUESTION_ROOT" <<'PY'
from pathlib import Path
import subprocess
import sys
import tempfile
root = Path(sys.argv[1])
with tempfile.TemporaryDirectory(prefix='watch-question-') as folder:
    binary = Path(folder) / 'checks'
    subprocess.run(['swiftc', '-parse-as-library', '-swift-version', '5', '-Onone',
        str(root / 'ios/Bain Luck/Bain Luck/Utilities/OutcomeVerdict.swift'),
        str(root / 'ios/Bain Luck/BainLuckWatch Watch App/WatchQuestionDetail.swift'),
        str(root / 'ios/Bain Luck/BainLuckWatch Watch App/WatchQuestionDetailAPIClient.swift'),
        str(root / 'ios/Bain Luck/BainLuckWatch Watch App/WatchQuestionDetailStore.swift'),
        str(root / 'tools/tests/watch-question/StoreChecks.swift'),
        str(root / 'tools/tests/watch-question/main.swift'), '-o', str(binary)],
        check=True, timeout=90)
    subprocess.run([str(binary)], check=True, timeout=30)
PY
