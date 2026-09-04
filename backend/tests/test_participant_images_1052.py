"""ux/1052 item 5 — a tennis card has a face because the payload carries one.

Alex, shopping /sports at phone width on 2026-09-03: three live tennis cards,
all initials (``IB``/``BB``, ``HS``/``CB``, ``YP``/``QZ``), beside soccer cards
drawing real crests. The renderer was correct and the wire was empty — the event
card payload had no image field of any kind.

What is pinned here is the property, not the prose:

  * an individual-sport fixture resolves to the register's PINNED image, and a
    team fixture never does — a club must not wear somebody's headshot;
  * the four keys are ALWAYS served, so "no photo of this player" and "this
    payload predates the field" stay different facts on the wire;
  * a face and a flag are independent — 22 of 378 registered players have a
    flag and no face, and a flag alone still beats two letters;
  * a broken register degrades to initials, never to an exception on /api/feed;
  * a fixture register never beats a committed one.

Every guard carries BOTH arms. "Returns None" alone passes for a resolver that
has been reduced to returning None.
"""

from __future__ import annotations

import json

import pytest

from app.utils import participant_images as pi


#: The three live matches Alex photographed, with the register spellings.
BUCSA = "Cristina Bucsa"
SAKATSUME = "Himeno Sakatsume"
BUSE = "Ignacio Buse"          # the card's `IB` — a men's-draw player
BONZI = "Benjamin Bonzi"
PUTINTSEVA = "Yulia Putintseva"
ZHENG = "Qinwen Zheng"

WTA = "tennis_wta_us_open"
ATP = "tennis_atp_us_open"


@pytest.fixture(autouse=True)
def _clean_cache():
    pi.reset_index_cache()
    yield
    pi.reset_index_cache()


def _register(tmp_path, players, name="us-open-2026.json"):
    (tmp_path / name).write_text(json.dumps({"players": players}))
    return tmp_path


def _player(entity_key, *, url=None, flag_url=None):
    return {
        "entity_key": entity_key,
        "draw": "womens-singles",
        "role": "contender",
        "image": {"url": url, "flag_url": flag_url, "verified_subject": True},
    }


# ---------------------------------------------------------------------------
# 1. The real, committed register — the cards Alex actually saw.
# ---------------------------------------------------------------------------


class TestTheLiveCardsResolve:
    """Against the register on disk, not a fixture. A resolver that works on a
    synthetic draw and misses the real spellings ships initials."""

    @pytest.mark.parametrize(
        "name, sport_key",
        [
            (BUCSA, WTA), (SAKATSUME, WTA),
            (BUSE, ATP), (BONZI, ATP),
            (PUTINTSEVA, WTA), (ZHENG, WTA),
        ],
    )
    def test_every_player_on_the_three_live_cards_has_something_to_draw(
        self, name, sport_key
    ):
        image = pi.participant_image(name, sport_key=sport_key)

        assert image is not None, f"{name} resolved to nothing"
        assert image.get("image_url") or image.get("flag_url"), (
            f"{name} has a register entry with neither a face nor a flag"
        )

    def test_a_face_is_a_face_and_a_flag_is_a_flag(self):
        """The two fields must not be crossed: a flag rendered into the face
        slot is a 500x500 country roundel where a headshot goes.

        Hosts compared on the parsed ``netloc``, not by substring — a substring
        test says yes to ``https://evil.example/?u=upload.wikimedia.org``, which
        is `py/incomplete-url-substring-sanitization` and is a real distinction
        even in a test that is only reading our own committed register.
        """
        from urllib.parse import urlparse

        image = pi.participant_image(BUCSA, sport_key=WTA)

        assert urlparse(image["image_url"]).netloc == "upload.wikimedia.org"
        flag = urlparse(image["flag_url"])
        assert flag.netloc == "a.espncdn.com"
        assert flag.path.startswith("/i/teamlogos/countries/")

    def test_a_player_with_no_face_still_gets_a_flag(self):
        """Ignacio Buse, measured 2026-09-03: no face on the register, Peru's
        flag on it. The card must not fall back to initials for him."""
        image = pi.participant_image(BUSE, sport_key=ATP)

        assert image["image_url"] is None
        assert image["flag_url"] is not None


# ---------------------------------------------------------------------------
# 2. Scope — an individual sport, and nothing else.
# ---------------------------------------------------------------------------


class TestOnlyOneOnOneFixturesResolve:
    def test_a_team_fixture_never_reaches_the_player_index(self):
        """A team name and a player name share one string field. Resolving a
        football fixture against a player index is how a club comes to wear
        somebody's headshot."""
        assert pi.participant_image(
            BUCSA, sport_key="soccer_germany_bundesliga"
        ) is None

    def test_CONTROL_the_same_name_DOES_resolve_for_tennis(self):
        """Without this arm the test above passes for a resolver that has been
        reduced to returning None for everything."""
        assert pi.participant_image(BUCSA, sport_key=WTA) is not None

    @pytest.mark.parametrize("name", [None, "", "   ", 17])
    def test_a_missing_or_non_string_name_is_not_an_error(self, name):
        assert pi.participant_image(name, sport_key=WTA) is None

    def test_an_unregistered_player_keeps_their_initials(self):
        """The honest fallback, and the one already on screen."""
        assert pi.participant_image("Nobody At All", sport_key=WTA) is None


# ---------------------------------------------------------------------------
# 3. The four keys on the wire.
# ---------------------------------------------------------------------------


class TestTheCardFields:
    def test_all_four_keys_are_served_even_when_every_value_is_null(self):
        """#2088's rule, applied here: absence must not be readable as "no
        photo". A client keying its initials fallback on `in` rather than on
        `is None` would silently never draw a face once one arrives."""
        fields = pi.participant_images_for_event(
            home_team="Real Madrid", away_team="Barcelona",
            sport_key="soccer_spain_la_liga",
        )

        assert set(fields) == {
            "home_image_url", "away_image_url", "home_flag_url", "away_flag_url",
        }
        assert set(fields.values()) == {None}

    def test_home_and_away_are_not_crossed(self):
        fields = pi.participant_images_for_event(
            home_team=BUCSA, away_team=SAKATSUME, sport_key=WTA
        )
        home = pi.participant_image(BUCSA, sport_key=WTA)
        away = pi.participant_image(SAKATSUME, sport_key=WTA)

        assert fields["home_image_url"] == home["image_url"]
        assert fields["away_image_url"] == away["image_url"]
        assert fields["home_image_url"] != fields["away_image_url"]

    def test_one_side_resolving_does_not_suppress_the_other(self):
        """The mixed card, which is what a real draw looks like."""
        fields = pi.participant_images_for_event(
            home_team=BUCSA, away_team="Nobody At All", sport_key=WTA
        )

        assert fields["home_image_url"] is not None
        assert fields["away_image_url"] is None
        assert fields["away_flag_url"] is None


# ---------------------------------------------------------------------------
# 4. The index — what it reads, what it refuses, and when it re-reads.
# ---------------------------------------------------------------------------


class TestTheIndex:
    def test_a_player_with_an_empty_image_block_is_not_indexed(self, tmp_path):
        """An empty block is a census RESULT — "we looked and found nothing" —
        and indexing it would put a null face where the caller expects a hit."""
        _register(tmp_path, [_player("nobody-pictured")])

        assert pi.participant_image(
            "Nobody Pictured", sport_key=WTA, directory=tmp_path
        ) is None

    def test_CONTROL_the_same_player_WITH_an_image_is_indexed(self, tmp_path):
        _register(tmp_path, [_player("nobody-pictured", flag_url="https://x/f.png")])

        assert pi.participant_image(
            "Nobody Pictured", sport_key=WTA, directory=tmp_path
        ) == {"image_url": None, "flag_url": "https://x/f.png"}

    def test_a_fixture_file_never_beats_a_committed_register(self, tmp_path):
        """`_`-prefixed files are fixtures — the convention `registered_market_ids`
        follows. A synthetic draw sorts BEFORE `us-open-…` and would otherwise
        win the collision and put a test photo on a live card."""
        (tmp_path / "_synthetic-draw.json").write_text(
            json.dumps({"players": [_player("cristina-bucsa", url="https://FAKE")]})
        )
        _register(tmp_path, [_player("cristina-bucsa", url="https://real/face.jpg")])

        image = pi.participant_image(BUCSA, sport_key=WTA, directory=tmp_path)
        assert image["image_url"] == "https://real/face.jpg"

    def test_the_first_committed_register_wins_a_name_collision(self, tmp_path):
        """Two tournaments, one player, two pinned photos — the same person, so
        either is right, but the answer must not depend on directory order.
        First file in sorted order wins, and that is asserted rather than
        assumed: without it the LAST file silently decides."""
        _register(
            tmp_path, [_player("cristina-bucsa", url="https://a/first.jpg")],
            name="a-open-2026.json",
        )
        _register(
            tmp_path, [_player("cristina-bucsa", url="https://z/second.jpg")],
            name="z-open-2026.json",
        )

        image = pi.participant_image(BUCSA, sport_key=WTA, directory=tmp_path)
        assert image["image_url"] == "https://a/first.jpg"

    def test_an_unreadable_register_degrades_to_initials_and_never_raises(
        self, tmp_path
    ):
        """Same posture as `load_register`. A broken register must cost the
        faces, not the feed."""
        (tmp_path / "us-open-2026.json").write_text("{not json")

        assert pi.participant_image(BUCSA, sport_key=WTA, directory=tmp_path) is None

    def test_a_register_with_no_players_key_is_not_an_error(self, tmp_path):
        (tmp_path / "us-open-2026.json").write_text(
            json.dumps({"mens-singles": {}, "womens-singles": {}})
        )

        assert pi.participant_image(BUCSA, sport_key=WTA, directory=tmp_path) is None

    def test_an_absent_directory_is_not_an_error(self, tmp_path):
        assert pi.participant_image(
            BUCSA, sport_key=WTA, directory=tmp_path / "nope"
        ) is None

    def test_the_index_is_reused_rather_than_reparsed_per_participant(
        self, tmp_path, monkeypatch
    ):
        """One feed page asks this ~120 times. Re-reading two JSON files per
        card would put the register on the hot path of /api/feed."""
        _register(tmp_path, [_player("cristina-bucsa", url="https://real/face.jpg")])
        builds: list[int] = []
        real = pi._build_index
        monkeypatch.setattr(
            pi, "_build_index", lambda paths: (builds.append(1), real(paths))[1]
        )

        for _ in range(10):
            pi.participant_image(BUCSA, sport_key=WTA, directory=tmp_path)

        assert len(builds) == 1

    def test_a_changed_register_is_picked_up_after_the_recheck_window(
        self, tmp_path, monkeypatch
    ):
        """The other arm of the cache. "Never re-read until the dyno restarts"
        is how a corrected photo stays wrong for a day."""
        _register(tmp_path, [_player("cristina-bucsa", url="https://old/face.jpg")])
        clock = {"t": 1000.0}
        monkeypatch.setattr(pi.time, "monotonic", lambda: clock["t"])

        first = pi.participant_image(BUCSA, sport_key=WTA, directory=tmp_path)
        assert first["image_url"] == "https://old/face.jpg"

        (tmp_path / "us-open-2026.json").write_text(
            json.dumps({"players": [_player("cristina-bucsa", url="https://new.jpg")]})
        )
        clock["t"] += pi.INDEX_RECHECK_S + 1

        second = pi.participant_image(BUCSA, sport_key=WTA, directory=tmp_path)
        assert second["image_url"] == "https://new.jpg"


# ---------------------------------------------------------------------------
# 5. The register's own verification is the reason this join is allowed.
# ---------------------------------------------------------------------------


class TestTheEvidenceIsNeverShipped:
    def test_the_card_carries_two_urls_and_nothing_else(self):
        """A client handed the evidence is a client invited to re-decide whether
        the photo is of the right person — a decision made offline precisely so
        it is not made at render time."""
        image = pi.participant_image(BUCSA, sport_key=WTA)

        assert set(image) == {"image_url", "flag_url"}

    def test_the_committed_register_still_carries_the_coverage_this_relies_on(self):
        """Alex's ruling 8 gate is a measurement, so it is measured. If the
        register is ever rebuilt with thin coverage, half the cards go back to
        initials and this says so instead of the site saying it."""
        from app.utils.tournament_register import REGISTER_DIR

        index = pi._index(REGISTER_DIR)
        faces = sum(1 for v in index.values() if v["image_url"])

        assert len(index) >= 300, f"only {len(index)} players carry an image"
        assert faces >= 300, f"only {faces} players carry a face"


# ---------------------------------------------------------------------------
# 6. The field reaches the wire — the whole point of the change.
# ---------------------------------------------------------------------------


class TestTheFeedActuallyServesIt:
    """A resolver nothing calls is a resolver that ships initials.

    `/api/feed` cannot be rendered in-process here (it needs a database), so
    this is a containment check on the ONE function that builds an event card —
    located by AST, not by grep, and raising rather than passing when it cannot
    find what it is asserting about.
    """

    def _event_card_builder(self):
        import ast
        import pathlib

        source = (
            pathlib.Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
        ).read_text()
        tree = ast.parse(source)
        holders = [
            (node.name, ast.get_source_segment(source, node) or "")
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and "format_event_data(" in (ast.get_source_segment(source, node) or "")
        ]
        # Not `assert holders` — a zero-yield scan must be loud about WHY.
        if len(holders) != 1:
            raise AssertionError(
                f"expected exactly one function in feed.py to build an event card, "
                f"found {len(holders)}: {[h[0] for h in holders]}. The guard below "
                f"cannot say anything about a call site it did not find."
            )
        return holders[0]

    def test_the_result_is_MERGED_INTO_the_event_card(self):
        """Not merely called — MERGED. Asserting the call appears is satisfied by

            _unused = participant_images_for_event(...)

        which resolves every face perfectly and serves none of them. So the
        shape is checked structurally: a call to the resolver must be an
        argument of ``event_data.update(...)``.
        """
        import ast

        name, body = self._event_card_builder()
        merged = False
        for node in ast.walk(ast.parse(body)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "update"
                and isinstance(func.value, ast.Name)
                and func.value.id == "event_data"
            ):
                continue
            for arg in node.args:
                if (
                    isinstance(arg, ast.Call)
                    and isinstance(arg.func, ast.Name)
                    and arg.func.id == "participant_images_for_event"
                ):
                    merged = True

        assert merged, (
            f"{name}() builds the event card and never merges a face into it — "
            f"the payload goes out imageless and every tennis card keeps its "
            f"initials"
        )

    def test_it_passes_BOTH_sides_and_the_sport_key(self):
        """A call that hands over one side, or forgets the sport key, resolves
        a football club against a player index."""
        _, body = self._event_card_builder()
        call = body.split("participant_images_for_event(", 1)[1].split("))", 1)[0]

        assert "home_team=" in call and "away_team=" in call
        assert "sport_key=" in call

    def test_the_four_keys_are_the_ones_the_helper_produces(self):
        """The card and the helper must not drift apart in name. The renderer
        keys off these exact strings; a rename on one side alone is a silent
        return to initials."""
        fields = pi.participant_images_for_event(
            home_team=BUCSA, away_team=SAKATSUME, sport_key=WTA
        )

        assert set(fields) == {
            "home_image_url", "away_image_url", "home_flag_url", "away_flag_url",
        }
        assert all(v is not None for v in fields.values())

    def test_the_directory_is_not_listed_once_per_participant(
        self, tmp_path, monkeypatch
    ):
        """The window check must come BEFORE the glob.

        `_score_events` calls this twice per card, ~60 cards a page. A directory
        listing per participant puts the filesystem on the hot path of
        /api/feed to re-learn something that changes at deploy speed — and a
        cache that still stats every call is a cache in name only.
        """
        _register(tmp_path, [_player("cristina-bucsa", url="https://real/face.jpg")])
        listings: list[int] = []
        real = pi._register_paths
        monkeypatch.setattr(
            pi, "_register_paths", lambda d: (listings.append(1), real(d))[1]
        )

        for _ in range(50):
            pi.participant_images_for_event(
                home_team=BUCSA, away_team=SAKATSUME, sport_key=WTA,
                directory=tmp_path,
            )

        assert len(listings) == 1, (
            f"the register directory was listed {len(listings)} times for 50 cards"
        )
