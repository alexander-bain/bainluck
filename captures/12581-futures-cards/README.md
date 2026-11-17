# Futures card source marks — local review render

Server candidate: `48e1519717ffcb4524a414f5689a7bd9e00d7ebb`, stacked on futures-detail PR #12870.

This is real formatter output from the existing Super Bowl fixture, rendered at 390 pt in macOS SwiftUI using the existing native source-mark model and sheet rows. It is not a production request or installed-iPhone proof. The fixture and evaluation clock are in `futures-card-marks-preview.json`. Field normalization is existing behavior; the source inputs are its pre-normalization prices.

Known native integration gap: the current single-source sheet method says only “Sportsbook's price” and ignores the server `method`. The server supplies “scaled with the other outcomes to total 100%” for the 25% single-source row. Builder C must retain that explanation when integrating futures cards. The preview deliberately preserves the current behavior. The blend explanation is wrapped by the local preview layout.

The payload comparison covers 21 complete browse/faceted/list/search/typeahead payloads, including three verified-title entry aliases. Removing only `source_mark` reproduces every existing field and the same SQL statement sequence. The comparison records compact JSON byte counts; these are local fixtures, not live latency measurements.
