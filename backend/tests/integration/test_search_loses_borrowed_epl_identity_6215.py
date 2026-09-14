"""#6215 — the reader's half, driven through `GET /api/events/search`.

CERT-2877's required test. The unit file
`tests/test_espn_identity_is_not_borrowed_6215.py` proves the WRITER stops
minting a borrowed identity; it cannot prove that a reader searching
"Deportivo" stops being handed one, because the ~1,010 rows already written are
not reachable by any code path — `_cleanup_bad_espn_matches` loads teams WITH an
`espn_id` and these no longer have one. Only the repair script reaches them, so
only a test that drives the repair's own decision and field-clear and then
serves the row through the real route can say the reader's half is paid.

WHAT A READER SEES TODAY (production, 2026-09-14, search `q=Deportivo`):

    {"id": 4551, "name": "Deportivo Achuapa",       "abbreviation": "ARS",
     "record": "19-7-3", "sport_key": "soccer_epl"}
    {"id": 4504, "name": "Deportivo Maipu",         "abbreviation": "CHE",
     "record": "12-9-7", "sport_key": "soccer_epl"}
    {"id": 4229, "name": "Deportivo Universitario", "abbreviation": "MNC",
     "record": "18-5-5", "sport_key": "soccer_epl"}

🔴 **WHAT IS ASSERTED AND WHAT IS NOT.** The badge and the record go. The
`· EPL` caption does NOT, and `TestTheCaptionIsNotClaimed` pins that as a fact
rather than leaving it to be discovered: `sport_key` is `teams.sport_id`, which
came from `event.sport_id`, and `soccer_epl` holds 2,249 events of which 2,104
predate June with no ESPN id — a foreign-fixtures-under-EPL cohort that is a
larger, separate defect. For 740 of the 1,077 rows there is no same-named row
under any other sport to derive the right one from. A test that quietly asserted
the caption changed would be asserting something no repair in this ship does.

NON-VACUITY. Every arm runs twice — once over the row as production stores it,
once over the same row after the repair's own clear — and the BEFORE arm asserts
the borrowed values ARE served. If the seed stops reaching the page, the
"no longer served" assertions would pass on an empty payload, and
`TestTheSeedIsReal` is what stops that reading as a pass.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS
from scripts.repair_6215_borrowed_espn_identity import (
    identity_is_borrowed,
    wrong_app_refusal,
)

SEARCH = "/api/events/search"


def _borrowed_team_row():
    """Production row 4551, transcribed rather than invented."""
    return SimpleNamespace(
        id=4551,
        name="Deportivo Achuapa",
        slug="deportivo-achuapa",
        abbreviation="ARS",
        sport_id=1298,
        logo_url_small=None,
        logo_url_large=None,
        primary_color=None,
        secondary_color=None,
        location="Arsenal",
        current_record="19-7-3",
        sport_key="soccer_epl",
        alternate_names=None,
        team_rank=0.9,
    )


def _repaired(row):
    """The same row after `repair_6215_borrowed_espn_identity.py --apply`.

    Applies the repair's OWN field list rather than a hand-written one, so a
    field added to or dropped from `ESPN_SOURCED_IDENTITY_FIELDS` moves this
    fixture with it and cannot leave the test asserting a stale contract.
    """
    assert identity_is_borrowed(row.name, row.location, row.alternate_names), (
        "the fixture is not in the population the repair selects — this test "
        "would be measuring a row the script never touches"
    )
    repaired = SimpleNamespace(**vars(row))
    for field in ESPN_SOURCED_IDENTITY_FIELDS:
        if hasattr(repaired, field):
            setattr(repaired, field, None)
    return repaired


def _empty_result(rows=()):
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    result.scalar.return_value = 0
    result.scalar_one_or_none.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    return result


def _db_serving(team_row):
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        sql = str(stmt)
        upper = sql.upper()
        result = _empty_result()
        if " teams" in sql and "SELECT" in upper:
            result.all.return_value = [team_row]
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


async def _client_for(session, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def before_client(monkeypatch):
    async for ac in _client_for(_db_serving(_borrowed_team_row()), monkeypatch):
        yield ac


@pytest.fixture
async def after_client(monkeypatch):
    async for ac in _client_for(
        _db_serving(_repaired(_borrowed_team_row())), monkeypatch
    ):
        yield ac


async def _teams(client):
    body = (await client.get(f"{SEARCH}?q=Deportivo")).json()
    return body.get("teams", [])


class TestTheSeedIsReal:
    """Without this, "no longer served" passes on an empty payload."""

    async def test_the_club_reaches_the_page_before_and_after(
        self, before_client, after_client
    ):
        for label, client in (("before", before_client), ("after", after_client)):
            names = [t.get("name") for t in await _teams(client)]
            assert "Deportivo Achuapa" in names, (
                f"the seeded club did not reach the page ({label}) — every "
                "assertion in this file would be vacuous"
            )


class TestTheBorrowedIdentityIsServedToday:
    """The defect, through the route, before anything is repaired."""

    async def test_the_reader_is_handed_arsenals_badge_and_record(
        self, before_client
    ):
        row = next(
            t for t in await _teams(before_client)
            if t.get("name") == "Deportivo Achuapa"
        )
        assert row.get("abbreviation") == "ARS"
        assert row.get("record") == "19-7-3"


class TestTheRepairIsWhatTheReaderGets:
    async def test_deportivo_search_loses_borrowed_epl_identity_6215(
        self, after_client
    ):
        """CERT-2877's required test, by name.

        A Guatemalan club stops being handed to a reader wearing Arsenal's
        initials and Arsenal's record.
        """
        rows = await _teams(after_client)
        row = next(t for t in rows if t.get("name") == "Deportivo Achuapa")

        assert row.get("abbreviation") is None, (
            f"still wearing a borrowed badge: {row.get('abbreviation')!r}"
        )
        assert row.get("record") is None, (
            f"still wearing a borrowed record: {row.get('record')!r}"
        )
        assert row.get("logo") is None

        served = str(rows)
        assert "ARS" not in served
        assert "19-7-3" not in served


class TestTheCaptionIsNotClaimed:
    """Stated as a fact, because a silent gap is how a false ship survives."""

    async def test_the_epl_caption_survives_the_repair(self, after_client):
        row = next(
            t for t in await _teams(after_client)
            if t.get("name") == "Deportivo Achuapa"
        )
        assert row.get("sport_key") == "soccer_epl", (
            "if this ever flips, the events cohort was repaired too and this "
            "test should be replaced by one asserting the right competition — "
            "not deleted"
        )

    def test_the_repair_does_not_touch_the_sport(self):
        assert "sport_id" not in ESPN_SOURCED_IDENTITY_FIELDS


class TestTheRepairSelectsTheRightRows:
    """The population predicate, on production values."""

    @pytest.mark.parametrize(
        "name, location, aliases",
        [
            ("Deportivo Achuapa", "Arsenal", None),
            ("Fluminense", "Arsenal", None),
            ("Marist Red Foxes", "Ohio State", None),
            ("Butler Bulldogs", "Oklahoma State", None),
        ],
    )
    def test_a_borrowed_row_is_selected(self, name, location, aliases):
        assert identity_is_borrowed(name, location, aliases) is True

    @pytest.mark.parametrize(
        "name, location",
        [
            ("Arsenal", "Arsenal"),
            ("Leeds United", "Leeds United"),
            # The mascot form. `names_match` alone calls all four of these
            # borrowed, which is what the prefix rule in `location_corresponds`
            # exists for — 63 rows turn on it and every one reads correct.
            ("Evansville Purple Aces", "Evansville"),
            ("Duke Blue Devils", "Duke"),
            ("Oregon Ducks", "Oregon"),
            ("Texas A&M Aggies", "Texas A&M"),
        ],
    )
    def test_a_legitimate_row_is_left_alone(self, name, location):
        assert identity_is_borrowed(name, location) is False

    def test_a_leading_word_is_required_not_a_substring(self):
        """A shared trailing word is not a location.

        ESPN composes `display_name` as location + name, so a real location is a
        LEADING run of whole words. `"Eastern Michigan Eagles"` does contain
        `"Michigan"` — substring containment would spare it, and the prefix rule
        does not.

        The mirror case is NOT asserted here and the reason is worth the line:
        ANY two-token name sharing one token with a two-token location — say
        `("Michigan Eagles", "Eastern Michigan")` — scores token overlap 0.5 and
        `names_match` accepts it before the prefix rule is ever consulted. That
        is the matcher's own tradeoff, written down in its docstring ("we accept
        this tradeoff"), and asserting against it here would pin someone else's
        decision as if it were this script's. Measured while writing this file,
        not assumed.
        """
        assert identity_is_borrowed("Eastern Michigan Eagles", "Michigan") is True

    def test_the_aliases_do_not_get_to_vouch_for_the_location(self):
        """Circular on a stored row: the same adoption wrote both.

        Production rows 173 and 197 hold a MIXTURE — `Marshall Thundering Herd`
        carries `Michigan Wolverines`, `SMU Mustangs` carries `Iowa Hawkeyes` —
        so a predicate that accepted aliases would let exactly the
        half-contaminated rows declare themselves clean.
        """
        assert (
            identity_is_borrowed(
                "Marshall Thundering Herd",
                "Eastern Michigan",
                ["Thundering Herd", "Marshall"],
            )
            is True
        )

    def test_the_alias_only_club_is_a_known_and_accepted_cost(self):
        """Inter Milan / Internazionale, written down rather than discovered.

        From the ROW alone this is indistinguishable from a borrowed identity,
        and the script clears it. It is not a live cost — Inter Milan carries an
        `espn_id`, so it is outside the candidate query entirely — but a future
        alias-only club with a cleared id would lose a correct badge here. The
        writer's own predicate does NOT have this weakness, because there the
        aliases are ours and the names are ESPN's.
        """
        assert identity_is_borrowed("Inter Milan", "Internazionale") is True

    def test_a_row_with_nothing_to_compare_is_left_alone(self):
        """Fail-OPEN here, the opposite of the writer, and deliberately.

        The writer refuses on silence because its cost is a missing crest. This
        script holds the UPDATE, so a row it cannot show to be wrong is a row it
        does not touch.
        """
        assert identity_is_borrowed("Some Club", None, None) is False
        assert identity_is_borrowed(None, "Arsenal", None) is False


class TestTheBackupAndRestoreControls:
    """D51. An undo that cannot run, or a write that runs anywhere, is neither."""

    def test_a_plan_needs_no_app(self):
        args = SimpleNamespace(apply=False, backup=False)
        assert wrong_app_refusal(args) is None

    def test_a_write_refuses_off_the_producer_app(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        refusal = wrong_app_refusal(SimpleNamespace(apply=True, backup=True))
        assert refusal and "REFUSING" in refusal and "bainluck-heavy" in refusal

    def test_a_write_refuses_off_a_dyno_entirely(self, monkeypatch):
        """UNSET refuses too: a laptop pointed at production is the case."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        refusal = wrong_app_refusal(SimpleNamespace(apply=True, backup=False))
        assert refusal and "HEROKU_APP_NAME is unset" in refusal

    def test_a_write_is_allowed_on_the_producer_app(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert wrong_app_refusal(SimpleNamespace(apply=True, backup=True)) is None

    def test_the_undo_shares_the_gate_rather_than_copying_it(self):
        """Two copies of one refusal is how they drift."""
        from scripts import restore_6215_borrowed_espn_identity as undo

        assert undo.wrong_app_refusal is wrong_app_refusal

    def test_the_undo_restores_every_field_the_repair_clears(self):
        """The backup table and the clear must not disagree about the columns."""
        from scripts import restore_6215_borrowed_espn_identity as undo

        for field in ESPN_SOURCED_IDENTITY_FIELDS:
            assert field in undo._RESTORE_SQL, (
                f"{field} is cleared by the repair and not restored by the undo"
            )

    def test_the_undo_never_clobbers_a_re_enriched_row(self):
        """COALESCE, so a club legitimately re-enriched after the repair keeps it."""
        from scripts import restore_6215_borrowed_espn_identity as undo

        for field in ESPN_SOURCED_IDENTITY_FIELDS:
            assert f"COALESCE(t.{field}, b.{field})" in undo._RESTORE_SQL, field
