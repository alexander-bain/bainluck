import SwiftUI

struct WatchQuestionDetailView: View {
    @Environment(\.scenePhase) private var scenePhase
    let destination: WatchQuestionDetailDestination
    let close: () -> Void
    var originLabel: String = "From your story"
    var backLabel: String = "Back to story"
    @StateObject private var store = WatchQuestionDetailStore()
    @State private var refreshID = 0
    @State private var outcomeSearch = ""

    private var matchingDetail: WatchQuestionDetail? {
        guard let detail = store.detail, detail.id == destination.id else { return nil }
        return detail
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                let heading = destination.heading(detail: matchingDetail)
                Text(heading.text).font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if heading.retained { Text(originLabel).font(.footnote) }
                if let detail = matchingDetail {
                    let matches = detail.outcomes(matching: outcomeSearch)
                    if detail.outcomes.count > 1 || !outcomeSearch.isEmpty {
                        TextField("Find an outcome", text: $outcomeSearch)
                            .frame(minHeight: 44)
                            .accessibilityLabel("Find an outcome by name")
                            .accessibilityIdentifier("watch.question.search")
                    }
                    if !outcomeSearch.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Text("Matching outcomes: \(matches.count)").font(.footnote)
                        Button("Show all outcomes") { outcomeSearch = "" }
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("watch.question.clear-search")
                    }
                    ForEach(matches) { outcome in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(outcome.name).font(.body.bold())
                            Text(outcome.reading)
                            Text(outcome.clock).font(.footnote)
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("watch.question.outcome.\(outcome.id)")
                    }
                    if detail.outcomes.isEmpty { Text("No available outcomes for this question.") }
                    else if matches.isEmpty { Text("No outcomes match your search.") }
                    if detail.hasOmittedOutcomes { Text("Some outcomes are unavailable.").font(.footnote) }
                }
                let status = store.requestStatus(for: destination.id)
                if status.loading { ProgressView("Loading question") }
                if let error = status.error { Text(error) }
                Button("Refresh") { refreshID += 1 }
                    .disabled(status.loading || scenePhase != .active)
                Button(backLabel, action: close)
            }.padding(.horizontal, 6)
        }
        .accessibilityIdentifier("watch.question.detail")
        .task(id: "\(destination.id):\(scenePhase):\(refreshID)") {
            guard scenePhase == .active else { return }
            await store.load(id: destination.id)
        }
        .onChange(of: destination.id) { _, _ in outcomeSearch = "" }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { store.cancel() }
        }
        .onDisappear { store.cancel() }
    }
}
