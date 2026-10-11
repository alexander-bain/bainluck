import Foundation
import os

/// #10090 — the installed-iPhone timing seam: when a pushed price arrived, when
/// the page's model adopted it, and when the view was handed it, each mark keyed
/// by event id and the revision basis of the value it speaks for.
///
/// Build 49 could not testify: it logged refusals and errors only, so a
/// tethered trace saw numbers change with no revision identity and no
/// receive/adopt boundary. These are `OSSignposter` events in the
/// `com.bainluck` / `liveTiming` log; `xctrace --template Logging` (or `log
/// collect --device`) records them on the phone's own clock.
///
/// WHAT EACH MARK PROVES — and what it does not:
/// - `frame.received`: a frame decoded off the stream. The owner may still
///   refuse it, so it proves receipt only.
/// - `model.headline.adopted` / `model.chart.appended`: the view model
///   published the value. MODEL adoption, not pixels.
/// - `view.headline.updated` / `view.chart.updated`: SwiftUI evaluated the
///   event page with that value in hand (an `onChange` in the same update
///   that gives the hero and chart their inputs). Still not a paint: the frame
///   is committed at the end of that main run-loop turn and reaches the glass
///   at a later display refresh, after any number transition.
///
/// A refused, stale, equal or invalid frame emits `frame.received` and nothing
/// else. An adopted value carries its OWN basis — read off the adopted event or
/// frame, never the newest revision the stream has seen.
///
/// IDs, revisions and source clocks only; no user data. Not a framework: five
/// event names, no export, no collector.
@MainActor
enum LiveTimingSeam {
    /// One emitted mark. `basis` is `rev:<row>=<n>;…` (rows sorted), else
    /// `clock:<source updated_at>`, else `none`; `null` for an explicit null
    /// folded result. `stamp` is the exact reference-date Double bit pattern or `-`.
    nonisolated struct Mark: Equatable, Sendable {
        let name: Name
        let eventId: Int
        let path: String
        let basis: String
        let stamp: String
    }

    nonisolated enum Name: String, Sendable {
        case frameReceived = "frame.received"
        case modelHeadlineAdopted = "model.headline.adopted"
        case modelChartAppended = "model.chart.appended"
        case viewHeadlineUpdated = "view.headline.updated"
        case viewChartUpdated = "view.chart.updated"
    }

    /// Test seam only: sees exactly what is signposted.
    static var observer: ((Mark) -> Void)?

    private static let signposter = OSSignposter(subsystem: "com.bainluck", category: "liveTiming")

    // MARK: - Basis

    nonisolated static func basis(revision: FoldRevision?, clock: String?) -> String {
        if let revision {
            return "rev:" + revision.rows.sorted { $0.key < $1.key }
                .map { "\($0.key)=\($0.value)" }.joined(separator: ";")
        }
        if let clock { return "clock:\(clock)" }
        return "none"
    }

    /// The basis of the headline an event carries: the provenance adoption
    /// wrote beside the value (`adoptFrameProvenance`, `adoptingFoldedQuote`).
    nonisolated static func headlineBasis(of event: EventDetail) -> String {
        basis(revision: event.blendFoldRevision?.revision, clock: event.heroProbabilityObservedAt)
    }

    nonisolated static func stamp(_ date: Date) -> String {
        String(date.timeIntervalSinceReferenceDate.bitPattern)
    }

    // MARK: - Marks

    static func frameReceived(_ frame: LiveStreamFrame) {
        let basis = frame.foldedResult
            ? frame.foldedQuote?.quote.map { Self.basis(revision: $0.blendFoldRevision, clock: nil) } ?? "null"
            : Self.basis(revision: frame.rev?.revision, clock: frame.updatedAt)
        emit(Mark(name: .frameReceived, eventId: frame.eventId,
                  path: frame.foldedResult ? "folded" : "raw", basis: basis, stamp: "-"))
    }

    static func modelHeadlineAdopted(_ event: EventDetail, path: String) {
        emit(Mark(name: .modelHeadlineAdopted, eventId: event.id, path: path,
                  basis: headlineBasis(of: event), stamp: "-"))
    }

    static func modelChartAppended(eventId: Int, path: String, basis: String, at date: Date) {
        emit(Mark(name: .modelChartAppended, eventId: eventId, path: path, basis: basis, stamp: stamp(date)))
    }

    /// A read moved the headline only if its value or provenance differs from
    /// the one already shown; the first load is not an adoption.
    static func readAdopted(prior: EventDetail?, fetched: EventDetail) {
        guard let prior, prior.id == fetched.id,
              prior.currentOdds?.homeProbability != fetched.currentOdds?.homeProbability
                || headlineBasis(of: prior) != headlineBasis(of: fetched) else { return }
        modelHeadlineAdopted(fetched, path: "read")
    }

    // MARK: - View

    /// What the event page hands its hero and chart, compared across updates.
    nonisolated struct Presented: Equatable, Sendable {
        let eventId: Int
        let revision: FoldRevision?
        let clock: String?
        let chartEdge: Date?
    }

    nonisolated static func presented(_ event: EventDetail, liveBlend: [LiveBlendPoint]) -> Presented {
        Presented(eventId: event.id, revision: event.blendFoldRevision?.revision,
                  clock: event.heroProbabilityObservedAt, chartEdge: liveBlend.last?.date)
    }

    static func viewUpdated(from old: Presented, to new: Presented) {
        guard old.eventId == new.eventId else { return }
        if old.revision != new.revision || old.clock != new.clock {
            emit(Mark(name: .viewHeadlineUpdated, eventId: new.eventId, path: "view",
                      basis: basis(revision: new.revision, clock: new.clock), stamp: "-"))
        }
        if let edge = new.chartEdge, edge != old.chartEdge {
            emit(Mark(name: .viewChartUpdated, eventId: new.eventId, path: "view", basis: "-", stamp: stamp(edge)))
        }
    }

    // MARK: - Emission

    private static func emit(_ mark: Mark) {
        observer?(mark)
        guard signposter.isEnabled else { return }
        // `emitEvent` takes a static name, hence the switch.
        let id = signposter.makeSignpostID()
        switch mark.name {
        case .frameReceived:
            signposter.emitEvent("frame.received", id: id, "\(message(mark), privacy: .public)")
        case .modelHeadlineAdopted:
            signposter.emitEvent("model.headline.adopted", id: id, "\(message(mark), privacy: .public)")
        case .modelChartAppended:
            signposter.emitEvent("model.chart.appended", id: id, "\(message(mark), privacy: .public)")
        case .viewHeadlineUpdated:
            signposter.emitEvent("view.headline.updated", id: id, "\(message(mark), privacy: .public)")
        case .viewChartUpdated:
            signposter.emitEvent("view.chart.updated", id: id, "\(message(mark), privacy: .public)")
        }
    }

    private static func message(_ mark: Mark) -> String {
        "event=\(mark.eventId) path=\(mark.path) basis=\(mark.basis) stamp=\(mark.stamp)"
    }
}
