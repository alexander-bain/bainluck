"""Real CI count parsers accept warning-free pytest without losing count pins."""

from pathlib import Path
import re
import subprocess

import pytest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"
# Gates exposed by removing eager route imports; counts remain in CI itself.
GATES = (
    "deadlock837",
    "pricelock10661",
    "livebeside10090",
    "own7594",
    "delay7617",
    "withdrawn8755",
    "latersession9588",
    "futurelive10300",
    "openleg10022",
    "evidence7878",
    "wire7878",
    "espnpass8796",
    "tennisrelease9797",
    "espnrelease9049",
    "playoff9602",
    "settledbox9713",
    "livebox8913",
    "livebox9067",
)


@pytest.mark.parametrize("gate", GATES)
def test_real_count_parser_keeps_exact_count_with_or_without_warnings(gate):
    source = WORKFLOW.read_text()
    matches = re.findall(rf'grep -qE "([^"]+)" /tmp/{re.escape(gate)}\.txt', source)
    assert len(matches) == 1
    pattern = matches[0]
    count = int(re.search(r"(\d+) passed", pattern).group(1))
    for summary, expected in (
        (f"=== {count} passed in 8.04s ===", 0),
        (f"=== {count} passed, 1 warning in 8.04s ===", 0),
        (f"=== {count - 1} passed in 8.04s ===", 1),
        (f"=== {count + 1} passed in 8.04s ===", 1),
        (f"=== 1{count} passed in 8.04s ===", 1),
        (f"=== {count} skipped in 8.04s ===", 1),
        (f"=== {count} passedaway ===", 1),
    ):
        result = subprocess.run(
            ["/usr/bin/grep", "-qE", pattern],
            input=summary,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == expected, (gate, pattern, summary, result.stderr)
