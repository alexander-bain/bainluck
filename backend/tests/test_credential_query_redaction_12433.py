"""#12433: a credential in a URL's query string never reaches a log line.

On Heroku the root logger is INFO, and httpx logs every request there as
``HTTP Request: GET <full url> "HTTP/1.1 200 OK"``. StatPal authenticates with
``?access_key=``, so its key rode that line into the dyno log: 6,456 lines in
24 h, almost all from the workers. ``raise_for_status()`` also writes the whole
URL into the exception's text, so any line that prints the exception or its
traceback printed the key too. The Odds API (``apiKey``) and DataGolf
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


def _refused(url: str) -> httpx.HTTPStatusError:
    """The error ``raise_for_status()`` raises, built by httpx itself."""
    request = httpx.Request("GET", url)
    response = httpx.Response(401, request=request)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e
    raise AssertionError("httpx did not refuse a 401")


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


def test_an_app_line_that_prints_the_exception_prints_no_key(caplog):
    """The shape of ``odds_api.py``: ``logger.warning("Error fetching %s: %s", sport, e)``."""
    error = _refused("https://api.the-odds-api.com/v4/sports/?apiKey=oddsoddsodds")
    assert "oddsoddsodds" in str(error), "the planted key must start in the text"
    caplog.set_level(logging.WARNING, logger="app.probe_12433")

    logging.getLogger("app.probe_12433").warning("Error fetching %s: %s", "nfl", error)
    logging.getLogger("app.probe_12433").warning(f"Error fetching nfl: {error}")

    assert "oddsoddsodds" not in caplog.text
    assert caplog.text.count("apiKey=***") == 2


def test_a_logged_traceback_prints_no_key(caplog):
    from pythonjsonlogger.json import JsonFormatter

    caplog.set_level(logging.ERROR, logger="app.probe_12433")
    try:
        raise RuntimeError("the poll failed") from _refused(
            "https://api.the-odds-api.com/v4/sports/?apiKey=oddsoddsodds"
        )
    except RuntimeError:
        logging.getLogger("app.probe_12433").exception("odds poll failed")

    (record,) = [r for r in caplog.records if r.name == "app.probe_12433"]
    plain = logging.Formatter().format(record)
    as_json = JsonFormatter().format(record)  # the web dyno's formatter
    assert "HTTPStatusError" in plain and "apiKey=***" in plain
    assert "oddsoddsodds" not in plain
    assert "oddsoddsodds" not in as_json


async def test_a_failed_statpal_request_count_read_logs_no_key(caplog, monkeypatch):
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


# Each process shape, in a fresh interpreter with the app's own logging setup:
# the web dyno imports app.main (JSON handler, root at INFO, as DYNO is set), a
# worker additionally runs Celery's own logging setup (which replaces the root
# handlers), and a one-off script brings its own basicConfig. Nothing from this
# test session is in the child, so the redaction has to come from the app.
_SHAPES = {
    "web": "import app.main",
    "worker": (
        "from app.tasks import celery_app\n"
        "celery_app.log.setup(loglevel='INFO', redirect_stdouts=False)"
    ),
    "one-off": "logging.basicConfig(level=logging.INFO)",
}

_KEYED_READS = """
import asyncio, logging, os
import httpx
{setup}
from app.services.statpal_api import StatPalAPIService

key = os.environ["FAKE_STATPAL_KEY"]


def answer(request):
    if request.url.path.endswith("/schedule"):
        return httpx.Response(200, json={{"schedule": []}})
    return httpx.Response(401, json={{"error": "no"}})


async def main():
    service = StatPalAPIService(api_key=key)
    await service.client.aclose()
    service.client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    try:
        print("PAYLOAD", await service._get("nfl", "schedule"), flush=True)
        response = await service.client.get(
            "https://statpal.io/api/user-request-count", params={{"access_key": key}}
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logging.getLogger("app.probe_12433").warning("request count failed: %s", e)
            logging.getLogger("app.probe_12433").exception("request count failed")
    finally:
        await service.client.aclose()


asyncio.run(main())
"""


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_every_process_shape_logs_a_keyed_statpal_read_without_the_key(shape):
    env = {k: v for k, v in os.environ.items() if k not in ("STATPAL_API_KEY", "DYNO")}
    env["FAKE_STATPAL_KEY"] = FAKE_STATPAL_KEY
    if shape != "one-off":
        env["DYNO"] = f"{shape}.1"
    script = textwrap.dedent(_KEYED_READS).format(setup=_SHAPES[shape])
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "PAYLOAD {'schedule': []}" in proc.stdout
    # The request line, the app line and the traceback all printed, redacted.
    assert "statpal.io/api/v1/nfl/schedule?access_key=***" in out
    assert "user-request-count?access_key=***" in out
    assert "HTTPStatusError" in out
    assert FAKE_STATPAL_KEY not in out


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
    from app.log_redaction import redact_record

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "%s and %s?key=", ("one",), None)
    redact_record(record)  # must not raise
    assert record.args == ("one",)


def test_an_argument_that_is_not_url_bearing_is_never_turned_into_text():
    """An ORM row's ``__str__`` can lazy-load; the check must not call it."""
    from app.log_redaction import redact_record

    class Touchy:
        def __str__(self):
            raise AssertionError("str() was called on a non-URL argument")

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "row %s", (Touchy(),), None)
    redact_record(record)
    assert record.msg == "row %s"


def test_importing_the_app_installs_the_redaction_exactly_once():
    import app  # noqa: F401 — the import is the installation
    from app.log_redaction import install_log_redaction

    before = logging.getLogRecordFactory()
    assert getattr(before, "_redacts_credentials_12433", False)
    install_log_redaction()
    assert logging.getLogRecordFactory() is before
