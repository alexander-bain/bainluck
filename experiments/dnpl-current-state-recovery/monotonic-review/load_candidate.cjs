const path = require('node:path');
const Module = require('node:module');
const ROOT = path.resolve(__dirname, '..');
const esbuild = require(path.join(ROOT, 'harness/node_modules/esbuild'));
module.exports = function loadCandidate() {
  const directory='monotonic-candidate';
  const source = path.join(ROOT, directory);
  const names = ['blendPreview','acceptCurrentPreview','requestLease'];
  const contents = names.map(name =>
    `export * from ${JSON.stringify(path.join(source, name+'.ts'))};`).join('\n');
  const built = esbuild.buildSync({stdin:{contents,resolveDir:ROOT,sourcefile:'independent-monotonic-review.ts'},
    bundle:true,write:false,platform:'node',format:'cjs',alias:{'@':path.join(ROOT,'source/frontend')}});
  const loaded = new Module(path.join(__dirname,'in-memory-review.cjs'), module);
  loaded._compile(built.outputFiles[0].text, loaded.id);
  return loaded.exports;
};
