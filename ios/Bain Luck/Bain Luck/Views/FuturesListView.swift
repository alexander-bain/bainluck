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
        NavigationStack {
            VStack(spacing: 0) {
                FuturesCategoryRail(
                    options: categoryOptions,
                    selectedTag: viewModel.selectedCategory,
                    onSelect: selectCategory
                )

                content
            }
            .navigationTitle("Futures")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .navigationDestination(for: Route.self) { RouteDestination(route: $0) }
        }
        .task {
            await viewModel.load()
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
                title: "Couldn't Load Futures",
                message: error,
                systemImage: "wifi.exclamationmark",
                actionTitle: "Try Again",
                action: { Task { await viewModel.load() } }
            )
        } else if viewModel.markets.isEmpty {
            FuturesBrowseStateView(
                title: "No \(selectedCategoryTitle)",
                message: emptyMessage,
                systemImage: "chart.line.uptrend.xyaxis",
                actionTitle: viewModel.selectedCategory.isEmpty ? nil : "Show All",
                action: viewModel.selectedCategory.isEmpty ? nil : { selectCategory("") }
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

            Section {
                ForEach(viewModel.markets) { market in
                    NavigationLink(value: Route.futuresDetail(id: market.id)) {
                        FuturesBrowseMarketRow(market: market)
                    }
                }
            } header: {
                Text(sectionTitle)
            } footer: {
                if !viewModel.hasMore {
                    Text("Showing \(viewModel.markets.count) markets")
                }
            }

            if viewModel.hasMore {
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
        if viewModel.selectedCategory.isEmpty {
            return "All markets"
        }
        return selectedCategoryTitle
    }

    private var emptyMessage: String {
        if viewModel.selectedCategory.isEmpty {
            return "There are no browseable futures markets right now."
        }
        return "No markets matched this category. Try another category or return to all futures."
    }

    private func selectCategory(_ tag: String) {
        guard viewModel.selectedCategory != tag else { return }
        withAnimation(.easeInOut(duration: 0.18)) {
            viewModel.selectedCategory = tag
        }
        viewModel.onCategoryChange()
    }
}
