"""#950: golf tournament normalization — de-obfuscate scrambled major names so
Polymarket events merge onto the canonical major card instead of orphaning."""

from app.routes.golf import _normalize_tournament, _fix_scrambled_major


def test_scrambled_us_open_normalizes_to_us_open():
    # Polymarket's "uptspt Open" obfuscation must resolve to the same key as
    # the real name → cross-source merge onto one us_open card.
    assert _normalize_tournament("2026 uptspt Open First Round Leader") == "us_open"
    assert _normalize_tournament("uptspt Open: To Make the Cut") == "us_open"


def test_clean_us_open_names_still_normalize():
    # Kalshi + Polymarket clean names share the us_open key (regression guard).
    assert _normalize_tournament("2026 U.S. Open: Winner Nationality") == "us_open"
    assert _normalize_tournament("PGA Tour: U.S. Open Winner") == "us_open"
    assert _normalize_tournament("US Open Winner") == "us_open"


def test_fix_scrambled_major_is_noop_for_clean_names():
    # Must not mangle normal names (other majors unaffected).
    for nm in ["2026 PGA Championship Winner", "The Masters Top 5", "U.S. Open"]:
        assert _fix_scrambled_major(nm) == nm


def test_fix_scrambled_major_preserves_surrounding_text():
    out = _fix_scrambled_major("2026 uptspt Open First Round Leader")
    assert "U.S. Open" in out and out.startswith("2026 ") and out.endswith("Leader")


def test_senior_open_does_not_fold_into_the_open():
    # L2-90: senior-tour majors contain "Open Championship" and were wrongly
    # folding into The (British) Open's family, contaminating its winner group
    # with a different field (e.g. KXCHAMPTOUR-USSOC "U.S. Senior Open").
    assert _normalize_tournament("U.S. Senior Open Championship Winner") != "the_open"
    assert _normalize_tournament("The Senior Open Championship - Winner") != "the_open"


def test_last_chance_qualifier_does_not_fold_into_the_open():
    # L2-93: The Open's DISTINCT Final Qualifying event ("The Open: Last-Chance
    # Qualifier Winner", KXPGATOUR-THOLCQ26) is a separate field competing for entry,
    # not the championship — it must not surface on the championship's page.
    assert _normalize_tournament("The Open: Last-Chance Qualifier Winner") != "the_open"
    assert _normalize_tournament("The Open Championship Final Qualifying Winner") != "the_open"


def test_real_the_open_still_normalizes():
    # Regression guard: the genuine major must still merge onto one the_open card.
    assert _normalize_tournament("The Open Championship Winner") == "the_open"
    assert _normalize_tournament("The Open Winner") == "the_open"
    assert _normalize_tournament("British Open Winner") == "the_open"
    assert _normalize_tournament("The Open - Top 10") == "the_open"


class TestResolutionDateNormalization:
    """#1077: golf resolution_date carried the Kalshi close-time artifact
    (gotcha #14), which diverges wildly across surfaces for the same tournament
    (The Open 2026: Kalshi Aug-2, detail-header Aug-16, real Jul-16–19). Once a
    DataGolf schedule end_date exists it is the ground truth — _enrich_with_schedule
    normalizes resolution_date to it so the field stops being a countdown footgun."""

    def test_resolution_date_normalized_to_schedule_end_date(self):
        from app.routes.golf import _enrich_with_schedule

        tournaments = [{
            "key": "the_open",
            "name": "The Open Championship",
            # the stale Kalshi close-time artifact (weeks after the real end)
            "resolution_date": "2026-08-02T00:00:00+00:00",
        }]
        schedule_by_key = {
            "the_open_championship": {
                "start_date": "2026-07-16",
                "end_date": "2026-07-19",
                "venue": "Royal Birkdale",
            }
        }
        _enrich_with_schedule(tournaments, schedule_by_key)
        t = tournaments[0]
        assert t["end_date"] == "2026-07-19"
        # resolution_date now agrees with the real tournament end, not Aug-2
        assert t["resolution_date"] == "2026-07-19"

    def test_resolution_date_untouched_when_no_schedule_end_date(self):
        from app.routes.golf import _enrich_with_schedule

        tournaments = [{
            "key": "some_event",
            "name": "Some Event",
            "resolution_date": "2026-08-02T00:00:00+00:00",
        }]
        # no schedule match → nothing to normalize against; leave the field alone
        _enrich_with_schedule(tournaments, {})
        assert tournaments[0]["resolution_date"] == "2026-08-02T00:00:00+00:00"
