import Foundation

// #8959 — the phone's Accuracy screen says what the website says about how
// current its numbers are.
//
// ## The defect this closes
//
// Web decides its banner in `frontend/lib/calibrationStaleness.ts`
// (`decideCalibrationStaleness`), which reads three things the server
// publishes: `availability`, the `staged` block dating the market data behind
// the curve (#2007), and the `producer` verdict on the hourly beat (#2649).
// Native decoded only `cache`, which a fallback tier attaches and the main tier
// never does. So on 2026-09-26 22:40Z production served `availability: "stale"`,
// `staged.frozen_over_drift: true`, `staged_at` 15 hours earlier and
// `cache: null`: the website read "The curve is current. The data behind it is
// older. … last staged Sep 26, 12:31 AM (14 hr ago)", and the phone showed the
// same curve with no banner at all.
//
// It had also drifted on the one state it did render. A fallback-tier serve of
// a current curve is documented steady state (`main` is evicted ahead of
// `last_good`), and web stopped calling that "not being refreshed right now"
// under #4046; the phone kept saying it. And its cadence sentence still carried
// the wording #4113 and #5042 retired on web.
//
// ## The rule
//
// This file is a port, state for state and string for string. It adds no
// state and no wording of its own: where web and this file disagree, this file
// is wrong. `frontend/e2e/contract/calibrationStalenessCopy8959.contract.test.js`
// reads both sources and goes red if either side rewords a sentence alone.
//
// It never infers a state the server did not declare. `availability` absent is
// not `fresh` — it is an older payload, and the only authority left is
// `cache.status`. A value that could not be read is `nil`, never a reassuring
// default (gotcha #53).

/// The `staged` block, as `app/utils/calibration_staged_disclosure.py` builds it.
///
/// Decoded field by field, because web reads it field by field: a block whose
/// `measured` is not a literal `true` is still an object, and its `reason` is
/// still readable (#5185). One wrongly-typed field must not erase the others.
nonisolated struct CalibrationStagedState: Decodable, Sendable {
    let measured: Bool?
    let reason: String?
    let stagedAt: String?
    let stagedAgeS: Double?
    let frozenOverDrift: Bool?

    private enum CodingKeys: String, CodingKey {
        case measured, reason, stagedAt, stagedAgeS, frozenOverDrift
    }

    init(measured: Bool?, reason: String?, stagedAt: String?, stagedAgeS: Double?,
         frozenOverDrift: Bool?) {
        self.measured = measured
        self.reason = reason
        self.stagedAt = stagedAt
        self.stagedAgeS = stagedAgeS
        self.frozenOverDrift = frozenOverDrift
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        measured = try? c.decodeIfPresent(Bool.self, forKey: .measured)
        reason = try? c.decodeIfPresent(String.self, forKey: .reason)
        stagedAt = try? c.decodeIfPresent(String.self, forKey: .stagedAt)
        stagedAgeS = try? c.decodeIfPresent(Double.self, forKey: .stagedAgeS)
        frozenOverDrift = try? c.decodeIfPresent(Bool.self, forKey: .frozenOverDrift)
    }
}

nonisolated enum CalibrationStalenessKind: String, Sendable {
    /// A dated last-good copy. The artifact is old AND nothing is republishing it.
    case lastGood = "last-good"
    /// The artifact is current; the market data behind it is dated.
    case frozenInputs = "frozen-inputs"
    /// The server refused `fresh` and the reason could not be read.
    case undisclosed
}

/// What the reader has to be told. Web's `CalibrationStalenessNotice`, minus the
/// drift counts web keeps only as data attributes (standing notice 34).
nonisolated struct CalibrationStalenessNotice: Equatable, Sendable {
    let kind: CalibrationStalenessKind
    /// When the served ARTIFACT was built, if the server dated it.
    let generatedAt: String?
    /// Age of the artifact in seconds, if the server measured it.
    let ageS: Double?
    /// When the market data behind the curve was last staged. Never the publish time.
    let stagedAt: String?
    let stagedAgeS: Double?
    /// `nil` = the payload did not say. NOT "healthy".
    let producerStalled: Bool?
    let beatsMissed: Int?
    /// Positive proof the served artifact is current: `stalled == false` AND
    /// `beats_missed == 0`. Every unreadable case is `false`.
    let producerProvenCurrent: Bool
    /// `staged.reason` verbatim, `nil` when the payload carried none.
    let stagedReason: String?
}

nonisolated enum CalibrationStaleness {
    /// Web's `AVAILABILITY_FRESH`.
    static let availabilityFresh = "fresh"
    /// `staged.reason` for a served bank with nothing in it (#5043's contract).
    static let stagedReasonServedBankEmpty = "served_bank_empty"

    /// Web's `decideCalibrationStaleness`. `nil` means "tell the reader nothing".
    static func decide(
        availability: String?,
        generatedAt: String?,
        cache: CalibrationCacheState?,
        producer: CalibrationProducerState?,
        staged: CalibrationStagedState?
    ) -> CalibrationStalenessNotice? {
        let availability = nonBlank(availability)
        let serverRefusedFresh = availability != nil && availability != availabilityFresh

        let producerStalled = producer?.stalled
        let beatsMissed = producer?.beatsMissed

        // #4046: which tier answered is our storage's business. The tier opens
        // the question and the producer settles it.
        let servedFromFallbackTier = cache?.status == "stale"
        let producerProvenCurrent = producerStalled == false && beatsMissed == 0
        let isLastGood = servedFromFallbackTier && !producerProvenCurrent

        guard isLastGood || serverRefusedFresh else { return nil }

        let stagedMeasured = staged?.measured == true
        // #7696: `cache` exists only on a fallback tier, so the tier-independent
        // statements of the same two facts are the fallbacks.
        let notice = { (kind: CalibrationStalenessKind) in
            CalibrationStalenessNotice(
                kind: kind,
                generatedAt: nonBlank(cache?.generatedAt) ?? nonBlank(generatedAt),
                ageS: finite(cache?.ageS) ?? finite(producer?.ageS),
                stagedAt: stagedMeasured ? nonBlank(staged?.stagedAt) : nil,
                stagedAgeS: stagedMeasured ? finite(staged?.stagedAgeS) : nil,
                producerStalled: producerStalled,
                beatsMissed: beatsMissed,
                producerProvenCurrent: producerProvenCurrent,
                stagedReason: nonBlank(staged?.reason)
            )
        }

        // A dated last-good is the STRONGER fact and outranks the rest.
        if isLastGood { return notice(.lastGood) }
        if stagedMeasured && staged?.frozenOverDrift == true { return notice(.frozenInputs) }
        return notice(.undisclosed)
    }

    /// Web's `stalenessHeadline` — the banner's bold lead.
    static func headline(_ notice: CalibrationStalenessNotice) -> String {
        switch notice.kind {
        case .lastGood:
            return "Showing the last complete snapshot."
        case .frozenInputs:
            // #4113: "The curve is current" is a claim, and it needs the proof.
            return notice.producerProvenCurrent
                ? "The curve is current. The data behind it is older."
                : "We can't confirm the curve is current. The data behind it is older."
        case .undisclosed:
            return notice.generatedAt != nil
                ? "We can't confirm how current the data behind this is."
                : "We can't confirm how current this is."
        }
    }

    /// Web's `stalenessScheduleClause`. THE BANNER MAY DESCRIBE, IT MAY NOT PREDICT.
    static func scheduleClause(_ notice: CalibrationStalenessNotice) -> String? {
        if notice.producerStalled == false {
            // #4113: `stalled` is a four-hour verdict; `beats_missed` is the hour.
            return notice.beatsMissed == 0 ? "The curve rebuilds hourly." : nil
        }
        guard notice.producerStalled == true else { return nil }
        // #5042: the count measures the ARTIFACT's age, not failed runs.
        guard let missed = notice.beatsMissed, missed > 0 else {
            return "Hourly rebuilds have not produced a new snapshot."
        }
        let noun = missed == 1 ? "hourly rebuild has" : "hourly rebuilds have"
        return "\(count(missed)) \(noun) come and gone without a new snapshot."
    }

    /// Web's `stalenessInputSentence` (#5185): an emptied bank is not an unreadable one.
    static func inputSentence(_ notice: CalibrationStalenessNotice) -> String {
        notice.stagedReason == stagedReasonServedBankEmpty
            ? "The market data behind it is being gathered again from scratch, so it has no date to show."
            : "We couldn’t read when the market data behind it was last staged."
    }

    /// The banner's body under the headline — web's `page.tsx` banner, branch for branch.
    static func body(_ notice: CalibrationStalenessNotice) -> String {
        switch notice.kind {
        case .lastGood:
            let when = notice.generatedAt.flatMap(bannerDate) ?? "earlier"
            let schedule = scheduleClause(notice).map { " " + $0 } ?? ""
            return "These numbers were built \(when)\(agoClause(notice.ageS)) "
                + "and are not being refreshed right now.\(schedule)"
        case .frozenInputs:
            let lead = notice.producerProvenCurrent
                ? "The curve was rebuilt on schedule, but the market data behind it was last staged "
                : "The market data behind it was last staged "
            let when = notice.stagedAt.flatMap(bannerDate) ?? "earlier"
            return lead + when + agoClause(notice.stagedAgeS)
                + ". So it describes the market as of then, not now."
        case .undisclosed:
            var parts = ""
            if let when = notice.generatedAt.flatMap(bannerDate) {
                parts += "These numbers were built \(when)\(agoClause(notice.ageS)). "
            }
            if let schedule = scheduleClause(notice) { parts += schedule + " " }
            return parts + inputSentence(notice) + " "
                + "We’d rather say so than call these numbers current."
        }
    }

    /// Web's `stalenessAgeLabel` (#7634): floored, rungs tested on the raw value.
    static func ageLabel(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds >= 90 else { return "moments" }
        if seconds < 90 * 60 { return "\(Int((seconds / 60).rounded(.down))) min" }
        if seconds < 48 * 3600 { return "\(Int((seconds / 3600).rounded(.down))) hr" }
        return "\(Int((seconds / 86400).rounded(.down))) days"
    }

    // MARK: - Helpers

    private static func agoClause(_ seconds: Double?) -> String {
        seconds.map { " (\(ageLabel($0)) ago)" } ?? ""
    }

    /// Web's `toLocaleString("en-US", {month: "short", day: "numeric", hour:
    /// "numeric", minute: "2-digit"})` — "Sep 26, 12:31 AM", in the device's zone.
    static func bannerDate(_ iso: String) -> String? {
        guard let date = parseISO(iso) else { return nil }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "MMM d, h:mm a"
        return f.string(from: date)
    }

    private static func parseISO(_ iso: String) -> Date? {
        let withFrac = ISO8601DateFormatter()
        withFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withFrac.date(from: iso) { return d }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        return plain.date(from: iso)
    }

    private static func nonBlank(_ s: String?) -> String? {
        guard let s, !s.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        return s
    }

    private static func finite(_ x: Double?) -> Double? {
        guard let x, x.isFinite else { return nil }
        return x
    }

    private static func count(_ n: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.locale = Locale(identifier: "en_US")
        return f.string(from: NSNumber(value: n)) ?? "\(n)"
    }
}
