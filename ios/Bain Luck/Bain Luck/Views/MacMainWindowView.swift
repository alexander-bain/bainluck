import SwiftUI

/// #10878 — the Mac main window's rules, kept out of the macOS-only view so the
/// iOS-hosted `BainLuckTests` can run them. The view below is the only part that
/// exists solely on macOS.
///
/// Before this, `MainTabView` chose its root from the size class alone, so a Mac
/// window got whichever of the phone tab bar or the iPad split the environment
/// happened to report, and Search / My Stuff took their single phone column
/// across a desktop-wide window.
enum MacMainWindow10878 {

    /// Which root `MainTabView` mounts.
    enum Root: Equatable {
        case phoneTabs
        case iPadSplit
        case macWindow
    }

    /// The Mac gets its own window no matter what size class it reports; iPhone
    /// and iPad keep exactly the rule they had (regular ⇒ split, anything else
    /// ⇒ tabs).
    static func root(isMac: Bool, sizeClass: UserInterfaceSizeClass?) -> Root {
        if isMac { return .macWindow }
        return sizeClass == .regular ? .iPadSplit : .phoneTabs
    }

    static var runsOnMac: Bool {
        #if os(macOS)
        return true
        #else
        return false
        #endif
    }

    // MARK: - Sidebar

    struct SidebarItem: Identifiable, Hashable {
        let tab: AppTab
        let title: String
        let systemImage: String
        var id: AppTab { tab }
    }

    /// The five places the phone's tab bar has, in the same order and with the
    /// same names, so a reader moving between phone and Mac finds them.
    static let destinations: [SidebarItem] = [
        SidebarItem(tab: .discover, title: "Discover", systemImage: "safari"),
        SidebarItem(tab: .feed, title: "Sports", systemImage: "rectangle.stack.fill"),
        SidebarItem(tab: .leagues, title: "Browse", systemImage: "square.grid.2x2"),
        SidebarItem(tab: .search, title: "Search", systemImage: "magnifyingglass"),
        SidebarItem(tab: .myStuff, title: "My Stuff", systemImage: "person.fill"),
    ]

    /// The iPad sidebar's Quick Links, unchanged.
    static let quickLinks: [SidebarItem] = [
        SidebarItem(tab: .preferences, title: "Preferences", systemImage: "gearshape"),
        SidebarItem(tab: .calibration, title: CalibrationView.readerTitle, systemImage: "chart.dots.scatter"),
    ]

    /// Category pages are hidden from navigation until web parity (#884), as
    /// on iPad. They stay in the detail switch so nothing that selects them
    /// lands on an empty window.
    static let detailOnlyTabs: Set<AppTab> = [.futures, .weather, .economics, .politics, .entertainment]

    /// The same words the phone tab bar and iPad sidebar print.
    static func liveBadge(count: Int) -> String? {
        count > 0 ? "\(count) live" : nil
    }

    /// A click on empty sidebar space deselects the list; keep the reader where
    /// they are instead of blanking the window. Deferred like the iPad's
    /// binding so the write never lands inside a view update.
    @MainActor
    static func applySelection(_ proposed: AppTab?, to coordinator: NavigationCoordinator) {
        guard let tab = proposed, tab != coordinator.selectedTab else { return }
        DispatchQueue.main.async { coordinator.selectedTab = tab }
    }

    // MARK: - Layout

    /// The shared screens choose their wide layouts (masonry grids, two-column
    /// search results) on `.regular`. A desktop window is that wide family.
    static let detailSizeClass: UserInterfaceSizeClass = .regular

    /// Widest the detail column grows. A normal laptop window (1200 wide, ideal
    /// sidebar) is narrower than this, so it is untouched; a wide desktop
    /// window centres a readable column instead of stretching cards edge to
    /// edge. Not narrower than Discover's own 800pt cap on Mac, so Discover is
    /// never squeezed by it.
    static let readableContentWidth: CGFloat = 1100

    static let sidebarMinWidth: CGFloat = 180
    static let sidebarIdealWidth: CGFloat = 220
    static let sidebarMaxWidth: CGFloat = 280

    /// The narrowest window supported. Below this the window stops shrinking
    /// rather than shrinking text or clipping actions.
    static let minimumWindowSize = CGSize(width: 800, height: 600)

    /// The narrowest detail width the iPad's `.regular` layouts already serve
    /// (portrait iPad with its sidebar open), so at the minimum window with the
    /// widest sidebar the Mac never asks them for less.
    static let narrowestRegularDetailWidth: CGFloat = 500
}

#if os(macOS)
/// #10878 — the Mac main window: a native sidebar with the phone's five places
/// and the iPad's Quick Links, and one destination mounted at a time in a
/// readable detail column. Only the selected screen is mounted, as on iPad, so
/// no offscreen screen keeps its tasks or subscriptions alive.
///
/// What a reader had on Discover, Search and My Stuff — results, the open
/// detail, how far they had read — is kept for them in `readingState`, above
/// the mount, so switching away and back returns them to the same place.
struct MacMainWindowView: View {
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @EnvironmentObject private var authManager: AuthManager
    @State private var columnVisibility = NavigationSplitViewVisibility.all
    /// Per window, so a second window keeps its own places.
    @State private var readingState = MacReadingState10878()

    private var selection: Binding<AppTab?> {
        Binding(
            get: { navCoordinator.selectedTab },
            set: { MacMainWindow10878.applySelection($0, to: navCoordinator) }
        )
    }

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            List(selection: selection) {
                Section {
                    ForEach(MacMainWindow10878.destinations) { item in
                        sidebarRow(item)
                            .badge(item.tab == .feed ? liveBadge : nil)
                    }
                }
                Section("Quick Links") {
                    ForEach(MacMainWindow10878.quickLinks) { item in
                        sidebarRow(item)
                    }
                }
            }
            .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(
                min: MacMainWindow10878.sidebarMinWidth,
                ideal: MacMainWindow10878.sidebarIdealWidth,
                max: MacMainWindow10878.sidebarMaxWidth
            )
        } detail: {
            let places = readingState.places(for: authManager.activeFeedUserId)
            destination(for: navCoordinator.selectedTab, places: places)
                // A new account rebuilds the screen on view too, so nothing the
                // previous account had open survives on it.
                .id(places.generation)
                .environment(\.horizontalSizeClass, MacMainWindow10878.detailSizeClass)
                .frame(maxWidth: MacMainWindow10878.readableContentWidth)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(
            minWidth: MacMainWindow10878.minimumWindowSize.width,
            minHeight: MacMainWindow10878.minimumWindowSize.height
        )
    }

    private var liveBadge: Text? {
        MacMainWindow10878.liveBadge(count: navCoordinator.liveGameCount).map { Text($0) }
    }

    private func sidebarRow(_ item: MacMainWindow10878.SidebarItem) -> some View {
        Label(item.title, systemImage: item.systemImage)
            .lineLimit(1)
            .tag(item.tab)
    }

    /// The iPad detail switch, destination for destination. Exhaustive, so a
    /// new `AppTab` cannot be added without deciding what the Mac shows.
    @ViewBuilder
    private func destination(for tab: AppTab, places: MacReadingState10878.Places) -> some View {
        switch tab {
        case .feed:
            FeedView()
        case .discover:
            DiscoverView(macPlace: places.discover)
        case .leagues:
            LeaguesView()
        case .search:
            SearchView(macPlace: places.search)
        case .myStuff:
            MyStuffView(macPlace: places.myStuff)
        case .futures:
            NavigationStack { FuturesListView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
        case .weather:
            NavigationStack { WeatherView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
        case .economics:
            NavigationStack { EconomicsView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
        case .politics:
            NavigationStack { PoliticsView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
        case .entertainment:
            NavigationStack { EntertainmentView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
        case .preferences:
            NavigationStack { PreferencesView() }
        case .calibration:
            NavigationStack { CalibrationView().navigationDestination(for: Route.self) { RouteDestination(route: $0) } }
        }
    }
}
#endif
