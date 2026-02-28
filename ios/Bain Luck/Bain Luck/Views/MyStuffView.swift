import Combine
import SwiftUI
import os

private let logger = Logger(subsystem: "com.bainluck", category: "mystuff")

// MARK: - ViewModel

@MainActor
final class MyStuffViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var loading = true
    @Published var error: String?

    private var refreshTimer: Timer?

    var liveNow: [FeedItem] {
        items.filter { $0.event?.status == "live" }
    }

    var justHappened: [FeedItem] {
        items.filter {
            let s = $0.event?.status
            return s == "completed" || s == "closed"
        }
    }

    var upcoming: [FeedItem] {
        items.filter {
            guard $0.type == "event" else { return false }
            let s = $0.event?.status
            return s == "scheduled" || s == nil
        }
    }

    var topMarkets: [FeedItem] {
        items.filter { $0.type == "futures" }
    }

    var hasLiveGames: Bool { !liveNow.isEmpty }

    func load() async {
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        do {
            let feed = try await APIClient.shared.fetchFeed(myTeamsOnly: true)
            items = feed.items
            error = nil
            loading = false
            logger.info("My Stuff feed loaded: \(feed.items.count) items")
            configureAutoRefresh()
        } catch {
            if isInitial {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("My Stuff feed error: \(error)")
        }
    }

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        guard hasLiveGames else { return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.load()
            }
        }
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}

// MARK: - View

struct MyStuffView: View {
    @EnvironmentObject var authManager: AuthManager
    @StateObject private var vm = MyStuffViewModel()
    @State private var path = NavigationPath()
    @State private var showOnboarding = false

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if authManager.isLoading {
                    ProgressView()
                } else if !authManager.isAuthenticated {
                    signInView
                } else if authManager.user?.onboardingCompleted != true {
                    onboardingPromptView
                } else {
                    teamFeedView
                }
            }
            .navigationTitle("My Stuff")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .toolbar {
                if authManager.isAuthenticated {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button {
                            authManager.signOut()
                            vm.items = []
                        } label: {
                            Text("Sign Out")
                                .font(.subheadline)
                        }
                    }
                }
            }
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .eventDetail(let id):
                    EventDetailView(eventId: id)
                case .futuresDetail(let id):
                    FuturesDetailView(marketId: id)
                case .eiRankings:
                    EIRankingsView()
                }
            }
        }
    }

    // MARK: - State 1: Sign In

    private var signInView: some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "person.crop.circle")
                .font(.system(size: 56))
                .foregroundStyle(.secondary)

            Text("See your teams in one place")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Sign in to follow teams and get personalized odds.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            Button {
                authManager.signInWithApple()
            } label: {
                HStack {
                    Image(systemName: "apple.logo")
                    Text("Sign in with Apple")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .foregroundStyle(.white)
                .background(.black)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .padding(.horizontal, 40)

            if let error = authManager.error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }

            Spacer()
        }
    }

    // MARK: - State 2: Onboarding Prompt

    private var onboardingPromptView: some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "sportscourt.fill")
                .font(.system(size: 56))
                .foregroundStyle(.blue)

            Text("Follow some teams to get started")
                .font(.title2)
                .fontWeight(.semibold)

            Text("Tell us what you're into and we'll personalize your feed.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            if let name = authManager.user?.displayName ?? authManager.user?.email {
                Text("Signed in as \(name)")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }

            Button {
                showOnboarding = true
            } label: {
                Text("Get Started")
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .foregroundStyle(.white)
                    .background(.blue)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .padding(.horizontal, 40)

            Spacer()
        }
        .fullScreenCover(isPresented: $showOnboarding) {
            OnboardingView()
                .environmentObject(authManager)
        }
    }

    // MARK: - State 3: Team Feed

    private var teamFeedView: some View {
        Group {
            if vm.loading {
                ProgressView("Loading your teams...")
            } else if let error = vm.error, vm.items.isEmpty {
                ContentUnavailableView(
                    "Couldn't Load Feed",
                    systemImage: "wifi.exclamationmark",
                    description: Text(error)
                )
            } else if vm.items.isEmpty {
                ContentUnavailableView(
                    "No Games Right Now",
                    systemImage: "sportscourt",
                    description: Text("Your teams don't have any games coming up.")
                )
            } else {
                teamFeedList
            }
        }
        .task {
            await vm.load()
        }
        .onDisappear {
            vm.stopRefresh()
        }
    }

    private var teamFeedList: some View {
        List {
            if !vm.liveNow.isEmpty {
                feedSection(title: "Live Now", systemImage: "circle.fill", imageColor: .red, items: vm.liveNow)
            }
            if !vm.justHappened.isEmpty {
                feedSection(title: "Just Happened", systemImage: "clock.arrow.circlepath", imageColor: .secondary, items: vm.justHappened)
            }
            if !vm.upcoming.isEmpty {
                feedSection(title: "Upcoming", systemImage: "calendar", imageColor: .blue, items: vm.upcoming)
            }
            if !vm.topMarkets.isEmpty {
                feedSection(title: "Top Markets", systemImage: "chart.bar.fill", imageColor: .purple, items: vm.topMarkets)
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await vm.load()
        }
    }

    // MARK: - Section Builder

    private func feedSection(title: String, systemImage: String, imageColor: Color, items: [FeedItem]) -> some View {
        Section {
            ForEach(items) { item in
                feedRow(item)
            }
        } header: {
            Label(title, systemImage: systemImage)
                .foregroundStyle(imageColor)
                .font(.subheadline)
                .fontWeight(.semibold)
                .textCase(nil)
        }
    }

    // MARK: - Row

    @ViewBuilder
    private func feedRow(_ item: FeedItem) -> some View {
        if item.type == "event", let event = item.event {
            Button {
                path.append(Route.eventDetail(id: event.id))
            } label: {
                EventCardView(event: event, reason: item.reason)
            }
            .buttonStyle(.plain)
        } else if item.type == "futures", let futures = item.futures {
            Button {
                path.append(Route.futuresDetail(id: futures.id))
            } label: {
                FuturesCardView(futures: futures)
            }
            .buttonStyle(.plain)
        }
    }
}
