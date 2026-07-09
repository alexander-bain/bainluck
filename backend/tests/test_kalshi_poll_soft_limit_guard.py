"""#150: poll_kalshi must degrade to PARTIAL progress under the soft limit.

ops r120 flagged SoftTimeLimitExceeded @437.8s on poll_kalshi — the #38/#995
create-starvation signature: if the soft limit fires mid-upsert-loop, the
uncommitted creates since the last incremental commit roll back, so a slow cycle
silently creates nothing. Two guards must be present in the upsert loop and can't
regress:
  1. a PER-EVENT deadline check (not only at %_COMMIT_EVERY boundaries) that
     commits + breaks before the soft limit;
  2. an `except SoftTimeLimitExceeded` on the per-event try that commits the
     partial batch and breaks (the tuple `except` below it does NOT catch it).
"""

import inspect

from app.tasks.kalshi import _poll_kalshi_markets


def _upsert_loop() -> str:
    src = inspect.getsource(_poll_kalshi_markets)
    assert "for event in events:" in src, "upsert loop shape changed"
    return src.split("for event in events:", 1)[1]


def test_per_event_deadline_check_present():
    loop = _upsert_loop()
    # The deadline break must appear BEFORE the per-event try (top of loop),
    # i.e. before the %_COMMIT_EVERY block, so a sub-_COMMIT_EVERY slow cycle
    # still exits before the soft limit.
    head = loop.split("try:", 1)[0]
    assert "_LOOP_DEADLINE_S" in head and "break" in head, (
        "per-event deadline check missing at the top of the upsert loop — a slow "
        "cycle can run into the soft limit and lose uncommitted creates"
    )
    assert "await session.commit()" in head, (
        "per-event deadline exit must COMMIT partial progress before breaking"
    )


def test_soft_time_limit_exceeded_is_caught_and_commits():
    src = inspect.getsource(_poll_kalshi_markets)
    assert "except SoftTimeLimitExceeded:" in src, (
        "poll_kalshi must catch SoftTimeLimitExceeded in the upsert loop and "
        "commit partial progress (the #38/#995 create-starvation guard)"
    )
    # The handler must commit + break (not continue past the limit). Split on the
    # tuple-except that follows the handler (its own inner `except Exception:` for
    # the commit would truncate a naive "except " split before the break).
    after = src.split("except SoftTimeLimitExceeded:", 1)[1].split(
        "except (httpx", 1
    )[0]
    assert "await session.commit()" in after and "break" in after
    assert 'stats["soft_limit_hit"]' in after


def test_soft_limit_import_present():
    src = inspect.getsource(__import__("app.tasks.kalshi", fromlist=["x"]))
    assert "from celery.exceptions import SoftTimeLimitExceeded" in src
