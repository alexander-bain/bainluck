"""Release-loop behavior guards; no signing assets, Apple or GitHub required."""

import importlib.util
import json
import plistlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULES = {}


def module(name):
    if name in MODULES:
        return MODULES[name]
    path = ROOT / "tools" / "testflight" / (name + ".py")
    assert path.exists(), f"missing TestFlight release implementation: {path}"
    spec = importlib.util.spec_from_file_location("testflight_" + name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    MODULES[name] = obj
    return obj


def test_start_is_tuesday_midnight_pacific_and_only_ios_changes():
    release = module("release")
    before = datetime(2026, 11, 3, 7, 59, 59, tzinfo=timezone.utc)
    after = datetime(2026, 11, 3, 8, 0, 0, tzinfo=timezone.utc)
    assert not release.eligible(["ios/a.swift"], before)
    assert release.eligible(["ios/a.swift"], after)
    assert not release.eligible(["frontend/a.ts"], after)


def test_next_build_uses_apple_master_and_day_zero_floors():
    release = module("release")
    assert release.next_build([99], 10) == 100
    assert release.next_build([99, 101], 10) == 102
    assert release.next_build([99], 111) == 112
    assert release.next_build([], 10) == 100
    with pytest.raises(ValueError):
        release.next_build(["invalid"], 10)


def test_master_floor_cannot_disappear_due_to_malformed_project():
    release = module("release")
    assert (
        release.master_floor(
            "CURRENT_PROJECT_VERSION = 10;\nCURRENT_PROJECT_VERSION = 120;"
        )
        == 120
    )
    with pytest.raises(ValueError):
        release.master_floor("CURRENT_PROJECT_VERSION = $(UNKNOWN);")


def test_apple_build_collection_reads_every_page_and_matching_train():
    release = module("release")
    pages = {
        "/builds?filter[app]=123&limit=200&include=preReleaseVersion": {
            "data": [build("1", "99", "p1")],
            "included": [train("p1", "1.0.5")],
            "links": {"next": "https://api.appstoreconnect.apple.com/v1/next"},
        },
        "https://api.appstoreconnect.apple.com/v1/next": {
            "data": [build("2", "101", "p1"), build("3", "999", "p2")],
            "included": [train("p1", "1.0.5"), train("p2", "1.0.4")],
        },
    }
    rows = release.apple_builds(pages.__getitem__, "123", "1.0.5")
    assert [r["attributes"]["version"] for r in rows] == ["99", "101"]


def test_apple_collection_refuses_unknown_train_and_foreign_pagination():
    release = module("release")
    with pytest.raises(ValueError):
        release.apple_builds(
            lambda _: {"data": [build("1", "99", "missing")]}, "123", "1.0.5"
        )
    with pytest.raises(ValueError):
        release.apple_builds(
            lambda _: {"data": [], "links": {"next": "https://example.com/steal"}},
            "123",
            "1.0.5",
        )


def build(identifier, version, release_train):
    return {
        "id": identifier,
        "attributes": {"version": version, "processingState": "VALID"},
        "relationships": {"preReleaseVersion": {"data": {"id": release_train}}},
    }


def train(identifier, version):
    return {
        "id": identifier,
        "type": "preReleaseVersions",
        "attributes": {"version": version},
    }


def test_verification_checks_nested_bundle_versions_and_build_numbers():
    release = module("release")
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        app = root / "Bain Luck.app"
        plugin = app / "PlugIns" / "Widget.appex"
        plugin.mkdir(parents=True)
        for bundle in [app, plugin]:
            (bundle / "Info.plist").write_bytes(
                plistlib.dumps(
                    {"CFBundleVersion": "100", "CFBundleShortVersionString": "1.0.5"}
                )
            )
        assert release.verify_bundles(root, "1.0.5", 100) == app
        (plugin / "Info.plist").write_bytes(
            plistlib.dumps(
                {"CFBundleVersion": "99", "CFBundleShortVersionString": "1.0.5"}
            )
        )
        with pytest.raises(ValueError):
            release.verify_bundles(root, "1.0.5", 100)


def test_delivery_requires_success_and_no_product_errors():
    release = module("release")
    release.verify_delivery(
        {"success-message": "No errors uploading", "product-errors": []}
    )
    for document in [{}, {"product-errors": [{"code": 1}], "success-message": "done"}]:
        with pytest.raises(ValueError):
            release.verify_delivery(document)


class FakeGitHub:
    """A git graph with actual fast-forward rejection, used to exercise CAS."""

    def __init__(self):
        self.ref = None
        self.commits = {
            "source": {
                "sha": "source",
                "tree": {"sha": "tree"},
                "parents": [],
                "message": "",
            }
        }
        self.runs = {}
        self.counter = 0

    def get(self, path):
        if path == "/git/ref/heads/testflight-release-lock":
            if self.ref is None:
                raise module("lease").ApiError(404)
            return {"object": {"sha": self.ref}}
        if path.startswith("/git/commits/"):
            return self.commits[path.split("/")[-1]]
        if path.startswith("/actions/runs/"):
            return self.runs.get(path, {"status": "in_progress"})
        raise AssertionError(path)

    def post(self, path, body):
        lease = module("lease")
        if path == "/git/commits":
            self.counter += 1
            sha = "commit" + str(self.counter)
            self.commits[sha] = dict(body, sha=sha, tree={"sha": body["tree"]})
            return {"sha": sha}
        if path == "/git/refs":
            if self.ref is not None:
                raise lease.ApiError(422)
            self.ref = body["sha"]
            return {"object": {"sha": self.ref}}
        raise AssertionError(path)

    def patch(self, path, body):
        lease = module("lease")
        assert body["force"] is False
        if self.ref not in self.commits[body["sha"]]["parents"]:
            raise lease.ApiError(422)
        self.ref = body["sha"]
        return {"object": {"sha": self.ref}}


def test_lease_serializes_every_waiter_without_dropping_pending_merges():
    lease = module("lease")
    api = FakeGitHub()
    first = lease.try_acquire(api, "source", 1, 1)
    assert first
    assert lease.try_acquire(api, "source", 2, 1) is None
    lease.release(api, first, 1, 1)
    second = lease.try_acquire(api, "source", 2, 1)
    assert second and second != first
    assert lease.try_acquire(api, "source", 3, 1) is None
    lease.release(api, second, 2, 1)
    assert lease.try_acquire(api, "source", 3, 1)


def test_lease_recovers_completed_attempt_but_not_active_owner():
    lease = module("lease")
    api = FakeGitHub()
    owner = lease.try_acquire(api, "source", 1, 1)
    assert lease.try_acquire(api, "source", 2, 1) is None
    api.runs["/actions/runs/1/attempts/1"] = {"status": "completed"}
    assert lease.try_acquire(api, "source", 2, 1)
    with pytest.raises(ValueError):
        lease.release(api, owner, 1, 1)


def test_stale_owner_cannot_unlock_another_release():
    lease = module("lease")
    api = FakeGitHub()
    token = lease.try_acquire(api, "source", 1, 1)
    with pytest.raises(ValueError):
        lease.release(api, token, 2, 1)
    assert lease.try_acquire(api, "source", 2, 1) is None


def test_marketing_version_respects_source_and_the_one_zero_five_floor():
    release = module("release")
    assert release.release_version("MARKETING_VERSION = 1.0;") == "1.0.5"
    assert release.release_version("MARKETING_VERSION = 1.0.6;") == "1.0.6"
    with pytest.raises(ValueError):
        release.release_version("MARKETING_VERSION = $(UNKNOWN);")


def test_profile_zip_rejects_traversal_before_writing_files():
    import base64
    import io
    import zipfile

    signing = module("prepare_signing")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../outside.mobileprovision", b"profile")
    with pytest.raises(ValueError):
        signing.profile_files(base64.b64encode(stream.getvalue()).decode())


def test_signing_requires_store_profiles_for_the_bain_luck_team():
    signing = module("prepare_signing")
    info = {
        "TeamIdentifier": ["J893F72P4R"],
        "ExpirationDate": datetime(2099, 1, 1),
        "Entitlements": {"application-identifier": "J893F72P4R.com.bainluck.Bain-Luck"},
    }
    assert signing.profile_bundle(info) == "com.bainluck.Bain-Luck"
    with pytest.raises(ValueError):
        signing.profile_bundle(dict(info, ProvisionedDevices=["test-device"]))
    with pytest.raises(ValueError):
        signing.profile_bundle(dict(info, TeamIdentifier=["other-team"]))


def test_project_parser_refuses_a_partially_dynamic_build_floor():
    release = module("release")
    with pytest.raises(ValueError):
        release.master_floor(
            "CURRENT_PROJECT_VERSION = 10;\nCURRENT_PROJECT_VERSION = $(UNKNOWN);"
        )


def test_workflow_only_release_master_and_never_discards_pending_builds():
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/testflight.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["on"]["push"]["branches"] == ["master"]
    assert "paths" not in workflow["on"]["push"]
    assert "pull_request_target" not in workflow["on"]
    assert workflow["jobs"]["scope"]["if"] == "github.ref == 'refs/heads/master'"
    assert "concurrency" not in workflow
    assert all("concurrency" not in job for job in workflow["jobs"].values())
    assert (
        workflow["jobs"]["return-lease"]["if"]
        == "always() && (needs.release.outputs.token != '' || needs.queue.outputs.token != '')"
    )
    for name in ("scope", "queue", "release", "return-lease"):
        checkout = next(
            step
            for step in workflow["jobs"][name]["steps"]
            if step.get("uses", "").startswith("actions/checkout")
        )
        assert checkout["with"]["ref"] == "master"
        assert checkout["with"]["persist-credentials"] == "false"


def test_competing_ref_advance_keeps_the_winning_owner():
    lease = module("lease")
    api = FakeGitHub()
    initial = lease.try_acquire(api, "source", 1, 1)
    lease.release(api, initial, 1, 1)
    real_patch = api.patch
    injected = []

    def competing_patch(path, body):
        if not injected:
            injected.append(True)
            competitor = lease.state_commit(
                api, "tree", api.ref, {"run_id": 2, "attempt": 1, "source": "source"}
            )
            real_patch(path, {"sha": competitor, "force": False})
        return real_patch(path, body)

    api.patch = competing_patch
    assert lease.try_acquire(api, "source", 3, 1) is None
    assert lease.read_state(api)[2]["run_id"] == 2


def test_internal_lease_branch_does_not_queue_more_secret_scan_runners():
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/gitleaks.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["on"]["push"]["branches-ignore"] == ["testflight-release-lock"]
    assert "branches" not in workflow["on"]["push"]
    assert "pull_request" in workflow["on"]
    assert workflow["on"]["pull_request"] in ("", None)
    assert workflow["on"]["schedule"]


def test_failed_job_retry_reacquires_ownership_for_its_actual_attempt():
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/testflight.yml").read_text(), Loader=yaml.BaseLoader
    )
    steps = workflow["jobs"]["release"]["steps"]
    lease_steps = [step for step in steps if step.get("id") == "lease"]
    assert (
        len(lease_steps) == 1
    ), "release retry must acquire a fresh current-attempt lease"
    assert "lease.py acquire" in lease_steps[0]["run"]
    assert steps.index(lease_steps[0]) < next(
        i for i, step in enumerate(steps) if step.get("id") == "number"
    )
    assert (
        workflow["jobs"]["release"]["outputs"]["token"]
        == "${{ steps.lease.outputs.token }}"
    )
    cleanup = workflow["jobs"]["return-lease"]["steps"][-1]
    assert "needs.release.outputs.token" in cleanup["env"]["LEASE_TOKEN"]


def test_retried_release_waits_for_another_merge_and_cannot_use_its_old_token():
    lease = module("lease")
    api = FakeGitHub()
    first = lease.try_acquire(api, "source", 1, 1)
    lease.release(api, first, 1, 1)
    other = lease.try_acquire(api, "source", 2, 1)
    assert lease.try_acquire(api, "source", 1, 2) is None
    lease.release(api, other, 2, 1)
    retry = lease.try_acquire(api, "source", 1, 2)
    assert retry and retry != first
    with pytest.raises(ValueError):
        lease.release(api, first, 1, 2)
    assert lease.read_state(api)[2]["attempt"] == 2
    lease.release(api, retry, 1, 2)


def test_batch_push_preserves_each_ios_commit_including_a_net_revert():
    import subprocess

    release = module("release")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        def git(*args):
            return (
                subprocess.check_output(
                    ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL
                )
                .decode()
                .strip()
            )

        git("init")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "release-test")
        path = root / "ios" / "app.swift"
        path.parent.mkdir()
        path.write_text("original\n")
        git("add", ".")
        git("commit", "-m", "baseline")
        before = git("rev-parse", "HEAD")
        path.write_text("changed\n")
        git("add", ".")
        git("commit", "-m", "ios merge one")
        first = git("rev-parse", "HEAD")
        (root / "readme.md").write_text("docs only\n")
        git("add", ".")
        git("commit", "-m", "docs merge")
        path.write_text("original\n")
        git("add", ".")
        git("commit", "-m", "ios merge two reverts one")
        reverted = git("rev-parse", "HEAD")
        assert git("diff", "--name-only", before, reverted, "--", "ios/") == ""
        assert release.new_ios_commits(root, before, reverted) == [first, reverted]


def test_batch_push_dispatches_one_isolated_release_per_selected_source():
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/testflight.yml").read_text(), Loader=yaml.BaseLoader
    )
    jobs = workflow["jobs"]
    assert (
        "dispatch" in jobs
    ), "batch must dispatch every selected commit, not only HEAD"
    assert "github.event_name == 'push'" in jobs["dispatch"]["if"]
    assert "github.event_name == 'workflow_dispatch'" in jobs["queue"]["if"]
    assert "sources" in jobs["scope"]["outputs"]
    assert "source" in jobs["scope"]["outputs"]
    assert "source_sha" in workflow["on"]["workflow_dispatch"]["inputs"]
    release_checkouts = [
        step
        for step in jobs["release"]["steps"]
        if step.get("uses", "").startswith("actions/checkout")
    ]
    assert len(release_checkouts) == 2
    assert release_checkouts[0]["with"]["ref"] == "master"
    assert release_checkouts[1]["with"]["ref"] == "${{ needs.scope.outputs.source }}"


def test_current_attempt_validation_and_stale_cleanup_preserve_another_owner():
    lease = module("lease")
    api = FakeGitHub()
    old = lease.try_acquire(api, "source", 1, 1)
    lease.release(api, old, 1, 1)
    other = lease.try_acquire(api, "source", 2, 1)
    assert not lease.release_if_owned(api, old, 1, 2)
    assert lease.read_state(api)[0] == other
    with pytest.raises(ValueError):
        lease.validate(api, old, "source", 1, 2)
    lease.release(api, other, 2, 1)
    token = lease.try_acquire(api, "source", 1, 2)
    lease.validate(api, token, "source", 1, 2)
    with pytest.raises(ValueError):
        lease.validate(api, token, "different-source", 1, 2)
    assert lease.release_if_owned(api, token, 1, 2)


def test_dispatch_preserves_all_source_shas_as_separate_master_runs():
    release = module("release")
    sources = ["a" * 40, "b" * 40]
    sent = []
    release.dispatch_sources(sources, sent.append)
    assert sent == [
        {"ref": "master", "inputs": {"source_sha": source}} for source in sources
    ]


def test_master_commit_selection_excludes_the_feature_commits_inside_a_merge():
    import subprocess

    release = module("release")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        def git(*args):
            return (
                subprocess.check_output(
                    ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL
                )
                .decode()
                .strip()
            )

        git("init", "-b", "master")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "release-test")
        (root / "ios").mkdir()
        path = root / "ios" / "app.swift"
        path.write_text("baseline\n")
        git("add", ".")
        git("commit", "-m", "baseline")
        before = git("rev-parse", "HEAD")
        git("checkout", "-b", "feature")
        path.write_text("new feature\n")
        git("add", ".")
        git("commit", "-m", "feature change")
        feature = git("rev-parse", "HEAD")
        git("checkout", "master")
        git("merge", "--no-ff", "feature", "-m", "merge iOS feature")
        merged = git("rev-parse", "HEAD")
        assert release.new_ios_commits(root, before, merged) == [merged]
        assert release.requested_source(root, merged, "master") == [merged]
        with pytest.raises(ValueError):
            release.requested_source(root, feature, "master")
