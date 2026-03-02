import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "sportCategory")

// MARK: - ViewModel

@MainActor
final class SportCategoryViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var loading = true
    @Published var error: String?

    let categoryKey: String

    init(categoryKey: String) {
        self.categoryKey = categoryKey
    }

    func load() async {
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        do {
            let feed = try await APIClient.shared.fetchFeed(limit: 200)
            let category = sportCategories.first { $0.id == categoryKey }
            items = feed.items.filter { item in
                category?.matches(item) ?? false
            }
            error = nil
            loading = false
            logger.info("Category \(self.categoryKey) loaded: \(self.items.count) items")
        } catch {
            if isInitial {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("Category feed error: \(error)")
        }
    }

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
}

// MARK: - View

struct SportCategoryView: View {
    let categoryKey: String
    let categoryName: String
    @StateObject private var vm: SportCategoryViewModel
    @EnvironmentObject var pinManager: PinManager

    init(categoryKey: String, categoryName: String) {
        self.categoryKey = categoryKey
        self.categoryName = categoryName
        _vm = StateObject(wrappedValue: SportCategoryViewModel(categoryKey: categoryKey))
    }

    var body: some View {
        Group {
            if vm.loading {
                SkeletonFeedView()
            } else if let error = vm.error, vm.items.isEmpty {
                ContentUnavailableView(
                    "Couldn't Load",
                    systemImage: "wifi.exclamationmark",
                    description: Text(error)
                )
            } else if vm.items.isEmpty {
                ContentUnavailableView(
                    "No \(categoryName) Right Now",
                    systemImage: "calendar",
                    description: Text("Check back later for \(categoryName.lowercased()) events and futures.")
                )
            } else {
                categoryList
            }
        }
        .navigationTitle(categoryName)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .task {
            await vm.load()
        }
        .refreshable {
            await vm.load()
        }
    }

    private var categoryList: some View {
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
                feedSection(title: "Markets", systemImage: "chart.bar.fill", imageColor: .purple, items: vm.topMarkets)
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }

    private func feedSection(title: String, systemImage: String, imageColor: Color, items: [FeedItem]) -> some View {
        Section {
            ForEach(items) { item in
                feedRow(item)
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        pinSwipeButton(item)
                    }
            }
        } header: {
            HStack(spacing: 6) {
                Label(title, systemImage: systemImage)
                    .foregroundStyle(imageColor)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .textCase(nil)
                Text("\(items.count)")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
        }
    }

    @ViewBuilder
    private func feedRow(_ item: FeedItem) -> some View {
        if item.type == "event", let event = item.event {
            NavigationLink(value: Route.eventDetail(id: event.id)) {
                EventCardView(
                    event: event,
                    reason: item.reason,
                    personalizationReasons: item.personalizationReasons,
                    headline: item.headline
                )
            }
            .buttonStyle(.plain)
        } else if item.type == "futures", let futures = item.futures {
            NavigationLink(value: Route.futuresDetail(id: futures.id)) {
                FuturesCardView(futures: futures)
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private func pinSwipeButton(_ item: FeedItem) -> some View {
        if let pinInfo = pinInfo(for: item) {
            let isPinned = pinManager.isPinned(type: pinInfo.type, id: pinInfo.id)
            Button {
                pinManager.togglePin(type: pinInfo.type, id: pinInfo.id)
            } label: {
                Label(isPinned ? "Unpin" : "Pin", systemImage: isPinned ? "bookmark.slash" : "bookmark")
            }
            .tint(isPinned ? .gray : .orange)
        }
    }

    private func pinInfo(for item: FeedItem) -> (type: String, id: Int)? {
        if item.type == "event", let event = item.event {
            return ("event", event.id)
        } else if item.type == "futures", let futures = item.futures {
            return ("future", futures.id)
        }
        return nil
    }
}
