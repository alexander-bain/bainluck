import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collect import floor_changed
from journeys import add_journeys


class CrateJourneys(unittest.TestCase):
    def read(self, t, *crates, previous=None):
        floor = {
            "generated_at": f"2026-11-20T20:{t}:00Z",
            "changes": [
                {"number": 13210, "line": line, "station": station, **flags}
                for line, station, flags in crates
            ],
        }
        add_journeys(floor, previous or {})
        return floor

    def test_remembers_the_last_sightings_and_never_fills_a_skipped_station(self):
        bench = ("Server", "Write", {})
        review = ("Server", "Review", {})
        first = self.read("01", bench)
        same = self.read("05", bench, previous=first)
        self.assertFalse(floor_changed(first, same))
        moved = self.read("10", review, previous=same)
        sent_back = self.read("14", bench, previous=moved)
        self.assertEqual(sent_back["changes"][0]["journey"], [
            {"station": "Write", "first_seen_at": first["generated_at"], "last_seen_at": same["generated_at"]},
            {"station": "Review", "first_seen_at": moved["generated_at"], "last_seen_at": moved["generated_at"]},
            {"station": "Write", "first_seen_at": sent_back["generated_at"]},
        ])
        self.assertNotIn("last_seen_at", first["changes"][0]["journey"][0])

    def test_breaks_on_a_missing_read_or_shelf_and_keeps_delivery_lines_independent(self):
        server = ("Server", "Merge line", {})
        website = ("Website", "Ship", {})
        first = self.read("01", server, website)
        gap = self.read("21", server, website, previous=first)
        shelved = self.read("25", ("Server", "Merge line", {"parked": True}), website, previous=gap)
        returned = self.read("29", server, ("Website", "Live", {}), previous=shelved)
        server_visits, website_visits = [change["journey"] for change in returned["changes"]]
        self.assertEqual(server_visits, [
            {"station": "Merge line", "first_seen_at": first["generated_at"], "last_seen_at": first["generated_at"]},
            {"station": "Merge line", "first_seen_at": gap["generated_at"], "last_seen_at": gap["generated_at"]},
            {"station": "Merge line", "first_seen_at": returned["generated_at"]},
        ])
        self.assertEqual([visit["station"] for visit in website_visits], ["Ship", "Ship", "Live"])
        self.assertEqual(website_visits[1]["last_seen_at"], shelved["generated_at"])

    def test_starts_from_the_old_published_station_when_the_history_field_is_new(self):
        old = {
            "generated_at": "2026-11-20T20:01:00Z",
            "changes": [{"number": 13210, "line": "Apps", "station": "Ship"}],
        }
        live = self.read("07", ("Apps", "Live", {}), previous=old)
        still_live = self.read("58", ("Apps", "Live", {}), previous=live)
        self.assertEqual(still_live["changes"][0]["journey"], [
            {"station": "Ship", "first_seen_at": old["generated_at"], "last_seen_at": old["generated_at"]},
            {"station": "Live", "first_seen_at": live["generated_at"]},
        ])
