"""Manus digest filer routing (#NNN / Queue #55, SEQUENCE 000d-filer).

The filer must stop spawning a fresh dated issue every sweep. Deduped findings now
route as COMMENTS to theme trackers (by module), with a single rolling log for
unmapped modules — never a per-sweep digest issue. Fingerprints are preserved so
dedup keeps working.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import manus_intake as mi


class FakeResult:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class GhRecorder:
    """Records gh CLI invocations; fakes search + create responses."""

    def __init__(self, search_returns="[]"):
        self.calls = []
        self.search_returns = search_returns

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if args[:3] == ["gh", "issue", "list"]:
            return FakeResult(stdout=self.search_returns)
        if args[:3] == ["gh", "issue", "create"]:
            return FakeResult(
                stdout="https://github.com/alexander-bain/bainluck/issues/9999\n",
                returncode=0,
            )
        return FakeResult(stdout="", returncode=0)

    def creates(self):
        return [c for c in self.calls if c[:3] == ["gh", "issue", "create"]]

    def comments(self):
        return [c for c in self.calls if c[:3] == ["gh", "issue", "comment"]]


def _f(module, fp=None):
    return {
        "module": module,
        "heading": f"{module} broke",
        "surface": f"https://bainluck.com/{module}",
        "severity": "P2",
        "fingerprint": fp or f"fp_{module}",
        "evidence": "something looked wrong",
    }


class TestModuleMapping:
    def test_known_modules_map(self):
        assert mi._tracker_for_module("feed") == 921
        assert mi._tracker_for_module("event_detail") == 921
        assert mi._tracker_for_module("chart_timing") == 922
        assert mi._tracker_for_module("grid") == 923
        assert mi._tracker_for_module("market_completeness") == 826
        assert mi._tracker_for_module("league_page") == 901
        assert mi._tracker_for_module("category_page") == 884

    def test_unmapped_modules_return_none(self):
        assert mi._tracker_for_module("event_matching") is None
        assert mi._tracker_for_module("visual_review") is None
        assert mi._tracker_for_module("") is None


class TestRouting:
    def test_all_mapped_never_creates_an_issue(self):
        gh = GhRecorder()
        findings = [_f("feed"), _f("grid"), _f("chart_timing")]
        plan = mi._file_findings(findings, "2026-06-15", "light", gh_run=gh)
        # No new issue created — the whole point of the fix
        assert gh.creates() == []
        # One comment per distinct tracker
        commented = {c[3] for c in gh.comments()}
        assert commented == {"921", "922", "923"}
        assert set(plan["trackers"]) == {921, 922, 923}
        assert plan["unmapped"] == 0

    def test_fingerprints_preserved_in_comment_bodies(self):
        gh = GhRecorder()
        findings = [_f("feed", fp="abc123")]
        mi._file_findings(findings, "2026-06-15", "light", gh_run=gh)
        bodies = "".join(c[-1] for c in gh.comments())
        assert "fingerprint:" in bodies
        assert "abc123" in bodies

    def test_unmapped_module_opens_one_issue_when_no_rolling_log(self):
        # Rolling log absent → it is created once (the single allowed create)
        gh = GhRecorder(search_returns="[]")
        plan = mi._file_findings([_f("event_matching")], "2026-06-15", "light", gh_run=gh)
        assert len(gh.creates()) == 1
        assert plan["unmapped"] == 1

    def test_unmapped_reuses_existing_rolling_log_no_create(self):
        # Rolling log already exists → comment on it, no create
        gh = GhRecorder(search_returns='[{"number": 850}]')
        mi._file_findings([_f("visual_review")], "2026-06-15", "light", gh_run=gh)
        assert gh.creates() == []
        assert any(c[3] == "850" for c in gh.comments())

    def test_mixed_mapped_and_unmapped(self):
        gh = GhRecorder(search_returns='[{"number": 850}]')
        findings = [_f("feed"), _f("event_matching")]
        plan = mi._file_findings(findings, "2026-06-15", "light", gh_run=gh)
        assert plan["trackers"] == {921: 1}
        assert plan["unmapped"] == 1
        assert gh.creates() == []  # rolling log existed
        commented = {c[3] for c in gh.comments()}
        assert "921" in commented and "850" in commented

    def test_dry_run_makes_no_gh_calls(self):
        gh = GhRecorder()
        plan = mi._file_findings([_f("feed")], "2026-06-15", "light", dry_run=True, gh_run=gh)
        assert gh.calls == []
        assert plan["trackers"] == {921: 1}
