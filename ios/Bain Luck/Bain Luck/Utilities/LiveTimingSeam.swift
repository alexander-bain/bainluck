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
/// - `preview.received`: a `preview_v3` whose envelope decoded for this page.
///   The reader may still refuse it (wrong session, replay, older epoch), so
///   it too proves receipt only. OFFERED is not adopted.
/// - `model.preview.adopted`: the page's reader now holds that preview
///   (`publishPreview`). Whether the hero prints it is the view mark's to say:
///   a held preview can still be outranked by a newer committed revision.
/// - `model.headline.adopted` / `model.chart.appended`: the view model
///   published the value. MODEL adoption, not pixels.
/// - `view.headline.updated` / `view.chart.updated`: SwiftUI evaluated the
///   event page with that value in hand (an `onChange` in the same update
///   that gives the hero and chart their inputs). They read what the hero and
///   chart actually print — `headline(event)` and `chartFrames(event)` — so a
///   displayed preview, its expiry and the committed fallback each show, with
///   the preview's own identity. Still not a paint: the frame is committed at
///   the end of that main run-loop turn and reaches the glass at a later
///   display refresh, after any number transition.
///
/// A refused, stale, equal or invalid frame emits `frame.received` and nothing
/// else. An adopted value carries its OWN basis — read off the adopted event or
/// frame, never the newest revision the stream has seen.
///
/// IDs, revisions, printed probabilities and source clocks only; no user data.
/// Not a framework: seven event names, no export, no collector.
@MainActor
enum LiveTimingSeam {
    /// One emitted mark. `basis` is `rev:<row>=<n>;…` (rows sorted), else
    /// `clock:<source updated_at>`, else `none`; `null` for an explicit null
    /// folded result; a preview's `v3:<incarnation>/<namespace>/<session>/e<epoch>/s<seq>/b<base_rev>`,
    /// which a folded preview extends with `/o<origin>`, `/f<fold_session>` and
    /// `/m<row>=<rev>;…` (`previewBasis`).
    /// `stamp` is the exact reference-date Double bit pattern or `-`: the chart
    /// edge on chart marks. `probability` is the home probability the mark
    /// speaks for, or `-`; `observed` is its source observation clock as a
    /// stamp, or `-`. Receipt (the observer's own clock), observation and
    /// chart edge stay three separate clocks.
    nonisolated struct Mark: Equatable, Sendable {
        let name: Name
        let eventId: Int
        let path: String
        let basis: String
        let stamp: String
        var probability: String = "-"
        var observed: String = "-"
    }

    nonisolated enum Name: String, Sendable {
        case frameReceived = "frame.received"
        case modelHeadlineAdopted = "model.headline.adopted"
        case modelChartAppended = "model.chart.appended"
        case viewHeadlineUpdated = "view.headline.updated"
        case viewChartUpdated = "view.chart.updated"
        case previewReceived = "preview.received"
        case modelPreviewAdopted = "model.preview.adopted"
    }

    /// Test seam only: sees exactly what is signposted.
    static var observer: ((Mark) -> Void)?

    private static let signposter = OSSignposter(subsystem: "com.bainluck", category: "liveTiming")

    /// Whether any mark would be seen. Work done only to build a mark (the
    /// view's comparison input) waits on this.
    /// The `liveTiming` signposter is ENABLED by default (it is not a
    /// `.dynamicTracing` category), so on an ordinary build this is true and
    /// that work runs on every update; only a log configuration that disables
    /// the category, with no observer, turns it off.
    static var isRecording: Bool { observer != nil || signposter.isEnabled }

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

    nonisolated static func stamp(_ date: Date?) -> String { date.map { stamp($0) } ?? "-" }

    nonisolated static func probability(_ p: Double?) -> String { p.map { String($0) } ?? "-" }

    /// A v3 preview's identity: domain and session, then the epoch, sequence
    /// and page-row base the reader holds it under. A folded preview adds its
    /// ledger origin (v1), its `fold_session` (v2) and its COMPLETE base, so
    /// two folds that differ only in a sibling row never share a name. A part
    /// the message lacks is `-`; a singleton's name has no folded parts.
    nonisolated static func previewBasis(authority: PreviewAuthorityV3?, session: String?,
                                         epoch: Int, seq: Int, baseRev: Int?, origin: Int? = nil,
                                         foldSession: String? = nil, base: FoldRevision? = nil) -> String {
        var name = "v3:\(authority.map { String($0.incarnation) } ?? "-")/\(authority?.namespace ?? "-")/\(session ?? "-")"
            + "/e\(epoch)/s\(seq)/b\(baseRev.map(String.init) ?? "-")"
        if let origin { name += "/o\(origin)" }
        if let foldSession { name += "/f\(foldSession)" }
        if let base {
            name += "/m" + base.rows.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: ";")
        }
        return name
    }

    /// The identity of a received frame: the one the reader would hold it
    /// under. Folded v2 has no epoch or sequence of its own (`BlendPreviewFrame`
    /// sets both to 0); `readerAfterV2` holds it at epoch 0, sequence
    /// `fold_seq`, on the page row's revision in its base — so its receipt is
    /// named the same way, and the adoption and view marks join it exactly.
    nonisolated static func previewBasis(of frame: BlendPreviewFrame, authority: PreviewAuthorityV3?,
                                         session: String?) -> String {
        let v2 = frame.foldedVersion == 2
        return previewBasis(authority: authority, session: session, epoch: v2 ? 0 : frame.epoch,
                            seq: v2 ? frame.foldSeq ?? frame.seq : frame.seq,
                            baseRev: v2 ? frame.baseFoldRevision?.rows[String(frame.eventId)] : frame.baseRev,
                            origin: frame.originEventId, foldSession: frame.foldSession, base: frame.baseFoldRevision)
    }

    /// The identity of the preview `reader` holds. A held fold with no origin
    /// is v2's: its session is the reader's `foldSession`, which every frame
    /// it accepted carried (`readerAfterV2`) and which no session change
    /// outlives (`readerReset`).
    nonisolated static func previewBasis(of held: BlendPreviewState, in reader: BlendPreviewReader) -> String {
        previewBasis(authority: reader.v3Authority, session: reader.v3Session,
                     epoch: held.epoch, seq: held.seq, baseRev: held.baseRev, origin: held.originEventId,
                     foldSession: held.baseFoldRevision != nil && held.originEventId == nil ? reader.foldSession : nil,
                     base: held.baseFoldRevision)
    }

    // MARK: - Marks

    static func frameReceived(_ frame: LiveStreamFrame) {
        let basis = frame.foldedResult
            ? frame.foldedQuote?.quote.map { Self.basis(revision: $0.blendFoldRevision, clock: nil) } ?? "null"
            : Self.basis(revision: frame.rev?.revision, clock: frame.updatedAt)
        emit(Mark(name: .frameReceived, eventId: frame.eventId,
                  path: frame.foldedResult ? "folded" : "raw", basis: basis, stamp: "-"))
    }

    /// A `preview_v3` this page's envelope check accepted, before its reader
    /// decides. `frame` is the envelope's frame as decoded once for the
    /// reader too (`receivePreviewV3`), never a second decode.
    static func previewReceived(_ envelope: PreviewEnvelopeV3, frame: BlendPreviewFrame?, eventId: Int) {
        guard isRecording else { return }
        emit(Mark(name: .previewReceived, eventId: eventId, path: "preview",
                  basis: frame.map { previewBasis(of: $0, authority: envelope.authority, session: envelope.session) }
                    ?? "none",
                  stamp: "-", probability: probability(frame?.p), observed: stamp(frame?.displayObservedAt)))
    }

    static func modelPreviewAdopted(_ held: BlendPreviewState, reader: BlendPreviewReader) {
        emit(Mark(name: .modelPreviewAdopted, eventId: held.eventId, path: "preview",
                  basis: previewBasis(of: held, in: reader), stamp: "-",
                  probability: probability(held.p), observed: stamp(held.observedAt)))
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

    /// What the event page's hero and chart print, compared across updates.
    /// Headline and chart are separate: each carries its own identity (the
    /// displayed preview's, else the committed basis for the headline and `-`
    /// for a committed chart point), value and clock.
    nonisolated struct Presented: Equatable, Sendable {
        let eventId: Int
        let headlineBasis: String
        let probability: Double?
        let observed: Date?
        let chartBasis: String
        let chartEdge: Date?
        let chartProbability: Double?

        /// Compares equal to itself, so a page whose marks nobody can see
        /// never fires its `onChange`.
        static let idle = Presented(eventId: 0, headlineBasis: "-", probability: nil, observed: nil,
                                    chartBasis: "-", chartEdge: nil, chartProbability: nil)
    }

    /// `committed` is the page's event; `headline` and `observed` what its hero
    /// prints (`headline(event)`, `displayedProbabilityObservedAt(event)`);
    /// `chartEnd` the last point its chart draws (`chartFrames(event)`), and
    /// `projected` whether that point is the preview's projection. `preview`
    /// is the identity of the displayed preview, nil when the hero prints
    /// committed truth; it names the chart only when the chart's end is its
    /// projection.
    nonisolated static func presented(committed: EventDetail, headline: EventDetail, observed: Date?,
                                      chartEnd: LiveBlendPoint?, projected: Bool, preview: String?) -> Presented {
        Presented(eventId: committed.id,
                  headlineBasis: preview ?? headlineBasis(of: committed),
                  probability: headline.currentOdds?.homeProbability, observed: observed,
                  chartBasis: projected ? preview ?? "none" : "-",
                  chartEdge: chartEnd?.date, chartProbability: chartEnd?.homeProbability)
    }

    static func viewUpdated(from old: Presented, to new: Presented) {
        guard old.eventId == new.eventId else { return }
        if old.headlineBasis != new.headlineBasis || old.probability != new.probability || old.observed != new.observed {
            emit(Mark(name: .viewHeadlineUpdated, eventId: new.eventId, path: "view",
                      basis: new.headlineBasis, stamp: "-",
                      probability: probability(new.probability), observed: stamp(new.observed)))
        }
        if let edge = new.chartEdge,
           edge != old.chartEdge || new.chartBasis != old.chartBasis || new.chartProbability != old.chartProbability {
            emit(Mark(name: .viewChartUpdated, eventId: new.eventId, path: "view", basis: new.chartBasis,
                      stamp: stamp(edge), probability: probability(new.chartProbability)))
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
        case .previewReceived:
            signposter.emitEvent("preview.received", id: id, "\(message(mark), privacy: .public)")
        case .modelPreviewAdopted:
            signposter.emitEvent("model.preview.adopted", id: id, "\(message(mark), privacy: .public)")
        }
    }

    private static func message(_ mark: Mark) -> String {
        "event=\(mark.eventId) path=\(mark.path) basis=\(mark.basis) stamp=\(mark.stamp)"
            + " p=\(mark.probability) observed=\(mark.observed)"
    }
}
