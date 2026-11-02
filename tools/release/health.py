"""Run the #10090 worker and latency checks plus anonymous public route probes."""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

import platforms
import discover

SPEED = pathlib.Path(__file__).resolve().parents[1] / 'speed'
ENTRY = re.compile(r'(\d+):(\d+):([A-Za-z_>:]+(?:\([^)]*\))?(?:\[[^\]]*\])?)')


def require_speed_tools(path=SPEED):
    for name in ('check.py','latency_guard2.py','latency_guard3.py'):
        if not (path/name).is_file(): raise FileNotFoundError(str(path/name))


def validate_health(body):
    if not isinstance(body,dict) or body.get('status') != 'ok' or body.get('db') is not True or body.get('redis') is not True:
        raise ValueError('anonymous health reports an unavailable dependency')


def validate_feed(body):
    if not isinstance(body,dict) or not isinstance(body.get('items'),list) or not body['items'] or any(not isinstance(x,dict) for x in body['items']):
        raise ValueError('anonymous feed is empty or malformed')


def probe(provider):
    # No cookie, Authorization, admin key, or signed-in session on these GETs.
    validate_health(platforms.request('https://api.bainluck.com/api/health'))
    validate_feed(platforms.request('https://api.bainluck.com/api/feed?limit=5'))
    if provider == 'vercel':
        with urllib.request.urlopen('https://bainluck.com', timeout=20) as response:
            if response.status != 200 or b'<html' not in response.read(1024*1024).lower():
                raise ValueError('production frontend is unavailable')


def verdict(output):
    lines=[line for line in output.splitlines() if line.startswith('VERDICT ')]
    if not lines: raise ValueError('speed tool returned no verdict')
    return lines[-1]


def run_tool(name,*args):
    result=subprocess.run([sys.executable,str(SPEED/name),*map(str,args)], capture_output=True,text=True,timeout=20)
    if result.returncode != 0: raise ValueError('speed tool failed: '+name)
    return verdict(result.stdout)


def effective(n, maximum, worst):
    # Same no-valid-price handling as the operational streak.py, before guard2
    # applies its separate na_orientation exclusion. Do not substitute HTTP latency.
    entries=[(int(ms),label) for _,ms,label in ENTRY.findall(worst)]
    dropped=sum('stamp_no_reading' in label for _,label in entries)
    if not dropped: return maximum, True
    rest=[ms for ms,label in entries if 'stamp_no_reading' not in label]
    if rest: return rest[0],True
    bound=entries[-1][0] if entries else maximum
    return bound,bound<500 or len(entries)<5


def streak_lines(raw):
    rows={}
    for line in raw.splitlines():
        if 'headline-clock' not in line: continue
        match=re.search(r'\]: (\{.*\})\s*$',line)
        try: message=json.loads(match.group(1))['message'] if match else line
        except (ValueError,KeyError): continue
        venue=re.search(r'live_blend_refresh\[(kalshi|polymarket)\]',message)
        n=re.search(r'n=(\d+)',message); maximum=re.search(r'max_ms=(\d+)',message); worst=re.search(r'worst=(\S+)',message)
        if not venue or not n or not maximum: continue
        # ISO date is the key so UTC midnight does not reorder minutes.
        rows.setdefault(line[:16],{})[venue.group(1)]=(int(n.group(1)),int(maximum.group(1)),worst.group(1) if worst else '-')
    lines=[]
    for stamp,row in sorted(rows.items()):
        k,p=row.get('kalshi'),row.get('polymarket')
        if not k or not p or not k[0] or not p[0]: continue
        ke,kk=effective(*k); pe,pk=effective(*p)
        lines.append('%s %s K=%dms P=%dms | K %s | P %s' % (stamp[11:16], 'PASS' if kk and pk and max(ke,pe)<500 else 'FAIL',ke,pe,k[2][:160],p[2][:160]))
    return lines


def capture():
    session=platforms.heroku('/log-sessions','POST',{'lines':1500,'tail':False,'dyno':'worker-ws.1'})
    with urllib.request.urlopen(session['logplex_url'],timeout=20) as response:
        return response.read().decode('utf-8','replace')


def watch(provider,candidate,working):
    require_speed_tools()
    release=dt.datetime.fromisoformat(candidate['created_at'].replace('Z','+00:00')) if provider=='heroku' else dt.datetime.now(dt.timezone.utc)
    started=time.monotonic(); deadline=started+1500
    combined={}; boot=False
    while time.monotonic()<deadline:
        if platforms.current(provider)['id'] != candidate['id']: return 'SUPERSEDED'
        probe(provider)
        raw=capture()
        for line in raw.splitlines(): combined[line]=None
        raw='\n'.join(combined)+'\n'
        cap=working/'worker-ws.log'; cap.write_text(raw)
        streak=working/'streak.log'; streak.write_text('\n'.join(streak_lines(raw))+'\n')
        if provider=='heroku':
            health=run_tool('check.py',release.isoformat(),cap)
            if health.startswith('VERDICT ROLLBACK'): return health
            # Existing check's own explicit "3-min health PASS" precedes A10
            # completion; PENDING with this suffix must never be called full PASS.
            boot=boot or health.startswith('VERDICT PASS') or '3-min health PASS' in health
        else:
            boot=time.monotonic()-started>=180
        start=(release+dt.timedelta(minutes=2)).strftime('%H:%M')
        latency=run_tool('latency_guard2.py',streak,start,5000,10)
        headline=run_tool('latency_guard3.py',streak,release.strftime('%H:%M'),start,12,20,30)
        for result in (latency,headline):
            if result.startswith('VERDICT ROLLBACK'): return result
        if boot and latency.startswith('VERDICT PASS') and headline.startswith('VERDICT PASS'):
            return 'VERDICT PASS'
        print('Waiting: boot=%s; %s; %s' % (boot,latency,headline),flush=True)
        time.sleep(30)
    return 'VERDICT ROLLBACK no conclusive health within the existing 25-minute observation deadline'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',required=True,choices=['heroku','vercel'])
    parser.add_argument('--candidate-id')
    parser.add_argument('--candidate-sha')
    parser.add_argument('--output',default='release-health.json')
    args=parser.parse_args()
    require_speed_tools()
    candidate=platforms.current(args.provider)
    out={'provider':args.provider,'candidate_id':candidate['id'],'candidate_sha':candidate.get('sha'),'verdict':'UNKNOWN','rollback':False}
    if candidate['id'] in discover.receipts(args.provider):
        out['verdict']='ALREADY CHECKED'
    elif (args.candidate_id and candidate['id']!=args.candidate_id) or (args.candidate_sha and candidate.get('sha')!=args.candidate_sha):
        out['verdict']='SUPERSEDED'
    else:
        try:
            working=pathlib.Path(os.environ.get('RUNNER_TEMP','/tmp'))/'release-loop'/candidate['id']
            working.mkdir(parents=True,exist_ok=True)
            out['verdict']=watch(args.provider,candidate,working)
        except Exception as exc:
            out['verdict']='VERDICT ROLLBACK health observer failed: '+type(exc).__name__
        out['rollback']=out['verdict'].startswith('VERDICT ROLLBACK')
    pathlib.Path(args.output).write_text(json.dumps(out))
    output=os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output,'a') as stream:
            for key in ('candidate_id','candidate_sha','rollback'):
                stream.write('%s=%s\n' % (key,str(out[key]).lower() if isinstance(out[key],bool) else out[key]))
    if out['verdict']=='VERDICT PASS':
        discover.record(args.provider,candidate,out['verdict'])
    if not out['rollback'] and out['verdict'] != 'ALREADY CHECKED':
        platforms.report('%s %s %s: %s' % (args.provider,candidate['id'],str(candidate.get('sha',''))[:8],out['verdict']))
    print(out['verdict'])
    return 1 if out['rollback'] else 0

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as exc:
        print('Health observer failed: '+type(exc).__name__,file=sys.stderr); sys.exit(2)
