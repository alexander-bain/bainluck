// #5105 — the internal switch for the Discover page's opening-edition wiring.
//
// ON, the page pins later pages to the edition page zero painted, restarts from
// page zero when the server retires that edition, carries the ordinary-live
// continuation's section membership through filtering, Back-restore and
// paging, and renders the continuation under its own heading
// (`hooks/useDiscoverOpeningEdition`, `components/discover/ContinuationSections`).
//
// OFF, the page is exactly today's: same requests, same reconciliation, same
// snapshot bytes, one flat list. `true` here is the LOCAL switch-on release
// candidate only; rollback is this one constant back to `false`.
//
// 🔴 A CONSTANT, NOT A QUERY PARAMETER OR AN ENVIRONMENT VARIABLE. Turning this
// on is a release decision that also needs the backend to serve sections and
// the native client to read them; nobody reaches it from a URL or a deploy
// variable. Tests mock this module to exercise the ON path against the real
// page.
export const DISCOVER_OPENING_EDITION_ENABLED = true;
