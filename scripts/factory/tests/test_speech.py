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
from speech import assemble_line, lane_facts, make_speech, speech_options


class WorkshopSpeech(unittest.TestCase):
    now = instant("2026-11-20T16:00:00Z")

    def setUp(self):
        self.floor = {
            "generated_at": iso(self.now),
            "changes": [
                {"number": 12945, "builder": "B", "line": "Server", "station": "Test",
                 "last_activity": iso(self.now), "checks_running": True,
                 "check_progress": {"done": 13, "total": 33},
                 "title": "Show scoreboard points in 2.0 (#13124)", "author": "Private account"},
                {"number": 13124, "builder": "E", "line": "Server", "station": "Review",
                 "station_since": iso(self.now - timedelta(minutes=40)), "title": "Fix the dock label"},
                {"number": 13101, "builder": "S", "line": "Website", "station": "Ship",
                 "merged_at": iso(self.now - timedelta(minutes=2)), "title": "Fit the page on a phone"},
            ],
            "raw_discussion": "Private comments",
        }
        self.save = Mock()
        self.budget = ModelBudget("", self.save, now=self.now)
        self.request = Mock(side_effect=self.provider)

    @staticmethod
    def provider(payload, key):
        options = json.loads(payload["messages"][-1]["content"])
        answers = {}
        for lane, details in options.items():
            number, change = next(iter(details["changes"].items()))
            topic = "scoreboard" if "scoreboard" in change["topics"] else change["topics"][0]
            answers[lane] = {
                "number": int(number),
                "clause": f"The {topic} gets a fresh coat",
                "status": change["statuses"][0],
                "mood": details["moods"][0],
            }
        return {
            "choices": [{"message": {"content": json.dumps(answers)}}],
            "usage": {"prompt_tokens": 250, "completion_tokens": 60},
        }

    def test_facts_and_answers_stay_on_their_own_lane(self):
        facts = lane_facts(self.floor)
        self.assertEqual(facts["B"], {
            "checks": {"number": 12945, "running": True, "done": 13, "total": 33},
            "recent_activity": True,
            "titles": {12945: "Show scoreboard points in 2.0 (#13124)"},
        })
        self.assertEqual(facts["E"]["waiting"], {"number": 13124, "station": "Review", "minutes": 40})
        self.assertEqual(facts["S"]["merged"], {"number": 13101, "recent": True})
        options = speech_options(facts["B"])
        answer = {
            "number": 12945, "clause": "The scoreboard gets a fresh coat for 2.0",
            "status": "13 of 33 checks finished on #12945.", "mood": "working",
        }
        self.assertEqual(assemble_line(answer, options), {
            "text": "The scoreboard gets a fresh coat for 2.0. 13 of 33 checks finished on #12945.",
            "mood": "working",
        })
        for change in [
            {"number": 13124}, {"clause": "The scoreboard gets ready for #13124"},
            {"clause": "The scoreboard gets 14 points"}, {"clause": "The scoreboard gets two points"},
            {"clause": "Alex gets a new scoreboard"}, {"clause": "The scoreboard gets a new alice"},
            {"clause": "The dock gets a polish"}, {"clause": "<b>The scoreboard</b>"},
            {"clause": "The scoreboard " + ("gets a polish " * 12).strip()},
            {"status": "33 of 13 checks finished on #12945."},
            {"status": "#12945 merged today."}, {"mood": "celebrating"},
        ]:
            with self.subTest(change=change):
                self.assertIsNone(assemble_line({**answer, **change}, options))

    def test_checks_use_the_model_only_for_changed_lane_facts(self):
        before, stats = make_speech(self.floor, {}, self.budget, "test", request=self.request)
        self.assertEqual(stats["day_calls"], 1)
        self.assertEqual(before["B"]["source"], "model")
        self.assertEqual(before["B"]["text"], "The scoreboard gets a fresh coat. 13 of 33 checks finished on #12945.")
        self.assertEqual(len(self.save.call_args_list), 2)
        content = self.request.call_args.args[0]["messages"][-1]["content"]
        self.assertNotIn("Private", content)
        payload = json.loads(content)
        for lane, number, title in (
            ("B", 12945, "Show scoreboard points in 2.0 (#13124)"),
            ("E", 13124, "Fix the dock label"),
            ("S", 13101, "Fit the page on a phone"),
        ):
            self.assertEqual(payload[lane]["changes"][str(number)]["title"], title)
        copy, _ = make_speech(self.floor, before, self.budget, "test", request=self.request)
        self.assertEqual(copy, before)
        self.request.assert_called_once()

        self.floor["changes"][0]["check_progress"]["done"] = 14
        after, stats = make_speech(self.floor, before, self.budget, "test", request=self.request)
        self.assertEqual(list(json.loads(self.request.call_args.args[0]["messages"][-1]["content"])), ["B"])
        self.assertEqual(after["E"], before["E"])
        self.assertNotEqual(after["B"]["facts_hash"], before["B"]["facts_hash"])
        self.assertEqual(stats["day_calls"], 2)

        self.floor["changes"][0]["title"] = "Keep the scoreboard in view"
        edited, stats = make_speech(self.floor, after, self.budget, "test", request=self.request)
        self.assertEqual(stats["day_calls"], 3)
        self.assertTrue(edited["B"]["text"].startswith("The scoreboard gets a fresh coat."))

    def test_a_bad_model_clause_publishes_only_the_fixed_status(self):
        def reply(payload, key):
            response = self.provider(payload, key)
            answers = json.loads(response["choices"][0]["message"]["content"])
            answers["B"]["clause"] = "The scoreboard gets 300 points"
            response["choices"][0]["message"]["content"] = json.dumps(answers)
            return response

        lines, _ = make_speech(self.floor, {}, self.budget, "test", request=reply)
        self.assertEqual(lines["B"]["source"], "facts")
        self.assertEqual(lines["B"]["text"], "13 of 33 checks finished on #12945.")
        self.assertEqual(lines["E"]["source"], "model")

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
        # The 199 calls include the three picture draws. The last speech call
        # still reaches the shared ceiling of 200.
        meter.update(
            calls=199, notes_calls=119, last_at=iso(self.now), last_facts="1" * 64,
            picture_day=meter["day"], picture_draws=3, picture_retry=False,
        )
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
        cap.update(calls=3, notes_calls=0, month_micros=MONTHLY_COST_MICROS)
        self.budget.body = meter_body("", cap)
        make_speech(self.floor, {}, self.budget, "test", request=self.request)
        self.request.assert_called_once()
