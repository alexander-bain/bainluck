import Foundation

/// #13430 — Shared small Lock Screen & Watch complication fitting rules.
///
/// Single source of truth for what can fit inside `accessoryCircular` and
/// `accessoryCorner` slots (both iPhone Lock Screen and Apple Watch faces),
/// compiled identically by `BainLuckWidget`, `BainLuckComplication`,
/// `BainLuckWatch Watch App`, and `BainLuckTests`.
nonisolated enum LockScreenSmallSlotPhase13430: String, Equatable, Sendable {
    case current
    case lastRecorded
    case openingLine
    case result
    case noResult
    case unavailable
}

nonisolated struct LockScreenSmallSlotRow13430: Equatable, Sendable {
    let label: String
    let shortLabel: String

    init(label: String, shortLabel: String) {
        self.label = label
        self.shortLabel = shortLabel
    }
}

nonisolated struct LockScreenSmallSlotModel13430: Equatable, Sendable {
    /// Short subject label inside the circular gauge or stacked circle ("BAL", "DET", "Draw").
    let subjectLabel: String
    /// Concise curved bezel label for the Watch corner complication ("BAL", "DET", "Newsom").
    let cornerLabel: String
    /// Fitted primary value ("74%", "<1%", "Won", "Draw", "Final", "Unknown", "—"), never exceeding `ringLimit` chars.
    let value: String
    /// Fractional gauge fill (`0...1`) when a live/upcoming percent gauge applies; `nil` for settled/verdict slots.
    let gaugeShare: Double?
    /// Games print their short team label in circular gauge notch; markets reserve gauge notch for clean numbers.
    let isGame: Bool
    /// Complete spoken label for VoiceOver.
    let accessibilityText: String

    init(
        subjectLabel: String,
        cornerLabel: String,
        value: String,
        gaugeShare: Double?,
        isGame: Bool,
        accessibilityText: String
    ) {
        self.subjectLabel = subjectLabel
        self.cornerLabel = cornerLabel
        self.value = value
        self.gaugeShare = gaugeShare
        self.isGame = isGame
        self.accessibilityText = accessibilityText
    }
}

nonisolated enum LockScreenSmallSlotFit13430 {
    /// Verdicts that share a line with the outcome name on Lock Screen rectangles.
    static let shortVerdicts: Set<String> = ["Won", "Lost", "Draw"]
    /// The longest word a circular or corner slot value holds whole ("Unknown").
    static let ringLimit = 7

    /// Opening lines and non-price states cannot fill a percentage ring without a caption.
    static func allowsRingValue(phase: LockScreenSmallSlotPhase13430) -> Bool {
        phase != .openingLine
    }

    /// Circular / corner slot value: a percentage figure, a verdict within `ringLimit`,
    /// or a short safe word standing for a longer venue/settlement phrase.
    static func ringValue(
        phase: LockScreenSmallSlotPhase13430,
        headlineExists: Bool,
        figure: String?,
        verdict: String?,
        rows: [LockScreenSmallSlotRow13430]
    ) -> String {
        guard allowsRingValue(phase: phase), headlineExists else {
            return phase == .noResult ? "Final" : "—"
        }
        if phase == .unavailable { return "—" }
        guard let verdict else { return figure ?? "—" }
        if shortVerdicts.contains(verdict) || verdict.count <= ringLimit { return verdict }
        if phase == .noResult { return "Unknown" }
        if let side = rows.first(where: { $0.label == verdict || $0.label + " wins" == verdict }),
           side.shortLabel.count <= ringLimit {
            return side.shortLabel
        }
        return "—"
    }
}
