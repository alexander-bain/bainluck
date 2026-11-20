from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model import instant, iso
from notes import ModelBudget, MONTHLY_COST_MICROS, meter_body, read_meter
from speech import lane_facts, make_speech, speech_options, valid_line


class WorkshopSpeech(unittest.TestCase):
    now = instant("2026-11-20T16:00:00Z")

    def setUp(self):
        self.floor = {
            "generated_at": iso(self.now),
            "changes": [
                {"number": 12945, "builder": "B", "line": "Server", "station": "Test",
                 "last_activity": iso(self.now), "checks_running": True,
                 "check_progress": {"done": 13, "total": 33},
                 "title": "Private title", "author": "Private account"},
                {"number": 13124, "builder": "E", "line": "Server", "station": "Review",
                 "station_since": iso(self.now - timedelta(minutes=40))},
                {"number": 13101, "builder": "S", "line": "Website", "station": "Ship",
                 "merged_at": iso(self.now - timedelta(minutes=2))},
            ],
            "raw_discussion": "Private comments",
        }
        self.save = Mock()
        self.budget = ModelBudget("", self.save, now=self.now)
        self.request = Mock(side_effect=self.provider)

    @staticmethod
    def provider(payload, key):
        options = json.loads(payload["messages"][-1]["content"])
        return {
            "choices": [{"message": {"content": json.dumps({
                lane: {"text": details["groups"][0][-1], "mood": details["moods"][0]}
                for lane, details in options.items()
            })}}],
            "usage": {"prompt_tokens": 250, "completion_tokens": 60},
        }

    def test_facts_and_answers_stay_on_their_own_lane(self):
        facts = lane_facts(self.floor)
        self.assertEqual(facts["B"], {
            "checks": {"number": 12945, "running": True, "done": 13, "total": 33},
            "recent_activity": True,
        })
        self.assertEqual(facts["E"]["waiting"], {"number": 13124, "station": "Review", "minutes": 40})
        self.assertEqual(facts["S"]["merged"], {"number": 13101, "recent": True})
        options = speech_options(facts["B"])
        self.assertTrue(valid_line({"text": "13 of 33 checks finished on #12945.", "mood": "working"}, options))
        for text, mood in [
            ("13 of 33 checks finished on #13124.", "working"),
            ("33 of 13 checks finished on #12945.", "working"),
            ("#12945 merged today.", "working"),
            ("13 of 33 checks finished on #12945.", "celebrating"),
            ("A person approved #12945.", "working"),
            ("<b>#12945 is in checks.</b>", "working"),
        ]:
            self.assertFalse(valid_line({"text": text, "mood": mood}, options))

    def test_checks_use_the_model_only_for_changed_lane_facts(self):
        before, stats = make_speech(self.floor, {}, self.budget, "test", request=self.request)
        self.assertEqual(stats["day_calls"], 1)
        self.assertEqual(before["B"]["source"], "model")
        self.assertEqual(len(self.save.call_args_list), 2)
        self.assertNotIn("Private", self.request.call_args.args[0]["messages"][-1]["content"])
        copy, _ = make_speech(self.floor, before, self.budget, "test", request=self.request)
        self.assertEqual(copy, before)
        self.request.assert_called_once()

        self.floor["changes"][0]["check_progress"]["done"] = 14
        after, stats = make_speech(self.floor, before, self.budget, "test", request=self.request)
        self.assertEqual(list(json.loads(self.request.call_args.args[0]["messages"][-1]["content"])), ["B"])
        self.assertEqual(after["E"], before["E"])
        self.assertNotEqual(after["B"]["facts_hash"], before["B"]["facts_hash"])
        self.assertEqual(stats["day_calls"], 2)

    def test_no_key_and_failed_call_use_the_plain_situation(self):
        lines, stats = make_speech(self.floor, {}, self.budget, None, request=self.request)
        self.assertEqual(lines["E"]["text"], "#13124 has waited 40 minutes for review.")
        self.assertEqual(lines["E"]["mood"], "waiting")
        self.assertEqual(stats["day_calls"], 0)
        self.request.assert_not_called()
        self.request.side_effect = TimeoutError()
        lines, stats = make_speech(self.floor, {}, self.budget, "test", request=self.request)
        self.assertEqual(stats["day_calls"], 1)
        self.assertEqual(lines["B"]["source"], "facts")
        make_speech(self.floor, lines, self.budget, "test", request=self.request)
        self.request.assert_called_once()

    def test_notes_and_speech_share_a_daily_and_monthly_budget(self):
        meter = read_meter("", self.now)
        meter.update(calls=199, notes_calls=119, last_at=iso(self.now), last_facts="1" * 64)
        self.budget.body = meter_body("", meter)
        _, stats = make_speech(self.floor, {}, self.budget, "test", request=self.request)
        self.assertEqual(stats["day_calls"], 200)
        make_speech(self.floor, {}, self.budget, "test", request=self.request)
        self.request.assert_called_once()
        tomorrow = self.now + timedelta(days=1)
        next_day = read_meter(self.budget.body, tomorrow)
        self.assertEqual(next_day["calls"], 0)
        self.assertGreater(next_day["month_micros"], 0)

        cap = deepcopy(read_meter(self.budget.body, self.now))
        cap.update(calls=1, notes_calls=0, month_micros=MONTHLY_COST_MICROS)
        self.budget.body = meter_body("", cap)
        make_speech(self.floor, {}, self.budget, "test", request=self.request)
        self.request.assert_called_once()
