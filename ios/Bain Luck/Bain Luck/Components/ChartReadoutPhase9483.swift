import Foundation

/// #9483 — the part of the game a chart reading belongs to, where the page can
/// prove it. Nil, the common case, leaves the readout's own period/clock badge.
///
/// The design review asked that an inspected reading name its subject, chance,
/// phase and observation time, with the pregame baseline told apart from play.
/// Before this, a pregame point printed only a wall clock, the same as a point
/// in a timeout with no state.
enum ChartReadoutPhase9483: Equatable {
    case pregame
    case final

    var word: String {
        switch self {
        case .pregame: return "Pregame"
        case .final: return "Final"
        }
    }
}

/// #9483 — what the chart already knows that decides a reading's phase and how
/// its time is said. Built once per chart body from the chart's own decisions;
/// adds no start or end rule of its own.
struct ChartReadoutContext9483 {
    /// The chart's existing Since Start cut (`OddsChartView.sinceStartDate`):
    /// the first observed opening period, else a stored start the payload calls
    /// a kickoff. Nil when the page has neither, and then nothing is "Pregame".
    var playStart: Date?
    /// A finished game's last drawn reading — where the line ends. Nil while
    /// the game is not over.
    var terminal: Date?
    var timeZone: TimeZone = .autoupdatingCurrent
    var locale: Locale = .autoupdatingCurrent
    /// The day a spoken time is dated against.
    var now: Date = Date()

    /// "Final" is the line's settled end on a finished game — the reading the
    /// card already prints as the result (`GamePlayCardView.printedLabels`,
    /// #9015). A finished line that stops short of 0 or 1 ends on a quote, not
    /// a result, and is named by its own state. "Pregame" is any reading
    /// before the play-start cut.
    func phase(at date: Date, probability: Double) -> ChartReadoutPhase9483? {
        if let terminal, date >= terminal, probability == 0 || probability == 1 { return .final }
        if let playStart, date < playStart { return .pregame }
        return nil
    }

    /// The reading's time as the inline card prints it ("3:50 PM"), with the
    /// weekday only when the reading is not from today ("Sun 6:06 PM"), so a
    /// scrub tick stays one short clause.
    func spokenTime(_ date: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let style = calendar.isDate(date, inSameDayAs: now)
            ? Date.FormatStyle(date: .omitted, time: .shortened, locale: locale, timeZone: timeZone)
            : Date.FormatStyle(locale: locale, timeZone: timeZone).weekday(.abbreviated).hour().minute()
        return date.formatted(style)
    }

    /// The chart's context: `readoutPoints` is the series the readout names
    /// (its terminal reading is where a finished line ends); a checkpoint
    /// mount's resting endpoint stands in for it when one is mounted.
    static func chart(playStart: Date?, gameFinished: Bool, readoutPoints: [ChartDataPoint],
                      checkpoints: PublicationCheckpointMount4974?) -> ChartReadoutContext9483 {
        guard gameFinished else { return ChartReadoutContext9483(playStart: playStart, terminal: nil) }
        let terminal: Date? = checkpoints != nil
            ? checkpoints?.resting?.date
            : readoutPoints.map(\.date).max()
        return ChartReadoutContext9483(playStart: playStart, terminal: terminal)
    }
}
