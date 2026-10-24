import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Checks are internal runner entry points, not clients for an existing database.
export function ownedPostgresConfig() {
  const data = process.env.DISPLAY_PERSIST_OWNED_PGDATA;
  const port = Number(process.env.PGPORT);
  if (!data || !Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error('Run npm test: a runner-owned PostgreSQL cluster is required.');
  }
  const root = fs.realpathSync(fileURLToPath(new URL('../.runtime/', import.meta.url)));
  const actual = fs.realpathSync(data);
  const relative = path.relative(root, actual);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error('The PostgreSQL data directory is outside this experiment runtime.');
  }
  const pid = fs.readFileSync(path.join(actual, 'postmaster.pid'), 'utf8').split('\n');
  if (fs.realpathSync(pid[1]) !== actual || Number(pid[3]) !== port) {
    throw new Error('Owned PostgreSQL process/port receipt does not match.');
  }
  return { host: '127.0.0.1', port, database: 'postgres', user: process.env.USER || 'agent' };
}
