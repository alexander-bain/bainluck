"""HTTP response compression contract (#1636).

The API shipped no ``Content-Encoding`` at all: every JSON body went out raw,
so ``/api/feed`` transferred 133,722 B where 17,965 B would do. This guards the
whole class — not just "gzip is on somewhere", but the four properties that
actually have to hold for the transfer saving to be real and safe:

1. **It is registered, and it is INNERMOST.** Ordering is the part most likely
   to regress silently under a future middleware edit. If GZip drifts outside
   ``LatencyMiddleware`` / ``request_timing``, compression cost stops landing in
   ``X-Response-Time`` and in the slow-event ring, and the instruments that this
   lane ranks by go quietly blind to it.
2. **The compression parameters are the benchmarked ones**, not Starlette's
   defaults. Level 9 buys 3.5% smaller bodies for 118% more CPU on the real
   production payloads; ``minimum_size`` 500 would compress the ~844 B
   scheduled-game responses #1636 asked to leave raw. A refactor that drops the
   kwargs reverts to both defaults and nothing else would notice.
3. **A gzip-capable client really gets a smaller body**, end-to-end through the
   REAL ``app.main.app`` stack rather than a hand-built replica of it.
4. **Nothing is broken for anyone else** — an ``identity`` client still gets
   correct raw bytes, both paths carry ``Vary: Accept-Encoding`` so a shared
   cache cannot cross-serve, and the decoded body is byte-identical.

``/openapi.json`` is the probe route: it is served by FastAPI itself, needs no
database, Redis or network, and is comfortably over ``minimum_size``.
"""

import gzip

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.main import (
    RESPONSE_GZIP_COMPRESSLEVEL,
    RESPONSE_GZIP_MINIMUM_SIZE,
    app,
)
from app.middleware.latency import LatencyMiddleware
from app.utils.rate_limit import RateLimitMiddleware


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _stack():
    """Registered middleware classes, OUTERMOST first.

    Starlette's ``add_middleware`` inserts at position 0, and the stack is built
    by wrapping in reverse, so ``user_middleware`` is already outermost-first.
    """
    return [m.cls for m in app.user_middleware]


# ---------------------------------------------------------------------------
# 1. Registration and position
# ---------------------------------------------------------------------------


def test_gzip_middleware_is_registered():
    assert GZipMiddleware in _stack(), (
        "GZipMiddleware is not registered on app.main.app — the API is serving "
        "every JSON body uncompressed again (#1636)."
    )


def test_gzip_is_innermost_of_the_measured_middlewares():
    stack = _stack()
    gzip_at = stack.index(GZipMiddleware)

    for cls, why in (
        (LatencyMiddleware, "the slow-event ring would stop seeing compression cost"),
        (RateLimitMiddleware, "429s would be compressed instead of the route bodies"),
        (CORSMiddleware, "CORS must stay outermost so error paths keep their headers"),
    ):
        assert (
            cls in stack
        ), f"{cls.__name__} vanished from the stack — this guard is now blind"
        assert stack.index(cls) < gzip_at, (
            f"GZipMiddleware must be registered FIRST so it is innermost, but "
            f"{cls.__name__} is inside it: {why}."
        )


def test_gzip_uses_the_benchmarked_parameters_not_starlette_defaults():
    entry = next(m for m in app.user_middleware if m.cls is GZipMiddleware)
    kwargs = entry.kwargs

    assert kwargs.get("compresslevel") == RESPONSE_GZIP_COMPRESSLEVEL == 6, (
        "compresslevel must stay at the benchmarked 6. Starlette's default is 9, "
        "which cost 9.73 ms vs 3.99 ms on /api/calibration for 3,325 bytes."
    )
    assert kwargs.get("minimum_size") == RESPONSE_GZIP_MINIMUM_SIZE == 1000, (
        "minimum_size must stay at 1000. Starlette's default of 500 would "
        "compress the ~844 B scheduled-game payloads #1636 asked to leave raw."
    )


# ---------------------------------------------------------------------------
# 2. End-to-end behaviour through the real app
# ---------------------------------------------------------------------------


def test_gzip_client_gets_a_materially_smaller_body(client):
    r = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"

    on_wire = int(r.headers["content-length"])
    decoded = len(r.content)  # httpx transparently decodes

    assert on_wire < decoded, "content-length is not the compressed size"
    assert decoded / on_wire >= 3.0, (
        f"JSON of this shape compresses ~6x; got {decoded / on_wire:.1f}x from "
        f"{decoded} -> {on_wire} B. A ratio this poor means the body is being "
        f"double-encoded or compressed at the wrong level."
    )


def test_identity_client_still_gets_correct_raw_bytes(client):
    gz = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    raw = client.get("/openapi.json", headers={"Accept-Encoding": "identity"})

    assert raw.status_code == 200
    assert raw.headers.get("content-encoding") is None
    assert int(raw.headers["content-length"]) == len(raw.content)
    assert raw.content == gz.content, (
        "gzip and identity clients disagree about the body — compression is "
        "corrupting or truncating the response."
    )


def test_both_paths_vary_on_accept_encoding(client):
    for accept in ("gzip", "identity"):
        r = client.get("/openapi.json", headers={"Accept-Encoding": accept})
        vary = r.headers.get("vary", "")
        assert "accept-encoding" in vary.lower(), (
            f"Accept-Encoding: {accept} response has Vary={vary!r}. Without it a "
            f"shared cache can hand a gzipped body to a client that cannot read it."
        )


# ---------------------------------------------------------------------------
# 3. The floor, and the exclusions, on an isolated app wired from the SAME
#    constants — so a change to either constant is caught here too.
# ---------------------------------------------------------------------------


def _isolated_client():
    probe = FastAPI()
    probe.add_middleware(
        GZipMiddleware,
        minimum_size=RESPONSE_GZIP_MINIMUM_SIZE,
        compresslevel=RESPONSE_GZIP_COMPRESSLEVEL,
    )

    @probe.get("/tiny")
    def tiny():
        # Sized into the 500..1000 B window ON PURPOSE. A body of a few bytes
        # would sit under Starlette's default floor too, so the assertion would
        # hold at minimum_size=500 as well and pin nothing. At ~700 B this route
        # is compressed at the default and raw at ours, so the floor itself is
        # what is under test.
        return {"pad": "y" * 700}

    @probe.get("/big")
    def big():
        return {"rows": ["a highly repetitive row"] * 400}

    @probe.get("/preencoded")
    def preencoded():
        from starlette.responses import Response

        body = gzip.compress(b"x" * 5000)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Encoding": "gzip"},
        )

    return TestClient(probe)


def test_small_responses_stay_uncompressed():
    r = _isolated_client().get("/tiny", headers={"Accept-Encoding": "gzip"})

    assert 500 < len(r.content) < 1000, (
        f"probe body is {len(r.content)} B — it must sit strictly between "
        f"Starlette's default floor and ours, or this test pins nothing"
    )
    assert r.headers.get("content-encoding") is None, (
        "A response below minimum_size was compressed — the floor #1636 asked "
        "for is gone."
    )


def test_large_responses_are_compressed_on_the_isolated_app():
    r = _isolated_client().get("/big", headers={"Accept-Encoding": "gzip"})

    assert r.headers.get("content-encoding") == "gzip"
    assert int(r.headers["content-length"]) < len(r.content)


def test_already_encoded_bodies_are_not_double_compressed():
    r = _isolated_client().get("/preencoded", headers={"Accept-Encoding": "gzip"})

    assert r.headers.get("content-encoding") == "gzip"
    # httpx strips exactly ONE Content-Encoding layer. So if the middleware had
    # compressed on top of the route's own gzip, what is left here would still
    # be a gzip stream (magic b"\x1f\x8b") instead of the payload.
    assert not r.content.startswith(b"\x1f\x8b"), (
        "The body was compressed a second time on top of a Content-Encoding "
        "the route had already set."
    )
    assert r.content == b"x" * 5000


def test_event_stream_is_never_compressed():
    """SSE through a buffering compressor stops being a stream.

    Nothing in the tree serves ``text/event-stream`` today; this pins the
    exclusion so the first thing that does cannot be silently broken by it.
    """
    probe = FastAPI()
    probe.add_middleware(
        GZipMiddleware,
        minimum_size=RESPONSE_GZIP_MINIMUM_SIZE,
        compresslevel=RESPONSE_GZIP_COMPRESSLEVEL,
    )

    @probe.get("/stream")
    def stream():
        from starlette.responses import StreamingResponse

        def gen():
            for i in range(500):
                yield f"data: event {i} padded out past the floor\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    r = TestClient(probe).get("/stream", headers={"Accept-Encoding": "gzip"})

    assert r.headers.get("content-encoding") is None, (
        "text/event-stream was compressed — SSE consumers will stall waiting "
        "for the compressor to flush."
    )
