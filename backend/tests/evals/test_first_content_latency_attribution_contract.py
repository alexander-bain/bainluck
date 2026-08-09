import copy
import json
from pathlib import Path

from scripts.evals.first_content_latency_attribution_contract import evaluate_packet


FIXTURE = Path(__file__).parent / "fixtures" / "first_content_latency_attribution_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def materialize(case):
    packet = copy.deepcopy(pack()["base"])
    packet.update(case.get("set", {}))
    for key in case.get("delete", []):
        packet.pop(key, None)
    return packet


def test_every_case_matches_the_oracle():
    for case in pack()["cases"]:
        result = evaluate_packet(materialize(case))
        assert result["verdict"] == case["expected_verdict"], case["id"]
        assert result["reasons"] == case["expected_reasons"], case["id"]


def test_clean_packet_recomposes_the_user_wait():
    result = evaluate_packet(pack()["base"])
    assert result["attribution"] == {"total_ms": 2400, "backend_ms": 1600, "network_and_queue_ms": 400, "client_to_content_ms": 400}


def test_backend_fast_client_slow_is_not_misattributed():
    case = next(row for row in pack()["cases"] if row["id"] == "backend-fast-client-slow")
    result = evaluate_packet(materialize(case))
    assert result["attribution"]["backend_ms"] == 20
    assert result["attribution"]["client_to_content_ms"] == 3900


def test_failure_classes_cover_the_whole_chain():
    reasons = {reason for case in pack()["cases"] for reason in case["expected_reasons"]}
    assert {"FIELDS_MISSING", "TRACE_ID_INVALID", "FIRST_CONTENT_NOT_PROVEN", "SERVER_STAGES_INVALID", "SERVER_STAGES_EXCEED_BACKEND", "RETRY_ACCOUNTING_MISSING", "TIMEOUT_BOUND_MISSING", "PRIVACY_FIELD_PRESENT"} <= reasons
