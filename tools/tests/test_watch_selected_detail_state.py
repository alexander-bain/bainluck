"""Selected-detail presentation must preserve the original truthful boundaries."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchSelectedGameView.swift"


def pending():
    text = VIEW.read_text()
    return text.split("} else if store.selectedEventID != nil {", 1)[1].split(
        "                } else {\n                    gamePicker", 1
    )[0]


def test_loading_error_and_not_yet_loaded_stay_distinct():
    text = pending()
    assert "if store.isRefreshing {" in text
    assert "} else if let error = store.errorMessage {" in text
    assert 'ProgressView("Loading selected game")' in text
    assert "Text(error)" in text
    assert 'Text("Reading unavailable")' in text
    assert 'Text("Game details have not loaded yet")' in text
    assert "Your selection is retained while details load." in text
    assert text.count("Your selection is retained. Refresh to try again.") == 2
    assert ".accessibilityElement(children: .ignore)" not in text
    assert ".minimumScaleFactor" not in text and ".lineLimit" not in text


def test_pending_context_is_identity_not_reading_and_refresh_action_remains_direct():
    text = pending()
    assert "picker.games.first(where: { store.isSelected(eventID: $0.id) })" in text
    assert "pickerMatchup(away:" in text
    assert "pickerScheduledStart(context)" in text
    assert "homeProbability" not in text and "observedAt" not in text
    view = VIEW.read_text()
    assert (
        "store.allowManualRetry()\n                        refreshGeneration += 1"
        in view
    )
    assert ".disabled(store.isRefreshing || scenePhase != .active)" in view
