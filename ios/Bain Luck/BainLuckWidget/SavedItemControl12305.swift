#if os(iOS)
import AppIntents
import SwiftUI
import WidgetKit

// #12305 — "My game": one press in Control Center, on the Lock Screen or on the
// Action button opens the saved game or market the reader chose. The choice is
// one of THEIR saved items, from the same bridge and entity the saved widget
// uses (#10875); a choice that is no longer theirs to open lands on My Stuff.

@available(iOS 18.0, *)
struct SelectSavedItemControlIntent12305: ControlConfigurationIntent {
    static var title: LocalizedStringResource = "Choose a saved game or market"
    static var description = IntentDescription("Open one of your saved games or markets in one press.")

    @Parameter(title: "Game or market")
    var item: SavedItemEntity10875?

    init() {}
}

/// The control's label and link: the chosen item's own title, never a number
/// (a price on a control would sit there unrefreshed), and its page while it is
/// the reader's saved item. The app reloads the control whenever the saved
/// items change, so a game unsaved or saved under another account since setup
/// is relabeled and relinked to My Stuff.
@available(iOS 18.0, *)
struct SavedItemControlProvider12305: AppIntentControlValueProvider {
    struct Value {
        let title: String
        let url: URL
    }

    func previewValue(configuration: SelectSavedItemControlIntent12305) -> Value {
        Value(title: configuration.item?.title ?? "My game", url: SavedWidgetControlLink12305.myStuff)
    }

    func currentValue(configuration: SelectSavedItemControlIntent12305) async throws -> Value {
        guard let item = configuration.item else {
            return Value(title: "My game", url: SavedWidgetControlLink12305.myStuff)
        }
        let snapshot = SavedItemWidgetFetch10875.bridge
        return Value(title: SavedWidgetControlLink12305.title(entityID: item.id, chosenTitle: item.title, snapshot: snapshot),
                     url: SavedWidgetControlLink12305.url(entityID: item.id, snapshot: snapshot))
    }
}

@available(iOS 18.0, *)
struct SavedItemControl12305: ControlWidget {
    var body: some ControlWidgetConfiguration {
        AppIntentControlConfiguration(kind: SavedWidgetBridge10875.controlKind,
                                      provider: SavedItemControlProvider12305()) { value in
            ControlWidgetButton(action: OpenSavedItemIntent12305(link: value.url)) {
                Label(value.title, systemImage: "bookmark.fill")
            }
        }
        .displayName("My game")
        .description("Open one of your saved games or markets.")
        .promptsForUserConfiguration()
    }
}
#endif
