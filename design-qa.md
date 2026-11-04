# Futures preview · Iteration 2 review

Ready for Alex’s design review. The first pass was rejected for insufficient similarity to Event Details; this record supersedes the earlier pass-level visual verdict.

Rendered code: `2629efea23`. Deployment: `https://bainluck-bvmat1i4o-alexander-bain.vercel.app`. Captures: Nov 3, 9:31 PM PT. [Design note and actual web/SwiftUI mapping](docs/designs/futures-page-2026-11.md). [Side-by-side evidence](docs/designs/futures-page-2026-11/iteration-2/README.md).

The reference images are actual production Event Details pages: live UNLV–Northern Arizona and the recent Canucks–Ducks final. Six market examples are paired at 390px and 1280px per half, with four additional one-leg state-study pairs. Source screenshots are unchanged; labels/dividers are outside their pixels. The hosted futures captures have no privacy overlay or Vercel toolbar. The native page’s existing tenths/auto-scaled axis is visible as a reference; futures follows the requested whole-number, fixed-axis rules.

Compared shared shell, hero typography/identity boxes, card spacing, section headings, range chips, chart frame and Bigger Picture rail. The shapes change their own body. Settled Georgia names the winner and uses actual Won/Lost marks. A retracted one-leg grade remains unavailable. Missing histories stay explicit.

Build passed; typecheck matches baseline 65 with zero new errors; 12 focused tests and 4 startup checks passed. All 16 futures viewports render without document overflow or final-preview console errors. Field expansion reaches all 24 legs, threshold selection updates the answer, ranges work, fullscreen Escape restores focus, and a related card reaches its market. The age-stamp timezone mismatch was reproduced with a UTC server and Pacific browser and fixed in this preview; age labels now share the reader clock.

This is prototype review evidence, not Alex’s approval, a production release, or an independent cert. No PR to master was opened. Taste calls E/F remain in the note; A–D are retired. Earlier captures remain archived under `docs/designs/futures-page-2026-11/`.
