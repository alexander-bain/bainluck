"""#219E: poll_polymarket_markets must fetch NEWEST-first within Gamma's cap.

Polymarket's Gamma API changed (~2026-07-14) to cap offset pagination at
offset 2000 (offset>=2100 -> HTTP 422 "offset too large, use /events/keyset").
The main active scan previously used no `order` param, so Gamma's default
oldest-first sort pinned the poll on the OLDEST ~2000 active events — all of
which were already ingested — and it could NEVER reach newly-created markets.
Daily creation cratered from ~1000-2000/day to <10/day while the poll kept
"succeeding" (it just re-updated the same stale window).

The fix is structural: order the scan newest-first (order=startDate,
ascending=False) so new markets land on the first pages, and bound max_pages
to the offset-2000 cap so we never burn calls on the guaranteed-422 tail.
Guard both so the freeze class can't regress.
"""

import inspect

from app.tasks.polymarket import _poll_polymarket_markets


def _main_scan_body() -> str:
    """The main active-events pagination loop (before the settled tag pass)."""
    src = inspect.getsource(_poll_polymarket_markets)
    # the main scan is everything up to the supplementary settled pass
    assert "Supplementary pass" in src, "poll shape changed (no settled pass marker)"
    return src.split("Supplementary pass", 1)[0]


def test_main_scan_fetches_newest_first():
    """order=startDate + ascending=False puts newly-created markets on page 0.

    Without this, Gamma's oldest-first default + the offset-2000 cap freeze
    creation (the #219E outage: poll succeeds, creates nothing).
    """
    head = _main_scan_body()
    # find the primary get_events call in the main scan
    assert "active=True, closed=False" in head, "main active scan call shape changed"
    call = head.split("active=True, closed=False", 1)[1].split(")", 1)[0]
    assert 'order="startDate"' in call, (
        "main active scan lost its newest-first ordering — Gamma's oldest-first "
        "default + offset-2000 cap will re-freeze poly creation (#219E)"
    )
    assert "ascending=False" in call, (
        "ascending must be False (descending) so the NEWEST markets are fetched "
        "first, inside the 2000-offset window (#219E)"
    )


def test_max_pages_respects_offset_cap():
    """max_pages*100 must stay within Gamma's offset-2000 pagination cap."""
    src = inspect.getsource(_poll_polymarket_markets)
    assert "max_pages = 20" in src, (
        "max_pages must be bounded to the Gamma offset-2000 cap (offset = "
        "page*100, so <=20 pages). A larger value burns calls on guaranteed-422 "
        "offsets and risks sticking the page cursor past the cap (#219E)"
    )


def test_offset_cap_error_resets_cursor():
    """A 422 'offset too large' must reset the page cursor, not stick on it."""
    src = inspect.getsource(_poll_polymarket_markets)
    assert "offset too large" in src, (
        "the poll must recognize Gamma's offset-cap 422 and reset its page "
        "cursor so the next run restarts at the newest page (#219E)"
    )
