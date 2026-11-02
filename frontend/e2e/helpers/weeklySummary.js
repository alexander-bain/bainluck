'use strict';
const {findingsFromManifest,decide,ACTIONS} = require('./sweepFiling');
const {validateManifest} = require('./manifest');

function weekStart(created) {
  const date = new Date(created);
  if (Number.isNaN(date.getTime())) throw new Error('invalid run timestamp');
  date.setUTCHours(0,0,0,0);
  date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
  return date.toISOString().slice(0,10);
}

const safe = value => String(value || 'unknown').replace(/[`|@<>\r\n]/g,' ').slice(0,160);
function summarize(manifests, expected) {
  if (!manifests.length) throw new Error('no manifest found; refusing');
  const lines = ['| journey | result | findings |','|---|---|---|'];
  let incomplete = false;
  for (const manifest of manifests) {
    const valid = validateManifest(manifest).ok;
    if (!valid) throw new Error('manifest untrusted or empty; refusing');
    if (!expected || manifest.run.checkout_sha !== expected.headSha) throw new Error('grading commit does not match triggering run');
    if (String(manifest.run.run_id) !== expected.runId) throw new Error('run identity does not match triggering run');
    const findings = findingsFromManifest(manifest);
    for (const finding of findings) {
      const decision = decide({verdict:finding.infra?'INFRA':'FAIL',manifestValid:valid,
        shaBound:true,fingerprint:finding.fingerprint,openIssue:false});
      if (decision.action === ACTIONS.REFUSE) throw new Error('manifest finding untrusted; refusing');
    }
    for (const journey of manifest.journeys) {
      if (!['pass','fail'].includes(journey.result)) incomplete = true;
      const reasons = findings.filter(f=>f.journey_id === journey.journey_id).map(f=>safe(f.reason_code));
      lines.push(`| ${safe(journey.journey_id)} | ${safe(journey.result)} | ${reasons.join(', ') || '—'} |`);
    }
  }
  lines.unshift(incomplete ? '**Evidence incomplete:** infrastructure or unknown results remain.' : 'Results for the weekly browser sweep.', '');
  const result = lines.join('\n');
  if (result.length > 55000) throw new Error('summary too large; refusing');
  return result;
}
const SUMMARY_LABELS = ['area:frontend','program:ux','priority:p3'];
module.exports = {weekStart,summarize,SUMMARY_LABELS};
