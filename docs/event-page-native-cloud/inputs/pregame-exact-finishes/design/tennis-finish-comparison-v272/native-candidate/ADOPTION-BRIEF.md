# Native tennis finish comparison — v272

PILLARS: FORMATTING / TRUTH. SHIP: compare all four exact set finishes in one graphic, with pre-match chances separate from current availability and the observed score.

Use all 154 absolute paths in `composed-sources.json`. This replaces the v260 composition for these shared families, with only LiveTennis.swift and TennisFocus.swift changing product behavior. The v271 darts/squash and v268 live-racing supplements remain separate. Do not add duplicate definitions or harness @main files to app targets.

The exact-finish card uses aligned 0–100% bars, four original outcomes and original baseline values. Fils 2–0 remains visible with a hatched baseline and No longer possible; the three other outcomes say No recent price. This observation does not settle a market. Original details, score, cutoffs, model, rail and reader hold semantics remain unchanged.

The expanded card removes nested panel padding and its repeated eyebrow. Phone reader footer keeps arrows/count/swipe guidance without repeated title/dots; wide presentation retains them. Fonts use SwiftUI text styles, with no Dynamic Type cap. AX3 may need vertical scrolling; fit is NOT claimed from browser evidence.

Run `python3 verify-source.py` for identity checks only. Under Native ownership, `python3 run-native-gates.py --render` retains every v260 check/render and adds four mounted tennis configurations: 375×667 and 393×852, standard and AX3, each covering all four cards, unavailable state and details return. No Apple commands were executed here. This is an optional reference; existing NFL UX → Native → Integrator work retains priority.

Review actual native captures for complete labels, a common baseline scale, hatch visibility, current/unavailable distinction, fixed match context, scroll reachability and original-market detail return. Exercise VoiceOver, touch, swipes and app integration separately. Capture success is not visual acceptance.

Swift compilation, native runtime/render, app/device and TestFlight: NOT_RUN.
