import json
from collections import Counter
from pathlib import Path


AUDIT_PATH = (
    Path(__file__).parents[2]
    / "scripts"
    / "evals"
    / "review_verify_audit.json"
)


def test_review_verify_audit_complete():
    data = json.loads(AUDIT_PATH.read_text())
    assert len(data) == 72
    assert len({entry["number"] for entry in data}) == len(data)

    allowed = {
        "close-with-existing-evidence",
        "needs-live-verification",
        "regressed",
        "blocked-on-dependency",
        "misrouted",
    }
    for entry in data:
        assert entry["classification"] in allowed
        assert entry["title"]
        assert entry["evidence"]
        assert all(item.startswith("github: issue #") for item in entry["evidence"])
        assert entry["closure_comment_draft"]
        assert entry["confidence"] in {"high", "medium", "low"}
        # Reject the prior generated-table failure mode: unrelated cards all cited
        # the same calibration/feed file and generic combined proof packet.
        joined = " ".join(entry["evidence"] + [entry["closure_comment_draft"]])
        assert "sentinel GREEN + payload generated_at + chart + native" not in joined

    counts = Counter(entry["classification"] for entry in data)
    assert counts["close-with-existing-evidence"] > 0
    assert counts["needs-live-verification"] > 0
    assert counts["blocked-on-dependency"] > 0
    assert counts["regressed"] > 0
    assert counts["misrouted"] > 0


def test_membership_reconciles_changed_snapshot():
    numbers = {entry["number"] for entry in json.loads(AUDIT_PATH.read_text())}
    # Moved/closed since the supplied draft snapshot.
    assert numbers.isdisjoint({1159, 1229, 1446})
    # Newly entered Review/Verify since that snapshot.
    assert {1455, 1457} <= numbers
