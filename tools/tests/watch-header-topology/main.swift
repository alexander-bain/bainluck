import Foundation

// Compile with the actual policy extracted from PickerCurrentGameJourneyTests.swift.
// Synthetic topology inputs cover rejection behavior; these are not native focus proof.
let frame = CGRect(x: 8, y: 74, width: 154.5, height: 17)
func child(_ rect: CGRect = frame, text: Bool = true, id: String = "", descendants: Int = 0) -> WatchHeaderLabelTopology.Child {
    .init(frame: rect, isStaticText: text, identifier: id, descendantCount: descendants)
}
func valid(_ roots: Int = 1, labels: Int, frame rect: CGRect = frame,
           children: [WatchHeaderLabelTopology.Child], rootText: Bool = true) -> Bool {
    WatchHeaderLabelTopology.isUnique(rootCount: roots, rootIsStaticText: rootText, labelCount: labels, rootFrame: rect, children: children)
}
precondition(valid(labels: 2, children: [child()])) // Observed final/closed wrapper + leaf.
precondition(valid(labels: 1, children: [])) // A platform exposing only the semantic row.
precondition(!valid(2, labels: 2, children: [])) // Two identified result rows.
precondition(!valid(labels: 3, children: [child()])) // Separate duplicate outside the root.
precondition(!valid(labels: 2, children: [])) // Same-label sibling is never a permitted child.
precondition(!valid(labels: 2, children: [child(frame.offsetBy(dx: 0, dy: 20))])) // Distinct visible copy.
precondition(!valid(labels: 3, children: [child(), child()])) // Multiple child copies.
precondition(!valid(labels: 2, children: [child(id: "second-semantic-row")]))
precondition(!valid(labels: 2, children: [child(text: false)]))
precondition(!valid(labels: 2, children: [child(descendants: 1)]))
precondition(!valid(labels: 1, frame: .zero, children: []))
precondition(!valid(labels: 1, children: [], rootText: false))
print("Header topology policy scenarios PASS")
