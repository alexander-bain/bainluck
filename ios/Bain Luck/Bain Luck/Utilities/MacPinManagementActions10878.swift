import Foundation
import SwiftUI

/// #10878 / #4931 / #4942 — desktop sheet geometry and right-click row actions
/// for `PinManagementView` (`Manage pins` modal sheet) on macOS.
///
/// ## Why this helper exists
///
/// 1. **Desktop sheet sizing**: On macOS, `PinManagementView` is presented inside
///    `.sheet` from `MyStuffView`, `PinButton`, and `PinFeedbackToast`. Without an
///    explicit minimum frame, a `NavigationStack { List { ... } }` inside an AppKit
///    sheet collapses to a cramped ~200pt box. Applying `MacPinManagementSheetMetrics10878`
///    on `PinManagementView` under `#if os(macOS)` sizes all three presentation
///    sites cleanly while leaving iPhone and iPad untouched.
/// 2. **Keyboard dismissal**: Attaching `.keyboardShortcut(.cancelAction)` to the
///    `"Done"` toolbar button under `#if os(macOS)` lets the reader close the
///    `Manage pins` sheet with `Escape`.
/// 3. **Honest right-click row actions**:
///    - Available game pin (`type == "event"`, `.available(title)`): offers
///      `Copy Title` (only when the hydrated title is non-empty), `Copy Link`,
///      `Open in New Window` (`openWindow(value: pin.value)` so a reader can pop a
///      saved game into a standalone Mac window rather than navigating inside the
///      modal sheet), and `Remove Pin` (omitted while a save/removal is in flight).
///    - Available market pin (`type == "future"`, `.available(title)`): offers
///      `Copy Title` (when non-empty), `Copy Link`, and `Remove Pin`.
///    - Failed detail lookup (`.failed`): offers `Retry Details`, `Copy Link`,
///      `Open in New Window` (for game pins), and `Remove Pin` — never `Copy Title`,
///      because `"Saved game"` / `"Saved market"` is a fallback placeholder rather
///      than the item's title.
///    - Loading detail lookup (`nil`): offers `Copy Link`, `Open in New Window`
///      (for game pins), and `Remove Pin` — never `Copy Title`.
///    - Confirmed-gone item (`.unavailable`, HTTP 404/410): offers **only**
///      `Remove Pin` (when not already saving). Never offers `Copy Link` or
///      `Open in New Window` for an item the server confirmed is no longer listed.
nonisolated enum MacPinManagementSheetMetrics10878: Sendable {
    static let minWidth: CGFloat = 520
    static let idealWidth: CGFloat = 560
    static let minHeight: CGFloat = 420
    static let idealHeight: CGFloat = 480
}

enum MacPinManagementAction10878: Hashable, Sendable {
    case retryDetails
    case copyTitle(String)
    case copyLink(String)
    case openInNewWindow(eventID: Int)
    case removePin(SavedPin)

    /// Returns the context-menu actions for a saved pin row in menu order.
    /// Empty means no context menu should be attached.
    static func actions(
        for pin: SavedPin,
        metadata: PinMetadata?,
        isSaving: Bool = false
    ) -> [MacPinManagementAction10878] {
        guard (pin.type == "event" || pin.type == "future"), pin.value > 0 else {
            return []
        }

        // Confirmed 404/410: the item is no longer listed on the server.
        // Never offer a dead link or a dead detail window; removal is the only
        // honest action, and if removal is already in flight, attach no menu.
        if case .unavailable = metadata {
            return isSaving ? [] : [.removePin(pin)]
        }

        var items: [MacPinManagementAction10878] = []

        switch metadata {
        case .available(let rawTitle):
            let trimmed = rawTitle.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                items.append(.copyTitle(trimmed))
            }
        case .failed:
            items.append(.retryDetails)
        case .unavailable, .none:
            break
        }

        let link = pin.type == "event"
            ? eventShareURL(pin.value)
            : futuresShareURL(pin.value)
        items.append(.copyLink(link))

        if pin.type == "event" {
            items.append(.openInNewWindow(eventID: pin.value))
        }

        if !isSaving {
            items.append(.removePin(pin))
        }

        return items
    }

    var title: String {
        switch self {
        case .retryDetails:
            return "Retry Details"
        case .copyTitle:
            return "Copy Title"
        case .copyLink:
            return "Copy Link"
        case .openInNewWindow:
            return "Open in New Window"
        case .removePin:
            return "Remove Pin"
        }
    }

    var systemImage: String {
        switch self {
        case .retryDetails:
            return "arrow.clockwise"
        case .copyTitle:
            return "doc.on.doc"
        case .copyLink:
            return "link"
        case .openInNewWindow:
            return "macwindow.badge.plus"
        case .removePin:
            return "bookmark.slash"
        }
    }

    var isDestructive: Bool {
        if case .removePin = self { return true }
        return false
    }
}

extension View {
    /// Applies a readable desktop sheet frame to `PinManagementView` on macOS;
    /// no-op on iOS/iPadOS/watchOS.
    @ViewBuilder
    func macPinManagementSheetFrame() -> some View {
        #if os(macOS)
        frame(
            minWidth: MacPinManagementSheetMetrics10878.minWidth,
            idealWidth: MacPinManagementSheetMetrics10878.idealWidth,
            minHeight: MacPinManagementSheetMetrics10878.minHeight,
            idealHeight: MacPinManagementSheetMetrics10878.idealHeight
        )
        #else
        self
        #endif
    }

    /// Binds `Escape` (`.cancelAction`) to the `Manage pins` Done button on macOS;
    /// no-op on iOS/iPadOS/watchOS.
    @ViewBuilder
    func macPinManagementDoneShortcut() -> some View {
        #if os(macOS)
        keyboardShortcut(.cancelAction)
        #else
        self
        #endif
    }

    /// Attaches a Mac right-click context menu to a saved pin row in `PinManagementView`.
    /// On iPhone, iPad, and Watch this returns `self` unchanged.
    @ViewBuilder
    func macPinManagementRowMenu(
        pin: SavedPin,
        metadata: PinMetadata?,
        isSaving: Bool,
        onRetryDetails: @escaping () -> Void,
        onRemove: @escaping () -> Void
    ) -> some View {
        #if os(macOS)
        modifier(
            MacPinManagementRowMenuModifier10878(
                pin: pin,
                metadata: metadata,
                isSaving: isSaving,
                onRetryDetails: onRetryDetails,
                onRemove: onRemove
            )
        )
        #else
        self
        #endif
    }
}

#if os(macOS)
private struct MacPinManagementRowMenuModifier10878: ViewModifier {
    let pin: SavedPin
    let metadata: PinMetadata?
    let isSaving: Bool
    let onRetryDetails: () -> Void
    let onRemove: () -> Void
    @Environment(\.openWindow) private var openWindow

    @ViewBuilder
    func body(content: Content) -> some View {
        let actions = MacPinManagementAction10878.actions(
            for: pin,
            metadata: metadata,
            isSaving: isSaving
        )
        if actions.isEmpty {
            content
        } else {
            let primaryActions = actions.filter { !$0.isDestructive }
            let destructiveActions = actions.filter { $0.isDestructive }
            content.contextMenu {
                ForEach(primaryActions, id: \.self) { action in
                    switch action {
                    case .retryDetails:
                        Button {
                            onRetryDetails()
                        } label: {
                            Label(action.title, systemImage: action.systemImage)
                        }
                    case .copyTitle(let title):
                        Button {
                            copyToClipboard(title)
                        } label: {
                            Label(action.title, systemImage: action.systemImage)
                        }
                    case .copyLink(let link):
                        Button {
                            copyToClipboard(link)
                        } label: {
                            Label(action.title, systemImage: action.systemImage)
                        }
                    case .openInNewWindow(let eventID):
                        Button {
                            openWindow(value: eventID)
                        } label: {
                            Label(action.title, systemImage: action.systemImage)
                        }
                    case .removePin:
                        EmptyView()
                    }
                }
                if !primaryActions.isEmpty && !destructiveActions.isEmpty {
                    Divider()
                }
                ForEach(destructiveActions, id: \.self) { action in
                    if case .removePin = action {
                        Button(role: .destructive) {
                            onRemove()
                        } label: {
                            Label(action.title, systemImage: action.systemImage)
                        }
                    }
                }
            }
        }
    }
}
#endif
