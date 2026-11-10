import { fileURLToPath } from 'node:url';
const map = {
  schema: 'stubs/schema.mjs', ops: 'stubs/ops.mjs', mathServer: 'stubs/mathServer.mjs',
  diff: 'stubs/diff.mjs', describe: 'stubs/describe.mjs', fieldChanges: 'stubs/fieldChanges.mjs',
};
export async function resolve(specifier, context, next) {
  if (specifier.includes('engine/dist/')) {
    const name = specifier.split('engine/dist/')[1].replace(/\.js$/, '');
    if (map[name]) return { url: new URL('./' + map[name], import.meta.url).href, shortCircuit: true };
  }
  return next(specifier, context);
}
