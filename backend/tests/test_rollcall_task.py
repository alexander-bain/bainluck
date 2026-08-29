"""C-ROLLCALL-BUILD-1 — binding of truth fixtures to our rows, and filing.

``_attach`` is where the duplicate hunt actually happens, and it is the part
most able to be quietly wrong in the reassuring direction: a matcher that is too
generous folds a duplicate into its sibling and reports a clean slate. These
tests pin both directions.
"""

from app.tasks.rollcall import _attach, _reconcile


def _ev(eid, home, away, espn_id=None, **flags):
    row = {
        "id": eid,
        "espn_id": espn_id,
        "home_team_name": home,
        "away_team_name": away,
        "has_kalshi": False,
        "has_polymarket": False,
        "has_espn": False,
        "has_odds_api": False,
    }
    row.update(flags)
    return row


def _fx(label, home, away, espn_id=None):
    return {"label": label, "home": home, "away": away, "espn_id": espn_id,
            "kickoff": "2026-08-26T22:40:00+00:00"}


class TestAttach:
    def test_one_event_one_fixture(self):
        rows = _attach(
            [_fx("BOS @ MIA", "Miami Marlins", "Boston Red Sox", "401581234")],
            [_ev(15291944, "Miami Marlins", "Boston Red Sox", espn_id="401581234",
                 has_kalshi=True, has_espn=True)],
        )
        assert len(rows) == 1
        assert rows[0].event_ids == [15291944]
        assert rows[0].sources == {
            "kalshi": True, "polymarket": False, "espn": True, "odds_api": False
        }

    def test_an_unstamped_duplicate_is_found_not_absorbed(self):
        """The id-anchored row is claimed first; the id-less sibling is then
        found by name and counted as the SECOND claim. That is the whole point —
        a duplicate must be visible, not quietly merged away."""
        rows = _attach(
            [_fx("BOS @ MIA", "Miami Marlins", "Boston Red Sox", "401581234")],
            [
                _ev(15291944, "Miami Marlins", "Boston Red Sox", espn_id="401581234"),
                _ev(15242101, "Miami Marlins", "Boston Red Sox"),
            ],
        )
        assert rows[0].event_ids == [15291944, 15242101]
        assert rows[0].matched_one is False

    def test_an_id_stamped_row_is_never_stolen_by_a_name_collision(self):
        """Two fixtures, one name-alike row each. The id pass runs first, so the
        stamped row goes to its own fixture rather than to whichever fixture the
        name pass reached first."""
        rows = _attach(
            [
                _fx("A", "Miami Marlins", "Boston Red Sox", "401581234"),
                _fx("B", "Miami Marlins", "Boston Red Sox", "401581999"),
            ],
            [
                _ev(1, "Miami Marlins", "Boston Red Sox", espn_id="401581234"),
                _ev(2, "Miami Marlins", "Boston Red Sox", espn_id="401581999"),
            ],
        )
        assert rows[0].event_ids == [1]
        assert rows[1].event_ids == [2]

    def test_a_fixture_with_no_event_is_missing(self):
        rows = _attach(
            [_fx("BOS @ MIA", "Miami Marlins", "Boston Red Sox", "401581234")],
            [_ev(9, "New York Mets", "Atlanta Braves")],
        )
        assert rows[0].event_ids == []
        assert rows[0].sources == {}

    def test_sources_are_not_read_off_an_ambiguous_match(self):
        """With two claimants the linkage question has no subject. Reading the
        first one's flags would report a linked fixture that does not exist."""
        rows = _attach(
            [_fx("BOS @ MIA", "Miami Marlins", "Boston Red Sox")],
            [
                _ev(1, "Miami Marlins", "Boston Red Sox", has_kalshi=True,
                    has_polymarket=True, has_espn=True, has_odds_api=True),
                _ev(2, "Miami Marlins", "Boston Red Sox"),
            ],
        )
        assert rows[0].sources == {}
        assert rows[0].missing_sources(("kalshi", "polymarket", "espn", "odds_api")) == [
            "kalshi", "polymarket", "espn", "odds_api"
        ]

    def test_an_unrelated_same_city_game_is_not_claimed(self):
        rows = _attach(
            [_fx("NYY @ BOS", "Boston Red Sox", "New York Yankees")],
            [_ev(5, "Boston Red Sox", "New York Mets")],
        )
        assert rows[0].event_ids == []

    def test_golf_fixtures_bind_on_the_event_name(self):
        """A golf fixture has no away side. ``fixture_matches`` requires both
        sides, so a tournament never binds by name — it is reported missing
        unless an id-anchored row exists. That is the honest answer today and it
        is asserted so nobody later reads a golf zero as a matcher bug."""
        rows = _attach(
            [{"label": "The Open", "home": "The Open Championship", "away": "",
              "espn_id": None, "datagolf_event_id": "100", "kickoff": "2026-07-16"}],
            [_ev(7, "The Open Championship", "")],
        )
        assert rows[0].event_ids == []
        assert rows[0].truth_ref == "100"


class TestFiling:
    def test_a_truth_unavailable_league_neither_files_nor_closes(self, monkeypatch):
        """No observation means no evidence in EITHER direction. Closing an open
        issue because a league went dark would be the worst possible read."""
        calls = []
        monkeypatch.setattr(
            "app.tasks.sentinel_filing.fetch_open_alert_issues", lambda: []
        )
        monkeypatch.setattr(
            "app.tasks.sentinel_filing.reconcile_issue",
            lambda **kw: calls.append(kw) or {"action": "filed"},
        )
        out = _reconcile("2026-08-26", [
            {"league": "nba", "verdict": "truth_unavailable", "offenders": []},
        ])
        assert calls == []
        assert out[0]["action"] == "skipped_truth_unavailable"

    def test_a_red_league_files_and_a_clean_one_resolves(self, monkeypatch):
        seen = []
        monkeypatch.setattr(
            "app.tasks.sentinel_filing.fetch_open_alert_issues", lambda: []
        )
        monkeypatch.setattr(
            "app.tasks.sentinel_filing.reconcile_issue",
            lambda **kw: seen.append((kw["marker_key"], kw["red"])) or {"action": "ok"},
        )
        _reconcile("2026-08-26", [
            {"league": "mlb", "verdict": "red", "offenders": [
                {"fixture": "A @ B", "gaps": ["dupes=2"], "event_ids": [1, 2]}],
             "events_external": 1, "clean": 0, "per_source": {},
             "axiom_sources": ["kalshi"], "truth_url": "u"},
            {"league": "nhl", "verdict": "pass", "offenders": [],
             "events_external": 3, "clean": 3, "per_source": {},
             "axiom_sources": ["kalshi"], "truth_url": "u"},
        ])
        assert seen == [("rollcall-fingerprint", True), ("rollcall-fingerprint", False)]

    def test_one_leagues_filing_failure_does_not_sink_the_others(self, monkeypatch):
        """gotcha #42 — one bad item must never wipe the pass."""
        def _boom(**kw):
            if kw["title"].startswith("[rollcall] MLB"):
                raise RuntimeError("github 502")
            return {"action": "ok"}

        monkeypatch.setattr(
            "app.tasks.sentinel_filing.fetch_open_alert_issues", lambda: []
        )
        monkeypatch.setattr("app.tasks.sentinel_filing.reconcile_issue", _boom)
        out = _reconcile("2026-08-26", [
            {"league": "mlb", "verdict": "red", "offenders": [
                {"fixture": "A @ B", "gaps": ["missing"], "event_ids": []}],
             "events_external": 1, "clean": 0, "per_source": {},
             "axiom_sources": ["kalshi"], "truth_url": "u"},
            {"league": "nhl", "verdict": "red", "offenders": [
                {"fixture": "C @ D", "gaps": ["missing"], "event_ids": []}],
             "events_external": 1, "clean": 0, "per_source": {},
             "axiom_sources": ["kalshi"], "truth_url": "u"},
        ])
        assert out[0]["action"] == "error"
        assert out[1]["action"] == "ok"
