import Foundation

/// #11564 — contract R2 envelopes for page-level preview tests
/// (`docs/contracts/dnpl-authority-v3.md`). A v3 page reads no legacy
/// `preview` event, so these tests open a v3 domain and wrap the same inner
/// frames they always sent in `preview_v3`.
@MainActor
enum V3PageWire {
    static let namespace = "11111111-1111-4111-8111-111111111111"
    private static var sessions = 0

    /// A fresh lowercase stream session, as the server mints one per opening.
    static func nextSession() -> String {
        sessions += 1
        return String(format: "%08x-0000-4000-8000-%012x", sessions, sessions)
    }

    static func open(_ eventId: Int, members: [Int], session: String,
                     incarnation: String = "1", namespace: String = namespace) -> String {
        let rows = members.sorted().map(String.init).joined(separator: ",")
        return """
        {"protocol":3,"event_id":\(eventId),"authority":{"incarnation":"\(incarnation)","namespace":"\(namespace)"},\
        "stream_session":"\(session)","members":[\(rows)]}
        """
    }

    static func preview(_ frame: String, eventId: Int, session: String,
                        incarnation: String = "1", namespace: String = namespace) -> String {
        """
        {"protocol":3,"event_id":\(eventId),"authority":{"incarnation":"\(incarnation)","namespace":"\(namespace)"},\
        "stream_session":"\(session)","frame":\(frame)}
        """
    }
}
