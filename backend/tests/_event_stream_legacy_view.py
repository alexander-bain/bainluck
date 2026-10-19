"""#10090: the legacy wire view of the event stream, for route tests written
before the stream's reconcile controls.

Since the reconcile-first route, every stream opens with an owned
current-state coverage read and may emit named ``event: reconcile`` controls.
Tests that predate that read have no database and assert the frames an old
listener sees, so they install this view: the coverage read answers a valid
constant floor, and reconcile controls are dropped from the wire (old
listeners ignore named events they do not know). Ported from the reviewed lab
adapter (attempt125/133 ``test_legacy_route/conftest.py``).

This view does NOT certify the coverage read's database cost, its failure
handling or the reconcile consumers; those are pinned by the route's own
reconcile tests.
"""

from app.routes import event_stream as route


def install_legacy_view(monkeypatch) -> None:
    async def coverage(event_id, ids):
        return {
            "event_id": event_id,
            "custody_id": "constant-fixture",
            "removal_rev": {str(i): 0 for i in ids},
        }

    monkeypatch.setattr(route, "_current_reconcile", coverage)
    original = route._stream

    async def stream(*a, **kw):
        underlying = original(*a, **kw)
        try:
            async for chunk in underlying:
                if not chunk.startswith("event: reconcile\n"):
                    yield chunk
        finally:
            await underlying.aclose()

    monkeypatch.setattr(route, "_stream", stream)
