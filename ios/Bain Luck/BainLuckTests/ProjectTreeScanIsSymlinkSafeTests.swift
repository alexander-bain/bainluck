import XCTest
@testable import Bain_Luck

/// #6671-adjacent — THE GUARDS' OWN GUARD, routed by int426 from the desk on
/// 2026-09-18 after `cf729f250` came back red from a worktree under `/tmp`.
///
/// Four whole-project scans stripped a `#filePath`-derived root out of a
/// symlink-resolved enumerated path with `replacingOccurrences`. Under `/tmp`
/// (a symlink to `/private/tmp` on macOS) the root sits in the MIDDLE of the
/// enumerated path, so the strip cut it from the middle and produced
/// `/privateViews/LeaguesView.swift`. Nothing matched an allowlist after that,
/// and `testNoTargetShortensATeamNameByHand` printed a confident six-line
/// census of a product defect that does not exist.
///
/// These four tests are about `ProjectTree` and nothing else. The first is the
/// one that would have gone red on the desk's rig; the other three are the
/// properties that make the class unrepeatable rather than this instance fixed.
final class ProjectTreeScanIsSymlinkSafeTests: XCTestCase {

    // MARK: - The reproduction

    /// A root reached THROUGH A SYMLINK still yields clean relative paths.
    ///
    /// This is the desk's failure, staged. The SYMLINK IS AN ANCESTOR of the
    /// root, not the root itself, because that is the real shape: `/tmp` is a
    /// symlink to `/private/tmp` and the worktree sits underneath it. (A
    /// symlink AT the root is a different thing — `FileManager` will not
    /// descend into it at all, so it cannot reproduce this bug.)
    ///
    /// The old idiom is computed alongside, so the test states what it protects
    /// against rather than only what it wants, and the premise is asserted
    /// before the conclusion: if the enumerated path ever stops differing from
    /// the handed-in root, this test is passing vacuously and says so.
    func testASymlinkedRootStillYieldsCleanRelativePaths() throws {
        let tmp = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("projecttree-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmp) }

        let realParent = tmp.appendingPathComponent("realparent", isDirectory: true)
        let nested = realParent.appendingPathComponent("proj/Views", isDirectory: true)
        try FileManager.default.createDirectory(at: nested, withIntermediateDirectories: true)
        try "import SwiftUI\n".write(
            to: nested.appendingPathComponent("LeaguesView.swift"), atomically: true, encoding: .utf8
        )

        let linkParent = tmp.appendingPathComponent("linkparent", isDirectory: true)
        try FileManager.default.createSymbolicLink(at: linkParent, withDestinationURL: realParent)
        let root = linkParent.appendingPathComponent("proj", isDirectory: true)

        let enumerated = try XCTUnwrap(
            FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)?
                .compactMap { $0 as? URL }
                .first { $0.pathExtension == "swift" },
            "the walk found no Swift file at all"
        )

        // THE PREMISE. Without this the rig could stop reproducing the
        // condition and the assertions below would pass on a tree with no
        // symlink in it — a green test about nothing.
        XCTAssertFalse(
            enumerated.path.hasPrefix(root.path + "/"),
            "the rig is no longer reproducing the symlinked-root condition, so this test "
                + "proves nothing — fix the rig before trusting it"
        )

        let relative = try ProjectTree.relativePath(of: enumerated, under: root)
        XCTAssertEqual(relative, "Views/LeaguesView.swift")
        XCTAssertFalse(
            relative.hasPrefix("/"),
            "a relative path beginning with / is the deformed shape this repair exists to stop"
        )

        // The defect itself, so this fails if someone restores the idiom.
        let oldIdiom = enumerated.path.replacingOccurrences(of: root.path + "/", with: "")
        XCTAssertNotEqual(
            oldIdiom, relative,
            "the old strip now agrees with the new one, which it cannot do under a symlink"
        )
    }

    // MARK: - The properties that outlive this instance

    /// Over the REAL tree, no relative path is absolute and none carries a
    /// `/private` tell. The scan's output shape, asserted on the population the
    /// guards actually judge.
    func testNoRelativePathInTheRealTreeIsAbsolute() throws {
        let files = try ProjectTree.swiftFiles(under: ProjectTree.root(), minimumFiles: 100)
        let deformed = files.map(\.path).filter { $0.hasPrefix("/") || $0.contains("/private") }
        XCTAssertEqual(deformed, [], "the scan is deforming relative paths again")
        XCTAssertTrue(
            files.contains { $0.path == "Bain Luck/Utilities/TeamShortName.swift" },
            "the walk is not reaching the app source"
        )
    }

    /// A file outside the root is REFUSED, not mangled. This is the half that
    /// survives today's cause: `replacingOccurrences` answered every wrong root
    /// with a plausible-looking string, and there is now no input for which
    /// this function returns one.
    func testAPathOutsideTheRootIsRefusedRatherThanMangled() {
        let root = URL(fileURLWithPath: "/a/b/c")
        let stranger = URL(fileURLWithPath: "/x/y/Views/LeaguesView.swift")
        XCTAssertThrowsError(try ProjectTree.relativePath(of: stranger, under: root)) { error in
            XCTAssertTrue(
                error is ProjectTree.Unreachable,
                "the wrong error type — callers distinguish an unrunnable scan from a read failure"
            )
            XCTAssertTrue(
                "\(error)".contains("UNRUNNABLE"),
                "the message must say the scan could not run, not describe a file"
            )
        }
    }

    /// An empty tree THROWS instead of returning an empty list.
    ///
    /// `offences == []` is also what a walk that enumerated nothing produces,
    /// so a scan that can return an empty list on failure can pass by failing.
    /// `BrowseHidesTheChallengeTile6445Tests` named this in a comment while its
    /// own walker still did `guard … else { return [] }`.
    func testAnEmptyTreeIsUnrunnableRatherThanClean() throws {
        let empty = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("projecttree-empty-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: empty, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: empty) }

        XCTAssertThrowsError(try ProjectTree.swiftFiles(under: empty)) { error in
            XCTAssertTrue(error is ProjectTree.Unreachable)
            XCTAssertTrue("\(error)".contains("0 Swift file"), "the message must say what it found")
        }
    }
}
