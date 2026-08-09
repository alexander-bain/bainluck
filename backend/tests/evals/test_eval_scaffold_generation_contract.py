import json
from pathlib import Path

import pytest

from scripts.evals.eval_scaffold_generation_contract import render, validate


FIXTURE = Path(__file__).parent / "fixtures" / "eval_scaffold_generation_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def test_every_fixture_matches_the_oracle():
    for case in pack()["cases"]:
        assert validate(case["input"]) == case["expected"], case["id"]


def test_renderer_emits_only_canonical_imports():
    for spec in pack()["render_specs"]:
        source = render(spec)
        assert f"from scripts.evals.{spec['module']} import" in source
        assert "backend.scripts" not in source
        assert validate({"source":source,"path":f"backend/tests/evals/test_{spec['module']}.py","module":spec["module"],"fixture":spec.get("fixture"),"verified_contexts":["repo_root_pytest","backend_pytest","direct_script"],"direct_execution":True}) == {"verdict":"ALLOW","reasons":[]}


def test_renderer_refuses_poison_names():
    for spec in ({"module":"../oops","symbols":["run"]},{"module":"good","symbols":["bad-name"]},{"module":"backend.good","symbols":["run"]}):
        with pytest.raises(ValueError):
            render(spec)


def test_mutating_prefix_turns_clean_output_red():
    spec = pack()["render_specs"][0]
    source = render(spec).replace("from scripts.evals.", "from backend.scripts.evals.")
    result = validate({"source":source,"path":f"backend/tests/evals/test_{spec['module']}.py","module":spec["module"],"verified_contexts":["repo_root_pytest","backend_pytest"]})
    assert "BACKEND_PREFIX_GENERATED" in result["reasons"]
