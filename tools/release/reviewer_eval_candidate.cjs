'use strict';

// Decide 75-A: the existing native reviewer may inspect the frozen study's
// never-merge inputs without full CI. This is not an alternative merge gate.
const LABEL = 'eval-candidate';
const REPOSITORY = 'alexander-bain/bainluck';

function hasLabel(pr) {
  return pr.labels?.some(label => label.name === LABEL) === true;
}

function registeredBranch(number) {
  let caseId, pass;
  if (number === 12132) [caseId, pass] = [2, 1];
  else if (number === 12150) [caseId, pass] = [12, 1];
  else if (number >= 12155 && number <= 12157) [caseId, pass] = [1, number - 12154];
  else if (number >= 12158 && number <= 12159) [caseId, pass] = [2, number - 12156];
  else if (number >= 12160 && number <= 12183) {
    [caseId, pass] = [3 + Math.floor((number - 12160) / 3), (number - 12160) % 3 + 1];
  } else if (number >= 12184 && number <= 12185) [caseId, pass] = [12, number - 12182];
  else if (number >= 12186 && number <= 12197) {
    [caseId, pass] = [13 + Math.floor((number - 12186) / 3), (number - 12186) % 3 + 1];
  } else return null;
  return `codex/eval-reviewer-full-r${String(caseId).padStart(2, '0')}-p${pass}-20261105`;
}

function eligible(pr, context, expectedHead) {
  if (!hasLabel(pr)) return false;
  const fullName = `${context.repo.owner}/${context.repo.repo}`;
  if (context.eventName !== 'pull_request_target' ||
      !['labeled', 'synchronize', 'reopened'].includes(context.payload.action) ||
      (context.payload.action === 'labeled' && context.payload.label?.name !== LABEL) ||
      fullName !== REPOSITORY || context.actor !== context.repo.owner ||
      pr.state !== 'open' || pr.draft !== true || pr.user?.login !== context.repo.owner ||
      pr.base?.ref !== 'master' || pr.head?.repo?.full_name !== fullName ||
      !registeredBranch(pr.number) || pr.head?.ref !== registeredBranch(pr.number) ||
      !/^[a-f0-9]{40}$/.test(expectedHead || '') || pr.head.sha !== expectedHead ||
      !pr.labels.some(label => label.name === 'tier-b')) {
    throw new Error('Only an owner-admitted exact-head registered never-merge study PR may bypass CI');
  }
  return true;
}

function alreadyReviewed(reviews, head) {
  return reviews.some(review => review.user?.login === 'claude[bot]' &&
    review.commit_id === head && ['APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'].includes(review.state));
}

module.exports = {LABEL, REPOSITORY, hasLabel, registeredBranch, eligible, alreadyReviewed};
