"""Existing-data presentation adapter preserves live transport and honest missingness."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "ios/Bain Luck/BainLuckWatch Watch App"


def test_complete_score_admission_and_unknown_observation():
    text = (WATCH / "WatchSelectedGameView.swift").read_text()
    helper = text.split("    private func pickerScorePreview(", 1)[1].split(
        "    private func pickerChoiceAccessibility(", 1
    )[0]
    for token in (
        'game.status?.lowercased() == "live"',
        "let rawAway = game.awayTeam, let rawHome = game.homeTeam",
        "let awayScore = game.awayScore, let homeScore = game.homeScore",
        "awayScore >= 0, homeScore >= 0",
        "guard !away.isEmpty, !home.isEmpty else { return nil }",
    ):
        assert token in helper
    assert "?? 0" not in helper and "Date(" not in helper
    assert "Score observation time unavailable." in helper
    assert ".accessibilityLabel(pickerChoiceAccessibility(game))" in text
    assert "preview.spoken" in text and "Text(preview.visual)" in text
    assert "store.select(eventID: game.id)" in text
    assert "pickerScheduledStart(game)" in text


def test_useful_stories_precede_connection_details_with_one_action():
    text = (WATCH / "WatchDiscoverStoriesView.swift").read_text()
    body = text.split("    var body:", 1)[1].split("        .onAppear", 1)[0]
    assert (
        body.index("if visibleReadings.isEmpty")
        < body.index("ForEach(visibleReadings)")
        < body.index(
            "if !visibleReadings.isEmpty", body.index("ForEach(visibleReadings)")
        )
    )
    assert body.count("discoveryRecovery") == 2
    assert (
        text.count(
            'Button(discoveries.isRefreshing ? "Refreshing…" : "Refresh discoveries")'
        )
        == 1
    )
    recovery = text.split("    private var discoveryRecovery:", 1)[1].split(
        "    private func clearContinuation()", 1
    )[0]
    for token in (
        "Text(error)",
        'ProgressView("Loading discoveries")',
        'Text("No discoveries right now")',
        'Text("Showing the last received stories.")',
        'Text("Saved stories · refresh to confirm")',
        "WatchTelemetry.shared.action(.refresh, surface: .discoveries)",
        "manualRefresh?.cancel()",
        "manualRefresh = Task { await discoveries.refresh() }",
        ".disabled(discoveries.isRefreshing || scenePhase != .active)",
    ):
        assert token in recovery
    assert ".foregroundStyle(.orange)" not in recovery
    assert text.count("await discoveries.refresh()") == 2
