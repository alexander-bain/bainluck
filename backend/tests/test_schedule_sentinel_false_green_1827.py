"""C-SEN-2-R2's four false-green boundary specimens (#1827, queue 388 FF4).

Codex re-certified PR #1827 at its frozen head ``b3a66c37`` and re-BLOCKed it:

    BLOCK — THE ONLY SYSTEM-WIDE GAME-EXISTENCE CHECK STILL CERTIFIES UNVERIFIABLE
    OR CONTRADICTORY IDENTITY AS GREEN AND HIDES ITS OWN PAIRING UNCERTAINTY AT
    THE OPERATOR SURFACE.

All four specimens reproduced unchanged against the committed 90-test suite —
which is the point of this file. **The green suite does not exercise these four
outcomes**, and one committed MLB test explicitly required the first false green.
A boundary the suite never visits is a boundary the suite cannot defend, so each
specimen is written here first, RED, against the detector as it stood.

The stake, stated by Fable when this was queued: *fixing them un-holds #1827, the
only absent-game detector we have.* A sentinel that cannot see an absent game is
the reliability priority's blind spot, so a false GREEN here is worse than no
sentinel — it is a sentinel that reports.

The four, in Codex's own order:

1. **Foreign namespace.** MLB StatsAPI truth is a ``gamePk``; we store it on no
   event column. A row individuated ONLY in an unrelated provider's namespace
   (``statpal_fixture_id``) was counted as ``paired_by_names_foreign_id_space``
   and then vanished from the verdict — green, with nothing dereferenced.
   *The fix is deliberately not N per-pair findings* — the state is constant for
   MLB and a constant is not a signal, which the committed suite was right about.
   It is ONE league-level declaration whose COUNT moves.

2. **Duplicate same-space id.** Two ESPN truth games; both of our rows assert
   ``espn-1``. Stage 0 correctly refuses to pair on a duplicated id, but the rows
   then fell through to name pairing and the SAME ESPN namespace was mislabeled
   foreign — green. Two of our rows claiming one official game id is a defect we
   can prove without inference (cf. #1947: three ``espn_id`` values shared by
   genuinely different games), so it is REAL.

3. **Exact-id wrong date.** An id-paired row starting 24 hours after the official
   truth raised zero ``schedule_wrong_date``: ``pair_events`` hard-coded
   ``mis_dated=False`` on identity pairs, and the comment justifying it claimed
   ``_check_pair`` already raised the finding. It did not. That comment is the
   whole defect — a false claim in a comment is load-bearing when it is the reason
   a check was omitted.

4. **Cockpit laundering.** A league whose verdict is ``green_unverified`` purely
   from pairing uncertainty rendered ``green`` on the operator tile, because the
   cockpit read only ``days_unverified`` (fetch failures) and the pairing-derived
   count was never serialized. The verdict string was preserved and ignored —
   gotcha #145's shape exactly: a green header over an unmeasured run.

Discipline: gotcha #43 (both directions — every specimen has a control asserting
the legitimate case is still NOT flagged) and gotcha #44 (no anchor reads the wall
clock; ``NOW`` is an absolute constant and ``now`` is injected everywhere).
"""

import importlib
from datetime import datetime, timedelta, timezone

ss = importlib.import_module("app.tasks.schedule_sentinel")

NOW = datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc)     # MLB in_season

MLB = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "mlb")
NBA = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "nba")

HOME, AWAY = "Toronto Blue Jays", "Boston Red Sox"
NBA_HOME, NBA_AWAY = "Boston Celtics", "Denver Nuggets"


def _ago(hours):
    return NOW - timedelta(hours=hours)


def _truth(home, away, *, start, state="final", hs=None, aws=None, key="g1",
           raw=None, dh=False, gnum=1):
    return ss.TruthGame(key=key, home=home, away=away, start=start, state=state,
                        raw_state=raw if raw is not None else state.title(),
                        home_score=hs, away_score=aws, doubleheader=dh,
                        game_number=gnum)


def _ours(eid, home, away, *, start, status="completed", hs=None, aws=None,
          espn_id=None, statpal_id=None, external_id=None):
    """Our event, with the FKs healthy — every specimen here is about IDENTITY,
    so nothing else may be the reason a finding fires."""
    return ss.OurEvent(
        id=eid, home_name=home, away_name=away,
        home_team_id=1, away_team_id=2,
        home_fk_name=home, away_fk_name=away,
        status=status, home_score=hs, away_score=aws, commence_time=start,
        espn_id=espn_id, statpal_fixture_id=statpal_id, external_id=external_id,
    )


def _checks(findings):
    return {f["check"] for f in findings}


def _verdict(findings, spec, *, days_unverified=None):
    """The verdict the module would publish for these findings.

    Deliberately routed through the REAL ``classify_findings`` →
    ``schedule_verdict`` pair rather than a bespoke check: the whole class of
    defect here is a fact that is true inside the detector and absent from the
    verdict, so a test that computes the verdict its own way cannot see it."""
    classified = ss.classify_findings(findings, spec, NOW)
    return ss.schedule_verdict(classified, covered=True,
                               days_unverified=days_unverified)


# ---------------------------------------------------------------------------
# SPECIMEN 1 — the foreign namespace
# ---------------------------------------------------------------------------
class TestSpecimen1ForeignNamespace:
    """MLB truth is a ``gamePk`` we hold on no column. Individuation in an
    unrelated namespace is not a dereference of THIS pairing."""

    def test_a_pairing_we_could_not_dereference_is_not_green(self):
        """CODEX SPECIMEN 1, verbatim: `paired=1`, `paired_by_id=0`,
        `paired_by_names_foreign_id_space=1`, zero findings, **green**."""
        truth = [_truth(HOME, AWAY, start=_ago(7), hs=4, aws=2, key="gamePk-1")]
        ours = [_ours(1, HOME, AWAY, start=_ago(7), hs=4, aws=2,
                      statpal_id="foreign-1")]

        findings, stats = ss.reconcile(truth, ours, MLB, NOW)

        assert stats["paired"] == 1, "the specimen must still PAIR — that is its point"
        assert stats["paired_by_id"] == 0
        assert stats["paired_by_names_foreign_id_space"] == 1
        assert _verdict(findings, MLB) != "green", (
            "MLB's gamePk was never dereferenced — nothing in this league was "
            "verified by identity, and the sentinel called it green"
        )
        assert _verdict(findings, MLB) == ss.GREEN_UNVERIFIED

    def test_the_declaration_is_ONE_per_league_not_one_per_pair(self):
        """A constant is not a signal. Ten unverifiable MLB pairs must produce ONE
        statement whose COUNT moves — not ten findings that are always there."""
        truth, ours = [], []
        for i in range(10):
            truth.append(_truth(f"Club {i}", f"Visitor {i}", start=_ago(7),
                                hs=1, aws=0, key=f"gamePk-{i}"))
            ours.append(_ours(i + 1, f"Club {i}", f"Visitor {i}", start=_ago(7),
                              hs=1, aws=0, statpal_id=f"foreign-{i}"))

        findings, stats = ss.reconcile(truth, ours, MLB, NOW)
        declarations = [f for f in findings
                        if f["check"] == "schedule_identity_space_unavailable"]

        assert stats["paired"] == 10
        assert len(declarations) == 1, "one declaration per league, not one per pair"
        assert declarations[0]["pairings_not_dereferenced"] == 10, (
            "the count is the signal — it is what moves when coverage changes"
        )
        assert declarations[0]["kind"] == "UNVERIFIED"

    def test_it_names_the_id_space_it_could_not_reach(self):
        """Ruling 042 obligation 1: if only a label was available, SAY SO in the
        output — and say which identifier was missing."""
        truth = [_truth(HOME, AWAY, start=_ago(7), hs=4, aws=2, key="gamePk-1")]
        ours = [_ours(1, HOME, AWAY, start=_ago(7), hs=4, aws=2,
                      statpal_id="foreign-1")]

        f = next(f for f in ss.reconcile(truth, ours, MLB, NOW)[0]
                 if f["check"] == "schedule_identity_space_unavailable")
        assert f["truth_id_space"] == "mlb_statsapi (not stored)"
        assert f["tier"] == "provenance"
        assert "mlb_statsapi" in f["detail"]

    # --- gotcha #43, the other direction -----------------------------------
    def test_an_empty_slate_is_still_plain_green(self):
        """No pairings means nothing went unverified. An off-season MLB day must
        not be dragged amber by a league-level declaration with nothing behind it."""
        findings, stats = ss.reconcile([], [], MLB, NOW)

        assert stats["paired"] == 0
        assert "schedule_identity_space_unavailable" not in _checks(findings)
        assert _verdict(findings, MLB) == "green"

    def test_a_league_whose_id_space_we_DO_store_is_untouched(self):
        """ESPN truth ↔ our ``espn_id``: dereferenced, verified, green. The
        declaration must not fire for a league that can be checked by identity."""
        truth = [_truth(NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                        key="401816469")]
        ours = [_ours(1, NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                      espn_id="401816469")]

        findings, stats = ss.reconcile(truth, ours, NBA, NOW)

        assert stats["paired_by_id"] == 1
        assert "schedule_identity_space_unavailable" not in _checks(findings)
        assert _verdict(findings, NBA) == "green"


# ---------------------------------------------------------------------------
# SPECIMEN 2 — the duplicated same-space id
# ---------------------------------------------------------------------------
class TestSpecimen2DuplicateSameSpaceId:
    """Two of our rows assert one official game id. Stage 0 refuses to pair on a
    duplicated id — correctly — and the rows then fell through into name pairing
    and were counted as FOREIGN. They are not foreign: they are contradictory."""

    def _fixture(self):
        t1 = _truth(NBA_HOME, NBA_AWAY, start=_ago(12), hs=4, aws=2, key="espn-1")
        t2 = _truth("Miami Heat", "Chicago Bulls", start=_ago(6), hs=1, aws=0,
                    key="espn-2")
        o1 = _ours(1, NBA_HOME, NBA_AWAY, start=_ago(12), hs=4, aws=2,
                   espn_id="espn-1")
        o2 = _ours(2, "Miami Heat", "Chicago Bulls", start=_ago(6), hs=1, aws=0,
                   espn_id="espn-1")   # <-- the SAME id on a different game
        return [t1, t2], [o1, o2]

    def test_two_rows_asserting_one_official_id_is_not_green(self):
        """CODEX SPECIMEN 2, verbatim: `paired=2`, `paired_by_id=0`,
        `foreign_id_space=2`, zero findings, **green**."""
        truth, ours = self._fixture()
        findings, stats = ss.reconcile(truth, ours, NBA, NOW)

        assert stats["paired"] == 2
        assert stats["paired_by_id"] == 0
        assert _verdict(findings, NBA) != "green", (
            "two of our rows claim to be the same official game and the sentinel "
            "called it green"
        )

    def test_a_duplicated_identity_is_REAL_not_merely_unverified(self):
        """This one needs no inference: the rows carry the truth source's OWN id
        space and two of them assert the same value. Provable, so it files."""
        truth, ours = self._fixture()
        findings, _ = ss.reconcile(truth, ours, NBA, NOW)
        classified = ss.classify_findings(findings, NBA, NOW)

        dupes = [f for f in classified["real"]
                 if f["check"] == "schedule_duplicate_identity"]
        assert len(dupes) == 2, "both rows asserting the id are implicated"
        assert {f["event_id"] for f in dupes} == {1, 2}
        assert dupes[0]["kind"] == "DUPLICATE"
        assert dupes[0]["duplicated_id"] == "espn-1"
        assert ss.schedule_verdict(classified, covered=True) == "red"

    def test_the_same_namespace_is_never_reported_as_foreign(self):
        """Codex's exact wording: *the same ESPN namespace is mislabeled as
        foreign*. A row carrying the truth source's own id space is not foreign to
        it, whatever happened to the pairing."""
        truth, ours = self._fixture()
        _, stats = ss.reconcile(truth, ours, NBA, NOW)

        assert stats["paired_by_names_foreign_id_space"] == 0

    def test_an_id_that_contradicts_its_pairing_is_unverified(self):
        """The neighbouring hole in the same class, closed conservatively.

        Our row carries an id in the truth source's OWN space naming a different
        game than the one it name-paired to. Not provably a duplicate, so not RED
        — but it cannot be reported as checked either."""
        truth = [_truth(NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                        key="espn-1")]
        ours = [_ours(1, NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                      espn_id="espn-77")]

        findings, stats = ss.reconcile(truth, ours, NBA, NOW)
        classified = ss.classify_findings(findings, NBA, NOW)

        assert "schedule_identity_conflict" in _checks(findings)
        assert classified["real"] == [], "a conflict is not yet a proven defect"
        assert ss.schedule_verdict(classified, covered=True) == ss.GREEN_UNVERIFIED
        assert stats["paired_by_names_foreign_id_space"] == 0

    # --- gotcha #43, the other direction -----------------------------------
    def test_distinct_ids_on_distinct_games_are_still_green(self):
        """The control. Two rows, two ids, two games — nothing contradicts."""
        t1 = _truth(NBA_HOME, NBA_AWAY, start=_ago(12), hs=4, aws=2, key="espn-1")
        t2 = _truth("Miami Heat", "Chicago Bulls", start=_ago(6), hs=1, aws=0,
                    key="espn-2")
        o1 = _ours(1, NBA_HOME, NBA_AWAY, start=_ago(12), hs=4, aws=2,
                   espn_id="espn-1")
        o2 = _ours(2, "Miami Heat", "Chicago Bulls", start=_ago(6), hs=1, aws=0,
                   espn_id="espn-2")

        findings, stats = ss.reconcile([t1, t2], [o1, o2], NBA, NOW)

        assert stats["paired_by_id"] == 2
        assert "schedule_duplicate_identity" not in _checks(findings)
        assert _verdict(findings, NBA) == "green"

    def test_a_row_with_no_espn_id_at_all_is_foreign_not_contradictory(self):
        """An ESPN-truth league row individuated only in StatPal genuinely IS in a
        foreign id space. The duplicate/conflict findings must not swallow it."""
        truth = [_truth(NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                        key="espn-1")]
        ours = [_ours(1, NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                      statpal_id="fx-1")]

        findings, stats = ss.reconcile(truth, ours, NBA, NOW)

        assert stats["paired_by_names_foreign_id_space"] == 1
        assert "schedule_duplicate_identity" not in _checks(findings)
        assert "schedule_identity_conflict" not in _checks(findings)


# ---------------------------------------------------------------------------
# SPECIMEN 3 — the exact id on the wrong date
# ---------------------------------------------------------------------------
class TestSpecimen3ExactIdWrongDate:
    """``pair_events`` hard-coded ``mis_dated=False`` on identity pairs and the
    comment justifying it said ``_check_pair`` already raised the finding. It did
    not. The date check was disabled for exactly the pairs we trust most."""

    def test_an_id_paired_row_24h_off_raises_wrong_date(self):
        """CODEX SPECIMEN 3, verbatim: `paired_by_id=1`, zero
        `schedule_wrong_date`, zero findings, **green**."""
        truth = [_truth(NBA_HOME, NBA_AWAY, start=_ago(31), hs=4, aws=2,
                        key="espn-9")]
        ours = [_ours(1, NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                      espn_id="espn-9")]

        findings, stats = ss.reconcile(truth, ours, NBA, NOW)

        assert stats["paired_by_id"] == 1, "identity must still pair it — it IS the game"
        assert "schedule_wrong_date" in _checks(findings), (
            "the id proves these are the same game, so a 24h gap is a WRONG DATE "
            "on a correctly-paired row — the one case the check was skipped for"
        )
        wd = next(f for f in findings if f["check"] == "schedule_wrong_date")
        assert wd["event_id"] == 1
        assert round(wd["hours_apart"]) == 24
        assert wd["paired_by"] == "id"

    def test_it_is_a_real_defect_and_turns_the_league_red(self):
        truth = [_truth(NBA_HOME, NBA_AWAY, start=_ago(31), hs=4, aws=2,
                        key="espn-9")]
        ours = [_ours(1, NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                      espn_id="espn-9")]

        classified = ss.classify_findings(
            ss.reconcile(truth, ours, NBA, NOW)[0], NBA, NOW)

        assert any(f["check"] == "schedule_wrong_date" for f in classified["real"])
        assert ss.schedule_verdict(classified, covered=True) == "red"

    # --- gotcha #43, the other direction -----------------------------------
    def test_an_id_paired_row_on_time_is_not_flagged(self):
        """The control that stops this becoming a cry-wolf: an exact-id pair whose
        clocks agree raises nothing."""
        truth = [_truth(NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                        key="espn-9")]
        ours = [_ours(1, NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                      espn_id="espn-9")]

        findings, _ = ss.reconcile(truth, ours, NBA, NOW)
        assert "schedule_wrong_date" not in _checks(findings)

    def test_a_routine_start_time_revision_is_not_a_wrong_date(self):
        """Providers revise start times by a few hours all the time. The bound is
        ``STRICT_PAIR_HOURS`` — the same bar a confident NAME pair must clear, so
        the two stages cannot disagree about what 'the right day' means."""
        truth = [_truth(NBA_HOME, NBA_AWAY, start=_ago(10), hs=4, aws=2,
                        key="espn-9")]
        ours = [_ours(1, NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                      espn_id="espn-9")]

        findings, _ = ss.reconcile(truth, ours, NBA, NOW)
        assert "schedule_wrong_date" not in _checks(findings)

    def test_a_missing_start_time_never_raises_it(self):
        """``hours_apart`` is None when either clock is absent. Absence of a
        measurement is not a measurement of 24h (gotcha #53)."""
        truth = [_truth(NBA_HOME, NBA_AWAY, start=_ago(7), hs=4, aws=2,
                        key="espn-9")]
        ours = [_ours(1, NBA_HOME, NBA_AWAY, start=None, hs=4, aws=2,
                      espn_id="espn-9")]

        findings, _ = ss.reconcile(truth, ours, NBA, NOW)
        assert "schedule_wrong_date" not in _checks(findings)


# ---------------------------------------------------------------------------
# SPECIMEN 4 — the cockpit launders the verdict it was handed
# ---------------------------------------------------------------------------
class TestSpecimen4CockpitLaundering:
    """The module decided ``green_unverified``; the tile rendered ``green``.

    The cockpit read only ``days_unverified`` — the FETCH-failure list — and the
    pairing-derived uncertainty was never serialized into ``per_league`` at all.
    The verdict string survived the trip and was ignored, which is the same defect
    as gotcha #145: a green header over a run that was never measured."""

    def _scorecard(self, league_row):
        return {"scorecard": {"per_league": [league_row],
                              "coverage_label": "1 of 1 leagues have a truth source",
                              "leagues_total": 1},
                "filed": [], "mode": "live"}

    def _row(self, **over):
        row = {"league": "mlb", "verdict": ss.GREEN_UNVERIFIED, "covered": True,
               "truth": "mlb_statsapi", "partial_by_design": False,
               "window": "3d", "truth_games": 5, "our_events": 5,
               "real_defects": 0, "explained": 0, "watch": 0,
               "kind_counts": {}, "days_unverified": [], "unverified": 1}
        row.update(over)
        return row

    def test_the_scorecard_serializes_the_pairing_uncertainty_count(self):
        """It cannot be read if it is never written. The count must reach the
        operator surface, not stop at the verdict string."""
        import app.tasks.schedule_sentinel as mod

        truth = [_truth(HOME, AWAY, start=_ago(7), hs=4, aws=2, key="gamePk-1")]
        ours = [_ours(1, HOME, AWAY, start=_ago(7), hs=4, aws=2,
                      statpal_id="foreign-1")]
        findings, stats = mod.reconcile(truth, ours, MLB, NOW)
        classified = mod.classify_findings(findings, MLB, NOW)

        assert len(classified["unverified"]) >= 1, (
            "the bucket the cockpit needs to see must be non-empty for this league"
        )

    def _tile(self, monkeypatch, row):
        """Drive the REAL cockpit entry point over a faked snapshot read.

        Deliberately not a re-implementation of the status ladder: the defect is
        that the tile's own ladder ignores a field, so a test that re-derives the
        ladder would agree with the bug."""
        from app.routes import admin_cockpit as cockpit

        monkeypatch.setattr(cockpit, "_read_state",
                            lambda key: _FakeRead(self._scorecard(row)))
        return cockpit._schedule_sentinel_group()

    def test_a_green_unverified_league_renders_amber_not_green(self, monkeypatch):
        """CODEX SPECIMEN 4, verbatim: the cockpit preserves the ignored verdict
        string but renders row **green** and overall **green**."""
        group = self._tile(monkeypatch, self._row())

        assert group["per_league"][0]["status"] == "amber", (
            "the module said green_unverified and the tile said green"
        )
        assert group["status"] == "amber"

    def test_the_verdict_string_alone_is_enough_to_stop_green(self, monkeypatch):
        """Belt and braces: even with the count missing (an older cached payload
        written before the count was serialized), the verdict the module published
        is authoritative. A rail that only works once BOTH ends are upgraded is a
        rail that is broken for the whole rollout."""
        row = self._row()
        row.pop("unverified")
        group = self._tile(monkeypatch, row)

        assert group["per_league"][0]["status"] == "amber"
        assert group["status"] == "amber"

    def test_the_count_alone_is_also_enough(self, monkeypatch):
        """The other end of the same rollout: a payload carrying the count but a
        verdict string this cockpit does not recognise."""
        group = self._tile(monkeypatch, self._row(verdict="green", unverified=3))

        assert group["per_league"][0]["status"] == "amber"
        assert group["status"] == "amber"

    # --- gotcha #43, the other direction -----------------------------------
    def test_a_genuinely_green_league_still_renders_green(self, monkeypatch):
        group = self._tile(monkeypatch, self._row(verdict="green", unverified=0))

        assert group["per_league"][0]["status"] == "green"
        assert group["status"] == "green"

    def test_a_red_league_still_outranks_unverified(self, monkeypatch):
        group = self._tile(monkeypatch, self._row(verdict="red", real_defects=2))

        assert group["per_league"][0]["status"] == "red"
        assert group["status"] == "red"

    def test_the_cockpits_copy_of_the_verdict_string_has_not_drifted(self):
        """The cockpit cannot import the sentinel (Celery-in-the-web-path), so it
        carries a literal. A copied constant with no equality test is exactly how a
        tile silently stops matching the verdict it renders."""
        from app.routes import admin_cockpit as cockpit

        assert cockpit._SCHEDULE_GREEN_UNVERIFIED == ss.GREEN_UNVERIFIED


class _FakeRead:
    """The cockpit's snapshot-read contract: ``.degraded``, ``.ok``, ``.value``."""

    degraded = False
    ok = True

    def __init__(self, value):
        self.value = value
