"""#10090: the legacy wire view of the event stream, for route tests written
before the stream's reconcile controls.

Since the reconcile-first route, every stream opens with an owned
current-state coverage read and may emit named ``event: reconcile`` controls.
Tests that predate that read have no database, so they install this view:
the coverage read answers a valid constant floor (``removal_rev`` 0 for every
id). Installed per module or per class in the older listener tests only —
never globally or from a shared conftest, so the reconcile controls and the
real PostgreSQL route tests always see the real read and the real frames.

``drop_reconcile=True`` additionally drops reconcile and DNPL commit-floor
controls from the wire (old listeners ignore named events they do not know).
Default DNPL makes the latter present without an event activation list; real
fold-preview controls remain covered by test_folded_blend_preview_10090.py. Only the modules whose
assertions read chunk position ask for it (latest_replay and folded_837 per
module, and the one folded case in stream_recovery_10666); every
other legacy module keeps those frames, so cancellation and release run
through the real route generator. Ported from the reviewed lab adapter
(attempt125/133 ``test_legacy_route/conftest.py``); scope per lane1's C-L1.

This view does NOT certify the coverage read's database cost, its failure
handling or the reconcile consumers; those are pinned by
tests/test_event_stream_recovery_read_controls_10090.py,
tests/test_event_stream_reconcile_route_controls_10090.py and
tests/integration/test_event_stream_reconcile_route_10090_pg.py.
"""

from app.routes import event_stream as route


def install_legacy_view(monkeypatch, *, drop_reconcile: bool = False) -> None:
    async def coverage(event_id, ids):
        return {
            "event_id": event_id,
            "custody_id": "constant-fixture",
            "removal_rev": {str(i): 0 for i in ids},
        }

    monkeypatch.setattr(route, "_current_reconcile", coverage)
    if not drop_reconcile:
        return
    original = route._stream

    async def stream(*a, **kw):
        underlying = original(*a, **kw)
        try:
            async for chunk in underlying:
                if not chunk.startswith(("event: reconcile\n", "event: fold_preview_floor\n")):
                    yield chunk
        finally:
            await underlying.aclose()

    monkeypatch.setattr(route, "_stream", stream)
