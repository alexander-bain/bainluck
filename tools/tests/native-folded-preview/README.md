# Folded DNPL source controls

Ship: the event-detail iPhone reader can show a folded DNPL probability, observation clock and disposable chart endpoint while committed persistence catches up, with full revision/origin authority.

`bash tools/tests/native-folded-preview/run.sh` compiles the actual Swift reader, fold revision and point value types, plus the exact pure chart projection methods extracted from `OddsChartView.swift`. It runs the same reader/chart test methods in `FoldedBlendPreview10090Tests.swift` with minimal model surfaces and assertion helpers. Compiler flags match Swift 5 language mode and default MainActor isolation. This does **not** build the app, exercise its real model decoder/lifecycle, render SwiftUI, or prove an installed phone received a value.

`bash tools/tests/native-folded-preview/run.sh --baseline abb1c06fe3a4b52d4a3f9af34183ec10c2ca62a2` runs a compatible regression probe against the original reader. Expected failure: valid folded display is withheld, unknown folded metadata is accepted, and a folded frame can masquerade as a singleton during membership transition. Preserve this failure.

Native's full app tests must run the XCTest files with real models and the controller/transport tests. Native retains Xcode, build/archive/upload and device ownership. The event-detail reader opts in with `preview_protocol=folded-v1`; other transport callers retain their existing URL.

## Folded v2 follow-on

The same harness also runs independent-origin epoch/sequence, session-open,
reconnect, same-tuple expiry, explicit retirement, sibling retention and
withdraw/recompose controls. V2 uses `preview_protocol=folded-v2`. Its parser
accepts full authority withdrawals without a probability while a sibling remains
pending; that sibling keeps its first-seen deadline. App/controller/transport
execution and installed-phone validation still belong to Native's real build.

## Membership boundary

`BlendPreview.readerAfterMembership` is the authoritative detail's membership
boundary (the adopted detail calls it): a changed fold prunes removed members'
fences and floors, keeps survivors' identity/deadline fences, withdraws the
display, drops the session and refuses old-membership packets, and the page
reopens its stream on the new fold. The harness runs the reader half (both
v2 and v1 paths); `AMembershipChangeReopensTheFoldedPreview10090Tests` covers
the page's stream reopen and runs only in Native's real build.
