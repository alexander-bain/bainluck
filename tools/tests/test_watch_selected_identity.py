"""The picker and store must agree on provider-proven selected identity."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "ios/Bain Luck/BainLuckWatch Watch App"


def test_picker_badge_and_fresh_action_share_store_identity():
    view = (WATCH / "WatchSelectedGameView.swift").read_text()
    others = view.split("private var otherPickerGames:", 1)[1].split(
        "private var pickerStatus:", 1
    )[0]
    assert "picker.games.filter { !store.isSelected(eventID: $0.id) }" in others
    current = view.split("private func currentPickerGame(", 1)[1].split(
        "private func currentPickerReading(", 1
    )[0]
    assert (
        "let rowID = picker.games.first { store.isSelected(eventID: $0.id) }?.id ?? game.id"
        in current
    )
    assert "return Button {" in current
    assert ".accessibilityAddTraits(.isSelected)" in current
    action = current.split("return Button {", 1)[1].split("} label:", 1)[0]
    assert "WatchTelemetry.shared.action(.reselectGame, surface: .picker)" in action
    assert "store.select(eventID: rowID)" in action
    assert "choosingGame = false" in action
    assert "store.isSelected(eventID: game.id) ? .reselectGame : .selectGame" in view
    # Selection remains alias-aware everywhere. Only decorative main-score metadata
    # has the stricter exact-ID contract (guarded separately); it cannot select.
    start = "    private func scoreTeamColor("
    end = "    @ViewBuilder\n    private func scoreTeamName("
    assert view.count(start) == view.count(end) == 1
    metadata = start + view.split(start, 1)[1].split(end, 1)[0]
    selection_view = view.replace(metadata, "")
    assert "game.id == store.selectedEventID" not in selection_view
    assert "store.selectedEventID == game.id" not in selection_view
    store = (WATCH / "WatchSelectedGameStore.swift").read_text()
    assert "guard eventID > 0, !isSelected(eventID: eventID) else { return }" in store
    fence = "guard requestRevision == revision, selectedEventID == id else { return }"
    learn = "retainIdentity(requestedID: id, canonicalID: result.id)"
    assert (
        store.index("try Task.checkCancellation()")
        < store.index(fence)
        < store.index(learn)
    )
    assert store.index(learn) < store.index("game = result")
    assert "telemetry?(telemetryOutcome, elapsed, telemetryCount)" in store
    for name in ("WatchComplicationSnapshot.swift", "WatchTelemetry.swift"):
        assert "selectedIdentityIDs" not in (WATCH / name).read_text()


def test_host_suite_keeps_identity_regressions_wired():
    host = ROOT / "tools/tests/watch-selected-game"
    assert 'IdentityChecks.swift"' in (host / "run.sh").read_text()
    assert "try await checkWatchSelectedIdentity()" in (host / "main.swift").read_text()
