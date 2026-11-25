from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect

AT = "2026-11-23T08:32:21Z"
BEFORE = "2026-11-22T23:30:00Z"
NOW = "2026-11-23T09:35:00Z"
REPO = f"repos/{collect.REPO}"
BRANCH_ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REF": "refs/heads/master",
    "GITHUB_EVENT_NAME": "push",
}


def http_error(code):
    return HTTPError("https://example.invalid/", code, "fixture", {}, None)


def summary(number, **fields):
    return {
        "number": number, "title": "Recorded change", "created_at": BEFORE,
        "updated_at": AT, "state": "open", "head": {"ref": "codex/work", "sha": "tip"},
        "author_association": "OWNER", **fields,
    }


class TransportTests(TestCase):
    def test_read_only_token_fallback_and_metrics_when_final_read_fails(self):
        with patch.dict("os.environ", {}, clear=True), patch(
            "collect.subprocess.check_output", return_value="fake-token\n"
        ) as auth:
            api = collect.GitHub()
        auth.assert_called_once_with(["gh", "auth", "token"], text=True)
        self.assertEqual(api.token, "fake-token")
        with patch.object(api, "request") as request:
            request.side_effect = [
                {"resources": {"core": {"remaining": 7}, "graphql": {"remaining": 9}}},
                URLError("rate read unavailable"),
            ]
            self.assertEqual(api.metrics()["rate_limit_remaining"], 7)
            self.assertEqual(api.metrics()["graphql_remaining"], 9)

    def test_pagination_respects_field_query_and_stops_on_a_short_page(self):
        api = collect.GitHub(token="fake")
        with patch.object(api, "request", side_effect=[{"items": list(range(100))}, {"items": [100]}, [1]]) as read:
            self.assertEqual(api.pages("example?status=open", "items"), list(range(101)))
            self.assertEqual(api.pages("example"), [1])
        self.assertEqual(read.call_args_list, [
            call(f"{REPO}/example?status=open&per_page=100&page=1"),
            call(f"{REPO}/example?status=open&per_page=100&page=2"),
            call(f"{REPO}/example?per_page=100&page=1"),
        ])

    def test_pagination_fails_if_no_page_ends(self):
        api = collect.GitHub(token="fake")
        with patch.object(api, "request", return_value=[0] * 100) as read:
            with self.assertRaisesRegex(RuntimeError, "pagination"):
                api.pages("example")
        self.assertEqual(read.call_count, 1000)

    def test_public_json_retries_the_read_then_returns_the_document(self):
        with patch("collect.urllib.request.urlopen", side_effect=[
            http_error(504), io.BytesIO(b'{"status":"ok"}'),
        ]) as fetch, patch("collect.time.sleep") as sleep:
            self.assertEqual(collect.GitHub(token="fake").public_json("https://example.invalid/"), {"status": "ok"})
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(20)

    def test_empty_response_is_retried_and_cannot_be_read_as_a_floor(self):
        api = collect.GitHub(token="fake")
        with patch("collect.urllib.request.urlopen", side_effect=[io.BytesIO() for _ in range(3)]) as read, patch(
            "collect.time.sleep"
        ) as sleep:
            with self.assertRaises(json.JSONDecodeError):
                api.public_json("https://example.invalid/")
        self.assertEqual(read.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(20), call(20)])

    def test_binary_upload_has_its_own_body_and_type(self):
        api = collect.GitHub(token="fake", read_only=False)
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(headers={}, read=lambda: b""))
        response.__exit__ = Mock(return_value=False)
        with patch("collect.urllib.request.urlopen", return_value=response) as fetch:
            self.assertIsNone(api.request("https://example.invalid/upload", binary=b"bytes"))
        request = fetch.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/octet-stream")
        self.assertEqual(request.data, b"bytes")

    def test_git_reads_and_ancestor_checks_have_explicit_results(self):
        with patch("collect.subprocess.check_output", return_value="main\n") as read, patch(
            "collect.subprocess.run", return_value=Mock(returncode=1)
        ) as ancestor:
            self.assertEqual(collect.git("rev-parse", "HEAD"), "main")
            self.assertFalse(collect.contains("main", "another"))
        read.assert_called_once_with(["git", "rev-parse", "HEAD"], text=True)
        ancestor.assert_called_once_with(["git", "merge-base", "--is-ancestor", "another", "main"], capture_output=True)


class EvidenceTests(TestCase):
    def test_pull_collects_renames_and_actual_parents_and_keeps_incomplete_evidence(self):
        api = Mock()
        api.request.return_value = {"changed_files": 1, "commits": 1, "merged_at": None}
        api.pages.side_effect = [
            [{"filename": "frontend/new.ts", "previous_filename": "frontend/old.ts"}],
            [{"sha": "merge", "parents": [{"sha": "base"}, {"sha": "main"}],
              "commit": {"committer": {"date": AT}}}],
        ]
        with patch("collect.contains", return_value=True) as included:
            pull = collect.collect_pull(api, summary(12, title="Report from sample-handle",
                                                     user={"login": "sample-handle"}))
        self.assertFalse(pull["title_trusted"])
        included.assert_called_once_with("origin/master", "main")
        self.assertEqual(pull["files"], ["frontend/new.ts", "frontend/old.ts"])
        self.assertTrue(pull["files_complete"])
        self.assertTrue(pull["commits_complete"])
        self.assertTrue(pull["commits"][0]["merge_from_master"])
        api.request.return_value = {"changed_files": 1, "merged_at": AT, "merge_commit_sha": "shipped"}
        api.pages.side_effect = [[{"filename": "frontend/new.ts"}]]
        close = collect.collect_pull(api, summary(12, state="closed"))
        self.assertEqual(close["merged_at"], AT)
        self.assertNotIn("commits", close)
        api.request.side_effect = URLError("evidence unavailable")
        with redirect_stderr(io.StringIO()) as recorded:
            missing = collect.collect_pull(api, summary(13))
        self.assertFalse(missing["files_complete"])
        self.assertFalse(missing["checks_complete"])
        self.assertIn("#13", recorded.getvalue())

    def test_acceptance_heading_can_use_the_past_tense(self):
        result = collect.safe_comment({
            "body": "**Fable ACCEPTED**", "created_at": AT, "updated_at": AT,
            "author_association": "OWNER",
        })
        self.assertTrue(result["fable_accept"])

    def test_annotation_reuses_immutable_commits_and_checks_rename_sources(self):
        api = Mock()
        api.request.return_value = {"parents": [{}, {"sha": "master-parent"}]}
        api.pages.side_effect = [
            [{"filename": "backend/tests/test_one.py"}],
            [{"filename": "backend/tests/test_two.py", "previous_filename": "backend/app/models.py"}],
        ]
        commits = [
            {"sha": "cached", "parents": 1, "at": AT},
            {"sha": "main-merge", "parents": 2, "at": AT},
            {"sha": "tests", "parents": 1, "at": AT},
            {"sha": "production-rename", "parents": 1, "at": AT},
        ]
        pull = {"number": 12, "commits": commits,
                "reviews": [{"state": "APPROVED", "submitted_at": BEFORE}],
                "comments": [{"fable_accept": True, "association": "OWNER", "created_at": BEFORE}]}
        with patch("collect.contains", return_value=True):
            collect.annotate_test_commits(api, [
                {"number": 10, "merged_at": AT}, {"number": 11}, pull
            ], {"12": {"commits": [{"sha": "cached", "test_only": True}]}})
        self.assertTrue(commits[0]["test_only"])
        self.assertTrue(commits[1]["merge_from_master"])
        self.assertTrue(commits[2]["test_only"])
        self.assertFalse(commits[3]["test_only"])
        self.assertEqual(api.pages.call_args_list, [
            call("commits/tests", "files"), call("commits/production-rename", "files"),
        ])

    def test_reconciliation_uses_exact_head_and_separates_ci_and_commit_statuses(self):
        api = Mock()
        contexts = [
            {"context": "Vercel", "state": "PENDING", "createdAt": AT},
            {"context": "TestFlight", "state": "SUCCESS", "createdAt": AT},
            {"name": "Update the factory"},
            {"name": "frontend-build", "status": "COMPLETED", "conclusion": "FAILURE",
             "startedAt": AT, "completedAt": NOW, "checkSuite": {
                "app": {"slug": "github-actions"}, "workflowRun": {"workflow": {"name": "CI"}},
             }},
        ]
        good = {
            "headRefOid": "tip",
            "timelineItems": {"nodes": [{"createdAt": AT}]},
            "reviews": {"totalCount": 101, "nodes": [
                {"author": {"login": "claude", "__typename": "Bot"}, "state": "APPROVED",
                 "submittedAt": AT, "commit": {"oid": "tip"}},
                {"author": {"login": "claude", "__typename": "User"}, "state": "APPROVED",
                 "submittedAt": AT, "commit": {"oid": "tip"}},
            ]},
            "comments": {"totalCount": 1, "nodes": [
                {"body": "**Fable: ACCEPT at `abcdef1234`**", "createdAt": AT, "updatedAt": AT,
                 "authorAssociation": "OWNER"},
            ]},
            "commits": {"nodes": [{"commit": {"statusCheckRollup": {
                "contexts": {"totalCount": len(contexts), "nodes": contexts},
            }}}]},
        }
        api.request.return_value = {"data": {"repository": {
            "p12": {"headRefOid": "other"}, "p13": good,
        }}}
        stale = {"number": 12, "state": "open", "head_sha": "tip"}
        current = {"number": 13, "state": "open", "head_sha": "tip"}
        collect.refresh_open_evidence(api, [stale, current])
        self.assertFalse(stale["checks_complete"])
        self.assertEqual(current["review_resumed_at"], AT)
        self.assertEqual(len(current["reviews"]), 1)
        self.assertFalse(current["reviews_complete"])
        self.assertEqual(current["comments"][0]["fable_accept_sha"], "abcdef1234")
        self.assertEqual([c["name"] for c in current["checks"]], ["Vercel", "TestFlight", "frontend-build"])
        self.assertTrue(current["checks"][-1]["ci"])
        api.request.return_value = {"errors": [{"path": ["repository"]}]}
        with self.assertRaisesRegex(RuntimeError, "open-change checks"):
            collect.refresh_open_evidence(api, [current])

    def test_deployment_history_pages_past_missing_reports_and_excludes_side_commits(self):
        api = Mock()
        def node(sha, committed, contexts):
            return {"oid": sha, "committedDate": committed,
                    "statusCheckRollup": {"contexts": {"nodes": contexts}}}
        def page(nodes, cursor, more, reports=None, errors=None):
            return {"errors": errors, "data": {"reports": reports, "repository": {
                "defaultBranchRef": {"target": {"history": {
                    "nodes": nodes, "pageInfo": {"endCursor": cursor, "hasNextPage": more},
                }}},
            }}}
        deploy = {"name": "deploy", "status": "IN_PROGRESS", "startedAt": AT,
                  "checkSuite": {"workflowRun": {"workflow": {"name": "CI"}}}}
        apps = "Bain Luck | TestFlight from master"
        api.request.side_effect = [
            page([node("side", AT, []), node("head", AT, [
                {"context": "Vercel", "state": "PENDING", "createdAt": AT,
                 "description": "Vercel is deploying your app"},
                {"context": apps, "state": "PENDING", "createdAt": AT, "description": "In progress"},
                deploy,
            ])], "next", True, {"issueCount": 0}),
            page([node("older", BEFORE, [
                {"context": line, "state": "SUCCESS", "createdAt": BEFORE}
                for line in ["Vercel", apps]
            ])], "unused", True),
        ]
        with patch("collect.git", return_value="head\nolder"):
            receipts, latest, starts, reports = collect.history_signals(api, collect.instant(AT), BEFORE)
        self.assertEqual([r["line"] for r in receipts], ["Website", "Apps"])
        self.assertEqual(latest["Apps"]["state"], "pending")
        self.assertEqual([r["line"] for r in starts], ["Website", "Apps", "Server"])
        self.assertEqual(reports, {"issueCount": 0})
        self.assertEqual(api.request.call_args_list[1].args[1]["variables"]["cursor"], "next")
        api.request.side_effect = None
        api.request.return_value = {"errors": [{"path": ["repository"]}]}
        with patch("collect.git", return_value="head"):
            with self.assertRaisesRegex(RuntimeError, "deployment status history"):
                collect.history_signals(api, collect.instant(AT), BEFORE)

    def test_failed_or_unreadable_master_job_evidence_stays_conservative(self):
        api = Mock()
        old = {"name": "CI", "status": "completed", "id": 1, "run_attempt": 1,
               "head_sha": "old", "conclusion": "failure", "updated_at": AT}
        current = {**old, "id": 2, "conclusion": "success", "updated_at": NOW}
        self.assertEqual(collect.master_checks(api, [current], [old], [])["tests"], "passing")
        self.assertNotIn("blocked_server_release", collect.master_checks(api, [], [old], []))
        pull = {"number": 12, "merged_at": AT, "merge_commit_sha": "old",
                "files": ["backend/app/tasks.py"]}
        api.request.side_effect = URLError("jobs unavailable")
        self.assertEqual(collect.master_checks(api, [], [old], [pull])["tests"], "failing")
        rerun = {**old, "id": 3, "run_attempt": 2, "status": "in_progress"}
        self.assertEqual(collect.master_checks(api, [rerun], [old], [pull])["tests"], "unknown")


class CollectorPassTests(TestCase):
    def test_a_run_with_no_verified_server_health_retains_the_last_floor(self):
        api = Mock()
        api.public_json.side_effect = http_error(504)
        with patch("collect.history_signals", return_value=([], {}, [], None)):
            with self.assertRaisesRegex(RuntimeError, "Retaining the previous snapshot"):
                collect.collect(api)
        api.pages.assert_not_called()

    def test_keeps_old_merged_changes_until_ancestry_confirms_the_release(self):
        old = summary(12, state="closed", merged_at=AT, merge_commit_sha="merged")
        opened = summary(13)
        before = {
            "generated_at": AT, "observed_since": BEFORE, "injury_clock": {"recorded": True},
            "changes": [{"number": 12, "station": "Ship", "merged_at": AT}],
        }
        start_time = "2026-11-23T08:01:11Z"
        published = collect.instant(NOW)
        now_posts = [
            {"body": "merging #17 (website)", "created_at": AT, "author_association": "OWNER"},
            {"body": "live #12 (server)", "created_at": "2026-11-23T09:00:00Z",
             "author_association": "OWNER"},
            {"body": "live #17 (server)", "created_at": AT, "author_association": "OWNER"},
        ]
        api = Mock()
        api.public_json.return_value = {"status": "ok", "commit": "server"}
        api.pages.side_effect = [[opened], now_posts]
        ci = {"id": 1, "name": "CI", "status": "completed", "conclusion": "success",
              "run_started_at": BEFORE, "updated_at": AT}
        api.request.side_effect = [
            [], old, {"workflow_runs": [ci, {"id": 2, "name": "TestFlight release", "conclusion": "cancelled"}]},
            {"workflow_runs": [ci]},
            {"workflow_runs": [{"status": "in_progress", "run_started_at": start_time}]},
        ]
        receipts = [
            {"line": "Website", "commit": "side-web", "at": AT},
            {"line": "Apps", "commit": "apps", "at": AT},
        ]
        git_results = {"rev-parse": "server", "show": BEFORE, "rev-list": "server\nmerged\napps"}
        with (
            patch("collect.datetime") as clock,
            patch("collect.history_signals", return_value=(receipts, {}, [], None)),
            patch("collect.git", side_effect=lambda command, *args: git_results[command]),
            patch("collect.contains", return_value=False) as contains,
            patch("collect.collect_pull", side_effect=lambda api, pull, cache: pull),
            patch("collect.refresh_open_evidence"),
        ):
            clock.now.return_value = published
            snapshot = collect.collect(api, before)
        api.request.assert_any_call(f"{REPO}/pulls/12")
        api.request.assert_any_call(
            f"{REPO}/actions/workflows/ci.yml/runs?branch=master&event=push&status=in_progress&per_page=100"
        )
        contains.assert_called_once_with("side-web", "merged")
        self.assertEqual(snapshot["master"]["oldest_running_ci_at"], start_time)
        self.assertEqual(snapshot["master"]["testflight"], "cancelled")
        self.assertEqual(snapshot["master"]["successful_runs"], [{"started_at": BEFORE, "finished_at": AT}])
        reported = snapshot["deployments"][-1]
        self.assertEqual(reported["kind"], "reported")
        self.assertEqual(reported["at"], now_posts[1]["created_at"])
        self.assertEqual(reported["contains"], ["merged"])

    def test_running_ci_read_failure_keeps_the_rest_of_the_snapshot(self):
        api = Mock()
        api.public_json.return_value = {"status": "ok", "commit": "server"}
        api.pages.return_value = []
        api.request.side_effect = [[], {"workflow_runs": []}, {"workflow_runs": []}, http_error(504)]
        original = collect.instant(NOW)
        receipts = [
            {"line": "Website", "commit": "web", "at": AT},
            {"line": "Apps", "commit": "apps", "at": AT},
        ]
        git_results = {"rev-parse": "server", "show": BEFORE, "rev-list": "web\napps\nserver"}
        with (
            patch("collect.datetime") as clock,
            patch("collect.history_signals", return_value=(receipts, {}, [], None)),
            patch("collect.git", side_effect=lambda command, *args: git_results[command]),
        ):
            clock.now.return_value = original
            snapshot = collect.collect(api, open_summaries=[])
        self.assertNotIn("oldest_running_ci_at", snapshot["master"])
        self.assertEqual(snapshot["deployments"][-1]["commit"], "server")
        self.assertEqual(snapshot["captured_at"], NOW)


class PublicationTests(TestCase):
    def test_master_publish_requires_both_checkout_ancestry_and_builtin_token(self):
        with patch.dict("os.environ", BRANCH_ENV, clear=True), patch(
            "collect.git", side_effect=["master", "candidate", "master", "candidate"]
        ), patch("collect.contains", side_effect=[False, True]):
            with self.assertRaisesRegex(RuntimeError, "checked-out master"):
                collect.authorize_publication()
            with self.assertRaisesRegex(RuntimeError, "built-in GitHub token"):
                collect.authorize_publication()

    def test_recovery_reads_the_temporary_snapshot_and_matches_the_cache_by_timestamp(self):
        api = Mock()
        release = {"assets": []}
        api.request.side_effect = [http_error(404), http_error(504), release]
        self.assertEqual(collect.read_published(api), (None, {}, {}))
        with self.assertRaises(HTTPError):
            collect.read_published(api)
        self.assertEqual(collect.read_published(api), (release, {}, {}))
        api.request.side_effect = None
        api.request.return_value = {"assets": [
            {"name": name, "browser_download_url": url, "updated_at": AT}
            for name, url in [("factory-next.json", "floor"), ("factory-cache.json", "cache")]
        ]}
        api.public_json.side_effect = [
            {"generated_at": AT, "_collector": {"old": "metadata"}},
            {"generated_at": AT, "pulls": {"12": {"head_sha": "tip"}}, "crew_week": {"week": 1}},
        ]
        _, previous, cache = collect.read_published(api)
        self.assertEqual(previous, {"generated_at": AT})
        self.assertEqual(cache, {"12": {"head_sha": "tip"}, "crew_week": {"week": 1}})

    def test_publisher_cleans_up_both_asset_names_before_promoting_the_new_read(self):
        api = Mock()
        api.request.side_effect = [
            [{"name": "factory-next.json", "id": 4}, {"name": "factory.json", "id": 5}],
            None, {"id": 6}, None, None,
        ]
        collect.publish_asset(api, {"id": 1, "upload_url": "https://example.invalid/publish"},
                              "factory.json", {"changes": []})
        self.assertEqual(api.request.call_args_list, [
            call(f"{REPO}/releases/1/assets"),
            call(f"{REPO}/releases/assets/4", method="DELETE"),
            call("https://example.invalid/publish?name=factory-next.json", method="POST",
                 binary=b'{"changes":[]}'),
            call(f"{REPO}/releases/assets/5", method="DELETE"),
            call(f"{REPO}/releases/assets/6", {"name": "factory.json"}, method="PATCH"),
        ])

    def test_cli_read_only_outputs_keep_the_snapshot_and_cache_separate(self):
        snapshot = {
            "captured_at": NOW, "pulls": [], "deployments": [],
            "master": {"tests": "passing", "testflight": "success"},
            "crew_posts": {"E": {"at": AT, "comment_id": 123}},
            "lane_updates": {"F": {"at": AT, "text": "checking the newest build"}},
        }
        api = Mock()
        api.metrics.return_value = {}
        previous = {"generated_at": AT, "observed_since": BEFORE}
        cache = {"pulls": {}, "crew_week": {"since": BEFORE, "builders": {}}}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "prior.json").write_text(json.dumps(previous))
            (root / "cache-in.json").write_text(json.dumps(cache))
            argv = ["collect.py", "--output", str(root / "factory.json"),
                    "--previous", str(root / "prior.json"), "--cache-input", str(root / "cache-in.json"),
                    "--capture", str(root / "fixture" / "capture.json"),
                    "--cache-output", str(root / "cache-out.json")]
            with (
                patch.dict("os.environ", {}, clear=True),
                patch("sys.argv", argv),
                patch("collect.GitHub", return_value=api) as client,
                patch("collect.collect", return_value=snapshot) as run,
                patch("collect.machine_queue", return_value={}),
                redirect_stdout(io.StringIO()),
            ):
                collect.main()
            output = json.loads((root / "factory.json").read_text())
            self.assertEqual(output["crew_posts"], snapshot["crew_posts"])
            self.assertEqual(output["lane_updates"], snapshot["lane_updates"])
            self.assertEqual(json.loads((root / "fixture" / "capture.json").read_text()), snapshot)
            self.assertEqual(json.loads((root / "cache-out.json").read_text())["generated_at"], NOW)
        client.assert_called_once_with(read_only=True)
        run.assert_called_once_with(api, previous, {"crew_week": cache["crew_week"]}, None)
        api.request.assert_not_called()

    def test_first_publish_creates_one_release_and_publishes_both_assets(self):
        snapshot = {"captured_at": NOW, "pulls": [], "deployments": [],
                    "master": {"tests": "passing", "testflight": "success"}}
        api = Mock()
        api.metrics.return_value = {}
        api.pages.return_value = []
        release = {"id": 15}
        api.request.side_effect = [http_error(404), release]
        with (
            TemporaryDirectory() as directory,
            patch.dict("os.environ", {}, clear=True),
            patch("sys.argv", ["collect.py", "--publish", "--output", f"{directory}/factory.json"]),
            patch("collect.authorize_publication"),
            patch("collect.GitHub", return_value=api),
            patch("collect.collect", return_value=snapshot),
            patch("collect.machine_queue", return_value={}),
            patch("collect.git", return_value="master-head"),
            patch("collect.publish_asset") as upload,
            redirect_stdout(io.StringIO()),
        ):
            collect.main()
        self.assertEqual(api.request.call_args.args[1]["target_commitish"], "master-head")
        self.assertEqual(api.request.call_args.kwargs["method"], "POST")
        self.assertEqual([args.args[2] for args in upload.call_args_list], [
            "factory-cache.json", "factory.json",
        ])

    def test_manual_draw_is_refused_outside_an_authorized_master_dispatch(self):
        with (
            patch.dict("os.environ", {"FACTORY_MEASURE_PICTURE": "true"}, clear=True),
            patch("sys.argv", ["collect.py", "--output", "unused"]),
            patch("collect.GitHub") as client,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            with self.assertRaises(SystemExit) as error:
                collect.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("manual master run", stderr.getvalue())
        client.assert_not_called()

    def test_meter_callback_patches_the_existing_release(self):
        api = Mock()
        api.metrics.return_value = {}
        def meter(_floor, budget, _key, **_options):
            budget.save("a test receipt")
            return None, {"status": "no-draw"}
        with (
            TemporaryDirectory() as directory,
            patch.dict("os.environ", {**BRANCH_ENV, "GITHUB_EVENT_NAME": "workflow_dispatch",
                                      "FACTORY_MEASURE_PICTURE": "true"}, clear=True),
            patch("sys.argv", ["collect.py", "--publish", "--output", f"{directory}/factory.json"]),
            patch("collect.authorize_publication"),
            patch("collect.GitHub", return_value=api),
            patch("collect.read_published", return_value=({"id": 15}, {}, {})),
            patch("collect.metered_picture", side_effect=meter),
            redirect_stdout(io.StringIO()),
        ):
            collect.main()
        api.request.assert_called_once_with(f"{REPO}/releases/15", {"body": "a test receipt"}, method="PATCH")

    def test_cli_entrypoint_checks_arguments_before_opening_a_client(self):
        with patch("sys.argv", [collect.__file__]), redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as error:
                runpy.run_path(collect.__file__, run_name="__main__")
        self.assertEqual(error.exception.code, 2)
        self.assertIn("--output", stderr.getvalue())
