"""Bounded provider calls. Credentials and response bodies never enter error messages."""
import json
import os
import urllib.parse
import urllib.request

REPO = 'alexander-bain/bainluck'


def request(url, token=None, method='GET', body=None, headers=None):
    h = {'Accept':'application/json', 'User-Agent':'bainluck-release-loop'}
    if token: h['Authorization'] = 'Bearer ' + token
    if headers: h.update(headers)
    data = None if body is None else json.dumps(body).encode()
    if data is not None: h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, headers=h, data=data, method=method)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


def required(name):
    value = os.environ.get(name)
    if not value: raise ValueError('required setting missing: ' + name)
    return value


def heroku(path, method='GET', body=None, headers=None):
    h={'Accept':'application/vnd.heroku+json; version=3'}
    h.update(headers or {})
    return request('https://api.heroku.com/apps/bainluck' + path, required('HEROKU_API_KEY'), method, body, h)


def vercel(path, method='GET', body=None):
    team = os.environ.get('VERCEL_TEAM_ID')
    if team: path += ('&' if '?' in path else '?') + urllib.parse.urlencode({'teamId':team})
    return request('https://api.vercel.com' + path, required('VERCEL_TOKEN'), method, body)


def github(path, method='GET', body=None):
    return request('https://api.github.com/repos/' + REPO + path, required('GH_TOKEN'), method, body,
                   {'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})


def release_sha(release):
    slug = release.get('slug')
    return heroku('/slugs/' + slug['id'])['commit'] if slug else None


def deployments(provider):
    if provider == 'heroku':
        rows = heroku('/releases', headers={'Range':'version ..; order=desc, max=100'})
        rows = [row for row in rows if row.get('status') == 'succeeded' and row.get('slug')]
        for row in rows:
            row['sha'] = release_sha(row)
        return rows
    project = required('VERCEL_PROJECT_ID')
    rows = vercel('/v6/deployments?' + urllib.parse.urlencode({'projectId':project,'target':'production','state':'READY','limit':100}))['deployments']
    for row in rows: row['sha'] = row.get('meta',{}).get('githubCommitSha') or row.get('gitSource',{}).get('sha')
    return rows


def current(provider):
    if provider == 'heroku':
        rows = heroku('/releases', headers={'Range':'version ..; order=desc, max=100'})
        row = next(row for row in rows if row.get('status') == 'succeeded')
        row['sha'] = release_sha(row)
        return row
    row = vercel('/v9/projects/' + required('VERCEL_PROJECT_ID'))['targets']['production']
    row['id'] = row.get('id') or row['deploymentId']
    row['sha'] = row.get('meta',{}).get('githubCommitSha') or row.get('gitSource',{}).get('sha')
    if not row['sha']:
        deployment = vercel('/v13/deployments/' + row['id'])
        row['sha'] = deployment.get('meta',{}).get('githubCommitSha') or deployment.get('gitSource',{}).get('sha')
    return row


def report(line):
    # The NOW issue number is intentionally a repository variable: the issue is
    # created for Day 0 and was not in master when this loop was prepared.
    number = required('NOW_ISSUE')
    if not number.isdecimal(): raise ValueError('NOW_ISSUE must be an issue number')
    github('/issues/' + number + '/comments', 'POST', {'body':line.replace('\n',' ')})
