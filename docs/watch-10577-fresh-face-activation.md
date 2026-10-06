# #10577 — Activate the freshly configured complication face

PILLAR: FORMATTING · TRUTH.
SHIP: The actual Watch face complication tap reliably opens the selected game.
Child of #4933; fixture-backed hosted acceptance remains distinct from physical
Watch, production, distribution and background delivery acceptance.

Retained merged run37394025988 at35bcda2fe4 failed
`WidgetTapJourneyTests.testActualComplicationHost`: the launcher was not found.
Its screenshot and hierarchy show Carousel still in `Face Library View`, with
the Siri Modular preview, `Switcher Face Title` and Edit control. Two home presses
did not establish an active face. The failure was in host activation preparation;
it did not pay mounted-complication or warm-route acceptance.

After selecting the installed Your game complication, setup now leaves the editor
with one home press and waits for an observed library or active face role. In the
library, it requires the exact Siri Modular title and one named customizable
preview with a hittable center inside the viewport, then taps that real preview
once. It waits for Watch Face with Face Library absent before querying the actual
bottom-left launcher. Already-active faces require the same final role check.
Failures retain screenshot/hierarchy evidence. No extra sleep, blind retry, URL
injection, activation callback or app relaunch substitutes for the face tap.

The focused UI regression configures a fresh face, asserts its active role,
and taps the mounted launcher through the existing warm-return helper. Original
cold/offline, empty-selection and warm picker/help journeys use the repaired
mount helper. Launcher ancestry/label, visibility/hittability, physical UI taps,
process UUID, accepted route count, selected probability and overlay assertions
remain intact. The regression adds no test timeout exception. The existing
hosted marker gate now requires its fresh-face marker and passing XCTest method;
local receipt guards accept 17 tests and reject an absent marker, missing method,
or failed method even beside a green summary.

No product, signing, project, receipt parser, observation adapter or canonical
reader source changes. No local Xcode/simulator or Apple action is performed.
Integrator owns composition and merge; #4933 retains physical acceptance.
