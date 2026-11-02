"""Shared health/full-suite rollback. Run in the provider's deployment concurrency group."""
import argparse
import json
import re
import sys
import time

import platforms
import discover
import veto


def rollback_if_current(provider, candidate_sha, candidate_id, live, previous_id, write):
    if not re.fullmatch(r'[0-9a-f]{40}', candidate_sha or ''):
        raise ValueError('rollback requires a full candidate SHA')
    if not live.get('sha') or not live.get('id') or not previous_id or previous_id == candidate_id:
        raise ValueError('rollback identity or prior release is unknown')
    if live['sha'] != candidate_sha or (candidate_id and live['id'] != candidate_id):
        return False
    write({'release':previous_id} if provider == 'heroku' else {'deploymentId':previous_id})
    return True


def known_good_targets(rows,candidate_sha):
    failed=discover.failed_sources(rows)
    targets=[]; seen=set()
    for row in rows:
        payload=row.get('payload',{})
        if not isinstance(payload,dict): continue
        sha=payload.get('candidate_sha'); identity=payload.get('candidate_id')
        if payload.get('verdict')=='VERDICT PASS' and sha!=candidate_sha and sha not in failed and identity not in seen and re.fullmatch(r'[0-9a-f]{40}',sha or ''):
            targets.append((identity,sha));seen.add(identity)
    return targets


def rollback(provider,candidate_sha,candidate_id=None,previous_id=None):
    live=platforms.current(provider)
    if live.get('sha')!=candidate_sha or (candidate_id and live['id']!=candidate_id): return False
    candidate_id=candidate_id or live['id']
    rows=discover.receipt_rows(provider)
    # Failure invalidates every older PASS of this source, including a restored
    # release, so a second failure cannot oscillate back to known-bad code.
    discover.record(provider,{'id':candidate_id,'sha':candidate_sha},'ROLLBACK REQUESTED')
    targets=known_good_targets(rows,candidate_sha)
    if previous_id: targets=[target for target in targets if target[0]==previous_id]
    if not targets: raise ValueError('no verified non-failed rollback baseline; bootstrap is required')
    previous_id,target_sha=targets[0]
    target=platforms.candidate(provider,previous_id)
    if target.get('sha')!=target_sha: raise ValueError('rollback baseline source disagrees with its PASS receipt')
    def write(body):
        if target_sha in discover.failed_sources(discover.receipt_rows(provider)):
            raise ValueError('rollback target received a failed-source veto after selection')
        if provider=='heroku': return platforms.heroku('/releases','POST',body)
        return platforms.vercel('/v1/projects/'+platforms.required('VERCEL_PROJECT_ID')+'/rollback','POST',body)
    changed=rollback_if_current(provider,candidate_sha,candidate_id,platforms.current(provider),previous_id,write)
    if changed: verify_rollback(provider,target_sha)
    return changed


def verify_rollback(provider, target_sha, read=None, sleep=time.sleep, now=time.monotonic):
    read=read or (lambda: platforms.current(provider))
    deadline=now()+90
    while now()<deadline:
        if read().get('sha')==target_sha: return
        sleep(2)
    raise RuntimeError('provider did not confirm the rollback target')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider', choices=['heroku','vercel'], required=True)
    parser.add_argument('--candidate-sha', required=True)
    parser.add_argument('--candidate-id')
    parser.add_argument('--previous-id')
    parser.add_argument('--reason', required=True)
    args=parser.parse_args()
    veto.mark_failed(args.candidate_sha,args.reason)
    candidate=platforms.candidate(args.provider,args.candidate_id) if args.candidate_id else platforms.current(args.provider)
    if candidate.get('sha')!=args.candidate_sha:
        print('SUPERSEDED');return 0
    changed=rollback(args.provider,args.candidate_sha,candidate['id'],args.previous_id)
    if changed:
        discover.record(args.provider,{'id':candidate['id'],'sha':args.candidate_sha},'ROLLED BACK')
    platforms.report('%s %s %s: %s — %s' % (args.provider,args.candidate_id or '',args.candidate_sha[:8],
                     'ROLLED BACK' if changed else 'superseded; no rollback',args.reason),key=args.provider+':'+candidate['id'])
    print('ROLLED BACK' if changed else 'SUPERSEDED')
    return 1 if changed else 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as exc:
        print('Rollback refused: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(2)
