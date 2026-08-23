"""Sentry Crons is OFF, and this is the guard that keeps it off.

## The incident

`CeleryIntegration(monitor_beat_tasks=True)` makes the SDK auto-create one Sentry
cron monitor per beat task, on that task's first dispatch. It silently created
**129 paid monitors** and consumed the entire **$100 pay-as-you-go budget in 4
days** (Fable/Alex ruling, 2026-08-21).

`beat_schedule` measures **132** entries on this tree. The two numbers are
different quantities — 129 monitors had dispatched at least once — and the
schedule is the one that bounds the cost, so it is the one asserted below.

Nothing was lost by turning it off. Beat observability here is the `task-metrics`
rail plus the samplers — the signal every latency and calibration read is already
taken against. Sentry Crons was a second, billed copy of a thing we own, and it
was not the copy anybody consulted.

## Why a guard test and not just the flag

`monitor_beat_tasks=False` is the SDK's OWN default, which is exactly what makes
this easy to re-break: the flag reads like boilerplate, and re-adding `=True`
looks like enabling monitoring rather than like spending a budget. The capability
is deleted, not remembered — and a deletion nobody guards is a deletion with a
half-life.

## What this pins that a grep would not

`build_celery_integration()` is called and its RESULT introspected, so this fails
if the flag flips, if the factory stops being the thing the init calls, or if a
future SDK renames the attribute. Asserting on the source text of
`app/tasks/__init__.py` would pass in all three cases.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from sentry_sdk.integrations.celery import CeleryIntegration

from app.tasks import SENTRY_MONITOR_BEAT_TASKS, build_celery_integration


def test_the_integration_the_worker_builds_has_cron_monitoring_off():
    integration = build_celery_integration()
    assert isinstance(integration, CeleryIntegration)
    assert integration.monitor_beat_tasks is False, (
        "Sentry Crons auto-creates one PAID monitor per beat task. With 129 beats "
        "that is 129 monitors and the whole $100 PAYG budget in 4 days."
    )


def test_the_constant_is_off():
    assert SENTRY_MONITOR_BEAT_TASKS is False


def test_the_blast_radius_is_the_whole_beat_schedule_and_it_only_grows():
    """Records WHAT ON WOULD COST, so the guard is not just a boolean nobody sizes.

    One paid monitor per beat entry, created on first dispatch. The floor is the
    129 that actually billed; the schedule is above it and every new beat raises
    the exposure, which is the argument for deleting the capability rather than
    watching the invoice.
    """
    from app.tasks import celery_app

    entries = len(celery_app.conf.beat_schedule)
    assert entries >= 129, (
        f"beat_schedule has {entries} entries; the incident billed 129 monitors. "
        "If this ever drops below the billed count, one of the two numbers is "
        "being measured wrong."
    )


def test_the_attribute_this_guard_reads_still_exists_on_the_sdk():
    """Fail loudly on an SDK rename rather than passing vacuously.

    A guard that asserts `getattr(x, "gone_flag", False) is False` passes forever
    once the attribute disappears. This is the tripwire for that.
    """
    assert "monitor_beat_tasks" in inspect.signature(CeleryIntegration.__init__).parameters
    assert hasattr(CeleryIntegration(), "monitor_beat_tasks")


def test_turning_it_on_would_actually_be_visible_to_this_guard():
    """The guard can distinguish ON from OFF — it is not asserting a tautology.

    Without this, a guard that only ever sees the OFF value cannot prove it would
    catch the ON one.
    """
    assert CeleryIntegration(monitor_beat_tasks=True).monitor_beat_tasks is True


def test_no_call_site_anywhere_passes_monitor_beat_tasks_true():
    """The whole app, not just the one factory.

    A second `sentry_sdk.init` (there is one in `app/main.py`) or a future worker
    entry point could re-enable crons without touching the factory this file
    otherwise guards.
    """
    app_dir = Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "monitor_beat_tasks":
                    continue
                if not (
                    isinstance(kw.value, ast.Constant) and kw.value.value is False
                ) and not (
                    isinstance(kw.value, ast.Name)
                    and kw.value.id == "SENTRY_MONITOR_BEAT_TASKS"
                ):
                    offenders.append(f"{path.relative_to(app_dir.parent)}:{node.lineno}")
    assert not offenders, (
        "monitor_beat_tasks must be False (or the pinned constant) at every call "
        f"site — 129 paid cron monitors otherwise. Offenders: {offenders}"
    )
