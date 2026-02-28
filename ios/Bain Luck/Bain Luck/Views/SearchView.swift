import SwiftUI
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "search")

// MARK: - ViewModel

final class SearchViewModel: ObservableObject {
    @Published var query = ""
    @Published var suggestions: [TypeaheadSuggestion] = []
    @Published var results: SearchResponse?
    @Published var loading = false
    @Published var error: String?

    private var debounceTask: Task<Void, Never>?

    @MainActor
    func onQueryChange() {
        debounceTask?.cancel()

        let trimmed = query.trimmingCharacters(in: .whitespaces)
        if trimmed.count < 2 {
            suggestions = []
            results = nil
            return
        }

        debounceTask = Task {
            try? await Task.sleep(nanoseconds: 200_000_000) // 200ms
            guard !Task.isCancelled else { return }
            await fetchTypeahead(trimmed)
        }
    }

    @MainActor
    func search() async {
        debounceTask?.cancel()
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard trimmed.count >= 2 else { return }

        loading = true
        do {
            results = try await APIClient.shared.fetchSearch(query: trimmed)
            suggestions = []
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Search failed: \(error)")
        }
    }

    @MainActor
    private func fetchTypeahead(_ q: String) async {
        do {
            let response = try await APIClient.shared.fetchTypeahead(query: q)
            guard !Task.isCancelled else { return }
            suggestions = response.suggestions
        } catch {
            logger.error("Typeahead failed: \(error)")
        }
    }
}

// MARK: - View

struct SearchView: View {
    @StateObject private var vm = SearchViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                searchField
                    .padding(.horizontal)
                    .padding(.vertical, 8)

                if vm.loading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if let results = vm.results {
                    searchResults(results)
                } else if !vm.suggestions.isEmpty {
                    suggestionList
                } else if vm.query.trimmingCharacters(in: .whitespaces).count >= 2 {
                    Spacer()
                    ContentUnavailableView(
                        "Search",
                        systemImage: "magnifyingglass",
                        description: Text("Press return to search")
                    )
                    Spacer()
                } else {
                    Spacer()
                    ContentUnavailableView(
                        "Search",
                        systemImage: "magnifyingglass",
                        description: Text("Search for teams, games, and futures markets.")
                    )
                    Spacer()
                }
            }
            .navigationTitle("Search")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .eventDetail(let id):
                    EventDetailView(eventId: id)
                case .futuresDetail(let id):
                    FuturesDetailView(marketId: id)
                }
            }
        }
    }

    // MARK: - Search Field

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            TextField("Teams, games, futures...", text: $vm.query)
                .textFieldStyle(.plain)
                .autocorrectionDisabled()
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
                .submitLabel(.search)
                .onSubmit {
                    Task { await vm.search() }
                }
                .onChange(of: vm.query) { _ in
                    vm.onQueryChange()
                }
            if !vm.query.isEmpty {
                Button {
                    vm.query = ""
                    vm.suggestions = []
                    vm.results = nil
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Suggestions

    private var suggestionList: some View {
        List(vm.suggestions) { suggestion in
            Button {
                if suggestion.type == "futures", let marketId = suggestion.marketId {
                    // Navigate directly to futures detail
                    vm.query = suggestion.text
                    vm.results = nil
                    vm.suggestions = []
                    // Use NavigationLink value instead — handle via search
                    vm.query = suggestion.text
                    Task { await vm.search() }
                } else {
                    // For events, trigger a full search
                    vm.query = suggestion.text
                    Task { await vm.search() }
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: suggestion.type == "futures" ? "chart.line.uptrend.xyaxis" : "sportscourt")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(width: 20)
                    Text(suggestion.text)
                        .font(.subheadline)
                        .lineLimit(1)
                    Spacer()
                    Image(systemName: "arrow.up.left")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .buttonStyle(.plain)
        }
        .listStyle(.plain)
    }

    // MARK: - Search Results

    private func searchResults(_ results: SearchResponse) -> some View {
        List {
            if !results.results.isEmpty {
                Section {
                    ForEach(results.results) { event in
                        NavigationLink(value: Route.eventDetail(id: event.id)) {
                            searchEventRow(event)
                        }
                    }
                } header: {
                    Label("Events", systemImage: "sportscourt")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .textCase(nil)
                }
            }

            if !results.futures.isEmpty {
                Section {
                    ForEach(results.futures) { market in
                        NavigationLink(value: Route.futuresDetail(id: market.id)) {
                            searchFuturesRow(market)
                        }
                    }
                } header: {
                    Label("Futures", systemImage: "chart.line.uptrend.xyaxis")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .textCase(nil)
                }
            }

            if results.results.isEmpty && results.futures.isEmpty {
                ContentUnavailableView(
                    "No Results",
                    systemImage: "magnifyingglass",
                    description: Text("No results found for \"\(results.query)\".")
                )
                .listRowBackground(Color.clear)
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }

    // MARK: - Event Row

    private func searchEventRow(_ event: SearchEvent) -> some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text("\(event.awayTeam) vs \(event.homeTeam)")
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    if let sport = event.sport {
                        Text(sportDisplayName(for: sport))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    StatusBadge(status: event.status)
                    if event.status == "scheduled", let ct = event.commenceTime {
                        RelativeTimeText(dateString: ct)
                    }
                }
            }

            Spacer()

            if event.status == "completed" || event.status == "closed" {
                if let away = event.awayScore, let home = event.homeScore {
                    Text("\(away) - \(home)")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .monospacedDigit()
                }
            } else if let odds = event.currentOdds,
                      let home = odds.homeProbability {
                Text(formatProbability(home))
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .monospacedDigit()
                    .foregroundStyle(.blue)
            }

            if let ei = event.ei ?? event.pulse {
                EIBadgeView(ei: ei, size: .sm)
            }
        }
        .padding(.vertical, 2)
    }

    // MARK: - Futures Row

    private func searchFuturesRow(_ market: SearchFuturesMarket) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(market.name)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(2)

            HStack(spacing: 6) {
                if let category = market.llmSportCategory ?? market.category {
                    Text(category.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let source = market.source {
                    Text(source.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            if let outcomes = market.topOutcomes, let top = outcomes.first {
                HStack(spacing: 4) {
                    Text(top.name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let prob = top.probability {
                        Text(formatProbability(prob))
                            .font(.caption)
                            .fontWeight(.medium)
                            .monospacedDigit()
                    }
                }
            }
        }
        .padding(.vertical, 2)
    }
}
