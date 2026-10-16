"""#11115 — install a fake ``KalshiAPIService`` for one test without leaking it.

The ``_backfill_kalshi_winners`` drivers replace
``app.services.kalshi_api.KalshiAPIService`` with a factory returning the test's
venue. Inside that call the #1853 archive arm lazily imports
``app.tasks.kalshi_resolution_sweep``, which binds ``KalshiAPIService`` at
import time. Imported for the FIRST time while the fake is installed, the cached
sweep module keeps the fake, and so does
``scripts.backfill_kalshi_resolution_window``, which re-exports it. monkeypatch
restores only the source attribute, so every later test in the process sees the
fake there (#11115 backend6: #989's constructor-identity guard went red behind
an earlier driver in the same shard).

``install`` imports the sweep before the fake goes in, so the cached module
holds the real class. ``assert_not_captured`` runs after the drive and fails if
any OTHER cached module bound a name to the fake, which catches the next lazy
importer of the same kind in the file that introduces it.
"""

from __future__ import annotations

import sys

_SOURCE = "app.services.kalshi_api"


def install(monkeypatch, venue):
    """Replace ``KalshiAPIService`` with a factory for ``venue``; return the factory."""
    import app.tasks.kalshi_resolution_sweep  # noqa: F401  -- binds the real class

    def fake_service(*_a, **_k):
        return venue

    monkeypatch.setattr(f"{_SOURCE}.KalshiAPIService", fake_service)
    return fake_service


def modules_holding(obj) -> list[str]:
    """Every cached module, other than the patched source, with a top-level name bound to ``obj``."""
    return sorted(
        name
        for name, m in list(sys.modules.items())
        if name != _SOURCE and any(v is obj for v in list(getattr(m, "__dict__", {}).values()))
    )


def assert_not_captured(fake_service) -> None:
    held = modules_holding(fake_service)
    assert held == [], (
        f"{held} bound the fake KalshiAPIService at import; monkeypatch will not "
        "undo that, so it leaks into every later test in the process (#11115)"
    )
