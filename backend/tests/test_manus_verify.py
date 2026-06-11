"""Unit tests for the Manus verify poller.

These guard the bug that motivated the rewrite: the poller used to read a
non-existent top-level ``status``/``result`` field from ``task.detail`` and so
never detected completion. The real Manus v2 shape is
``{"task": {"status": "stopped", "credit_usage": N}}`` with the verdict text in
``assistant_message`` content from ``task.listMessages``.
"""

from scripts import manus_verify


def test_extract_verdict_pulls_assistant_content_and_attachments():
    messages = {
        "messages": [
            {"type": "status_update", "status_update": {"agent_status": "running"}},
            {
                "type": "assistant_message",
                "assistant_message": {
                    "content": "PASS — the /playoffs/nba grid renders with real content.",
                    "attachments": [
                        {"file_name": "screenshot.png", "url": "https://x/y.png"}
                    ],
                },
            },
        ]
    }
    verdict = manus_verify.extract_verdict(messages)
    assert "PASS" in verdict
    assert "/playoffs/nba" in verdict
    assert "screenshot.png" in verdict


def test_poll_task_detects_stopped_and_returns_verdict(monkeypatch):
    # First poll: still running. Second poll: stopped.
    statuses = iter(
        [
            {"status": "running", "credit_usage": 5},
            {"status": "stopped", "credit_usage": 42},
        ]
    )
    monkeypatch.setattr(manus_verify, "get_task_status", lambda tid: next(statuses))
    monkeypatch.setattr(
        manus_verify,
        "collect_messages",
        lambda tid: {
            "messages": [
                {
                    "type": "assistant_message",
                    "assistant_message": {"content": "PASS — looks good", "attachments": []},
                }
            ]
        },
    )

    result = manus_verify.poll_task("TID", timeout_seconds=60, interval=1, sleep=lambda *_: None)

    assert result["status"] == "complete"
    assert result["task_id"] == "TID"
    assert result["credits"] == 42
    assert "PASS" in result["verdict"]


def test_poll_task_reports_error_status(monkeypatch):
    monkeypatch.setattr(
        manus_verify, "get_task_status", lambda tid: {"status": "error", "credit_usage": 3}
    )
    # collect_messages must NOT be called on the error path.
    monkeypatch.setattr(
        manus_verify,
        "collect_messages",
        lambda tid: (_ for _ in ()).throw(AssertionError("should not collect on error")),
    )

    result = manus_verify.poll_task("TID", timeout_seconds=60, interval=1, sleep=lambda *_: None)

    assert result["status"] == "error"
    assert result["credits"] == 3


def test_poll_task_times_out_when_never_stops(monkeypatch):
    monkeypatch.setattr(
        manus_verify, "get_task_status", lambda tid: {"status": "running", "credit_usage": 1}
    )
    result = manus_verify.poll_task("TID", timeout_seconds=3, interval=1, sleep=lambda *_: None)
    assert result["status"] == "timeout"
    assert result["task_id"] == "TID"


def test_poll_task_handles_none_status_then_stops(monkeypatch):
    # A transient None (transport hiccup) must not crash the loop.
    statuses = iter([None, {"status": "stopped", "credit_usage": 7}])
    monkeypatch.setattr(manus_verify, "get_task_status", lambda tid: next(statuses))
    monkeypatch.setattr(
        manus_verify,
        "collect_messages",
        lambda tid: {"messages": []},
    )
    result = manus_verify.poll_task("TID", timeout_seconds=60, interval=1, sleep=lambda *_: None)
    assert result["status"] == "complete"
    assert result["verdict"] == ""
