"""CAL-P127 — guards for the payload fetch's bounded 429 retry.

A whole-cell sweep spends its rate budget on ``db-query`` chunks and only THEN
asks for ``/api/calibration``. The public limit is 60 requests a minute, so the
payload fetch routinely arrives as the 61st request in the window and comes back
429. Measured on ``kalshi/golf`` 2026-08-29: the ``--by series`` fold completed
all sixty chunks and then threw the 429 out of ``main``, discarding two minutes
of finished DB work and writing no JSON.

The retry that fixes that is three lines, and every way of getting it wrong is
silent:

* **Swallow the 429 and return an empty payload.** The self-check then reads
  ``payload n=0`` and the delta line divides by zero or, worse, prints a fold of
  nothing as agreement. This is gotcha #53 exactly — an empty answer that is a
  response shape, not an absence.
* **Cache the payload to disk.** The self-check's whole warrant is that it
  compares the rail against the curve the site is serving *now*; a cache lets a
  stale curve certify a fold of a newer population, and nothing says so.
* **Retry forever.** A throttle becomes a hang, and a hang in a background sweep
  reads as a slow cell.
* **Retry on every HTTPError.** A 500 or a 404 is a real answer about the
  service and must not be re-asked into looking like a throttle.

The tests marked **SILENT** are the ones whose breakage still produces a
complete, plausible, well-formed table.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


#: A payload with one cell, two buckets, chosen so the fold's three outputs are
#: all distinct and hand-checkable:
#:   bucket 0   n=100  winners=10  sum_prob=20.0  -> |0.10 - 0.20| = 0.10
#:   bucket 1   n=100  winners=90  sum_prob=80.0  -> |0.90 - 0.80| = 0.10
#: ECE = (0.10*100 + 0.10*100) / 200 * 100 = 10.0
#: gap = ((20 - 10) + (80 - 90)) / 200 * 100 = 0.0
PAYLOAD = {
    "generated_at": "2026-08-29T00:36:47.978149+00:00",
    "population_version": "q268",
    "buckets": [
        {"source": "kalshi", "category": "golf", "bucket_idx": 0,
         "n": 100, "winners": 10, "sum_prob": 20.0},
        {"source": "kalshi", "category": "golf", "bucket_idx": 1,
         "n": 100, "winners": 90, "sum_prob": 80.0},
        {"source": "kalshi", "category": "economics", "bucket_idx": 0,
         "n": 999, "winners": 1, "sum_prob": 900.0},
    ],
}


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.example/api/calibration", code, "nope", {}, None)


@pytest.fixture()
def api_env(monkeypatch):
    monkeypatch.setenv("BAINLUCK_API", "https://api.example")
    # A retry that actually slept would make this suite take three minutes.
    monkeypatch.setattr(cce.time, "sleep", lambda _s: None)


def _install(monkeypatch, script):
    """``script`` is a list of ints (HTTP error codes) and ``None`` (success)."""
    calls = {"n": 0}

    def fake_urlopen(_url, timeout=None):
        i = calls["n"]
        calls["n"] += 1
        step = script[i] if i < len(script) else script[-1]
        if step is not None:
            raise _http_error(step)
        return _FakeResponse(json.dumps(PAYLOAD).encode())

    monkeypatch.setattr(cce.urllib.request, "urlopen", fake_urlopen)
    return calls


# --------------------------------------------------------------------------
# The retry does what it says
# --------------------------------------------------------------------------

def test_first_try_success_does_not_retry(api_env, monkeypatch):
    calls = _install(monkeypatch, [None])
    assert cce.fetch_payload() == PAYLOAD
    assert calls["n"] == 1


def test_a_429_is_re_asked_and_the_second_answer_is_returned(api_env, monkeypatch):
    calls = _install(monkeypatch, [429, None])
    assert cce.fetch_payload() == PAYLOAD
    assert calls["n"] == 2


def test_two_consecutive_429s_still_recover(api_env, monkeypatch):
    calls = _install(monkeypatch, [429, 429, None])
    assert cce.fetch_payload() == PAYLOAD
    assert calls["n"] == 3


# --------------------------------------------------------------------------
# ...and it stays bounded, and stays loud
# --------------------------------------------------------------------------

def test_the_retry_is_bounded_and_re_raises_the_429_unchanged(api_env, monkeypatch):
    """SILENT if broken as an infinite loop: a throttle becomes a hang."""
    calls = _install(monkeypatch, [429])
    with pytest.raises(urllib.error.HTTPError) as exc:
        cce.fetch_payload()
    assert exc.value.code == 429
    assert calls["n"] == cce.PAYLOAD_RETRIES


def test_the_bound_is_small_enough_to_finish(api_env):
    """A 'bounded' retry that waits half an hour is a hang with paperwork."""
    assert 2 <= cce.PAYLOAD_RETRIES <= 5
    assert cce.PAYLOAD_RETRIES * cce.PAYLOAD_BACKOFF_S <= 5 * 60


def test_the_backoff_clears_a_whole_rate_window(api_env):
    """The limit is 60/min, so anything under a minute re-asks inside it."""
    assert cce.PAYLOAD_BACKOFF_S >= 60


def test_a_non_429_http_error_is_not_retried(api_env, monkeypatch):
    """SILENT: re-asking a 500 three times makes an outage look like a throttle."""
    for code in (400, 404, 500, 502, 503):
        calls = _install(monkeypatch, [code])
        with pytest.raises(urllib.error.HTTPError) as exc:
            cce.fetch_payload()
        assert exc.value.code == code
        assert calls["n"] == 1, f"{code} was retried"


# --------------------------------------------------------------------------
# The thing the retry must NOT have quietly become
# --------------------------------------------------------------------------

def test_a_throttled_fetch_never_returns_an_empty_payload(api_env, monkeypatch):
    """SILENT, and the worst one: gotcha #53.

    An empty ``buckets`` list folds to ``n=0``, which the self-check prints as a
    payload cell of zero rows — a well-formed table asserting the published cell
    does not exist. Exhaustion must raise, never return.
    """
    _install(monkeypatch, [429])
    with pytest.raises(urllib.error.HTTPError):
        cce.fetch_payload()


def test_the_payload_is_not_cached_across_calls(api_env, monkeypatch):
    """SILENT: a cache lets a stale curve certify a fold of a newer population.

    Two calls must produce two fetches. The self-check's warrant is that it
    compares against what the site is serving now.
    """
    calls = _install(monkeypatch, [None])
    cce.fetch_payload()
    cce.fetch_payload()
    assert calls["n"] == 2


def test_fetch_payload_reads_no_file(api_env, monkeypatch):
    """The same claim from the other side: no on-disk cache path exists."""
    src = (SCRIPTS / "calibration_cell_exact.py").read_text()
    body = src.split("def fetch_payload(")[1].split("\ndef ")[0]
    # ``urlopen`` is the whole point of the function, so the file-open check has
    # to be spelled in a way that cannot match it — that near-miss is why this
    # assertion names each door instead of grepping for "open".
    for banned in (" open(", "=open(", "(open(", "read_text", "read_bytes",
                   "Path(", "pickle", "shelve", "os.environ.get(\"CACHE"):
        assert banned not in body, f"fetch_payload touches {banned!r}"
    assert "urlopen(" in body, "the guard is checking the wrong function"


# --------------------------------------------------------------------------
# payload_cell still folds the same quantity through the new door
# --------------------------------------------------------------------------

def test_payload_cell_folds_the_named_cell_only(api_env, monkeypatch):
    _install(monkeypatch, [None])
    n, ece, gap, meta = cce.payload_cell("kalshi", "golf")
    assert n == 200
    assert ece == 10.0
    assert gap == 0.0
    assert meta["generated_at"] == PAYLOAD["generated_at"]
    assert meta["population_version"] == "q268"


def test_payload_cell_survives_a_throttle_the_same_way(api_env, monkeypatch):
    """The reason this change exists: the sweep's finished work is not thrown away."""
    _install(monkeypatch, [429, None])
    n, ece, gap, _meta = cce.payload_cell("kalshi", "golf")
    assert (n, ece, gap) == (200, 10.0, 0.0)


def test_an_absent_cell_folds_to_zero_rows_not_a_crash(api_env, monkeypatch):
    """A cell genuinely not in the payload is a real answer and must stay one —
    which is exactly why the THROTTLED case must not be allowed to look like it."""
    _install(monkeypatch, [None])
    n, ece, gap, _meta = cce.payload_cell("kalshi", "no_such_category")
    assert n == 0
    assert ece is None and gap is None
