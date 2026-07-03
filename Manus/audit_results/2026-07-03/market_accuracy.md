Starting the Market Accuracy Ground Truth audit. I'll visit bainluck.com/feed to pick 4 events, then systematically audit each one for monotonicity, cross-game contamination, and data accuracy.

Making progress on the audit. I've analyzed the first NBA Finals event (Game 4, Knicks vs Spurs). The page structure uses "Additional Markets" rather than "Projected scoring" sections. The game is completed so all markets show settlement values (0% or 100%). Now moving on to check more events including live/scheduled MLB games which will have actual probability distributions to check for monotonicity.

The Market Accuracy Ground Truth audit is complete. Here are the key findings:

**Cross-Game Contamination: CONFIRMED (CRITICAL)**

Two of the four audited events show cross-game contamination in the NBA Finals series (Knicks vs Spurs):

1. **Game 4** (`/events/14918299`): Shows 18 1H O/U thresholds when Kalshi only has 9 for this game. The extra 9 thresholds (99.5–123.5, all at 100%) are from Game 3 where 1H total was 125. Threshold 111.5 appears in BOTH the 0% and 100% groups simultaneously — impossible for a single game.

2. **Game 3** (`/events/14870286`): 1H O/U 123.5 shows 0% when 1H total was 125 (should be 100%). This threshold is likely from Game 2 contaminating Game 3's page.

**Monotonicity: CLEAN in primary sections**
- Total Maps (Projected Combined Scoring equivalent): All correctly monotonic
- Player Props: All 25+ players checked across events are correctly monotonic
- The contamination creates apparent monotonicity violations only in the Additional Markets section where outcomes from different games are mixed together

**Root Cause:** Bainluck appears to aggregate markets across the entire series ticker (KXNBA1HTOTAL) rather than filtering to only the specific game event date.

The full JSON report and detailed markdown analysis are attached.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/foMXYZX4j6WxzxroxWwiUw/sandbox/bcRhcCoaYGxKpQqbHn70JV_1783120545935_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9hdWRpdA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvZm9NWFlaWDRqNld4enhyb3hXd2lVdy9zYW5kYm94L2JjUmhjQ29hWUd4S3BRcWJIbjcwSlZfMTc4MzEyMDU0NTkzNV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjloZFdScGRBLmpzb24iLCJDb25kaXRpb24iOnsiRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjE4MzAyOTc2MDB9fX1dfQ__&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=WfjFmhKNY7rsnZ-~Zl8dGarfk1SLZvsb~hKNNBLStg6hCIaRkRi~10rgs4bL7mWiJlj1TFomrjdTMvBxHyfPrkptbUeSzKpQjUCNQJPynBz87EI2zv1etNjUpW8rokL-8wJCoG2gIB3nwT6ALpYNrWz2iEkczIwt5v7e4-G3Yxc88QtC9uXFGTzkGRt~cvX2Er-smrPLRfVGlr9BK1LtgcEE~lQ4PPK~P4PBrI5IQ4mpslS0uu6DJoqCi~a6u639pVVTIZw48TDD4siAUZaxnrhKpV6mVvvUxDYWdD6QgCBZW3BfUzGxUsxAFIB7z5OR2aM4cUKL7EqdmZ5S6Y86ng__


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/foMXYZX4j6WxzxroxWwiUw/sandbox/bcRhcCoaYGxKpQqbHn70JV_1783120545935_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9ncm91bmRfdHJ1dGg.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvZm9NWFlaWDRqNld4enhyb3hXd2lVdy9zYW5kYm94L2JjUmhjQ29hWUd4S3BRcWJIbjcwSlZfMTc4MzEyMDU0NTkzNV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjluY205MWJtUmZkSEoxZEdnLm1kIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxODMwMjk3NjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=Lv7mtc8FuNFi5qAqEXxtp1dJ7-Vapa-me3bD7~AmReoSsFjY~QikrySr~5vU5VW8BzANw9TsuKXh5hIkXKK8rd60V0YtMaEMWIZ6UnvYXtoGHXHrZ4ixdPKEhhkh4D-XCoYQc527DGdj0E1ushgS14IJqWpK0BIYBgFkR5YFs2N0rACEKTLsryjYO1uGmmM3SItEeVDFyhth1pp45JOLIkQD6f~XemRhxLmuHMQDjCPbMZs0PNkjfuzY-zM5bSUTgLb5xa5Oi66DFoJl4ekuFHWv-BvtsGNuUwmm79CkozRl8-vOm5AGg1rz0vrPALP2dMCm7OSlRnw8sOjDqr4LDQ__