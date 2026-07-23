import SwiftUI

struct WatchTabView: View {
    var body: some View {
        TabView {
            WatchHomeView()
            WatchGuessView()
            WatchGlancesView()
            WatchLiveView()
        }
        .tabViewStyle(.verticalPage)
    }
}
