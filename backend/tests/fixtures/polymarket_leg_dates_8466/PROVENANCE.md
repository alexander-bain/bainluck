# #8466 fixture provenance

`gamma-event-1038648.json` — Polymarket Gamma `GET /events/1038648`, captured
2026-09-24T20:58:22Z. SOURCE BYTES, unedited.

The event ("US-Iran ceasefire continues through...?") ends 2026-10-31T23:59Z.
Its six legs each carry their own `endDate`: Sep 20 (closed at capture),
Sep 25, Sep 30, Oct 31, Nov 30, Dec 31. Production stored all six children
with the event's Oct 31 (`futures_markets` 61300896, 61311441, 61318327,
61318328, …), and Discover printed "Resolves Oct 31, 2026" on the Sep 30 leg.
