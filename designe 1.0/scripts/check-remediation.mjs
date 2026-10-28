import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

const exports = {};
const source = readFileSync(new URL('../lib/ix-live.ts', import.meta.url), 'utf8');
new Function('exports', 'require', ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports, name => {
  if (name === 'server-only') return {};
  if (name === './pilot') return {PilotError:class extends Error {}};
  if (name === './pilot-contract') return {};
  throw new Error(name);
});
const {recommendationHref, verificationLabel} = exports;
const details = new URL(recommendationHref('ws_42', {cursor:'o50',rec:'rec_8'}), 'https://example.test');
assert.equal(details.pathname, '/workspace/recommendations');
assert.equal(details.searchParams.get('cursor'), 'o50');
assert.equal(details.searchParams.get('rec'), 'rec_8');
const closed = new URL(recommendationHref('ws_42', {cursor:'o50'}), details);
assert.equal(closed.searchParams.get('cursor'), 'o50');
assert.equal(closed.searchParams.get('rec'), null);
assert.equal(new URL(recommendationHref('ws_42'), details).searchParams.get('cursor'), null);
assert.equal(new URL(recommendationHref('ws_42', {cursor:'o50&rec=rec_9'}), details).searchParams.get('cursor'), 'o50&rec=rec_9');
assert.match(verificationLabel({status:'unavailable',reason:'verification_worker_not_implemented'}), /не подключена/i);
assert.match(verificationLabel({status:'confirmed',reason:'excluded_sites_present'}), /источнике/i);
assert.doesNotMatch(verificationLabel({status:'unknown',reason:'private_machine_code'}), /private_machine_code/);
console.log('PASS recommendation pagination links and safe verification messages');
