#if DEBUG
import SwiftUI

/// Bounded, local-only activation for #10236's still-unpaid mounted change
/// clause. Native supplies the DEBUG entry hook and ten retained JSON inputs.
/// This is the real matrix and delivery/reconciliation path; the source of
/// inputs and wire are synthetic. It does not certify production or a phone.
struct EventPropsMatrixCurrentnessActivation10236: View {
    @StateObject private var model: Activation10236

    init(directory: URL) {
        _model = StateObject(wrappedValue: Activation10236(directory: directory))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Synthetic currentness exercise — #10236")
                    .font(.headline)
                Text(model.phase).accessibilityIdentifier("BL10236Phase")
                if let error = model.error {
                    Text(error).foregroundStyle(.red)
                }
                Button("Run changes, then open Judge 2+ hits") { model.start() }
                    .disabled(!model.ready || model.running || model.finished)
                // Never key this view by phase or replace it during a step:
                // its own sheet selection and scroll positions must survive.
                if let props = model.value?.duringPlayerProps {
                    EventPropsMatrixView(props: props)
                }
                Text("12 seconds to open the question, then 6 seconds per step. Read the actual sheet and retain video plus BL10236 logs. Phase text alone is not UI proof.")
                    .font(.caption)
            }.padding()
        }
        .task { await model.prepare() }
        .onDisappear { model.stop() }
    }
}

@MainActor
private final class Activation10236: ObservableObject {
    @Published private(set) var value: GameMarketsResponse?
    @Published private(set) var phase = "Loading local inputs"
    @Published private(set) var error: String?
    @Published private(set) var ready = false
    @Published private(set) var running = false
    @Published private(set) var finished = false

    private let directory: URL
    private var inputs: [GameMarketsResponse] = []
    private var feed: ActivationFeed10236?
    private var delivery: GameMarketsPriceDelivery?
    private var wire = ActivationWire10236()
    private var runner: Task<Void, Never>?
    private var budgetClock: TimeInterval = 1_000
    private var generation = 0

    private static let names = [
        "01-initial", "02-newer-changed", "03-older-refused",
        "04-repeated-heartbeat-no-restamp", "05-equal-value-new-observation",
        "06-equal-revision-conflict-refused", "07-explicit-withdrawal",
        "08-withdrawn-old-quote-no-resurrection", "09-new-evidence-restoration",
        "10-selected-question-removed"
    ]
    private static let question = "s:aaron judge|hits|full_game|ge:2|over"

    init(directory: URL) { self.directory = directory }

    func prepare() async {
        guard delivery == nil else { return }
        let epoch = generation
        do {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let bodies = try Self.names.map { name in
                try decoder.decode(GameMarketsResponse.self,
                    from: Data(contentsOf: directory.appendingPathComponent(name + ".json")))
            }
            guard let first = bodies.first,
                  bodies.allSatisfy({ $0.eventId == first.eventId && $0.duringPlayerProps != nil }),
                  first.duringPlayerProps?.rows.contains(where: { $0.questionKey == Self.question }) == true,
                  !(first.streamMarketIds ?? []).isEmpty else {
                throw ActivationError10236.invalidInputs
            }
            inputs = bodies
            let feed = ActivationFeed10236(first)
            self.feed = feed
            let delivery = GameMarketsPriceDelivery(eventID: first.eventId,
                fetch: { id in try await feed.read(id) },
                publish: { [weak self] in self?.value = $0 },
                makeHandle: { [weak self] _ in
                    guard let self else { throw ActivationError10236.stopped }
                    self.wire = ActivationWire10236()
                    return self.wire
                },
                now: { [weak self] in self?.budgetClock ?? 0 },
                // No wall-clock polling races the explicit finite sequence.
                // Cancellation still releases this sleep at host departure.
                fallbackSleep: { _ in try? await Task.sleep(nanoseconds: 3_600_000_000_000) })
            self.delivery = delivery
            delivery.setVisible(true)
            await delivery.load()
            guard generation == epoch, !Task.isCancelled else { return }
            guard value != nil else { throw ActivationError10236.noPublication }
            ready = true
            phase = Self.names[0]
            await record()
        } catch {
            guard generation == epoch else { return }
            fail(error)
        }
    }

    func start() {
        guard ready, !running, !finished, let delivery, let feed else { return }
        running = true
        let epoch = generation
        runner = Task { [weak self] in
            guard let self else { return }
            do {
                try await Task.sleep(nanoseconds: 12_000_000_000)
                for index in 1..<Self.names.count {
                    try Task.checkCancellation()
                    guard self.generation == epoch else { return }
                    // Request-budget time is deliberately not a quote clock.
                    self.budgetClock += 3
                    if index == 3 {
                        let before = self.value
                        let reads = await feed.readCount
                        guard self.wire.emit("heartbeat", "") else {
                            throw ActivationError10236.heartbeatNotDelivered
                        }
                        // Give any accidentally queued read a chance to run.
                        try await Task.sleep(nanoseconds: 200_000_000)
                        guard self.value == before, await feed.readCount == reads else {
                            throw ActivationError10236.heartbeatChangedProjection
                        }
                    } else {
                        await feed.set(self.inputs[index])
                        // Actor suspension may have allowed host departure.
                        // load() permits hidden reads, so recheck before it.
                        try Task.checkCancellation()
                        guard self.generation == epoch else { return }
                        await delivery.load()
                    }
                    try Task.checkCancellation()
                    guard self.generation == epoch else { return }
                    self.phase = Self.names[index]
                    await self.record()
                    if index < Self.names.count - 1 {
                        try await Task.sleep(nanoseconds: 6_000_000_000)
                    }
                }
                self.running = false
                self.finished = true
                // Keep the final unavailable detail mounted for observation.
                // Completion means inputs delivered, not UI acceptance.
                print("BL10236 INPUT_SEQUENCE_FINISHED ui_acceptance=UNVERIFIED")
            } catch is CancellationError {
                // Leaving the host cancels the finite exercise, not a pass.
            } catch {
                guard self.generation == epoch else { return }
                self.fail(error)
            }
        }
    }

    private func record() async {
        let row = value?.duringPlayerProps?.rows.first { $0.questionKey == Self.question }
        let probability = row?.current.probability.map(String.init(describing:)) ?? "nil"
        let observed = row?.current.observedAt ?? "nil"
        let reads = await feed?.readCount ?? 0
        let state = row?.current.state ?? "absent"
        print("BL10236 phase=\(phase) question=\(Self.question) row_present=\(row != nil) state=\(state) probability=\(probability) observed=\(observed) reads=\(reads) ui_acceptance=UNVERIFIED")
    }

    private func fail(_ failure: Error) {
        error = "Exercise stopped: \(failure)"
        phase = "FAILED — no acceptance"
        running = false
        ready = false
        delivery?.setVisible(false)
        print("BL10236 FAILED \(failure)")
    }

    func stop() {
        generation += 1
        runner?.cancel()
        runner = nil
        delivery?.setVisible(false)
        running = false
        ready = false
        print("BL10236 HOST_LEFT ui_acceptance=UNVERIFIED")
    }
}

private actor ActivationFeed10236 {
    private var body: GameMarketsResponse
    private(set) var readCount = 0
    init(_ body: GameMarketsResponse) { self.body = body }
    func set(_ body: GameMarketsResponse) { self.body = body }
    func read(_ eventID: Int) throws -> GameMarketsResponse {
        guard body.eventId == eventID else { throw ActivationError10236.invalidInputs }
        readCount += 1
        return body
    }
}

@MainActor
private final class ActivationWire10236: LiveStreamHandle {
    private var handlers: [String: @MainActor (String) -> Void] = [:]
    private(set) var isClosed = false
    var isConnecting: Bool { false }
    func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
        handlers[event] = handler
    }
    func emit(_ event: String, _ raw: String) -> Bool {
        guard !isClosed, let handler = handlers[event] else { return false }
        handler(raw)
        return true
    }
    func close() { isClosed = true; handlers.removeAll() }
}

private enum ActivationError10236: Error {
    case invalidInputs, stopped, noPublication, heartbeatNotDelivered, heartbeatChangedProjection
}
#endif
