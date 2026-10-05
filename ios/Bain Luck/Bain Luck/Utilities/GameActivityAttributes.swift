#if os(iOS) && canImport(ActivityKit)
import ActivityKit
import Foundation

/// The activity keeps one canonical event identity throughout its lifetime.
/// Foreground delivery and source observation clocks are separate concerns.
@available(iOS 16.1, *)
nonisolated struct GameActivityAttributes: ActivityAttributes {
    let eventID: Int

    nonisolated struct ContentState: Codable, Hashable {
        let snapshot: GameActivitySnapshot
    }
}
#endif
