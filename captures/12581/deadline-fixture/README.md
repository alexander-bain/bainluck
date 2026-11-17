# Same-deadline source-mark contract preview

These 390 pt SwiftUI renders use the complete existing historical November 3 fixtures for the November 30 and December 31 boards. All 13 candidate markets and their outcomes are supplied; the unchanged selectors choose six members per board. The screenshots show the complete December board and all six of its members. They are local server-contract previews, not current production numbers or installed-app captures.

The open No sheet shows the original rounding: source No 11.5% displays as 12% in the source row; the existing card displays Yes 89% and No 11%. The new method explains that the pair is rounded to total 100%. Both original probabilities and rendered percentages are unchanged.

The sheet method function is copied from Builder C's PR #12878 at 1b59e048cd; its exact source is retained in native-method-source.txt. That correction lets single-source marks print the server explanation. Installed presentation acceptance belongs to C; this render does not establish installation or navigation.

Every original field is preserved when source_mark is removed from the complete after-payload. The two boards' combined compact JSON is 29,098 bytes before and 38,777 after. These are fixture sizes, not production latency measurements. Source times remain absent because row-touch clocks do not prove when these input prices were read.

Separate regression cases cover a Yes-only market (No is calculated and explicitly explained), missing/unknown sources, real zero, unknown results, and the pre-existing stored-No/displayed-complement conflict. That conflict gets a mark with state none and reason display_basis_conflict; neither old value is silently changed. The screenshots do not claim such a conflict was observed live.
