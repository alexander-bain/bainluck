import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
export const candidateRoot=process.env.CANDIDATE_ROOT || (fs.existsSync(path.join(here,'../src/broker.mjs')) ? path.resolve(here,'..') : path.resolve(here,'../fenced-display-authority-20261020'));
export const candidateUrl=file=>pathToFileURL(path.join(candidateRoot,file)).href;
