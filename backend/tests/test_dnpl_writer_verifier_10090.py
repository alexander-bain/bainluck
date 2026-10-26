"""Actual collector and wire parser with offline StreamReader responses only."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest

from app.services import dnpl_writer_verifier as collector
from app.services.dnpl_writer_observations import (
    VERIFIER,
    VERIFIER_SHA256,
    validate_payloads,
)


@pytest.fixture
def binding():
    return {
        "run_id": str(uuid4()),
        "nonce": "b" * 32,
        "step": "arm",
        "expected_authority": {},
        "expected_primary": "exact",
        "apps": {
            app: {"release": 4, "slug": str(uuid4()), "commit": "a" * 40}
            for app in collector.APPS
        },
    }


def response(body=b"[]", *, status=200, headers=(), framing=True):
    fields = [f"HTTP/1.1 {status} test", "Content-Type: application/json"]
    if framing:
        fields.append(f"Content-Length: {len(body)}")
    fields.extend(headers)
    return ("\r\n".join(fields) + "\r\n\r\n").encode() + body


def wire(monkeypatch, payloads):
    attempts, writes, closed = [], [], []

    class Writer:
        def write(self, data):
            writes.append(data)

        async def drain(self):
            pass

        def close(self):
            closed.append(True)

    async def connect(host, port, **kwargs):
        attempts.append((host, port, kwargs))
        reader = asyncio.StreamReader()
        reader.feed_data(payloads[len(attempts) - 1])
        reader.feed_eof()
        return reader, Writer()

    monkeypatch.setattr(collector.asyncio, "open_connection", connect)
    return attempts, writes, closed


def test_exact_eight_direct_reads_produce_revalidatable_raw_evidence(
    tmp_path, monkeypatch, binding
):
    payloads = []
    for app in collector.APPS:
        value = binding["apps"][app]
        payloads.extend(
            [
                [
                    {
                        "current": True,
                        "status": "succeeded",
                        "version": 4,
                        "slug": {"id": value["slug"]},
                    }
                ],
                {"id": value["slug"], "commit": value["commit"]},
                [{"type": "worker-ws", "quantity": 0}],
                [{"type": "web", "name": "web.1", "release": {"version": 4}}],
            ]
        )
    raw = [json.dumps(data).encode() for data in payloads]
    attempts, writes, closed = wire(monkeypatch, [response(data) for data in raw])
    monkeypatch.setenv("HEROKU_API_KEY", "local-test-value")
    monkeypatch.setenv("HTTPS_PROXY", "http://must-not-use.invalid")
    result = collector.collect(binding, tmp_path)
    assert len(attempts) == len(writes) == len(closed) == len(result["reads"]) == 8
    for host, port, options in attempts:
        assert (host, port, options["server_hostname"]) == (
            "api.heroku.com",
            443,
            "api.heroku.com",
        )
        assert options["ssl"].check_hostname
    for index, request in enumerate(writes):
        assert request.startswith(b"GET /apps/")
        assert b"Authorization: Bearer local-test-value\r\n" in request
        assert (b"Range: version ..; max=5, order=desc\r\n" in request) == (
            index % 4 == 0
        )
        assert (b"version=3.sdk" in request) == (index % 4 == 0)
    validate_payloads(
        binding,
        {
            r["name"]: json.loads((tmp_path / (r["name"] + ".json")).read_bytes())
            for r in result["reads"]
        },
    )
    for record, expected in zip(result["reads"], raw, strict=True):
        assert (tmp_path / (record["name"] + ".json")).read_bytes() == expected
        assert record["sha256"] == hashlib.sha256(expected).hexdigest()
        assert record["start_ns"] <= record["end_ns"]
    assert "local-test-value" not in json.dumps(result)
    assert all("local-test-value" not in f.read_text() for f in tmp_path.iterdir())


@pytest.mark.parametrize(
    "status,headers",
    [
        (301, ("Location: https://elsewhere.invalid",)),
        (302, ("Location: /apps/bainluck/dynos",)),
        (401, ()),
        (429, ()),
        (500, ()),
        (206, ()),
        (200, ("Next-Range: id ..",)),
    ],
)
def test_refusal_never_redirects_retries_or_follows_pages(monkeypatch, status, headers):
    attempts, writes, closed = wire(
        monkeypatch, [response(status=status, headers=headers)]
    )
    with pytest.raises(ValueError):
        asyncio.run(
            collector.HTTP("fake").get(collector.PLATFORM, "/apps/bainluck/dynos")
        )
    assert len(attempts) == len(writes) == len(closed) == 1


@pytest.mark.parametrize(
    "path,status,headers",
    [
        ("/apps/bainluck/dynos", 200, ("Content-Range: id 1..2", "Link: <metadata>")),
        ("/apps/bainluck/formation", 200, ("Next-Range: ",)),
        ("/apps/bainluck/releases", 206, ("Next-Range: version ..",)),
    ],
)
def test_complete_lists_and_explicit_bounded_release_history(
    monkeypatch, path, status, headers
):
    attempts, _, _ = wire(monkeypatch, [response(status=status, headers=headers)])
    assert asyncio.run(collector.HTTP("fake").get(collector.PLATFORM, path)) == b"[]"
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "payload",
    [
        response(headers=("Content-Length: 2",)),
        response(headers=("Transfer-Encoding: chunked",)),
        response(headers=("Content-Encoding: gzip",)),
        response(headers=("Content-Type: text/html",)),
        response(headers=("Content-Length: 1048577",), framing=False),
        response(b"[", headers=("Content-Length: 2",), framing=False),
        response(b"x" * (collector.MAX_BYTES + 1), framing=False),
        response(b"not-json"),
        response(
            b"2\r\n[]XX0\r\n\r\n",
            headers=("Transfer-Encoding: chunked",),
            framing=False,
        ),
        response(
            b"0\r\nUnexpected: trailer\r\n\r\n",
            headers=("Transfer-Encoding: chunked",),
            framing=False,
        ),
    ],
)
def test_malformed_or_oversized_wire_refuses(monkeypatch, payload):
    attempts, _, closed = wire(monkeypatch, [payload])
    with pytest.raises((ValueError, asyncio.IncompleteReadError)):
        asyncio.run(
            collector.HTTP("fake").get(collector.PLATFORM, "/apps/bainluck/dynos")
        )
    assert len(attempts) == len(closed) == 1


@pytest.mark.parametrize(
    "payload",
    [
        response(b"[]", framing=False),
        response(
            b"1\r\n[\r\n1\r\n]\r\n0\r\n\r\n",
            headers=("Transfer-Encoding: chunked",),
            framing=False,
        ),
    ],
)
def test_bounded_eof_and_chunked_bodies(monkeypatch, payload):
    wire(monkeypatch, [payload])
    assert (
        asyncio.run(
            collector.HTTP("fake").get(collector.PLATFORM, "/apps/bainluck/dynos")
        )
        == b"[]"
    )


@pytest.mark.parametrize("field", ["Via", "Set-Cookie", "Link", "X-Request-Id"])
def test_unused_repeated_metadata_does_not_block_verification(monkeypatch, field):
    attempts, writes, closed = wire(
        monkeypatch, [response(headers=(f"{field}: first", f"{field.lower()}: second"))]
    )
    http = collector.HTTP("fake")
    assert asyncio.run(http.get(collector.PLATFORM, "/apps/bainluck/dynos")) == b"[]"
    assert http.attempts == len(attempts) == len(writes) == len(closed) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("Content-Length", "2"),
        ("Transfer-Encoding", "chunked"),
        ("Content-Type", "application/json"),
        ("Content-Encoding", "identity"),
        ("Next-Range", ""),
        ("Content-Range", "id first..last"),
    ],
)
@pytest.mark.parametrize("conflicting", [False, True])
def test_repeated_critical_headers_refuse_case_insensitively(
    monkeypatch, field, value, conflicting
):
    second = "conflicting" if conflicting else value
    payload = (
        f"HTTP/1.1 200 OK\r\n{field}: {value}\r\n"
        f"{field.lower()}: {second}\r\n\r\n[]"
    ).encode()
    attempts, writes, closed = wire(monkeypatch, [payload])
    http = collector.HTTP("fake")
    with pytest.raises(ValueError, match="http_duplicate_header"):
        asyncio.run(http.get(collector.PLATFORM, "/apps/bainluck/dynos"))
    assert http.attempts == len(attempts) == len(writes) == len(closed) == 1


def test_ninth_attempt_is_refused_before_connection(monkeypatch):
    attempts, _, _ = wire(monkeypatch, [response()] * 8)

    async def run():
        http = collector.HTTP("fake")
        for _ in range(8):
            await http.get(collector.PLATFORM, "/apps/bainluck/dynos")
        with pytest.raises(ValueError, match="http_request_budget"):
            await http.get(collector.PLATFORM, "/apps/bainluck/dynos")

    asyncio.run(run())
    assert len(attempts) == 8


def test_failed_connection_spends_one_attempt_without_retry(monkeypatch):
    calls = []

    async def fail(*args, **kwargs):
        calls.append(1)
        raise OSError("offline")

    monkeypatch.setattr(collector.asyncio, "open_connection", fail)

    async def run():
        http = collector.HTTP("fake")
        with pytest.raises(OSError):
            await http.get(collector.PLATFORM, "/apps/bainluck/dynos")
        assert http.attempts == 1

    asyncio.run(run())
    assert len(calls) == 1


@pytest.mark.parametrize(
    "host,path",
    [
        ("evil.invalid", "/apps/bainluck/dynos"),
        (collector.PLATFORM, "/apps/other/dynos"),
        (collector.PLATFORM, "/apps/bainluck/config-vars"),
        (collector.PLATFORM, "/apps/bainluck/dynos?next=1"),
    ],
)
def test_allowlist_refuses_before_connection(monkeypatch, host, path):
    attempts, _, _ = wire(monkeypatch, [])
    with pytest.raises(ValueError, match="http_not_allowed"):
        asyncio.run(collector.HTTP("fake").get(host, path))
    assert not attempts


def test_actual_parent_pin_matches_child():
    assert hashlib.sha256(VERIFIER.read_bytes()).hexdigest() == VERIFIER_SHA256


def test_real_child_without_explicit_credential_refuses_before_network(
    tmp_path, binding
):
    env = {key: value for key, value in os.environ.items() if key != "HEROKU_API_KEY"}
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(VERIFIER),
            "--binding",
            json.dumps(binding),
            "--directory",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=2,
        env=env,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "REFUSED", "error_type": "KeyError"}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("phase", ["connect", "body"])
def test_whole_request_deadline_covers_connect_and_trickling_body(monkeypatch, phase):
    closed, requested = [], []
    real_timeout = asyncio.timeout

    def short_timeout(seconds):
        assert seconds == 10
        return real_timeout(0.02)

    monkeypatch.setattr(collector.asyncio, "timeout", short_timeout)

    class Writer:
        def write(self, data):
            requested.append(data)

        async def drain(self):
            pass

        def close(self):
            closed.append(True)

    async def connect(*args, **kwargs):
        if phase == "connect":
            await asyncio.Event().wait()
        reader = asyncio.StreamReader()
        reader.feed_data(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n["
        )
        # Socket stays open; a missing last byte must not reset the deadline.
        return reader, Writer()

    monkeypatch.setattr(collector.asyncio, "open_connection", connect)
    with pytest.raises(TimeoutError):
        asyncio.run(
            collector.HTTP("fake").get(collector.PLATFORM, "/apps/bainluck/dynos")
        )
    assert len(requested) == len(closed) == (phase == "body")


def test_cancellation_closes_transport_without_retry(monkeypatch):
    closed = []

    async def run():
        sent = asyncio.Event()

        class Writer:
            def write(self, data):
                sent.set()

            async def drain(self):
                pass

            def close(self):
                closed.append(True)

        async def connect(*args, **kwargs):
            return asyncio.StreamReader(), Writer()

        monkeypatch.setattr(collector.asyncio, "open_connection", connect)
        http = collector.HTTP("fake")
        task = asyncio.create_task(http.get(collector.PLATFORM, "/apps/bainluck/dynos"))
        await sent.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert http.attempts == 1

    asyncio.run(run())
    assert closed == [True]
