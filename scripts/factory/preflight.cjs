const fs = require("node:fs");
const DATA_URL =
  "https://github.com/alexander-bain/bainluck/releases/download/factory-data/factory.json";

function decide(previous, openNumbers, now = Date.now()) {
  if (!previous || !Number.isFinite(Date.parse(previous.generated_at))) {
    return { refresh: true, reason: "first observation" };
  }
  const before = new Set(
    previous.changes
      .filter((change) => !change.merged_at)
      .map((change) => change.number),
  );
  const after = new Set(openNumbers);
  const opened = [...after].filter((number) => !before.has(number));
  const closed = [...before].filter((number) => !after.has(number));
  if (opened.length || closed.length) {
    return {
      refresh: true,
      reason: "change opened, merged or closed",
      opened,
      closed,
    };
  }
  const age = now - Date.parse(previous.generated_at);
  return {
    refresh: age < 0 || age >= 180_000,
    reason:
      age >= 0 && age < 180_000
        ? "published copy is under three minutes old"
        : "refresh due",
  };
}

async function run({
  token = process.env.GITHUB_TOKEN,
  fetcher = fetch,
  output = process.env.GITHUB_OUTPUT,
} = {}) {
  let calls = 0;
  let publicReads = 0;
  let remaining = null;
  const request = async (cursor) => {
    calls += 1;
    const response = await fetcher("https://api.github.com/graphql", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query:
          'query($cursor:String) { rateLimit { remaining } repository(owner:"alexander-bain",name:"bainluck") { pullRequests(states:OPEN,first:100,after:$cursor) { nodes { number } pageInfo { hasNextPage endCursor } } } }',
        variables: { cursor },
      }),
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) throw new Error(`GitHub HTTP ${response.status}`);
    const result = await response.json();
    if (result.errors)
      throw new Error("GitHub could not read the open changes");
    remaining = result.data.rateLimit.remaining;
    return result.data.repository.pullRequests;
  };
  try {
    publicReads += 1;
    const response = await fetcher(DATA_URL, {
      signal: AbortSignal.timeout(8000),
      cache: "no-store",
    });
    if (!response.ok && response.status !== 404)
      throw new Error(`Snapshot HTTP ${response.status}`);
    const previous = response.ok ? await response.json() : null;
    const numbers = [];
    let cursor = null;
    while (true) {
      const pulls = await request(cursor);
      numbers.push(...pulls.nodes.map((pull) => pull.number));
      if (!pulls.pageInfo.hasNextPage) break;
      cursor = pulls.pageInfo.endCursor;
    }
    const decision = decide(previous, numbers);
    if (output) fs.appendFileSync(output, `refresh=${decision.refresh}\n`);
    console.log(JSON.stringify({ phase: "preflight", ...decision }));
    return decision;
  } finally {
    console.log(
      `FACTORY_METRICS ${JSON.stringify({ phase: "preflight", github_api_calls: calls, public_reads: publicReads, rate_limit_resource: "graphql", rate_limit_remaining: remaining })}`,
    );
  }
}

module.exports = { decide, run };
if (require.main === module)
  run().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
