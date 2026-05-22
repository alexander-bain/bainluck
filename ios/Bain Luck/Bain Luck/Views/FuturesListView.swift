import SwiftUI

// MARK: - View

struct FuturesListView: View {
    @StateObject private var viewModel = FuturesListViewModel()

    private var categoryOptions: [FuturesCategoryOption] {
        FuturesCategoryOption.makeOptions(from: viewModel.categoryFacets)
    }

    private var selectedCategoryTitle: String {
        categoryOptions.first { $0.tag == viewModel.selectedCategory }?.title ?? "All markets"
    }

    var body: some View {
        VStack(spacing: 0) {
            FuturesCategoryRail(
                options: categoryOptions,
                selectedTag: viewModel.selectedCategory,
                onSelect: selectCategory
            )

            content
        }
        .navigationTitle("Explore")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.large)
        #endif
        .searchable(text: $viewModel.searchText, prompt: "Search markets")
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Menu {
                    Picker("Sort", selection: $viewModel.sortOption) {
                        ForEach(FuturesBrowseSortOption.allCases) { option in
                            Label(option.label, systemImage: option.icon)
                                .tag(option)
                        }
                    }
                } label: {
                    Label(viewModel.sortOption.label, systemImage: viewModel.sortOption.icon)
                        .font(.subheadline)
                }
            }
        }
        .onChange(of: viewModel.sortOption) { _, _ in
            viewModel.onSortChange()
        }
        .task {
            await viewModel.load()
            await viewModel.loadMovers()
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "futures_list", type: "futures_list")
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.loading {
            FuturesBrowseLoadingView()
        } else if let error = viewModel.error, viewModel.markets.isEmpty {
            FuturesBrowseStateView(
                title: "Couldn't Load Markets",
                message: error,
                systemImage: "wifi.exclamationmark",
                actionTitle: "Try Again",
                action: { Task { await viewModel.load() } }
            )
        } else if viewModel.markets.isEmpty {
            FuturesBrowseStateView(
                title: noResultsTitle,
                message: emptyMessage,
                systemImage: "chart.line.uptrend.xyaxis",
                actionTitle: clearActionTitle,
                action: clearAction
            )
        } else {
            marketList
        }
    }

    private var marketList: some View {
        List {
            if let error = viewModel.error {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .listRowBackground(Color.cardBackground)
                }
            }

            // Movers section — only show when no search and no category filter
            if !viewModel.movers.isEmpty
                && viewModel.selectedCategory.isEmpty
                && viewModel.searchText.isEmpty {
                Section {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 12) {
                            ForEach(viewModel.movers) { mover in
                                NavigationLink(value: Route.futuresDetail(id: mover.marketId)) {
                                    MoverCardView(mover: mover)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal, 4)
                        .padding(.vertical, 4)
                    }
                    .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                    .listRowBackground(Color.clear)
                } header: {
                    HStack(spacing: 6) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.caption2)
                        Text("Biggest Movers")
                        Spacer()
                        Text("24h")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Section {
                ForEach(viewModel.markets) { market in
                    NavigationLink(value: Route.futuresDetail(id: market.id)) {
                        FuturesBrowseMarketRow(market: market)
                    }
                }
            } header: {
                HStack {
                    Text(sectionTitle)
                    Spacer()
                    if !viewModel.searchText.isEmpty {
                        Text("\(viewModel.markets.count) results")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            } footer: {
                if !viewModel.hasMore {
                    Text("Showing \(viewModel.markets.count) markets")
                }
            }

            if let loadMoreError = viewModel.loadMoreError {
                Section {
                    VStack(spacing: 8) {
                        Label(loadMoreError, systemImage: "exclamationmark.triangle.fill")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)

                        Button("Try Again") {
                            Task { await viewModel.loadMore() }
                        }
                        .buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                .listRowBackground(Color.clear)
            } else if viewModel.hasMore {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .listRowBackground(Color.clear)
                    .task {
                        await viewModel.loadMore()
                    }
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await viewModel.load()
        }
    }

    private var sectionTitle: String {
        if !viewModel.searchText.isEmpty {
            return "Search Results"
        }
        if viewModel.selectedCategory.isEmpty {
            return "All markets"
        }
        return selectedCategoryTitle
    }

    private var noResultsTitle: String {
        if !viewModel.searchText.isEmpty {
            return "No Results"
        }
        return "No \(selectedCategoryTitle)"
    }

    private var emptyMessage: String {
        if !viewModel.searchText.isEmpty {
            return "No markets matched \"\(viewModel.searchText)\". Try a different search or clear your filters."
        }
        if viewModel.selectedCategory.isEmpty {
            return "There are no browseable futures markets right now."
        }
        return "No markets matched this category. Try another category or return to all futures."
    }

    private var clearActionTitle: String? {
        if !viewModel.searchText.isEmpty {
            return "Clear Search"
        }
        if !viewModel.selectedCategory.isEmpty {
            return "Show All"
        }
        return nil
    }

    private var clearAction: (() -> Void)? {
        if !viewModel.searchText.isEmpty {
            return { viewModel.searchText = "" }
        }
        if !viewModel.selectedCategory.isEmpty {
            return { selectCategory("") }
        }
        return nil
    }

    private func selectCategory(_ tag: String) {
        guard viewModel.selectedCategory != tag else { return }
        withAnimation(.easeInOut(duration: 0.18)) {
            viewModel.selectedCategory = tag
        }
        viewModel.onCategoryChange()
    }
}

// MARK: - Mover Card

private struct MoverCardView: View {
    let mover: FuturesMover

    private var change: Double? { mover.probabilityChange24h }
    private var isPositive: Bool { (change ?? 0) > 0 }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(mover.marketName ?? "Market")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Text(mover.name)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: 0)

            HStack(alignment: .bottom) {
                if let prob = mover.currentProbability {
                    Text(formatProbability(prob))
                        .font(.subheadline)
                        .fontWeight(.bold)
                        .monospacedDigit()
                }

                Spacer()

                if let change, abs(change) >= 0.005 {
                    HStack(spacing: 2) {
                        Image(systemName: isPositive ? "arrow.up" : "arrow.down")
                            .font(.system(size: 9, weight: .bold))
                        Text(formatProbability(abs(change)))
                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                            .monospacedDigit()
                    }
                    .foregroundStyle(isPositive ? Color.green : Color.red)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(
                        (isPositive ? Color.green : Color.red).opacity(0.12)
                    )
                    .clipShape(Capsule())
                }
            }
        }
        .padding(10)
        .frame(width: 155, height: 110)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.primary.opacity(0.06), lineWidth: 1)
        )
    }
}
