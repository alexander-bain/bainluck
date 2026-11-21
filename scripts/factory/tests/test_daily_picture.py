import base64
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daily_picture import asset_label, asset_name, gallery, metered_picture, picture_request, quote
from collect import main, publish_daily_picture
from notes import ModelBudget, meter_body
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
        self.image = b"RIFF\x06\0\0\0WEBPVP"
        self.request = Mock(return_value=({
            "usage": {
                "input_tokens": 105,
                "input_tokens_details": {"text_tokens": 105, "image_tokens": 0},
                "output_tokens": 823,
            },
            "data": [{"b64_json": base64.b64encode(self.image).decode()}],
        }, "req_test"))

    def test_scheduled_path_is_off_and_the_template_never_includes_titles(self):
        result, receipt = metered_picture(self.snapshot, self.budget, "fake", request=self.request)
        self.assertIsNone(result)
        self.assertEqual(receipt["status"], "off")
        self.request.assert_not_called()
        self.save.assert_not_called()
        record, payload = picture_request(self.snapshot, image_model_for_task("factory_picture"))
        self.assertEqual((record["floor"], record["shipped"]), (1, 1))
        self.assertEqual(payload["n"], 1)
        self.assertIn("no lettering", payload["prompt"])
        self.assertNotIn("private title", payload["prompt"])

    def test_measurement_reserves_and_prices_one_image_without_returning_it(self):
        result, receipt = metered_picture(
            self.snapshot, self.budget, "fake", sample=True, request=self.request
        )
        self.assertIsNone(result)
        self.assertEqual(receipt["status"], "measured")
        self.assertEqual(receipt["used_micros"], 25_215)
        self.assertEqual(receipt["month_cost_usd"], 0.025215)
        self.assertLess(receipt["used_micros"], receipt["reserve_micros"])
        self.assertEqual(self.save.call_count, 2)
        tomorrow = datetime(2026, 11, 23, 3, tzinfo=timezone.utc)
        again = ModelBudget(self.budget.body, self.save, now=tomorrow)
        metered_picture(
            {**self.snapshot, "generated_at": tomorrow.isoformat()},
            again, "fake", sample=True, request=self.request,
        )
        self.request.assert_called_once()

    def test_sample_respects_the_old_five_dollar_limit(self):
        meter = self.budget.state()
        meter.update(calls=1, month_micros=4_960_000)
        self.budget = ModelBudget(meter_body("", meter), self.save, now=self.now)
        _, receipt = metered_picture(
            self.snapshot, self.budget, "fake", sample=True, request=self.request
        )
        self.assertEqual(receipt["status"], "over-measurement-budget")
        self.request.assert_not_called()
        self.save.assert_not_called()

    def test_unknown_usage_keeps_the_reserve_and_prevents_another_measurement(self):
        self.request.side_effect = TimeoutError()
        _, receipt = metered_picture(
            self.snapshot, self.budget, "fake", sample=True, request=self.request
        )
        self.assertEqual(receipt["status"], "usage-unavailable")
        reserve = quote(image_model_for_task("factory_picture"))["reserve_micros"]
        self.assertEqual(self.budget.state()["month_micros"], reserve)
        metered_picture(self.snapshot, self.budget, "fake", sample=True, request=self.request)
        self.request.assert_called_once()

    def test_enabled_path_rejects_lettering_then_keeps_yesterdays_date(self):
        picture, receipt = metered_picture(
            self.snapshot, self.budget, "fake", enabled=True, request=self.request,
            prepare=lambda: True, check=lambda image: False,
        )
        self.assertIsNone(picture)
        self.assertEqual(receipt["status"], "picture-unusable")
        earlier = {"day": "2026-11-20", "as_of": "2026-11-21T03:00:00Z", "floor": 2, "shipped": 5}
        asset = {"name": asset_name(earlier), "label": asset_label(earlier), "state": "uploaded"}
        self.assertEqual(gallery([asset], self.now), [earlier])
        metered_picture(
            self.snapshot, self.budget, "fake", enabled=True, request=self.request,
            prepare=lambda: True, check=lambda image: True,
        )
        self.request.assert_called_once()

    def test_gallery_has_seven_pacific_days_and_ignores_incomplete_assets(self):
        records = [
            {"day": f"2026-11-{day}", "as_of": f"2026-11-{day + 1}T03:00:00Z", "floor": day, "shipped": 5}
            for day in range(12, 22)
        ]
        assets = [{"name": asset_name(record), "label": asset_label(record), "state": "uploaded"}
                  for record in records]
        self.assertEqual(gallery(assets + [{**assets[-1], "state": "starter"}], self.now), records[-7:][::-1])

    def test_missing_key_or_unregistered_picture_model_skips_the_provider(self):
        metered_picture(self.snapshot, self.budget, "", sample=True, request=self.request)
        with patch.dict("os.environ", {"LLM_MODEL_FACTORY_PICTURE": "unpriced"}):
            _, receipt = metered_picture(
                self.snapshot, self.budget, "fake", sample=True, request=self.request
            )
        self.assertEqual(receipt["status"], "unpriced")
        self.request.assert_not_called()

    def test_manual_master_measurement_bypasses_collecting_and_publishing(self):
        api = Mock()
        api.metrics.return_value = {"github_api_calls": 2}
        with patch.dict("os.environ", {
            "FACTORY_MEASURE_PICTURE": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
        }), patch("sys.argv", ["collect.py", "--publish", "--output", "/unused"]), patch(
            "collect.authorize_publication"
        ) as authorize, patch("collect.GitHub", return_value=api), patch(
            "collect.read_published", return_value=({"id": 1}, self.snapshot, {})
        ), patch("collect.metered_picture", return_value=(None, {"status": "measured"})) as measure, patch(
            "collect.collect"
        ) as collect_floor, patch("collect.publish_asset") as publish, redirect_stdout(io.StringIO()) as out:
            main()
        authorize.assert_called_once()
        self.assertTrue(measure.call_args.kwargs["sample"])
        collect_floor.assert_not_called()
        publish.assert_not_called()
        self.assertIn('"status": "measured"', out.getvalue())

    def test_upload_is_disabled_with_the_shipped_switch(self):
        api = Mock()
        self.assertIsNone(publish_daily_picture(api, {}, None))
        api.request.assert_not_called()
