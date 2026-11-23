"""Every production requirements line must use an exact ``==`` version pin (Alex ruling 351: A).

Both the primary ``bainluck`` Heroku app and ``bainluck-heavy`` deploy from
``backend/requirements.txt``. Unpinned lower bounds allowed ``redis 8.2.0`` and
``sentry-sdk 3.0.0`` to land unannounced from PyPI and break CI and Heroku release
startup. Every non-comment line must carry a single exact ``==<version>`` pin.
"""

from __future__ import annotations

import re
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"

_EXACT_PIN = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.,-]+\])?==[A-Za-z0-9_.+-]+$"
)


def _unpinned_lines(text: str) -> tuple[int, list[tuple[int, str]]]:
    """Return (requirement_line_count, [(line_number, stripped_line), ...]) for non-exact lines."""
    total = 0
    bad: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        code = raw.split("#", 1)[0].strip()
        if not code:
            continue
        total += 1
        if not _EXACT_PIN.fullmatch(code) or "*" in code:
            bad.append((lineno, code))
    return total, bad


def test_every_production_requirement_has_exact_pin():
    total, bad = _unpinned_lines(REQUIREMENTS.read_text())
    assert total >= 20, f"expected at least 20 requirements, found {total}"
    assert bad == [], f"requirements.txt has non-exact lines: {bad}"


def test_exact_pin_check_rejects_ranges_wildcards_and_bare_packages():
    sample = "\n".join(
        [
            "fastapi==0.136.3",
            "uvicorn[standard]>=0.27.0",
            "sqlalchemy[asyncio]>=2.0.50,<2.1",
            "openai",
            "PyYAML~=6.0",
            "Pillow!=12.0.0",
            "redis==8.1.*",
            "-r base.txt",
        ]
    )
    total, bad = _unpinned_lines(sample)
    assert total == 8
    assert bad == [
        (2, "uvicorn[standard]>=0.27.0"),
        (3, "sqlalchemy[asyncio]>=2.0.50,<2.1"),
        (4, "openai"),
        (5, "PyYAML~=6.0"),
        (6, "Pillow!=12.0.0"),
        (7, "redis==8.1.*"),
        (8, "-r base.txt"),
    ]


def test_exact_pin_check_accepts_extras_and_inline_comments():
    sample = "\n".join(
        [
            "# header comment",
            "fastapi==0.136.3",
            "sqlalchemy[asyncio]==2.0.58",
            "sentry-sdk[fastapi,celery]==2.75.0",
            "PyYAML==6.0.3  # Horizon Calendar",
        ]
    )
    total, bad = _unpinned_lines(sample)
    assert total == 4
    assert bad == []
