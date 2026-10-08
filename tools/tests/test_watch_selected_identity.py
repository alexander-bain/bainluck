"""The picker and store must agree on provider-proven selected identity."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "ios/Bain Luck/BainLuckWatch Watch App"


def test_picker_badge_and_fresh_action_share_store_identity():
    view = (WATCH / "WatchSelectedGameView.swift").read_text()
    assert "let isSelected = store.isSelected(eventID: game.id)" in view
    assert "store.isSelected(eventID: game.id) ? .reselectGame : .selectGame" in view
    assert view.count("store.isSelected(eventID: game.id)") == 2
    assert "game.id == store.selectedEventID" not in view
    assert "store.selectedEventID == game.id" not in view
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
