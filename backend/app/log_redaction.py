"""#12433: a credential in a URL's query string never reaches a log line.

StatPal authenticates with ``?access_key=``, The Odds API with ``?apiKey=`` and
DataGolf with ``?key=``. Two kinds of log line carried those values:

* httpx (0.28) logs every request on the ``httpx`` logger at INFO as
  ``HTTP Request: GET <full url> "HTTP/1.1 200 OK"``, and on Heroku the root
  logger is INFO. Fable's count on Nov 9 found the StatPal key in 6,456 lines
  in 24 h: worker-realtime 5,905, worker-background 550 and one-off ``run.4963``
  1.
* ``raise_for_status()`` writes the whole URL into the ``HTTPStatusError``'s
  text, so any line that prints the exception, or its traceback, prints the
  key (#6404 hit this on an open endpoint).

The redaction runs where every record is made: the logging module's record
factory. It covers every logger and every handler, including the handlers
Celery puts on the root logger when a worker starts. ``app/__init__.py``
installs it, so every process that imports anything from ``app`` has it before
its first request: web, workers, beat, worker-ws and one-off scripts. This
module imports only the standard library for that reason.
"""

import logging
import re
from collections.abc import Mapping

#: A query parameter whose NAME ends in one of these words is a credential:
#: ``access_key``, ``apiKey``, ``api_key``, ``key``, ``token``, ``access_token``,
#: ``client_secret``. Matching on the suffix will redact a harmless parameter now
#: and then. In a log line that costs nothing, and an under-match is the leak.
_CREDENTIAL_QUERY_RE = re.compile(
    r"(?i)([?&;][A-Za-z0-9_.\-]*(?:key|token|secret|password|signature)=)[^&;\s'\"#]+"
)

REDACTED = "***"

#: Argument types whose text can hold a request URL. Anything else is not turned
#: into a string here, so the check never runs a ``__str__`` that has side
#: effects (an ORM row's lazy load) for a record no handler would have printed.
_URL_BEARING_MODULES = ("httpx",)

#: Exceptions to walk through ``__cause__``/``__context__`` before giving up.
_MAX_CHAIN = 8

_INSTALLED = "_redacts_credentials_12433"


def redact_credentials(text: object) -> str:
    """``text`` as a string, with every credential query value replaced."""
    return _CREDENTIAL_QUERY_RE.sub(r"\g<1>" + REDACTED, str(text))


def _carries_a_credential(value: object) -> bool:
    if not (
        isinstance(value, (str, BaseException))
        or type(value).__module__.split(".")[0] in _URL_BEARING_MODULES
    ):
        return False
    try:
        return _CREDENTIAL_QUERY_RE.search(str(value)) is not None
    except Exception:  # noqa: BLE001 — a log call must never fail here
        return False


def _redact_exception_chain(exc: BaseException | None) -> bool:
    """Rewrites each exception in the chain whose text carries a credential.

    ``args`` is what ``str()`` reads for httpx's errors, so after this every
    reader of the exception (a JSON formatter, Sentry, a later ``str(e)``) sees
    the redacted text. Returns whether anything was rewritten.
    """
    rewritten, seen = False, 0
    while exc is not None and seen < _MAX_CHAIN:
        seen += 1
        if _carries_a_credential(exc):
            try:
                exc.args = (redact_credentials(exc),)
                rewritten = True
            except Exception:  # noqa: BLE001
                pass
        exc = exc.__cause__ or exc.__context__
    return rewritten


def redact_record(record: logging.LogRecord) -> None:
    """Redacts ``record`` in place: its message and the exception it carries."""
    args = record.args
    values = args.values() if isinstance(args, Mapping) else args if isinstance(args, tuple) else ()
    if _carries_a_credential(record.msg) or any(_carries_a_credential(v) for v in values):
        # Formatted once here, arguments dropped, so no handler downstream can
        # format the original URL back in.
        record.msg = redact_credentials(record.getMessage())
        record.args = ()
    exc_info = record.exc_info
    if exc_info and _redact_exception_chain(exc_info[1]):
        # A formatter uses `exc_text` when it is set; this covers an exception
        # whose own `__str__` ignores `args`.
        record.exc_text = redact_credentials(logging.Formatter().formatException(exc_info))


def install_log_redaction() -> None:
    """Wrap the record factory once, so every new record is redacted."""
    previous = logging.getLogRecordFactory()
    if getattr(previous, _INSTALLED, False):
        return

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        try:
            redact_record(record)
        except Exception:  # noqa: BLE001 — a log call must never fail here
            pass
        return record

    setattr(factory, _INSTALLED, True)
    logging.setLogRecordFactory(factory)
