import SwiftUI

// MARK: - View

struct FuturesListView: View {
    @StateObject private var vm = FuturesListViewModel()

    private var categoryOptions: [FuturesCategoryOption] {
        FuturesCategoryOption.makeOptions(from: vm.categoryFacets)
    }

    private var selectedCategoryTitle: String {
        categoryOptions.first { $0.tag == vm.selectedCategory }?.title ?? "All markets"
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                FuturesCategoryRail(
                    options: categoryOptions,
                    selectedTag: vm.selectedCategory,
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
            await vm.load()
        }
        .onAppear {
            AnalyticsService.trackScreen(name: "futures_list", type: "futures_list")
        }
    }

    @ViewBuilder
    private var content: some View {
        if vm.loading {
            FuturesBrowseLoadingView()
        } else if let error = vm.error, vm.markets.isEmpty {
            FuturesBrowseStateView(
                title: "Couldn't Load Futures",
                message: error,
                systemImage: "wifi.exclamationmark",
                actionTitle: "Try Again",
                action: { Task { await vm.load() } }
            )
        } else if vm.markets.isEmpty {
            FuturesBrowseStateView(
                title: "No \(selectedCategoryTitle)",
                message: emptyMessage,
                systemImage: "chart.line.uptrend.xyaxis",
                actionTitle: vm.selectedCategory.isEmpty ? nil : "Show All",
                action: vm.selectedCategory.isEmpty ? nil : { selectCategory("") }
            )
        } else {
            marketList
        }
    }

    private var marketList: some View {
        List {
            if let error = vm.error {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .listRowBackground(Color.cardBackground)
                }
            }

            Section {
                ForEach(vm.markets) { market in
                    NavigationLink(value: Route.futuresDetail(id: market.id)) {
                        FuturesBrowseMarketRow(market: market)
                    }
                }
            } header: {
                Text(sectionTitle)
            } footer: {
                if !vm.hasMore {
                    Text("Showing \(vm.markets.count) markets")
                }
            }

            if vm.hasMore {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .listRowBackground(Color.clear)
                    .task {
                        await vm.loadMore()
                    }
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable {
            await vm.load()
        }
    }

    private var sectionTitle: String {
        if vm.selectedCategory.isEmpty {
            return "All markets"
        }
        return selectedCategoryTitle
    }

    private var emptyMessage: String {
        if vm.selectedCategory.isEmpty {
            return "There are no browseable futures markets right now."
        }
        return "No markets matched this category. Try another category or return to all futures."
    }

    private func selectCategory(_ tag: String) {
        guard vm.selectedCategory != tag else { return }
        withAnimation(.easeInOut(duration: 0.18)) {
            vm.selectedCategory = tag
        }
        vm.onCategoryChange()
    }
}
