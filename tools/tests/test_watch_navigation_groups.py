"""Grouping must preserve direct primary actions and truthful utility controls."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchSelectedGameView.swift"


def source():
    return (
        SOURCE.read_text()
        .split("    var body: some View {", 1)[1]
        .split("                #if DEBUG", 1)[0]
    )


def test_primary_actions_precede_disclosure_and_clear_is_last():
    text = source()
    assert text.index(".action(.refresh,") < text.index(".action(.chooseGame,")
    assert text.index(".action(.chooseGame,") < text.index(".action(.discoveries,")
    assert text.index(".action(.discoveries,") < text.index("if showingMoreActions {")
    assert text.index("if showingMoreActions {") < text.index(
        'NavigationLink("Diagnostics")'
    )
    assert (
        text.index('NavigationLink("Diagnostics")')
        < text.index("Divider()")
        < text.index(".action(.clearGame,")
    )
    assert 'Text("Clear selected game")' in text
    assert (
        ".overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary, lineWidth: 1))"
        in text
    )


def test_utilities_have_explicit_expansion_state_and_conditional_handoff():
    text = source()
    assert '.accessibilityValue(showingMoreActions ? "Expanded" : "Collapsed")' in text
    assert '.accessibilityIdentifier("watch.more-actions")' in text
    utilities = text.split("if showingMoreActions {", 1)[1].split(
        "                    Divider()", 1
    )[0]
    assert "if store.game != nil {" in utilities
    assert 'Text("Continue on iPhone")' in utilities
    assert 'NavigationLink("Diagnostics")' in utilities
    assert "showingHandoffHelp = true" in utilities
    assert "store.clearSelection()" not in utilities


def test_grouping_keeps_wrapping_full_width_primary_controls():
    text = source()
    for title in (
        "Choose another game",
        "Discoveries",
        "More actions",
        "Clear selected game",
    ):
        control = text.split('"' + title + '"', 1)[1].split(".buttonStyle(.plain)", 1)[
            0
        ]
        assert ".fixedSize(horizontal: false, vertical: true)" in control
        assert ".frame(maxWidth: .infinity, minHeight: 44)" in control
        assert ".minimumScaleFactor" not in control
        assert ".lineLimit" not in control
