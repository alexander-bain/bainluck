"""#12433: a credential in a URL's query string never reaches a log line.

StatPal authenticates with ``?access_key=``, The Odds API with ``?apiKey=`` and
DataGolf with ``?key=``. httpx (0.28) logs every request on the ``httpx``
logger at INFO as ``HTTP Request: GET <full url> "HTTP/1.1 200 OK"``, and on
Heroku the root logger is INFO (``app/main.py``, ``app/tasks/__init__.py``), so
every call printed its key to the dyno log. On Nov 9 a live StatPal key was
read off that line during the #5341 dry run on a one-off dyno.

This module imports only the standard library, because ``app/__init__.py``
installs the filter. That way every process that imports anything from
``app`` (web, workers, beat, worker-ws, one-off scripts) has it before its
first request, whatever its own logging setup does later. The filter sits on
the LOGGER, not on a handler: Celery replaces the root handlers when a worker
starts, and a handler filter would go with them.
"""

import logging
import re

#: A query parameter whose NAME ends in one of these words is a credential:
#: ``access_key``, ``apiKey``, ``api_key``, ``key``, ``token``, ``access_token``,
#: ``client_secret``. Matching on the suffix will redact a harmless parameter now
#: and then. In a log line that costs nothing, and an under-match is the leak.
_CREDENTIAL_QUERY_RE = re.compile(
    r"(?i)([?&;][A-Za-z0-9_.\-]*(?:key|token|secret|password|signature)=)[^&;\s'\"#]+"
)

REDACTED = "***"

#: httpx writes its request line on this one logger (``httpx._client``).
HTTP_CLIENT_LOGGER = "httpx"


def redact_credentials(text: object) -> str:
    """``text`` as a string, with every credential query value replaced."""
    return _CREDENTIAL_QUERY_RE.sub(r"\g<1>" + REDACTED, str(text))


class CredentialQueryFilter(logging.Filter):
    """Rewrites a record whose message carries a credential query value.

    The message is formatted once here and the arguments are dropped, so no
    handler downstream can format the original URL back in. A record that
    doesn't format passes through untouched, because a log filter must never
    raise.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — a log call must never fail here
            return True
        redacted = redact_credentials(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def install_http_client_log_redaction() -> None:
    """Put the filter on the HTTP client's logger, once."""
    target = logging.getLogger(HTTP_CLIENT_LOGGER)
    if not any(isinstance(f, CredentialQueryFilter) for f in target.filters):
        target.addFilter(CredentialQueryFilter())
