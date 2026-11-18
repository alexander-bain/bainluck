const test = require("node:test");
const assert = require("node:assert/strict");
const { decide, run } = require("../preflight.cjs");

const now = Date.parse("2026-11-18T01:30:00Z");
const previous = {
  generated_at: new Date(now).toISOString(),
  changes: [{ number: 12903, merged_at: null }],
};

test("three-minute boundary is exact", () => {
  assert.equal(decide(previous, [12903], now + 179999).refresh, false);
  assert.equal(decide(previous, [12903], now + 180000).refresh, true);
});
test("opened, merged, and closed changes bypass the recent-copy gate", () => {
  assert.equal(decide(previous, [12903, 12904], now).refresh, true);
  assert.equal(decide(previous, [], now).refresh, true);
  assert.equal(decide(null, [12903], now).refresh, true);
});
test("a future timestamp does not suppress updates", () => {
  assert.equal(decide(previous, [12903], now - 1).refresh, true);
});
test("the cheap gate makes only read requests and reports calls and remaining budget", async () => {
  const urls = [];
  const messages = [];
  const log = console.log;
  console.log = (value) => messages.push(value);
  try {
    await run({
      token: "fixture",
      fetcher: async (url, options) => {
        urls.push(url);
        if (url.includes("api.github.com")) {
          assert.equal(options.method, "POST");
          assert.match(JSON.parse(options.body).query, /^query/);
        } else assert.equal(options.method, undefined);
        const value = url.includes("api.github.com")
          ? {
              data: {
                rateLimit: { remaining: 999 },
                repository: {
                  pullRequests: {
                    nodes: [{ number: 12903 }],
                    pageInfo: { hasNextPage: false },
                  },
                },
              },
            }
          : { ...previous, generated_at: new Date().toISOString() };
        return { ok: true, json: async () => value };
      },
    });
  } finally {
    console.log = log;
  }
  assert.equal(urls.length, 2);
  const metrics = JSON.parse(
    messages.find((value) => value.startsWith("FACTORY_METRICS ")).slice(16),
  );
  assert.equal(metrics.github_api_calls, 1);
  assert.equal(metrics.public_reads, 1);
  assert.equal(metrics.rate_limit_remaining, 999);
});
