import Combine
import Foundation

/// Only known saved IDs are hydrated, at most three at once. Row existence and
/// Remove never depend on metadata or on membership in the followed-team feed.
final class PinManagementViewModel: ObservableObject {
    typealias Lookup = @Sendable (SavedPin) async -> PinMetadata
    @Published private(set) var metadata: [SavedPin: PinMetadata] = [:]
    private let lookup: Lookup
    private var generation = UUID()

    init(lookup: @escaping Lookup = PinManagementViewModel.lookupPin) {
        self.lookup = lookup
    }

    @MainActor
    func load(_ pins: [SavedPin], retryFailed: Bool = false) async {
        let token = UUID()
        generation = token
        metadata = metadata.filter { pins.contains($0.key) }
        let needed = pins.filter { metadata[$0] == nil || (retryFailed && metadata[$0] == .failed) }
        let lookup = lookup
        await withTaskGroup(of: (SavedPin, PinMetadata).self) { group in
            var iterator = needed.makeIterator()
            for _ in 0..<min(3, needed.count) {
                if let pin = iterator.next() { group.addTask { (pin, await lookup(pin)) } }
            }
            while let (pin, result) = await group.next() {
                guard !Task.isCancelled, generation == token else {
                    group.cancelAll()
                    return
                }
                metadata[pin] = result
                if let next = iterator.next() { group.addTask { (next, await lookup(next)) } }
            }
        }
    }

    nonisolated static func lookupPin(_ pin: SavedPin) async -> PinMetadata {
        do {
            if pin.type == "event" {
                let game = try await APIClient.shared.fetchEvent(id: pin.value)
                return .available(title: "\(game.awayTeam) at \(game.homeTeam)")
            }
            let market = try await APIClient.shared.fetchFuturesDetail(id: pin.value)
            return .available(title: market.name)
        } catch APIError.httpError(let code, _) where code == 404 || code == 410 {
            return .unavailable
        } catch {
            return .failed
        }
    }
}
