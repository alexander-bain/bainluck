Starting the Market Accuracy Ground Truth audit. I'll visit bainluck.com/feed to select 4 events, then audit each for monotonicity, cross-game contamination, and cross-reference with Kalshi.

I notice that the Lakers team page doesn't show recent game results (unlike the Hurricanes page). The NBA season appears to be over with only futures remaining. Let me adapt my approach - I'll focus on events that DO have the market sections (totals maps, margin maps, additional markets) which are the bainluck equivalents of "Projected Scoring" and "Spread" sections. I've found that the NHL game (event 14798909) has these sections. Let me now look for more events with these features.

The Market Accuracy Ground Truth audit is complete. Here are the key findings:

**Overall Result:** 2/4 events fully clean, 2/4 have monotonicity violations in series-level or cross-source markets.

**Critical Findings:**
1. **Series Total Goals Monotonicity Violation (WARNING):** On NHL Stanley Cup Finals game pages, P(50+ goals in series) = 50% while P(45+ goals in series) = 38%. This is mathematically impossible since 50+ ⊂ 45+. This violation is replicated identically across Games 3 and 5.

2. **MLB Game Props Monotonicity Violation (WARNING):** On the Braves vs Padres game, P(Braves -3.5) = 19% > P(Braves -2.5) = 9%, which violates the subset relationship.

**Good News:**
- All game-level "Total maps" (Full game goals map) sections pass monotonicity perfectly
- No cross-game contamination found at the game level
- No wrong-game outcomes detected

**Kalshi Cross-Reference:** Could not be completed for live price comparison since the NHL Finals series is over and all series markets have been settled/removed from Kalshi.

The full JSON report and detailed markdown report are attached.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/37u8WnZCuYjtdp8FdLsyMb/sandbox/B4Prhih2rrdea3sLesyLSp_1782380233200_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9hdWRpdA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvMzd1OFduWkN1WWp0ZHA4RmRMc3lNYi9zYW5kYm94L0I0UHJoaWgycnJkZWEzc0xlc3lMU3BfMTc4MjM4MDIzMzIwMF9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjloZFdScGRBLmpzb24iLCJDb25kaXRpb24iOnsiRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjE3OTg3NjE2MDB9fX1dfQ__&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=YLjYLMMER9IUmkOQig9J-KvM7Kz5TehLHhhdI1KWbQvPxA6rjxbr9wV4TU3O3pIImOg6EvPadSF1mc8u7lhedaqqQl5I-TpJ1wCJpsaa7UDcoo-S0DNtjQYh2BxOiR9Oisz3oGD-2SL7OdlEqyJ2KdWrnT~THq9qRg3~OwxeAdyfusg5WOxx~dXi3RYJEseuYP75YGlvRTpBmM6-JWCmwegjnzT-mvv5xBOutBN5SNeSZo4UFaPCb-lJ301rR7SaD8BPSX8-p6b-7PchgWPvPM8D5axewSsfwTJqq-PH5rcNblK5nSTjk9yLowiuJM8l8io0X6hVznE9PPtUZIsFHA__


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/37u8WnZCuYjtdp8FdLsyMb/sandbox/B4Prhih2rrdea3sLesyLSp_1782380233200_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9hdWRpdF9yZXBvcnQ.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvMzd1OFduWkN1WWp0ZHA4RmRMc3lNYi9zYW5kYm94L0I0UHJoaWgycnJkZWEzc0xlc3lMU3BfMTc4MjM4MDIzMzIwMF9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjloZFdScGRGOXlaWEJ2Y25RLm1kIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=EE7LMFeqTfnSn3hMmoho3twLAo2Lx-JH0GIYZzWrsywll4HIjZcUjguADCfzUEYDd94hAPiKwXlp2Q~xZHtCnzp7tR3Z0I5TVOH1tvnwh4aGQD-NcNx7QCVA~DqFAsPL75OrC2j5gh04v5CATGLqFwef8Q~4yTV9NB13zdXgmiwyazB7sxbDRY6rWvVO2bxfZSfM1-BkE8SAigXIL7gDRWsu2ZnI6jQ7x0eFl~OFVNH8ffG6CThp7JXOmRYcOkoNQahVsSm~5LgHAmKi0BvKKOZHtXk33VZFiS2jNZ~c45DxrCTbXFTPTs~SWbXHoSoGbBtxNzRYeMJciq~A7RHrqw__