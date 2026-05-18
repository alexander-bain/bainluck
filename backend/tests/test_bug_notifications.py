from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.bug_notifications import (
    BUG_FIXED_EMAIL_SUBJECT,
    _build_gmail_message,
    build_bug_fixed_email_prompt_body,
    build_bug_fixed_email_prompt_input,
    format_bug_fixed_email_html,
    send_bug_fixed_email,
)


class _Result:
    def __init__(self, report):
        self.report = report

    def scalar_one_or_none(self):
        return self.report


class _Session:
    def __init__(self, report):
        self.report = report

    async def execute(self, _statement):
        return _Result(self.report)


def _report(**overrides):
    defaults = {
        "id": 123,
        "user_email": "jane.doe@example.com",
        "notification_sent_at": None,
        "status": "fixed",
        "description": "The Discover card was blank.",
        "resolution_summary": "We fixed the image fallback.",
        "app_state": {"user_name": "Jane Doe"},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_build_prompt_input_prefers_app_state_name():
    prompt_input = build_bug_fixed_email_prompt_input(_report())

    assert prompt_input.first_name == "Jane"
    assert prompt_input.description == "The Discover card was blank."
    assert prompt_input.resolution_summary == "We fixed the image fallback."


def test_build_prompt_body_contains_report_context():
    prompt_input = build_bug_fixed_email_prompt_input(_report())
    prompt_body = build_bug_fixed_email_prompt_body(prompt_input)

    assert "Write a short email to Jane" in prompt_body
    assert 'Bug they reported: "The Discover card was blank."' in prompt_body
    assert 'What we fixed: "We fixed the image fallback."' in prompt_body


def test_build_gmail_message_includes_plain_text_and_html_parts():
    body_html = format_bug_fixed_email_html(
        "Jane",
        "Thanks for the report.\nWe fixed <the> image fallback.",
    )

    message = _build_gmail_message(
        "jane.doe@example.com",
        BUG_FIXED_EMAIL_SUBJECT,
        body_html,
    )

    assert message["To"] == "jane.doe@example.com"
    assert message["From"] == "Bain Luck <bugs@bainluck.com>"
    assert message["Subject"] == BUG_FIXED_EMAIL_SUBJECT
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["Precedence"] == "bulk"
    assert message["X-Auto-Response-Suppress"] == "All"
    assert "List-Unsubscribe" not in message
    assert "List-Unsubscribe-Post" not in message
    assert message.is_multipart()

    plain_body = message.get_body(preferencelist=("plain",)).get_content()
    html_body = message.get_body(preferencelist=("html",)).get_content()
    assert "Hi Jane," in plain_body
    assert "We fixed <the> image fallback." in plain_body
    assert "<div" not in plain_body
    assert "We fixed &lt;the&gt; image fallback." in html_body


def test_build_gmail_message_rejects_invalid_headers():
    body_html = format_bug_fixed_email_html("Jane", "Fixed.")

    with pytest.raises(ValueError):
        _build_gmail_message(
            "jane.doe@example.com",
            "Your bug report was fixed\nBcc: attacker@example.com",
            body_html,
        )

    with pytest.raises(ValueError):
        _build_gmail_message(
            "jane.doe@example.com\nBcc: attacker@example.com",
            BUG_FIXED_EMAIL_SUBJECT,
            body_html,
        )


@pytest.mark.asyncio
async def test_send_bug_fixed_email_skips_missing_email():
    calls = []

    async def send_email(**kwargs):
        calls.append(kwargs)
        return True

    sent = await send_bug_fixed_email(
        123,
        _Session(_report(user_email=None)),
        send_email=send_email,
    )

    assert sent is False
    assert calls == []


@pytest.mark.asyncio
async def test_send_bug_fixed_email_skips_invalid_email():
    calls = []

    async def send_email(**kwargs):
        calls.append(kwargs)
        return True

    sent = await send_bug_fixed_email(
        123,
        _Session(_report(user_email="not-an-email")),
        send_email=send_email,
    )

    assert sent is False
    assert calls == []


@pytest.mark.asyncio
async def test_send_bug_fixed_email_skips_already_notified():
    calls = []

    async def send_email(**kwargs):
        calls.append(kwargs)
        return True

    sent = await send_bug_fixed_email(
        123,
        _Session(_report(notification_sent_at=datetime.now(timezone.utc))),
        send_email=send_email,
    )

    assert sent is False
    assert calls == []


@pytest.mark.asyncio
async def test_send_bug_fixed_email_skips_unresolved_report():
    calls = []

    async def send_email(**kwargs):
        calls.append(kwargs)
        return True

    sent = await send_bug_fixed_email(
        123,
        _Session(_report(status="reviewed")),
        send_email=send_email,
    )

    assert sent is False
    assert calls == []


@pytest.mark.asyncio
async def test_send_bug_fixed_email_skips_missing_resolution_summary():
    calls = []

    async def send_email(**kwargs):
        calls.append(kwargs)
        return True

    sent = await send_bug_fixed_email(
        123,
        _Session(_report(resolution_summary=" ")),
        send_email=send_email,
    )

    assert sent is False
    assert calls == []


@pytest.mark.asyncio
async def test_send_bug_fixed_email_uses_injected_seams_and_marks_sent():
    generated_inputs = []
    sent_messages = []
    marked = []
    sent_at = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)

    async def generate_body(prompt_input):
        generated_inputs.append(prompt_input)
        return "Thanks for the report. We fixed the image fallback."

    async def send_email(**kwargs):
        sent_messages.append(kwargs)
        return True

    async def mark_notification_sent(db, report_id, timestamp):
        marked.append((db, report_id, timestamp))

    session = _Session(_report())
    sent = await send_bug_fixed_email(
        123,
        session,
        generate_body=generate_body,
        send_email=send_email,
        mark_notification_sent=mark_notification_sent,
        now_fn=lambda: sent_at,
    )

    assert sent is True
    assert generated_inputs[0].first_name == "Jane"
    assert sent_messages == [
        {
            "to_email": "jane.doe@example.com",
            "subject": BUG_FIXED_EMAIL_SUBJECT,
            "body_html": sent_messages[0]["body_html"],
        }
    ]
    assert "Hi Jane" in sent_messages[0]["body_html"]
    assert "We fixed the image fallback" in sent_messages[0]["body_html"]
    assert marked == [(session, 123, sent_at)]


@pytest.mark.asyncio
async def test_send_bug_fixed_email_does_not_mark_when_send_fails():
    marked = []

    async def send_email(**kwargs):
        return False

    async def mark_notification_sent(db, report_id, timestamp):
        marked.append((db, report_id, timestamp))

    sent = await send_bug_fixed_email(
        123,
        _Session(_report()),
        send_email=send_email,
        mark_notification_sent=mark_notification_sent,
    )

    assert sent is False
    assert marked == []


def test_celery_task_is_registered():
    from app.tasks import celery_app

    assert "app.tasks.send_bug_fixed_email" in celery_app.tasks
