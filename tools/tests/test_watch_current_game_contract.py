"""Guard the two mounted native accessibility regressions in the current card."""

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchSelectedGameView.swift"


def scope(text, start, end):
    assert text.count(start) == 1
    assert text.count(end) == 1
    return text.split(start, 1)[1].split(end, 1)[0]


def check_native_current_button(text):
    current = scope(
        text, "private func currentPickerGame(", "private func currentPickerReading("
    )
    assert "return Button {" in current
    assert '.accessibilityIdentifier("watch.pick.\\(rowID)")' in current
    assert ".accessibilityAddTraits(.isSelected)" in current
    # The observed wrapper changed this Button into Other in the mounted tree.
    # Other main-reading groups deliberately use ignore and must stay permitted.
    assert ".accessibilityElement(children: .ignore)" not in current


def check_disclosed_error_identity(text):
    picker = scope(text, "private var gamePicker:", "private func currentPickerGame(")
    assert "Button {\n                showingPickerDetails.toggle()" in picker
    assert (
        '.accessibilityValue(showingPickerDetails ? "Expanded" : "Collapsed")' in picker
    )
    assert '.accessibilityIdentifier("watch.picker-info")' in picker
    assert picker.count("if showingPickerDetails {") == 1
    details = picker.split("if showingPickerDetails {", 1)[1]
    child = 'Text(error).accessibilityIdentifier("watch.picker-error")'
    contain = ".accessibilityElement(children: .contain)"
    parent = '.accessibilityIdentifier("watch.picker-details")'
    for marker in (child, contain, parent):
        assert details.count(marker) == 1
    assert details.index(child) < details.index(contain) < details.index(parent)
    # Attach contain to the named parent, not to an unrelated nearby child.
    assert contain + "\n                " + parent in details
    assert ".accessibilityElement(children: .ignore)" not in details


def test_current_card_remains_a_native_selected_button():
    text = VIEW.read_text()
    assert ".accessibilityElement(children: .ignore)" in text
    check_native_current_button(text)


def test_details_parent_preserves_named_error_child():
    check_disclosed_error_identity(VIEW.read_text())


def test_observed_current_button_ignore_mutation_is_rejected():
    text = VIEW.read_text()
    current = scope(
        text, "private func currentPickerGame(", "private func currentPickerReading("
    )
    assert current.count(".buttonStyle(.plain)") == 1
    bad = current.replace(
        ".buttonStyle(.plain)",
        ".buttonStyle(.plain)\n        .accessibilityElement(children: .ignore)",
    )
    assert text.count(current) == 1
    with pytest.raises(AssertionError):
        check_native_current_button(text.replace(current, bad))


def test_observed_missing_details_contain_mutation_is_rejected():
    text = VIEW.read_text()
    marker = (
        ".accessibilityElement(children: .contain)\n"
        '                .accessibilityIdentifier("watch.picker-details")'
    )
    assert text.count(marker) == 1
    bad = text.replace(marker, '.accessibilityIdentifier("watch.picker-details")')
    with pytest.raises(AssertionError):
        check_disclosed_error_identity(bad)


def test_parent_contain_cannot_mask_lost_child_identifier():
    text = VIEW.read_text()
    marker = 'Text(error).accessibilityIdentifier("watch.picker-error")'
    assert text.count(marker) == 1
    with pytest.raises(AssertionError):
        check_disclosed_error_identity(text.replace(marker, "Text(error)"))


# Exact83ac/main/widget fixture union; retain the ORIGINAL accepted hash below.
COMPOSITION_NORMALIZATION = (
    ("    var rectangularScoreScenario: String? = nil\n", ""),
    ("    var fixedObservation: Date? = nil\n", ""),
    (
        '                        "BAINLUCK_WATCH_UI_SHARED_PUBLICATION", "BAINLUCK_WATCH_UI_CIRCULAR_IDENTITY",\n                        "BAINLUCK_WATCH_UI_FIXED_OBSERVATION", "BAINLUCK_WATCH_UI_RECTANGULAR_SCORE_HOST"]\n',
        '                        "BAINLUCK_WATCH_UI_SHARED_PUBLICATION", "BAINLUCK_WATCH_UI_CIRCULAR_IDENTITY"]\n',
    ),
    (
        '                    rectangularScoreScenario: environment["BAINLUCK_WATCH_UI_RECTANGULAR_SCORE_HOST"].flatMap {\n                        ["score", "final", "away-final", "tie", "zero"].contains($0) ? $0 : nil\n                    },\n',
        "",
    ),
    (
        '                    fixedObservation: environment["BAINLUCK_WATCH_UI_FIXED_OBSERVATION"].flatMap { ISO8601DateFormatter().date(from: $0) },\n',
        "",
    ),
    (
        '            if rectangularScoreScenario != nil {\n                let defaults = UserDefaults(suiteName: suite)\n                if let game {\n                    // DEBUG receipt of the actual store callback, never a fixture-fed expected result.\n                    // Per-process identity rejects a receipt left by the pre-termination process.\n                    let receipt: [String: Any] = [\n                        "process_id": Self.processID, "event_id": game.id,\n                        "home_name": game.homeTeam, "away_name": game.awayTeam,\n                        "home_score": game.homeScore.map { $0 as Any } ?? NSNull(),\n                        "away_score": game.awayScore.map { $0 as Any } ?? NSNull(),\n                        "score_observed_at": game.scoreObservedAt.map { $0.timeIntervalSince1970 as Any } ?? NSNull(),\n                        "probability_absent": game.homeProbability == nil,\n                        "status": game.status ?? ""\n                    ]\n                    if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]),\n                       let text = String(data: data, encoding: .utf8) {\n                        defaults?.set(text, forKey: "watch.ui-test.rectangular-score-store-receipt")\n                    } else {\n                        defaults?.removeObject(forKey: "watch.ui-test.rectangular-score-store-receipt")\n                    }\n                } else {\n                    defaults?.removeObject(forKey: "watch.ui-test.rectangular-score-store-receipt")\n                }\n            }\n',
        "",
    ),
    (
        '    }\n\n    var rectangularScoreStoreReceipt: String {\n        guard rectangularScoreScenario != nil else { return "" }\n        return UserDefaults(suiteName: suite)?.string(forKey: "watch.ui-test.rectangular-score-store-receipt") ?? ""\n',
        "",
    ),
    (
        '        let scoreFeed = """\n        {"items":[{"type":"event","score":90,"data":{"id":101,"home_team":"Association Sportive de Saint-Étienne Full Canonical Name","away_team":"Club de Football Long Complete Opponent Name","status":"live"}}],"has_more":false}\n        """\n        let source = rectangularScoreScenario != nil ? scoreFeed : (pickerAlias != nil ? aliasFeed : (rounding ? roundingFeed : standard))\n        let feed = try decoder.decode(WatchFeedResponse.self, from: Data(source.utf8))\n',
        "        let feed = try decoder.decode(WatchFeedResponse.self, from: Data((pickerAlias != nil ? aliasFeed : (rounding ? roundingFeed : standard)).utf8))\n",
    ),
    (
        "        let time = ISO8601DateFormatter().string(from: fixedObservation ?? Date().addingTimeInterval(-60))\n",
        "        let time = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-60))\n",
    ),
    (
        '        }\n        if first, let scenario = rectangularScoreScenario {\n            payload["home_team"] = "Association Sportive de Saint-Étienne Full Canonical Name"\n            payload["away_team"] = "Club de Football Long Complete Opponent Name"\n            payload["home_team_data"] = ["team_id": 1, "abbreviation": "SF"]\n            payload["away_team_data"] = ["team_id": 2, "abbreviation": "LA"]\n            payload["sport"] = "baseball_mlb"\n            payload["status"] = ["final", "away-final", "tie"].contains(scenario) ? "completed" : "live"\n            payload["home_score"] = scenario == "away-final" || scenario == "tie" ? 2 : 4\n            payload["away_score"] = scenario == "away-final" ? 4 : scenario == "zero" ? 0 : 2\n            payload.removeValue(forKey: "hero_probability")\n            payload.removeValue(forKey: "hero_probability_away")\n            payload.removeValue(forKey: "hero_probability_observed_at")\n            // score_observed_at retains the supplied independent fixedObservation.\n',
        "",
    ),
)


def normalize_composed_fixture(text):
    for composed, main in COMPOSITION_NORMALIZATION:
        assert (
            text.count(composed) == 1
        ), "Missing, duplicated or unreviewed composition block"
        text = text.replace(composed, main, 1)
    return text


def test_concrete_fixture_actors_preserve_all_accepted_behavior():
    fixture = normalize_composed_fixture(
        (VIEW.parent / "WatchUIFixture.swift").read_text()
    )
    assert (
        "nonisolated struct WatchUIFixture: WatchSelectedGameTransport, WatchGamePickerTransport {"
        in fixture
    )
    for delegate in (
        "if let pickerDesign { return try await pickerDesign.fetchGames() }",
        "if let pickerDesign { return try await pickerDesign.fetch(eventID: eventID) }",
        "if let pickerAlias { return try await pickerAlias.fetch(eventID: eventID) }",
    ):
        assert fixture.count(delegate) == 1
    # Added main-score color specimens are opt-in; reconstruct all earlier fixture bytes.
    for name in ("FEED", "DETAIL"):
        start = "        // MAIN_SCORE_COLOR_" + name + "_BEGIN\n"
        end = "        // MAIN_SCORE_COLOR_" + name + "_END\n"
        assert fixture.count(start) == fixture.count(end) == 1
        block = start + fixture.split(start, 1)[1].split(end, 1)[0] + end
        fixture = fixture.replace(block, "")
    fixture = fixture.replace(
        'items = malformed + "," + scoreColorSecond',
        'items = malformed + "," + coloredSecond',
    )
    fixture = fixture.replace(
        'items = scoreColorFirst + "," + scoreColorSecond',
        'items = first + "," + coloredSecond',
    )
    # Team-color specimen is also opt-in; default/missing metadata stays byte-identical.
    color_feed = '        let coloredSecond = scenario == "team-color"\n            ? datedSecond.replacingOccurrences(of: "\\"status\\":\\"scheduled\\"", with: "\\"status\\":\\"scheduled\\",\\"away_team_data\\":{\\"primary_color\\":\\"#E31837\\"},\\"home_team_data\\":{\\"primary_color\\":\\"#00338D\\"}")\n            : datedSecond\n'
    assert fixture.count(color_feed) == 1
    fixture = fixture.replace(color_feed, "")
    fixture = fixture.replace(
        'items = malformed + "," + coloredSecond',
        'items = malformed + "," + datedSecond',
    )
    fixture = fixture.replace(
        'items = first + "," + coloredSecond', 'items = first + "," + datedSecond'
    )
    # New schedule-only fixture is opt-in; reconstruct all previously accepted bytes.
    date_feed = '\n        let datedSecond = scenario == "scheduled-time"\n            ? second.replacingOccurrences(of: "\\"status\\":\\"scheduled\\"", with: "\\"status\\":\\"scheduled\\",\\"commence_time\\":\\"2026-10-09T02:00:00Z\\"")\n            : second\n'
    date_detail = '        if !first && scenario == "scheduled-time" {\n            payload["commence_time"] = "2026-10-09T02:00:00Z"\n        }\n'
    assert fixture.count(date_feed) == fixture.count(date_detail) == 1
    fixture = fixture.replace(date_feed, "").replace(date_detail, "")
    fixture = fixture.replace(
        'items = malformed + "," + datedSecond', 'items = malformed + "," + second'
    )
    fixture = fixture.replace(
        'items = first + "," + datedSecond', 'items = first + "," + second'
    )
    # Only redundant protocol conformances changed after mounted acceptance.
    # Reconstruct the exact accepted fixture, preserving every actor/body byte.
    for plain, original in (
        (
            "actor WatchPickerAliasFixture {",
            "actor WatchPickerAliasFixture: WatchSelectedGameTransport {",
        ),
        (
            "actor WatchPickerCurrentGameFixture {",
            "actor WatchPickerCurrentGameFixture: WatchSelectedGameTransport, WatchGamePickerTransport {",
        ),
    ):
        assert fixture.count(plain) == 1
        assert original not in fixture
        fixture = fixture.replace(plain, original)
    assert hashlib.sha256(fixture.encode()).hexdigest() == (
        "608e0b60b0b2f381e2bd2090222e9c99d404996b1982c52044ba60f07c3b33e3"
    )


def check_selected_game_single_clock(text):
    selected = scope(
        text, "private func selectedGame(", "private func probabilityReading("
    )
    schedule = "TimelineView(.periodic(from: .now, by: 15))"
    # One clock for the game screen and one for the separately presented picker.
    assert text.count("TimelineView(") == 2
    assert selected.count("TimelineView(") == 1
    assert selected.count(schedule) == 1
    picker = scope(text, "private var gamePicker:", "private var pickerRefreshButton:")
    assert picker.count("TimelineView(") == picker.count(schedule) == 1
    assert schedule + " { context in\n                    currentPickerGame(game, now: context.date)\n                }" in picker
    current = scope(text, "private func currentPickerGame(", "private func currentPickerReading(")
    assert "now: Date" in current
    assert "Date()" not in current
    assert "WatchObservationAge(observedAt: observed, now: now)" in current
    assert "observationText(game, now: context.date)" in selected
    assert selected.count("probabilityObservationText(game, now: context.date)") == 1
    # Available full named probability leads the useful phase/score context.
    assert (
        "let probabilityFirst = game.showsForecast && game.homeProbabilityText != nil"
        in selected
    )
    assert selected.index("probabilityReading(game)") < selected.index(
        "if showsContextHeader {"
    )
    assert selected.index("if showsContextHeader {") < selected.index(
        "fullWidthScores(game)"
    )
    assert selected.index("probabilityReading(game)") < selected.index("Divider()")
    assert selected.index("fullWidthScores(game)") < selected.index("Divider()")
    assert selected.index("Divider()") < selected.index('Text("Last saved update")')
    assert selected.index('Text("Last saved update")') < selected.index(
        "observationText(game,"
    )
    assert ".foregroundStyle(.orange)" not in selected
    assert (
        "let hasReportedScore = game.homeScore != nil || game.awayScore != nil"
        in selected
    )
    assert (
        "let showsScores = hasReportedScore || game.isLive || game.isFinal || game.isClosed"
        in selected
    )
    assert "if showsScores {" in selected
    assert (
        "let showsContextHeader = game.isClosed || finalOutcomeText(game) != nil || (hasSuppliedState && !store.isRestoredReading && store.errorMessage == nil)"
        in selected
    )
    assert selected.index("if showsContextHeader {") < selected.index(
        "fullWidthScores(game)"
    )
    assert selected.index("Divider()") < selected.index("if !showsContextHeader {")
    assert '.accessibilityIdentifier("watch.scheduled-matchup")' in selected
    assert (
        "game.homeScore ?? 0" not in selected and "game.awayScore ?? 0" not in selected
    )
    assert "if game.showsForecast && game.homeProbability != nil" in selected
    assert (
        '.accessibilityValue(isLive && age.isStale ? "May be out of date" : "")' in text
    )
    assert 'Text("Stale ' not in text
    assert 'Text("Waiting for a newer ' not in text
    probability = scope(
        text, "private func probabilityReading(", "private func fullWidthScores("
    )
    assert "if game.showsForecast" in probability
    assert "if let probabilityText = game.homeProbabilityText" in probability


def check_final_outcome_admission(text):
    outcome = scope(text, "private func finalOutcomeText(", "private func gameState(")
    assert (
        "guard game.isFinal, let home = game.homeScore, let away = game.awayScore,"
        in outcome
    )
    assert "home >= 0, away >= 0 else { return nil }" in outcome
    assert 'return "Final · scores tied"' in outcome
    assert "game.homeScore ?? 0" not in outcome and "game.awayScore ?? 0" not in outcome


def test_final_outcome_keeps_final_and_nonnegative_admission():
    text = VIEW.read_text()
    check_final_outcome_admission(text)
    for before, after in [
        ("guard game.isFinal, let home", "guard let home"),
        ("home >= 0, away >= 0 else", "home >= -1, away >= 0 else"),
        ('return "Final · scores tied"', 'return "Final · tied result"'),
    ]:
        assert before in text
        with pytest.raises(AssertionError):
            check_final_outcome_admission(text.replace(before, after, 1))


def test_selected_game_reordering_keeps_one_periodic_clock():
    check_selected_game_single_clock(VIEW.read_text())


def test_a_second_timeline_for_adjacent_probability_is_rejected():
    text = VIEW.read_text()
    marker = "probabilityObservationText(game, now: context.date)"
    changed = text.replace(
        marker,
        "TimelineView(.periodic(from: .now, by: 15)) { context in " + marker + " }",
        1,
    )
    with pytest.raises(AssertionError):
        check_selected_game_single_clock(changed)


def check_exact_score_color_metadata(text):
    helper = scope(text, "private func scoreTeamColor(", "private func scoreTeamName(")
    assert "guard store.selectedEventID == game.id," in helper
    assert (
        "picker.games.first(where: { $0.id == game.id }) else { return nil }" in helper
    )
    assert "store.isSelected" not in helper
    assert (
        "pickerTeamColor(home ? metadata.homeTeamData?.primaryColor : metadata.awayTeamData?.primaryColor)"
        in helper
    )
    assert "fetch" not in helper and "refresh" not in helper and "Task" not in helper


def test_score_markers_require_exact_loaded_selected_event_metadata():
    check_exact_score_color_metadata(VIEW.read_text())


def test_selection_alias_cannot_supply_main_score_colors():
    text = VIEW.read_text()
    marker = "picker.games.first(where: { $0.id == game.id })"
    assert text.count(marker) == 1
    bad = text.replace(
        marker, "picker.games.first(where: { store.isSelected(eventID: $0.id) })"
    )
    with pytest.raises(AssertionError):
        check_exact_score_color_metadata(bad)


def test_color_lookup_cannot_ignore_the_displayed_selection():
    text = VIEW.read_text()
    marker = "guard store.selectedEventID == game.id,"
    assert text.count(marker) == 1
    with pytest.raises(AssertionError):
        check_exact_score_color_metadata(text.replace(marker, "guard game.id > 0,"))


def test_main_marker_keeps_existing_parser_and_silent_native_name_fallback():
    text = VIEW.read_text()
    parser = scope(text, "private func pickerTeamColor(", "private func pickerMatchup(")
    assert "guard let raw else { return nil }" in parser
    assert "hex.count == 6" in parser
    assert "$0.isHexDigit && $0.isASCII" in parser
    name = scope(
        text, "private func scoreTeamName(", "private func stateAccessibilityLabel("
    )
    assert "if let color" in name
    assert ".frame(width: 6, height: 6)" in name
    assert ".accessibilityHidden(true)" in name
    assert "Text(name).fixedSize(horizontal: false, vertical: true)" in name
    assert "else {\n            Text(name)" in name
    assert "lineLimit" not in name and "minimumScaleFactor" not in name


def test_closed_qualification_is_plain_once_and_precedes_scores_even_when_saved():
    text = VIEW.read_text()
    selected = scope(text, "private func selectedGame(", "private func gameState(")
    state = scope(text, "private func gameState(", "private func probabilityReading(")
    spoken = scope(
        text, "private func stateAccessibilityLabel(", "private func flexibleRow<"
    )
    assert "let showsContextHeader = game.isClosed ||" in selected
    assert 'Text(game.isClosed ? "Result not confirmed"' in state
    assert 'if game.isClosed { return "Result not confirmed" }' in spoken
    assert "Last reported score · final result unverified" not in selected
    assert selected.index("if showsContextHeader {") < selected.index(
        "fullWidthScores(game)"
    )


def check_shared_live_identity_admission(text):
    admission = scope(
        text,
        "private func usesSharedLiveIdentity(",
        "private func sharedLiveHomeReading(",
    )
    assert "game.isLive && game.homeProbabilityText != nil" in admission
    assert "&& game.homeScore != nil && game.awayScore != nil" in admission
    selected = scope(
        text, "private func selectedGame(", "private func scheduledStartText("
    )
    assert "let sharedLiveIdentity = usesSharedLiveIdentity(game)" in selected
    assert (
        "if sharedLiveIdentity {\n                    sharedLiveHomeReading(game)"
        in selected
    )
    assert (
        "} else if probabilityFirst {\n                    probabilityReading(game)"
        in selected
    )
    assert (
        "if sharedLiveIdentity {\n                        sharedLiveAwayReading(game)"
        in selected
    )
    assert "} else {\n                        fullWidthScores(game)" in selected


def test_shared_home_identity_requires_live_known_probability_and_both_scores():
    text = VIEW.read_text()
    check_shared_live_identity_admission(text)
    for before, after in [
        (
            "game.isLive && game.homeProbabilityText != nil",
            "game.homeProbabilityText != nil",
        ),
        ("game.isLive && game.homeProbabilityText != nil", "game.isLive"),
        (
            "&& game.homeScore != nil && game.awayScore != nil",
            "&& game.homeScore != nil",
        ),
        (
            "&& game.homeScore != nil && game.awayScore != nil",
            "&& game.awayScore != nil",
        ),
    ]:
        assert text.count(before) == 1
        with pytest.raises(AssertionError):
            check_shared_live_identity_admission(text.replace(before, after, 1))


def test_shared_identity_keeps_full_independent_spoken_labels_and_unscaled_values():
    text = VIEW.read_text()
    shared = scope(
        text, "private func sharedLiveHomeReading(", "private func fullWidthScores("
    )
    for marker in [
        '.accessibilityIdentifier("watch.home-identity")',
        ".accessibilityLabel(game.homeTeam)",
        'Text("Win chance")',
        'Text("Score")',
        'Text("Score \\(score)")',
        ".font(.system(size: 34, weight: .bold, design: .rounded))",
        "Text(probability).font(.title2.bold())",
        '.accessibilityLabel("\\(team) win probability, \\(probability)")',
        '.accessibilityLabel("\\(team), score \\(score)")',
        '.accessibilityLabel("\\(game.awayTeam), score \\(score)")',
        "if dynamicTypeSize.isAccessibilitySize",
    ]:
        assert marker in shared
    for forbidden in ["minimumScaleFactor", "lineLimit", "truncationMode", "?? 0"]:
        assert forbidden not in shared


def check_picker_choices_before_refresh(text):
    picker = scope(text, "private var gamePicker:", "private var pickerRefreshButton:")
    before, after = picker.split("ForEach(otherPickerGames)", 1)
    assert (
        "if otherPickerGames.isEmpty {\n                pickerRefreshButton\n            }"
        in before
    )
    assert (
        "if !otherPickerGames.isEmpty {\n                pickerRefreshButton\n            }"
        in after
    )
    assert before.index(
        'accessibilityIdentifier("watch.picker-status")'
    ) < before.index("pickerRefreshButton")
    assert after.index("pickerRefreshButton") < after.index(
        "showingPickerDetails.toggle()"
    )
    refresh = scope(
        text, "private var pickerRefreshButton:", "private func pickerTeamColor("
    )
    for required in (
        "WatchTelemetry.shared.action(.refresh, surface: .picker)",
        "if choosingGame { gamesRefreshGeneration += 1 }",
        "else { refreshGeneration += 1 }",
        ".disabled(picker.isLoading || scenePhase != .active)",
        '.accessibilityIdentifier("watch.picker-refresh")',
    ):
        assert refresh.count(required) == 1
    assert text.count('.accessibilityIdentifier("watch.picker-refresh")') == 1


def test_populated_picker_choices_precede_the_single_refresh_action():
    check_picker_choices_before_refresh(VIEW.read_text())


def test_empty_picker_cannot_lose_refresh_next_to_explanation():
    text = VIEW.read_text()
    broken = text.replace(
        "if otherPickerGames.isEmpty {\n                pickerRefreshButton",
        "if !otherPickerGames.isEmpty {\n                pickerRefreshButton",
        1,
    )
    with pytest.raises(AssertionError):
        check_picker_choices_before_refresh(broken)


def test_composition_normalizer_rejects_altered_missing_or_duplicate_blocks():
    fixture = (VIEW.parent / "WatchUIFixture.swift").read_text()
    for composed, _ in COMPOSITION_NORMALIZATION:
        for replacement in (
            "",
            composed + composed,
            composed + "// unreviewed change\n",
        ):
            altered = fixture.replace(composed, replacement, 1)
            if replacement.endswith("// unreviewed change\n"):
                # Exact added block remains recognizable; original fixture hash
                # must still reject unrelated surviving bytes.
                normalized = normalize_composed_fixture(altered)
                assert normalized != normalize_composed_fixture(fixture)
            else:
                with pytest.raises(AssertionError):
                    normalize_composed_fixture(altered)


def test_picker_requires_schedule_date_without_implicit_wall_clock():
    text = VIEW.read_text()
    for changed in (
        text.replace("currentPickerGame(game, now: context.date)", "currentPickerGame(game, now: Date())"),
        text.replace("private func currentPickerGame(_ game: WatchSelectedGame, now: Date)",
                     "private func currentPickerGame(_ game: WatchSelectedGame, now: Date = Date())"),
    ):
        with pytest.raises(AssertionError):
            check_selected_game_single_clock(changed)
