"""Prepare the durable worker log path without sending anything until explicitly applied."""
import argparse
import hmac
import json
import subprocess
import sys
import urllib.error
import urllib.parse

import platforms


def prepare(apply,master_current,origin,destination_confirmed=False):
    plan={'activation':'held','drain':'https://bainluck.com/api/release-log-drain',
          'collector_origin':origin,'retention_seconds':7200,'max_records':5000,
          'requirements':['confirmed collector origin','master is current','loop routes merged and deployed',
                          'RELEASE_LOG_DRAIN_TOKEN and existing ADMIN_TOKEN','30 minutes of continuous worker history']}
    if not apply:return plan
    if not master_current or not origin or not destination_confirmed:
        raise ValueError('drain setup needs master-current and explicit destination confirmation')
    parsed=urllib.parse.urlsplit(origin.rstrip('/'))
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('collector origin must be a plain HTTPS origin')
    origin=origin.rstrip('/')
    secret=platforms.required('RELEASE_LOG_DRAIN_TOKEN');admin=platforms.required('ADMIN_TOKEN')
    if len(secret)<32:raise ValueError('drain token must have at least 32 characters')
    config=platforms.heroku('/config-vars')
    if not hmac.compare_digest(admin,config.get('ADMIN_TOKEN') or config.get('ADMIN_SECRET') or ''):
        raise ValueError('read token does not match existing backend admin authorization')
    project=platforms.required('VERCEL_PROJECT_ID')
    platforms.vercel('/v10/projects/'+project+'/env?upsert=true','POST',[
        {'key':'RELEASE_LOG_DRAIN_TOKEN','value':secret,'type':'encrypted','target':['production']},
        {'key':'RELEASE_LOG_API_ORIGIN','value':origin,'type':'plain','target':['production']},
    ])
    # GitHub's sealed secret receives only the existing machine read credential.
    subprocess.run(['gh','secret','set','ADMIN_TOKEN','--repo',platforms.REPO],input=admin,text=True,capture_output=True,check=True)
    subprocess.run(['gh','secret','set','RELEASE_LOG_DRAIN_TOKEN','--repo',platforms.REPO],input=secret,text=True,capture_output=True,check=True)
    try:platforms.github('/actions/variables/RELEASE_LOG_API_ORIGIN','PATCH',{'name':'RELEASE_LOG_API_ORIGIN','value':origin})
    except urllib.error.HTTPError as exc:
        if exc.code!=404:raise
        platforms.github('/actions/variables','POST',{'name':'RELEASE_LOG_API_ORIGIN','value':origin})
    drain='https://logplex:'+urllib.parse.quote(secret,safe='')+'@bainluck.com/api/release-log-drain'
    rows=platforms.heroku('/log-drains')
    if not any(row.get('url')==drain for row in rows):
        platforms.heroku('/log-drains','POST',{'url':drain})
    # Install the drain before changing the backend token so Logplex can retain
    # the restart's startup frames while the new web process becomes available.
    if config.get('RELEASE_LOG_DRAIN_TOKEN')!=secret:
        platforms.heroku('/config-vars','PATCH',{'RELEASE_LOG_DRAIN_TOKEN':secret})
    return {**plan,'collector_origin':origin,'activation':'configured; bootstrap Vercel routes, then warm history before arming'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--master-is-current',action='store_true')
    parser.add_argument('--collector-origin');parser.add_argument('--destination-confirmed',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare(args.apply,args.master_is_current,args.collector_origin,args.destination_confirmed),indent=2))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Durable drain setup refused: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
