"""C-ROLLCALL-BUILD-1 — binding of truth fixtures to our rows, and filing.

``_attach`` is where the duplicate hunt actually happens, and it is the part
most able to be quietly wrong in the reassuring direction: a matcher that is too
generous folds a duplicate into its sibling and reports a clean slate. These
tests pin both directions.
"""

from app.tasks.rollcall import _attach, _reconcile


#: The nominal first pitch every helper defaults to, so a test that does not
#: care about time does not have to say so.
T0 = "2026-08-26T22:40:00+00:00"


def _ev(eid, home, away, espn_id=None, commence_time=T0, **flags):
    row = {
        "id": eid,
        "espn_id": espn_id,
        "home_team_name": home,
        "away_team_name": away,
        "commence_time": commence_time,
        "has_kalshi": False,
        "has_polymarket": False,
        "has_espn": False,
        "has_odds_api": False,
    }
    row.update(flags)
    return row


def _fx(label, home, away, espn_id=None, kickoff=T0):
    return {"label": label, "home": home, "away": away, "espn_id": espn_id,
            "kickoff": kickoff}


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

    def test_tomorrows_series_game_is_not_todays_duplicate(self):
        """The defect the first production read found. A three-game series names
        the identical matchup on three days, and the ±18h window holds two of
        them — so a name-only matcher reported MLB as 17 fixtures / 17 duplicated
        out of an ordinary Thursday. Tomorrow's game must fall to nobody."""
        rows = _attach(
            [_fx("LAD @ DET", "Detroit Tigers", "Los Angeles Dodgers",
                 kickoff="2026-08-28T22:40:00+00:00")],
            [
                _ev(15290804, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T22:40:00+00:00"),
                _ev(15290969, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-29T17:10:00+00:00"),
            ],
        )
        assert rows[0].event_ids == [15290804]
        assert rows[0].matched_one is True

    def test_a_real_duplicate_on_the_same_day_is_still_caught(self):
        """The other direction, and the reason the fix is a time bound rather
        than a first-match-wins: two rows for the SAME start time are the
        duplicate this sentinel exists to find, and both must be claimed."""
        rows = _attach(
            [_fx("BOS @ NYY", "New York Yankees", "Boston Red Sox",
                 kickoff="2026-08-28T23:15:00+00:00")],
            [
                _ev(1, "New York Yankees", "Boston Red Sox",
                    commence_time="2026-08-28T23:15:00+00:00"),
                _ev(2, "New York Yankees", "Boston Red Sox",
                    commence_time="2026-08-28T23:20:00+00:00"),
            ],
        )
        assert rows[0].event_ids == [1, 2]
        assert rows[0].matched_one is False

    def test_a_doubleheader_splits_across_its_two_fixtures(self):
        """Nearest-in-time, not first-match-wins: game 2 belongs to fixture 2."""
        rows = _attach(
            [
                _fx("g1", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T17:10:00+00:00"),
                _fx("g2", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T22:40:00+00:00"),
            ],
            [
                _ev(2, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T22:40:00+00:00"),
                _ev(1, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T17:10:00+00:00"),
            ],
        )
        assert rows[0].event_ids == [1]
        assert rows[1].event_ids == [2]

    def test_a_delayed_first_game_does_not_hand_itself_to_the_second(self):
        """CERT-434's BLOCK specimen, verbatim.

        Same teams at 17:00 and 20:00; game 1 is pushed to 19:00 by rain. Under
        independent nearest-fixture picks BOTH rows chose the 20:00 fixture —
        19:00 is one hour from it and two from its own — so the sentinel filed
        `g1 missing` and `g2 dupes=2` about two perfectly healthy games. The
        assignment is one-to-one: the pairing that minimises TOTAL skew
        (2.0 + 0.0) beats the one that minimises each row's own (1.0 + 3.0).
        """
        rows = _attach(
            [
                _fx("g1", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T17:00:00+00:00"),
                _fx("g2", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T20:00:00+00:00"),
            ],
            [
                _ev(1, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T19:00:00+00:00"),
                _ev(2, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T20:00:00+00:00"),
            ],
        )
        assert [r.event_ids for r in rows] == [[1], [2]]
        assert [r.ambiguous for r in rows] == [False, False]

    def test_the_same_specimen_in_the_other_input_order(self):
        """Order-independence is the property, not the specimen. A matcher that
        happens to be right when the delayed row is listed first and wrong when
        it is listed second is still the bug."""
        rows = _attach(
            [
                _fx("g1", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T17:00:00+00:00"),
                _fx("g2", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T20:00:00+00:00"),
            ],
            [
                _ev(2, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T20:00:00+00:00"),
                _ev(1, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T19:00:00+00:00"),
            ],
        )
        assert [r.event_ids for r in rows] == [[1], [2]]

    def test_an_unbreakable_tie_is_refused_not_decided_by_list_order(self):
        """Both rows sit exactly between both fixtures, so the two pairings cost
        the same and nothing in the data prefers either. Deciding it by list
        order would be a coin flip presented as a finding, so the group is
        marked ambiguous — and an ambiguous fixture is graded by nobody."""
        rows = _attach(
            [
                _fx("g1", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T17:00:00+00:00"),
                _fx("g2", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T21:00:00+00:00"),
            ],
            [
                _ev(1, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T19:00:00+00:00"),
                _ev(2, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T19:00:00+00:00"),
            ],
        )
        assert [r.ambiguous for r in rows] == [True, True]

    def test_one_row_equidistant_from_two_fixtures_is_refused(self):
        """The same refusal with the cardinalities reversed: one event, two
        fixtures, no reason to prefer either. Guessing produces a confident
        `missing` on whichever fixture lost the coin flip."""
        rows = _attach(
            [
                _fx("g1", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T17:00:00+00:00"),
                _fx("g2", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T21:00:00+00:00"),
            ],
            [_ev(1, "Detroit Tigers", "Los Angeles Dodgers",
                 commence_time="2026-08-28T19:00:00+00:00")],
        )
        assert [r.ambiguous for r in rows] == [True, True]

    def test_a_duplicate_inside_a_doubleheader_is_still_caught(self):
        """The control that keeps the fix from being a cover-up: three rows for
        two fixtures. Two of them pair off; the third has nowhere one-to-one to
        go and lands on its nearest fixture as the visible duplicate it is."""
        rows = _attach(
            [
                _fx("g1", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T17:00:00+00:00"),
                _fx("g2", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T20:00:00+00:00"),
            ],
            [
                _ev(1, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T17:00:00+00:00"),
                _ev(2, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T20:00:00+00:00"),
                _ev(3, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T20:05:00+00:00"),
            ],
        )
        assert [r.event_ids for r in rows] == [[1], [2, 3]]
        assert [r.ambiguous for r in rows] == [False, False]

    def test_a_delayed_game_beside_an_id_stamped_sibling_still_finds_its_own(self):
        """The occupied-fixture case. g2 is already settled by its provider id,
        so the delayed id-less row must take the EMPTY fixture rather than pile
        onto the stamped one just because it is nearer in time."""
        rows = _attach(
            [
                _fx("g1", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T17:00:00+00:00"),
                _fx("g2", "Detroit Tigers", "Los Angeles Dodgers",
                    espn_id="401816706", kickoff="2026-08-28T20:00:00+00:00"),
            ],
            [
                _ev(1, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T19:00:00+00:00"),
                _ev(2, "Detroit Tigers", "Los Angeles Dodgers",
                    espn_id="401816706", commence_time="2026-08-28T20:00:00+00:00"),
            ],
        )
        assert [r.event_ids for r in rows] == [[1], [2]]

    def test_unrelated_matchups_never_compete_for_each_others_fixtures(self):
        """The grouping is per matchup, so a busy slate cannot let one game's
        delay perturb another game's binding."""
        rows = _attach(
            [
                _fx("a", "Detroit Tigers", "Los Angeles Dodgers",
                    kickoff="2026-08-28T17:00:00+00:00"),
                _fx("b", "New York Yankees", "Boston Red Sox",
                    kickoff="2026-08-28T17:30:00+00:00"),
            ],
            [
                _ev(1, "New York Yankees", "Boston Red Sox",
                    commence_time="2026-08-28T17:30:00+00:00"),
                _ev(2, "Detroit Tigers", "Los Angeles Dodgers",
                    commence_time="2026-08-28T19:00:00+00:00"),
            ],
        )
        assert [r.event_ids for r in rows] == [[2], [1]]
        assert [r.ambiguous for r in rows] == [False, False]

    def test_a_rain_delayed_start_still_binds(self):
        """Six hours of slack, so a provisional or delayed start is not a
        fabricated `missing`."""
        rows = _attach(
            [_fx("BOS @ MIA", "Miami Marlins", "Boston Red Sox",
                 kickoff="2026-08-28T22:40:00+00:00")],
            [_ev(1, "Miami Marlins", "Boston Red Sox",
                 commence_time="2026-08-29T01:55:00+00:00")],
        )
        assert rows[0].event_ids == [1]

    def test_an_untimed_event_is_never_name_matched(self):
        """Declining beats guessing — an event whose start we cannot parse
        cannot be told apart from tomorrow's game in the same series."""
        rows = _attach(
            [_fx("BOS @ MIA", "Miami Marlins", "Boston Red Sox")],
            [_ev(1, "Miami Marlins", "Boston Red Sox", commence_time=None)],
        )
        assert rows[0].event_ids == []

    def test_a_wrong_provider_id_reads_as_mis_stamped_not_missing(self):
        """The second defect the first production read found. BOS @ NYY
        2026-08-29 17:05Z: event 14877917 is the right game at the right time
        stamped `401815659` while the board says `401874913`. "Never created"
        and "created with the wrong id" want opposite repairs, so they must not
        share a word."""
        rows = _attach(
            [_fx("BOS @ NYY", "New York Yankees", "Boston Red Sox",
                 espn_id="401874913", kickoff="2026-08-29T17:05:00+00:00")],
            [_ev(14877917, "New York Yankees", "Boston Red Sox",
                 espn_id="401815659", commence_time="2026-08-29T17:05:00+00:00")],
        )
        assert rows[0].event_ids == []
        assert rows[0].mis_stamped is True
        assert rows[0].id_conflicts == [
            {"event_id": 14877917, "espn_id": "401815659"}
        ]

    def test_a_genuinely_absent_game_stays_missing(self):
        """The other direction — no row of any stamp names this fixture."""
        rows = _attach(
            [_fx("TOR @ PHX", "Phoenix Mercury", "Toronto Tempo",
                 espn_id="401999001")],
            [_ev(1, "New York Liberty", "Chicago Sky", espn_id="401999002")],
        )
        assert rows[0].event_ids == []
        assert rows[0].mis_stamped is False
        assert rows[0].id_conflicts == []

    def test_tomorrows_mis_stamped_sibling_is_not_a_conflict(self):
        """The conflict search is bounded in time by the same rule the name pass
        is, or every series would report a stamp defect it does not have."""
        rows = _attach(
            [_fx("LAD @ DET", "Detroit Tigers", "Los Angeles Dodgers",
                 espn_id="401816706", kickoff="2026-08-28T22:40:00+00:00")],
            [_ev(9, "Detroit Tigers", "Los Angeles Dodgers", espn_id="401816721",
                 commence_time="2026-08-29T17:10:00+00:00")],
        )
        assert rows[0].mis_stamped is False

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

    def test_a_wholly_ambiguous_league_neither_files_nor_closes(self, monkeypatch):
        """Same argument as `truth_unavailable`, and this is the direction that
        bites. A slate the binder refused end to end is not evidence of health,
        so it must not reach the rail at all — otherwise `red=False` sends it
        down the green path and CLOSES an open roll-call issue with a comment
        saying the league is clean on a day nothing was graded."""
        calls = []
        monkeypatch.setattr(
            "app.tasks.sentinel_filing.fetch_open_alert_issues", lambda: []
        )
        monkeypatch.setattr(
            "app.tasks.sentinel_filing.reconcile_issue",
            lambda **kw: calls.append(kw) or {"action": "resolved"},
        )
        out = _reconcile("2026-08-26", [
            {"league": "mlb", "verdict": "ambiguous", "offenders": [],
             "events_external": 2, "graded": 0, "ambiguous": 2, "clean": 0,
             "per_source": {}, "axiom_sources": ["kalshi"], "truth_url": "u"},
        ])
        assert calls == []
        assert out[0]["action"] == "skipped_ambiguous"

    def test_a_partly_refused_league_still_reconciles_on_what_it_graded(self, monkeypatch):
        """The refusal is per fixture, not a mute switch: a league with one
        refused fixture and four clean ones is still observed and still speaks."""
        calls = []
        monkeypatch.setattr(
            "app.tasks.sentinel_filing.fetch_open_alert_issues", lambda: []
        )
        monkeypatch.setattr(
            "app.tasks.sentinel_filing.reconcile_issue",
            lambda **kw: calls.append(kw) or {"action": "resolved"},
        )
        _reconcile("2026-08-26", [
            {"league": "mlb", "verdict": "pass", "offenders": [],
             "events_external": 5, "graded": 4, "ambiguous": 1, "clean": 4,
             "per_source": {}, "axiom_sources": ["kalshi"], "truth_url": "u"},
        ])
        assert len(calls) == 1 and calls[0]["red"] is False
        # The green comment must not claim five fixtures were verified.
        assert "4/4 graded fixtures" in calls[0]["green_comment"]
        assert "1 further fixture(s) refused" in calls[0]["green_comment"]

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
