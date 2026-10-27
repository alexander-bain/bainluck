"""Collector command contract; all Platform/CLI responses are local doubles."""

from contextlib import contextmanager
import io
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import dnpl_writer_verifier as collector
from app.services.dnpl_writer_observations import VERIFIER, validate_payloads


def test_exact_eight_read_only_requests_produce_revalidatable_raw_evidence(
    tmp_path, monkeypatch
):
    apps = {
        app: {"release": 4, "slug": str(uuid4()), "commit": "a" * 40}
        for app in collector.APPS
    }
    binding = {
        "run_id": str(uuid4()),
        "nonce": "b" * 32,
        "step": "arm",
        "expected_authority": {},
        "expected_primary": "exact",
        "apps": apps,
    }
    requests, commands = [], []

    @contextmanager
    def open_response(request, *, timeout):
        requests.append(request)
        assert request.get_method() == "GET"
        assert request.full_url.startswith("https://api.heroku.com/apps/")
        app = request.full_url.split("/")[4]
        if request.full_url.endswith("/formation"):
            data = [{"type": "worker-ws", "quantity": 0}]
        else:
            data = {"id": apps[app]["slug"], "commit": apps[app]["commit"]}
        yield io.BytesIO(json.dumps(data).encode())

    def run(argv, **kwargs):
        commands.append(argv)
        app = argv[argv.index("-a") + 1]
        assert argv[1] in ("releases", "ps")
        if argv[1] == "releases":
            data = [
                {
                    "current": True,
                    "status": "succeeded",
                    "version": 4,
                    "slug": {"id": apps[app]["slug"]},
                }
            ]
        else:
            data = [{"type": "web", "name": "web.1", "release": {"version": 4}}]
        kwargs["stdout"].write(json.dumps(data).encode())
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("HEROKU_API_KEY", "local-test-value")
    monkeypatch.setattr(
        collector.urllib.request,
        "build_opener",
        lambda *_: SimpleNamespace(open=open_response),
    )
    monkeypatch.setattr(collector.subprocess, "run", run)
    result = collector.collect(binding, tmp_path)
    assert len(requests) == len(commands) == 4
    assert len(result["reads"]) == 8
    validate_payloads(
        binding,
        {
            record["name"]: json.loads(
                (tmp_path / (record["name"] + ".json")).read_text()
            )
            for record in result["reads"]
        },
    )
    assert "local-test-value" not in json.dumps(result)


def test_real_child_without_explicit_credential_refuses_before_cli_or_network(tmp_path):
    binding = {
        "run_id": str(uuid4()),
        "nonce": "b" * 32,
        "step": "arm",
        "expected_authority": {},
        "expected_primary": "exact",
        "apps": {app: {} for app in collector.APPS},
    }
    env = {key: value for key, value in os.environ.items() if key != "HEROKU_API_KEY"}
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(VERIFIER),
            "--binding",
            json.dumps(binding),
            "--directory",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=2,
        env=env,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "REFUSED", "error_type": "KeyError"}
    assert list(tmp_path.iterdir()) == []


def test_redirect_is_not_followed():
    with pytest.raises(ValueError, match="redirect refused"):
        collector.NoRedirect().redirect_request(
            None, None, 302, "redirect", {}, "https://other.invalid"
        )
