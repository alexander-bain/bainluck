"""Prepare the signed GitHub review subscription; default is read-only preview."""
import argparse
import hashlib
import hmac
import json
import os
import subprocess
import urllib.request

REPO = 'alexander-bain/bainluck'
URL = 'https://api.bainluck.com/api/release-loop/tier-b-review'


def gh(method, path, body=None):
    args = ['gh', 'api', '--method', method, path]
    if body is not None:
        args.extend(['--input', '-'])
    result = subprocess.run(args, input=json.dumps(body) if body is not None else None,
                            text=True, capture_output=True, check=True)
    return json.loads(result.stdout or '{}')


def configuration(secret):
    return {'url': URL, 'content_type': 'json', 'insecure_ssl': '0', 'secret': secret}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirmation', default='')
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({'repository': REPO, 'url': URL, 'events': ['pull_request_review'],
                          'secret_environment': 'TIER_B_REVIEW_WEBHOOK_SECRET', 'applied': False}, indent=2))
        return
    if args.confirmation != 'branch protection on':
        parser.error('setup requires Alex to write "branch protection on"')
    secret = os.environ.get('TIER_B_REVIEW_WEBHOOK_SECRET')
    if not secret:
        parser.error('TIER_B_REVIEW_WEBHOOK_SECRET is not configured')
    # Verify the deployed receiver before creating any active subscription.
    body = json.dumps({'repository': {'full_name': REPO}}).encode()
    signature = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(URL, data=body, method='POST',
        headers={'Content-Type': 'application/json', 'X-GitHub-Event': 'ping',
                 'X-Hub-Signature-256': signature})
    with urllib.request.urlopen(request, timeout=10) as response:
        ping = json.load(response)
    if ping.get('accepted') is not True:
        raise RuntimeError('signed review receiver did not verify')
    result = subprocess.run(['gh', 'api', f'repos/{REPO}/hooks?per_page=100', '--paginate', '--slurp'],
                            text=True, capture_output=True, check=True)
    hooks = [hook for page in json.loads(result.stdout) for hook in page]
    matching = [hook for hook in hooks if hook.get('config', {}).get('url') == URL]
    if len(matching) > 1:
        raise RuntimeError('duplicate review subscriptions; refusing')
    if matching:
        hook = matching[0]
        events = sorted(set(hook.get('events', [])) | {'pull_request_review'})
        actual = gh('PATCH', f'repos/{REPO}/hooks/{hook["id"]}',
                    {'active': True, 'events': events, 'config': configuration(secret)})
    else:
        actual = gh('POST', f'repos/{REPO}/hooks', {'name': 'web', 'active': True,
                    'events': ['pull_request_review'], 'config': configuration(secret)})
    if not actual.get('active') or 'pull_request_review' not in actual.get('events', []):
        raise RuntimeError('review subscription did not take effect')
    print('Signed review subscription is active; default-branch policy receives review updates.')


if __name__ == '__main__':
    main()
