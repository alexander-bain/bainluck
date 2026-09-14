"""Guard: the fold says WHAT each dropped row was dropped in favour of (#5532).

THE PAGE THIS EXISTS FOR. `/api/leagues/baseball_mlb`, 2026-09-13, served one
contest twice — `15311666` St. Louis Cardinals 3-1 Chicago White Sox `completed`
with ESPN id 401816926, and `15311614`, the same 3-1 score, still reading `live`
two and a half hours after ESPN closed it. A reader at 390px saw "● Top 9th" and
"Sep 13 FINAL" for one game on one screen.

`_folded_past_rails` in `app/routes/league_futures.py` fixes that by dropping a
row from the upcoming rail when the row that absorbed it is a Final the same
response is already printing. To ask that question it needs the pair — dropped
row and its survivor — and :attr:`FoldResult.dropped_ids` carries only one half.

WHAT EACH TEST HERE IS ACTUALLY DEFENDING. Not "a dict gets populated":

* the map is never re-derivable from `twin_fold_key` equality, which is the
  cheap-looking alternative and is WRONG on exactly the pairs #5918 and #5964
  were written for (`TestItIsNotReconstructibleFromTheKey` — the class that
  carries this file);
* it agrees with `dropped_ids` exactly, so a consumer can never read a survivor
  for a row that is still being served, nor miss one for a row that went
  (`test_its_keys_are_exactly_the_dropped_ids`);
* every loser in a pile-up names the SURVIVOR and not the row above it in the
  ranking (`test_a_four_row_pileup_points_every_loser_at_the_one_survivor`);
* it stays empty when nothing folds, so a consumer's `.get()` cannot quietly
  read a stale pair (`test_a_fold_that_drops_nothing_records_nothing`).
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import fold_twin_events, twin_fold_key

KICKOFF = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads, with `Event.sport` loaded.

    Deliberately not a MagicMock, for the reason the two sibling fold suites
    give: an auto-attribute mock makes every `espn_id` truthy and every
    `sport.key` a soccer key by accident, which would let this whole file pass
    with the soccer pass — and the field under test — deleted.
    """

    def __init__(
        self,
        id,
        home,
        away,
        *,
        sport_key="soccer_spain_la_liga",
        sport_id=7,
        commence_time=KICKOFF,
        home_score=None,
        away_score=None,
        espn_id=None,
        external_id=None,
        commence_time_source="espn",
        sources=None,
    ):
        self.id = id
        self.sport_id = sport_id
        self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.external_id = external_id
        self.commence_time_source = commence_time_source
        self.win_probability_sources = sources


def _celta_pair():
    """The #5918 production pair, read 2026-09-13 14:11Z.

    Two different spellings of one fixture, so the two rows carry DIFFERENT
    strict `twin_fold_key`s and are folded by the soccer name pass rather than
    by the strict key. That is the only reason this file uses a soccer pair.
    """
    finished = _Row(
        15298077,
        "Celta Vigo",
        "Málaga",
        home_score=1,
        away_score=1,
        espn_id="401882885",
        external_id="0eba3c2d3bcf1d1fe4ab3180a3d03152",
        sources={"kalshi": {"value": 0.99}},
    )
    ghost = _Row(
        15310518,
        "RC Celta de Vigo",
        "Malaga CF",
        sources={"statpal_injuries": [{"team": "Celta Vigo"}]},
    )
    return finished, ghost


def _exact_name_pair():
    """A pair the STRICT key folds on its own — the control for the class below.

    Same names, same minute, so `twin_fold_key` is equal on both rows and the
    key-equality shortcut gets the right answer here. Its existence is what
    makes the soccer failure a finding rather than a blanket claim.
    """
    finished = _Row(
        15311666,
        "Chicago White Sox",
        "St. Louis Cardinals",
        sport_key="baseball_mlb",
        sport_id=3,
        home_score=1,
        away_score=3,
        espn_id="401816926",
        sources={"espn": {"value": 0.8}},
    )
    stuck_live = _Row(
        15311614,
        "Chicago White Sox",
        "St. Louis Cardinals",
        sport_key="baseball_mlb",
        sport_id=3,
    )
    return finished, stuck_live


# ── the contract ────────────────────────────────────────────────────────────


class TestTheContract:
    def test_the_dropped_row_names_the_row_that_absorbed_it(self):
        finished, ghost = _celta_pair()

        result = fold_twin_events([finished, ghost])

        assert result.dropped_ids == [15310518]
        assert result.survivor_of == {15310518: 15298077}

    def test_its_keys_are_exactly_the_dropped_ids(self):
        """Both directions. A survivor must never appear as a key — a consumer
        reading `survivor_of[x]` for a row it is still serving would drop a
        contest off the page — and a dropped row must never be missing one,
        which would silently restore today's duplicate."""
        finished, ghost = _celta_pair()
        other_home, other_away = _exact_name_pair()

        result = fold_twin_events([finished, ghost, other_home, other_away])

        assert set(result.survivor_of) == set(result.dropped_ids)
        assert set(result.survivor_of).isdisjoint(set(result.survivor_of.values()))

    def test_a_fold_that_drops_nothing_records_nothing(self):
        """Two genuinely different games. `.get()` on an empty map is the only
        thing standing between a consumer and a stale pair."""
        one = _Row(1, "Celta Vigo", "Málaga")
        two = _Row(2, "Celta Vigo", "Málaga", commence_time=KICKOFF + timedelta(days=1))

        result = fold_twin_events([one, two])

        assert result.dropped_ids == []
        assert result.survivor_of == {}

    def test_a_four_row_pileup_points_every_loser_at_the_one_survivor(self):
        """Not at the row above it in the ranking. A consumer asking "is my
        survivor a Final on this page" must get the row actually being served,
        not an intermediate that was itself dropped."""
        scored = _Row(400, "Celta Vigo", "Málaga", home_score=2, away_score=0)
        rows = [scored] + [
            _Row(i, "RC Celta de Vigo", "Malaga CF") for i in (401, 402, 403)
        ]

        result = fold_twin_events(rows)

        assert [row.id for row in result.events] == [400]
        assert result.survivor_of == {401: 400, 402: 400, 403: 400}

    def test_the_survivor_it_names_is_a_row_the_fold_actually_serves(self):
        """The map is worthless if it can name a row the caller no longer holds."""
        finished, ghost = _celta_pair()
        other_home, other_away = _exact_name_pair()

        result = fold_twin_events([finished, ghost, other_home, other_away])

        served = {row.id for row in result.events}
        assert set(result.survivor_of.values()) <= served


# ── the reason the field exists at all ──────────────────────────────────────


class TestItIsNotReconstructibleFromTheKey:
    """🔴 THE CLASS THIS FILE IS FOR.

    The cheap alternative to this field is for the consumer to collect the
    `twin_fold_key`s of the rows it is serving and ask whether a dropped row's
    own key is among them. That is what `_folded_past_rails` did when #5532
    first landed. It is correct on exact-name pairs and wrong on every pair the
    soccer name pass was written for — and being wrong means the duplicate goes
    back on the page, which is the whole defect.

    Both halves are asserted here, in the same run, so neither is a story.
    """

    def test_the_soccer_pair_folds_although_its_two_keys_differ(self):
        """The precondition, asserted rather than assumed. If this ever stops
        being true the class below is passing for the wrong reason."""
        finished, ghost = _celta_pair()

        assert twin_fold_key(finished) != twin_fold_key(ghost)
        assert fold_twin_events([finished, ghost]).dropped_ids == [15310518]

    def test_the_key_equality_shortcut_gets_this_pair_WRONG(self):
        """The strawman, run as code. This is the re-derivation a consumer
        reaches for; here it fails to connect the dropped row to its survivor."""
        finished, ghost = _celta_pair()

        result = fold_twin_events([finished, ghost])
        served_keys = {twin_fold_key(row) for row in result.events}

        assert twin_fold_key(ghost) not in served_keys, (
            "the shortcut cannot see that 15310518 was absorbed by a row still "
            "on the page — this is the under-reach survivor_of removes"
        )

    def test_survivor_of_gets_the_same_pair_RIGHT(self):
        """The positive form of the assertion above, on the same specimen."""
        finished, ghost = _celta_pair()

        result = fold_twin_events([finished, ghost])

        served = {row.id for row in result.events}
        assert result.survivor_of[ghost.id] in served

    def test_the_shortcut_works_on_an_exact_name_pair_which_is_why_it_survived(self):
        """The control. The shortcut is not broken everywhere — it is broken on
        the soccer pass only, which is exactly why it read as correct when it
        shipped and why this file pins a soccer specimen."""
        finished, stuck_live = _exact_name_pair()

        assert twin_fold_key(finished) == twin_fold_key(stuck_live)
        result = fold_twin_events([finished, stuck_live])
        served_keys = {twin_fold_key(row) for row in result.events}

        assert twin_fold_key(stuck_live) in served_keys
        assert result.survivor_of == {15311614: 15311666}


# ── it must not disturb what the fold already promised ──────────────────────


class TestItChangesNothingElse:
    def test_the_election_and_the_venue_union_are_untouched(self):
        """The field is a record of a decision, never an input to one."""
        finished, ghost = _celta_pair()

        result = fold_twin_events([finished, ghost])

        survivor = result.events[0]
        assert survivor.id == 15298077
        assert survivor.home_score == 1
        assert result.merged_sources[15298077] == {
            "kalshi": {"value": 0.99},
            "statpal_injuries": [{"team": "Celta Vigo"}],
        }

    def test_an_unkeyable_row_is_never_dropped_and_never_recorded(self):
        """A row the fold cannot key survives, so it owes no survivor."""
        keyable = _Row(1, "Celta Vigo", "Málaga", home_score=3)
        nameless = _Row(2, None, "Málaga")

        result = fold_twin_events([keyable, nameless])

        assert {row.id for row in result.events} == {1, 2}
        assert result.survivor_of == {}
