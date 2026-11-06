'use strict';

// #11951: use the existing @claude command for the frozen CI-blocked cohort.
// These are advisory semantic reviews, never approvals or replacements for CI.
const MARKER = 'reviewer-eval-11951';
const REVIEW_MARKER = '[Reviewer eval #11951 — advisory]';

function parseRequest(context) {
  const body = context.payload?.comment?.body || '';
  if (!body.includes(`<!-- ${MARKER}`)) return null;
  const owner = context.repo.owner;
  const number = context.payload?.issue?.number;
  if (context.eventName !== 'issue_comment' || context.actor !== owner ||
      !context.payload?.issue?.pull_request || !Number.isInteger(number) ||
      number < 12169 || number > 12183) {
    throw new Error('Only the owner can request this registered 15-input cohort');
  }
  const heads = [...body.matchAll(/<!-- reviewer-eval-11951 head:([a-f0-9]{40}) -->/g)];
  if (heads.length !== 1) throw new Error('Supply exactly one frozen-head marker');
  const index = number - 12169;
  const caseId = String(6 + Math.floor(index / 3)).padStart(2, '0');
  return {number, head: heads[0][1], owner,
    repository: `${owner}/${context.repo.repo}`,
    branch: `codex/eval-reviewer-full-r${caseId}-p${index % 3 + 1}-20261105`};
}

function configuration(request, pr, reviews) {
  if (pr.number !== request.number || pr.state !== 'open' || pr.draft !== false ||
      pr.user?.login !== request.owner || pr.head?.repo?.full_name !== request.repository ||
      pr.head?.ref !== request.branch || pr.head?.sha !== request.head ||
      !pr.labels?.some(label => label.name === 'tier-b')) {
    throw new Error('The registered PR changed or is not an eligible never-merge study input');
  }
  if (reviews.some(r => r.commit_id === request.head &&
      ((r.user?.login === 'claude[bot]' && ['APPROVED', 'CHANGES_REQUESTED'].includes(r.state)) ||
       (['claude[bot]', 'github-actions[bot]'].includes(r.user?.login) &&
        r.state === 'COMMENTED' && r.body?.startsWith(REVIEW_MARKER))))) {
    return {skip: true};
  }
  const tools = ['Read', 'Grep', 'Glob', 'Bash(git diff:*)', 'Bash(git log:*)',
    'Bash(gh pr view:*)', 'Bash(gh pr diff:*)', 'Bash(gh pr checks:*)',
    `Bash(gh pr review ${request.number} --comment:*)`, 'Bash(cd:*)',
    'Bash(python -m pytest:*)', 'Bash(python3 -m pytest:*)', 'Bash(gh run view:*)',
    'Bash(echo:*)', 'Bash(tail:*)'];
  return {
    skip: false,
    head: request.head,
    args: `--model claude-sonnet-5-5 --tools Read,Grep,Glob,Bash --allowedTools "${tools.join(',')}" --max-turns 60 --max-budget-usd 0.40`,
    prompt: `Review PR #${request.number} in ${request.repository} at exactly ${request.head}.
This is a frozen, never-merge input for reviewer study #11951. Recheck that head before reviewing; stop if it moved. Never merge, push, edit tracked files, or open any .env* file.
Perform the semantic review in docs/release-loop/tier-b-review-brief.md: read CLAUDE.md, the description, linked issue and full diff; assess scope, standing principles, numbers, membership, tests and integration. Use the same evidence standards. Run focused tests directly without a pipe when needed; state exactly what you ran.
This cohort's CI qualification is recorded separately. Do not claim CI is green. CI failure alone is not a semantic finding: trace every alleged defect to production code, trigger, evidence and user impact. The normal brief's red-CI approval rule still holds, so this output is advisory and cannot supply its approval gate.
End with exactly one COMMENT review using gh pr review ${request.number} --comment --body <body>. Start its body with ${REVIEW_MARKER}, then Head: ${request.head}, then Advisory verdict: REQUEST_CHANGES or APPROVE, findings with evidence and smallest fixes, and tests run. Never submit --approve or --request-changes for this advisory route.`,
  };
}

async function configure(github, context) {
  const request = parseRequest(context);
  if (!request) return null;
  const args = {...context.repo, pull_number: request.number};
  const {data: pr} = await github.rest.pulls.get(args);
  const reviews = await github.paginate(github.rest.pulls.listReviews, {...args, per_page: 100});
  return configuration(request, pr, reviews);
}

module.exports = {MARKER, REVIEW_MARKER, parseRequest, configuration, configure};
