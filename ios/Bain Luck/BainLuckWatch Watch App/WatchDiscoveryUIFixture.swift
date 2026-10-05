#if DEBUG
import Foundation

/// Reuses the isolated UI-test defaults and production decoder, without network.
extension WatchUIFixture {
    @MainActor func makeDiscoveryStore() -> WatchDiscoveryStore {
        WatchDiscoveryStore(transport: WatchDiscoveryFixtureTransport(offline: offline),
                            defaults: UserDefaults(suiteName: suite)!)
    }
}

private nonisolated struct WatchDiscoveryFixtureTransport: WatchDiscoveryTransport {
    let offline: Bool
    func fetch() async throws -> [WatchDiscoveryReading] {
        if offline { throw URLError(.notConnectedToInternet) }
        let payload = """
        {"items":[
          {"type":"futures","data":{"id":301,"name":"Will inflation fall below 3%?","status":"open","top_outcomes":[{"name":"Yes","probability":0.455,"price_observed_at":"2026-10-05T12:00:00Z"}]}},
          {"type":"futures","data":{"id":302,"name":"Did the mission reach orbit?","resolved":true,"winner":"Yes","top_outcomes":[{"name":"Yes","probability":0.88,"price_observed_at":"2026-10-05T11:50:00Z"}]}},
          {"type":"futures","data":{"id":303,"name":"Will the central bank hold rates?","status":"open","top_outcomes":[{"name":"Hold","probability":0.64}]}}
        ]}
        """
        return try WatchDiscoveryDecoder.decode(Data(payload.utf8))
    }
}
#endif
