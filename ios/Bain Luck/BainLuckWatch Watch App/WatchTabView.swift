import SwiftUI

struct WatchTabView: View {
    var body: some View {
        NavigationStack {
            #if DEBUG
            if WatchUIFixture.current != nil,
               ProcessInfo.processInfo.environment["BAINLUCK_WATCH_UI_LARGE_TEXT"] == "1" {
                // Layout stress only: watchOS Simulator cannot apply simctl content_size.
                WatchSelectedGameView().dynamicTypeSize(.accessibility5)
            } else {
                WatchSelectedGameView()
            }
            #else
            WatchSelectedGameView()
            #endif
        }
    }
}
