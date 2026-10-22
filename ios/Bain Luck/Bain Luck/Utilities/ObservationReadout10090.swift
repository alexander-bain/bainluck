import SwiftUI

/// THE RECORDING-FRIENDLY OBSERVATION READOUT (#10090, the iPhone half of
/// Speed's web readout, PR #11414).
///
/// A phone reader recording the event page needs three facts about the
/// probability the headline prints, and the details popover only gave one of
/// them (when an update reached this phone):
///
/// 1. **When that probability was observed** — local wall time to the
///    millisecond. This is the displayed value's own clock
///    (`EventDetailViewModel.displayedProbabilityObservedAt`): the preview's
///    observation time while a preview shows, the committed hero clock
///    otherwise. A page that prints no price owns no clock, so it says
///    "Time unavailable" rather than borrow a source's newer stamp.
/// 2. **How many forward observations this page visit has shown**
///    (`ObservationCount10090`). The first valid displayed clock counts 1;
///    only a clock strictly newer than the visit's maximum adds one.
///    Repeats, a backwards clock, a return to the earlier maximum and an age
///    tick never do.
/// 3. **How the CURRENTLY DISPLAYED value arrived**
///    (`ObservationDelivery10090`): read from the value the headline prints,
///    never from the rollout flag, freshness, source identity or an age tick.
nonisolated enum ObservationDelivery10090: String, Equatable, Sendable {
    /// The headline prints an admitted preview (`BlendPreview.displayed`).
    case dnpl
    /// The headline prints the committed price (served or pushed).
    case committed
    /// No printed price, so no delivery path to name.
    case unknown

    /// Web's wording (`LiveConnectionStatus`), so one recording reads both.
    var label: String {
        switch self {
        case .dnpl: return "DNPL active"
        case .committed: return "Committed delivery"
        case .unknown: return "Delivery unknown"
        }
    }
}

/// The page visit's forward high-water counter (web's `useObservationCount`).
nonisolated struct ObservationCount10090: Equatable, Sendable {
    private(set) var highWater: Date?
    private(set) var count = 0

    /// Idempotent for any clock at or below the high-water, so reading the
    /// same displayed value on every render can never count it twice. A nil
    /// (unknown or unowned) clock changes nothing.
    mutating func observe(_ observedAt: Date?) {
        guard let observedAt else { return }
        if let highWater, observedAt <= highWater { return }
        highWater = observedAt
        count += 1
    }
}

/// What the details popover prints for the displayed probability.
nonisolated struct ObservationReadout10090: Equatable, Sendable {
    /// The displayed value's own clock, which may be OLDER than the visit's
    /// maximum (a backwards clock is shown as it is, uncounted). Nil when the
    /// page cannot prove which clock dates the value it prints.
    let observedAt: Date?
    let count: Int
    let delivery: ObservationDelivery10090

    static let timeLabel = "Probability observed"
    static let countLabel = "Observations shown"
    static let deliveryLabel = "Current probability delivery"
    static let timeUnavailable = "Time unavailable"

    /// Local wall time to the millisecond with its zone; the date leads only
    /// when the clock is from an earlier day (`FreshnessRevealView.receiptClock`'s rule).
    static func clock(_ observedAt: Date, now: Date = .now, calendar: Calendar = .current,
                      locale: Locale = .current) -> String {
        var style = Date.FormatStyle(locale: locale, calendar: calendar, timeZone: calendar.timeZone)
            .hour().minute(.twoDigits).second(.twoDigits).secondFraction(.fractional(3))
            .timeZone(.specificName(.short))
        if !calendar.isDate(observedAt, inSameDayAs: now) {
            style = style.month(.abbreviated).day().year()
        }
        return observedAt.formatted(style)
    }

    func timeText(now: Date = .now, calendar: Calendar = .current, locale: Locale = .current) -> String {
        observedAt.map { Self.clock($0, now: now, calendar: calendar, locale: locale) } ?? Self.timeUnavailable
    }

    var countText: String { "\(count) · first + newer times" }
}

/// Carries the page's readout into `FreshnessRevealView` (absent everywhere
/// else, where the popover prints exactly what it printed before).
private struct ObservationReadoutKey10090: EnvironmentKey {
    static let defaultValue: ObservationReadout10090? = nil
}

extension EnvironmentValues {
    var observationReadout10090: ObservationReadout10090? {
        get { self[ObservationReadoutKey10090.self] }
        set { self[ObservationReadoutKey10090.self] = newValue }
    }
}

/// The three rows, each ONE accessibility element: VoiceOver reads title and
/// text together ("Probability observed: 6:59:08.123 PM PDT"), and a UI
/// recording finds each row by identifier and reads the same exact text from
/// its label. No separate value, so nothing is spoken twice.
struct ObservationReadoutRows10090: View {
    let readout: ObservationReadout10090
    let now: Date

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            row(ObservationReadout10090.timeLabel, readout.timeText(now: now), id: "observation-time")
            row(ObservationReadout10090.countLabel, readout.countText, id: "observation-count")
            row(ObservationReadout10090.deliveryLabel, readout.delivery.label, id: "observation-delivery")
        }
    }

    private func row(_ title: String, _ text: String, id: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).fontWeight(.medium)
            Text(text).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title): \(text)")
        .accessibilityIdentifier(id)
    }
}

extension EventDetailView {
    /// Whether the hero prints a priced pair — the condition of the priced arm
    /// and of the NFL paired headline's priced arm, which both mount the
    /// details. False on the `vs` arm (no price, so no clock to own) and on an
    /// opening line, which mounts no details at all.
    static func heroPrintsPrice(_ headline: EventDetail) -> Bool {
        guard let odds = headline.currentOdds else { return false }
        let shown = OpeningLineHero.resolve(odds, for: headline)
        return !shown.isOpeningLine && DrawPricedWinner.printablePair(
            away: shown.awayProbability, home: shown.homeProbability, sport: headline.sport) != nil
    }
}
