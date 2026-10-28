"""#10090: pin the Python-leg CodeQL config (lane1's guard from its review of PR #11698).

The init-step allowance pins `config-file` to one path; this pins what that path
says, so the scope stays Alex's approval (Python leg, backend/tests/** only).
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_python_codeql_config_skips_backend_tests_and_nothing_else():
    config = yaml.safe_load(
        (ROOT / ".github/codeql/codeql-config.yml").read_text()
    )
    assert set(config) == {"name", "paths-ignore"}
    assert config["paths-ignore"] == ["backend/tests/**"]
