import Foundation

/// #4974 — `GET /api/events/{id}/publications`: a finished game's stored
/// probability checkpoints, one vertex per recorded row and nothing between.
///
/// Decoded by `APIClient`'s decoder (`.convertFromSnakeCase`), so the served
/// keys `event_id` / `schema_version` / `time_basis` arrive as the camel-case
/// properties below. The body is exactly five keys and each vertex exactly
/// three (`backend/app/utils/publication_reader.py`).
///
/// These types carry the served values RAW. `t` stays the server's string and
/// `p` the server's double; nothing here parses, rounds, complements or orders
/// anything. Whether a response may be drawn at all is
/// `PublicationJourney4974.adopt`'s question, not the decoder's.
nonisolated struct PublicationCheckpointsResponse: Decodable, Sendable, Equatable {
    let eventId: Int
    let schemaVersion: Int
    /// What `t` means. Slice 1 serves `recorded_at_insert_before_commit`: the
    /// row's insert stamp, taken before commit — a checkpoint, never the
    /// moment the value became public.
    let timeBasis: String
    /// More rows than the server serves; it then sends no vertices at all.
    let truncated: Bool
    /// In the server's order (by `rev`).
    let vertices: [PublicationCheckpointVertex]
}

/// One stored `(rev, recorded_at, blend_probability)` row.
nonisolated struct PublicationCheckpointVertex: Decodable, Sendable, Equatable {
    /// The row's commit-order revision. Signed 64-bit, as stored; a negative
    /// value is refused by adoption, never clamped here.
    let rev: Int64
    /// `recorded_at`, the server's UTC ISO 8601 string, verbatim.
    let t: String
    /// The blended probability as a fraction 0...1, HOME orientation.
    let p: Double
}
