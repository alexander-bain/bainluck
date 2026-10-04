import Foundation

/// Formats the server's saved expectation and official actual. It never grades
/// a threshold, averages prices, or substitutes a venue's settlement result.
nonisolated enum PropExpectationActualDisplay {
    enum Mark: Equatable, Sendable { case reached, below, unknown }

    struct Expectation: Equatable, Sendable {
        let valueText: String?
        let label: String
        let basisText: String?
    }

    struct Actual: Equatable, Sendable {
        let countText: String?
        let sourceLabel: String?
        let stateText: String
        let isFinal: Bool
    }

    static func expectation(_ expectation: AfterPropExpectation) -> Expectation {
        guard let probability = expectation.savedProbability else {
            return Expectation(valueText: nil, label: "Saved pregame chance", basisText: nil)
        }
        let sourceNames = expectation.contributors.compactMap { SourceLabels.label(for: $0.source) }
        var names: [String] = []
        for name in sourceNames where !names.contains(name) { names.append(name) }
        let basis: String?
        switch expectation.basis {
        case "single_source":
            basis = names.count == 1 && sourceNames.count == expectation.contributors.count ? names.first : nil
        case "blend_mean":
            if names.count > 1 && sourceNames.count == expectation.contributors.count {
                basis = "Average of \(names.joined(separator: " and "))"
            } else if expectation.contributors.count > 1 {
                basis = "Average of \(expectation.contributors.count) prices"
            } else {
                basis = nil
            }
        default:
            basis = nil
        }
        return Expectation(valueText: formatProbability(probability), label: "Saved pregame chance", basisText: basis)
    }

    static func actual(_ actual: AfterPropActual?, stat: AfterPropStat?) -> Actual {
        guard let actual else { return unavailableActual() }
        if let stat, stat.statKey != actual.statKey || stat.periodKey != actual.periodKey {
            return unavailableActual()
        }
        guard let count = actual.finalCount else {
            return unavailableActual(pending: actual.state == "pending")
        }
        let unit = stat.map { count == 1 ? $0.unitSingular : $0.unitPlural }
        let countText = unit.map { "\(count) \($0)" } ?? "\(count)"
        return Actual(countText: countText, sourceLabel: actual.sourceLabel, stateText: "Final", isFinal: true)
    }

    static func mark(_ question: AfterPropQuestion, actual: AfterPropActual?) -> Mark {
        guard supportedQuestion(question), let actual, actual.finalCount != nil,
              actual.actualKey == question.actualKey,
              actual.subject.key == question.subject.key,
              actual.statKey == question.statKey, actual.periodKey == question.periodKey else { return .unknown }
        switch question.comparison?.state {
        case "reached": return .reached
        case "below": return .below
        default: return .unknown
        }
    }

    static func markText(_ mark: Mark) -> String {
        switch mark {
        case .reached: return "Reached"
        case .below: return "Below"
        case .unknown: return "Unknown"
        }
    }

    static func question(_ question: AfterPropQuestion, stat: AfterPropStat?) -> String {
        guard supportedQuestion(question) else { return absentProbabilityMarker }
        guard let stat, stat.statKey == question.statKey, stat.periodKey == question.periodKey else {
            return question.predicate.label
        }
        let unit = question.predicate.count == 1 ? stat.unitSingular : stat.unitPlural
        return "\(question.predicate.label) \(unit)"
    }

    static func accessibilityLabel(_ question: AfterPropQuestion, actual: AfterPropActual?, stat: AfterPropStat?) -> String {
        let spokenQuestion: String
        if supportedQuestion(question) {
            let unit = stat.flatMap {
                $0.statKey == question.statKey && $0.periodKey == question.periodKey ? $0.unitPlural : nil
            }
            spokenQuestion = "\(question.predicate.count) or more" + (unit.map { " \($0)" } ?? "")
        } else {
            spokenQuestion = "Question unavailable"
        }
        let chance = expectation(question.expectation).valueText.map {
            $0.replacingOccurrences(of: "<", with: "under ")
                .replacingOccurrences(of: ">", with: "over ")
                .replacingOccurrences(of: "%", with: " percent")
        } ?? "unavailable"
        return [question.subject.label, spokenQuestion, "saved pregame chance \(chance)",
                "result \(markText(mark(question, actual: actual)).lowercased())"].joined(separator: ", ")
    }

    private static func supportedQuestion(_ question: AfterPropQuestion) -> Bool {
        question.predicate.kind == "count_at_least" && question.predicate.side == "over"
            && question.predicate.count >= 0 && question.periodKey == "full_game"
    }

    private static func unavailableActual(pending: Bool = false) -> Actual {
        Actual(countText: nil, sourceLabel: nil, stateText: pending ? "Pending" : "Unknown", isFinal: false)
    }
}
