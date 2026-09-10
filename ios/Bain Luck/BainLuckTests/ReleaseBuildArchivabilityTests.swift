import XCTest
@testable import Bain_Luck

/// The app could not be archived at all, and nothing in the repo could tell.
///
/// Swift 6.3.3's `EarlyPerfInliner` crashes while inlining into the *synthesized*
/// deallocating destructor of a generic class. Debug builds run no optimizer, so
/// every simulator build, every `xcodebuild test` run and all of CI stayed green
/// while `xcodebuild archive` died — and it died with **exit code 0** and no
/// `.xcarchive` on disk, so even a script that checked the status would have
/// called it a pass (gotcha #124: read the artifact, not the exit code).
/// Measured on master `421bdc36`, 2026-09-09: two crashes, one per generic class.
///
/// Writing the destructor out by hand gives the pass a real body and it compiles.
/// This suite pins the invariant that keeps it compiling. It is a source scan
/// because the defect is a *codegen* property that no runtime assertion can see:
/// the only true test is an `-O` build, which CI does not run, so the real gate is
/// `tools/native-release-check.sh` and this suite is the cheap tripwire in front
/// of it.
final class ReleaseBuildArchivabilityTests: XCTestCase {

    /// Every generic class in the app target must declare an explicit `deinit`.
    ///
    /// Deliberately expressed as an invariant over whatever generic classes exist,
    /// NOT as an allowlist of the two that exist today. An allowlist would have to
    /// be edited to add a third generic class, and editing it is exactly the moment
    /// someone would skip the deinit; this way a third class fails until it carries
    /// one. It also means the guard does not encode the current duplication as a
    /// requirement.
    ///
    /// Matches on the DECLARATION shape and skips comment lines, so the doc
    /// comments on the two deinits — which name the classes and the word `deinit`
    /// — can neither satisfy nor trip it.
    func testEveryGenericClassDeclaresAnExplicitDeinit() throws {
        var offenders: [String] = []
        var generics: [String] = []

        for (relative, source) in try appTargetSources() {
            let code = source
                .split(separator: "\n", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.hasPrefix("//") }

            let declaresGenericClass = code.contains { line in
                guard let range = line.range(of: "class ") else { return false }
                // `class Name<` with the angle bracket before any `{` or `:` —
                // i.e. a generic parameter list, not an inheritance clause.
                let after = line[range.upperBound...]
                guard let lt = after.firstIndex(of: "<") else { return false }
                let head = after[..<lt]
                return !head.isEmpty
                    && !head.contains("{")
                    && !head.contains(":")
                    && head.allSatisfy { $0.isLetter || $0.isNumber || $0 == "_" }
            }
            guard declaresGenericClass else { continue }
            generics.append(relative)

            let declaresDeinit = code.contains {
                $0 == "deinit {" || $0.hasPrefix("deinit ") || $0 == "deinit"
            }
            if !declaresDeinit { offenders.append(relative) }
        }

        XCTAssertFalse(
            generics.isEmpty,
            "The scan found no generic classes at all — the matcher has drifted and "
                + "this suite is now vacuous, which is worse than a failure."
        )

        XCTAssertEqual(
            offenders, [],
            "These generic classes have no explicit `deinit`, so Swift synthesizes "
                + "one and `xcodebuild archive` crashes in EarlyPerfInliner with "
                + "exit code 0 and no .xcarchive. Add `deinit { }` releasing the "
                + "stored properties, and run tools/native-release-check.sh."
        )
    }

    /// The two known sites still hold their deinits, named individually so a
    /// failure says which file to open. This is a specimen check, not the
    /// invariant — the test above is the invariant.
    func testTheTwoKnownGenericClassesStillCarryTheirDeinits() throws {
        let expected = [
            "Utilities/DiscoverPresentation.swift",   // MemoizedPresentation<Value>
            "Utilities/SportsSiblingMerge.swift",     // SportsSiblingMerge<T>
        ]
        let sources = try appTargetSources()
        for path in expected {
            let source = try XCTUnwrap(
                sources.first(where: { $0.relative == path })?.source,
                "\(path) has moved or been deleted — re-point this specimen check."
            )
            let code = source
                .split(separator: "\n", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.hasPrefix("//") }
            XCTAssertTrue(
                code.contains { $0 == "deinit {" || $0.hasPrefix("deinit ") },
                "\(path) lost its explicit deinit — the archive will crash again."
            )
        }
    }

    // MARK: - Helpers

    private func appTargetSources() throws -> [(relative: String, source: String)] {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (source root)
            .appendingPathComponent("Bain Luck")

        let enumerator = try XCTUnwrap(FileManager.default.enumerator(atPath: root.path))
        var out: [(relative: String, source: String)] = []
        for case let relative as String in enumerator where relative.hasSuffix(".swift") {
            let source = try String(
                contentsOf: root.appendingPathComponent(relative), encoding: .utf8
            )
            out.append((relative, source))
        }
        return out
    }
}
