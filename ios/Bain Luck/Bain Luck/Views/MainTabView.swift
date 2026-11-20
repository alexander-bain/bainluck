import SwiftUI

struct MainTabView: View {
    @EnvironmentObject private var navCoordinator: NavigationCoordinator
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var pinManager: PinManager
    @Environment(\.followManager295A) private var followManager
    @Environment(\.gameAlertsPrompt295A) private var alertsPrompt
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var columnVisibility = NavigationSplitViewVisibility.automatic
    @State private var didApplyLaunchLanding295A = false

    var body: some View {
        // #10878: the Mac gets its own window; iPhone and iPad keep the
        // size-class rule they had.
        switch MacMainWindow10878.root(isMac: MacMainWindow10878.runsOnMac, sizeClass: sizeClass) {
        case .macWindow:
            #if os(macOS)
            MacMainWindowView()
                .modifier(mainTabLandingAndAlerts295A)
            #else
            EmptyView() // unreachable: `root` answers `.macWindow` only on macOS
            #endif
        case .iPadSplit:
            iPadLayout
                .onAppear { navCoordinator.usesSidebarQuickLinks = true }
                .modifier(mainTabLandingAndAlerts295A)
        case .phoneTabs:
            iPhoneLayout
                .onAppear { navCoordinator.usesSidebarQuickLinks = false }
                .modifier(mainTabLandingAndAlerts295A)
        }
    }

    // MARK: - iPhone (Compact)

    private var mainTabLandingAndAlerts295A: some ViewModifier {
        MainTabLandingAndAlertsModifier295A(
            navCoordinator: navCoordinator,
            authManager: authManager,
            pinManager: pinManager,
            followManager: followManager,
            alertsPrompt: alertsPrompt,
            didApplyLaunchLanding295A: $didApplyLaunchLanding295A
        )
    }

    private var iPhoneLayout: some View {
        TabView(selection: $navCoordinator.selectedTab) {
            MyStuffView()
                .tabItem {
                    Label("My Stuff", systemImage: "person.fill")
                }
                .tag(AppTab.myStuff)

            DiscoverView()
                .tabItem {
                    Label("Discover", systemImage: "safari")
                }
                .tag(AppTab.discover)

            FeedView()
                .tabItem {
                    Label("Sports", systemImage: "rectangle.stack.fill")
                }
                .tag(AppTab.feed)
                .badge(navCoordinator.liveGameCount > 0 ? "\(navCoordinator.liveGameCount) live" : nil)

            LeaguesView()
                .tabItem {
                    Label("Browse", systemImage: "square.grid.2x2")
                }
                .tag(AppTab.leagues)

            SearchView()
                .tabItem {
                    Label("Search", systemImage: "magnifyingglass")
                }
                .tag(AppTab.search)
                #if os(macOS)
                .keyboardShortcut("k", modifiers: .command)
                #endif
        }
    }

    // MARK: - iPad (Regular)

    /// Wraps `selectedTab` as optional for `List(selection:)` compatibility.
    private var tabSelection: Binding<AppTab?> {
        Binding(
            get: { MacMainWindow10878.highlightedSidebarTab(for: navCoordinator.selectedTab) },
            set: { newTab in
                guard let tab = newTab else { return }
                DispatchQueue.main.async { navCoordinator.selectedTab = tab }
            }
        )
    }

    private var iPadLayout: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            List(selection: tabSelection) {
                Section {
                    Label("My Stuff", systemImage: "person.fill")
                        .tag(AppTab.myStuff)

                    Label("Discover", systemImage: "safari")
                        .tag(AppTab.discover)

                    HStack {
                        Label("Sports", systemImage: "rectangle.stack.fill")
                        Spacer()
                        if navCoordinator.liveGameCount > 0 {
                            Text("\(navCoordinator.liveGameCount) live")
                                .font(.caption2)
                                .fontWeight(.semibold)
                                .foregroundStyle(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.red)
                                .clipShape(Capsule())
                        }
                    }
                    .tag(AppTab.feed)

                    Label("Browse", systemImage: "square.grid.2x2")
                        .tag(AppTab.leagues)

                    Label("Search", systemImage: "magnifyingglass")
                        .tag(AppTab.search)
                }

                Section("Quick Links") {
                    // Category pages hidden from nav until web parity is achieved (#884).
                    // Views stay in the detail switch for deep-link support.
                    sidebarLabel("Preferences", systemImage: "gearshape")
                        .tag(AppTab.preferences)
                    sidebarLabel(CalibrationView.readerTitle, systemImage: "chart.dots.scatter")
                        .tag(AppTab.calibration)
                }
            }
            .navigationTitle("")
            .toolbar {
                ToolbarItem(placement: .principal) {
                    HStack(spacing: 6) {
                        Text("🍀")
                        Text("Bain Luck")
                            .font(.headline.weight(.semibold))
                    }
                    .lineLimit(1)
                }
            }
            .navigationSplitViewColumnWidth(min: 190, ideal: 220, max: 260)
        } detail: {
            switch navCoordinator.selectedTab {
            case .feed:
                FeedView()
            case .discover:
                DiscoverView()
            case .leagues:
                LeaguesView()
            case .search:
                SearchView()
            case .myStuff:
                MyStuffView()
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

    private func sidebarLabel(_ title: String, systemImage: String) -> some View {
        Label {
            Text(title)
                .lineLimit(1)
                .minimumScaleFactor(0.82)
        } icon: {
            Image(systemName: systemImage)
        }
    }
}

private struct MainTabLandingAndAlertsModifier295A: ViewModifier {
    let navCoordinator: NavigationCoordinator
    @ObservedObject var authManager: AuthManager
    @ObservedObject var pinManager: PinManager
    @ObservedObject var followManager: FollowManager295A
    @ObservedObject var alertsPrompt: GameAlertsPromptController295A
    @Binding var didApplyLaunchLanding295A: Bool

    func body(content: Content) -> some View {
        content
            .onAppear {
                followManager.setAuthenticated(authManager.isAuthenticated)
                guard !didApplyLaunchLanding295A else { return }
                didApplyLaunchLanding295A = true
                navCoordinator.applyLaunchLanding295A(
                    followedCount: followManager.subjects.count,
                    pinnedCount: pinManager.savedPins.count,
                    hasPersistedServerFollows: followManager.hasPersistedServerFollows
                )
            }
            .onChange(of: authManager.isAuthenticated) { _, authed in
                followManager.setAuthenticated(authed)
                if authed {
                    Task {
                        if let prefs = try? await APIClient.shared.fetchPreferences() {
                            followManager.mergeServerFavorites(prefs.favorites)
                        }
                    }
                }
            }
            .modifier(GameAlertsRootSheetModifier295A(controller: alertsPrompt))
    }
}

private struct GameAlertsRootSheetModifier295A: ViewModifier {
    @ObservedObject var controller: GameAlertsPromptController295A

    func body(content: Content) -> some View {
        content.sheet(isPresented: $controller.isSheetPresented) {
            VStack(spacing: 16) {
                Capsule()
                    .fill(Color.secondary.opacity(0.25))
                    .frame(width: 36, height: 4)
                    .padding(.top, 10)

                GameAlertsOfferCard295A(
                    subjectName: controller.sheetSubjectName,
                    onTurnOn: { controller.acceptOffer() },
                    onNotNow: { controller.declineOffer() }
                )
                .padding(.horizontal, 16)

                Spacer(minLength: 8)
            }
            #if os(iOS)
            .presentationDetents([.height(220)])
            .presentationDragIndicator(.hidden)
            #endif
        }
    }
}
