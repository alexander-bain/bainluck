"""1.0.4 inline Discoveries boundaries; portable source guards, not UI acceptance."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "ios/Bain Luck/BainLuckWatch Watch App"


def check_mount(parent, stories):
    mount = parent.index("WatchDiscoverStoriesView(")
    assert parent.index('accessibilityIdentifier("watch.clear-selection")') < mount
    assert "continuation: $discoveryContinuation" in parent
    assert "isActive: !choosingGame && !showingHandoffHelp" in parent
    assert "ScrollView" not in stories
    for extra in (
        "NavigationStack",
        "NavigationLink",
        ".sheet(",
        "TextField",
        "Search",
        "Collections",
        "showMore",
    ):
        assert extra not in stories
    assert 'Text("Discoveries")' in stories


def check_handoff(parent, stories):
    assert (
        "guard scenePhase == .active, !choosingGame, discoveryContinuation == nil else { return nil }"
        in parent
    )
    game_action = parent.split(
        "WatchTelemetry.shared.action(.phoneContinuation, surface: .game)", 1
    )[1].split("} label:", 1)[0]
    assert game_action.index("discoveryContinuation = nil") < game_action.index(
        "showingHandoffHelp = true"
    )
    assert "continuation = .futures(reading.id)" in stories
    assert "element: canInteract ? continuation : nil" in stories
    assert "StoryContinuation.configure(activity, destination: destination)" in stories
    assert "!ids.contains(id)" in stories
    assert "if isChoosing { discoveryContinuation = nil }" in parent
    for marker in (".onOpenURL { url in", ".onChange(of: store.selectedEventID)"):
        assert (
            "discoveryContinuation = nil"
            in parent.split(marker, 1)[1].split("scroll.scrollTo", 1)[0]
        )


def check_lifecycle(stories):
    assert "isActive && scenePhase == .active" in stories
    assert ".task(id: canInteract)" in stories
    assert "guard canInteract else { return }" in stories
    assert ".disabled(!canInteract)" in stories
    assert ".disabled(discoveries.isRefreshing || !canInteract)" in stories
    for marker in (".onChange(of: canInteract)", ".onDisappear"):
        section = stories.split(marker, 1)[1].split(".onChange", 1)[0]
        for action in (
            "manualRefresh?.cancel()",
            "discoveries.cancelRefresh()",
            "clearContinuation()",
        ):
            assert action in section


class DiscoveriesFirstSliceTests(unittest.TestCase):
    def setUp(self):
        self.parent = (WATCH / "WatchSelectedGameView.swift").read_text()
        self.stories = (WATCH / "WatchDiscoverStoriesView.swift").read_text()

    def test_inline_after_paid_game_controls_with_no_browsing_stack(self):
        check_mount(self.parent, self.stories)

    def test_single_explicit_canonical_handoff_destination(self):
        check_handoff(self.parent, self.stories)

    def test_hidden_inactive_or_departed_content_cancels_and_refuses_actions(self):
        check_lifecycle(self.stories)

    def test_all_three_server_selected_rows_use_the_existing_store(self):
        store = (WATCH / "WatchDiscoveryStore.swift").read_text()
        self.assertIn("Array(readings.prefix(3))", store)
        self.assertNotIn("hasSelectedGame ? 2", store)
        self.assertIn("discoveries.visibleReadings()", self.stories)
        self.assertIn("ForEach(visibleReadings)", self.stories)

    def test_truthful_existing_card_and_saved_recovery_remain(self):
        for contract in (
            "WatchDiscoveryCardPresentation(reading: reading, now: context.date)",
            "if let result = display.result",
            "display.observation",
            "display.spokenObservation",
            "Saved stories · refresh to confirm",
            "Showing the last received stories.",
            "No discoveries right now",
            ".fixedSize(horizontal: false, vertical: true)",
        ):
            self.assertIn(contract, self.stories)
        self.assertLess(
            self.stories.index("if let result = display.result"),
            self.stories.index("let probability = display.probability"),
        )

    def test_guards_reject_nested_scroll_or_added_browse(self):
        for extra in ("ScrollView", "NavigationLink", "TextField", "Collections"):
            with self.subTest(extra=extra), self.assertRaises(AssertionError):
                check_mount(self.parent, self.stories + extra)

    def test_guards_reject_competing_or_stale_handoff(self):
        for old in (
            ", discoveryContinuation == nil",
            "if isChoosing { discoveryContinuation = nil }",
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                check_handoff(self.parent.replace(old, ""), self.stories)
        for old in ("!ids.contains(id)", "continuation = .futures(reading.id)"):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                check_handoff(self.parent, self.stories.replace(old, "REMOVED"))

    def test_guards_reject_lost_cancellation_or_interaction_fence(self):
        for old in (
            "manualRefresh?.cancel()",
            "discoveries.cancelRefresh()",
            "guard canInteract else { return }",
            ".disabled(!canInteract)",
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                check_lifecycle(self.stories.replace(old, "REMOVED"))


if __name__ == "__main__":
    unittest.main()
