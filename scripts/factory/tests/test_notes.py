from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import instant, iso
from notes import (
    DAILY_CALLS,
    caption_facts,
    fallback,
    make_notes,
    meter_body,
    read_meter,
    valid_answer,
)
from llm_models import REPLACEMENT_MODEL


class ForemanNotes(unittest.TestCase):
    now = instant("2026-11-19T07:57:00Z")
    key = "fake-provider-key"

    def setUp(self):
        self.snapshot = {
            "generated_at": iso(self.now),
            "changes": [
                {
                    "number": 12998,
                    "line": "Website",
                    "station": "Review",
                    "station_since": iso(self.now - timedelta(minutes=40)),
                    "title": "Untrusted title",
                    "author": "Private account",
                    "body": "Raw discussion",
                },
                {"number": 12999, "line": "Server", "station": "Write"},
                {
                    "number": 13000,
                    "line": "Apps",
                    "station": "Live",
                    "live_at": iso(self.now),
                    "testflight_build": 5801,
                },
                {
                    "number": 13001,
                    "line": "Server",
                    "station": "Merge line",
                    "parked": True,
                },
                {
                    "number": 13002,
                    "line": "Server",
                    "station": "Review",
                    "bot_update": True,
                },
            ],
            "stops": [
                {
                    "kind": "hold",
                    "line": "Server",
                    "test": "test_floor",
                    "body": "Private note",
                }
            ],
            "comments": ["raw comment"],
        }
        self.pulls = [
            {"number": 12998, "title": "Untrusted title"},
            {
                "number": 12999,
                "title_trusted": True,
                "title": "Ask Alex about the bench",
            },
            {
                "number": 13000,
                "title_trusted": True,
                "title": "See https://outside.invalid",
            },
        ]
        self.body = "Public event snapshots for /factory."
        self.writes = []
        self.request = Mock(side_effect=self.fake_response)

    def fake_response(self, payload, key):
        self.assertEqual(key, self.key)
        facts = json.loads(payload["messages"][-1]["content"])
        answer = fallback(facts)
        answer["floor"] = "The server dock is on hold."
        return {
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40},
        }

    def save(self, body):
        self.body = body
        self.writes.append(body)

    def run_notes(self, *, key=key, previous=None, now=None):
        with patch.dict("os.environ", {"LLM_MODEL_FACTORY_NOTES": REPLACEMENT_MODEL}):
            return make_notes(
                self.snapshot,
                self.pulls,
                previous or {},
                self.body,
                self.save,
                key,
                now=now or self.now,
                request=self.request,
            )

    def test_facts_include_only_allowed_fields_and_public_trusted_titles(self):
        self.assertEqual(
            caption_facts(self.snapshot, self.pulls),
            {
                "counts": {"on_floor": 2, "live": 1, "parked": 1},
                "stations": {
                    "Bench": {
                        "count": 1,
                        "change": {
                            "number": 12999,
                            "lane": "Server",
                            "title": "Ask the founder about the bench",
                        },
                    },
                    "Inspection": {
                        "count": 1,
                        "change": {
                            "number": 12998,
                            "lane": "Website",
                            "minutes_waiting": 40,
                        },
                    },
                    "Live": {
                        "count": 1,
                        "change": {"number": 13000, "lane": "Apps", "build": 5801},
                    },
                },
                "server_hold": {"active": True, "test": "test_floor"},
                "testflight_builds": [5801],
            },
        )

    def test_validator_rejects_wrong_numbers_prs_markup_and_length(self):
        facts = caption_facts(self.snapshot, self.pulls)
        good = fallback(facts)
        self.assertTrue(valid_answer(good, facts))
        for text in (
            "#1199 has waited 40 minutes at inspection.",
            "#12998 has waited 73 minutes at inspection.",
            "#12999 has waited 40 minutes at inspection.",
            "<b>1 crate at inspection.</b>",
        ):
            bad = deepcopy(good)
            bad["stations"]["Inspection"] = text
            self.assertFalse(valid_answer(bad, facts), text)
        self.assertFalse(
            valid_answer({**good, "floor": "2 crates on the floor. " * 20}, facts)
        )
        self.assertFalse(
            valid_answer(
                {**good, "floor": "Two workers are fixing a broken truck."}, facts
            )
        )

    def test_no_secret_uses_counts_and_never_reserves_or_calls(self):
        note, stats = self.run_notes(key=None)
        self.assertEqual(note["source"], "counts")
        self.assertEqual(note["snapshot_at"], self.snapshot["generated_at"])
        self.assertEqual(
            note["stations"]["Inspection"],
            "#12998 has waited 40 minutes at inspection.",
        )
        self.assertEqual(
            (stats["tokens_in"], stats["tokens_out"], stats["day_cost_usd"]), (0, 0, 0)
        )
        self.assertEqual(self.writes, [])
        self.request.assert_not_called()

    def test_error_or_timeout_falls_back_and_counts_the_attempt(self):
        for error in (
            OSError("provider outage"),
            subprocess.TimeoutExpired("request", 8),
        ):
            with self.subTest(error=type(error)):
                self.body = "Public event snapshots for /factory."
                self.request.side_effect = error
                note, stats = self.run_notes()
                self.assertEqual(note["source"], "counts")
                self.assertEqual(stats["day_calls"], 1)
                self.assertIsNone(stats["tokens_in"])
                self.assertGreater(stats["day_cost_usd"], 0)
                self.assertEqual(read_meter(self.body, self.now)["calls"], 1)

    def test_fake_model_uses_registry_request_and_measured_price(self):
        note, stats = self.run_notes()
        self.assertEqual(note["source"], "model")
        self.assertEqual(note["floor"], "The server dock is on hold.")
        payload, _ = self.request.call_args.args
        self.assertEqual(payload["model"], REPLACEMENT_MODEL)
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertIn("max_completion_tokens", payload)
        self.assertEqual(len(self.writes), 2)
        self.assertLess(
            read_meter(self.writes[1], self.now)["micros"],
            read_meter(self.writes[0], self.now)["micros"],
        )
        self.assertEqual((stats["tokens_in"], stats["tokens_out"]), (100, 40))
        self.assertAlmostEqual(stats["day_cost_usd"], 0.000030, places=6)

    def test_unchanged_or_fewer_than_ten_minutes_never_calls_again(self):
        note, _ = self.run_notes()
        self.assertEqual(
            self.run_notes(previous=note, now=self.now + timedelta(minutes=30))[0][
                "source"
            ],
            "model",
        )
        self.run_notes(now=self.now + timedelta(minutes=30))
        self.request.assert_called_once()
        self.snapshot["changes"][0]["station"] = "Write"
        self.assertEqual(
            self.run_notes(now=self.now + timedelta(minutes=9, seconds=59))[0][
                "source"
            ],
            "counts",
        )
        self.request.assert_called_once()
        self.assertEqual(
            self.run_notes(now=self.now + timedelta(minutes=10))[0]["source"], "model"
        )
        self.assertEqual(self.request.call_count, 2)

    def test_daily_cap_and_pacific_midnight_do_not_reset_spacing(self):
        meter = read_meter(self.body, self.now)
        meter.update(
            calls=DAILY_CALLS - 1,
            last_at=iso(self.now - timedelta(minutes=10)),
            last_facts="1" * 64,
        )
        self.body = meter_body(self.body, meter)
        note, stats = self.run_notes()
        self.assertEqual(stats["day_calls"], 120)
        self.assertEqual(self.run_notes(previous=note)[0]["source"], "counts")
        self.snapshot["changes"][0]["station"] = "Write"
        self.assertEqual(
            self.run_notes(now=self.now + timedelta(minutes=4))[0]["source"], "counts"
        )
        self.request.assert_called_once()
        note, stats = self.run_notes(now=self.now + timedelta(minutes=10))
        self.assertEqual(note["source"], "model")
        self.assertEqual(stats["day_calls"], 1)

    def test_cannot_call_if_the_reservation_cannot_be_saved(self):
        self.save = Mock(side_effect=OSError("release update failed"))
        self.assertEqual(self.run_notes()[0]["source"], "counts")
        self.request.assert_not_called()
