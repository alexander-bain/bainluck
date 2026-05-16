import SwiftUI

struct EventModelsView: View {
    let eventId: Int

    @State private var event: EventDetail?
    @State private var history: EventHistoryResponse?
    @State private var loading = true
    @State private var error: String?

    var body: some View {
        Group {
            if loading {
                ProgressView()
            } else if let error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text(error)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding()
            } else if let event {
                content(event)
            }
        }
        .navigationTitle("Probability Sources")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await load() }
    }

    @ViewBuilder
    private func content(_ event: EventDetail) -> some View {
        ScrollView {
            VStack(spacing: 16) {
                Text("\(event.homeTeam ?? "Home") vs \(event.awayTeam ?? "Away")")
                    .font(.headline)
                    .padding(.top)

                ForEach(sources, id: \.key) { source in
                    sourceCard(source)
                }

                explanationCard
            }
            .padding(.horizontal)
            .padding(.bottom, 32)
        }
    }

    private var sources: [(key: String, info: WinProbSourceInfo, value: Double?)] {
        guard let history else { return [] }
        let sourceInfos = history.winProbSources ?? [:]
        let sourceValues = event?.winProbabilitySources ?? [:]

        return sourceInfos.map { (key, info) in
            let value = sourceValues[key]?.value?.doubleValue
            return (key: key, info: info, value: value)
        }.sorted { ($0.info.displayName ?? "") < ($1.info.displayName ?? "") }
    }

    private func sourceCard(_ source: (key: String, info: WinProbSourceInfo, value: Double?)) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Circle()
                    .fill(Color(hex: source.info.color ?? "#888888"))
                    .frame(width: 10, height: 10)
                Text(source.info.displayName ?? source.key.capitalized)
                    .font(.subheadline.weight(.semibold))
                if let type = source.info.type {
                    Text(type.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.systemGray5, in: Capsule())
                }
                Spacer()
                if let value = source.value {
                    Text("\(Int(value * 100))%")
                        .font(.title3.weight(.bold).monospacedDigit())
                }
            }

            if let methodology = source.info.methodology, !methodology.isEmpty {
                Text(methodology)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let attribution = source.info.attribution, !attribution.isEmpty {
                Text("Source: \(attribution)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding()
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
    }

    private var explanationCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Why multiple sources?", systemImage: "info.circle")
                .font(.subheadline.weight(.semibold))
            Text("Betting markets reflect real money at stake. Statistical models compute from game state alone. Comparing them reveals when the market and the math disagree.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(Color.blue.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }

    private func load() async {
        do {
            async let eventReq = APIClient.shared.fetchEvent(id: eventId)
            async let historyReq = APIClient.shared.fetchEventHistory(id: eventId)
            let (e, h) = try await (eventReq, historyReq)
            event = e
            history = h
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }
}

