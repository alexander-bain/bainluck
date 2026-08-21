"""The labelling nudge rides the digest — for ONE person (UX-P117, #2060 item 6).

── THE GUARD, AND WHY IT IS THE WHOLE TEST ──────────────────────────────────────

``_run_morning_digest`` renders ONE payload and broadcasts it to every opted-in
device. So a labelling reminder added unconditionally to
``render_digest_payload`` does not nudge Alex — it tells the entire user base to
go and label Alex's gold set, at 7:05 every morning, with no way to turn it off
short of unsubscribing from the digest.

The tests therefore assert BOTH directions (gotcha #43): the admin gets the line
AND the non-admin's payload is byte-identical to the one that shipped before this
queue. A one-directional assertion here cannot tell "correctly targeted" from
"broadcast to everyone".

The second guard is on the deep link. A push has one tap target, and the digest's
is the most interesting market of the day. The nudge must not take it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tasks.morning_digest import admin_digest_tokens, digest_recipients
from app.utils.morning_digest import (
    LABELING_DEEP_LINK,
    LABELING_NOTIFICATION_CATEGORY,
    DigestCandidate,
    render_digest_payload,
)

ADMIN_USER_ID = 364  # DEFAULT_ADMIN_USER_IDS


class _Row(SimpleNamespace):
    """A DeviceToken stand-in whose attributes live in ``__dict__``.

    Mirrors `test_morning_digest_token_kind._Row`: the production reader goes
    through ``__dict__`` to dodge an ORM lazy load, so a stand-in that exposes the
    column any other way tests a path that does not ship.
    """


def _device(id=1, token="tok", kind="fcm"):
    row = _Row(id=id, device_token=token)
    if kind is not None:
        row.token_kind = kind
    return row


def _user(id=1, email="someone@example.com", opted_in=True):
    return SimpleNamespace(
        id=id, email=email, push_preferences={"morning_digest": opted_in}
    )


def _candidate(market_id=1):
    return DigestCandidate(
        market_id=market_id,
        name="Will the Fed cut rates in September?",
        leader_name="Yes",
        leader_prob=0.62,
        interestingness=80.0,
        category="economics",
    )


# ---------------------------------------------------------------------------
# admin_digest_tokens — both directions
# ---------------------------------------------------------------------------


def test_admin_by_default_user_id_is_found():
    rows = [(_device(token="alex-tok"), _user(id=ADMIN_USER_ID))]
    assert admin_digest_tokens(rows) == {"alex-tok"}


def test_a_normal_user_is_not_an_admin():
    rows = [(_device(token="someone-tok"), _user(id=9999))]
    assert admin_digest_tokens(rows) == set()


def test_an_anonymous_device_is_not_an_admin():
    """A device with no user attached must never receive the nudge."""
    rows = [(_device(token="anon-tok"), None)]
    assert admin_digest_tokens(rows) == set()


def test_admin_by_email_is_found(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_EMAILS", "alex@bainluck.com")
    rows = [(_device(token="e-tok"), _user(id=42, email="Alex@BainLuck.com"))]
    assert admin_digest_tokens(rows) == {"e-tok"}


def test_a_null_email_does_not_crash_the_broadcast():
    rows = [(_device(token="t"), _user(id=42, email=None))]
    assert admin_digest_tokens(rows) == set()


def test_admin_and_recipient_sets_are_independent():
    """Being an admin does not opt you in; opting in does not make you an admin.

    Both gates apply, and the send loop intersects them — an opted-out admin gets
    no digest at all, nudge included.
    """
    rows = [
        (_device(id=1, token="alex"), _user(id=ADMIN_USER_ID, opted_in=False)),
        (_device(id=2, token="other"), _user(id=7, opted_in=True)),
    ]
    assert digest_recipients(rows) == [(2, "other")]
    assert admin_digest_tokens(rows) == {"alex"}


# ---------------------------------------------------------------------------
# render_digest_payload — the nudge itself, both directions
# ---------------------------------------------------------------------------


def test_the_default_payload_is_unchanged():
    """The non-admin's push must be exactly what it was before this queue."""
    payload = render_digest_payload([_candidate()], payload_id="digest-20260821")
    assert "Label today" not in payload.body
    assert "labeling_url" not in payload.data
    assert "category" not in payload.data


def test_the_admin_payload_carries_the_line():
    payload = render_digest_payload(
        [_candidate()], payload_id="digest-20260821", labeling_reminder=True
    )
    assert "Label today" in payload.body
    assert payload.data["labeling_url"] == LABELING_DEEP_LINK
    assert payload.data["category"] == LABELING_NOTIFICATION_CATEGORY


def test_the_nudge_does_not_steal_the_tap_target():
    """The digest's job is the market; the nudge is an ACTION beside it.

    Overwriting `url` would convert the tap target into an admin screen for the
    one person who most wants the market.
    """
    plain = render_digest_payload([_candidate(7)], payload_id="d-1")
    nudged = render_digest_payload(
        [_candidate(7)], payload_id="d-1", labeling_reminder=True
    )
    assert nudged.data["url"] == plain.data["url"]
    assert "/futures/7" in nudged.data["url"]
    assert nudged.data["labeling_url"] != nudged.data["url"]


def test_the_nudge_survives_an_empty_slate():
    """No standout markets is still a labelling day."""
    payload = render_digest_payload([], labeling_reminder=True)
    assert "Label today" in payload.body
    assert payload.data["labeling_url"] == LABELING_DEEP_LINK


def test_the_market_lines_are_untouched_by_the_nudge():
    plain = render_digest_payload([_candidate()])
    nudged = render_digest_payload([_candidate()], labeling_reminder=True)
    assert nudged.body.startswith(plain.body)
    assert nudged.items == plain.items


@pytest.mark.parametrize("reminder", [True, False])
def test_title_never_changes(reminder):
    """The brand hook is the same push either way — this is one digest."""
    payload = render_digest_payload([_candidate()], labeling_reminder=reminder)
    assert payload.title == "\U0001f340 Today's most interesting odds"
