import SwiftUI

struct WatchAwardsView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var browser = WatchAwardsStore()
    @State private var action: Task<Void, Never>?
    @State private var question: WatchQuestionDetailDestination?
    @State private var categorySearch = ""
    let close: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(browser.page?.name ?? browser.ceremony?.name ?? "Awards")
                    .font(.headline).accessibilityAddTraits(.isHeader)
                if browser.ceremony == nil {
                    Text("Choose a ceremony to see its available categories.").font(.footnote)
                    ForEach(WatchAwardsCeremony.allCases) { ceremony in
                        Button(ceremony.name) { start { await browser.open(ceremony) } }
                            .disabled(scenePhase != .active)
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("watch.awards.ceremony.\(ceremony.id)")
                    }
                } else {
                    if let page = browser.page {
                        if page.isSaved {
                            Text("Previously received ceremony · refresh to confirm").font(.footnote)
                        }
                        let matches = page.categories(matching: categorySearch)
                        if page.categories.count > 1 || !categorySearch.isEmpty {
                            TextField("Find a category", text: $categorySearch)
                                .frame(minHeight: 44)
                                .accessibilityLabel("Find an awards category by name")
                                .accessibilityIdentifier("watch.awards.search")
                        }
                        if !categorySearch.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                            Text("Matching categories: \(matches.count)").font(.footnote)
                            Button("Show all categories") { categorySearch = "" }
                                .frame(minHeight: 44)
                                .accessibilityIdentifier("watch.awards.clear-search")
                        }
                        ForEach(matches) { category in
                            Button {
                                guard scenePhase == .active,
                                      let current = browser.category(id: category.id) else { return }
                                question = .init(id: current.id, question: current.name)
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(category.name).font(.body)
                                    if category.resultUnconfirmed {
                                        Text("Category result unconfirmed").font(.footnote)
                                    }
                                    Text("Read category and nominees").font(.footnote)
                                }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                            }
                            .disabled(scenePhase != .active || browser.isLoading)
                            .accessibilityIdentifier("watch.awards.category.\(category.id)")
                        }
                        if page.categories.isEmpty { Text("No available categories for this ceremony.") }
                        else if matches.isEmpty { Text("No categories match your search.") }
                        if page.hasUnavailableCategories {
                            Text("Some ceremony information is unavailable.").font(.footnote)
                        }
                    }
                    if browser.isLoading { ProgressView("Loading ceremony") }
                    if let error = browser.errorMessage { Text(error).font(.footnote) }
                    Button("Refresh") { start { await browser.refresh() } }
                        .disabled(browser.isLoading || scenePhase != .active)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("watch.awards.refresh")
                    Button("All ceremonies") { action?.cancel(); browser.browse() }
                        .frame(minHeight: 44)
                }
                Button("Back to Discoveries", action: close).frame(minHeight: 44)
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 6)
        }
        .accessibilityIdentifier("watch.awards.browser")
        .sheet(item: $question) { destination in
            WatchQuestionDetailView(destination: destination, close: { question = nil },
                originLabel: "From your ceremony", backLabel: "Back to ceremony")
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await browser.refresh()
        }
        .onChange(of: browser.ceremony) { _, _ in categorySearch = "" }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { action?.cancel(); browser.cancel(); question = nil }
        }
        .onDisappear { action?.cancel(); browser.cancel() }
    }

    private func start(_ operation: @escaping @MainActor () async -> Void) {
        action?.cancel()
        action = Task { await operation() }
    }
}
