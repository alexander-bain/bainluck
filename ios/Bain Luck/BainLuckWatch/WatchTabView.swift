import SwiftUI

struct WatchTabView: View {
    var body: some View {
        TabView {
            WatchGuessView()
            WatchGlancesView()
            WatchLiveView()
        }
        .tabViewStyle(.verticalPage)
    }
}
