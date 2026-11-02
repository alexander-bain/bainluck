#!/usr/bin/env python3
"""Prepare master protection; activation requires Alex's exact explicit signal."""
import argparse
import json
from pathlib import Path
import subprocess

REPO = 'alexander-bain/bainluck'
ROOT = Path(__file__).resolve().parents[2]


def protection(contexts):
    if not contexts:
        raise ValueError('refusing protection without required checks')
    return {
        'required_status_checks': {'strict': True, 'contexts': sorted(set(contexts))},
        'enforce_admins': True,
        'required_pull_request_reviews': {
            'dismiss_stale_reviews': True,
            'require_code_owner_reviews': False,
            'required_approving_review_count': 0,
            'bypass_pull_request_allowances': {'users': [], 'teams': [], 'apps': []},
        },
        'restrictions': None,
        'allow_force_pushes': False,
        'allow_deletions': False,
        'required_conversation_resolution': True,
    }


def api(method, endpoint, body=None):
    result = subprocess.run(
        ['gh', 'api', '--method', method, endpoint, '--input', '-']
        if body is not None else ['gh', 'api', '--method', method, endpoint],
        input=json.dumps(body) if body is not None else None,
        text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout or '{}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--confirmation', default='')
    args = parser.parse_args()
    contexts = json.loads((ROOT / '.github/release-loop-required-checks.json').read_text())
    desired = protection(contexts)
    if not args.activate:
        print(json.dumps({'repository': REPO, 'allow_auto_merge': True,
                          'master_protection': desired, 'activated': False}, indent=2))
        return
    if args.confirmation != 'branch protection on':
        parser.error('activation requires Alex to write "branch protection on"')
    # Preserve any already-required contexts; never weaken an existing gate.
    try:
        existing = api('GET', f'repos/{REPO}/branches/master/protection')
    except subprocess.CalledProcessError as error:
        if '(HTTP 404)' not in error.stderr:
            raise
        existing = {}
    old_checks = existing.get('required_status_checks') or {}
    contexts.extend(old_checks.get('contexts', []))
    contexts.extend(c['context'] for c in old_checks.get('checks', []))
    desired = protection(contexts)
    old_reviews = existing.get('required_pull_request_reviews') or {}
    desired['required_pull_request_reviews']['required_approving_review_count'] = old_reviews.get('required_approving_review_count', 0)
    # Protection first, then auto-merge. Enabling repository support does not
    # opt any PR into auto-merge and does not merge a commit.
    api('PUT', f'repos/{REPO}/branches/master/protection', desired)
    api('PATCH', f'repos/{REPO}', {'allow_auto_merge': True})
    actual = api('GET', f'repos/{REPO}/branches/master/protection')
    if not actual.get('enforce_admins', {}).get('enabled'):
        raise RuntimeError('admin enforcement did not take effect')
    if not actual.get('required_pull_request_reviews'):
        raise RuntimeError('pull request requirement did not take effect')
    got = set((actual.get('required_status_checks') or {}).get('contexts', []))
    if not set(contexts).issubset(got):
        raise RuntimeError('required check verification failed')
    print('Master requires PRs and checks; admin bypass off; repository auto-merge enabled.')


if __name__ == '__main__':
    main()
