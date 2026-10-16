#if os(iOS)
import EventKit
import EventKitUI
import UIKit

/// #10880 — presents the system's own event editor, prefilled from a
/// ``CalendarEntryDraft10880``.
///
/// PRIVACY IS THE DESIGN, NOT A SETTING. On iOS 17+ `EKEventEditViewController`
/// runs out of process: the reader reviews and saves in system UI, and the app
/// is never granted calendar access. So this file must never:
///
/// - ask for access (`requestFullAccessToEvents`, `requestWriteOnlyAccessToEvents`,
///   `requestAccess`). There is no prompt, at launch or ever.
/// - save, or read anything back (`save`, `events(matching:)`, `calendars(for:)`).
///   Only the editor's own Add button saves.
/// - pick a calendar or an alert. No `calendar` is set and the editor's
///   chooser uses the reader's default. No `EKAlarm` is added; the reader
///   adds one in the editor if they want it. `eventEditViewControllerDefaultCalendarForNewEvents`
///   is deliberately not implemented, because answering it would mean reading
///   the reader's calendars.
///
/// `CalendarFeedCard10880Tests` holds this file to that list.
///
/// The app reports nothing back to the reader. The editor's completion is the
/// only signal of a save, and the editor closing (Add, Cancel or a swipe away)
/// only dismisses it and re-opens the gate. A cancelled editor leaves no entry,
/// because nothing here writes one.
final class CalendarEditorPresenter10880: NSObject, EKEventEditViewDelegate {
    static let shared = CalendarEditorPresenter10880()

    private var gate = CalendarPresentationGate10880()
    /// Weak on purpose: UIKit owns a presented editor, so this becomes nil
    /// once the editor is gone by any route, including one that never calls
    /// the delegate.
    private weak var editor: EKEventEditViewController?

    func present(_ draft: CalendarEntryDraft10880) {
        if gate.state == .open, editor == nil { gate.editorVanished() }
        guard gate.requestOpen() else { return }
        // One main-queue hop so the context menu that sent the tap has
        // finished dismissing before UIKit is asked to present over it.
        DispatchQueue.main.async { [self] in
            guard let host = Self.presentingHost() else {
                gate.didFinish()
                return
            }
            let store = EKEventStore()
            let editor = EKEventEditViewController()
            editor.eventStore = store
            editor.event = Self.event(from: draft, in: store)
            editor.editViewDelegate = self
            self.editor = editor
            host.present(editor, animated: true)
            gate.didPresent()
        }
    }

    func eventEditViewController(
        _ controller: EKEventEditViewController,
        didCompleteWith action: EKEventEditViewAction
    ) {
        controller.dismiss(animated: true)
        gate.didFinish()
    }

    /// The editor's starting values. The start is the served instant itself;
    /// `timeZone` keeps EventKit's default (the device's zone), so the entry
    /// is pinned to that instant and is not a floating time.
    static func event(from draft: CalendarEntryDraft10880, in store: EKEventStore) -> EKEvent {
        let event = EKEvent(eventStore: store)
        event.title = draft.title
        event.startDate = draft.start
        event.endDate = draft.end
        event.url = draft.url
        event.notes = draft.notes
        return event
    }

    /// The top of the foreground-active scene's key window (gotcha #27: Stage
    /// Manager can hand back a background scene). Nil when the top controller
    /// is mid-dismissal, because presenting on it would be refused.
    private static func presentingHost() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }
        guard let window = scene?.keyWindow ?? scene?.windows.first(where: \.isKeyWindow),
              var top = window.rootViewController else { return nil }
        while let presented = top.presentedViewController {
            if presented.isBeingDismissed { return nil }
            top = presented
        }
        return top.isBeingDismissed ? nil : top
    }
}
#endif
