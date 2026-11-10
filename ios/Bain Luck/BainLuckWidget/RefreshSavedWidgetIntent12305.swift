import AppIntents
import SwiftUI
import WidgetKit

/// #12305 — the saved widget's ↻. Running it is the whole job: WidgetKit asks
/// the widget for a new timeline after an intent from one of its buttons
/// finishes, so the reading is fetched again without opening the app.
struct RefreshSavedWidgetIntent12305: AppIntent {
    static var title: LocalizedStringResource = "Refresh saved widget"
    static var isDiscoverable = false

    init() {}

    func perform() async throws -> some IntentResult {
        .result()
    }
}

extension SavedItemWidgetEntry10875 {
    /// A reading, or the "Can't reach Bain Luck" message: the two states a new
    /// fetch can change. Setup and account messages are answered in the app.
    var isRefreshable12305: Bool {
        switch content {
        case .detail, .unreachable: return true
        case .notConfigured, .openApp, .otherAccount, .removed, .gone: return false
        }
    }
}

/// Its own VoiceOver element, outside the widget's combined reading.
struct SavedRefreshButton12305: View {
    var body: some View {
        Button(intent: RefreshSavedWidgetIntent12305()) {
            Image(systemName: "arrow.clockwise")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .frame(width: 24, height: 24)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Refresh")
        .accessibilityHint("Loads a new reading.")
    }
}
