"""Replay the retained scorer fixtures and the two separately observed public detail rows."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import patch

if sys.argv[1] == "original":
    # Execute the exact base producer and fixture against the same surrounding
    # checkout so unrelated changes on adjacent branches cannot affect the diff.
    backend = Path.cwd()
    for module_name, relative_path in (
        ("app.utils.deadline_family_story", "app/utils/deadline_family_story.py"),
        ("tests.test_deadline_family_story_9878", "tests/test_deadline_family_story_9878.py"),
    ):
        source = subprocess.check_output(
            ["git", "-C", str(backend.parent), "show",
             f"f82a475ae2dff17c17758718e5fab406e9f930cf:backend/{relative_path}"],
            text=True,
        )
        module = types.ModuleType(module_name)
        module.__file__ = str(backend / relative_path)
        sys.modules[module_name] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)

from app.utils import discover_bundles
from app.utils.deadline_family_story import build_deadline_member_contract, verify_and_select_deadline_family
from tests.test_deadline_family_story_9878 import (
    test_case17_v3_gap3_real_feed_serialization_dedup_and_display_chain_integration,
)

receipts = Path(__file__).resolve().parent
assemble = discover_bundles._make_deadline_family_bundle_item
historical = []


def record(*args, **kwargs):
    bundle = assemble(*args, **kwargs)
    historical.append(deepcopy(bundle))
    return bundle


with patch.object(discover_bundles, "_make_deadline_family_bundle_item", record):
    test_case17_v3_gap3_real_feed_serialization_dedup_and_display_chain_integration()

def json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


public_members = []
observed_day = datetime(2026, 11, 17, 21, tzinfo=timezone.utc)
for path in sorted(receipts.glob("detail-*.json")):
    detail = json.loads(path.read_text())
    public_members.append(build_deadline_member_contract(
        market_id=detail["id"], name=detail["name"], source=detail["source"],
        external_id=detail["external_id"], group_id=detail["group_id"],
        status=detail["status"], resolution_date=detail["resolution_date"],
        description=detail["description"], outcomes=detail["outcomes"], now=observed_day,
    ))
assert len(public_members) == 2 and all(public_members)
public_family, refusal = verify_and_select_deadline_family(public_members, now=observed_day)
assert public_family is None and refusal == "missing_rule_equivalence_proof"
assert len(historical) >= 2
output = {"historical_scorer_bundles": historical, "public_detail_members": public_members,
          "public_detail_group_refusal": refusal}
path = receipts / ("family-" + sys.argv[1] + ".json")
path.write_text(json.dumps(output, default=json_value, ensure_ascii=False, indent=2) + "\n")
