"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

// #11155: execute the actual inline program with deterministic API/time
// specimens. No network, real waiting, production hook or new dependency.
const ROOT = path.resolve(__dirname, "../../..");
const workflow = fs.readFileSync(path.join(ROOT, ".github/workflows/codeql.yml"), "utf8");
const WAIT = "Wait for parent master CodeQL baseline";
const QUALIFY = "Qualify compose security or record master baseline";
const PUBLISH = "Publish CodeQL security receipt";
const BASE = "a".repeat(40);
const REPOSITORY = "example/controlled";

function step(name) {
  const header = `      - name: ${name}\n`;
  const start = workflow.indexOf(header);
  assert.notEqual(start, -1, `missing ${name}`);
  assert.equal(workflow.indexOf(header, start + header.length), -1, `duplicate ${name}`);
  const end = workflow.indexOf("\n      - name:", start + header.length);
  return workflow.slice(start, end === -1 ? workflow.length : end + 1);
}

const waitStep = step(WAIT);
const inline = waitStep.slice(waitStep.indexOf("        run: |\n") + "        run: |\n".length)
  .split("\n").map(line => line.startsWith("          ") ? line.slice(10) : line).join("\n");

function run(fields = {}) {
  return {
    id: 42, run_attempt: 1, path: ".github/workflows/codeql.yml",
    head_sha: BASE, head_branch: "master", event: "push",
    repository: { id: 7, full_name: REPOSITORY }, head_repository: { id: 7 },
    status: "in_progress", conclusion: null, ...fields,
  };
}
function listing(rows = [run()], total = rows.length) {
  return { total_count: total, workflow_runs: rows };
}
function response(payload, duration = 0) { return { payload, duration }; }
const completed = (conclusion = "success") => run({ status: "completed", conclusion });

const harness = `
import contextlib, io, json, subprocess, sys, time, types
spec = json.load(sys.stdin)
state = {"now": 0, "calls": [], "sleeps": []}
responses = spec["responses"]
def request(args, **kwargs):
    index = len(state["calls"])
    item = responses[min(index, len(responses) - 1)]
    timeout = kwargs.get("timeout")
    state["calls"].append({"args": args, "timeout": timeout, "at": state["now"]})
    duration = item.get("duration", 0)
    if timeout is not None and duration > timeout:
        state["now"] += timeout
        raise subprocess.TimeoutExpired(args, timeout)
    state["now"] += duration
    if item.get("error"):
        raise subprocess.CalledProcessError(1, args, stderr="DO-NOT-PRINT-API-SECRET")
    return types.SimpleNamespace(stdout=item.get("raw", json.dumps(item.get("payload"))), returncode=0)
def sleep(seconds):
    state["sleeps"].append({"at": state["now"], "seconds": seconds})
    state["now"] += seconds
subprocess.run = request
time.monotonic = lambda: state["now"]
time.sleep = sleep
output = io.StringIO()
with contextlib.redirect_stdout(output):
    exec(compile(spec["program"], "codeql-inline-wait", "exec"), {})
state["log"] = output.getvalue()
print(json.dumps(state))
`;

function simulate(options = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "codeql-11155-"));
  const protectedFiles = {
    "codeql-provenance.json": options.provenance ?? JSON.stringify({ base: BASE }),
    "codeql-security.json": "unchanged-security-receipt\n",
    "github-env": "unchanged-env\n", "github-output": "unchanged-output\n",
  };
  try {
    for (const [file, content] of Object.entries(protectedFiles)) {
      fs.writeFileSync(path.join(directory, file), content);
    }
    const child = spawnSync("python3", ["-c", harness], {
      cwd: directory, timeout: 5000, maxBuffer: 2_000_000, encoding: "utf8",
      env: { ...process.env, GITHUB_EVENT_NAME: "push",
        GITHUB_REF: "refs/heads/integrator/compose-controlled",
        GITHUB_REPOSITORY: REPOSITORY, GITHUB_REPOSITORY_ID: "7",
        GITHUB_ENV: path.join(directory, "github-env"),
        GITHUB_OUTPUT: path.join(directory, "github-output"), ...options.env },
      input: JSON.stringify({ program: options.program ?? inline,
        responses: options.responses ?? [response(listing()), response(completed())] }),
    });
    assert.equal(child.error, undefined, "wait did not finish within the test harness bound");
    assert.equal(child.status, 0, child.stderr);
    for (const [file, content] of Object.entries(protectedFiles)) {
      assert.equal(fs.readFileSync(path.join(directory, file), "utf8"), content,
        `qualifier input changed: ${file}`);
    }
    const result = JSON.parse(child.stdout);
    assert.doesNotMatch(result.log, /DO-NOT-PRINT-API-SECRET/);
    assert.match(result.log, /qualifier decides/);
    return result;
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
}

function assertBounded(result) {
  assert.ok(result.now <= 720, `elapsed deadline exceeded: ${result.now}`);
  for (const call of result.calls) {
    assert.ok(call.timeout > 0 && call.timeout <= 20);
    assert.ok(call.at + call.timeout <= 720, "request ignores remaining deadline");
    assert.equal(call.args[0], "gh");
    assert.equal(call.args[1], "api");
  }
  for (const sleep of result.sleeps) {
    assert.ok(sleep.seconds > 0 && sleep.seconds <= 20);
    assert.ok(sleep.at + sleep.seconds <= 720);
  }
}

describe("#11155 compose parent-baseline readiness", () => {
  it("is one compose-PUSH-only Python step between analysis and unchanged qualification", () => {
    assert.match(waitStep, /^        if: github.event_name == 'push' && startsWith\(github.ref, 'refs\/heads\/integrator\/compose-'\)\n/m);
    assert.match(waitStep, /^        shell: python$/m);
    assert.ok(workflow.indexOf(`      - name: Perform CodeQL Analysis\n`) < workflow.indexOf(`      - name: ${WAIT}\n`));
    assert.ok(workflow.indexOf(`      - name: ${WAIT}\n`) < workflow.indexOf(`      - name: ${QUALIFY}\n`));
    const cap = Number(inline.match(/^CAP_SECONDS = (\d+)$/m)?.[1]);
    assert.ok(cap > 0 && cap <= 900);
    assert.equal(cap, 720);
    assert.equal(crypto.createHash("sha256").update(step(QUALIFY)).digest("hex"),
      "dc636f039d6ebf30a353afe88b6bb0b08002f0509b5d2486f2fc816293c525f2");
    assert.equal(crypto.createHash("sha256").update(step(PUBLISH)).digest("hex"),
      "cc44180facb352795066b409f76596a851f4368d92734361c2767174fd730efe");
    assert.doesNotMatch(waitStep, /GITHUB_ENV|GITHUB_OUTPUT|continue-on-error|\.write\(/);
  });

  it("waits only on pending status, reads the exact current run, then hands off without accepting evidence", () => {
    const result = simulate({ responses: [response(listing()), response(run()), response(completed())] });
    assertBounded(result);
    assert.equal(result.now, 20);
    assert.equal(result.calls.length, 3);
    assert.equal(result.calls[0].args[2], `repos/${REPOSITORY}/actions/workflows/codeql.yml/runs?head_sha=${BASE}&event=push&branch=master&per_page=100`);
    assert.ok(result.calls.slice(1).every(c => c.args[2] === `repos/${REPOSITORY}/actions/runs/42`));
    assert.match(result.log, /parent run completed/);
  });

  for (const conclusion of ["success", "failure", "cancelled", "timed_out", null]) {
    it(`immediately hands a completed/${conclusion} run to the unchanged qualifier`, () => {
      const result = simulate({ responses: [response(listing()), response(completed(conclusion))] });
      assert.equal(result.now, 0);
      assert.equal(result.calls.length, 2);
      assert.equal(result.sleeps.length, 0);
      assert.match(result.log, /parent run completed/);
    });
  }

  it("does not confuse attempts of the same run ID with ambiguity", () => {
    const result = simulate({ responses: [response(listing([run(), run({ run_attempt: 2 })])),
      response(run({ run_attempt: 3 })), response(completed())] });
    assert.equal(result.calls.length, 3);
    assert.match(result.log, /parent run completed/);
  });

  const badListings = [listing([]), listing([run(), run({ id: 43 })]), listing([run()], 101),
    { workflow_runs: [run()] }, { total_count: 1, workflow_runs: null }];
  for (const [index, payload] of badListings.entries()) {
    it(`ends missing/ambiguous/incomplete listing ${index} promptly and grants nothing`, () => {
      const result = simulate({ responses: [response(payload)] });
      assert.equal(result.calls.length, 1);
      assert.equal(result.sleeps.length, 0);
      assert.match(result.log, /missing, ambiguous or invalid/);
    });
  }

  for (const fields of [{ head_sha: "b".repeat(40) }, { head_branch: "feature" },
    { event: "pull_request" }, { path: ".github/workflows/other.yml" },
    { repository: { id: 8, full_name: REPOSITORY } }, { head_repository: { id: 8 } }]) {
    it(`does not poll a foreign listing: ${JSON.stringify(fields)}`, () => {
      const result = simulate({ responses: [response(listing([run(fields)]))] });
      assert.equal(result.calls.length, 1);
      assert.equal(result.sleeps.length, 0);
    });
  }

  it("ends current-run identity movement without following another run", () => {
    const result = simulate({ responses: [response(listing()), response(run({ id: 43 }))] });
    assert.equal(result.calls.length, 2);
    assert.equal(result.sleeps.length, 0);
    assert.match(result.log, /identity changed/);
  });

  for (const fields of [{ status: "unknown" }, { conclusion: "failure" }]) {
    it(`ends unexpected nonterminal state ${JSON.stringify(fields)}`, () => {
      const result = simulate({ responses: [response(listing()), response(run(fields))] });
      assert.equal(result.calls.length, 2);
      assert.equal(result.sleeps.length, 0);
      assert.match(result.log, /unexpected run state/);
    });
  }

  for (const failed of [{ error: true }, { raw: "not JSON" }, { raw: "x".repeat(1_000_001) }]) {
    it(`returns API failure/malformed/oversize evidence to qualification without retry`, () => {
      const result = simulate({ responses: [failed] });
      assert.equal(result.calls.length, 1);
      assert.equal(result.sleeps.length, 0);
      assert.match(result.log, /unavailable evidence/);
    });
  }

  for (const provenance of ["not JSON", "{}", JSON.stringify({ base: "not-a-sha" })]) {
    it(`does not request evidence for invalid provenance ${provenance}`, () => {
      const result = simulate({ provenance });
      assert.equal(result.calls.length, 0);
    });
  }

  for (const env of [{ GITHUB_REF: "refs/heads/master" }, { GITHUB_EVENT_NAME: "pull_request" },
    { GITHUB_EVENT_NAME: "schedule" }, { GITHUB_REF: "refs/heads/feature" }]) {
    it(`never polls outside a compose PUSH: ${JSON.stringify(env)}`, () => {
      const result = simulate({ env });
      assert.equal(result.calls.length, 0);
      assert.equal(result.sleeps.length, 0);
    });
  }

  it("stops on the first request timeout without a generic retry", () => {
    const result = simulate({ responses: [response(listing(), 21)] });
    assert.equal(result.calls.length, 1);
    assert.equal(result.now, 20);
    assert.match(result.log, /timeout/);
    assertBounded(result);
  });

  it("counts request time as well as sleep and clips the last request to remaining budget", () => {
    const result = simulate({ responses: [response(listing(), 5), response(run(), 15)] });
    assertBounded(result);
    assert.equal(result.now, 720);
    assert.equal(result.calls.at(-1).timeout, 15);
    assert.match(result.log, /timeout/);
  });

  it("also ends at the cap when requests are instant", () => {
    const result = simulate({ responses: [response(listing()), response(run())] });
    assertBounded(result);
    assert.equal(result.now, 720);
    assert.match(result.log, /deadline reached/);
    assert.ok(result.calls.every(c => c.at < 720));
  });

  it("the boundedness control kills a mutant that resets the request timeout", () => {
    const mutant = inline.replace("timeout=min(REQUEST_SECONDS, remaining)", "timeout=REQUEST_SECONDS");
    assert.notEqual(mutant, inline);
    assert.throws(() => assertBounded(simulate({ program: mutant,
      responses: [response(listing(), 5), response(run(), 15)] })), /elapsed deadline|remaining deadline/);
  });

  it("the input-preservation control kills a mutant that changes qualifier provenance", () => {
    assert.throws(() => simulate({ program: inline + '\nopen("codeql-provenance.json", "w").write("changed")\n' }),
      /qualifier input changed/);
  });
});
