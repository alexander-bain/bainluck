#!/usr/bin/env node
'use strict';
// Day 0: one weekly summary replaces every per-finding issue write.
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {summarize,weekStart,SUMMARY_LABELS} = require('../helpers/weeklySummary');
const REPO = 'alexander-bain/bainluck';
const TITLE = 'Browser audit weekly summary';
const MARKER = '<!-- browser-audit-weekly-summary -->';
const gh = args => execFileSync('gh',args,{encoding:'utf8'});
function findManifests(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir,{withFileTypes:true}).flatMap(entry=>{
    const full = path.join(dir,entry.name);
    return entry.isDirectory()?findManifests(full):entry.name==='manifest.json'?[full]:[];
  });
}
function main() {
  const runId = process.env.AUDIT_RUN_ID;
  const run = JSON.parse(gh(['api',`repos/${REPO}/actions/runs/${runId}`]));
  // Only the scheduled weekly production sweep writes. Manual browser checks
  // still publish their run summary and artifacts without adding issue noise.
  if (run.event !== 'schedule' || run.head_branch !== 'master') return;
  const files = findManifests(process.env.AUDIT_ARTIFACT_ROOT || 'audit-artifacts');
  const summary = summarize(files.map(file=>JSON.parse(fs.readFileSync(file,'utf8'))));
  fs.writeFileSync('filer-summary.md',summary);
  const week = weekStart(run.created_at);
  const weekMarker = `<!-- browser-audit-week:${week} -->`;
  const pages = JSON.parse(gh(['api',`repos/${REPO}/issues?state=all&per_page=100`,'--paginate','--slurp']));
  const candidates = pages.flat().filter(issue=>!issue.pull_request && String(issue.body||'').includes(MARKER));
  if (candidates.length > 1) throw new Error('dedup state unknown: duplicate summary issues; refusing');
  const body = `${weekMarker}\n## Week of ${week}\n\n${summary}\n\nRun: ${run.html_url}`;
  if (!candidates.length) {
    execFileSync('gh',['api','--method','POST',`repos/${REPO}/issues`,'--input','-'],{encoding:'utf8',input:JSON.stringify({title:TITLE,body:`${MARKER}\n\n${body}`,labels:SUMMARY_LABELS})});
    return;
  }
  const issue = candidates[0];
  const comments = JSON.parse(gh(['api',`repos/${REPO}/issues/${issue.number}/comments?per_page=100`,'--paginate','--slurp'])).flat();
  if ([issue,...comments].some(comment=>String(comment.body||'').includes(weekMarker))) return;
  gh(['api','--method','POST',`repos/${REPO}/issues/${issue.number}/comments`,'-f',`body=${body}`]);
}
try {main();} catch (error) {console.error(error.message);process.exitCode=1;}
