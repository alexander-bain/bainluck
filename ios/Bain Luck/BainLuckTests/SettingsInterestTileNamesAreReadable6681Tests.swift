#if canImport(UIKit)
import UIKit
import XCTest
@testable import Bain_Luck

/// #6681 — three of the 22 Settings → Your Interests tiles could not show their
/// own name: "College Foo…", "College Basketball", "Entertainm…".
///
/// The row is `[emoji | name] Spacer() [Love Big Wild Nah]`. The capsules are
/// `.fixedSize()`, the Spacer absorbs nothing, so the name is the only
/// compressible thing in the row and it is also the ONLY thing distinguishing
/// one row from the next — every row's capsules read the same four words. A
/// reader scanning for College Football saw the same truncated stem as College
/// Basketball two rows down.
///
/// ## Why this test measures instead of asserting a modifier is present
///
/// A test that greps for `.minimumScaleFactor` passes for any value, including
/// the 0.85 first proposed on the issue — which measurement shows would have
/// left two of the three names still truncated. The question is not "is there a
/// floor" but "is the floor low enough for the longest name to fit", and that
/// is arithmetic over real font metrics.
///
/// `AffinityRowMetrics` is shared with `PreferencesView` rather than restated
/// here, so a padding change moves the view and this test together. What is NOT
/// shared is the text measurement, which is the part that has to be real.
///
/// ## What this is not
///
/// Not a rendering test — this target has no SwiftUI inspection or snapshot
/// facility. It is a width model of one row, and it is only trustworthy because
/// it was validated against a photograph: at 402pt it predicts exactly the
/// three names that truncate on the device and no others, which is what the
/// BEFORE frame in `artifacts/native-216/` shows.
@MainActor
final class SettingsInterestTileNamesAreReadable6681Tests: XCTestCase {

    /// The device #6681 was filed from — iPhone 17 / 17 Pro, 402pt across.
    private let referenceWidth: CGFloat = 402

    /// Every tile the grid draws, both sections.
    private var allTileNames: [String] {
        (OnboardingSportsData.sports + OnboardingSportsData.beyondSports).map(\.name)
    }

    // MARK: - Measurement

    /// Default Dynamic Type, so the numbers do not move with the simulator's
    /// accessibility settings.
    private var traits: UITraitCollection {
        UITraitCollection(preferredContentSizeCategory: .large)
    }

    private func nameFont(weight: UIFont.Weight) -> UIFont {
        let base = UIFont.preferredFont(forTextStyle: .subheadline, compatibleWith: traits)
        return UIFont.systemFont(ofSize: base.pointSize, weight: weight)
    }

    private func width(_ string: String, font: UIFont) -> CGFloat {
        (string as NSString).size(withAttributes: [.font: font]).width
    }

    /// The four capsules plus their padding and gaps.
    ///
    /// Each label is measured at the WIDER of its two weights: the selected
    /// capsule is bold and the row is `.fixedSize()`, so the block never gets
    /// narrower than this no matter which level the reader picked.
    private var capsuleBlockWidth: CGFloat {
        let bold = UIFont.systemFont(ofSize: AffinityRowMetrics.capsuleFontSize, weight: .bold)
        let medium = UIFont.systemFont(ofSize: AffinityRowMetrics.capsuleFontSize, weight: .medium)
        let labels = AffinityLevel.allCases.map(\.shortLabel)
        let capsules = labels.reduce(CGFloat.zero) { total, label in
            total + max(width(label, font: bold), width(label, font: medium))
                + 2 * AffinityRowMetrics.capsuleHorizontalPadding
        }
        return capsules + CGFloat(labels.count - 1) * AffinityRowMetrics.capsuleSpacing
    }

    private func nameBudget(screenWidth: CGFloat) -> CGFloat {
        AffinityRowMetrics.nameBudget(
            screenWidth: screenWidth,
            capsuleBlockWidth: capsuleBlockWidth
        )
    }

    /// An ACTIVE tile is semibold, which is the wider of the two states — so
    /// this is the width that has to fit.
    private func widestRenderedName(_ name: String) -> CGFloat {
        width(name, font: nameFont(weight: .semibold))
    }

    // MARK: - The ship

    /// Every tile name fits at the shipped floor on the device the defect was
    /// filed from. This is the assertion that fails if the floor is raised, if
    /// a padding grows, or if someone adds a longer display name.
    func testEveryTileNameFitsAtTheShippedFloorOnTheFiledDevice() {
        let budget = nameBudget(screenWidth: referenceWidth)
        XCTAssertGreaterThan(budget, 0, "The row model produced a nonsensical budget")

        for name in allTileNames {
            let needed = budget / widestRenderedName(name)
            XCTAssertLessThanOrEqual(
                AffinityRowMetrics.nameMinimumScaleFactor,
                needed,
                """
                "\(name)" still truncates at \(referenceWidth)pt: it needs a \
                minimumScaleFactor of \(String(format: "%.3f", needed)) and the row \
                ships \(AffinityRowMetrics.nameMinimumScaleFactor). Lower the floor, \
                shorten the name, or give the name more room — do not raise the floor \
                and call it fixed.
                """
            )
        }
    }

    /// CONTROL — the measurement has teeth.
    ///
    /// Without a floor (scale 1.0) exactly three names overflow, and they are
    /// the three #6681 reported. If this ever reads zero, the model has stopped
    /// measuring the defect and the test above is passing vacuously.
    func testWithoutAFloorExactlyTheThreeReportedNamesOverflow() {
        let budget = nameBudget(screenWidth: referenceWidth)
        let overflowing = allTileNames
            .filter { widestRenderedName($0) > budget }
            .sorted()

        XCTAssertEqual(
            overflowing,
            ["College Basketball", "College Football", "Entertainment"],
            """
            The unscaled overflow set no longer matches what #6681 reported from \
            the device. Either the row geometry moved or the display names did — \
            re-photograph before trusting the fit test above.
            """
        )
    }

    /// CONTROL — the floor that was first proposed would NOT have finished the
    /// job, and this pins exactly how far short it fell.
    ///
    /// The issue suggested 0.85. Measured, that clears College Football (needs
    /// 0.866) and Entertainment (0.983) but leaves **College Basketball**
    /// (0.757) truncated on every phone — and College Basketball is the worst
    /// one to lose, because "College Football" sits two rows above it and they
    /// share their first eight characters. Pinned so nobody rounds the shipped
    /// 0.65 back up to a tidier number and reintroduces exactly one defect.
    func testTheFirstProposedFloorWouldHaveLeftTheWorstNameTruncated() {
        let budget = nameBudget(screenWidth: referenceWidth)
        let proposed: CGFloat = 0.85
        let stillTruncated = allTileNames
            .filter { budget / widestRenderedName($0) < proposed }
            .sorted()

        XCTAssertEqual(
            stillTruncated,
            ["College Basketball"],
            "The 0.85 counter-example this fix was chosen over no longer reproduces"
        )
    }

    /// The shipped floor is low enough for every phone Apple currently ships,
    /// and this states plainly where it is not.
    ///
    /// 375pt (iPhone SE 3rd gen, 13 mini) is the honest residual: five names
    /// overflow there and the longest needs 0.553, which at this text style is
    /// under 9pt — too small to be worth calling a fix. The floor improves that
    /// row without resolving it. Asserted rather than left unsaid so the next
    /// reader does not have to rediscover it.
    func testTheFloorCoversEveryCurrentPhoneAndTheResidualIsNamed() {
        for width in [393, 402, 440] as [CGFloat] {
            let budget = nameBudget(screenWidth: width)
            for name in allTileNames {
                let needed = budget / widestRenderedName(name)
                XCTAssertLessThanOrEqual(
                    AffinityRowMetrics.nameMinimumScaleFactor,
                    needed,
                    "\"\(name)\" does not fit at \(Int(width))pt"
                )
            }
        }

        let narrow = nameBudget(screenWidth: 375)
        let unfixedAt375 = allTileNames
            .filter { narrow / widestRenderedName($0) < AffinityRowMetrics.nameMinimumScaleFactor }
        XCTAssertEqual(
            unfixedAt375.sorted(),
            ["College Basketball", "College Football"],
            """
            The known 375pt residual changed. If it grew, the row needs real \
            space back (tighter capsules or a wrapped name), not a lower floor.
            """
        )
    }
}
#endif
