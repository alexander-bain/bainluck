"""#12433: a credential in a URL's query string never reaches a log line.

On Heroku the root logger is INFO, and httpx logs every request there as
``HTTP Request: GET <full url> "HTTP/1.1 200 OK"``. StatPal authenticates with
``?access_key=``, so its key rode that line into the dyno log; a live one was
read off it during the #5341 dry run. The Odds API (``apiKey``) and DataGolf
(``key``) put theirs in the same place.

Every key in this file is made up. ``app.log_redaction`` is imported inside
the tests, so that on a base without it the behaviour tests fail on the leak
itself rather than the file failing to collect.
"""

import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import httpx
import pytest

FAKE_STATPAL_KEY = "statpalstatpal"
BACKEND = Path(__file__).resolve().parents[1]


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


@pytest.mark.parametrize(
    "url,secret",
    [
        (
            f"https://statpal.io/api/v1/nfl/schedule?access_key={FAKE_STATPAL_KEY}&season=2026",
            FAKE_STATPAL_KEY,
        ),
        (
            "https://api.the-odds-api.com/v4/sports/upcoming/odds"
            "?apiKey=oddsoddsodds&regions=us&markets=h2h",
            "oddsoddsodds",
        ),
        (
            "https://feeds.datagolf.com/preds/in-play?tour=pga&key=golfgolfgolf",
            "golfgolfgolf",
        ),
        (
            "https://example.test/v1/thing?access_token=tokentoken",
            "tokentoken",
        ),
    ],
)
def test_the_http_clients_request_line_does_not_print_the_credential(caplog, url, secret):
    caplog.set_level(logging.INFO, logger="httpx")
    with httpx.Client(transport=httpx.MockTransport(_ok)) as client:
        client.get(url)
    lines = [r.getMessage() for r in caplog.records if r.name == "httpx"]
    assert lines, "httpx logged no request line, so this test proves nothing"
    assert secret not in caplog.text
    assert any("=***" in line and "HTTP Request: GET https://" in line for line in lines)


def test_a_url_without_a_credential_is_logged_whole(caplog):
    """The control: the request line keeps its use for everything else."""
    caplog.set_level(logging.INFO, logger="httpx")
    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=team"
    with httpx.Client(transport=httpx.MockTransport(_ok)) as client:
        client.get(url)
    assert url in caplog.text


# A fresh interpreter with Heroku's logging shape (root at INFO with a stream
# handler) that imports only the StatPal client, so the redaction has to come
# from importing the app, not from anything this test session set up.
_STATPAL_SCHEDULE_READ = textwrap.dedent(
    """
    import asyncio, io, logging, os
    import httpx

    stream = io.StringIO()
    logging.root.handlers = [logging.StreamHandler(stream)]
    logging.root.setLevel(logging.INFO)

    from app.services.statpal_api import StatPalAPIService

    def answer(request):
        return httpx.Response(200, json={"schedule": []})

    async def main():
        service = StatPalAPIService(api_key=os.environ["FAKE_STATPAL_KEY"])
        await service.client.aclose()
        service.client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
        try:
            return await service._get("nfl", "schedule")
        finally:
            await service.client.aclose()

    print("PAYLOAD", asyncio.run(main()))
    print(stream.getvalue())
    """
)


def test_a_successful_statpal_schedule_read_logs_its_url_without_the_key():
    env = {k: v for k, v in os.environ.items() if k not in ("STATPAL_API_KEY", "DYNO")}
    env["FAKE_STATPAL_KEY"] = FAKE_STATPAL_KEY
    proc = subprocess.run(
        [sys.executable, "-c", _STATPAL_SCHEDULE_READ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    assert "PAYLOAD {'schedule': []}" in proc.stdout
    assert "HTTP Request: GET https://statpal.io/api/v1/nfl/schedule?access_key=***" in proc.stdout
    assert FAKE_STATPAL_KEY not in out


async def test_a_failed_request_count_read_logs_no_key(caplog, monkeypatch):
    """``raise_for_status()`` writes the whole URL into the exception's text."""
    from app.services import statpal_api

    real_client = httpx.AsyncClient

    def refusing_client(**kwargs):
        refuse = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "no"}))
        return real_client(transport=refuse, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", refusing_client)
    caplog.set_level(logging.WARNING, logger=statpal_api.logger.name)

    assert await statpal_api.get_statpal_request_count(api_key=FAKE_STATPAL_KEY) is None

    warnings = [r.getMessage() for r in caplog.records if r.name == statpal_api.logger.name]
    assert warnings and "401" in warnings[0] and "access_key=***" in warnings[0]
    assert FAKE_STATPAL_KEY not in caplog.text


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Client error '401 Unauthorized' for url "
            "'https://statpal.io/api/user-request-count?access_key=abc123'",
            "Client error '401 Unauthorized' for url "
            "'https://statpal.io/api/user-request-count?access_key=***'",
        ),
        ("https://x.test/a?apiKey=k1&regions=us&key=k2", "https://x.test/a?apiKey=***&regions=us&key=***"),
        ("https://x.test/a?API_KEY=ab%2Bcd#frag", "https://x.test/a?API_KEY=***#frag"),
        ("GET https://x.test/a?client_secret=s1 done", "GET https://x.test/a?client_secret=*** done"),
    ],
)
def test_redact_credentials(text, expected):
    from app.log_redaction import redact_credentials

    assert redact_credentials(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "https://statsapi.mlb.com/api/v1/schedule?sportId=1&season=2026",
        "sort_key=commence_time",  # no query string, so not a URL parameter
        "cache key=abc in plain prose",
    ],
)
def test_redact_credentials_leaves_everything_else_alone(text):
    from app.log_redaction import redact_credentials

    assert redact_credentials(text) == text


def test_a_record_that_does_not_format_passes_through_untouched():
    from app.log_redaction import CredentialQueryFilter

    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, "%s and %s", ("one",), None)
    assert CredentialQueryFilter().filter(record) is True
    assert (record.msg, record.args) == ("%s and %s", ("one",))


def test_importing_the_app_installs_exactly_one_filter_on_the_http_client_logger():
    import app  # noqa: F401 — the import is the installation
    from app.log_redaction import CredentialQueryFilter, install_http_client_log_redaction

    install_http_client_log_redaction()
    filters = logging.getLogger("httpx").filters
    assert sum(isinstance(f, CredentialQueryFilter) for f in filters) == 1
