#!/usr/bin/env bash
# Validate branch-local frontend test dependencies before borrowing an install.
# Usage: scripts/setup-worktree-deps.sh [target-worktree] [source-worktree]
# Default source: ~/bainluck. Existing private installs are checked and preserved.
# This never installs packages, replaces existing links/directories, or writes to
# the source install. If borrowing refuses, use npm ci in a PRIVATE target only:
# first remove an unwanted node_modules SYMLINK explicitly, never its destination.
set -euo pipefail
TARGET="${1:-$(git rev-parse --show-toplevel)}"
SOURCE="${2:-$HOME/bainluck}"
if [ "$#" -gt 2 ]; then
  echo 'Usage: setup-worktree-deps.sh [target-worktree] [source-worktree]' >&2
  exit 1
fi
command -v node >/dev/null || { echo 'FAIL: Node.js is required to validate dependencies.' >&2; exit 1; }
node - "$TARGET" "$SOURCE" <<'JS'
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {execFileSync} = require('node:child_process');
const required = ['ts-jest', 'jest', 'jest-environment-jsdom', 'next', 'typescript'];
let created;
function fail(message) { throw new Error(message); }
function json(file) {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink()) fail(`Expected a regular file: ${file}`);
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}
function inputs(frontend) {
  const manifest = path.join(frontend, 'package.json');
  const lockfile = path.join(frontend, 'package-lock.json');
  const pkg = json(manifest), lock = json(lockfile);
  if (lock.lockfileVersion !== 3 || !lock.packages || !lock.packages[''])
    fail(`Expected npm lockfile v3 with a root package: ${lockfile}`);
  for (const field of ['dependencies', 'devDependencies', 'optionalDependencies']) {
    if (stable(pkg[field] || {}) !== stable(lock.packages[''][field] || {}))
      fail(`package.json and package-lock.json disagree on ${field}: ${frontend}`);
  }
  return {pkg, lock, manifest: fs.readFileSync(manifest), lockfile: fs.readFileSync(lockfile)};
}
function stable(value) {
  if (Array.isArray(value)) return JSON.stringify(value.map(v => JSON.parse(stable(v))));
  if (value && typeof value === 'object')
    return JSON.stringify(Object.fromEntries(Object.keys(value).sort().map(k => [k, JSON.parse(stable(value[k]))])));
  return JSON.stringify(value);
}
function packagePath(modules, key) {
  // Lock paths are data, never shell/code or permission to leave this install.
  if (!/^node_modules\/(?:[^/]+\/)*[^/]+$/.test(key) || key.split('/').some(p => p === '.' || p === '..'))
    fail(`Unsupported installed-lock path: ${key}`);
  const result = path.resolve(path.dirname(modules), key);
  if (!result.startsWith(modules + path.sep)) fail(`Installed-lock path escapes install: ${key}`);
  return result;
}
function verifyInstall(frontend, modules, target) {
  if (!fs.lstatSync(modules).isDirectory()) fail(`Install must be a real directory: ${modules}`);
  const installed = json(path.join(modules, '.package-lock.json'));
  if (installed.lockfileVersion !== 3 || !installed.packages)
    fail(`Missing npm v3 installed-lock metadata: ${modules}`);
  const fields = ['version', 'resolved', 'integrity', 'dependencies', 'optionalDependencies', 'peerDependencies', 'peerDependenciesMeta'];
  for (const [key, entry] of Object.entries(target.lock.packages)) {
    if (!key) continue;
    if (typeof entry.version !== 'string' || !entry.version) fail(`Target lock lacks an exact package version: ${key}`);
    if (!installed.packages[key] && !entry.optional)
      fail(`Installed lock is missing required package ${key}; use a private exact-lock npm ci`);
  }
  for (const [key, entry] of Object.entries(installed.packages)) {
    const expected = target.lock.packages[key];
    if (!expected || entry.link || expected.link) fail(`Unexpected or linked installed-lock package: ${key}`);
    if (fields.some(field => stable(entry[field] ?? null) !== stable(expected[field] ?? null)))
      fail(`Installed lock differs from target lock: ${key}`);
    const directory = packagePath(modules, key);
    if (!fs.lstatSync(directory).isDirectory() || fs.realpathSync(directory) !== directory)
      fail(`Package must not be hand-linked or escape the install: ${key}`);
    const actual = json(path.join(directory, 'package.json'));
    if (actual.version !== expected.version) fail(`Installed version differs from target lock: ${key}`);
  }
  for (const name of required) {
    if (!target.pkg.dependencies?.[name] && !target.pkg.devDependencies?.[name])
      fail(`Target must declare required frontend tool ${name}`);
    const key = 'node_modules/' + name;
    if (!installed.packages[key]) fail(`Missing required frontend tool ${name}`);
    // resolve() finds an executable module entry without running package code.
    const resolved = fs.realpathSync(createRequire(path.join(frontend, 'package.json')).resolve(name));
    const directory = path.join(modules, name);
    if (!resolved.startsWith(directory + path.sep)) fail(`Required tool resolves outside validated install: ${name}`);
  }
}
try {
  const targetRoot = fs.realpathSync(process.argv[2]);
  const frontend = path.join(targetRoot, 'frontend');
  if (!fs.lstatSync(frontend).isDirectory()) fail(`Invalid target frontend: ${frontend}`);
  const target = inputs(frontend);
  const destination = path.join(frontend, 'node_modules');
  let existing;
  try { existing = fs.lstatSync(destination); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (existing && !existing.isSymbolicLink()) {
    if (!existing.isDirectory()) fail(`Refusing to replace existing target: ${destination}`);
    verifyInstall(frontend, destination, target);
    console.log(`verified private install, preserved: ${destination}`);
  } else {
    const sourceRoot = fs.realpathSync(process.argv[3]);
    const sourceFrontend = path.join(sourceRoot, 'frontend');
    const source = inputs(sourceFrontend);
    if (!target.manifest.equals(source.manifest) || !target.lockfile.equals(source.lockfile))
      fail('Target/source package.json or package-lock.json differ; borrowing is unsafe');
    const modules = path.join(sourceFrontend, 'node_modules');
    verifyInstall(sourceFrontend, modules, target);
    if (existing && fs.realpathSync(destination) !== modules)
      fail(`Existing dependency symlink points elsewhere; leaving it unchanged: ${destination}`);
    try { execFileSync('git', ['-C', targetRoot, 'check-ignore', '-q', '--', 'frontend/node_modules']); }
    catch { fail('Target must be a Git worktree ignoring frontend/node_modules; fix .gitignore before borrowing'); }
    if (!existing) {
      fs.symlinkSync(modules, destination, 'dir'); // exclusive create, never replace another install
      created = destination;
    }
    // Catch input drift during setup. Borrowing does not lock another writer's
    // future npm operations; use private npm ci if the source may be modified.
    const after = inputs(sourceFrontend);
    if (!source.manifest.equals(after.manifest) || !source.lockfile.equals(after.lockfile))
      fail('Source dependency inputs changed during setup');
    verifyInstall(frontend, modules, target);
    console.log(`verified borrowed install: ${destination} -> ${modules}`);
  }
  console.log('verified: exact inputs/installed-lock metadata, installed versions and required tool resolution (including jest-environment-jsdom).');
  console.log('Run the target tests with TZ=UTC. This is not a package-content integrity audit or a lock against later shared-install changes.');
} catch (error) {
  if (created) {
    try { if (fs.lstatSync(created).isSymbolicLink()) fs.unlinkSync(created); } catch {}
  }
  console.error(`FAIL: ${error.message}`);
  console.error('No existing private install or source dependencies were changed. For a private worktree, remove only an unwanted node_modules symlink, then run npm ci in its frontend directory. Never install through a borrowed symlink.');
  process.exitCode = 1;
}
JS
