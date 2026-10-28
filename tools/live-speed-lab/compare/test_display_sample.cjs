const assert = require('node:assert/strict');
const {before, after, beforeEach, test} = require('node:test');
const {chromium} = require('playwright');
const {readDisplayIdentity10090} = require('./display_sample.cjs');

let browser, page;
const markup = `<div id="container">
  <span data-testid="event-hero-probability" data-probability="0.72"
    data-display-basis="preview" data-display-state="v3:1:slot:session:e2.s3:fold:1=4"
    data-display-received="123.456" data-display-observed-at="2026-10-28T06:00:00Z">72%</span>
  <section data-testid="win-probability-card"><div data-chart-endpoint-at="2026-10-28T06:00:00Z"
    data-chart-endpoint-basis="history" data-chart-endpoint-state="fold:1=2"
    data-chart-history="rev=fold:1=2;through=2026-10-28T06:00:00Z">chart</div></section>
</div>`;
before(async () => {
  browser = await chromium.launch({headless: true, channel: 'chrome'});
  page = await browser.newPage({viewport: {width: 390, height: 844}});
  await page.route('**/*', route => route.abort());
});
after(async () => { if (browser) await browser.close(); });
beforeEach(async () => { await page.setContent(markup); });

test('records different headline/chart identities without changing the page', async () => {
  const before = await page.content();
  const sample = await page.evaluate(readDisplayIdentity10090);
  assert.equal(sample.headline.attributes['data-display-state'], 'v3:1:slot:session:e2.s3:fold:1=4');
  assert.equal(sample.chart.attributes['data-chart-endpoint-state'], 'fold:1=2');
  assert.equal(sample.headline.visible, true);
  assert.equal(sample.chart.inViewport, true);
  assert.ok(sample.ended_mono >= sample.started_mono);
  assert.equal(await page.content(), before);
});

test('equal rounded values still retain distinct state identities', async () => {
  const a = await page.evaluate(readDisplayIdentity10090);
  await page.locator('[data-display-state]').evaluate(n => n.setAttribute('data-display-state', 'v3:1:slot:session:e2.s4:fold:1=4'));
  const b = await page.evaluate(readDisplayIdentity10090);
  assert.notEqual(a.headline.attributes['data-display-state'], b.headline.attributes['data-display-state']);
  assert.equal(await page.locator('[data-display-state]').innerText(), '72%');
});

test('unavailable never borrows the headline identity for the chart', async () => {
  await page.locator('[data-chart-endpoint-state]').evaluate(n => {
    n.setAttribute('data-chart-endpoint-state', '');
    n.setAttribute('data-chart-endpoint-basis', 'unavailable');
  });
  const sample = await page.evaluate(readDisplayIdentity10090);
  assert.equal(sample.chart.attributes['data-chart-endpoint-state'], '');
  assert.equal(sample.chart.attributes['data-chart-endpoint-basis'], 'unavailable');
  assert.notEqual(sample.headline.attributes['data-display-state'], '');
});

test('missing attributes and missing surfaces are not coverage', async () => {
  await page.locator('[data-display-state]').evaluate(n => n.removeAttribute('data-display-state'));
  await page.locator('[data-testid="win-probability-card"]').evaluate(n => n.remove());
  const sample = await page.evaluate(readDisplayIdentity10090);
  assert.equal(sample.headline.status, 'unsupported');
  assert.equal(sample.headline.attributes['data-display-state'], null);
  assert.equal(sample.chart.status, 'missing');
});

test('duplicate surfaces are ambiguous, not the first matching element', async () => {
  await page.locator('#container').evaluate(n => n.after(n.cloneNode(true)));
  const sample = await page.evaluate(readDisplayIdentity10090);
  for (const surface of [sample.headline, sample.chart]) {
    assert.equal(surface.status, 'ambiguous');
    assert.equal(surface.attributes, null);
  }
});

test('ancestor hiding and offscreen geometry are recorded separately', async () => {
  await page.locator('#container').evaluate(n => n.style.transform = 'translateY(2000px)');
  let sample = await page.evaluate(readDisplayIdentity10090);
  assert.equal(sample.headline.visible, true);
  assert.equal(sample.headline.inViewport, false);
  await page.locator('#container').evaluate(n => n.hidden = true);
  sample = await page.evaluate(readDisplayIdentity10090);
  assert.equal(sample.headline.visible, false);
  assert.equal(sample.chart.visible, false);
});
