"""Read-only child collector for an explicitly invoked recovery wrapper.

Not an authorization mechanism or a writer hold. This module is deliberately
standalone so the parent can hash and execute these exact bytes with -I.
Never invoked by startup. Source preparation does not authorize live invocation.
"""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import time
from uuid import UUID

MAX_BYTES = 1048576
APPS = ("bainluck", "bainluck-heavy")


MAX_REQUESTS = 8
PLATFORM = "api.heroku.com"


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def allowed(host, path):
    if host != PLATFORM:
        return False
    return any(
        path
        in (f"/apps/{app}/releases", f"/apps/{app}/formation", f"/apps/{app}/dynos")
        or re.fullmatch(
            f"/apps/{app}/slugs/[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}",
            path,
        )
        for app in APPS
    )


class HTTP:
    def __init__(self, token):
        need(
            isinstance(token, str)
            and 0 < len(token) <= 4096
            and all(32 < ord(c) < 127 for c in token),
            "token_shape",
        )
        self.token = token
        self.attempts = 0

    async def get(self, host, path):
        need(allowed(host, path), "http_not_allowed")
        need(self.attempts < MAX_REQUESTS, "http_request_budget")
        self.attempts += 1  # Debit before connect/send, including failed attempts.
        writer = None
        releases = path.endswith("/releases")
        accept = (
            "application/vnd.heroku+json; version=3.sdk"
            if releases
            else "application/vnd.heroku+json; version=3"
        )
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
            f"Authorization: Bearer {self.token}\r\nAccept: {accept}\r\n"
            "Accept-Encoding: identity\r\nConnection: close\r\n"
        )
        if releases:
            request += "Range: version ..; max=5, order=desc\r\n"
        request += "\r\n"
        try:
            async with asyncio.timeout(10):
                reader, writer = await asyncio.open_connection(
                    host,
                    443,
                    ssl=ssl.create_default_context(),
                    server_hostname=host,
                    limit=65536,
                )
                writer.write(request.encode("ascii"))
                await writer.drain()
                header = await reader.readuntil(b"\r\n\r\n")
                need(len(header) <= 65536, "http_headers_size")
                lines = header.decode("ascii").split("\r\n")
                status = int(lines[0].split()[1])
                need(status == 200 or (releases and status == 206), "http_status")
                headers = {}
                for line in lines[1:]:
                    if not line:
                        continue
                    k, v = line.split(":", 1)
                    k, v = k.lower(), v.strip()
                    # Ignore repeated unused metadata; never merge framing,
                    # representation or pagination authority.
                    if k in headers:
                        need(
                            k
                            not in {
                                "content-length",
                                "transfer-encoding",
                                "content-type",
                                "content-encoding",
                                "next-range",
                                "content-range",
                            },
                            "http_duplicate_header",
                        )
                        continue
                    headers[k] = v
                need(
                    headers.get("content-encoding", "identity") == "identity",
                    "http_encoding",
                )
                need(
                    headers.get("content-type", "").split(";")[0] == "application/json",
                    "http_content_type",
                )
                # Heroku's installed client follows a nonempty Next-Range.
                # Content-Range describes this response, not another page. The
                # status check above also refuses206 for non-release responses.
                # Releases deliberately use bounded history; newest must be current.
                need(releases or not headers.get("next-range"), "http_pagination")
                need(
                    not (
                        "transfer-encoding" in headers and "content-length" in headers
                    ),
                    "http_framing",
                )
                if "transfer-encoding" in headers:
                    need(headers["transfer-encoding"] == "chunked", "http_transfer")
                    chunks = bytearray()
                    for _ in range(10000):
                        line = await reader.readline()
                        need(
                            len(line) <= 32 and line.endswith(b"\r\n"),
                            "http_chunk_line",
                        )
                        size = int(line.strip(), 16)
                        need(0 <= size <= MAX_BYTES - len(chunks), "http_body_size")
                        if size == 0:
                            need(await reader.readline() == b"\r\n", "http_trailers")
                            break
                        chunk = await reader.readexactly(size + 2)
                        need(chunk.endswith(b"\r\n"), "http_chunk_end")
                        chunks.extend(chunk[:-2])
                    else:
                        need(False, "http_chunk_count")
                    body = bytes(chunks)
                elif "content-length" in headers:
                    size = int(headers["content-length"])
                    need(0 <= size <= MAX_BYTES, "http_body_size")
                    body = await reader.readexactly(size)
                else:
                    # Do not rely on read(n) returning all bytes before EOF.
                    chunks = bytearray()
                    while True:
                        chunk = await reader.read(
                            min(65536, MAX_BYTES + 1 - len(chunks))
                        )
                        if not chunk:
                            break
                        chunks.extend(chunk)
                        need(len(chunks) <= MAX_BYTES, "http_body_size")
                    body = bytes(chunks)
                json.loads(body)
                return body
        finally:
            if writer:
                writer.close()


def collect(binding, directory):
    return asyncio.run(_collect(binding, directory))


async def _collect(binding, directory):
    if set(binding) != {
        "run_id",
        "step",
        "nonce",
        "expected_authority",
        "expected_primary",
        "apps",
    }:
        raise ValueError("exact binding required")
    UUID(binding["run_id"])
    if not re.fullmatch(r"[0-9a-f]{32}", binding["nonce"]):
        raise ValueError("fresh nonce required")
    if set(binding["apps"]) != set(APPS) or any(directory.iterdir()):
        raise ValueError("fresh collection directory and exact apps required")
    token = os.environ["HEROKU_API_KEY"]
    http = HTTP(token)
    reads = []

    async def record(name, endpoint):
        start = time.time_ns()
        data = await http.get(PLATFORM, endpoint)
        path = directory / (name + ".json")
        with path.open("xb") as raw:
            os.chmod(path, 0o600)
            raw.write(data)
        end = time.time_ns()
        reads.append(
            {
                "name": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "start_ns": start,
                "end_ns": end,
            }
        )

    for app in APPS:
        source = binding["apps"][app]
        # The path is derived from a validated UUID, never caller URL text.
        slug = str(UUID(source["slug"]))
        await record(app + "-releases", f"/apps/{app}/releases")
        await record(app + "-slug", f"/apps/{app}/slugs/{slug}")
        await record(app + "-formation", f"/apps/{app}/formation")
        await record(app + "-dynos", f"/apps/{app}/dynos")
    return {"binding": binding, "reads": reads}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        if len(args.binding) > 8192:
            raise ValueError("binding too large")
        result = collect(json.loads(args.binding), args.directory)
    except Exception as exc:
        print(json.dumps({"status": "REFUSED", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
