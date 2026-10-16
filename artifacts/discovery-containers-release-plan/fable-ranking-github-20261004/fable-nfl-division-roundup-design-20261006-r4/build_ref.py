import json,re,html
css=open('proto.css').read()
EX=json.load(open('examples.json'))
# ---- card rules, copied verbatim from the prototype stylesheet
want=[r'\.num\{',r'\.card\{',r'\.khead\{',r'\.kicker\{',r'\.tag\{',r'\.headline\{',r'\.headline\.long\{',r'\.rows\{',r'\.row\{',r'\.row \.n\{',r'\.row \.n small,',r'\.row \.t\{',r'\.row \.meter\{',r'\.meter\{',r'\.meter i\{',r'\.src\{']
rules=[]
for w in want:
    m=re.search(r'^'+w+r'.*$',css,re.M); assert m,w; rules.append(m.group(0))
card_css='\n'.join(rules)
open('roundup-card.css','w').write(card_css+'\n')
LIGHT="--sans: ui-sans-serif,-apple-system,BlinkMacSystemFont,'SF Pro Text',system-ui,'Inter','Segoe UI',Roboto,sans-serif; --mono:'JetBrains Mono','SF Mono',ui-monospace,Menlo,Consolas,monospace; --bg:#F5F5F7; --card:#FFFFFF; --elev:#F0F0F2; --line:#E5E7EB; --ink:#111827; --ink2:#4B5563; --ink3:#6B7280; --track:#ECEEF2; --a:#2563EB;"
DARK="--sans: ui-sans-serif,-apple-system,BlinkMacSystemFont,'SF Pro Text',system-ui,'Inter','Segoe UI',Roboto,sans-serif; --mono:'JetBrains Mono','SF Mono',ui-monospace,Menlo,Consolas,monospace; --bg:#0B0F17; --card:#151B26; --elev:#1C2431; --line:#283244; --ink:#F3F4F6; --ink2:#C3CAD6; --ink3:#97A1B2; --track:#232C3B; --a:#3B82F6;"
for t in re.findall(r'--[a-z0-9]+:#[0-9A-Fa-f]{6}',LIGHT+DARK): assert t.replace(':',':') in css.replace(' ',''), t
def pct_fill(n): return n
def card(c,src='Venue prices: Kalshi'):
    rows=''.join(f'<div class="row"><div class="n num ">{r["num"]}<small>%</small></div><div class="t">{html.escape(r["text"])}</div><div class="meter" title="{html.escape(r["text"])}: {r["num"]}%"><i style="width: {r["num"]}%;"></i></div></div>' for r in c['rows'])
    tag=f'<span class="tag">{c["tag"]}</span>' if c.get('tag') else ''
    hl='headline long' if len(c['headline'])>44 else 'headline'
    return f'<article class="card"><div class="khead"><span class="kicker">Round-up</span>{tag}</div><h2 class="{hl}">{html.escape(c["headline"])}</h2><div class="rows">{rows}</div><div class="src">{src}</div></article>'
E={c['cid']:c for c in EX}
def spec(cid,theme,w=358,src='Venue prices: Kalshi',ex=None): return f'<div class="sp sp-{theme}" data-ex="{ex or cid}" style="--w:{w}px"><div class="slot">{card(E[cid],src)}</div></div>'
CTX=json.load(open('ctx_uris.json'))

RULINGS=[("Bars are blue.","Green stays for the leader within one contest and for \"Won\"."),
("New parts, built to this reference.","The header and rows are not the existing grouped-card parts. If the card then looks inconsistent with other feed cards, the other cards may be the ones to change."),
("Rows run highest probability first.","The rule selects the four closest races; the card lists them high to low."),
("Tapping the card opens a container.","The container shows an event card for each item in it. Rows are not separate links."),
("The footer wording is accepted for now.","It can change if it looks wrong in production.")]
SETTLED=[("Light only.","The product has no dark mode. Dark values stay on file below and are not part of the check."),
("Product colors where they exist.","Seven of the nine colors already exist in the product under other names. See the Colors table."),
("The product's number format.","The product's own formatter applies, so 99.7% prints as >99%. No exception is needed.")]
MUST=[("The number is the Bain Luck blend.","The prototype showed venue prices."),
("The footer line.","\"Venue prices: Kalshi\" belongs to the prototype. The product's line goes here, in the same style."),
("The buttons under the card.","Like, Share, Not for me and Details were test instruments. The product's existing card actions apply, with their own icons."),
("The whole card is one target.","A tap opens the NFL divisions container. Rows are not separate targets.")]
MAY=[("Card width","to fit the product's column. The card is fluid; it was checked from 340 to 448."),
("Font faces","to the platform's system faces, keeping sizes and weights."),
("The tag text","to the product's own league or topic name."),
("Color names","to the product's tokens, as mapped in the Colors table.")]
MAYNOT=["Type sizes, weights, spacing, corner radius or bar height.","The order of parts: header line, headline, rows, footer.","Row order: highest probability first.","The number on the left with the small percent sign, and a bar under every label.","No icons, emoji, chevrons, logos, images, colored text or motion inside the card.","No ellipsis. Labels wrap."]
PROD={'--bg':('--surface-deep','same'),'--card':('--surface-card','same'),'--line':('--surface-border','same'),'--ink':('--text-primary','same'),'--ink2':('none','keep #4B5563; the nearest product grey is too faint on the tag fill'),'--ink3':('--text-secondary','same'),'--elev':('--surface-elevated','same'),'--track':('--surface-elevated','#F0F0F2; the difference is not visible'),'--a':('--series-1','same')}
TOK=[('--bg','Ground behind the card','#F5F5F7','#0B0F17'),('--card','Card surface','#FFFFFF','#151B26'),('--line','Card border, footer rule','#E5E7EB','#283244'),('--ink','Headline, number, label','#111827','#F3F4F6'),('--ink2','Tag text','#4B5563','#C3CAD6'),('--ink3','Kicker, % sign, footer','#6B7280','#97A1B2'),('--elev','Tag fill','#F0F0F2','#1C2431'),('--track','Bar track','#ECEEF2','#232C3B'),('--a','Bar fill','#2563EB','#3B82F6')]
tokrows=''.join(f'<tr><td><code>{n}</code></td><td>{u}</td><td><span class="chip" style="background:{l}"></span><code>{l}</code></td><td><code>{PROD[n][0]}</code><br><span class="sm">{PROD[n][1]}</span></td><td><span class="chip" style="background:{d}"></span><code>{d}</code></td></tr>' for n,u,l,d in TOK)
li=lambda L:''.join(f'<li><b>{a}</b> {b}</li>' for a,b in L)
MEAS=[('Card','Padding 18 top, 18 sides, 13 bottom. Border 1px. Corner radius 16. 14 between stacked blocks.'),
('Header line','Kicker left, tag right, vertically centred, at least 10 apart.'),
('Kicker','11px, weight 600, uppercase, letter-spacing 0.09em, color ink3.'),
('Tag','11px, weight 600, color ink2 on the elev fill. Padding 2 by 9. Fully rounded.'),
('Headline','23px, line-height 1.2, weight 700, letter-spacing −0.015em, balanced wrapping. Sits 8 below the header line. Over 44 characters it drops to 19px at line-height 1.25.'),
('Row','Two columns: a 49.6-wide number column, a 12 gap, then the label column. 14 between rows.'),
('Number','Monospaced, 20px, line-height 1.15, weight 700, letter-spacing −0.03em, right-aligned. Whole percentages only.'),
('Percent sign','60% of the number size (12px), weight 500, color ink3, 1 to the right of the digits.'),
('Label','15px, line-height 1.3, weight 400, color ink. Wraps to as many lines as it needs. Never truncated.'),
('Bar','In the label column, 7 below the label. 6 tall, radius 3, track color. Fill width equals the probability as a share of the track, never under 3. Left end square against the track, right end rounded 3.'),
('Footer','11.5px, color ink3. 1px rule above it, then 10 of space.')]
measrows=''.join(f'<tr><th scope="row">{a}</th><td>{b}</td></tr>' for a,b in MEAS)
page=f'''<title>Round-up Card Reference</title>
<style>
:root{{--pg:#FAFAF9;--pg-ink:#16181D;--pg-ink2:#4A4F5A;--pg-ink3:#6E7481;--pg-line:#E2E4E8;--pg-soft:#F0F1F3;--pg-acc:#0B6B4F}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--pg:#0E1116;--pg-ink:#EEF0F3;--pg-ink2:#BCC2CC;--pg-ink3:#8D95A3;--pg-line:#262C36;--pg-soft:#171C24;--pg-acc:#5FD3A8;color-scheme:dark}}}}
:root[data-theme="dark"]{{--pg:#0E1116;--pg-ink:#EEF0F3;--pg-ink2:#BCC2CC;--pg-ink3:#8D95A3;--pg-line:#262C36;--pg-soft:#171C24;--pg-acc:#5FD3A8;color-scheme:dark}}
*{{box-sizing:border-box}}
body{{background:var(--pg);color:var(--pg-ink);font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,"Inter","Segoe UI",Roboto,sans-serif;font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}}
.doc{{max-width:60rem;margin:0 auto;padding-inline:16px;padding-block:28px 72px}}
.doc h1{{font-size:30px;line-height:1.15;letter-spacing:-0.02em;margin:0 0 8px;text-wrap:balance}}
.doc h2{{font-size:20px;line-height:1.25;letter-spacing:-0.01em;margin:44px 0 10px;text-wrap:balance}}
.doc h3{{font-size:13px;letter-spacing:.07em;text-transform:uppercase;color:var(--pg-ink3);margin:0 0 8px;font-weight:600}}
.doc p,.doc li{{max-width:42rem;color:var(--pg-ink2)}} .doc p{{margin:0 0 12px}} .doc ul,.doc ol{{margin:0 0 12px;padding-left:1.2em;display:grid;gap:6px}}
.doc b,.doc strong{{color:var(--pg-ink)}}
.lede{{font-size:17px}} .meta{{font-size:13px;color:var(--pg-ink3)}}
code{{font-family:"JetBrains Mono","SF Mono",ui-monospace,Menlo,Consolas,monospace;font-size:.88em}}
.duo{{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;margin:14px 0 6px}}
.fig{{min-width:0;max-width:100%}} .fig figcaption,.cap{{font-size:13px;color:var(--pg-ink3);margin-top:8px}}
figure{{margin:0}}
/* specimens: each carries the prototype's own tokens, so it shows one theme whatever the viewer's theme is */
.sp{{background:var(--bg);padding:16px;border-radius:12px;border:1px solid var(--pg-line);max-width:100%;font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,"Inter","Segoe UI",Roboto,sans-serif;font-size:15px;line-height:1.45;color:var(--ink)}}
.sp-light{{{LIGHT}}} .sp-dark{{{DARK}}}
.sp .slot{{width:var(--w);max-width:100%}}
@media (max-width:430px){{.sp{{margin-inline:-16px;max-width:none;border-radius:0;border-inline:0}} .fig{{width:100%}}}}
.sp h2{{max-width:none}}
/* ---- the card: these rules are copied verbatim from the prototype stylesheet ---- */
.sp {card_css.replace(chr(10),chr(10)+'.sp ')}
.sp .row .n small{{font-size:.6em;font-weight:500;color:var(--ink3);letter-spacing:0;margin-left:1px}}
.tw{{overflow-x:auto;margin:12px 0}} table{{border-collapse:collapse;font-size:14.5px;min-width:34rem;width:100%}}
th,td{{text-align:left;vertical-align:top;padding:9px 12px 9px 0;border-top:1px solid var(--pg-line);color:var(--pg-ink2)}} thead th{{border-top:0;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--pg-ink3);font-weight:600}}
tbody th{{color:var(--pg-ink);font-weight:600;white-space:nowrap;width:9rem}}
.ctx{{display:block;max-width:100%;height:auto;border:1px solid var(--pg-line);border-radius:12px}}
.sm{{font-size:12.5px;color:var(--pg-ink3)}}
.chip{{display:inline-block;width:14px;height:14px;border-radius:4px;border:1px solid var(--pg-line);vertical-align:-2px;margin-right:7px}}
.cols{{display:grid;grid-template-columns:repeat(auto-fit,minmax(17rem,1fr));gap:20px 28px;margin-top:8px}} .cols>div{{min-width:0}}
.note{{border-left:3px solid var(--pg-acc);padding:2px 0 2px 14px;margin:14px 0}}
pre{{background:var(--pg-soft);border:1px solid var(--pg-line);border-radius:10px;padding:14px;overflow-x:auto;font-size:13px;line-height:1.5;margin:10px 0}}
</style>
<div class="doc">
<header>
<h1>Round-up Card Reference</h1>
<p class="lede">The exact design of the round-up card from Comparison Feed Two, for the first slice: NFL division front-runners. A build is faithful when it matches this page.</p>
<p class="meta">Fable for Alex · Tue Oct 6, 2026 · Card rules copied from the prototype page source, unchanged. Measurements taken from a rendered card 358 wide. All sizes in CSS pixels. On a screen narrower than 390 the examples shrink to fit.</p>
</header>

<h2>Rulings so far</h2>
<p>Alex ruled these on Oct 6. They override the prototype where the two differ.</p>
<ul>{li(RULINGS)}</ul>
<p>Settled without a ruling, after the coordinator's review of the product's design system:</p>
<ul>{li(SETTLED)}</ul>

<h2>The card</h2>
<p>Four contests, one row each. Every row is the current leader of its own division, so the rows are not rivals and do not add to 100.</p>
<div class="duo">
<figure class="fig">{spec('canonical','light')}<figcaption>Light. 358 wide, 330 tall.</figcaption></figure>
<figure class="fig">{spec('canonical','dark')}<figcaption>Dark, kept on file. The product is light only today, so this is not part of the check.</figcaption></figure>
</div>
<p class="cap">Example numbers are venue prices from Oct 6, 2:41pm PT. They are fixture data for comparing builds, not current values.</p>

<h2>States the build must handle</h2>
<div class="duo">
<figure class="fig">{spec('three','light')}<figcaption>Three rows, the minimum. 280 tall.</figcaption></figure>
<figure class="fig">{spec('long','light')}<figcaption>Long headline and long labels. The headline steps down to 19px; labels wrap and are never cut off.</figcaption></figure>
</div>
<div class="duo">
<figure class="fig">{spec('extremes','dark')}<figcaption>High and low values, and no tag. The kicker stands alone on the header line.</figcaption></figure>
<figure class="fig">{spec('canonical','light',340)}<figcaption>A narrower column, 340 wide. Only the label column and bar get narrower.</figcaption></figure>
</div>

<h2>Measurements</h2>
<div class="tw"><table><thead><tr><th>Part</th><th>Specification</th></tr></thead><tbody>{measrows}</tbody></table></div>
<p>At 358 wide the canonical card is 330 tall: content starts 19 from the top edge, each row is 36 tall with 14 between rows, and the footer rule sits 14 below the last bar.</p>
<p>Type: the system sans-serif stack for text and a monospaced stack for numbers (<code>JetBrains Mono</code>, then <code>SF Mono</code>, then the system monospace). Faces differ by platform, so compare layout and weight, not letter shapes.</p>

<h2>Colors</h2>
<div class="tw"><table><thead><tr><th>Prototype name</th><th>Used for</th><th>Value</th><th>Product color</th><th>Dark, on file</th></tr></thead><tbody>{tokrows}</tbody></table></div>
<p>Text is always one of the three inks. No text takes the bar color. Product colors were read from <code>frontend/app/globals.css</code> in the main checkout on Oct 6 and should be confirmed against the release branch.</p>

<h2>What the build may change, and what it may not</h2>
<div class="cols">
<div><h3>Must change from the prototype</h3>
<ul>{li(MUST)}</ul></div>
<div><h3>May adapt</h3>
<ul>{li(MAY)}</ul></div>
<div><h3>May not change without Alex</h3>
<ul>{''.join('<li>'+x+'</li>' for x in MAYNOT)}</ul></div>
</div>

<h2>The footer line in the product</h2>
<p>The coordinator's proposed rule shows the four divisions with the lowest leader probability, out of the divisions that have a blended number, and says the card must disclose that. The footer is the place for it. It uses the footer style above, unchanged, on one line.</p>
<div class="duo">
<figure class="fig">{spec('canonical','light',358,'Bain Luck blend · the 4 closest of 8 divisions','footer')}<figcaption>When all eight divisions qualify.</figcaption></figure>
<figure class="fig">{spec('three','light',358,'Bain Luck blend · 3 of 8 divisions','footer3')}<figcaption>When a division drops out and only three qualify. Below three, no card is shown and the feed is unchanged.</figcaption></figure>
</div>
<p>The headline stays "NFL division front-runners". It does not say "tightest", so it remains true when some divisions cannot be evaluated.</p>
<h3>When the numbers are old</h3>
<p>The existing grouped card has no freshness note of its own. This card needs one. When the product's own age rule says a number is old, the footer adds the product's usual wording after the coverage line and may run to a second line. Nothing else moves.</p>
<div class="duo">
<figure class="fig">{spec('canonical','light',358,'Bain Luck blend · the 4 closest of 8 divisions · last number 2 hours ago','stale')}<figcaption>Old numbers. The footer wraps to two lines and the card grows by one footer line.</figcaption></figure>
</div>
<h3>Loading and errors</h3>
<p>These come from the feed, not the card: the existing loading placeholders, the existing "feed unavailable" notice, and the last good cards kept on screen with a retry note. The card adds nothing of its own.</p>

<h2>Buttons and Details in the prototype</h2>
<p>These images show what sat around the card in Comparison Feed Two. They are here so the build knows what it is replacing. The card ends at its border; the buttons sit 10 below it.</p>
<div class="duo">
<figure class="fig"><img class="ctx" src="{CTX['acts']}" width="{CTX['acts_size'][0]}" height="{CTX['acts_size'][1]}" alt="The prototype card with its four buttons underneath: Like, Share, Not for me and Details."><figcaption>The prototype's buttons. Test instruments. The product's existing card actions replace them.</figcaption></figure>
<figure class="fig"><img class="ctx" src="{CTX['details']}" width="{CTX['details_size'][0]}" height="{CTX['details_size'][1]}" alt="The prototype card with Details open, listing the full sentence and venue wording behind each row."><figcaption>Details open. It lists the exact claim behind each row. Not part of the first slice: tapping the card opens the container instead.</figcaption></figure>
</div>

<h2>Fixture data</h2>
<p>Use exactly this content when comparing a build with this page. The row label is the contest, a colon, then the leader's short name.</p>
<pre>{html.escape(json.dumps([dict(id=c['cid'],headline=c['headline'],tag=c['tag'],rows=[dict(label=r['text'],percent=int(r['num'])) for r in c['rows']]) for c in EX],indent=1))}</pre>

<h2>How a build is checked</h2>
<ol>
<li>Render the built card with the fixture data above, in light, at card widths 340, 358 and 448, and in windows of 390 by 800 and 950 by 1028.</li>
<li>Place each image beside the matching reference image from this bundle.</li>
<li>Fable lists every difference in position, size, weight, color and wrapping. Positions should agree to within 1 pixel. Letter shapes may differ by platform.</li>
<li>Each difference is either fixed or accepted by Alex by name. The card is called faithful only after that.</li>
</ol>
<p>Passing component tests does not replace this comparison.</p>
</div>
'''
open('roundup-card-reference.html','w').write(page)
open('roundup-card-reference-standalone.html','w').write('<!doctype html><html lang="en"><head><meta charset="utf8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>'+page+'</body></html>')
print(len(page)); print(card_css)

fixture=[dict(id=c['cid'],headline=c['headline'],tag=c['tag'],rows=[dict(label=r['text'],percent=int(r['num'])) for r in c['rows']]) for c in EX]
json.dump(fixture,open('roundup-card-fixture.json','w'),indent=1)
md=["# NFL division round-up card: design reference","","PILLARS: FORMATTING, DISCOVER. Prepared by Fable for Alex, Tue 2026-10-06, 9:15pm PT; revised 9:35pm PT after the coordinator's reply (delivery path, window sizes, selection rule) and Alex's ruling on bar color. For the first comparison slice Alex approved on 10/6: \"NFL division front-runners\" (#4463, #10354, #10357). A reference for the build, not a ruling and not an assignment.","","The rendered reference is `fable-nfl-division-roundup-design-20261006/roundup-card-reference-standalone.html`, and https://claude.ai/artifact/ARTIFACT_URL for Alex. The card rules in it are copied verbatim from the Comparison Feed Two page source (`roundup-card.css`). A check of every element's position and style found no difference between the reference and the prototype (`verify_geom_output.txt`).","","## Measurements","","All sizes in CSS pixels, from a rendered card 358 wide.","","| Part | Specification |","|---|---|"]
md+=[f"| {a} | {b} |" for a,b in MEAS]
md+=["","At 358 wide the canonical four-row card is 330 tall and the three-row card is 280 tall. Content starts 19 from the top edge, each row is 36 tall with 14 between rows, and the footer rule sits 14 below the last bar.","","Type: the system sans-serif stack for text and a monospaced stack for numbers (JetBrains Mono, then SF Mono, then the system monospace). Faces differ by platform, so compare layout and weight, not letter shapes. The reference images were rendered in Chromium on Linux.","","## Colors","","| Token | Used for | Light | Dark |","|---|---|---|---|"]
md+=[f"| `{n}` | {u} | `{l}` | `{d}` |" for n,u,l,d in TOK]
md+=["","Text is always one of the three inks. No text takes the bar color.","","## What the build may change, and what it may not","","**Must change from the prototype**","","- The number is the Bain Luck blend. The prototype showed venue prices.","- The footer line. \"Venue prices: Kalshi\" belongs to the prototype. The product's own source or freshness line goes here, in the same style.","- The buttons under the card. Like, Share, Not for me and Details were test instruments. The product's existing card actions apply.","- A row opens its question page. The whole row is the target, at least 44 tall including the space around it.","","**May adapt**","","- Card width, to fit the product's column. The card is fluid; it was checked from 340 to 448.","- Font faces, to the platform's system faces, keeping sizes and weights.","- The tag text, to the product's own league or topic name.","","**May not change without Alex**","","- Type sizes, weights, spacing, corner radius or bar height.","- The order of parts: header line, headline, rows, footer.","- Row order: highest probability first.","- Whole-number percentages with the small percent sign.","- No icons, logos, images, colored text or motion on the bars.","- No ellipsis. Labels wrap.","","**Ruled by Alex on Oct 6: the bars stay blue.** On the live site that day, Discover lists drew the leader's bar green and used green for \"Won\". Here every row is a leader and none has won, so green keeps one meaning.","","## The footer line in the product","","The coordinator's proposed rule shows the four divisions with the lowest leader probability, out of the divisions that have a blended number, and requires the card to disclose coverage and ordering. The footer carries it, in the footer style above, on one line. Proposed wording, not yet ruled by Alex:","","- All eight qualify: `Bain Luck blend · the 4 closest of 8 divisions`","- Only three qualify: `Bain Luck blend · 3 of 8 divisions`","- Fewer than three: no card.","","Both fit on one line at 340 wide and leave the card height unchanged. The headline stays \"NFL division front-runners\" and does not say \"tightest\".","","## Buttons and Details in the prototype","","`context-images/` shows the card inside the prototype page at 390 by 800 and 950 by 1028, light and dark, with and without Details open. The four buttons (Like, Share, Not for me, Details) sat 10 below the card and were test instruments; the product's existing card actions replace them. Details listed the exact claim behind each row. It is not part of the first slice: each row opens its question page instead.","","## Fixture data","","`roundup-card-fixture.json` holds four cases: canonical (four rows), three (the minimum), long (long headline and labels), extremes (97% and 8%, no tag). The numbers are venue prices from Oct 6, 2:41pm PT, kept as fixed test content. The long and extremes cases are layout tests, not proposed cards.","","## How a build is checked","","1. Render the built card with the fixture data, in light and dark, at card widths 340, 358 and 448, and in windows of 390 by 800 and 950 by 1028.","2. Place each image beside the matching reference image in `reference-images/` (named `proto_<case>_<theme>_<width>.png`, 2x).","3. Fable lists every difference in position, size, weight, color and wrapping. Positions should agree to within 1 pixel. Letter shapes may differ by platform.","4. Each difference is either fixed or accepted by Alex by name. The card is called faithful only after that.","","Passing component tests does not replace this comparison.","","## Not covered","","- The selection rule itself. The coordinator proposed it on Oct 6 (#10354): the four lowest leader probabilities among qualifying divisions, three if only three qualify, no card below three. This reference covers the three- and four-row states that rule produces.","- The destination page a row opens. The coordinator proposes a separate web division page showing the same blended number. No design exists for it here.","- The iPhone app. This reference is for the web card.","- Loading, error and stale states. The prototype had none; the product's existing card states apply and should be shown to Alex before the build is called done.","","## Files","","In `fable-nfl-division-roundup-design-20261006/`: `roundup-card-reference-standalone.html`, `roundup-card.css`, `roundup-card-fixture.json`, `reference-images/` (24 card images), `context-images/` (8 page images), `context.html`, `context_card.json`, `measure.json`, `proto_render.html`, `build_ref.py`, `measure.py`, `verify_geom.py`, `context_shots.py`, `verify_geom_output.txt`, `MANIFEST.json`."]
open('FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261006.md','w').write('\n'.join(md)+'\n')

# ---------- revision 3 of the companion spec: rulings, color mapping, states
t=open('FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261006.md').read()
def cut(text,a,b,new):
    i=text.index(a); j=text.index(b,i); return text[:i]+new+text[j:]
t=t.replace("revised 9:35pm PT after the coordinator's reply (delivery path, window sizes, selection rule) and Alex's ruling on bar color.","revised 9:35pm and 10:00pm PT after the coordinator's replies and Alex's rulings.")
rul="## Rulings so far\n\nAlex ruled these on Oct 6. They override the prototype where the two differ.\n\n"+"\n".join(f"- **{x}** {y}" for x,y in RULINGS)+"\n\nSettled without a ruling, after the coordinator's review of the product's design system:\n\n"+"\n".join(f"- **{x}** {y}" for x,y in SETTLED)+"\n\n"
t=t.replace("## Measurements",rul+"## Measurements",1)
col="## Colors\n\n| Prototype name | Used for | Value | Product color | Dark, on file |\n|---|---|---|---|---|\n"+"\n".join(f"| `{n}` | {u} | `{l}` | `{PROD[n][0]}` ({PROD[n][1]}) | `{d}` |" for n,u,l,d in TOK)+"\n\nText is always one of the three inks. No text takes the bar color. Product colors were read from `frontend/app/globals.css` in the main checkout on Oct 6 and should be confirmed against the release branch.\n\n"
t=cut(t,"## Colors","## What the build may change",col)
body="## What the build may change, and what it may not\n\n**Must change from the prototype**\n\n"+"\n".join(f"- {x} {y}" for x,y in MUST)+"\n\n**May adapt**\n\n"+"\n".join(f"- {x}, {y}" for x,y in MAY)+"\n\n**May not change without Alex**\n\n"+"\n".join(f"- {x}" for x in MAYNOT)+"""

## The footer line in the product

The selection rule shows the four divisions with the lowest leader probability, out of the divisions that have a blended number, and the card must disclose coverage and ordering. The footer carries it, in the footer style above. Wording accepted by Alex for now:

- All eight qualify: `Bain Luck blend · the 4 closest of 8 divisions`
- A division drops out and only three qualify: `Bain Luck blend · 3 of 8 divisions`, with three rows.
- Fewer than three: no card, and the feed is unchanged.

Both fit on one line at 340 wide and leave the card height unchanged. The headline stays "NFL division front-runners" and does not say "tightest".

**When the numbers are old.** The existing grouped card has no freshness note of its own. This card needs one. When the product's own age rule says a number is old, the footer adds the product's usual wording after the coverage line, for example `Bain Luck blend · the 4 closest of 8 divisions · last number 2 hours ago`. It may run to a second line; the card grows by one footer line and nothing else moves.

**Loading and errors** come from the feed, not the card: the existing loading placeholders, the existing feed-unavailable notice, and the last good cards kept on screen with a retry note.

## Buttons and Details in the prototype

`context-images/` shows the card inside the prototype page at 390 by 800 and 950 by 1028, with and without Details open. The four buttons (Like, Share, Not for me, Details) sat 10 below the card and were test instruments; the product's existing card actions replace them, with their own icons. Details listed the exact claim behind each row. It is not part of the first slice: tapping the card opens the container instead.

"""
t=cut(t,"## What the build may change","## Fixture data",body)
t=t.replace("1. Render the built card with the fixture data, in light and dark, at card widths 340, 358 and 448, and in windows of 390 by 800 and 950 by 1028.","1. Render the built card with the fixture data, in light, at card widths 340, 358 and 448, and in windows of 390 by 800 and 950 by 1028.")
t=t.replace("- The destination page a row opens. The coordinator proposes a separate web division page showing the same blended number. No design exists for it here.","- The container a tap opens. Alex ruled that tapping the card opens a container showing an event card for each item. Its contents and layout are not designed here.")
t=t.replace("- Loading, error and stale states. The prototype had none; the product's existing card states apply and should be shown to Alex before the build is called done.","- The age rule that decides when numbers count as old. The product's existing rule applies.")
t=t.replace("https://claude.ai/artifact/ARTIFACT_URL","https://claude.ai/artifact/5YKssYU8GQWaRsZ7ttpDCS")
assert "Rulings so far" in t and "--surface-elevated" in t and "tapping the card opens the container" in t and "a row opens" not in t.lower()
open('FABLE-NFL-DIVISION-ROUNDUP-DESIGN-20261006.md','w').write(t)
