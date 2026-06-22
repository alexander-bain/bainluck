Starting the Market Accuracy Ground Truth audit. I'll visit bainluck.com/feed to pick 4 events, then audit each for monotonicity, cross-game contamination, and cross-reference with Kalshi.

The Market Accuracy Ground Truth audit is complete. Here's a summary of findings:

**Result: 4/4 events clean — no monotonicity violations, no cross-game contamination detected.**

Key findings:
- **Argentina vs Austria** (scheduled FIFA World Cup game): All O/U thresholds perfectly monotonic across 9 full-game thresholds, team totals, period markets, and spreads. Kalshi cross-reference shows probabilities match within 0-1%.
- **Iran vs Belgium** (completed 0-0): All markets correctly settled at 0%. No contamination.
- **LA Angels vs Athletics** (completed MLB): Limited markets, all properly settled. No contamination.
- **NY Liberty vs LA Sparks** (completed WNBA): No additional markets present on the page.

**Important limitation:** The NBA and NHL seasons are over, so the primary contamination risk scenario (playoff series with multiple games between same teams) was untestable. FIFA World Cup games have zero contamination risk since each matchup occurs exactly once.

BainLuck shows 3 extra O/U thresholds (6.5, 7.5, 8.5) beyond what Kalshi offers — these are sourced from Polymarket, not from a different game.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/jSSUucKtTsVJyp3QxwHKb9/sandbox/v8fPy42cdSAYezBV8bifWl_1782142164110_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9hdWRpdA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvalNTVXVjS3RUc1ZKeXAzUXh3SEtiOS9zYW5kYm94L3Y4ZlB5NDJjZFNBWWV6QlY4YmlmV2xfMTc4MjE0MjE2NDExMF9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjloZFdScGRBLmpzb24iLCJDb25kaXRpb24iOnsiRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjE3OTg3NjE2MDB9fX1dfQ__&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=sFvrK1dYkSZ2YFybzyjLNsQ~nKCsRtwZELBOF123dnh0~5Ug3wcukPOydAxHWXbIeq9gazbdPWxOloJ53C6siijwbxDw9-1CF086TRck9vRcmz7rAfnxuboaoqZKWUapLVSfYsgG9WdZZmxwZV486TvkmeFOaR99ok26h702fC~JVKMCoJRMk49XxhCnD~m7QLgmccQ1Na~9~qga4ZClr2PCy881ANHJ693mu~GTPoSqLwhFRmVXKNctlrvnJmKWQlLjkUj2Tc4vskdf5-S9FYxyIWol1bgtu~WicWI847WMHAnXFN0e~r2xFdHkeR6A569OAyod7yrkUAnp0I-oxQ__


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/jSSUucKtTsVJyp3QxwHKb9/sandbox/v8fPy42cdSAYezBV8bifWl_1782142164110_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9hdWRpdF9yZXBvcnQ.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvalNTVXVjS3RUc1ZKeXAzUXh3SEtiOS9zYW5kYm94L3Y4ZlB5NDJjZFNBWWV6QlY4YmlmV2xfMTc4MjE0MjE2NDExMF9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjloZFdScGRGOXlaWEJ2Y25RLm1kIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=dEzQobfy9qlJncun8WFWOylWc9AOzBS4a0B~h9RctkoBF7kBFX2-BKvBNkY8s0eiM3eqOvtcBQzlQYy8QrtdO1hBTFRPt4LeOzoNwPLdOv2DKFmptfrSRAY-faW93NouYgvF1iTznLMtQ~w3ovM2XFCrb8I2BzHztWlgdJMLm5v8j0B09tUvYSXJ~KRUFF8RYi9CoClpfNN20Qraz1oQKn28ttxy9h08CQfh-alp0GK5PW3qBwGT1S48Y8RPTJAV2PjDomrPWwzCGoTmrddYI9c3sFD3VDW28KDM~bKDE-fBqhXTRZSFY3hRe9MyB58WFWFm5wZUfii9Tj6g-N2gGw__