import base64
from datetime import datetime, timedelta, timezone
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daily_picture import MAX_WEBP_BYTES, asset_label, asset_name, gallery, metered_picture, picture_request, quote, webp_dimensions
from collect import main, publish_daily_picture
from notes import MONTHLY_COST_MICROS, ModelBudget, meter_body
from llm_models import image_model_for_task


class DailyPictureTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 22, 3, tzinfo=timezone.utc)
        self.changes = [
            {"number": 1, "station": "Test", "title": "a private title"},
            {"number": 2, "station": "Live", "live_at": self.now.isoformat()},
            {"number": 2, "station": "Live", "live_at": self.now.isoformat()},
        ]
        self.snapshot = {"generated_at": self.now.isoformat(), "changes": self.changes}
        self.save = Mock()
        self.budget = ModelBudget("", self.save, now=self.now)
        # A lossless 1024×1024 solid-color fixture with a real WebP frame.
        self.image = base64.b64decode(
            "UklGRlAAAABXRUJQVlA4TEMAAAAv/8P/AAfQseY1qf8BgUCyv/kERfQ/4z//+c9//vOf"
            "//znP//5z3/+85///Oc///nPf/7zn//85z//+c9//vOf//zfAA=="
        )
        self.request = Mock(return_value=({
            "usage": {
                "input_tokens": 105,
                "input_tokens_details": {"text_tokens": 105, "image_tokens": 0},
                "output_tokens": 823,
            },
            "data": [{"b64_json": base64.b64encode(self.image).decode()}],
        }, "req_test"))

    def test_disabled_path_skips_the_provider_and_the_template_omits_titles(self):
        result, receipt = metered_picture(
            self.snapshot, self.budget, "fake", enabled=False, request=self.request,
        )
        self.assertIsNone(result)
        self.assertEqual(receipt["status"], "off")
        self.request.assert_not_called()
        self.save.assert_not_called()
        record, payload = picture_request(self.snapshot, image_model_for_task("factory_picture"))
        self.assertEqual((record["floor"], record["shipped"]), (1, 1))
        self.assertEqual(payload["n"], 1)
        self.assertIn("no lettering", payload["prompt"])
        self.assertIn("free of signs, labels, words, letters, numbers and rows of tiny marks.", payload["prompt"])
        self.assertNotIn("private title", payload["prompt"])

    def test_measurement_reserves_and_prices_one_image_for_the_receipt(self):
        result, receipt = metered_picture(
            self.snapshot, self.budget, "fake", sample=True, enabled=False, request=self.request,
        )
        self.assertEqual(result[1], self.image)
        self.assertEqual(receipt["status"], "measured")
        self.assertEqual(receipt["used_micros"], 25_215)
        self.assertEqual(receipt["month_before_micros"], 0)
        self.assertEqual(receipt["month_cost_usd"], 0.025215)
        self.assertLess(receipt["used_micros"], receipt["reserve_micros"])
        self.assertEqual(self.save.call_count, 2)
        tomorrow = datetime(2026, 11, 23, 3, tzinfo=timezone.utc)
        again = ModelBudget(self.budget.body, self.save, now=tomorrow)
        metered_picture(
            {**self.snapshot, "generated_at": tomorrow.isoformat()},
            again, "fake", sample=True, enabled=False, request=self.request,
        )
        self.request.assert_called_once()

    def test_request_uses_plain_scene_phrases_with_exact_numbers_only_in_the_caption(self):
        snapshot = {
            **self.snapshot,
            "changes": self.changes + [
                {"number": number, "station": "Review", "title": "PRINT #13447"}
                for number in range(100, 110)
            ],
            "stops": [{"kind": "hold", "line": "Server"}],
        }
        result, receipt = metered_picture(
            snapshot, self.budget, "fake", request=self.request,
            prepare=lambda: True, check=lambda image: True,
        )
        self.assertEqual(receipt["status"], "drawn")
        record, _ = result
        self.assertEqual((record["floor"], record["shipped"]), (11, 1))
        (payload, _), _ = self.request.call_args
        self.assertEqual(payload["n"], 1)
        self.assertIn("The space by the workbench is clear of crates.", payload["prompt"])
        self.assertIn("Unmarked wooden cargo rests beside the brass rollers", payload["prompt"])
        self.assertIn("Unmarked wooden cargo fills the space around a bare table.", payload["prompt"])
        self.assertIn("A red lamp glows by the loading ramp.", payload["prompt"])
        self.assertNotRegex(payload["prompt"], r'[0-9"{}#:]+|PRINT|private title')

    def test_unsafe_outgoing_request_is_refused_before_the_meter_or_provider(self):
        record, payload = picture_request(self.snapshot, image_model_for_task("factory_picture"))
        prepare = Mock(return_value=True)
        for override in (
            {"prompt": payload["prompt"] + '\n"Ship 42 crates"'},
            {"prompt": payload["prompt"] + "\nPaint the word Factory."},
            {"prompt": payload["prompt"].replace("bare wood", "printed signs")},
            {"n": 2},
        ):
            with self.subTest(override=override), patch(
                "daily_picture.picture_request", return_value=(record, {**payload, **override}),
            ):
                picture, receipt = metered_picture(
                    self.snapshot, self.budget, "fake", request=self.request, prepare=prepare,
                )
                self.assertIsNone(picture)
                self.assertEqual(receipt["status"], "unsafe-picture-request")
        self.save.assert_not_called()
        prepare.assert_not_called()
        self.request.assert_not_called()

    def test_sample_respects_the_old_five_dollar_limit(self):
        meter = self.budget.state()
        meter.update(calls=1, month_micros=4_960_000)
        self.budget = ModelBudget(meter_body("", meter), self.save, now=self.now)
        _, receipt = metered_picture(
            self.snapshot, self.budget, "fake", sample=True, enabled=False, request=self.request,
        )
        self.assertEqual(receipt["status"], "over-measurement-budget")
        self.request.assert_not_called()
        self.save.assert_not_called()

    def test_failed_request_keeps_the_reserve_and_prevents_another_measurement(self):
        self.request.side_effect = TimeoutError()
        _, receipt = metered_picture(
            self.snapshot, self.budget, "fake", sample=True, enabled=False, request=self.request,
        )
        self.assertEqual(receipt["status"], "request-failed")
        reserve = quote(image_model_for_task("factory_picture"))["reserve_micros"]
        self.assertEqual(self.budget.state()["month_micros"], reserve)
        metered_picture(
            self.snapshot, self.budget, "fake", sample=True, enabled=False, request=self.request,
        )
        self.request.assert_called_once()

    def test_bad_usage_names_the_check_and_keeps_the_reserve(self):
        response, request_id = self.request.return_value
        self.request.return_value = ({**response, "usage": {}}, request_id)
        picture, receipt = metered_picture(
            self.snapshot, self.budget, "fake", request=self.request,
            prepare=lambda: True,
        )
        self.assertIsNone(picture)
        self.assertEqual(receipt["status"], "usage-unavailable")
        self.assertEqual(self.budget.state()["month_micros"], receipt["reserve_micros"])
        self.request.assert_called_once()

    def test_daily_draw_waits_until_evening_and_settles_once_per_pacific_day(self):
        meter = self.budget.state()
        meter.update(calls=1, month_micros=38_066)
        body = meter_body("", meter)
        before_evening = self.now - timedelta(hours=2)
        prepare = Mock(return_value=True)
        check = Mock(return_value=True)
        options = {"request": self.request, "prepare": prepare, "check": check}

        _, receipt = metered_picture(
            {**self.snapshot, "generated_at": before_evening.isoformat()},
            ModelBudget(body, self.save, now=before_evening), "fake", **options,
        )
        self.assertEqual(receipt["status"], "outside-daily-turn")
        self.request.assert_not_called()

        budget = ModelBudget(body, self.save, now=self.now)
        picture, receipt = metered_picture(self.snapshot, budget, "fake", **options)
        self.assertEqual(asset_name(picture[0]), "factory-picture-2026-11-21.webp")
        self.assertEqual(picture[1], self.image)
        self.assertEqual(receipt["status"], "drawn")
        self.assertEqual(receipt["month_before_micros"], 38_066)
        self.assertEqual(receipt["used_micros"], 25_215)
        self.assertEqual(receipt["month_cost_usd"], 0.063281)

        again = ModelBudget(budget.body, self.save, now=self.now + timedelta(minutes=5))
        _, receipt = metered_picture(self.snapshot, again, "fake", **options)
        self.assertEqual(receipt["status"], "outside-daily-turn")
        self.request.assert_called_once()
        self.assertEqual(self.save.call_count, 2)

    def test_daily_draw_keeps_the_picture_and_monthly_limits(self):
        with patch("daily_picture.quote", return_value={"reserve_micros": 500_001}):
            _, receipt = metered_picture(self.snapshot, self.budget, "fake", request=self.request)
        self.assertEqual(receipt["status"], "over-picture-budget")

        meter = self.budget.state()
        meter.update(calls=1, month_micros=MONTHLY_COST_MICROS - 1,
                     picture_day=meter["day"], picture_draws=1, picture_retry=True)
        budget = ModelBudget(meter_body("", meter), self.save, now=self.now)
        _, receipt = metered_picture(self.snapshot, budget, "fake", request=self.request)
        self.assertEqual(receipt["status"], "no-reservation")
        self.request.assert_not_called()
        self.save.assert_not_called()

    def test_three_lettering_rejections_leave_the_previous_picture_and_prevent_a_fourth_draw(self):
        earlier = {"day": "2026-11-20", "as_of": "2026-11-21T03:00:00Z", "floor": 2, "shipped": 5}
        asset = {"name": asset_name(earlier), "label": asset_label(earlier), "state": "uploaded"}
        budget = self.budget
        for attempt in range(1, 4):
            picture, receipt = metered_picture(
                self.snapshot, budget, "fake", request=self.request,
                prepare=lambda: True, check=lambda image: False,
            )
            self.assertIsNone(picture)
            self.assertEqual(receipt["status"], "lettering-found")
            self.assertEqual(receipt["attempt"], attempt)
            self.assertEqual(receipt["day"], "2026-11-21")
            self.assertEqual(receipt["used_micros"], 25_215)
            self.assertEqual(receipt["month_cost_usd"], attempt * 25_215 / 1_000_000)
            budget = ModelBudget(budget.body, self.save, now=self.now)
        self.assertEqual(gallery([asset], self.now), [earlier])
        _, receipt = metered_picture(
            self.snapshot, budget, "fake", request=self.request,
            prepare=lambda: True, check=lambda image: True,
        )
        self.assertEqual(receipt["status"], "outside-daily-turn")
        self.assertEqual(self.request.call_count, 3)

    def test_picture_slots_stay_available_after_notes_and_speech_reach_197(self):
        meter = self.budget.state()
        meter.update(calls=195, picture_day="2026-11-20", picture_draws=3, picture_retry=False)
        budget = ModelBudget(meter_body("", meter), self.save, now=self.now)
        self.assertIsNotNone(budget.reserve(1, notes_hash="a" * 64))
        self.assertIsNotNone(budget.reserve(1))
        self.assertEqual(budget.state()["calls"], 197)
        for attempt in range(1, 4):
            self.assertIsNone(budget.reserve(1, notes_hash="b" * 64))
            self.assertIsNone(budget.reserve(1))
            _, receipt = metered_picture(
                self.snapshot, budget, "fake", request=self.request,
                prepare=lambda: True, check=lambda image: False,
            )
            self.assertEqual((receipt["attempt"], receipt["status"]), (attempt, "lettering-found"))
        self.assertEqual(budget.state()["calls"], 200)
        self.assertEqual(self.request.call_count, 3)

    def test_picture_slots_count_separately_from_the_197_other_calls(self):
        meter = self.budget.state()
        meter.update(calls=197, picture_day=meter["day"], picture_draws=1, picture_retry=False)
        budget = ModelBudget(meter_body("", meter), self.save, now=self.now)
        self.assertIsNotNone(budget.reserve(1))
        self.assertEqual(budget.state()["calls"], 198)
        self.assertIsNone(budget.reserve(1, notes_hash="a" * 64))
        self.assertIsNone(budget.reserve(1))

    def test_november_23_legacy_rejection_counts_as_draw_one_and_successful_retry_closes_the_day(self):
        now = datetime(2026, 11, 24, 3, tzinfo=timezone.utc)
        meter = ModelBudget("", self.save, now=now).state()
        meter.update(calls=159, micros=70_961, month_micros=271_141, picture_day="2026-11-23")
        snapshot = {**self.snapshot, "generated_at": now.isoformat()}
        budget = ModelBudget(meter_body("", meter), self.save, now=now)
        options = {"request": self.request, "prepare": lambda: True, "check": lambda image: True}
        picture, receipt = metered_picture(snapshot, budget, "fake", **options)
        self.assertEqual(picture[1], self.image)
        self.assertEqual((receipt["attempt"], receipt["status"]), (2, "drawn"))
        self.assertEqual(receipt["month_before_micros"], 271_141)
        self.assertEqual(receipt["month_cost_usd"], 0.296356)
        again = ModelBudget(budget.body, self.save, now=now)
        _, receipt = metered_picture(snapshot, again, "fake", **options)
        self.assertEqual(receipt["status"], "outside-daily-turn")
        self.request.assert_called_once()

    def test_other_legacy_draws_with_unknown_outcomes_do_not_unlock_retries(self):
        meter = self.budget.state()
        meter.update(calls=1, picture_day=meter["day"])
        budget = ModelBudget(meter_body("", meter), self.save, now=self.now)
        _, receipt = metered_picture(self.snapshot, budget, "fake", request=self.request)
        self.assertEqual(receipt["status"], "outside-daily-turn")
        self.request.assert_not_called()

    def test_unknown_charge_consumes_retry_and_stops_more_draws(self):
        options = {"request": self.request, "prepare": lambda: True, "check": lambda image: False}
        _, first = metered_picture(self.snapshot, self.budget, "fake", **options)
        self.assertEqual(first["status"], "lettering-found")
        self.request.side_effect = TimeoutError()
        _, second = metered_picture(self.snapshot, self.budget, "fake", **options)
        self.assertEqual((second["attempt"], second["status"]), (2, "request-failed"))
        self.assertEqual(self.budget.state()["month_micros"], 25_215 + second["reserve_micros"])
        _, after = metered_picture(self.snapshot, self.budget, "fake", **options)
        self.assertEqual(after["status"], "outside-daily-turn")
        self.assertEqual(self.request.call_count, 2)

    def test_picture_validation_has_a_distinct_receipt_for_each_refusal(self):
        response, request_id = self.request.return_value
        short_webp = "UklGRi4AAABXRUJQVlA4TCIAAAAv/8F/AAfQseY1qf8BgUCyv/cMRfQ/4z//+c9//vOf//wf"
        for status, images in (
            ("picture-count-invalid", []),
            ("image-data-invalid", [{"b64_json": "!!!"}]),
            ("not-a-webp-image", [{"b64_json": base64.b64encode(b"plain text").decode()}]),
            ("not-a-webp-image", [{"b64_json": base64.b64encode(self.image[:-1]).decode()}]),
            ("image-too-large", [{"b64_json": base64.b64encode(self.image + bytes(MAX_WEBP_BYTES)).decode()}]),
            ("wrong-image-size", [{"b64_json": short_webp}]),
        ):
            with self.subTest(status=status):
                budget = ModelBudget("", self.save, now=self.now)
                provider = Mock(return_value=({**response, "data": images}, request_id))
                check = Mock()
                picture, receipt = metered_picture(
                    self.snapshot, budget, "fake", request=provider,
                    prepare=lambda: True, check=check,
                )
                self.assertIsNone(picture)
                self.assertEqual(receipt["status"], status)
                self.assertEqual(receipt["used_micros"], 25_215)
                metered_picture(
                    self.snapshot, budget, "fake", request=provider,
                    prepare=lambda: True, check=check,
                )
                provider.assert_called_once()
                check.assert_not_called()

    def test_webp_reads_lossy_lossless_and_extended_frames(self):
        lossy = "UklGRjIAAABXRUJQVlA4ICYAAACQAQCdASoIAAcAAUAmJZACdLoAA5gA/vuNS/V2J8KEE+vgCn3AAA=="
        extended = ("UklGRlYAAABXRUJQVlA4WAoAAAAQAAAABwAABgAAQUxQSAoAAAABB1DAiAhERP8D"
                    "VlA4ICYAAACQAQCdASoIAAcAAUAmJZACdLoAA5gA/vuNS/V2J8KEE+vgCn3AAA==")
        self.assertEqual(webp_dimensions(base64.b64decode(lossy)), (8, 7))
        self.assertEqual(webp_dimensions(base64.b64decode(extended)), (8, 7))
        self.assertEqual(webp_dimensions(self.image), (1024, 1024))

    def test_lettering_tool_failure_names_the_check(self):
        check = Mock(side_effect=subprocess.TimeoutExpired("tesseract", 10))
        picture, receipt = metered_picture(
            self.snapshot, self.budget, "fake", request=self.request,
            prepare=lambda: True, check=check,
        )
        self.assertIsNone(picture)
        self.assertEqual(receipt["status"], "lettering-check-failed")
        self.assertEqual(receipt["used_micros"], 25_215)
        self.request.assert_called_once()

    def test_missing_lettering_tool_does_not_spend(self):
        picture, receipt = metered_picture(
            self.snapshot, self.budget, "fake", request=self.request, prepare=lambda: False,
        )
        self.assertIsNone(picture)
        self.assertEqual(receipt["status"], "text-check-unavailable")
        self.request.assert_not_called()

    def test_oversize_prompt_names_the_check_without_spending(self):
        with patch("daily_picture.MAX_PROMPT_BYTES", 1):
            _, receipt = metered_picture(
                self.snapshot, self.budget, "fake", request=self.request, prepare=lambda: True,
            )
        self.assertEqual(receipt["status"], "prompt-too-large")
        self.request.assert_not_called()

    def test_gallery_has_seven_pacific_days_and_ignores_incomplete_assets(self):
        records = [
            {"day": f"2026-11-{day}", "as_of": f"2026-11-{day + 1}T03:00:00Z", "floor": day, "shipped": 5}
            for day in range(12, 22)
        ]
        assets = [{"name": asset_name(record), "label": asset_label(record), "state": "uploaded"}
                  for record in records]
        self.assertEqual(gallery(assets + [{**assets[-1], "state": "starter"}], self.now), records[-7:][::-1])

    def test_missing_key_or_unregistered_picture_model_skips_the_provider(self):
        metered_picture(
            self.snapshot, self.budget, "", sample=True, enabled=False, request=self.request,
        )
        with patch.dict("os.environ", {"LLM_MODEL_FACTORY_PICTURE": "unpriced"}):
            _, receipt = metered_picture(
                self.snapshot, self.budget, "fake", sample=True, enabled=False, request=self.request,
            )
        self.assertEqual(receipt["status"], "unpriced")
        self.request.assert_not_called()

    def test_manual_master_measurement_saves_only_the_picture_for_the_receipt(self):
        api = Mock()
        api.metrics.return_value = {"github_api_calls": 2}
        with TemporaryDirectory() as directory:
            output = Path(directory) / "factory.json"
            with patch.dict("os.environ", {
                "FACTORY_MEASURE_PICTURE": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
            }), patch("sys.argv", ["collect.py", "--publish", "--output", str(output)]), patch(
                "collect.authorize_publication"
            ) as authorize, patch("collect.GitHub", return_value=api), patch(
                "collect.read_published", return_value=({"id": 1}, self.snapshot, {})
            ), patch(
                "collect.metered_picture", return_value=(({}, self.image), {"status": "measured"})
            ) as measure, patch("collect.collect") as collect_floor, patch(
                "collect.publish_asset"
            ) as publish, redirect_stdout(io.StringIO()) as out:
                main()
            self.assertEqual(output.with_name("factory-measured-picture.webp").read_bytes(), self.image)
            self.assertFalse(output.exists())
        authorize.assert_called_once()
        self.assertTrue(measure.call_args.kwargs["sample"])
        collect_floor.assert_not_called()
        publish.assert_not_called()
        self.assertIn('"status": "measured"', out.getvalue())

    def test_upload_skips_the_release_when_daily_pictures_are_off(self):
        api = Mock()
        with patch("collect.DAILY_PICTURE_ENABLED", False):
            self.assertIsNone(publish_daily_picture(api, {}, None))
        api.request.assert_not_called()

    def test_measurement_write_error_logs_the_refused_write(self):
        api = Mock()
        api.metrics.return_value = {}
        with TemporaryDirectory() as directory, patch.dict("os.environ", {
            "FACTORY_MEASURE_PICTURE": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
        }), patch(
            "sys.argv", ["collect.py", "--publish", "--output", f"{directory}/factory.json"]
        ), patch("collect.authorize_publication"), patch("collect.GitHub", return_value=api), patch(
            "collect.read_published", return_value=({"id": 1}, self.snapshot, {})
        ), patch(
            "collect.metered_picture", return_value=(({}, self.image), {"status": "measured"})
        ) as draw, patch.object(Path, "write_bytes", side_effect=PermissionError), redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(PermissionError):
                main()
        draw.assert_called_once()
        self.assertIn('FACTORY_PICTURE {"status": "write-failed"}', out.getvalue())

    def test_release_upload_logs_a_rejection_or_an_unconfirmed_reply(self):
        for status, response in (
            ("upload-failed", HTTPError("https://example.invalid/upload", 422, "rejected", {}, None)),
            ("upload-unconfirmed", HTTPError("https://example.invalid/upload", 502, "gateway", {}, None)),
            ("upload-unconfirmed", IncompleteRead(b"")),
            ("upload-unconfirmed", {"state": "starter"}),
            ("published", {"state": "uploaded", "name": "factory-picture-2026-11-21.webp",
                           "label": "v1|2026-11-22T03:00:00+00:00|0|0"}),
        ):
            with self.subTest(status=status):
                api = Mock()
                api.pages.return_value = []
                api.metrics.return_value = {}
                api.request.side_effect = [response]
                record = {"day": "2026-11-21", "as_of": self.now.isoformat(), "floor": 0, "shipped": 0}
                run = {"captured_at": self.now.isoformat(), "pulls": [], "deployments": [],
                       "master": {"tests": "passing", "testflight": "success"}}
                release = {"id": 1, "upload_url": "https://example.invalid/upload{?name,label}"}
                with TemporaryDirectory() as directory, patch.dict("os.environ", {
                    "FACTORY_MEASURE_PICTURE": "false", "OPENAI_API_KEY": "",
                }), patch(
                    "sys.argv", ["collect.py", "--publish", "--output", f"{directory}/factory.json"]
                ), patch("collect.authorize_publication"), patch("collect.GitHub", return_value=api), patch(
                    "collect.read_published", return_value=(release, {}, {})
                ), patch("collect.collect", return_value=run), patch(
                    "collect.machine_queue", return_value={}
                ), patch(
                    "collect.metered_picture", return_value=((record, self.image), {"status": "drawn"})
                ) as draw, patch("collect.publish_asset"), redirect_stdout(io.StringIO()) as out:
                    main()
                tagged = next(line for line in out.getvalue().splitlines() if line.startswith("FACTORY_PICTURE "))
                self.assertEqual(json.loads(tagged.split(" ", 1)[1])["status"], status)
                self.assertEqual(api.request.call_args.kwargs["method"], "POST")
                api.request.assert_called_once()
                draw.assert_called_once()

    def test_collector_leaves_an_already_published_picture_in_place(self):
        api = Mock()
        api.pages.return_value = []
        api.metrics.return_value = {}
        record = {"day": "2026-11-21", "as_of": self.now.isoformat(), "floor": 0, "shipped": 0}
        asset = {"name": asset_name(record), "label": asset_label(record), "state": "uploaded"}
        run = {"captured_at": self.now.isoformat(), "pulls": [], "deployments": [],
               "master": {"tests": "passing", "testflight": "success"}}
        release = {"id": 1, "assets": [asset]}
        with TemporaryDirectory() as directory, patch.dict("os.environ", {
            "FACTORY_MEASURE_PICTURE": "false", "OPENAI_API_KEY": "",
        }), patch(
            "sys.argv", ["collect.py", "--publish", "--output", f"{directory}/factory.json"]
        ), patch("collect.authorize_publication"), patch("collect.GitHub", return_value=api), patch(
            "collect.read_published", return_value=(release, {}, {})
        ), patch("collect.collect", return_value=run), patch(
            "collect.machine_queue", return_value={}
        ), patch("collect.ModelBudget", return_value=self.budget), patch(
            "collect.metered_picture"
        ) as draw, patch("collect.publish_asset"), redirect_stdout(io.StringIO()) as out:
            main()
            reading = json.loads((Path(directory) / "factory.json").read_text())
        draw.assert_not_called()
        api.request.assert_not_called()
        self.assertEqual(reading["pictures"], [record])
        self.assertIn('FACTORY_PICTURE {"status": "already-published"}', out.getvalue())
