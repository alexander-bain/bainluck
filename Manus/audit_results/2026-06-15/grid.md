Starting the Championship Grid Deep Audit for bainluck.com. I'll systematically audit each playoff grid (NBA, NHL, MLB, Golf) by checking structure, team identity, probability quality, source verification, interactivity, and mobile rendering. This will involve visiting each grid, performing detailed checks, and cross-referencing with Kalshi and Polymarket data.

I have completed the deep audit of the championship grids on bainluck.com. The audit covered the NBA, NHL, MLB, and Golf grids, checking for structure, team identity, probability quality, source verification, and mobile responsiveness.

The MLB grid is performing excellently, with perfect column sums and no monotonicity violations. However, I found some critical issues with the other grids:
- The NBA and NHL grids are missing columns (Win Conference, Make Playoffs).
- The NBA and NHL seasons have concluded, but the grids show stale data (Knicks at 95%, Hurricanes at 88%) instead of 100%.
- The Golf grid has multiple monotonicity violations, likely due to Kalshi minimum bid values being treated as actual probabilities.

You can find the detailed findings, source comparisons, and suggested improvements in the attached audit report.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/RM6crz5d8EFYW3czk8G5XT/sandbox/c8i77dvc1VQRwRmjhLAv2C_1781538388574_na1fn_L2hvbWUvdWJ1bnR1L2F1ZGl0X3JlcG9ydA.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvUk02Y3J6NWQ4RUZZVzNjems4RzVYVC9zYW5kYm94L2M4aTc3ZHZjMVZRUndSbWpoTEF2MkNfMTc4MTUzODM4ODU3NF9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJGMVpHbDBYM0psY0c5eWRBLm1kIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=oHAiWpt1bgZxM9CoIV7uj3DPeBzgQDhkmobHVEyt9RdzjmFBAuKv2rbw6WZ4rv-rHUrVxhCq7TX0OSmCWLNmNlpG9cj9foGr5sDEd~V01-hIQJ3ZsJO-WRD6Z2NmW1bsFiTe3ggh0pg76xMDjz2zdYpsoKjlttyT1zlEhEhlQGlb7p4qPin8mSbjwwGw8b2loTuiIjpJaTLyDJVpY8t4v2o-Z0wt7JsS5QwoyE2Jsp~7DfoXAmNGHXW9KeTs9BImXnG6GPDXwVKBixVgnWUqfcuSRCyekvj5885HWwv70uttDyupefmVGTM-vDWM4TRbWIGFbR5NB1HHrF1coMGMxA__