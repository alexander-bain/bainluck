"""Bounded provider calls. Credentials and response bodies never enter error messages."""
import json
import os
import time
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
        raw=response.read()
        return json.loads(raw) if raw.strip() else {}


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
    alias=vercel('/v4/aliases/bainluck.com')
    identity=alias.get('deploymentId') or (alias.get('deployment') or {}).get('id')
    if not identity: raise ValueError('live production domain has no deployment identity')
    return candidate('vercel',identity)


def github_pages(path, read=None):
    read=read or github
    rows=[]; page=1; deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        batch=read(path+('&' if '?' in path else '?')+'per_page=100&page='+str(page))
        if not isinstance(batch,list): raise ValueError('GitHub pagination shape is invalid')
        rows.extend(batch)
        if len(batch)<100: return rows
        page+=1
    raise TimeoutError('GitHub pagination did not finish')


def candidate(provider, candidate_id):
    if not isinstance(candidate_id,str) or not candidate_id or len(candidate_id)>128:
        raise ValueError('invalid provider candidate identity')
    quoted=urllib.parse.quote(candidate_id,safe='')
    if provider=='heroku':
        row=heroku('/releases/'+quoted)
        if row.get('status')!='succeeded': raise ValueError('release did not succeed')
        row['sha']=release_sha(row)
    else:
        row=vercel('/v13/deployments/'+quoted)
        if row.get('projectId')!=required('VERCEL_PROJECT_ID') or row.get('readyState')!='READY':
            raise ValueError('deployment is not ready in this project')
        row['sha']=row.get('meta',{}).get('githubCommitSha') or row.get('gitSource',{}).get('sha')
    return row


def report(line,key=None):
    number=required('NOW_ISSUE')
    if not number.isdecimal(): raise ValueError('NOW_ISSUE must be an issue number')
    body=' '.join(line.splitlines())
    if key:
        marker='<!-- release-loop:'+key+' -->'
        body+=' '+marker
        comments=github_pages('/issues/'+number+'/comments')
        previous=next((row for row in comments if marker in row.get('body','')),None)
        if previous:
            if previous['body']!=body:
                github('/issues/comments/'+str(previous['id']),'PATCH',{'body':body})
            return
    github('/issues/'+number+'/comments','POST',{'body':body})
