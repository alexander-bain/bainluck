"""#12379: a flipped scores feed lands each score on the club it belongs to.

The Odds API scores feed names a game's two clubs as ``home_team`` and
``away_team``, lists each club's score by NAME, and can flip which club it calls
home, as the odds feed does (#8530). The writer read each score off the FEED's
``home_team`` and wrote it to the ROW's home, so after a flip every score sat on
the other club. Three college basketball finals served the loser as the winner:
event 15343426 read San Diego St 66, Colorado 77 for a game San Diego State won
77-66. Its score snapshots flip mid-game, from 32-14 to 17-33.

These drive the real ``_poll_all_odds`` on #7147's SQLite rail and read the row
back through a fresh session.
"""

from datetime import datetime, timedelta, timezone

from tests.test_a_settled_final_survives_the_writer_7147_e2e import (
    _run_pass,
    _snapshots,
    _stored,
)

HOME, AWAY = "San Diego St Aztecs", "Colorado Buffaloes"


def _specimen():
    now = datetime.now(timezone.utc)
    return dict(
        external_id="odds-api-specimen",
        espn_id=None,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=now - timedelta(hours=2),
        status="live",
    )


def _record(*, feed_home, feed_away, scores, completed):
    """One ``get_scores`` record. ``scores`` maps a club's NAME to its score."""
    commence = datetime.now(timezone.utc) - timedelta(hours=2)
    return {
        "id": "odds-api-specimen",
        "completed": completed,
        "commence_time": commence.isoformat().replace("+00:00", "Z"),
        "home_team": feed_home,
        "away_team": feed_away,
        "scores": [{"name": name, "score": str(score)} for name, score in scores.items()],
    }


async def test_a_final_from_a_flipped_feed_keeps_the_winner_on_the_winner():
    payload = [
        _record(
            feed_home=AWAY,  # the feed calls Colorado home; the row says San Diego St
            feed_away=HOME,
            scores={HOME: 77, AWAY: 66},
            completed=True,
        )
    ]
    _result, engine, event_id, _service = await _run_pass(specimen=_specimen(), payload=payload)

    stored = _stored(engine, event_id)
    assert (stored["home_score"], stored["away_score"]) == (77, 66), stored
    assert stored["status"] == "completed"


async def test_a_mid_game_flip_does_not_swap_the_running_score():
    """15343426's shape: the feed flips during play and the score stays put."""
    payload = [
        _record(feed_home=AWAY, feed_away=HOME, scores={HOME: 33, AWAY: 17}, completed=False)
    ]
    _result, engine, event_id, _service = await _run_pass(specimen=_specimen(), payload=payload)

    stored = _stored(engine, event_id)
    assert (stored["home_score"], stored["away_score"]) == (33, 17), stored
    assert _snapshots(engine, event_id)[-1] == (33, 17)


async def test_control_a_feed_in_the_rows_orientation_writes_as_before():
    payload = [
        _record(feed_home=HOME, feed_away=AWAY, scores={HOME: 77, AWAY: 66}, completed=True)
    ]
    _result, engine, event_id, _service = await _run_pass(specimen=_specimen(), payload=payload)

    stored = _stored(engine, event_id)
    assert (stored["home_score"], stored["away_score"]) == (77, 66), stored
    assert stored["status"] == "completed"
