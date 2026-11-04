# Futures prototype evidence

[Preview](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/109085) · branch `design/futures-page-proto` · application commit `d32237d61f`.

The deployment keeps Vercel authentication. The deployment-scoped review link in [NOW #11852](https://github.com/alexander-bain/bainluck/issues/11852) works without a team login for 30 days. No project-wide protection was changed.

Captured Nov 3, 7:32 PM PT: six examples at both requested widths, plus open and settled one-leg studies (16 screenshots). The [capture manifest](capture-manifest.json) records each route and verifies no horizontal overflow. Its browser console error list is empty. The [public screenshot index](public-screenshots.json) contains sanctioned CDN links with a 30-day lifetime; the image files in this branch are the durable copies.

| Example | Preview | 390 px | 1280 px |
|---|---|---|---|
| Duel · Kansas Senate | [Open](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/109085) | [Screenshot](duel-390.jpg) | [Screenshot](duel-1280.jpg) |
| Field · Closest Governor race | [Open](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/108629) | [Screenshot](field-390.jpg) | [Screenshot](field-1280.jpg) |
| Quantity · Denver snow | [Open](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/65536371) | [Screenshot](quantity-390.jpg) | [Screenshot](quantity-1280.jpg) |
| Participation · CFP qualifiers | [Open](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/227) | [Screenshot](participation-390.jpg) | [Screenshot](participation-1280.jpg) |
| One leg · as served | [Open](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/109918) | [Screenshot](one-leg-390.jpg) | [Screenshot](one-leg-1280.jpg) |
| Settled today · Georgia Governor | [Open](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/108645) | [Screenshot](settled-today-390.jpg) | [Screenshot](settled-today-1280.jpg) |
| One leg · open study | [Open](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/109918?state=open) | [Screenshot](one-leg-open-390.jpg) | [Screenshot](one-leg-open-1280.jpg) |
| One leg · settled study | [Open](https://bainluck-1no21ut75-alexander-bain.vercel.app/kernels-preview/futures/109918?state=settled) | [Screenshot](one-leg-settled-390.jpg) | [Screenshot](one-leg-settled-1280.jpg) |

Production responses: Nov 3, 2026, starting at 6:33 PM PT. See the [design note](../futures-page-2026-11.md) and [request manifest](../../../frontend/app/kernels-preview/futures/_data/manifest.json). Georgia's stored settlement time is 6:27 PM PT, with authoritative `api_settlement` grades. The one-leg study states are labelled assumptions and do not alter its captured grade.

Validation: Next.js build passed; TypeScript 65 existing errors against baseline 65 (zero new); prototype guard tests 7/7; startup imports 4/4. Hosted field expansion reaches all 24 outcomes; threshold selection updates the answer; fullscreen Escape returns focus. No production route or API changes, no Midterms/`feed_collections.py`/`events.py` edits, no PR or master push.
