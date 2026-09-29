# #9524 web CI wiring correction — SOURCE PASS

Reviewed exactly two files on base 9f2f4a5da1964d48ba9f626a19fbeb69e7abc294; hashes are in the adjacent JSON.

The #7064 source-wiring assertion now names the actual useGameMarketsStream(eventId, event?.id ?? eventId) call and still requires its data to enter servedGameMarkets. The import assertion, useMemo gameMarkets binding, and withoutEventOwnMoneyline(servedGameMarkets) assertion remain intact. The unchanged page source confirms that exact path. The production-fixture assertions still require precisely two own-moneyline rows removed from each array, 64 real props retained, and every other market preserved name-for-name. No business assertion was weakened.

BUILD.txt changes only remove trailing whitespace from lines183-185; comparison after stripping old line tails reproduces the new file exactly. No build result or other log content changed.

No production-source change. Reviewer ran no tests, build, or typecheck; author owns focused checks and CI.
