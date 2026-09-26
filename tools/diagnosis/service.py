"""Install/start or stop the one local launchd diagnosis worker."""
from pathlib import Path
import os
import json
import datetime as dt
import plistlib
import subprocess
import sys

label = 'com.bainluck.diagnosis'
target = f'gui/{os.getuid()}/{label}'
root = Path.home() / 'bainluck-diagnosis'
plist = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
if sys.argv[1] == 'stop':
    root.mkdir(exist_ok=True)
    (root / 'PAUSED').touch()
    result = subprocess.run(['launchctl', 'bootout', target], capture_output=True, text=True)
    print('Diagnosis lane stopped/paused. Existing artifacts preserved.')
    if result.returncode and 'Could not find service' not in result.stderr:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    (root/'STATUS.json').write_text(json.dumps({'state':'stopped','updated_at':dt.datetime.now(dt.timezone.utc).isoformat()})+'\n')
else:
    root.mkdir(exist_ok=True)
    (root / 'PAUSED').unlink(missing_ok=True)
    if subprocess.run(['launchctl','print',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0:
        print('Diagnosis service already loaded; active session left alone.')
        raise SystemExit(0)
    plist.parent.mkdir(parents=True, exist_ok=True)
    data = {'Label':label, 'ProgramArguments':[sys.executable,str(Path(__file__).with_name('runner.py')),'loop'],
            'WorkingDirectory':str(root), 'RunAtLoad':True, 'KeepAlive':True,'ThrottleInterval':60,
            'ProcessType':'Background', 'StandardOutPath':str(root/'service.log'),
            'StandardErrorPath':str(root/'service.log'),
            'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/local/bin:/usr/bin:/bin:/opt/facebook/bin')}}
    plist.write_bytes(plistlib.dumps(data))
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=True)
    print('Diagnosis service started; launchd will restart it after crashes and login.')
