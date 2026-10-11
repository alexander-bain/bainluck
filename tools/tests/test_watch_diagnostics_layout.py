"""Source contract for readable sections around the unchanged Watch consent control."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchDiagnosticsView.swift"


def test_every_existing_consent_fact_remains_visible_once():
    source = VIEW.read_text()
    for fact in (
        "Shares screen visits, actions and load times as part of your iPhone’s analytics.",
        "Your iPhone must also allow analytics.",
        "No game names or search text are included.",
        "Off by default.",
        "Turning this off clears unsent Watch diagnostics.",
        "Data already sent cannot be recalled here.",
        "Your choice could not be saved. It applies for this session.",
    ):
        assert source.count(fact) == 1
    for title in ("Your choice", "What is shared", "Turning it off"):
        assert source.count(f'Text("{title}")') == 1
    assert "DisclosureGroup" not in source
    assert ".accessibilityElement(children: .ignore)" not in source


def test_explicit_toggle_binding_and_telemetry_lifecycle_stay_unchanged():
    source = VIEW.read_text()
    for required in (
        'Toggle("Share Watch diagnostics", isOn: Binding(',
        "get: { telemetry.enabled }, set: { telemetry.setEnabled($0) }))",
        '.accessibilityIdentifier("watch.diagnostics.choice")',
        "telemetry.screen(.diagnostics)",
        "telemetry.content(.diagnostics)",
    ):
        assert source.count(required) == 1
    assert source.count("telemetry.setEnabled(") == 1
    assert ".onChange" not in source


def test_session_warning_and_phone_requirement_stay_in_the_choice_section():
    source = VIEW.read_text()
    choice = source.split("Section {", 1)[1].split("} header:", 1)[0]
    assert 'Toggle("Share Watch diagnostics"' in choice
    assert "if !telemetry.consentSaved {" in choice
    assert (
        'Text("Your choice could not be saved. It applies for this session.")' in choice
    )
    assert 'Text("Your iPhone must also allow analytics.")' in choice
    assert choice.index("watch.diagnostics.choice") < choice.index(
        "watch.diagnostics.persistence-warning"
    )
    assert choice.index("watch.diagnostics.persistence-warning") < choice.index(
        "watch.diagnostics.phone-requirement"
    )
