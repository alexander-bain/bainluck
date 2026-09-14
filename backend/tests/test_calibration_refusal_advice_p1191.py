"""CAL-P1191 (#997): a refusal may only promise a wait it can keep.

THE DEFECT, MEASURED ON PRODUCTION 2026-09-13 20:57 PT. ``/api/calibration``
answered 503 with ``Retry-After: 30`` and the sentence *"Calibration data is
temporarily unavailable. It is rebuilt hourly — please retry shortly."*, and
bainluck.com/calibration printed that sentence to readers. Neither half was
true: the D112 population-version rollover had made every stored snapshot
unservable at any age, the rebuild was 65 of 128 units in, and publication was
eight to eleven hourly beats away. A reader who did what the page said — retry
shortly — got the same page, for four hours and counting.

WHY ONE SENTENCE WAS NEVER ENOUGH. The 503 has two reasons and they are
opposite in kind:

  * ``route_budget_exhausted`` — THIS REQUEST ran out of its own time budget. A
    servable snapshot may well exist and the very next request may get it.
    "Please retry shortly" with 30 s is exactly right, and this suite pins that
    it survives.
  * ``no_trustworthy_snapshot`` — reached only after the over-age durable tier
    has already declined, i.e. nothing servable exists at ANY age. The wait is
    however long a full rebuild takes. Nothing here can name that number, so
    the honest copy names no number at all.

So these tests assert the DIFFERENCE, not just the two values: a change that
collapses the advice back to one sentence reddens them even if it picks the
cautious sentence, because then the transient case starts under-promising and
the mapping has stopped doing its job.

Route-level, driving ``public_calibration`` against a fake Redis, so both
branches are proved end-to-end rather than at the helper (gotcha #43, both
directions). The unknown-reason branch is the exception and says why.
"""

from __future__ import annotations

import pytest

from app.utils import request_cache as rc
from tests.conftest import unavailable_body

# ``pytest.ini`` runs asyncio in AUTO mode, so the async tests below need no
# mark — and a module-level ``pytestmark`` would put one on the two synchronous
# tests at the bottom, which pytest then warns about.

#: Phrases that assert a wait the terminal refusal cannot keep. "hourly" is here
#: because the retired sentence used it to imply the next hour would fix it.
#:
#: THE SECOND GROUP IS RULING 142, RE-STATED ON THIS SIDE OF THE WIRE, AND IT IS
#: NOT DUPLICATION. ``frontend/lib/copyBans.ts`` already forbids "check back",
#: "coming soon" and their family — a section states what it IS, not what it
#: WILL be — and ``shippedCopyBans.test.ts`` enforces it by scanning the BUILT
#: BUNDLE. That scan caught this ship's first draft, but only because the page
#: carries a hardcoded fallback copy of the sentence. The sentence the reader
#: normally sees is composed by this route at runtime and is in no bundle, so
#: the ruling had no gate on the path that actually serves it. It does now.
PROMISE_WORDS = (
    "shortly",
    "hourly",
    "moment",
    "second",
    "minute",
    "check back",
    "coming soon",
    "stay tuned",
    "will appear",
)


class _FakeRedis:
    """Nothing stored anywhere — the state the terminal refusal is for."""

    async def get(self, key):
        return None


def _use(monkeypatch, client):
    async def _getter():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    return client


@pytest.fixture(autouse=True)
def _clean_state():
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


async def _refuse_with_nothing_stored(monkeypatch) -> dict:
    """The production state: no snapshot anywhere, compute gets nowhere."""
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _use(monkeypatch, _FakeRedis())
    monkeypatch.setattr(rc, "CALIBRATION_COMPUTE_DEADLINE_MS", 100)

    async def _hang(db):
        import asyncio

        await asyncio.sleep(30)

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _hang)
    res = await calibration.public_calibration(db=object())
    body = unavailable_body(res)
    # Starlette's ``Headers`` is case-insensitive; ``dict()`` of it is not.
    body["_retry_after_header"] = res.headers["Retry-After"]
    return body


async def _refuse_with_no_budget(monkeypatch) -> dict:
    """The transient state: the request's own budget was gone on arrival."""
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _use(monkeypatch, _FakeRedis())
    monkeypatch.setattr(rc, "CALIBRATION_ROUTE_BUDGET_MS", 0)

    async def _boom(db):
        raise AssertionError("a compute was started with no budget left")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)
    res = await calibration.public_calibration(db=object())
    body = unavailable_body(res)
    # Starlette's ``Headers`` is case-insensitive; ``dict()`` of it is not.
    body["_retry_after_header"] = res.headers["Retry-After"]
    return body


async def test_the_terminal_refusal_promises_the_reader_no_timing(monkeypatch):
    """Nothing servable at any age ⇒ no "shortly", no "hourly", no number."""
    body = await _refuse_with_nothing_stored(monkeypatch)

    assert body["reason"] == "no_trustworthy_snapshot"
    message = body["message"].lower()
    for word in PROMISE_WORDS:
        assert word not in message, (
            f"the terminal refusal promised {word!r} — this is the exact "
            f"sentence production printed for four hours: {body['message']!r}"
        )
    assert body["message"].strip(), "a refusal with no sentence is the old opaque failure"


async def test_the_terminal_refusal_stops_advising_a_thirty_second_wait(monkeypatch):
    body = await _refuse_with_nothing_stored(monkeypatch)

    assert body["retry_after_s"] == 900
    assert body["_retry_after_header"] == "900"


async def test_the_transient_refusal_keeps_the_short_promise(monkeypatch):
    """The other direction: a budget miss IS seconds away, and must still say so.

    Without this, "make the copy cautious" passes by making every refusal
    cautious, and a reader whose single request timed out is told to come back
    in fifteen minutes for data that is already sitting in Redis.
    """
    body = await _refuse_with_no_budget(monkeypatch)

    assert body["reason"] == "route_budget_exhausted"
    assert body["retry_after_s"] == 30
    assert body["_retry_after_header"] == "30"
    assert "shortly" in body["message"].lower()


async def test_the_two_refusals_do_not_give_the_same_advice(monkeypatch):
    """The discriminating assertion. One sentence for both reasons is the bug."""
    terminal = await _refuse_with_nothing_stored(monkeypatch)
    transient = await _refuse_with_no_budget(monkeypatch)

    assert terminal["message"] != transient["message"]
    assert terminal["retry_after_s"] > transient["retry_after_s"]


@pytest.mark.parametrize("refuse", [_refuse_with_nothing_stored, _refuse_with_no_budget])
async def test_the_header_and_the_field_are_one_number(monkeypatch, refuse):
    """A client that trusts the header and one that reads the body agree.

    Both were literal ``30``s before, so they could not disagree; now the
    number is computed once and written twice, which is where they can.
    """
    body = await refuse(monkeypatch)

    assert int(body["_retry_after_header"]) == body["retry_after_s"]


@pytest.mark.parametrize("refuse", [_refuse_with_nothing_stored, _refuse_with_no_budget])
async def test_the_legacy_detail_mirror_carries_the_same_advice(monkeypatch, refuse):
    """#1680's surface: the shipped page reads ``error.detail.message``.

    Per-reason copy that reached only the top level would leave the page
    printing nothing while the body carried the sentence.
    """
    body = await refuse(monkeypatch)
    mirror = body["detail"]

    assert mirror["message"] == body["message"]
    assert mirror["retry_after_s"] == body["retry_after_s"]
    assert mirror["reason"] == body["reason"]


def test_a_reason_nobody_mapped_falls_to_the_cautious_half():
    """The branch no request can reach today, and the reason it is a function.

    Two call sites exist, so an unmapped reason cannot be produced end-to-end —
    but the next reason someone adds lands here, and the failure mode is silent:
    it would inherit whatever the default says. The default is the sentence that
    is never a lie, and this pins that choice rather than the lookup.
    """
    from app.routes.calibration import UNAVAILABLE_ADVICE, unavailable_advice

    retry_after_s, message = unavailable_advice("a_reason_added_in_2027")

    assert retry_after_s == 900
    assert "shortly" not in message.lower()
    assert (retry_after_s, message) != UNAVAILABLE_ADVICE["route_budget_exhausted"]


def test_only_the_transient_reason_is_allowed_to_promise_a_short_wait():
    """Scans every mapped sentence, so a third mapping cannot smuggle one in."""
    from app.routes.calibration import (
        UNAVAILABLE_ADVICE,
        UNAVAILABLE_ADVICE_DEFAULT,
    )

    for reason, (retry_after_s, message) in UNAVAILABLE_ADVICE.items():
        if reason == "route_budget_exhausted":
            continue
        assert retry_after_s >= 900, (
            f"{reason!r} advises a {retry_after_s}s wait; only a refusal caused "
            f"by this request's own budget is that fast"
        )
        for word in PROMISE_WORDS:
            assert word not in message.lower(), f"{reason!r} promised {word!r}"

    default_retry, default_message = UNAVAILABLE_ADVICE_DEFAULT
    assert default_retry >= 900
    for word in PROMISE_WORDS:
        assert word not in default_message.lower()
