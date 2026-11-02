"""Choose a bounded live-path gate; uncertainty keeps the ordinary full CI path.

The existing ci-change-scope.sh remains the job classifier. This extension
selects directly impacted Python tests for its backend scope and always adds startup.
PEP 701 detection follows the #10090 py311_fstring_check.py, read in place;
Python 3.11 itself is the authoritative syntax gate on the hosted runner.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import subprocess
import sys
import tokenize
import warnings
from pathlib import Path

GLOBAL_MODULES = {'backend/app/main.py', 'backend/app/database.py', 'backend/app/celery_app.py'}


def is_live_event(event_name, event, associated_prs, sha):
    if event_name == 'pull_request':
        number = event.get('pull_request', {}).get('number')
        current = [pr for pr in associated_prs if pr.get('number') == number]
        if len(current) != 1:
            return False
        pr = current[0]
        return (pr.get('state') == 'open' and pr.get('head', {}).get('sha') == sha
                and pr.get('base', {}).get('ref') == 'master'
                and any(x.get('name') == 'live-path' for x in pr.get('labels', [])))
    if event_name != 'push' or event.get('ref') != 'refs/heads/master' or not associated_prs:
        return False
    return all(p.get('merged_at') and p.get('base', {}).get('ref') == 'master'
               and p.get('merge_commit_sha') == sha
               and any(x.get('name') == 'live-path' for x in p.get('labels', []))
               for p in associated_prs)


def module_name(path):
    name = path.removeprefix('backend/').removesuffix('.py').replace('/', '.')
    return name.removesuffix('.__init__')


def references(tree, current):
    refs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            refs.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                parent = current.split('.')[:-node.level]
                base = '.'.join(parent + ([base] if base else []))
            refs.add(base)
            refs.update(base + '.' + a.name for a in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.replace('/', '.').removeprefix('backend.').removesuffix('.py')
            if value.startswith('app.'):
                refs.add(value)
    return refs


def select_tests(root, changed):
    if not changed:
        return None
    speed_changes = [p for p in changed if p.startswith('tools/speed/')]
    for path in changed:
        if path.endswith('/conftest.py'):
            return None
        if path.startswith('tools/speed/'):
            if not (root / path).is_file():
                return None
            continue
        if not path.endswith('.py') or not path.startswith(('backend/app/', 'backend/tests/')):
            return None
        if path in GLOBAL_MODULES or path.endswith('/__init__.py') or path.startswith(('backend/app/models/', 'backend/app/config/')):
            return None
        if not (root / path).is_file():
            return None
    dependencies = {}
    paths = {}
    for directory in ('backend/app', 'backend/tests'):
        for file in (root / directory).rglob('*.py'):
            relative = file.relative_to(root).as_posix()
            name = module_name(relative)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', SyntaxWarning)
                    dependencies[name] = references(ast.parse(file.read_text()), name)
            except (SyntaxError, UnicodeError, OSError):
                return None
            paths[name] = relative
    changed_modules = {module_name(p) for p in changed}
    affected = set(changed_modules)
    # This bounded gate follows test-helper dependencies, not the entire
    # application graph. Broad regressions are owned by the post-deploy suite.
    while True:
        next_set = affected | {name for name, refs in dependencies.items()
                               if name.startswith('tests.') and refs & affected}
        if next_set == affected:
            break
        affected = next_set
    selected = {paths[name].removeprefix('backend/') for name in affected
                if name in paths and paths[name].startswith('backend/tests/test_')}
    for path in changed:
        if path.startswith('backend/app/'):
            target = module_name(path)
            if not any(name.startswith('tests.test_') and name != 'tests.test_startup'
                       and target in refs for name, refs in dependencies.items()):
                return None
    if not selected and any(p.startswith('backend/tests/') for p in changed):
        return None
    if speed_changes:
        selected.update('../' + p.relative_to(root).as_posix() for p in (root / 'tools/speed/tests').rglob('test_*.py'))
    selected.add('tests/test_startup.py')
    return sorted(selected)


def pep701_errors(path):
    if not hasattr(tokenize, 'FSTRING_START'):
        # The real 3.11 parser sees the forbidden syntax directly.
        try:
            compile(path.read_text(), str(path), 'exec')
        except SyntaxError as exc:
            return [(exc.lineno, exc.msg)]
        return []
    bad, stack = [], []
    for token in tokenize.generate_tokens(io.StringIO(path.read_text()).readline):
        if token.type == tokenize.FSTRING_START:
            quote = token.string.lstrip('rRfFbBuU')
            if stack and quote.startswith(stack[-1]):
                bad.append((token.start[0], 'nested f-string reuses enclosing quote'))
            stack.append(quote)
        elif token.type == tokenize.FSTRING_END:
            stack.pop()
        elif stack and token.type == tokenize.STRING:
            body = token.string.lstrip('rRbBuU')
            if body.startswith(stack[-1]):
                bad.append((token.start[0], 'replacement field reuses enclosing quote'))
            if '\\' in token.string:
                bad.append((token.start[0], 'backslash inside replacement field'))
        elif stack and token.type == tokenize.COMMENT:
            bad.append((token.start[0], 'comment inside f-string'))
    return bad


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--event-name', default=os.environ.get('GITHUB_EVENT_NAME', ''))
    parser.add_argument('--prs-json')
    args = parser.parse_args()
    root = Path.cwd()
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text()) if os.environ.get('GITHUB_EVENT_PATH') else {}
    prs = json.loads(Path(args.prs_json).read_text()) if args.prs_json else []
    live, selected = False, None
    # Do not deploy a fast candidate before item3's shared rollback exists.
    if (os.environ.get('RELEASE_LOOP_FAST_ENABLED') == 'true'
            and (root / 'tools/release/rollback.py').is_file()
            and is_live_event(args.event_name, event, prs, args.head)):
        try:
            output = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', args.base, args.head], text=True)
            changed = output.splitlines()
            if args.event_name == 'push':
                parent = subprocess.check_output(['git', 'rev-parse', args.head + '^1'], text=True).strip()
                if parent != args.base:
                    print('live=false\ntests=[]')
                    if os.environ.get('GITHUB_OUTPUT'):
                        with open(os.environ['GITHUB_OUTPUT'], 'a') as destination:
                            destination.write('live=false\ntests=[]\nrun_attempt=' + os.environ.get('GITHUB_RUN_ATTEMPT','') + '\nhead=' + args.head + '\n')
                    return 0
            for path in changed:
                if path.startswith('tools/speed/') and path.endswith('.sh') and (root / path).exists():
                    subprocess.run(['bash', '-n', str(root / path)], check=True)
                if path.endswith('.py') and (root / path).exists():
                    errors = pep701_errors(root / path)
                    if errors:
                        for line, reason in errors:
                            print(f'{path}:{line}: {reason}', file=sys.stderr)
                        return 1
            selected = select_tests(root, changed)
            live = selected is not None
        except (OSError, ValueError, subprocess.CalledProcessError):
            # Uncertain eligibility retains the full CI path.
            live, selected = False, None
    outputs = f'live={str(live).lower()}\ntests={json.dumps(selected or [])}\nrun_attempt={os.environ.get("GITHUB_RUN_ATTEMPT","")}\nhead={args.head}\n'
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as destination:
            destination.write(outputs)
    print(outputs, end='')
    return 0

if __name__ == '__main__':
    sys.exit(main())
