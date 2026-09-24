"""The manifest must install greenlet with SQLAlchemy and hold it below 2.1 (#8454).

SQLAlchemy 2.1.0 reached PyPI at 2026-09-24T20:12Z and no longer pulls ``greenlet``
in by default. ``requirements.txt`` said only ``sqlalchemy>=2.0.50``, so the next fresh
install resolved 2.1.0 without greenlet and ``from sqlalchemy.ext.asyncio import
AsyncSession`` raised at conftest import: every backend shard and ``search-recall``
failed before a single test ran, on PRs that touched no Python at all. A Heroku build
installing fresh would have resolved the same thing.

This guard reads the manifest, not the environment: the environment that runs it
already has greenlet (or it could not have imported conftest), so a runtime import
check would pass exactly when the manifest is fine and never run when it is not.
"""

from __future__ import annotations

import re
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"

_REQ = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(\[[^\]]*\])?\s*([^#;]*)")


def _parse(text: str) -> dict[str, tuple[set[str], str]]:
    """Distribution name (lowercased) -> (extras, specifier string)."""
    out: dict[str, tuple[set[str], str]] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _REQ.match(line)
        if not m:
            continue
        extras = {e.strip().lower() for e in (m.group(2) or "").strip("[]").split(",") if e.strip()}
        out[m.group(1).lower()] = (extras, m.group(3).replace(" ", ""))
    return out


def _violations(text: str) -> list[str]:
    reqs = _parse(text)
    problems: list[str] = []
    if "sqlalchemy" not in reqs:
        return ["sqlalchemy is not declared"]
    extras, spec = reqs["sqlalchemy"]
    if "asyncio" not in extras and "greenlet" not in reqs:
        problems.append("greenlet is not installed: need sqlalchemy[asyncio] or an explicit greenlet line")
    if not re.search(r"<\s*2\.1(\.0)?(,|$)", spec):
        problems.append(f"sqlalchemy has no <2.1 upper bound (spec {spec!r})")
    return problems


def test_manifest_installs_greenlet_and_bounds_sqlalchemy_below_2_1():
    assert _violations(REQUIREMENTS.read_text()) == []


def test_the_pre_8454_line_is_refused_on_both_counts():
    # Strawman: the exact line that broke CI must fail both checks, or the guard is vacuous.
    problems = _violations("sqlalchemy>=2.0.50\nasyncpg>=0.31.0\n")
    assert len(problems) == 2, problems


def test_an_explicit_greenlet_line_satisfies_the_install_check():
    assert _violations("sqlalchemy>=2.0.50,<2.1\ngreenlet>=3.0\n") == []


def test_an_extra_without_the_bound_is_still_refused():
    assert _violations("sqlalchemy[asyncio]>=2.0.50\n") == [
        "sqlalchemy has no <2.1 upper bound (spec '>=2.0.50')"
    ]
