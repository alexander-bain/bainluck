#if DEBUG
import Combine
import SwiftUI

/// Finite local inputs, real Game delivery and real Game/Series sections.
/// This supports #10238's same-sheet clause; it is not production evidence.
/// Native owns the DEBUG entry hook and all Apple execution.
struct EventQuestionMatrixCurrentnessActivation10238: View {
    @StateObject private var model: Activation10238

    init(directory: URL) {
        _model = StateObject(wrappedValue: Activation10238(directory: directory))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Synthetic Game / Series exercise — #10238").font(.headline)
                Text(model.phase).accessibilityIdentifier("BL10238Phase")
                if let error = model.error { Text(error).foregroundStyle(.red) }
                Button("Run changes, then open a Game or Series option") { model.start() }
                    .disabled(!model.ready || model.running || model.finished)
                // These sibling identities stay mounted through nil payloads.
                // Neither phase nor question availability may key these views.
                EventQuestionMatrixSection10238(matrix: model.game?.gameQuestionMatrix, scope: .game)
                EventQuestionMatrixSection10238(matrix: model.series?.seriesQuestionMatrix, scope: .series)
                Text("Two separate runs: open Game Over, then Series Home. 12 seconds to select; 6 seconds per input. Read the actual open sheet. Phase completion is not acceptance.")
                    .font(.caption)
            }.padding()
        }
        .task { await model.prepare() }
        .onDisappear { model.stop() }
    }
}

private final class Activation10238: ObservableObject {
    @Published private(set) var game: GameMarketsResponse?
    @Published private(set) var series: RelatedFuturesResponse?
    @Published private(set) var phase = "Loading local inputs"
    @Published private(set) var error: String?
    @Published private(set) var ready = false
    @Published private(set) var running = false
    @Published private(set) var finished = false

    private let directory: URL
    private var inputs: [ActivationInput10238] = []
    private var feed: ActivationFeed10238?
    private var delivery: GameMarketsPriceDelivery?
    private var runner: Task<Void, Never>?
    private var budgetClock: TimeInterval = 1_000
    private var generation = 0
    private var preparationEpoch: Int?

    private static let names = [
        "01-initial", "02-newer", "03-price-withdrawn", "04-price-restored",
        "05-option-removed", "06-option-restored", "07-question-removed",
        "08-question-restored", "09-game-matrix-absent", "10-series-matrix-absent",
        "11-both-restored", "12-game-final-series-open", "13-series-absent-game-final"
    ]

    init(directory: URL) { self.directory = directory }

    @MainActor func prepare() async {
        guard preparationEpoch == nil, delivery == nil else { return }
        let epoch = generation
        preparationEpoch = epoch
        defer { if preparationEpoch == epoch { preparationEpoch = nil } }
        do {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let bodies = try Self.names.map {
                try decoder.decode(ActivationInput10238.self,
                    from: Data(contentsOf: directory.appendingPathComponent($0 + ".json")))
            }
            guard let first = bodies.first,
                  bodies.allSatisfy({ $0.game.eventId == first.game.eventId && $0.series.eventId == first.game.eventId }),
                  first.game.gameQuestionMatrix?.displayScope == "game",
                  first.series.seriesQuestionMatrix?.displayScope == "series",
                  !(first.game.streamMarketIds ?? []).isEmpty else {
                throw ActivationError10238.invalidInputs
            }
            inputs = bodies
            let feed = ActivationFeed10238(first.game)
            self.feed = feed
            let delivery = GameMarketsPriceDelivery(eventID: first.game.eventId,
                fetch: { id in try await feed.read(id) },
                publish: { [weak self] body in
                    guard let self, self.generation == epoch else { return }
                    self.game = body
                },
                // A local inert wire prevents real network subscription.
                makeHandle: { _ in ActivationWire10238() },
                now: { [weak self] in self?.budgetClock ?? 0 },
                fallbackSleep: { _ in try? await Task.sleep(nanoseconds: 3_600_000_000_000) })
            self.delivery = delivery
            delivery.setVisible(true)
            await delivery.load()
            try Task.checkCancellation()
            guard generation == epoch else { return }
            guard game != nil else { throw ActivationError10238.noPublication }
            // Preserve the real response admission rule, not a new Series fence.
            adoptSeries(first.series)
            ready = true
            phase = Self.names[0]
            record()
        } catch is CancellationError {
            if generation == epoch { stop() }
        } catch {
            if generation == epoch { fail(error) }
        }
    }

    @MainActor func start() {
        guard ready, !running, !finished, let delivery, let feed else { return }
        running = true
        let epoch = generation
        runner = Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                try await Task.sleep(nanoseconds: 12_000_000_000)
                for index in 1..<Self.names.count {
                    try Task.checkCancellation()
                    guard self.generation == epoch else { return }
                    self.budgetClock += 3 // Request budget, never a quote clock.
                    await feed.set(self.inputs[index].game)
                    try Task.checkCancellation()
                    guard self.generation == epoch else { return }
                    await delivery.load()
                    try Task.checkCancellation()
                    guard self.generation == epoch else { return }
                    self.adoptSeries(self.inputs[index].series)
                    self.phase = Self.names[index]
                    self.record()
                    if index < Self.names.count - 1 {
                        try await Task.sleep(nanoseconds: 6_000_000_000)
                    }
                }
                self.running = false
                self.finished = true
                print("BL10238 INPUT_SEQUENCE_FINISHED ui_acceptance=UNVERIFIED")
            } catch is CancellationError {
                // Host departure is cancellation, never a passing exercise.
            } catch {
                if self.generation == epoch { self.fail(error) }
            }
        }
    }

    @MainActor private func adoptSeries(_ incoming: RelatedFuturesResponse) {
        // Same response-level guard as EventDetailViewModel.fetchData(). A
        // series-only empty envelope does not prove production withdrawal.
        if series == nil || incoming.homeTeamFutures != nil || incoming.awayTeamFutures != nil
            || incoming.sharedFutures != nil || incoming.boxScore != nil {
            series = incoming
        }
    }

    @MainActor private func record() {
        // Log actual adopted data; phase names alone cannot establish a pass.
        for (scope, matrix) in [("game", game?.gameQuestionMatrix), ("series", series?.seriesQuestionMatrix)] {
            let question = matrix?.questions.first { $0.questionKey == "synthetic:primary" }
            let key = scope == "game" ? "o:91001" : "o:92001"
            let option = question?.options.first { $0.optionKey == key }
            let value = option?.published.value.map(String.init(describing:)) ?? "nil"
            print("BL10238 phase=\(phase) scope=\(scope) matrix=\(matrix != nil) question=\(question != nil) option=\(option != nil) value=\(value) state=\(option?.published.valueState ?? "absent") ui_acceptance=UNVERIFIED")
        }
    }

    @MainActor private func fail(_ failure: Error) {
        phase = "FAILED — no acceptance"
        error = "Exercise stopped: \(failure)"
        running = false
        ready = false
        delivery?.setVisible(false)
        print("BL10238 FAILED \(failure)")
    }

    @MainActor func stop() {
        generation += 1
        runner?.cancel()
        runner = nil
        delivery?.setVisible(false)
        delivery = nil
        feed = nil
        inputs = []
        preparationEpoch = nil
        game = nil
        series = nil
        finished = false
        phase = "Host left — no acceptance"
        running = false
        ready = false
        print("BL10238 HOST_LEFT ui_acceptance=UNVERIFIED")
    }
}

private struct ActivationInput10238: Decodable {
    let game: GameMarketsResponse
    let series: RelatedFuturesResponse
}

private actor ActivationFeed10238 {
    private var body: GameMarketsResponse
    init(_ body: GameMarketsResponse) { self.body = body }
    func set(_ body: GameMarketsResponse) { self.body = body }
    func read(_ eventID: Int) throws -> GameMarketsResponse {
        guard body.eventId == eventID else { throw ActivationError10238.invalidInputs }
        return body
    }
}

private final class ActivationWire10238: LiveStreamHandle {
    private(set) var isClosed = false
    var isConnecting: Bool { false }
    @MainActor func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
    @MainActor func close() { isClosed = true }
}

private enum ActivationError10238: Error { case invalidInputs, noPublication }
#endif
