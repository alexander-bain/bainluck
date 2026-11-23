"""Tests for the #13281 static call-keyword gate (.github/scripts/check_call_keywords.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "check_call_keywords.py"
BACKEND_APP = ROOT / "backend" / "app"


def _run_checker(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_unknown_keyword_like_league_ceiling_fails_and_names_file_and_line(tmp_path: Path):
    pkg = tmp_path / "backend"
    app_dir = pkg / "app"
    routes = app_dir / "routes"
    routes.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (routes / "__init__.py").write_text("", encoding="utf-8")
    (routes / "helpers.py").write_text(
        "def _same_league_row_preference(team, *, stale_only=False):\n"
        "    return 1 if stale_only else 0\n",
        encoding="utf-8",
    )
    (routes / "events.py").write_text(
        "from app.routes.helpers import _same_league_row_preference\n\n\n"
        "def _dedupe_team_name_lookup(team):\n"
        "    return _same_league_row_preference(team, league_ceiling=10)\n",
        encoding="utf-8",
    )

    res = _run_checker(app_dir)
    assert res.returncode == 1
    assert "findings: 1" in res.stdout
    assert "routes/events.py" in res.stdout
    assert "5 _same_league_row_preference" in res.stdout
    assert "unknown keyword 'league_ceiling'" in res.stdout


def test_missing_required_and_extra_positional_fail_while_valid_and_kwargs_pass(tmp_path: Path):
    pkg = tmp_path / "backend"
    app_dir = pkg / "app"
    utils = app_dir / "utils"
    utils.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (utils / "__init__.py").write_text("", encoding="utf-8")
    (utils / "sample.py").write_text(
        "def f(a, b, *, flag=False):\n"
        "    return (a, b, flag)\n\n"
        "def g(x, **kw):\n"
        "    return (x, kw)\n\n"
        "def ok():\n"
        "    f(1, 2, flag=True)\n"
        "    g(1, anything=99)\n\n"
        "def bad():\n"
        "    f(1)\n"
        "    f(1, 2, 3)\n",
        encoding="utf-8",
    )

    res = _run_checker(app_dir)
    assert res.returncode == 1
    assert "findings: 2" in res.stdout
    assert "12 f missing b" in res.stdout
    assert "13 f 3 positional, takes 2" in res.stdout


def test_real_backend_app_has_zero_findings():
    res = _run_checker(BACKEND_APP)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "| findings: 0" in res.stdout
