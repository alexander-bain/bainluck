"""Queue 311 Item A1 (#1159) — only FCM-kind tokens reach the digest broadcast.

The digest has reached zero recipients since 7/17 because every registered row
holds a raw APNS hex, which FCM's ``messaging.send()`` rejects. ``token_kind``
is the discriminator that makes the sendable rows addressable.

The stakes are higher than a missed notification: the send loop deactivates a
row whose token FCM rejects, so an unfiltered broadcast would switch off real
devices one by one. These tests assert BOTH directions — the APNS row is
excluded AND the FCM row survives — because a filter tested in one direction
only is indistinguishable from a filter that drops everything.
"""

from types import SimpleNamespace

from app.tasks.morning_digest import (
    digest_recipients,
    is_sendable_via_fcm,
    token_kind_of,
)


class _Row(SimpleNamespace):
    """A DeviceToken stand-in whose attributes live in ``__dict__``.

    That matters: the production reader deliberately goes through ``__dict__``
    to avoid an ORM lazy load, so a stand-in exposing the column any other way
    would be testing a different code path than the one that ships.
    """


def _device(id=1, token="tok", kind="fcm"):
    row = _Row(id=id, device_token=token)
    if kind is not None:
        row.token_kind = kind
    return row


def _user(opted_in=True):
    return SimpleNamespace(push_preferences={"morning_digest": opted_in})


# ---------------------------------------------------------------------------
# token_kind_of — absence resolves to the UNSENDABLE reading
# ---------------------------------------------------------------------------


def test_legacy_row_with_no_kind_reads_as_apns():
    """Every pre-Queue-311 row is a raw APNS hex; absence has one right answer."""
    assert token_kind_of(_device(kind=None)) == "apns"


def test_empty_kind_reads_as_apns():
    assert token_kind_of(_device(kind="")) == "apns"


def test_explicit_kinds_round_trip():
    assert token_kind_of(_device(kind="apns")) == "apns"
    assert token_kind_of(_device(kind="fcm")) == "fcm"


def test_only_fcm_is_sendable():
    assert is_sendable_via_fcm(_device(kind="fcm")) is True
    assert is_sendable_via_fcm(_device(kind="apns")) is False
    assert is_sendable_via_fcm(_device(kind=None)) is False


# ---------------------------------------------------------------------------
# digest_recipients — both directions
# ---------------------------------------------------------------------------


def test_apns_row_is_excluded_from_the_broadcast():
    rows = [(_device(id=1, token="apns-hex", kind="apns"), _user(opted_in=True))]
    assert digest_recipients(rows) == []


def test_fcm_row_is_included():
    rows = [(_device(id=2, token="fcm-registration", kind="fcm"), _user(opted_in=True))]
    assert digest_recipients(rows) == [(2, "fcm-registration")]


def test_legacy_row_is_excluded_even_when_opted_in():
    rows = [(_device(id=3, token="legacy", kind=None), _user(opted_in=True))]
    assert digest_recipients(rows) == []


def test_mixed_set_keeps_only_the_sendable_row():
    """The realistic post-A2 state: one device, two rows, one of them sendable."""
    user = _user(opted_in=True)
    rows = [
        (_device(id=1, token="apns-hex", kind="apns"), user),
        (_device(id=2, token="fcm-registration", kind="fcm"), user),
    ]
    assert digest_recipients(rows) == [(2, "fcm-registration")]


def test_opt_in_gate_still_applies_to_fcm_rows():
    """Sendability does not override consent — both gates are required."""
    rows = [(_device(id=4, token="fcm-registration", kind="fcm"), _user(opted_in=False))]
    assert digest_recipients(rows) == []


def test_missing_user_is_not_an_opt_in():
    rows = [(_device(id=5, token="fcm-registration", kind="fcm"), None)]
    assert digest_recipients(rows) == []
