"""Selected-detail presentation must preserve the original truthful boundaries."""

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchSelectedGameView.swift"


def pending():
    text = VIEW.read_text()
    return text.split("} else if store.selectedEventID != nil {", 1)[1].split(
        "                } else {\n                    gamePicker", 1
    )[0]


def assert_distinct_pending_states(text):
    # Match sibling branches at the same indentation, so an error hidden behind
    # a loading-first branch cannot pass just because all labels still exist.
    states = re.search(
        r"^(?P<indent>[ \t]*)if let error = store\.errorMessage \{\n"
        r"(?P<error>.*?)^(?P=indent)\} else if store\.isRefreshing \{\n"
        r"(?P<loading>.*?)^(?P=indent)\} else \{\n"
        r"(?P<unloaded>.*?)^(?P=indent)\}",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert states, "Existing error must take precedence over initial loading"
    error, loading, unloaded = (
        states.group("error"),
        states.group("loading"),
        states.group("unloaded"),
    )
    retry = re.fullmatch(
        r"(?P<context>.*?)^(?P<indent>[ \t]*)if store\.isRefreshing \{\n"
        r"(?P<progress>.*?)^(?P=indent)\}\s*",
        error,
        re.MULTILINE | re.DOTALL,
    )
    assert retry, "Retry progress must remain inside the retained-error branch"
    context = retry.group("context")
    assert not re.search(r"^\s*if\b", context, re.MULTILINE)
    for content in (
        'Text("Reading unavailable")',
        "Text(error)",
        'Text("Your selection is retained. Refresh to try again.")',
        '.accessibilityIdentifier("watch.selection-state-heading")',
        '.accessibilityIdentifier("watch.selection-retry-explanation")',
    ):
        assert content in context, "Error context must survive both idle and retry"
    assert 'ProgressView("Retrying selected game")' in retry.group("progress")
    assert '.accessibilityIdentifier("watch.loading-selected-game")' in retry.group(
        "progress"
    )
    assert 'ProgressView("Loading selected game")' in loading
    assert "Your selection is retained while details load." in loading
    assert '.accessibilityIdentifier("watch.selection-loading-explanation")' in loading
    assert 'Text("Game details have not loaded yet")' in unloaded
    assert "Your selection is retained. Refresh to try again." in unloaded
    assert '.accessibilityIdentifier("watch.selection-retry-explanation")' in unloaded
    # Preserve the original content, selection, accessibility and scaling guards.
    assert 'ProgressView("Loading selected game")' in text
    assert "Text(error)" in text
    assert 'Text("Reading unavailable")' in text
    assert 'Text("Game details have not loaded yet")' in text
    assert "Your selection is retained while details load." in text
    assert text.count("Your selection is retained. Refresh to try again.") == 2
    assert ".accessibilityElement(children: .ignore)" not in text
    assert ".minimumScaleFactor" not in text and ".lineLimit" not in text


def test_loading_error_and_not_yet_loaded_stay_distinct():
    assert_distinct_pending_states(pending())


@pytest.mark.parametrize(
    "mutation",
    [
        "loading_first",
        "error_only_while_retrying",
        "error_hidden_during_retry",
        "lost_retry",
        "lost_initial_loading",
        "lost_not_yet_loaded",
        "lost_retention",
        "hidden_accessibility",
        "shrinking",
        "truncation",
    ],
)
def test_pending_state_guard_rejects_lost_truthful_states(mutation):
    text = pending()
    mutations = {
        "loading_first": text.replace(
            "if let error = store.errorMessage {", "if store.isRefreshing {", 1
        ),
        "error_only_while_retrying": text.replace("Text(error)", 'Text("")', 1).replace(
            'ProgressView("Retrying selected game")',
            'Text(error)\n                                ProgressView("Retrying selected game")',
            1,
        ),
        "error_hidden_during_retry": text.replace(
            "Text(error)",
            "if !store.isRefreshing {\n                                Text(error)\n                            }",
            1,
        ),
        "lost_retry": text.replace(
            'ProgressView("Retrying selected game")', "EmptyView()", 1
        ),
        "lost_initial_loading": text.replace(
            'ProgressView("Loading selected game")', "EmptyView()", 1
        ),
        "lost_not_yet_loaded": text.replace(
            'Text("Game details have not loaded yet")', "EmptyView()", 1
        ),
        "lost_retention": text.replace(
            'Text("Your selection is retained. Refresh to try again.")',
            "EmptyView()",
            1,
        ),
        "hidden_accessibility": text + "\n.accessibilityElement(children: .ignore)",
        "shrinking": text + "\n.minimumScaleFactor(0.5)",
        "truncation": text + "\n.lineLimit(1)",
    }
    altered = mutations[mutation]
    assert altered != text
    with pytest.raises(AssertionError):
        assert_distinct_pending_states(altered)


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
