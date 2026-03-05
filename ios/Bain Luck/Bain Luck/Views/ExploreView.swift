import Combine
import SwiftUI
import os

private let logger = Logger(subsystem: "com.bainluck", category: "explore")

// MARK: - Namespace Config

private let nsLabels: [String: String] = [
    "sport": "Sport",
    "importance": "Importance",
    "signal": "Signal",
    "timing": "Timing",
    "stakes": "Stakes",
    "narrative": "Narrative",
    "audience": "Audience",
    "tier": "Tier",
    "competitive_structure": "Structure",
    "league": "League",
    "status": "Status",
    "ei": "EI",
    "source": "Source",
]

private let nsOrder = [
    "stakes", "narrative", "audience", "importance",
    "signal", "sport", "timing", "competitive_structure",
]

private func nsColor(_ ns: String) -> Color {
    switch ns {
    case "sport": return .blue
    case "importance": return .purple
    case "signal": return .green
    case "timing": return .cyan
    case "stakes": return .red
    case "narrative": return .orange
    case "audience": return .teal
    case "tier", "competitive_structure": return .indigo
    default: return .secondary
    }
}

private func tagLabel(_ tag: String) -> String {
    let val = tag.split(separator: ":", maxSplits: 1).last.map(String.init) ?? tag
    return val.replacingOccurrences(of: "_", with: " ").capitalized
}

// MARK: - Tab

enum ExploreTab: String, CaseIterable {
    case events = "Events"
    case futures = "Futures"
}

// MARK: - ViewModel

@MainActor
final class ExploreViewModel: ObservableObject {
    @Published var tab: ExploreTab = .events
    @Published var selectedTags: [String] = []
    @Published var page = 1
    @Published var loading = false
    @Published var error: String?

    // Events
    @Published var eventsResponse: FacetedEventsResponse?

    // Futures
    @Published var futuresResponse: FacetedFuturesResponse?

    var facets: [String: [FacetTag]] {
        switch tab {
        case .events: return eventsResponse?.facets ?? [:]
        case .futures: return futuresResponse?.facets ?? [:]
        }
    }

    var total: Int {
        switch tab {
        case .events: return eventsResponse?.total ?? 0
        case .futures: return futuresResponse?.total ?? 0
        }
    }

    var totalPages: Int {
        max(1, Int(ceil(Double(total) / 20.0)))
    }

    func toggleTag(_ tag: String) {
        if let idx = selectedTags.firstIndex(of: tag) {
            selectedTags.remove(at: idx)
        } else {
            selectedTags.append(tag)
        }
        page = 1
        Task { await load() }
    }

    func clearTags() {
        selectedTags.removeAll()
        page = 1
        Task { await load() }
    }

    func switchTab(_ newTab: ExploreTab) {
        guard tab != newTab else { return }
        tab = newTab
        page = 1
        Task { await load() }
    }

    func goToPage(_ p: Int) {
        page = p
        Task { await load() }
    }

    func load() async {
        loading = true
        do {
            switch tab {
            case .events:
                eventsResponse = try await APIClient.shared.fetchFacetedEvents(tags: selectedTags, page: page)
            case .futures:
                futuresResponse = try await APIClient.shared.fetchFacetedFutures(tags: selectedTags, page: page)
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
            logger.error("Explore load failed: \(error)")
        }
        loading = false
    }
}

// MARK: - View

struct ExploreView: View {
    @StateObject private var vm = ExploreViewModel()
    @State private var path = NavigationPath()
    @State private var showFacetSheet = false

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                // Tab bar + active filters
                headerControls
                    .padding(.horizontal)
                    .padding(.vertical, 8)

                if vm.loading && vm.eventsResponse == nil && vm.futuresResponse == nil {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if let error = vm.error, vm.total == 0 {
                    ContentUnavailableView(
                        "Error",
                        systemImage: "exclamationmark.triangle",
                        description: Text(error)
                    )
                } else {
                    resultsList
                }
            }
            .navigationTitle("Explore")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showFacetSheet = true
                    } label: {
                        Image(systemName: "line.3.horizontal.decrease.circle")
                    }
                }
            }
            .sheet(isPresented: $showFacetSheet) {
                facetSheet
            }
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .eventDetail(let id):
                    EventDetailView(eventId: id)
                case .futuresDetail(let id):
                    FuturesDetailView(marketId: id)
                case .eiRankings:
                    EIRankingsView()
                case .preferences:
                    PreferencesView()
                case .sportCategory(let key, let name):
                    SportCategoryView(categoryKey: key, categoryName: name)
                }
            }
            .task {
                await vm.load()
            }
            .refreshable {
                await vm.load()
            }
            .onAppear {
                AnalyticsService.trackScreen(name: "explore", type: "explore")
            }
        }
    }

    // MARK: - Header

    private var headerControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Tab picker
            HStack(spacing: 2) {
                ForEach(ExploreTab.allCases, id: \.self) { tab in
                    Button {
                        vm.switchTab(tab)
                    } label: {
                        Text(tab.rawValue)
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 7)
                            .background(vm.tab == tab ? Color.primary.opacity(0.12) : Color.clear)
                            .foregroundStyle(vm.tab == tab ? .primary : .secondary)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(3)
            .background(Color(.secondarySystemGroupedBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))

            // Active filters
            if !vm.selectedTags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(vm.selectedTags, id: \.self) { tag in
                            let ns = tag.split(separator: ":").first.map(String.init) ?? ""
                            Button {
                                vm.toggleTag(tag)
                            } label: {
                                HStack(spacing: 3) {
                                    Text(tagLabel(tag))
                                        .font(.caption2)
                                        .fontWeight(.medium)
                                    Image(systemName: "xmark")
                                        .font(.system(size: 7, weight: .bold))
                                }
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(nsColor(ns).opacity(0.12))
                                .foregroundStyle(nsColor(ns))
                                .clipShape(Capsule())
                            }
                            .buttonStyle(.plain)
                        }
                        Button {
                            vm.clearTags()
                        } label: {
                            Text("Clear")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .underline()
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    // MARK: - Results

    private var resultsList: some View {
        List {
            // Count + pagination header
            Section {
                HStack {
                    if vm.loading {
                        ProgressView()
                            .scaleEffect(0.8)
                        Text("Loading...")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Text("\(vm.total) \(vm.tab == .events ? "events" : "markets")")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if vm.totalPages > 1 {
                        paginationControls
                    }
                }
            }
            .listRowBackground(Color.clear)

            // Event rows
            if vm.tab == .events, let response = vm.eventsResponse {
                if response.events.isEmpty && !vm.loading {
                    ContentUnavailableView(
                        "No Events",
                        systemImage: "magnifyingglass",
                        description: Text("No events match these filters.")
                    )
                    .listRowBackground(Color.clear)
                } else {
                    ForEach(response.events) { event in
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            EventCardView(event: event, reason: nil)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            // Futures rows
            if vm.tab == .futures, let response = vm.futuresResponse {
                if response.markets.isEmpty && !vm.loading {
                    ContentUnavailableView(
                        "No Markets",
                        systemImage: "chart.bar",
                        description: Text("No futures markets match these filters.")
                    )
                    .listRowBackground(Color.clear)
                } else {
                    ForEach(response.markets) { market in
                        NavigationLink(value: Route.futuresDetail(id: market.id)) {
                            facetedFuturesRow(market)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }

    // MARK: - Pagination

    private var paginationControls: some View {
        HStack(spacing: 8) {
            Button {
                vm.goToPage(max(1, vm.page - 1))
            } label: {
                Image(systemName: "chevron.left")
                    .font(.caption2)
            }
            .disabled(vm.page <= 1)

            Text("\(vm.page)/\(vm.totalPages)")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .monospacedDigit()

            Button {
                vm.goToPage(min(vm.totalPages, vm.page + 1))
            } label: {
                Image(systemName: "chevron.right")
                    .font(.caption2)
            }
            .disabled(vm.page >= vm.totalPages)
        }
        .foregroundStyle(.primary)
    }

    // MARK: - Faceted Futures Row

    private func facetedFuturesRow(_ market: FacetedFuturesMarket) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if let cat = market.llmSportCategory {
                    Text(cat.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if let source = market.source {
                    sourceBadge(source)
                }
            }

            Text(market.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)

            if let outcomes = market.topOutcomes?.prefix(3) {
                VStack(spacing: 3) {
                    ForEach(Array(outcomes)) { outcome in
                        HStack {
                            Text(outcome.name)
                                .font(.caption)
                                .lineLimit(1)
                            Spacer()
                            if let m = outcome.movement, abs(m) >= 0.005 {
                                HStack(spacing: 1) {
                                    Image(systemName: m > 0 ? "arrow.up" : "arrow.down")
                                        .font(.system(size: 7))
                                    Text(formatProbability(abs(m)))
                                        .font(.system(size: 9))
                                }
                                .foregroundStyle(m > 0 ? .green : .red)
                            }
                            if let prob = outcome.probability {
                                Text(formatProbability(prob))
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .monospacedDigit()
                            }
                        }
                    }
                }
            }

            if let total = market.outcomeCount, let shown = market.topOutcomes?.count, total > shown {
                Text("+\(total - shown) more")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 4)
    }

    private func sourceBadge(_ source: String) -> some View {
        let label: String
        let color: Color
        switch source {
        case "polymarket":
            label = "Polymarket"
            color = .blue
        case "kalshi":
            label = "Kalshi"
            color = Color(hex: "#22c55e")
        case "odds_api":
            label = "Sportsbooks"
            color = Color(hex: "#d97706")
        default:
            label = source.capitalized
            color = .gray
        }
        return Text(label)
            .font(.system(size: 9, weight: .medium))
            .foregroundStyle(color)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(color.opacity(0.12))
            .clipShape(Capsule())
    }

    // MARK: - Facet Sheet

    private var facetSheet: some View {
        NavigationStack {
            List {
                let sorted = sortedNamespaces
                if sorted.isEmpty {
                    ContentUnavailableView(
                        "No Filters",
                        systemImage: "line.3.horizontal.decrease",
                        description: Text("No tag facets available for the current view.")
                    )
                    .listRowBackground(Color.clear)
                } else {
                    ForEach(sorted, id: \.self) { ns in
                        if let tags = vm.facets[ns], !tags.isEmpty {
                            Section {
                                ForEach(tags.prefix(15), id: \.tag) { facet in
                                    let active = vm.selectedTags.contains(facet.tag)
                                    Button {
                                        vm.toggleTag(facet.tag)
                                    } label: {
                                        HStack {
                                            Image(systemName: active ? "checkmark.circle.fill" : "circle")
                                                .font(.subheadline)
                                                .foregroundStyle(active ? nsColor(ns) : .secondary)
                                            Text(tagLabel(facet.tag))
                                                .font(.subheadline)
                                                .foregroundStyle(active ? .primary : .secondary)
                                            Spacer()
                                            Text("\(facet.count)")
                                                .font(.caption2)
                                                .foregroundStyle(.tertiary)
                                                .monospacedDigit()
                                        }
                                    }
                                    .buttonStyle(.plain)
                                }
                            } header: {
                                Text(nsLabels[ns] ?? ns.capitalized)
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .textCase(.uppercase)
                                    .foregroundStyle(nsColor(ns))
                            }
                        }
                    }
                }
            }
            #if os(iOS)
            .listStyle(.insetGrouped)
            #endif
            .navigationTitle("Filters")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if !vm.selectedTags.isEmpty {
                        Button("Clear All") {
                            vm.clearTags()
                        }
                        .font(.subheadline)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        showFacetSheet = false
                    }
                    .fontWeight(.semibold)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private var sortedNamespaces: [String] {
        vm.facets.keys.sorted { a, b in
            let ai = nsOrder.firstIndex(of: a) ?? 99
            let bi = nsOrder.firstIndex(of: b) ?? 99
            return ai < bi
        }
    }
}
