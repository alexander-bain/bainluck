import Foundation

/// THE ONE WAY A GUARD WALKS THIS PROJECT'S SOURCE TREE.
///
/// THE DEFECT (int426 at the desk, 2026-09-18). Four guards each computed the
/// project root from their own `#filePath` and then stripped it out of an
/// enumerated path with `replacingOccurrences`:
///
///     let rel = url.path.replacingOccurrences(of: root.path + "/", with: "")
///
/// `#filePath` is the path the COMPILER was handed; `FileManager`'s enumerator
/// returns a SYMLINK-RESOLVED one. Those are the same string in a normal
/// checkout and different strings in a worktree under `/tmp` — which on macOS
/// is a symlink to `/private/tmp`. The root then occurs in the MIDDLE of the
/// enumerated path, `replacingOccurrences` cheerfully cuts it out of the
/// middle, and every relative path comes back deformed:
///
///     expected: "Views/LeaguesView.swift"
///     actual:   "/privateViews/LeaguesView.swift"
///
/// WHY THAT IS WORSE THAN A RED TEST. A deformed path matches no allowlist and
/// no control, so `knownOutstanding` stops excusing the files it excuses and
/// the scan reports them as fresh offences. On `cf729f250` this printed a
/// confident census of six watch-app lines "deriving a team's short label by
/// hand" — a product verdict, in the voice of a product verdict, computed over
/// a tree the scanner could not see. Its own anti-vacuity sibling was failing
/// with *"the scan never reached … it is not walking the whole project"* in the
/// same run, and nothing connected the two. A guard whose self-check is failing
/// is not entitled to report a product verdict.
///
/// SO THE STRIP IS TOTAL, NOT BEST-EFFORT. `relativePath(of:under:)` requires
/// the file to sit under the root and THROWS when it does not, which is the
/// half that outlives today's cause: a relative path can no longer begin with
/// `/` for any reason — a moved test file, a different symlink, a root computed
/// with the wrong number of `deletingLastPathComponent()` — because the only
/// way out of this function is a real relative path or an error.
///
/// This is also the fifth copy of one rule in a directory whose guards exist to
/// stop the fifth copy of one rule. It is a shared helper for that reason too.
enum ProjectTree {

    /// A scan that could not see the tree it is about. THROWN, never returned:
    /// the caller must not be able to reach its assertion with a partial or
    /// deformed walk, because an empty offender list is also what a walk that
    /// enumerated nothing produces.
    struct Unreachable: Error, CustomStringConvertible {
        let reason: String
        var description: String {
            "UNRUNNABLE — this scan could not see the project tree, so any verdict "
                + "it prints is about nothing: \(reason)"
        }
    }

    /// The iOS project root — `ios/Bain Luck/` — from the calling test's own
    /// location. The default argument expands at the CALL SITE, so each guard
    /// still walks up from itself; all of them live in `BainLuckTests/`, two
    /// levels down.
    static func root(from filePath: String = #filePath) -> URL {
        URL(fileURLWithPath: filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .resolvingSymlinksInPath()
    }

    /// `url` expressed relative to `root`, or an error. Both sides are
    /// symlink-resolved first, because one of them comes from the compiler and
    /// the other from the filesystem and only the filesystem's is canonical.
    static func relativePath(of url: URL, under root: URL) throws -> String {
        let file = url.resolvingSymlinksInPath().path
        let base = root.resolvingSymlinksInPath().path
        let prefix = base.hasSuffix("/") ? base : base + "/"
        guard file.hasPrefix(prefix) else {
            throw Unreachable(
                reason: "\(file) is not under \(base), so it has no relative path here. "
                    + "The old code silently returned a deformed one instead."
            )
        }
        return String(file.dropFirst(prefix.count))
    }

    /// Every `.swift` file under `root`, as (relative path, url), sorted so a
    /// failure reads the same twice.
    ///
    /// `minimumFiles` is the anti-vacuity floor, and it throws rather than
    /// returning a short list for the same reason as above: a caller that gets
    /// a value back will assert on it.
    static func swiftFiles(under root: URL, minimumFiles: Int = 50) throws -> [(path: String, url: URL)] {
        guard let walker = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        ) else {
            throw Unreachable(reason: "FileManager would not enumerate \(root.path)")
        }
        var out: [(path: String, url: URL)] = []
        while let url = walker.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            out.append((try relativePath(of: url, under: root), url))
        }
        guard out.count >= minimumFiles else {
            throw Unreachable(
                reason: "only \(out.count) Swift file(s) under \(root.path), expected at "
                    + "least \(minimumFiles) — this is not the project tree"
            )
        }
        return out.sorted { $0.path < $1.path }
    }

    /// The same walk, with each file's text read — the shape most of the
    /// guards here actually want.
    static func swiftSources(under root: URL, minimumFiles: Int = 50) throws -> [(path: String, text: String)] {
        try swiftFiles(under: root, minimumFiles: minimumFiles).map {
            ($0.path, try String(contentsOf: $0.url, encoding: .utf8))
        }
    }
}
