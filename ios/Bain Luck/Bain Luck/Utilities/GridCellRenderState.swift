import Foundation

// MARK: - Championship-grid cell state (#7557)
//
// THE DEFECT THIS FILE EXISTS FOR. `/api/playoffs/{league}` publishes a typed
// `state` on every grid cell (queue 295 / L2-227, served since #7387 went live
// at v4821), and `GridCell` did not decode it. Every rung therefore took
// `LadderRungState`'s default `.open` and printed `ladderPercent(nil)` — "—",
// the app's own NO-MARKET glyph — on cells the venue has already GRADED.
// Measured on the 17:04Z 2026-09-20 MLB payload, not inferred: 120 cells, of
// which 7 `won` and 46 `eliminated`, and all 53 of those carry
// `merged_probability: null`. Milwaukee has clinched its division; the MIL
// DIVISION rung read "—". The web grid drew ✓ on the same cell.
//
// The app was one field short of correct: `LadderRungState` has had `.clinched`
// and `.eliminated` since it was written, and both `trailingValue` and `bar`
// already draw them (✓ over a filled deep-ink track, ✕ over an empty one).
//
// THIS IS THE SWIFT TWIN OF `frontend/lib/gridCellState.ts` and is deliberately
// the same shape, because the two surfaces drifting apart is the class of bug
// that produced #7536 and this one: five reader states frozen by the C108
// contract corpus (`backend/tests/evals/fixtures/grid_register_contract.json`
// → `application_repair_contract.reader_states`), `clinched` accepted as an
// alias for `won`, and FAIL CLOSED throughout — a state this build does not
// recognise is a cell we cannot vouch for, never a cell we guess about.
// `frontend/__tests__/ios/gridCellStateParity7557.test.ts` reds CI when one
// surface learns a state the other has not.
//
// Identity/rendering only: no ranking, blending, probability or weighting
// decision lives here.

/// The five reader states a championship-grid cell can be in.
nonisolated enum GridCellRenderState: String, Sendable, CaseIterable {
    /// Trading. The only state that carries a number.
    case live
    /// Authoritative terminal result — the outcome was achieved.
    case won
    /// Authoritative terminal result — the outcome is impossible.
    case eliminated
    /// Registered, but the source market is not currently there.
    case missing
    /// The cell cannot be vouched for (malformed / out of contract).
    case unavailable

    /// The venue has graded this cell. A terminal cell carries a RESULT and
    /// never a price — "settled means settled".
    var isTerminal: Bool { self == .won || self == .eliminated }
}

extension GridCellRenderState {
    /// A served `state` string, read fail-closed. One reading for every surface
    /// that carries the register — the grid cell here, and since #8691 the
    /// Championship Path stage — so the two cannot disagree about a word.
    static func declared(_ state: String?) -> GridCellRenderState? {
        guard let state else { return nil }
        if let known = GridCellRenderState(rawValue: state) { return known }
        // The register vocabulary is won/eliminated; "clinched" is the web and
        // native DISPLAY word for the same thing. Accept it so a future
        // producer using the display word cannot silently degrade the cell to
        // `unavailable`. (Same clause as `readDeclaredState` on the web side.)
        if state == "clinched" { return .won }
        return .unavailable
    }
}

extension GridCell {
    /// The state the payload declared, read fail-closed.
    ///
    /// `nil` means the payload declared nothing at all — a pre-register cached
    /// response — which is the one case where the number alone decides. An
    /// unrecognised string is `.unavailable`, never `.live`: this build cannot
    /// say what a state it has never heard of means.
    var declaredRenderState: GridCellRenderState? {
        GridCellRenderState.declared(state)
    }

    /// What a reader should be shown for this cell.
    var renderState: GridCellRenderState {
        guard let declared = declaredRenderState else {
            // Pre-register payload: infer from the number alone, the way every
            // build before the register did.
            return usableProbability == nil ? .missing : .live
        }
        // A cell declared live with no usable number cannot be SHOWN as live:
        // there is nothing to draw. Fail closed rather than draw a zero.
        if declared == .live && usableProbability == nil { return .unavailable }
        return declared
    }

    /// The probability a reader may be shown. Non-nil ONLY when the cell is
    /// live, so a graded cell can never hand a percentage to a renderer.
    var publishedProbability: Double? {
        renderState == .live ? usableProbability : nil
    }

    /// The 24-hour trend a reader may be shown. Non-nil ONLY when the cell is
    /// live — a settled cell has stopped moving, so a delta beside it is a
    /// claim about a market that is no longer trading.
    var publishedTrend24H: Double? {
        guard renderState == .live, let trend = trend24H, trend.isFinite else { return nil }
        return trend
    }

    /// A probability is usable only if it is a real number inside [0, 1]. NaN,
    /// infinity and an out-of-contract 1.4 are not numbers this app draws.
    private var usableProbability: Double? {
        guard let value = mergedProbability, value.isFinite, value >= 0, value <= 1 else {
            return nil
        }
        return value
    }
}
